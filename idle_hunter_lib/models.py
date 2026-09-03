"""What a finding is, and the one place IaC ownership lowers a score."""

from dataclasses import dataclass

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


def iac_managed(tags):
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
        names_an_iac_tool = any(
            tool in val for tool in ("terraform", "cloudformation", "cdk", "pulumi", "ansible")
        )
        if is_ownership_key and names_an_iac_tool:
            return True
    return False


def finding(kind, rid, region, score, monthly_usd, note, command=None, tags=None):
    if iac_managed(tags):
        score = max(score - IAC_PENALTY, 5)
        note += " — IaC-managed (delete via the stack, not the CLI)"
    return Finding(kind, rid, region, score, round(monthly_usd, 2), note, command)
