"""CloudWatch reads. A metric with no datapoints is unknown, never zero."""

from datetime import datetime, timedelta, timezone

LB_NAMESPACES = {
    "application": "AWS/ApplicationELB",
    "network": "AWS/NetworkELB",
    "gateway": "AWS/GatewayELB",
}


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
