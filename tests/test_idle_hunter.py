from datetime import datetime, timedelta, timezone

from idle_hunter import (
    NAT_IDLE_BYTES,
    finding,
    iac_managed,
    price,
    render,
    score_empty_lb,
    score_idle_nat,
    score_stale_snapshot,
    score_unattached_volume,
    score_unused_ami,
)


def days_ago(n):
    return datetime.now(timezone.utc) - timedelta(days=n)


def test_volume_score_grows_with_age_and_caps():
    young = {"CreateTime": days_ago(1), "Tags": [{"Key": "Name", "Value": "x"}]}
    old_unnamed = {"CreateTime": days_ago(365), "Tags": []}
    assert score_unattached_volume(young) < score_unattached_volume(old_unnamed) <= 95


def test_lb_score_zero_when_targets_exist():
    lb = {"CreatedTime": days_ago(90), "Type": "application"}
    assert score_empty_lb(lb, target_count=3) == 0
    assert score_empty_lb(lb, target_count=0) == 85


def test_lb_score_boosted_by_zero_traffic():
    lb = {"CreatedTime": days_ago(90), "Type": "application"}
    assert score_empty_lb(lb, 0, bytes_30d=0) == 95
    assert score_empty_lb(lb, 0, bytes_30d=None) == 85  # unknown ≠ idle
    assert score_empty_lb(lb, 0, bytes_30d=10_000) == 85


def test_nat_score_needs_a_metric():
    nat = {"CreateTime": days_ago(200)}
    assert score_idle_nat(nat, None) == 0  # no datapoints ≠ dead
    assert score_idle_nat(nat, 0) == 85
    assert score_idle_nat(nat, NAT_IDLE_BYTES - 1) == 65
    assert score_idle_nat(nat, NAT_IDLE_BYTES + 1) == 0


def test_snapshot_and_ami_scores():
    snap = {"StartTime": days_ago(400)}
    assert score_stale_snapshot(snap, source_exists=True) == 0
    assert score_stale_snapshot(snap, source_exists=False) == 80  # capped
    assert score_stale_snapshot({"StartTime": days_ago(1)}, False) == 45
    ami = {"CreationDate": "2020-01-01T00:00:00.000Z"}
    assert score_unused_ami(ami, in_use=True) == 0
    assert score_unused_ami(ami, in_use=False) == 75  # capped


def test_iac_managed_tags_lower_the_score():
    assert iac_managed([{"Key": "aws:cloudformation:stack-name", "Value": "prod"}])
    assert iac_managed([{"Key": "managed_by", "Value": "Terraform"}])
    assert not iac_managed([{"Key": "Name", "Value": "terraforming-mars"}])
    assert not iac_managed(None)
    f = finding(
        "ebs-unattached",
        "vol-1",
        "eu-west-1",
        90,
        8.0,
        "n",
        tags=[{"Key": "terraform:module", "Value": "vpc"}],
    )
    assert f.confidence == 60 and "IaC-managed" in f.note


def test_price_falls_back_to_estimates_without_live_lookup():
    assert price("elb", "eu-west-1") == 18.0

    class Boom:
        def client(self, *a, **k):
            raise RuntimeError("no pricing:GetProducts")

    assert price("elb", "eu-west-1", session=Boom(), live=True) == 18.0


def test_render_sorts_and_filters():
    fs = [
        finding("ebs-unattached", "vol-1", "eu-west-1", 60, 8.0, "n1"),
        finding("eip-unassociated", "eip-1", "eu-west-1", 90, 3.6, "n2"),
    ]
    out = render(fs, min_confidence=80)
    assert "eip-1" in out and "vol-1" not in out
    assert "1 finding(s)" in out


def test_eni_score_zero_when_a_service_owns_it():
    from idle_hunter import score_unattached_eni

    assert score_unattached_eni({"Status": "available"}) == 85
    # RequesterManaged is not low confidence, it is the wrong resource entirely
    assert score_unattached_eni({"Status": "available", "RequesterManaged": True}) == 0
    assert score_unattached_eni({"Status": "in-use"}) == 0


def test_rds_score_treats_missing_metrics_as_unknown():
    from idle_hunter import score_idle_rds

    assert score_idle_rds({}, 0) == 80  # nothing connected in 30 days
    assert score_idle_rds({}, 5) == 55  # below the noise floor
    assert score_idle_rds({}, 5000) == 0  # in use
    assert score_idle_rds({}, None) == 0  # no metric is unknown, never idle
