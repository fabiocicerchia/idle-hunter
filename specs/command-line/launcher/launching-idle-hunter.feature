@domain:command-line @area:launcher @from:idle-hunter/idle-hunter
Feature: Launching idle-hunter
  Lets an operator run the scanner either straight from a checkout or as an installed command, and trust its exit status in scripts and CI.

  Background:
    Given the operator has AWS credentials for an account with resources in eu-west-1

  @id:command-line.launcher.001 @rule:command-line.launcher.same-scan-and-exit-status-from-any-launcher @inferred @source:idle_hunter.py#main
  Scenario Outline: The standalone script and the installed command run the same scan and report its exit status
    Given idle-hunter is available as <launcher>
    When the operator runs a scan with "<arguments>" through <launcher>
    Then the scan report is printed on stdout exactly as the scan command produces it
    And diagnostics are printed on stderr
    And the process exits with the scan command's exit status

    Examples:
      | launcher                               | arguments                 |
      | the standalone script ./idle_hunter.py | --region eu-west-1        |
      | the installed idle-hunter command      | --region eu-west-1 --json |
