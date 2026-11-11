@domain:command-line @area:scan-command @from:idle-hunter-lib/cli
Feature: Running a scan
  The scan command lets an operator choose which regions to sweep and how the findings are printed, for a person reading them or for a script that consumes them.

  Background:
    Given the operator has AWS credentials for the account being scanned

  @id:command-line.scan-command.001 @rule:command-line.scan.region-defaults-to-us-east-1 @gap @source:idle_hunter_lib/cli.py#main
  Scenario Outline: A scan covers one region, us-east-1 unless another is named
    When the operator runs "idle-hunter scan <options>"
    Then only findings from region "<scanned region>" are reported

    Examples:
      | options            | scanned region |
      | (none)             | us-east-1      |
      | --region eu-west-1 | eu-west-1      |

  @id:command-line.scan-command.002 @rule:command-line.scan.all-regions-covers-enabled-regions @gap @source:idle_hunter_lib/cli.py#main
  Scenario: An all-regions scan covers every region enabled for the account, whatever --region says
    Given the account has regions "us-east-1", "eu-west-1" and "ap-southeast-2" enabled
    When the operator runs "idle-hunter scan --all-regions --region eu-west-1"
    Then regions "us-east-1", "eu-west-1" and "ap-southeast-2" are all scanned
    And --region does not narrow the scan

  @id:command-line.scan-command.003 @rule:command-line.scan.output-modes @gap @source:idle_hunter_lib/cli.py#main
  Scenario Outline: The operator chooses between a readable report, a report with cleanup commands, and JSON
    Given the scan finds an unattached volume "vol-0abc1234" in "eu-west-1"
    When the operator runs "idle-hunter scan --region eu-west-1 <options>"
    Then stdout shows <output>

    Examples:
      | options    | output                                                                                                            |
      | (none)     | a text report headed "# idle-hunter report — 1 finding(s)" with no "$ aws" lines                                  |
      | --commands | the same text report with "$ aws ec2 delete-volume --region eu-west-1 --volume-id vol-0abc1234" under the finding |
      | --json     | a JSON document with "version": 1 and a "findings" list containing vol-0abc1234                                   |

  @id:command-line.scan-command.004 @rule:command-line.scan.stable-finding-order @gap @source:idle_hunter_lib/cli.py#main
  Scenario: Two scans of the same estate list findings in the same order
    Given an all-regions scan finds zombies in several regions, finishing them in a different order on each run
    When the operator runs the same scan twice with --json
    Then both outputs list findings ordered by region, then kind, then id
    And the two outputs diff cleanly
