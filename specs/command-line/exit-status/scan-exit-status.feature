@domain:command-line @area:exit-status @from:idle-hunter-lib/cli
Feature: Telling a complete scan from a partial one
  Operators and the pipelines that run idle-hunter rely on the exit status and stderr to know whether the report covers every region they asked for, so a lost region never passes for a clean estate.

  Background:
    Given the operator has AWS credentials for the account being scanned

  @id:command-line.exit-status.001 @rule:command-line.exit-status.lost-region-exits-3 @verified @source:idle_hunter_lib/cli.py#main @test:tests/test_cli.py#test_main_warns_about_the_regions_it_lost_and_exits_nonzero
  Scenario: A scan that lost a region still prints its report but exits 3 and names the missing regions
    Given region "eu-west-3" could not be scanned
    When the operator runs an all-regions scan
    Then the report of the findings that were gathered is printed on stdout
    And stderr shows "WARNING: 1 region(s) failed and are missing from this report: eu-west-3"
    And the command exits with status 3

  @id:command-line.exit-status.002 @rule:command-line.exit-status.complete-scan-exits-0 @verified @source:idle_hunter_lib/cli.py#main @test:tests/test_cli.py#test_main_exits_zero_when_no_region_failed
  Scenario: A scan that covered every requested region exits 0
    Given every requested region was scanned
    When the operator runs a scan
    Then the report is printed on stdout
    And no missing-region warning appears on stderr
    And the command exits with status 0

  @id:command-line.exit-status.003 @rule:command-line.exit-status.single-region-failure-aborts @inferred @source:idle_hunter_lib/regions.py#scan_regions @questionable
  Scenario: A failure while scanning a single region aborts the run with no report instead of exiting 3
    Given the operator scans only "eu-west-1"
    And AWS refuses a call in "eu-west-1" with AccessDenied
    When the operator runs a scan
    Then no report is printed on stdout
    And an error traceback is printed on stderr
    And the command exits with status 1, not 3
