"""idle-hunter — find zombie AWS resources with a confidence-to-delete score.

Checks:
  * unattached EBS volumes           (age-weighted)
  * unassociated Elastic IPs
  * load balancers with no targets   (CloudWatch-confirmed idle)
  * idle NAT gateways                (CloudWatch bytes)
  * snapshots whose source volume is gone
  * self-owned AMIs no instance uses

Every finding gets a 0-100 confidence score; nothing is ever deleted — the
output is a report (optionally with ready-to-review `aws` CLI commands).

  idle-hunter scan --region eu-west-1
  idle-hunter scan --all-regions --min-confidence 80 --commands
"""

import argparse
import logging
import sys

from idle_hunter_lib.regions import scan_regions
from idle_hunter_lib.render import render, render_json

LOGGER = logging.getLogger(__name__)

# The exit codes this tool promises. 3 is contract, not choice: README.md:17
# tells readers a run that lost a region exits 3. argparse still owns 2.
EXIT_OK = 0
EXIT_PARTIAL_RESULTS = 3

# What --region defaults to, and the region --all-regions enumerates from.
DEFAULT_REGION = "us-east-1"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="idle-hunter",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subcommands = parser.add_subparsers(dest="cmd", required=True)
    scan = subcommands.add_parser("scan", help="scan for zombie resources")
    scan.add_argument("--region", default=DEFAULT_REGION)
    scan.add_argument("--all-regions", action="store_true")
    scan.add_argument("--min-confidence", type=int, default=0)
    scan.add_argument("--commands", action="store_true", help="print deletion commands (never executed)")
    scan.add_argument(
        "--live-pricing",
        action="store_true",
        help="look up real prices via the Pricing API (needs pricing:GetProducts)",
    )
    scan.add_argument(
        "--workers",
        type=int,
        default=8,
        metavar="N",
        help="regions scanned in parallel with --all-regions (default 8; lower it if the account is being throttled)",
    )
    scan.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    # One logger for the process: diagnostics on stderr, results on stdout.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)
    args = _build_parser().parse_args(argv)

    # boto3 is only needed once a scan actually runs; --help and --version
    # must not require it.
    import boto3  # noqa: PLC0415

    session = boto3.Session()
    regions = [args.region]
    if args.all_regions:
        ec2 = session.client("ec2", region_name=DEFAULT_REGION)
        regions = [r["RegionName"] for r in ec2.describe_regions()["Regions"]]

    findings, failed = scan_regions(regions, session, args.live_pricing, args.workers)
    # Completion order is non-deterministic once regions run in parallel, so
    # sort before emitting: two runs over the same estate must diff cleanly.
    findings.sort(key=lambda f: (f.region, f.kind, str(f.id)))

    if args.json:
        render_json(findings, args.min_confidence, sys.stdout)
    else:
        print(render(findings, args.min_confidence, args.commands))  # noqa: T201 — the tool's output

    if failed:
        LOGGER.warning(
            "%d region(s) failed and are missing from this report: %s",
            len(failed),
            ", ".join(sorted(failed)),
        )
        # never let a lost region look like a clean estate
        return EXIT_PARTIAL_RESULTS
    return EXIT_OK
