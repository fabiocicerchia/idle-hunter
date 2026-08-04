from datetime import datetime, timedelta, timezone

from idle_hunter import (
    finding,
    iac_managed,
    price,
    render,
    score_empty_lb,
    score_unattached_volume,
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


def test_iac_managed_tags_lower_the_score():
    assert iac_managed([{"Key": "aws:cloudformation:stack-name", "Value": "prod"}])
    assert iac_managed([{"Key": "managed_by", "Value": "Terraform"}])
    assert not iac_managed([{"Key": "Name", "Value": "terraforming-mars"}])
    assert not iac_managed(None)
    f = finding("ebs-unattached", "vol-1", "eu-west-1", 90, 8.0, "n",
                tags=[{"Key": "terraform:module", "Value": "vpc"}])
    assert f["confidence"] == 60 and "IaC-managed" in f["note"]


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
