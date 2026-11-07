@domain:reporting @area:cleanup-review-script @from:examples/basic
Feature: Turning a scan into a cleanup script for review
  Gives an operator a ready-to-edit cleanup script built from one region's scan, so deletions happen only after a person has read each one and every volume is snapshotted before it is deleted.

  Background:
    Given idle-hunter is installed and has read access to the AWS account

  @id:reporting.cleanup-review-script.001 @rule:reporting.cleanup-review-script.snapshot-before-volume-delete @inferred @source:examples/basic/review.sh#review.sh
  Scenario: Every unattached volume is snapshotted before its delete command
    Given the scan of eu-west-1 finds unattached volume vol-0abc at 95% confidence
    When the operator generates the cleanup script for eu-west-1
    Then the block for vol-0abc first reads "aws ec2 create-snapshot --region eu-west-1 --volume-id vol-0abc --description 'pre-delete idle-hunter'"
    And the next line is "aws ec2 delete-volume --region eu-west-1 --volume-id vol-0abc"
    And the generated script stops at the first failing command, so the delete is not reached if the snapshot fails
    And blocks for other kinds of finding, such as an Elastic IP, carry no snapshot line

  @id:reporting.cleanup-review-script.002 @rule:reporting.cleanup-review-script.nothing-runs-until-reviewed @inferred @source:examples/basic/review.sh#review.sh
  Scenario: Generating the cleanup script changes nothing in the account
    Given the scan of eu-west-1 finds an unattached volume and an unassociated Elastic IP
    When the operator generates the cleanup script for eu-west-1
    Then no AWS resource is created, changed or deleted
    And the script is written to standard output for the operator to save and edit
    And after its "#!/usr/bin/env bash" line it reads "# Generated from: idle-hunter scan --region eu-west-1 --min-confidence 80"
    And it then reads "# Review every line before running. Delete what you are unsure about."

  @id:reporting.cleanup-review-script.003 @rule:reporting.cleanup-review-script.annotated-finding-blocks @inferred @source:examples/basic/review.sh#review.sh
  Scenario Outline: Each finding becomes a commented block showing its score, reason and estimated cost
    Given the scan finds a <kind> finding <id> at <confidence>% with note "<note>", about $<cost>/mo, and suggested command "<command>"
    When the operator generates the cleanup script
    Then the block starts with "# [<confidence>%] <kind> <id> - <note>"
    And it is followed by "#   ~$<cost>/mo (estimate, not your price)"
    And then the line "<line>"

    Examples:
      | kind             | id            | confidence | note                                  | cost | command                                                                  | line                                                                     |
      | eip-unassociated | eipalloc-0def | 90         | elastic IP 203.0.113.7 not associated | 3.6  | aws ec2 release-address --region eu-west-1 --allocation-id eipalloc-0def | aws ec2 release-address --region eu-west-1 --allocation-id eipalloc-0def |
      | eip-unassociated | eipalloc-0aaa | 90         | elastic IP 203.0.113.9 not associated | 3.6  |                                                                          | # (no command for this finding)                                          |

  @id:reporting.cleanup-review-script.004 @rule:reporting.cleanup-review-script.summary-total @inferred @source:examples/basic/review.sh#review.sh
  Scenario: The script ends with the number of findings and their combined monthly estimate
    Given the scan finds two findings costing about $16.00/mo and $3.60/mo
    When the operator generates the cleanup script
    Then the last line reads "# 2 finding(s), ~$20/mo estimated"

  @id:reporting.cleanup-review-script.005 @rule:reporting.cleanup-review-script.confidence-threshold @verified @source:examples/basic/review.sh#review.sh @test:tests/test_idle_hunter.py#test_json_output_is_versioned @questionable
  Scenario Outline: Only findings at or above the chosen confidence reach the script, 80 unless stated
    Given the scan of eu-west-1 finds an empty load balancer at 60%, an unattached volume at 85% and an Elastic IP at 90%
    When the operator generates the cleanup script with minimum confidence <minimum>
    Then the script contains blocks for <included>
    And the header names --min-confidence <shown>

    Examples:
      | minimum     | shown | included                      |
      | (not given) | 80    | the volume and the Elastic IP |
      | 90          | 90    | the Elastic IP only           |
      | 60          | 60    | all three findings            |

  @id:reporting.cleanup-review-script.006 @rule:reporting.cleanup-review-script.region-required @inferred @source:examples/basic/review.sh#review.sh
  Scenario: The script refuses to run without a region
    When the operator generates the cleanup script without naming a region
    Then it prints an error containing "usage: review.sh <region> [min-confidence]" on standard error
    And it exits non-zero and writes no script
    And no scan is run

  @id:reporting.cleanup-review-script.007 @rule:reporting.cleanup-review-script.no-script-from-failed-scan @inferred @source:examples/basic/review.sh#review.sh
  Scenario: A scan that loses its region produces no cleanup script
    Given the scan of eu-west-1 fails, for example because the credentials are denied
    When the operator generates the cleanup script for eu-west-1
    Then the scan's access error appears on standard error
    And the operator gets no script: no header, no blocks and no summary line
    And the command exits with the scan's non-zero status
