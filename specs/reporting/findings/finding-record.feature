@domain:reporting @area:findings @from:idle-hunter-lib/models
Feature: What each finding reports
  Operators and the scripts that consume scans rely on every finding carrying the same fields, in the same order, with a cost they can add up.

  @id:reporting.findings.001 @rule:reporting.findings.field-order @verified @source:idle_hunter_lib/models.py#Finding @test:tests/test_idle_hunter.py#test_json_output_is_versioned
  Scenario: Every finding lists kind, id, region, confidence, monthly cost, note and command in that order
    Given an unassociated Elastic IP eipalloc-0abc1234 in eu-west-1 scoring 90
    When the operator runs a scan with JSON output
    Then the finding's fields appear in the order kind, id, region, confidence, monthly_usd, note, command
    And command is present even when no cleanup command was suggested

  @id:reporting.findings.002 @rule:reporting.findings.cost-rounded-to-cents @inferred @source:idle_hunter_lib/models.py#finding
  Scenario Outline: A finding's monthly cost is rounded to the nearest cent
    Given an unattached EBS volume vol-0abc1234 whose estimated monthly cost is <estimate> USD
    When the operator runs a scan
    Then the finding for vol-0abc1234 shows a monthly cost of <shown> USD

    Examples:
      | estimate | shown |
      | 8.0      | 8.0   |
      | 3.6499   | 3.65  |
      | 12.3333  | 12.33 |
