"""Monthly cost per unit: built-in estimates, or the Pricing API with --live-pricing."""
import json

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
    # db.t3.medium single-AZ on-demand as a baseline. The finding names the real
    # class so the reader can scale it; --live-pricing is not wired up for RDS.
    "rds": 60.0,
}


# key -> (pricing service code, TERM_MATCH filters, months-per-unit multiplier)
PRICE_QUERIES = {
    "ebs_gb": ("AmazonEC2", (("productFamily", "Storage"), ("volumeApiName", "gp3")), 1),
    "snapshot_gb": ("AmazonEC2", (("productFamily", "Storage Snapshot"),), 1),
    "eip": ("AmazonEC2", (("productFamily", "IP Address"),), 730),
    "elb": ("AWSELB", (("productFamily", "Load Balancer-Application"),), 730),
    "nat": ("AmazonEC2", (("productFamily", "NAT Gateway"),), 730),
}


_PRICE_CACHE = {}


def _lookup_price(session, service_code, filters):
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


def price(key, region, session=None, live=False):
    """Monthly USD per unit — Pricing API when `live`, else the built-in estimate."""
    if not live or key not in PRICE_QUERIES:
        return PRICE_DEFAULTS[key]
    if (key, region) not in _PRICE_CACHE:
        service, filters, months = PRICE_QUERIES[key]
        try:
            found = _lookup_price(session, service, filters + (("regionCode", region),))
        except Exception:  # no pricing:GetProducts, or an unpriced shape — fall back
            found = None
        _PRICE_CACHE[(key, region)] = found * months if found else PRICE_DEFAULTS[key]
    return _PRICE_CACHE[(key, region)]
