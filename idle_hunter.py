#!/usr/bin/env python3
"""idle-hunter — find zombie AWS resources with a confidence-to-delete score.

Checks:
  * unattached EBS volumes           (age-weighted)
  * unassociated Elastic IPs
  * load balancers with no targets   (CloudWatch-confirmed idle)
  * idle NAT gateways                (CloudWatch bytes)
  * snapshots whose source volume is gone
  * self-owned AMIs no instance uses

Every finding gets a 0-100 confidence score; nothing is ever deleted — the
output is a report (optionally with ready-to-review `aws` CLI commands).

  idle-hunter scan --region eu-west-1
  idle-hunter scan --all-regions --min-confidence 80 --commands
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
PRICE_DEFAULTS = {
    "ebs_gb": 0.08,
    "snapshot_gb": 0.05,
    "eip": 3.6,
    "elb": 18.0,
    "nat": 32.9,
    # An unattached ENI is free. It is still worth reporting: it pins the subnet
    # and security group it references, so it blocks their deletion.
    "eni": 0.0,
    # RDS price is dominated by instance class, which this estimate cannot know —
    # db.t3.medium single-AZ on-demand as a baseline. --live-pricing resolves the
    # real class; without it the finding names the class so the reader can scale.
    "rds": 60.0,
}

# key -> (pricing service code, TERM_MATCH filters, months-per-unit multiplier)
#
# A filter value of None is a hole filled at call time from price()'s keyword
# arguments. RDS needs them: unlike a gigabyte or an idle NAT gateway it has no
# single per-unit rate — class, engine, deployment and licence each move the
# price, and none is known until the instance is in hand.
PRICE_QUERIES = {
    "ebs_gb": ("AmazonEC2", (("productFamily", "Storage"), ("volumeApiName", "gp3")), 1),
    "snapshot_gb": ("AmazonEC2", (("productFamily", "Storage Snapshot"),), 1),
    "eip": ("AmazonEC2", (("productFamily", "IP Address"),), 730),
    "elb": ("AWSELB", (("productFamily", "Load Balancer-Application"),), 730),
    "nat": ("AmazonEC2", (("productFamily", "NAT Gateway"),), 730),
    "rds": (
        "AmazonRDS",
        (
            ("productFamily", "Database Instance"),
            ("instanceType", None),
            ("databaseEngine", None),
            ("deploymentOption", None),
            ("licenseModel", None),
        ),
        730,
    ),
}

# describe_db_instances reports the engine as an API token; the Pricing API wants
# the marketing name. Oracle and SQL Server arrive edition-suffixed (oracle-ee,
# sqlserver-ex), so those match on the family prefix.
RDS_ENGINE_NAMES = {
    "aurora-mysql": "Aurora MySQL",
    "aurora-postgresql": "Aurora PostgreSQL",
    "mariadb": "MariaDB",
    "mysql": "MySQL",
    "postgres": "PostgreSQL",
}
RDS_ENGINE_PREFIXES = (("oracle", "Oracle"), ("sqlserver", "SQL Server"), ("db2", "Db2"))

# Only the two paid licence models have their own name upstream; every
# open-source engine prices as "No license required" whatever token it reports.
RDS_LICENCE_NAMES = {
    "license-included": "License included",
    "bring-your-own-license": "Bring your own license",
}


def rds_engine_name(engine):
    """Pricing API `databaseEngine` for an RDS engine token, or None if unknown.

    None means "do not guess". A wrong engine name still matches a real SKU, so
    the instance would be priced confidently as something it is not — worse than
    falling back to a baseline the finding admits is a baseline.
    """
    engine = (engine or "").lower()
    if engine in RDS_ENGINE_NAMES:
        return RDS_ENGINE_NAMES[engine]
    for prefix, name in RDS_ENGINE_PREFIXES:
        if engine.startswith(prefix):
            return name
    return None


def rds_shape(db):
    """The four Pricing API filters that identify one instance's SKU."""
    return {
        "instanceType": db.get("DBInstanceClass"),
        "databaseEngine": rds_engine_name(db.get("Engine")),
        "deploymentOption": "Multi-AZ" if db.get("MultiAZ") else "Single-AZ",
        "licenseModel": RDS_LICENCE_NAMES.get(db.get("LicenseModel", ""), "No license required"),
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


def _cache_key(key, region, params):
    return (key, region, tuple(sorted(params.items())))


def price(key, region, session=None, live=False, **params):
    """Monthly USD per unit — Pricing API when `live`, else the built-in estimate.

    `params` fill the None holes in this key's PRICE_QUERIES filters. A hole left
    unfilled falls back to the estimate rather than querying without it: a
    partial filter set matches some other shape's SKU and prices the wrong thing.
    """
    if not live or key not in PRICE_QUERIES:
        return PRICE_DEFAULTS[key]
    ck = _cache_key(key, region, params)
    if ck not in _PRICE_CACHE:
        service, filters, months = PRICE_QUERIES[key]
        resolved = tuple((k, params.get(k) if v is None else v) for k, v in filters)
        found = None
        if all(v for _, v in resolved):
            try:
                found = _lookup_price(session, service, resolved + (("regionCode", region),))
            except Exception:  # no pricing:GetProducts, or an unpriced shape — fall back
                found = None
        _PRICE_CACHE[ck] = (found * months, True) if found else (PRICE_DEFAULTS[key], False)
    return _PRICE_CACHE[ck][0]


def price_is_live(key, region, **params):
    """Whether the price already resolved for these arguments came from the API.

    Read after price(), so a finding can say which of the two numbers the reader
    is looking at instead of implying a measurement that never happened.
    """
    entry = _PRICE_CACHE.get(_cache_key(key, region, params))
    return bool(entry and entry[1])


# --- CloudWatch -------------------------------------------------------------
def cw_sum(cw, namespace, metric, dimensions, days=30):
    """Summed metric over `days`, or None when the metric reported nothing at all.

    None means "unknown", not "idle" — a resource with no datapoints may simply
    predate the metric or not publish it, and must not be scored as dead.
    """
    end = datetime.now(timezone.utc)
    resp = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric,
        Dimensions=[{"Name": k, "Value": v} for k, v in dimensions],
        StartTime=end - timedelta(days=days),
        EndTime=end,
        Period=86400,
        Statistics=["Sum"],
    )
    points = resp.get("Datapoints", [])
    return sum(p["Sum"] for p in points) if points else None


