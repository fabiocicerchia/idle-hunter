import json
from datetime import datetime, timedelta, timezone

from idle_hunter import (
    NAT_IDLE_BYTES,
    PRICE_DEFAULTS,
    finding,
    iac_managed,
    price,
    price_is_live,
    rds_engine_name,
    rds_shape,
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


class FakePricing:
    """Minimal Pricing API stand-in: records the filters, returns one price."""

    def __init__(self, usd, seen):
        self.usd = usd
        self.seen = seen

    def client(self, *a, **k):
        return self

    def get_products(self, ServiceCode, Filters, MaxResults):
        self.seen.append({f["Field"]: f["Value"] for f in Filters})
        doc = {
            "terms": {
                "OnDemand": {
                    "t": {"priceDimensions": {"d": {"pricePerUnit": {"USD": str(self.usd)}}}}
                }
            }
        }
        return {"PriceList": [json.dumps(doc)]}


def test_rds_engine_name_maps_families_and_refuses_to_guess():
    assert rds_engine_name("postgres") == "PostgreSQL"
    assert rds_engine_name("aurora-mysql") == "Aurora MySQL"
    # Edition-suffixed families match on the prefix.
    assert rds_engine_name("oracle-ee") == "Oracle"
    assert rds_engine_name("sqlserver-ex") == "SQL Server"
    # An engine we cannot name must not be guessed into some other engine's SKU.
    assert rds_engine_name("neptune") is None
    assert rds_engine_name(None) is None


def test_rds_shape_carries_class_engine_deployment_and_licence():
    shape = rds_shape(
        {
            "DBInstanceClass": "db.r6g.xlarge",
            "Engine": "postgres",
            "MultiAZ": True,
            "LicenseModel": "postgresql-license",
        }
    )
    assert shape == {
        "instanceType": "db.r6g.xlarge",
        "databaseEngine": "PostgreSQL",
        "deploymentOption": "Multi-AZ",
        "licenseModel": "No license required",
    }
    byol = rds_shape(
        {
            "DBInstanceClass": "db.m5.large",
            "Engine": "oracle-ee",
            "LicenseModel": "bring-your-own-license",
        }
    )
    assert byol["deploymentOption"] == "Single-AZ"
    assert byol["licenseModel"] == "Bring your own license"


def test_rds_live_pricing_queries_the_instance_shape_not_a_flat_rate():
    seen = []
    shape = rds_shape({"DBInstanceClass": "db.m5.large", "Engine": "mysql", "MultiAZ": False})
    hourly = 0.171
    got = price("rds", "eu-west-2", session=FakePricing(hourly, seen), live=True, **shape)

    assert got == hourly * 730 and got != PRICE_DEFAULTS["rds"]
    assert price_is_live("rds", "eu-west-2", **shape)
    # The class, engine, deployment and licence all have to reach the query, or
    # it prices some other instance's SKU.
    assert seen[0]["instanceType"] == "db.m5.large"
    assert seen[0]["databaseEngine"] == "MySQL"
    assert seen[0]["deploymentOption"] == "Single-AZ"
    assert seen[0]["licenseModel"] == "No license required"
    assert seen[0]["regionCode"] == "eu-west-2"


def test_rds_unnameable_engine_falls_back_without_querying():
    seen = []
    shape = rds_shape({"DBInstanceClass": "db.m5.large", "Engine": "neptune"})
    got = price("rds", "eu-west-3", session=FakePricing(9.99, seen), live=True, **shape)

    # A half-filled filter set would match the wrong SKU, so it must not be sent.
    assert seen == []
    assert got == PRICE_DEFAULTS["rds"]
    assert not price_is_live("rds", "eu-west-3", **shape)


def test_rds_price_is_not_live_without_the_flag():
    shape = rds_shape({"DBInstanceClass": "db.m5.large", "Engine": "mysql"})
    assert price("rds", "eu-north-1", **shape) == PRICE_DEFAULTS["rds"]
    assert not price_is_live("rds", "eu-north-1", **shape)
