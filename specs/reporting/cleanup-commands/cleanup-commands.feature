@domain:reporting @area:cleanup-commands @from:idle-hunter-lib/render
Feature: Reviewing cleanup commands
  Lets the operator see the deletion command for each finding to review and run themselves, only when they ask for it.

  Background:
    Given the operator runs a scan without asking for JSON

  @id:reporting.cleanup-commands.002 @rule:reporting.cleanup-commands.no-line-without-command @inferred @source:idle_hunter_lib/render.py#render
  Scenario: A finding with no suggested command gets no command line, even when commands are requested
    Given the scan found a finding nat-0123abcd with no suggested command
    When the operator reads the report after asking for commands
    Then the finding shows only its summary line and its note
    And no line starting with "$" appears under it
