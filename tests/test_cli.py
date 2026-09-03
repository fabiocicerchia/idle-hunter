"""The two diagnostics and the partial-results exit code.

Neither path is reachable without an AWS account, so the scan is replaced at
the seam and the assertions are on what the code returns and logs.
"""

import logging

from idle_hunter_lib import cli, regions


def test_a_failed_region_is_logged_when_the_caller_passes_no_handler(monkeypatch, caplog):
    def boom(region, session=None, live_pricing=False):
        raise RuntimeError("AccessDenied")

    monkeypatch.setattr(regions, "scan_region", boom)
    with caplog.at_level(logging.WARNING, logger="idle_hunter_lib.regions"):
        findings, failed = regions.scan_regions(["eu-west-1", "eu-west-2"])

    assert findings == []
    assert sorted(failed) == ["eu-west-1", "eu-west-2"]
    assert "eu-west-1: AccessDenied" in caplog.text


def test_main_warns_about_the_regions_it_lost_and_exits_nonzero(monkeypatch, caplog, capsys):
    monkeypatch.setattr(cli, "scan_regions", lambda *a, **kw: ([], ["eu-west-3"]))
    with caplog.at_level(logging.WARNING, logger="idle_hunter_lib.cli"):
        code = cli.main(["scan", "--region", "eu-west-3"])

    assert code == 3
    assert "1 region(s) failed and are missing from this report: eu-west-3" in caplog.text
    assert "0 finding(s)" in capsys.readouterr().out  # the report still lands on stdout


def test_main_exits_zero_when_no_region_failed(monkeypatch):
    monkeypatch.setattr(cli, "scan_regions", lambda *a, **kw: ([], []))
    assert cli.main(["scan", "--region", "eu-west-3"]) == 0
