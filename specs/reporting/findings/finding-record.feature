@domain:reporting @area:findings @from:idle-hunter-lib/models
Feature: What each finding reports
  Operators and the scripts that consume scans rely on every finding carrying the same fields, in the same order, with a cost they can add up.

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
