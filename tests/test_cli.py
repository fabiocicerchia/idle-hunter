"""The two diagnostics and the partial-results exit code.

Neither path is reachable without an AWS account, so the scan is replaced at
the seam and the assertions are on what the code returns and logs.
"""

import logging
from typing import NoReturn

import pytest

from idle_hunter_lib import cli, regions
from idle_hunter_lib.models import Finding
from idle_hunter_lib.types import Session


def test_a_failed_region_is_logged_when_the_caller_passes_no_handler(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(region: str, session: Session | None = None, live_pricing: bool = False) -> NoReturn:
        raise RuntimeError("AccessDenied")

    monkeypatch.setattr(regions, "scan_region", boom)
    with caplog.at_level(logging.WARNING, logger="idle_hunter_lib.regions"):
        findings, failed = regions.scan_regions(["eu-west-1", "eu-west-2"])

    assert findings == []
    assert sorted(failed) == ["eu-west-1", "eu-west-2"]
    assert "eu-west-1: AccessDenied" in caplog.text


def test_main_warns_about_the_regions_it_lost_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    def one_region_lost(*_args: object, **_kwargs: object) -> tuple[list[Finding], list[str]]:
        return [], ["eu-west-3"]

    monkeypatch.setattr(cli, "scan_regions", one_region_lost)
    with caplog.at_level(logging.WARNING, logger="idle_hunter_lib.cli"):
        code = cli.main(["scan", "--region", "eu-west-3"])

    assert code == 3
    assert "1 region(s) failed and are missing from this report: eu-west-3" in caplog.text
    assert "0 finding(s)" in capsys.readouterr().out  # the report still lands on stdout


def test_main_exits_zero_when_no_region_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def nothing_lost(*_args: object, **_kwargs: object) -> tuple[list[Finding], list[str]]:
        return [], []

    monkeypatch.setattr(cli, "scan_regions", nothing_lost)
    assert cli.main(["scan", "--region", "eu-west-3"]) == 0
