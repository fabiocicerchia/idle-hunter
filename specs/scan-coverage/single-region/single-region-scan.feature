@domain:scan-coverage @area:single-region @from:idle-hunter-lib/regions
Feature: Scanning one region
  Lets an operator run every zombie check against one chosen AWS region and get a single list of findings to review before cleaning up.

  Background:
    Given the operator has read-only AWS credentials for the account

  @id:scan-coverage.single-region.001 @rule:scan-coverage.single-region.runs-every-check @verified @source:idle_hunter_lib/regions.py#scan_region @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario: A region scan reports every kind of zombie the region holds
    Given region eu-west-1 holds an unattached volume, an unassociated Elastic IP, a load balancer with no targets, an idle NAT gateway, an unused image, an orphaned snapshot, a detached network interface and an idle database
    When the operator scans region eu-west-1
    Then the report lists one finding of each kind: ebs-unattached, eip-unassociated, elb-no-targets, nat-idle, ami-unused, snapshot-orphaned, eni-unattached, rds-idle
    And every finding is tagged with region eu-west-1

  @id:scan-coverage.single-region.002 @rule:zombie-detection.storage.snapshot-in-use-not-orphaned @verified @source:idle_hunter_lib/regions.py#scan_region @test:tests/test_scan_wiring.py#test_only_genuinely_orphaned_snapshots_are_reported
  Scenario: A snapshot still backing a live volume or an image is not reported as orphaned
    Given region eu-west-1 has snapshot snap-live whose source volume still exists
    And snapshot snap-ami backs a registered image
    And snapshot snap-orphan's source volume is gone and no image uses it
    When the operator scans region eu-west-1
    Then the only snapshot-orphaned finding is snap-orphan
    And snap-live and snap-ami are not reported as orphaned snapshots

  @id:scan-coverage.single-region.003 @rule:scan-coverage.single-region.failure-aborts-scan @inferred @source:idle_hunter_lib/regions.py#scan_regions @questionable
  Scenario: A failure in the only scanned region stops the scan instead of being skipped
    Given the operator's credentials are denied access in region eu-west-3
    When the operator scans region eu-west-3
    Then no report is printed
    And the scan ends with the access error rather than the 'region(s) failed and are missing from this report' warning
