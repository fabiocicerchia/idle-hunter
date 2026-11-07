@domain:zombie-detection @area:storage @from:idle-hunter-lib/scan
Feature: Finding storage leftovers
  Lets an operator see unattached EBS volumes, orphaned snapshots and unused AMIs with the monthly storage cost each one is still billing.

  Background:
    Given Given the operator's AWS account in region eu-west-1

  @id:zombie-detection.storage.001 @rule:zombie-detection.storage.unattached-volume-reported @verified @source:idle_hunter_lib/scan.py#scan_volumes @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario: An unattached volume is reported with its storage cost, an attached one is not
    Given a 200 GiB volume vol-0dead in status available, created 210 days ago
    And a 10 GiB volume vol-0live in status in-use
    When the operator scans the region
    Then vol-0dead is reported as ebs-unattached
    And its monthly cost is 200 times the per-GiB EBS price
    And its note reads "200 GiB, created 210d ago, status=available"
    And vol-0live is not reported

  @id:zombie-detection.storage.002 @rule:zombie-detection.storage.orphaned-snapshot-only-when-source-gone-and-not-backing-ami @verified @source:idle_hunter_lib/scan.py#scan_snapshots @test:tests/test_scan_wiring.py#test_only_genuinely_orphaned_snapshots_are_reported
  Scenario Outline: A snapshot is orphaned only when its source volume is gone and no AMI is built from it
    Given the account owns snapshot <snapshot> taken from volume <source volume>
    And <source state>
    And <ami state>
    When the operator scans the region
    Then snapshot <snapshot> is <outcome>

    Examples:
      | snapshot     | source volume | source state               | ami state                             | outcome                                                                            |
      | snap-0orphan | vol-0gone     | vol-0gone no longer exists | no AMI is built from snap-0orphan     | reported as snapshot-orphaned, costed at its size times the per-GiB snapshot price |
      | snap-0live   | vol-0live     | vol-0live still exists     | no AMI is built from snap-0live       | not reported                                                                       |
      | snap-0ami    | vol-0gone     | vol-0gone no longer exists | AMI ami-0base is built from snap-0ami | not reported (the AMI is the finding instead)                                      |

  @id:zombie-detection.storage.003 @rule:zombie-detection.storage.unused-ami-reported @verified @source:idle_hunter_lib/scan.py#scan_images @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind @questionable
  Scenario: A self-owned AMI that no running or stopped instance uses is reported with the cost of its snapshots
    Given the account owns AMI ami-0base named old-base, backed by 8 GiB of snapshots
    And the only instance launched from ami-0base is terminated
    And AMI ami-0prod is used by a running instance
    When the operator scans the region
    Then ami-0base is reported as ami-unused
    And its monthly cost is 8 times the per-GiB snapshot price
    And its note starts "old-base: no instance uses it" and ends "8 GiB of snapshots"
    And ami-0prod is not reported