# --- scoring (pure) ---------------------------------------------------------
NAT_IDLE_BYTES = 10 * 1024**2  # 30d of DNS/health-check noise, not real traffic
RDS_IDLE_CONNECTIONS = 30  # 30d: a monitoring probe once a day, not an application


def score_unattached_volume(vol):
    """Unattached EBS volume: base 50, +age, +unnamed, capped 95."""
    score = 50
    days = age_days(vol["CreateTime"])
    score += min(days // 7 * 5, 35)  # +5/week unattached-ish, cap +35
    if not any(t["Key"] == "Name" for t in vol.get("Tags", [])):
        score += 10  # unnamed → likely forgotten
    return min(score, 95)


def score_unassociated_eip(_addr):
    return 90  # unassociated EIPs cost money and have no state to lose


def score_unattached_eni(eni):
    """Detached ENI: 85 when it is yours, 0 when a service owns it.

    `RequesterManaged` means some AWS service (RDS, Lambda, an ELB node, a VPC
    endpoint) created this interface and is responsible for it. Those look
    exactly like abandoned interfaces and deleting one breaks the service that
    owns it, so they score 0 rather than a lowered number — this is not a
    confidence judgement, it is the wrong resource.
    """
    if eni.get("Status") != "available":
        return 0
    if eni.get("RequesterManaged"):
        return 0
    return 85


def score_idle_rds(_db, connections_30d):
    """RDS instance: 80 at zero connections in 30d, 55 below the noise floor, else 0.

    `None` means CloudWatch returned nothing — unknown, not idle — so it scores
    0 for the same reason `score_idle_nat` does: a database is the last thing
    that should be deleted on missing evidence.
    """
    if connections_30d is None or connections_30d > RDS_IDLE_CONNECTIONS:
        return 0
    return 80 if connections_30d == 0 else 55


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


def score_stale_snapshot(snap, source_exists):
    """Snapshot whose source volume is gone: base 45, +5 per 30d, capped 80."""
    if source_exists:
        return 0
    return min(45 + age_days(snap["StartTime"]) // 30 * 5, 80)


def score_unused_ami(image, in_use):
    """Self-owned AMI no instance runs: base 40, +5 per 30d, capped 75."""
    if in_use:
        return 0
    return min(40 + age_days(image["CreationDate"]) // 30 * 5, 75)


def finding(kind, rid, region, score, monthly_usd, note, command=None, tags=None):
    if iac_managed(tags):
        score = max(score - IAC_PENALTY, 5)
        note += " — IaC-managed (delete via the stack, not the CLI)"
    return {
        "kind": kind,
        "id": rid,
        "region": region,
        "confidence": score,
        "monthly_usd": round(monthly_usd, 2),
        "note": note,
        "command": command,
    }


# --- the AWS half -----------------------------------------------------------
def _pages(client, op, key, **kwargs):
    for page in client.get_paginator(op).paginate(**kwargs):
        yield from page[key]


def _scan_volumes(ec2, region, price_of):
    """Unattached volumes, plus the id set every live volume is in (for snapshots)."""
    findings, live_ids = [], set()
    for vol in _pages(ec2, "describe_volumes", "Volumes"):
        live_ids.add(vol["VolumeId"])
        if vol["Status"] != "available":
            continue
        gb = vol["Size"]
        findings.append(
            finding(
                "ebs-unattached",
                vol["VolumeId"],
                region,
                score_unattached_volume(vol),
                gb * price_of("ebs_gb"),
                f"{gb} GiB, created {age_days(vol['CreateTime'])}d ago, status=available",
                f"aws ec2 delete-volume --region {region} --volume-id {vol['VolumeId']}",
                vol.get("Tags"),
            )
        )
    return findings, live_ids


def _scan_eips(ec2, region, price_of):
    return [
        finding(
            "eip-unassociated",
            addr.get("AllocationId", addr.get("PublicIp", "?")),
            region,
            score_unassociated_eip(addr),
            price_of("eip"),
            f"elastic IP {addr.get('PublicIp')} not associated",
            f"aws ec2 release-address --region {region} --allocation-id {addr.get('AllocationId')}",
            addr.get("Tags"),
        )
        for addr in ec2.describe_addresses()["Addresses"]
        if "AssociationId" not in addr
    ]


def _scan_enis(ec2, region, price_of):
    findings = []
    for eni in _pages(
        ec2,
        "describe_network_interfaces",
        "NetworkInterfaces",
        Filters=[{"Name": "status", "Values": ["available"]}],
    ):
        score = score_unattached_eni(eni)
        if not score:
            continue
        eni_id = eni["NetworkInterfaceId"]
        desc = (eni.get("Description") or "").strip() or "no description"
        findings.append(
            finding(
                "eni-unattached",
                eni_id,
                region,
                score,
                price_of("eni"),
                f"detached network interface in {eni.get('SubnetId', '?')} ({desc}) — "
                f"free, but it pins its subnet and security groups",
                f"aws ec2 delete-network-interface --region {region} "
                f"--network-interface-id {eni_id}",
                eni.get("TagSet"),
            )
        )
    return findings


def _scan_rds(rds, cw, region, price_of):
    findings = []
    for db in _pages(rds, "describe_db_instances", "DBInstances"):
        if db.get("DBInstanceStatus") != "available":
            continue
        name = db["DBInstanceIdentifier"]
        conns = cw_sum(cw, "AWS/RDS", "DatabaseConnections", [("DBInstanceIdentifier", name)])
        score = score_idle_rds(db, conns)
        if not score:
            continue
        klass = db.get("DBInstanceClass", "?")
        shape = rds_shape(db)
        monthly = price_of("rds", **shape)
        cost = (
            f"priced as {klass} {shape['deploymentOption']} on-demand"
            if price_is_live("rds", region, **shape)
            else f"cost shown is a db.t3.medium baseline, scale it for {klass}"
        )
        findings.append(
            finding(
                "rds-idle",
                name,
                region,
                score,
                monthly,
                f"{klass} {db.get('Engine', '?')} took {int(conns)} connection(s) in 30d ({cost})",
                f"aws rds delete-db-instance --region {region} --db-instance-identifier {name} "
                f"--final-db-snapshot-identifier {name}-final",
                db.get("TagList"),
            )
        )
    return findings


LB_NAMESPACES = {
    "application": "AWS/ApplicationELB",
    "network": "AWS/NetworkELB",
    "gateway": "AWS/GatewayELB",
}


def _scan_load_balancers(elb, cw, region, price_of):
    findings = []
    for lb in _pages(elb, "describe_load_balancers", "LoadBalancers"):
        targets = 0
        for tg in elb.describe_target_groups(LoadBalancerArn=lb["LoadBalancerArn"])["TargetGroups"]:
            targets += len(
                elb.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])[
                    "TargetHealthDescriptions"
                ]
            )
        traffic = None
        if not targets and lb["Type"] in LB_NAMESPACES:
            traffic = cw_sum(
                cw,
                LB_NAMESPACES[lb["Type"]],
                "ProcessedBytes",
                [("LoadBalancer", lb["LoadBalancerArn"].split("loadbalancer/")[-1])],
            )
        score = score_empty_lb(lb, targets, traffic)
        if score:
            idle = ", no traffic in 30d" if traffic == 0 else ""
            tags = elb.describe_tags(  # not in describe_load_balancers; only fetched for findings
                ResourceArns=[lb["LoadBalancerArn"]]
            )["TagDescriptions"][0]["Tags"]
            findings.append(
                finding(
                    "elb-no-targets",
                    lb["LoadBalancerName"],
                    region,
                    score,
                    price_of("elb"),
                    f"{lb['Type']} LB with 0 registered targets{idle}",
                    f"aws elbv2 delete-load-balancer --region {region} "
                    f"--load-balancer-arn {lb['LoadBalancerArn']}",
                    tags,
                )
            )
    return findings


def _scan_nat_gateways(ec2, cw, region, price_of):
    findings = []
    for nat in _pages(
        ec2,
        "describe_nat_gateways",
        "NatGateways",
        Filter=[{"Name": "state", "Values": ["available"]}],
    ):
        nat_id = nat["NatGatewayId"]
        out = cw_sum(cw, "AWS/NATGateway", "BytesOutToDestination", [("NatGatewayId", nat_id)])
        score = score_idle_nat(nat, out)
        if score:
            mib = (out or 0) / 1024**2
            findings.append(
                finding(
                    "nat-idle",
                    nat_id,
                    region,
                    score,
                    price_of("nat"),
                    f"NAT gateway sent {mib:.1f} MiB in 30d, up {age_days(nat['CreateTime'])}d",
                    f"aws ec2 delete-nat-gateway --region {region} --nat-gateway-id {nat_id}",
                    nat.get("Tags"),
                )
            )
    return findings


def _scan_images(ec2, region, price_of):
    """Self-owned AMIs no instance uses, plus the snapshot ids AMIs still back."""
    in_use = {
        inst["ImageId"]
        for res in _pages(ec2, "describe_instances", "Reservations")
        for inst in res["Instances"]
        if inst["State"]["Name"] != "terminated"
    }
    # ponytail: instances only. AMIs referenced solely by launch templates or ASGs
    # still read as unused — add those lookups if that produces false positives.
    findings, ami_snapshots = [], set()
    for image in _pages(ec2, "describe_images", "Images", Owners=["self"]):
        gb = 0
        for bdm in image.get("BlockDeviceMappings", []):
            ebs = bdm.get("Ebs", {})
            if "SnapshotId" in ebs:
                ami_snapshots.add(ebs["SnapshotId"])
                gb += ebs.get("VolumeSize", 0)
        score = score_unused_ami(image, image["ImageId"] in in_use)
        if score:
            findings.append(
                finding(
                    "ami-unused",
                    image["ImageId"],
                    region,
                    score,
                    gb * price_of("snapshot_gb"),
                    f"{image.get('Name', 'unnamed')}: no instance uses it, "
                    f"registered {age_days(image['CreationDate'])}d ago, {gb} GiB of snapshots",
                    f"aws ec2 deregister-image --region {region} --image-id {image['ImageId']}",
                    image.get("Tags"),
                )
            )
    return findings, ami_snapshots


def _scan_snapshots(ec2, region, price_of, live_volume_ids, ami_snapshots):
    findings = []
    for snap in _pages(ec2, "describe_snapshots", "Snapshots", OwnerIds=["self"]):
        if snap["SnapshotId"] in ami_snapshots:
            continue  # backing a registered AMI — that AMI is the finding, not this
        gb = snap.get("VolumeSize", 0)
        score = score_stale_snapshot(snap, snap.get("VolumeId") in live_volume_ids)
        if score:
            findings.append(
                finding(
                    "snapshot-orphaned",
                    snap["SnapshotId"],
                    region,
                    score,
                    gb * price_of("snapshot_gb"),
                    f"{gb} GiB, source {snap.get('VolumeId', '?')} no longer exists, "
                    f"taken {age_days(snap['StartTime'])}d ago",
                    f"aws ec2 delete-snapshot --region {region} --snapshot-id {snap['SnapshotId']}",
                    snap.get("Tags"),
                )
            )
    return findings


def scan_region(region, session=None, live_pricing=False):
    import boto3

    session = session or boto3.Session()
    ec2 = session.client("ec2", region_name=region)
    elb = session.client("elbv2", region_name=region)
    cw = session.client("cloudwatch", region_name=region)
    rds = session.client("rds", region_name=region)
    price_of = partial(price, region=region, session=session, live=live_pricing)

    volumes, live_volume_ids = _scan_volumes(ec2, region, price_of)
    images, ami_snapshots = _scan_images(ec2, region, price_of)
    return (
        volumes
        + images
        + _scan_eips(ec2, region, price_of)
        + _scan_enis(ec2, region, price_of)
        + _scan_load_balancers(elb, cw, region, price_of)
        + _scan_nat_gateways(ec2, cw, region, price_of)
        + _scan_rds(rds, cw, region, price_of)
        + _scan_snapshots(ec2, region, price_of, live_volume_ids, ami_snapshots)
    )


def scan_regions(regions, session=None, live_pricing=False, workers=8, on_error=None):
    """Scan several regions concurrently.

    Each worker builds its own boto3 Session: Session objects are not
    thread-safe, and sharing one across a pool is the classic way to get
    intermittent credential errors under load.

    A region that fails is reported and skipped rather than aborting the sweep —
    but the caller is told, because a report that quietly lost a region reads
    exactly like a clean estate. Returns `(findings, failed_regions)`.
    """
    if len(regions) == 1:
        return scan_region(regions[0], session, live_pricing), []

    findings, failed = [], []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(regions)))) as pool:
        pending = {pool.submit(scan_region, r, None, live_pricing): r for r in regions}
        for future in as_completed(pending):
            region = pending[future]
            try:
                findings.extend(future.result())
            except Exception as exc:  # one bad region must not lose the other 30
                failed.append(region)
                if on_error:
                    on_error(region, exc)
                else:
                    print(f"warning: {region}: {exc}", file=sys.stderr)
    return findings, failed


