@domain:reporting @area:json-output @from:idle-hunter-lib/render
Feature: Machine-readable findings
  Gives scripts, dashboards and cloudledger a versioned JSON document of the findings they can rely on.

  Background:
    Given the operator runs a scan asking for JSON

  @id:reporting.json-output.001 @rule:reporting.json-output.versioned-envelope @verified @source:idle_hunter_lib/render.py#render_json @test:tests/test_idle_hunter.py#test_json_output_is_versioned
  Scenario: The JSON document carries a format version and a fixed set of fields per finding
    Given the scan found an Elastic IP eip-1 in eu-west-1 at 90% confidence costing $3.6 a month
    When a script reads the JSON output
    Then the document has exactly the keys "version" and "findings", in that order
    And "version" is 1
    And each finding has exactly the keys kind, id, region, confidence, monthly_usd, note and command
    And command is included whether or not the operator asked for commands

  @id:reporting.json-output.002 @rule:reporting.json-output.min-confidence-applies @verified @source:idle_hunter_lib/render.py#render_json @test:tests/test_idle_hunter.py#test_json_output_is_versioned
  Scenario: The minimum confidence also filters the JSON findings
    Given the scan found an Elastic IP eip-1 at 90% confidence
    And the scan found an EBS volume vol-1 at 60% confidence
    When a script reads the JSON output of a scan with a minimum confidence of 80
    Then the findings list holds eip-1 only

  @id:reporting.json-output.003 @rule:reporting.json-output.zero-confidence-included @inferred @source:idle_hunter_lib/render.py#render_json @questionable
  Scenario: Without a minimum confidence, 0% findings are included in the JSON
    Given the findings handed to the JSON output include lb-app-1 scored 0% (no scan check emits a 0% finding today)
    And the scan found an Elastic IP eip-1 at 90% confidence
    When a script reads the JSON output of a scan without a minimum confidence
    Then the findings list holds both lb-app-1 and eip-1
    And lb-app-1 has confidence 0
