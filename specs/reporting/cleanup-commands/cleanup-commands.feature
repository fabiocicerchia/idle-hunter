@domain:reporting @area:cleanup-commands @from:idle-hunter-lib/render
Feature: Reviewing cleanup commands
  Lets the operator see the deletion command for each finding to review and run themselves, only when they ask for it.

  Background:
    Given the operator runs a scan without asking for JSON

  @id:reporting.cleanup-commands.001 @rule:reporting.cleanup-commands.shown-only-on-request @inferred @source:idle_hunter_lib/render.py#render
  Scenario Outline: Deletion commands appear under a finding only when the operator asks for them
    Given the scan found an EBS volume vol-0f9e8d7c with the suggested command "aws ec2 delete-volume --volume-id vol-0f9e8d7c --region eu-west-1"
    When the operator reads the report <with_flag> asking for commands
    Then the report <shows> the line "       $ aws ec2 delete-volume --volume-id vol-0f9e8d7c --region eu-west-1" under the finding

    Examples:
      | with_flag | shows         |
      | after     | shows         |
      | without   | does not show |

  @id:reporting.cleanup-commands.002 @rule:reporting.cleanup-commands.no-line-without-command @inferred @source:idle_hunter_lib/render.py#render
  Scenario: A finding with no suggested command gets no command line, even when commands are requested
    Given the scan found a finding nat-0123abcd with no suggested command
    When the operator reads the report after asking for commands
    Then the finding shows only its summary line and its note
    And no line starting with "$" appears under it
