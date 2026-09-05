"""The confidence-to-delete scores: pure functions of a resource and a signal.

Nothing here talks to AWS and nothing reads a clock beyond `now()`. Every
score caps below 100 on purpose — a scanner cannot know your intent.
"""

from datetime import datetime, timezone

from idle_hunter_lib.types import Resource

NAT_IDLE_BYTES = 10 * 1024**2  # 30d of DNS/health-check noise, not real traffic


RDS_IDLE_CONNECTIONS = 30  # 30d: a monitoring probe once a day, not an application


# A load balancer with no targets for a month is not between deployments.
LB_STALE_DAYS = 30


def age_days(created: datetime) -> int:
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - created).days


def score_unattached_volume(vol: Resource) -> int:
    """Unattached EBS volume: base 50, +age, +unnamed, capped 95."""
    score = 50
    days = age_days(vol["CreateTime"])
    score += min(days // 7 * 5, 35)  # +5/week unattached-ish, cap +35
    if not any(tag["Key"] == "Name" for tag in vol.get("Tags", [])):
        score += 10  # unnamed → likely forgotten
    return min(score, 95)


def score_unassociated_eip(_addr: Resource) -> int:
    return 90  # unassociated EIPs cost money and have no state to lose


def score_unattached_eni(eni: Resource) -> int:
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


def score_idle_rds(_db: Resource, connections_30d: float | None) -> int:
    """RDS instance: 80 at zero connections in 30d, 55 below the noise floor, else 0.

    `None` means CloudWatch returned nothing — unknown, not idle — so it scores
    0 for the same reason `score_idle_nat` does: a database is the last thing
    that should be deleted on missing evidence.
    """
    if connections_30d is None or connections_30d > RDS_IDLE_CONNECTIONS:
        return 0
    return 80 if connections_30d == 0 else 55


def score_empty_lb(lb: Resource, target_count: int, bytes_30d: float | None = None) -> int:
    """LB with no targets: 85 over 30d old else 60, +10 if CloudWatch confirms no traffic."""
    if target_count > 0:
        return 0
    score = 85 if age_days(lb["CreatedTime"]) > LB_STALE_DAYS else 60
    if bytes_30d == 0:
        score += 10
    return min(score, 95)


def score_idle_nat(_nat: Resource, bytes_30d: float | None) -> int:
    """NAT gateway: 85 at zero bytes out in 30d, 65 under the noise floor, else 0."""
    if bytes_30d is None or bytes_30d > NAT_IDLE_BYTES:
        return 0
    return 85 if bytes_30d == 0 else 65


def score_stale_snapshot(snap: Resource, source_exists: bool) -> int:
    """Snapshot whose source volume is gone: base 45, +5 per 30d, capped 80."""
    if source_exists:
        return 0
    return min(45 + age_days(snap["StartTime"]) // 30 * 5, 80)


def score_unused_ami(image: Resource, in_use: bool) -> int:
    """Self-owned AMI no instance runs: base 40, +5 per 30d, capped 75."""
    if in_use:
        return 0
    return min(40 + age_days(image["CreationDate"]) // 30 * 5, 75)