def render(findings, min_confidence=0, show_commands=False):
    rows = [f for f in findings if f["confidence"] >= max(min_confidence, 1)]
    rows.sort(key=lambda f: (-f["confidence"], -f["monthly_usd"]))
    total = sum(f["monthly_usd"] for f in rows)
    lines = [f"# idle-hunter report — {len(rows)} finding(s), ~${total:,.0f}/mo reclaimable\n"]
    for f in rows:
        lines.append(
            f"[{f['confidence']:3d}%] {f['kind']}  {f['id']}  "
            f"({f['region']})  ~${f['monthly_usd']}/mo"
        )
        lines.append(f"       {f['note']}")
        if show_commands and f.get("command"):
            lines.append(f"       $ {f['command']}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="idle-hunter",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scan for zombie resources")
    s.add_argument("--region", default="us-east-1")
    s.add_argument("--all-regions", action="store_true")
    s.add_argument("--min-confidence", type=int, default=0)
    s.add_argument(
        "--commands", action="store_true", help="print deletion commands (never executed)"
    )
    s.add_argument(
        "--live-pricing",
        action="store_true",
        help="look up real prices via the Pricing API (needs pricing:GetProducts)",
    )
    s.add_argument(
        "--workers",
        type=int,
        default=8,
        metavar="N",
        help="regions scanned in parallel with --all-regions (default 8; "
        "lower it if the account is being throttled)",
    )
    s.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    import boto3

    session = boto3.Session()
    regions = [args.region]
    if args.all_regions:
        ec2 = session.client("ec2", region_name="us-east-1")
        regions = [r["RegionName"] for r in ec2.describe_regions()["Regions"]]

    findings, failed = scan_regions(regions, session, args.live_pricing, args.workers)
    # Completion order is non-deterministic once regions run in parallel, so
    # sort before emitting: two runs over the same estate must diff cleanly.
    findings.sort(key=lambda f: (f["region"], f["kind"], str(f["id"])))

    if args.json:
        # --min-confidence applies here too: a script generated from this output
        # must not contain deletes the caller asked to be filtered out.
        json.dump(
            [f for f in findings if f["confidence"] >= args.min_confidence],
            sys.stdout,
            indent=2,
            default=str,
        )
    else:
        print(render(findings, args.min_confidence, args.commands))

    if failed:
        print(
            f"\nwarning: {len(failed)} region(s) failed and are missing from this "
            f"report: {', '.join(sorted(failed))}",
            file=sys.stderr,
        )
        return 3  # partial results — never let a lost region look like a clean estate
    return 0


if __name__ == "__main__":
    sys.exit(main())
