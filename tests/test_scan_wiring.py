"""Wiring smoke test: a fake boto3 session that yields one of every finding kind.

The AWS calls are not the point — the cross-check dependencies are: a snapshot
is only orphaned if its volume is absent from the volume scan, and only if no
AMI still backs it.
"""
from datetime import datetime, timedelta, timezone

from idle_hunter import scan_region


def ago(n):
    return datetime.now(timezone.utc) - timedelta(days=n)


RESPONSES = {
    "describe_volumes": {"Volumes": [
        {"VolumeId": "vol-dead", "Size": 200, "Status": "available",
         "CreateTime": ago(210), "Tags": []},
        {"VolumeId": "vol-live", "Size": 10, "Status": "in-use", "CreateTime": ago(5)},
    ]},
    "describe_addresses": {"Addresses": [
        {"AllocationId": "eipalloc-1", "PublicIp": "52.1.2.3"},
        {"AllocationId": "eipalloc-2", "PublicIp": "52.1.2.4", "AssociationId": "eipassoc-1"},
    ]},
    "describe_nat_gateways": {"NatGateways": [
        {"NatGatewayId": "nat-idle", "CreateTime": ago(300), "Tags": []},
    ]},
    "describe_snapshots": {"Snapshots": [
        {"SnapshotId": "snap-orphan", "VolumeId": "vol-gone", "VolumeSize": 100,
         "StartTime": ago(400)},
        {"SnapshotId": "snap-live", "VolumeId": "vol-live", "VolumeSize": 10,
         "StartTime": ago(400)},
        {"SnapshotId": "snap-ami", "VolumeId": "vol-gone", "VolumeSize": 8,
         "StartTime": ago(400)},
    ]},
    "describe_images": {"Images": [
        {"ImageId": "ami-unused", "Name": "old-base", "CreationDate": "2020-01-01T00:00:00.000Z",
         "BlockDeviceMappings": [{"Ebs": {"SnapshotId": "snap-ami", "VolumeSize": 8}}]},
        {"ImageId": "ami-running", "Name": "prod", "CreationDate": "2024-01-01T00:00:00.000Z",
         "BlockDeviceMappings": []},
    ]},
    "describe_instances": {"Reservations": [
        {"Instances": [{"ImageId": "ami-running", "State": {"Name": "running"}},
                       {"ImageId": "ami-unused", "State": {"Name": "terminated"}}]},
    ]},
    "describe_load_balancers": {"LoadBalancers": [
        {"LoadBalancerName": "legacy-alb", "LoadBalancerArn": "arn:...:loadbalancer/app/legacy/abc",
         "Type": "application", "CreatedTime": ago(90)},
    ]},
    "describe_target_groups": {"TargetGroups": [{"TargetGroupArn": "arn:tg"}]},
    "describe_target_health": {"TargetHealthDescriptions": []},
    "describe_tags": {"TagDescriptions": [{"Tags": [{"Key": "managed-by", "Value": "terraform"}]}]},
    "get_metric_statistics": {"Datapoints": [{"Sum": 0.0}]},
}


class FakeClient:
    def __getattr__(self, op):
        def call(**_kw):
            return RESPONSES[op]
        return call

    def get_paginator(self, op):
        class P:
            paginate = staticmethod(lambda **_kw: [RESPONSES[op]])
        return P()


class FakeSession:
    def client(self, _name, **_kw):
        return FakeClient()


def test_scan_region_finds_one_of_each_kind():
    findings = scan_region("eu-west-1", FakeSession())
    by_kind = {f["kind"]: f for f in findings}

    assert set(by_kind) == {"ebs-unattached", "eip-unassociated", "elb-no-targets",
                            "nat-idle", "ami-unused", "snapshot-orphaned"}
    assert by_kind["ebs-unattached"]["id"] == "vol-dead"        # in-use volume is not a finding
    assert by_kind["ebs-unattached"]["confidence"] == 95
    assert by_kind["eip-unassociated"]["id"] == "eipalloc-1"    # associated EIP is not a finding
    assert by_kind["nat-idle"]["confidence"] == 85
    assert by_kind["ami-unused"]["id"] == "ami-unused"          # terminated instance doesn't count
    assert by_kind["elb-no-targets"]["confidence"] == 95 - 30   # zero traffic, terraform-tagged
    assert "IaC-managed" in by_kind["elb-no-targets"]["note"]


def test_only_genuinely_orphaned_snapshots_are_reported():
    orphans = [f for f in scan_region("eu-west-1", FakeSession())
               if f["kind"] == "snapshot-orphaned"]
    # snap-live's volume still exists; snap-ami is counted by the AMI finding instead
    assert [f["id"] for f in orphans] == ["snap-orphan"]


if __name__ == "__main__":
    for f in scan_region("eu-west-1", FakeSession()):
        print(f"{f['confidence']:3d} {f['kind']:20s} {f['id']:15s} ${f['monthly_usd']}")
