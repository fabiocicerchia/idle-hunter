@domain:scan-coverage @area:partial-failures @from:idle-hunter-lib/regions
Feature: Sweeping several regions at once
  Lets an operator scan many regions in one run and still trust the result when some regions cannot be read.

  Background:
    Given the operator has read-only AWS credentials for the account

  @id:scan-coverage.partial-failures.001 @rule:scan-coverage.partial-failures.failed-region-skipped-and-named @verified @source:idle_hunter_lib/regions.py#scan_regions @test:tests/test_scan_wiring.py#test_scan_regions_runs_in_parallel_and_survives_one_bad_region @test:tests/test_cli.py#test_a_failed_region_is_logged_when_the_caller_passes_no_handler
  Scenario Outline: A region that fails is skipped and named, while the other regions are still reported
    Given regions <regions> are being swept
    And each healthy region holds one unattached volume
    And region(s) <failing> refuse access with AccessDenied
    When the operator sweeps the regions
    Then the report contains findings from <reported> only
    And the operator is warned "<region>: AccessDenied" for each region in <failing>
    And <failing> are listed as missing from this report

    Examples:
      | regions                           | failing              | reported               | region      |
      | eu-west-1, eu-broken-1, us-east-1 | eu-broken-1          | eu-west-1, us-east-1   | eu-broken-1 |
      | eu-west-1, eu-west-2              | eu-west-1, eu-west-2 | no region (0 findings) | eu-west-1   |
      | eu-west-1, us-east-1              | none                 | eu-west-1, us-east-1   | none        |
