"""Fan out over regions. Two checks feed a later one, so the call order matters."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

from idle_hunter_lib.models import Finding
from idle_hunter_lib.pricing import price
from idle_hunter_lib.scan import (
    scan_eips,
    scan_enis,
    scan_images,
    scan_load_balancers,
    scan_nat_gateways,
    scan_rds,
    scan_snapshots,
    scan_volumes,
)
from idle_hunter_lib.types import Session

LOGGER = logging.getLogger(__name__)


def scan_region(region: str, session: Session | None = None, live_pricing: bool = False) -> list[Finding]:
    # As in cli: imported when a scan starts, not at module load.
    import boto3  # noqa: PLC0415

    # boto3 ships no annotations; this is the one place an untyped session
    # crosses into the scan, and everything below takes it as a Session.
    live_session: Session = session or boto3.Session()  # pyright: ignore[reportUnknownMemberType]
    ec2 = live_session.client("ec2", region_name=region)
    elb = live_session.client("elbv2", region_name=region)
    cw = live_session.client("cloudwatch", region_name=region)
    rds = live_session.client("rds", region_name=region)
    price_of = partial(price, region=region, session=live_session, live=live_pricing)

    volumes, live_volume_ids = scan_volumes(ec2, region, price_of)
    images, ami_snapshots = scan_images(ec2, region, price_of)
    return (
        volumes
        + images
        + scan_eips(ec2, region, price_of)
        + scan_enis(ec2, region, price_of)
        + scan_load_balancers(elb, cw, region, price_of)
        + scan_nat_gateways(ec2, cw, region, price_of)
        + scan_rds(rds, cw, region, price_of)
        + scan_snapshots(ec2, region, price_of, live_volume_ids, ami_snapshots)
    )


def scan_regions(
    regions: list[str],
    session: Session | None = None,
    live_pricing: bool = False,
    workers: int = 8,
    on_error: Callable[[str, BaseException], None] | None = None,
) -> tuple[list[Finding], list[str]]:
    """Scan several regions concurrently.

    Each worker builds its own boto3 Session: Session objects are not
    thread-safe, and sharing one across a pool is the classic way to get
    intermittent credential errors under load.

    A region that fails is reported and skipped rather than aborting the sweep —
    but the caller is told, because a report that quietly lost a region reads
    exactly like a clean estate. Returns `(findings, failed_regions)`.
    """
    if len(regions) == 1:
        return scan_region(regions[0], session, live_pricing), []

    findings: list[Finding] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(regions)))) as pool:
        pending = {pool.submit(scan_region, r, None, live_pricing): r for r in regions}
        for future in as_completed(pending):
            region = pending[future]
            # .exception() rather than try/except around .result(): one bad
            # region must not lose the other 30, and asking the future what
            # went wrong says that without catching everything to find out.
            # BaseException, because that is what a future carries: a
            # KeyboardInterrupt in a worker is not something to hand to an
            # error callback that expects a failed region.
            exc: BaseException | None = future.exception()
            if exc is None:
                findings.extend(future.result())
                continue
            failed.append(region)
            if on_error:
                on_error(region, exc)
            else:
                LOGGER.warning("%s: %s", region, exc)
    return findings, failed
