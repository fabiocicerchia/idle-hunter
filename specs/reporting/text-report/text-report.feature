@domain:reporting @area:text-report @from:idle-hunter-lib/render
Feature: Reading the scan report
  Gives the operator a readable list of zombie resources, most deletable first, with the monthly money they would reclaim.

  Background:
    Given the operator runs a scan without asking for JSON

  @id:reporting.text-report.001 @rule:reporting.text-report.summary-header @inferred @source:idle_hunter_lib/render.py#render
  Scenario: The report opens with how many findings it lists and what they would save each month
    Given the scan found an Elastic IP eip-0a1b2c3d in eu-west-1 at 90% confidence costing $3.6 a month
    And the scan found an EBS volume vol-0f9e8d7c in eu-west-1 at 60% confidence costing $8.0 a month
    When the operator reads the report
    Then the first line reads "# idle-hunter report — 2 finding(s), ~$12/mo reclaimable"
    And each finding line shows its confidence, kind, id, region and its unrounded monthly cost, such as "[ 90%] eip-unassociated  eip-0a1b2c3d  (eu-west-1)  ~$3.6/mo"
    And the finding's note is printed on the line below it

  @id:reporting.text-report.002 @rule:reporting.text-report.most-confident-first @inferred @source:idle_hunter_lib/render.py#render
  Scenario Outline: Findings are listed most confident first, then most expensive first
    Given the scan found findings with these confidences and monthly costs: <findings>
    When the operator reads the report
    Then the findings appear in the order <order>

    Examples:
      | findings                        | order        |
      | vol-1 60% $8.0, eip-1 90% $3.6  | eip-1, vol-1 |
      | nat-1 85% $32.4, eip-2 85% $3.6 | nat-1, eip-2 |

  @id:reporting.text-report.003 @rule:reporting.text-report.min-confidence-filter @verified @source:idle_hunter_lib/render.py#render @test:tests/test_idle_hunter.py#test_render_sorts_and_filters
  Scenario Outline: Findings below the chosen minimum confidence are left out of the report and its totals
    Given the scan found an Elastic IP eip-1 at 90% confidence costing $3.6 a month
    And the scan found an EBS volume vol-1 at 60% confidence costing $8.0 a month
    When the operator reads the report with a minimum confidence of <min>
    Then the report lists <listed>
    And the first line counts <count> finding(s)

    Examples:
      | min | listed          | count |
      | 80  | eip-1 only      | 1     |
      | 60  | eip-1 and vol-1 | 2     |
      | 95  | no findings     | 0     |

  @id:reporting.text-report.004 @rule:reporting.text-report.zero-confidence-never-shown @inferred @source:idle_hunter_lib/render.py#render @questionable
  Scenario: A resource scored 0% is never shown in the report, even with no minimum confidence
    Given the findings handed to the report include lb-app-1 scored 0% (no scan check emits a 0% finding today)
    And the scan found an Elastic IP eip-1 at 90% confidence
    When the operator reads the report without choosing a minimum confidence
    Then the report lists eip-1 only
    And the first line counts 1 finding(s)
