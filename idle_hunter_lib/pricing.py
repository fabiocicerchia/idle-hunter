"""Monthly cost per unit: built-in estimates, or the Pricing API with --live-pricing."""

import json
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from idle_hunter_lib.types import Resource, Session

# The Pricing API is only served from us-east-1, whatever region is being priced.
# https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html
PRICING_API_REGION = "us-east-1"


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


def rds_engine_name(engine: str | None) -> str | None:
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


def rds_shape(db: Resource) -> dict[str, str | None]:
    """The four Pricing API filters that identify one instance's SKU."""
    return {
        "instanceType": db.get("DBInstanceClass"),
        "databaseEngine": rds_engine_name(db.get("Engine")),
        "deploymentOption": "Multi-AZ" if db.get("MultiAZ") else "Single-AZ",
        "licenseModel": RDS_LICENCE_NAMES.get(db.get("LicenseModel", ""), "No license required"),
    }


_PRICE_CACHE = {}


def _lookup_price(session: Session, service_code: str, filters: list[dict[str, str]]) -> float | None:
    """First positive on-demand USD price matching `filters`, or None."""
    client = session.client("pricing", region_name=PRICING_API_REGION)
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


def _cache_key(key: str, region: str, params: dict[str, Any]) -> tuple[str, str, tuple[tuple[str, Any], ...]]:
    return (key, region, tuple(sorted(params.items())))


def price(key: str, region: str, session: Session | None = None, live: bool = False, **params: Any) -> float:
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
            # No pricing:GetProducts, no credentials, no endpoint, or a price
            # document that does not parse — fall back to the built-in estimate.
            # Named rather than blanket: a bug in _lookup_price should surface,
            # not quietly read as "this shape has no price".
            try:
                found = _lookup_price(session, service, (*resolved, ("regionCode", region)))
            except (BotoCoreError, ClientError, ValueError, TypeError):
                found = None
        _PRICE_CACHE[ck] = (found * months, True) if found else (PRICE_DEFAULTS[key], False)
    return _PRICE_CACHE[ck][0]


def price_is_live(key: str, region: str, **params: Any) -> bool:
    """Whether the price already resolved for these arguments came from the API.

    Read after price(), so a finding can say which of the two numbers the reader
    is looking at instead of implying a measurement that never happened.
    """
    entry = _PRICE_CACHE.get(_cache_key(key, region, params))
    return bool(entry and entry[1])
