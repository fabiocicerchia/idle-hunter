"""The only code that calls boto3: one _scan_* per resource kind."""

from collections.abc import Iterator
from typing import Any

from idle_hunter_lib.metrics import LB_NAMESPACES, cw_sum
from idle_hunter_lib.models import Finding, finding
from idle_hunter_lib.pricing import price_is_live, rds_shape
from idle_hunter_lib.score import (
    age_days,
    score_empty_lb,
    score_idle_nat,
    score_idle_rds,
    score_stale_snapshot,
    score_unassociated_eip,
    score_unattached_eni,
    score_unattached_volume,
    score_unused_ami,
)
from idle_hunter_lib.types import Client, PriceOf, Resource


def _pages(client: Client, op: str, key: str, **kwargs: Any) -> Iterator[Resource]:
    for page in client.get_paginator(op).paginate(**kwargs):
        yield from page[key]


def _scan_volumes(ec2: Client, region: str, price_of: PriceOf) -> tuple[list[Finding], set[str]]:
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
                command=f"aws ec2 delete-volume --region {region} --volume-id {vol['VolumeId']}",
                tags=vol.get("Tags"),
            )
        )
    return findings, live_ids


def _scan_eips(ec2: Client, region: str, price_of: PriceOf) -> list[Finding]:
    return [
        finding(
            "eip-unassociated",
            addr.get("AllocationId", addr.get("PublicIp", "?")),
            region,
            score_unassociated_eip(addr),
            price_of("eip"),
            f"elastic IP {addr.get('PublicIp')} not associated",
            command=f"aws ec2 release-address --region {region} --allocation-id {addr.get('AllocationId')}",
            tags=addr.get("Tags"),
        )
        for addr in ec2.describe_addresses()["Addresses"]
        if "AssociationId" not in addr
    ]


def _scan_enis(ec2: Client, region: str, price_of: PriceOf) -> list[Finding]:
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
                command=f"aws ec2 delete-network-interface --region {region} --network-interface-id {eni_id}",
                tags=eni.get("TagSet"),
            )
        )
    return findings


def _scan_rds(rds: Client, cw: Client, region: str, price_of: PriceOf) -> list[Finding]:
    findings = []
    for db in _pages(rds, "describe_db_instances", "DBInstances"):
        if db.get("DBInstanceStatus") != "available":
            continue
        name = db["DBInstanceIdentifier"]
        conns = cw_sum(cw, "AWS/RDS", "DatabaseConnections", [("DBInstanceIdentifier", name)])
        score = score_idle_rds(db, conns)
        if not score:
            continue
        instance_class = db.get("DBInstanceClass", "?")
        # The four filters that identify this instance's SKU. With --live-pricing
        # they resolve the real class; without them the finding says so rather
        # than presenting the baseline as if it were this instance's bill.
        shape = rds_shape(db)
        monthly = price_of("rds", **shape)
        cost = (
            f"priced as {instance_class} {shape['deploymentOption']} on-demand"
            if price_is_live("rds", region, **shape)
            else f"cost shown is a db.t3.medium baseline, scale it for {instance_class}"
        )
        findings.append(
            finding(
                "rds-idle",
                name,
                region,
                score,
                monthly,
                f"{instance_class} {db.get('Engine', '?')} took {int(conns)} connection(s) in 30d ({cost})",
                command=f"aws rds delete-db-instance --region {region} --db-instance-identifier {name} "
                f"--final-db-snapshot-identifier {name}-final",
                tags=db.get("TagList"),
            )
        )
    return findings


def _registered_targets(elb: Client, lb_arn: str) -> int:
    """Targets registered across every target group of one load balancer."""
    total = 0
    for tg in elb.describe_target_groups(LoadBalancerArn=lb_arn)["TargetGroups"]:
        health = elb.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])
        total += len(health["TargetHealthDescriptions"])
    return total


