"""What a finding is, and the one place IaC ownership lowers a score."""

from dataclasses import dataclass

from idle_hunter_lib.types import Tags

IAC_PENALTY = 30


@dataclass(frozen=True)
class Finding:
    """One zombie candidate. Field order is the JSON output order."""

    kind: str
    id: str
    region: str
    confidence: int
    monthly_usd: float
    note: str
    command: str | None = None


def iac_managed(tags: Tags | None) -> bool:
    """True if tags say a stack owns this — deleting it by hand just gets reverted."""
    for tag in tags or []:
        key = tag.get("Key", "").lower()
        val = str(tag.get("Value", "")).lower()
        if key.startswith(("aws:cloudformation:", "elasticbeanstalk:", "eks:", "kubernetes.io/")):
            return True
        if "terraform" in key or "pulumi" in key or key.startswith("cdk"):
            return True
        is_ownership_key = key.replace("_", "-") in (
            "managed-by",
            "provisioner",
            "iac",
            "created-by",
        )
        names_an_iac_tool = any(tool in val for tool in ("terraform", "cloudformation", "cdk", "pulumi", "ansible"))
        if is_ownership_key and names_an_iac_tool:
            return True
    return False


def finding(  # noqa: PLR0913,PLR0917 — these are Finding's own fields, plus the tags that adjust the score
    kind: str,
    rid: str,
    region: str,
    score: int,
    monthly_usd: float,
    note: str,
    *,
    command: str | None = None,
    tags: Tags | None = None,
) -> Finding:
    if iac_managed(tags):
        score = max(score - IAC_PENALTY, 5)
        note += " — IaC-managed (delete via the stack, not the CLI)"
    return Finding(kind, rid, region, score, round(monthly_usd, 2), note, command)
