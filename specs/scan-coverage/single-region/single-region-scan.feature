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