def _scan_load_balancers(elb: Client, cw: Client, region: str, price_of: PriceOf) -> list[Finding]:
    findings = []
    for lb in _pages(elb, "describe_load_balancers", "LoadBalancers"):
        targets = _registered_targets(elb, lb["LoadBalancerArn"])
        traffic = None
        if not targets and lb["Type"] in LB_NAMESPACES:
            traffic = cw_sum(
                cw,
                LB_NAMESPACES[lb["Type"]],
                "ProcessedBytes",
                [("LoadBalancer", lb["LoadBalancerArn"].split("loadbalancer/")[-1])],
            )
        score = score_empty_lb(lb, targets, traffic)
        if not score:
            continue
        idle_note = ", no traffic in 30d" if traffic == 0 else ""
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
                f"{lb['Type']} LB with 0 registered targets{idle_note}",
                command=f"aws elbv2 delete-load-balancer --region {region} --load-balancer-arn {lb['LoadBalancerArn']}",
                tags=tags,
            )
        )
    return findings


def _scan_nat_gateways(ec2: Client, cw: Client, region: str, price_of: PriceOf) -> list[Finding]:
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
        if not score:
            continue
        mib = (out or 0) / 1024**2
        findings.append(
            finding(
                "nat-idle",
                nat_id,
                region,
                score,
                price_of("nat"),
                f"NAT gateway sent {mib:.1f} MiB in 30d, up {age_days(nat['CreateTime'])}d",
                command=f"aws ec2 delete-nat-gateway --region {region} --nat-gateway-id {nat_id}",
                tags=nat.get("Tags"),
            )
        )
    return findings


def _backing_snapshots(image: Resource) -> tuple[set[str], int]:
    """The snapshot ids an AMI is built from, and their total size in GiB."""
    # Bound separately, not as `snapshot_ids, gb = set(), 0`: the pinned
    # greenlint (v0.1.4) only reads single-name assignments when it works out
    # what a name holds, so the tuple form left `gb` untyped and `gb += ...`
    # below read as a sequence rebuild (GL007) rather than the integer sum it
    # is. Fixed upstream in greenlint v0.8.3, which destructures tuple targets.
    snapshot_ids = set()
    gb = 0
    for bdm in image.get("BlockDeviceMappings", []):
        ebs = bdm.get("Ebs", {})
        if "SnapshotId" in ebs:
            snapshot_ids.add(ebs["SnapshotId"])
            gb += ebs.get("VolumeSize", 0)
    return snapshot_ids, gb


def _scan_images(ec2: Client, region: str, price_of: PriceOf) -> tuple[list[Finding], set[str]]:
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
        snapshot_ids, gb = _backing_snapshots(image)
        ami_snapshots |= snapshot_ids
        score = score_unused_ami(image, image["ImageId"] in in_use)
        if not score:
            continue
        findings.append(
            finding(
                "ami-unused",
                image["ImageId"],
                region,
                score,
                gb * price_of("snapshot_gb"),
                f"{image.get('Name', 'unnamed')}: no instance uses it, "
                f"registered {age_days(image['CreationDate'])}d ago, {gb} GiB of snapshots",
                command=f"aws ec2 deregister-image --region {region} --image-id {image['ImageId']}",
                tags=image.get("Tags"),
            )
        )
    return findings, ami_snapshots


def _scan_snapshots(
    ec2: Client, region: str, price_of: PriceOf, live_volume_ids: set[str], ami_snapshots: set[str]
) -> list[Finding]:
    findings = []
    for snap in _pages(ec2, "describe_snapshots", "Snapshots", OwnerIds=["self"]):
        if snap["SnapshotId"] in ami_snapshots:
            continue  # backing a registered AMI — that AMI is the finding, not this
        gb = snap.get("VolumeSize", 0)
        score = score_stale_snapshot(snap, snap.get("VolumeId") in live_volume_ids)
        if not score:
            continue
        findings.append(
            finding(
                "snapshot-orphaned",
                snap["SnapshotId"],
                region,
                score,
                gb * price_of("snapshot_gb"),
                f"{gb} GiB, source {snap.get('VolumeId', '?')} no longer exists, "
                f"taken {age_days(snap['StartTime'])}d ago",
                command=f"aws ec2 delete-snapshot --region {region} --snapshot-id {snap['SnapshotId']}",
                tags=snap.get("Tags"),
            )
        )
    return findings
