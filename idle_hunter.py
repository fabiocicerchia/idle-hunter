#!/usr/bin/env python3
"""idle-hunter — find zombie AWS resources with a confidence-to-delete score.

Checks (initial set):
  * unattached EBS volumes           (age-weighted)
  * unassociated Elastic IPs
  * load balancers with no targets
  * old EBS/RDS snapshots of deleted sources

Every finding gets a 0-100 confidence score; nothing is ever deleted — the
output is a report (optionally with ready-to-review `aws` CLI commands).

  idle-hunter scan --region eu-west-1
  idle-hunter scan --all-regions --min-confidence 80 --commands
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from functools import partial


def age_days(created):
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - created).days


# --- IaC ownership ----------------------------------------------------------
IAC_PENALTY = 30


def iac_managed(tags):
    """True if tags say a stack owns this — deleting it by hand just gets reverted."""
    for t in tags or []:
        key = t.get("Key", "").lower()
        val = str(t.get("Value", "")).lower()
        if key.startswith(("aws:cloudformation:", "elasticbeanstalk:", "eks:", "kubernetes.io/")):
            return True
        if "terraform" in key or "pulumi" in key or key.startswith("cdk"):
            return True
        if key.replace("_", "-") in ("managed-by", "provisioner", "iac", "created-by"):
            if any(x in val for x in ("terraform", "cloudformation", "cdk", "pulumi", "ansible")):
                return True
    return False


# --- pricing ----------------------------------------------------------------
# Rough us-east-1 list prices, monthly per unit. Used unless --live-pricing.
PRICE_DEFAULTS = {"ebs_gb": 0.08, "eip": 3.6, "elb": 18.0, "nat": 32.9}

# key -> (pricing service code, TERM_MATCH filters, months-per-unit multiplier)
PRICE_QUERIES = {
    "ebs_gb": ("AmazonEC2", (("productFamily", "Storage"), ("volumeApiName", "gp3")), 1),
    "eip": ("AmazonEC2", (("productFamily", "IP Address"),), 730),
    "elb": ("AWSELB", (("productFamily", "Load Balancer-Application"),), 730),
    "nat": ("AmazonEC2", (("productFamily", "NAT Gateway"),), 730),
}

_PRICE_CACHE = {}


def _lookup_price(session, service_code, filters):
    """First positive on-demand USD price matching `filters`, or None."""
    client = session.client("pricing", region_name="us-east-1")
    resp = client.get_products(
        ServiceCode=service_code,
        Filters=[{"Type": "TERM_MATCH", "Field": k, "Value": v} for k, v in filters],
        MaxResults=20,
    )
    for doc in resp.get("PriceList", []):
        for term in json.loads(doc).get("terms", {}).get("OnDemand", {}).values():
            for dim in term.get("priceDimensions", {}).values():
                price = float(dim.get("pricePerUnit", {}).get("USD", 0))
                if price > 0:
                    return price
    return None


def price(key, region, session=None, live=False):
    """Monthly USD per unit — Pricing API when `live`, else the built-in estimate."""
    if not live:
        return PRICE_DEFAULTS[key]
    if (key, region) not in _PRICE_CACHE:
        service, filters, months = PRICE_QUERIES[key]
        try:
            found = _lookup_price(session, service, filters + (("regionCode", region),))
        except Exception:  # no pricing:GetProducts, or an unpriced shape — fall back
            found = None
        _PRICE_CACHE[(key, region)] = found * months if found else PRICE_DEFAULTS[key]
    return _PRICE_CACHE[(key, region)]


# --- CloudWatch -------------------------------------------------------------
def cw_sum(cw, namespace, metric, dimensions, days=30):
    """Summed metric over `days`, or None when the metric reported nothing at all.

    None means "unknown", not "idle" — a resource with no datapoints may simply
    predate the metric or not publish it, and must not be scored as dead.
    """
    end = datetime.now(timezone.utc)
    resp = cw.get_metric_statistics(
        Namespace=namespace, MetricName=metric,
        Dimensions=[{"Name": k, "Value": v} for k, v in dimensions],
        StartTime=end - timedelta(days=days), EndTime=end,
        Period=86400, Statistics=["Sum"],
    )
    points = resp.get("Datapoints", [])
    return sum(p["Sum"] for p in points) if points else None


# --- scoring (pure) ---------------------------------------------------------
NAT_IDLE_BYTES = 10 * 1024 ** 2  # 30d of DNS/health-check noise, not real traffic


def score_unattached_volume(vol):
    """Unattached EBS volume: base 50, +age, +unnamed, capped 95."""
    score = 50
    days = age_days(vol["CreateTime"])
    score += min(days // 7 * 5, 35)                      # +5/week unattached-ish, cap +35
    if not any(t["Key"] == "Name" for t in vol.get("Tags", [])):
        score += 10                                      # unnamed → likely forgotten
    return min(score, 95)


def score_unassociated_eip(_addr):
    return 90  # unassociated EIPs cost money and have no state to lose


def score_empty_lb(lb, target_count, bytes_30d=None):
    """LB with no targets: 85 over 30d old else 60, +10 if CloudWatch confirms no traffic."""
    if target_count > 0:
        return 0
    score = 85 if age_days(lb["CreatedTime"]) > 30 else 60
    if bytes_30d == 0:
        score += 10
    return min(score, 95)


def score_idle_nat(_nat, bytes_30d):
    """NAT gateway: 85 at zero bytes out in 30d, 65 under the noise floor, else 0."""
    if bytes_30d is None or bytes_30d > NAT_IDLE_BYTES:
        return 0
    return 85 if bytes_30d == 0 else 65


def finding(kind, rid, region, score, monthly_usd, note, command=None, tags=None):
    if iac_managed(tags):
        score = max(score - IAC_PENALTY, 5)
        note += " — IaC-managed (delete via the stack, not the CLI)"
    return {"kind": kind, "id": rid, "region": region, "confidence": score,
            "monthly_usd": round(monthly_usd, 2), "note": note, "command": command}


# --- the AWS half -----------------------------------------------------------
def _pages(client, op, key, **kwargs):
    for page in client.get_paginator(op).paginate(**kwargs):
        yield from page[key]


def _scan_volumes(ec2, region, price_of):
    findings = []
    for vol in _pages(ec2, "describe_volumes", "Volumes",
                      Filters=[{"Name": "status", "Values": ["available"]}]):
        gb = vol["Size"]
        findings.append(finding(
            "ebs-unattached", vol["VolumeId"], region,
            score_unattached_volume(vol), gb * price_of("ebs_gb"),
            f"{gb} GiB, created {age_days(vol['CreateTime'])}d ago, status=available",
            f"aws ec2 delete-volume --region {region} --volume-id {vol['VolumeId']}",
            vol.get("Tags"),
        ))
    return findings


def _scan_eips(ec2, region, price_of):
    return [
        finding(
            "eip-unassociated", addr.get("AllocationId", addr.get("PublicIp", "?")), region,
            score_unassociated_eip(addr), price_of("eip"),
            f"elastic IP {addr.get('PublicIp')} not associated",
            f"aws ec2 release-address --region {region} --allocation-id {addr.get('AllocationId')}",
            addr.get("Tags"),
        )
        for addr in ec2.describe_addresses()["Addresses"] if "AssociationId" not in addr
    ]


LB_NAMESPACES = {"application": "AWS/ApplicationELB", "network": "AWS/NetworkELB",
                 "gateway": "AWS/GatewayELB"}


def _scan_load_balancers(elb, cw, region, price_of):
    findings = []
    for lb in _pages(elb, "describe_load_balancers", "LoadBalancers"):
        targets = 0
        for tg in elb.describe_target_groups(
                LoadBalancerArn=lb["LoadBalancerArn"])["TargetGroups"]:
            targets += len(elb.describe_target_health(
                TargetGroupArn=tg["TargetGroupArn"])["TargetHealthDescriptions"])
        traffic = None
        if not targets and lb["Type"] in LB_NAMESPACES:
            traffic = cw_sum(cw, LB_NAMESPACES[lb["Type"]], "ProcessedBytes",
                             [("LoadBalancer", lb["LoadBalancerArn"].split("loadbalancer/")[-1])])
        score = score_empty_lb(lb, targets, traffic)
        if score:
            idle = ", no traffic in 30d" if traffic == 0 else ""
            tags = elb.describe_tags(  # not in describe_load_balancers; only fetched for findings
                ResourceArns=[lb["LoadBalancerArn"]])["TagDescriptions"][0]["Tags"]
            findings.append(finding(
                "elb-no-targets", lb["LoadBalancerName"], region, score, price_of("elb"),
                f"{lb['Type']} LB with 0 registered targets{idle}",
                f"aws elbv2 delete-load-balancer --region {region} "
                f"--load-balancer-arn {lb['LoadBalancerArn']}",
                tags,
            ))
    return findings


def _scan_nat_gateways(ec2, cw, region, price_of):
    findings = []
    for nat in _pages(ec2, "describe_nat_gateways", "NatGateways",
                      Filter=[{"Name": "state", "Values": ["available"]}]):
        nat_id = nat["NatGatewayId"]
        out = cw_sum(cw, "AWS/NATGateway", "BytesOutToDestination", [("NatGatewayId", nat_id)])
        score = score_idle_nat(nat, out)
        if score:
            mib = (out or 0) / 1024 ** 2
            findings.append(finding(
                "nat-idle", nat_id, region, score, price_of("nat"),
                f"NAT gateway sent {mib:.1f} MiB in 30d, up {age_days(nat['CreateTime'])}d",
                f"aws ec2 delete-nat-gateway --region {region} --nat-gateway-id {nat_id}",
                nat.get("Tags"),
            ))
    return findings


def scan_region(region, session=None, live_pricing=False):
    import boto3
    session = session or boto3.Session()
    ec2 = session.client("ec2", region_name=region)
    elb = session.client("elbv2", region_name=region)
    cw = session.client("cloudwatch", region_name=region)
    price_of = partial(price, region=region, session=session, live=live_pricing)

    return (_scan_volumes(ec2, region, price_of)
            + _scan_eips(ec2, region, price_of)
            + _scan_load_balancers(elb, cw, region, price_of)
            + _scan_nat_gateways(ec2, cw, region, price_of))


def render(findings, min_confidence=0, show_commands=False):
    rows = [f for f in findings if f["confidence"] >= min_confidence]
    rows.sort(key=lambda f: (-f["confidence"], -f["monthly_usd"]))
    total = sum(f["monthly_usd"] for f in rows)
    lines = [f"# idle-hunter report — {len(rows)} finding(s), ~${total:,.0f}/mo reclaimable\n"]
    for f in rows:
        lines.append(f"[{f['confidence']:3d}%] {f['kind']}  {f['id']}  "
                     f"({f['region']})  ~${f['monthly_usd']}/mo")
        lines.append(f"       {f['note']}")
        if show_commands and f.get("command"):
            lines.append(f"       $ {f['command']}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="idle-hunter", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scan for zombie resources")
    s.add_argument("--region", default="us-east-1")
    s.add_argument("--all-regions", action="store_true")
    s.add_argument("--min-confidence", type=int, default=0)
    s.add_argument("--commands", action="store_true", help="print deletion commands (never executed)")
    s.add_argument("--live-pricing", action="store_true",
                   help="look up real prices via the Pricing API (needs pricing:GetProducts)")
    s.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    import boto3
    session = boto3.Session()
    regions = [args.region]
    if args.all_regions:
        ec2 = session.client("ec2", region_name="us-east-1")
        regions = [r["RegionName"] for r in ec2.describe_regions()["Regions"]]

    findings = []
    for region in regions:
        findings.extend(scan_region(region, session, args.live_pricing))

    if args.json:
        json.dump(findings, sys.stdout, indent=2, default=str)
    else:
        print(render(findings, args.min_confidence, args.commands))
    return 0


if __name__ == "__main__":
    sys.exit(main())
