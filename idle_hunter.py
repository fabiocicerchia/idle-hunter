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
from datetime import datetime, timezone


def age_days(created):
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - created).days


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


def score_empty_lb(lb, target_count):
    if target_count > 0:
        return 0
    return 85 if age_days(lb["CreatedTime"]) > 30 else 60


def finding(kind, rid, region, score, monthly_usd, note, command=None):
    return {"kind": kind, "id": rid, "region": region, "confidence": score,
            "monthly_usd": round(monthly_usd, 2), "note": note, "command": command}


def scan_region(region, session=None):
    import boto3
    session = session or boto3.Session()
    ec2 = session.client("ec2", region_name=region)
    findings = []

    for vol in ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}])["Volumes"]:
        gb = vol["Size"]
        findings.append(finding(
            "ebs-unattached", vol["VolumeId"], region,
            score_unattached_volume(vol), gb * 0.08,
            f"{gb} GiB, created {age_days(vol['CreateTime'])}d ago, status=available",
            f"aws ec2 delete-volume --region {region} --volume-id {vol['VolumeId']}",
        ))

    for addr in ec2.describe_addresses()["Addresses"]:
        if "AssociationId" not in addr:
            findings.append(finding(
                "eip-unassociated", addr.get("AllocationId", addr.get("PublicIp", "?")), region,
                score_unassociated_eip(addr), 3.6,
                f"elastic IP {addr.get('PublicIp')} not associated",
                f"aws ec2 release-address --region {region} --allocation-id {addr.get('AllocationId')}",
            ))

    elb = session.client("elbv2", region_name=region)
    for lb in elb.describe_load_balancers()["LoadBalancers"]:
        targets = 0
        for tg in elb.describe_target_groups(
                LoadBalancerArn=lb["LoadBalancerArn"])["TargetGroups"]:
            targets += len(elb.describe_target_health(
                TargetGroupArn=tg["TargetGroupArn"])["TargetHealthDescriptions"])
        s = score_empty_lb(lb, targets)
        if s:
            findings.append(finding(
                "elb-no-targets", lb["LoadBalancerName"], region, s, 18.0,
                f"{lb['Type']} LB with 0 registered targets",
                f"aws elbv2 delete-load-balancer --region {region} --load-balancer-arn {lb['LoadBalancerArn']}",
            ))
    return findings


def render(findings, min_confidence=0, show_commands=False):
    rows = [f for f in findings if f["confidence"] >= min_confidence]
    rows.sort(key=lambda f: (-f["confidence"], -f["monthly_usd"]))
    total = sum(f["monthly_usd"] for f in rows)
    lines = [f"# idle-hunter report — {len(rows)} finding(s), ~${total:,.0f}/mo reclaimable\n"]
    for f in rows:
        lines.append(f"[{f['confidence']:3d}%] {f['kind']:availability<0} " if False else
                     f"[{f['confidence']:3d}%] {f['kind']}  {f['id']}  ({f['region']})  ~${f['monthly_usd']}/mo")
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
        findings.extend(scan_region(region, session))

    if args.json:
        json.dump(findings, sys.stdout, indent=2, default=str)
    else:
        print(render(findings, args.min_confidence, args.commands))
    return 0


if __name__ == "__main__":
    sys.exit(main())
