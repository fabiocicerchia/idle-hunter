@domain:zombie-detection @area:usage-metrics @from:idle-hunter-lib/metrics
Feature: Proving a resource is idle from its activity
  Operators rely on activity totals to tell a dead resource from one that is quiet or has never been measured, so nothing is flagged for deletion without proof it is unused.

  Background:
    Given the operator scans a region of an AWS account
    And activity is totalled over the last 30 days

  @id:zombie-detection.usage-metrics.001 @rule:usage-metrics.evidence.no-activity-data-is-unknown-not-idle @verified @source:idle_hunter_lib/metrics.py#cw_sum @test:tests/test_idle_hunter.py#test_nat_score_needs_a_metric @test:tests/test_idle_hunter.py#test_rds_score_treats_missing_metrics_as_unknown @test:tests/test_idle_hunter.py#test_lb_score_boosted_by_zero_traffic
  Scenario Outline: A resource that reported no activity data is never treated as idle
    Given a <resource> whose activity metric (<metric>) reported no data in the last 30 days
    When the operator runs a scan
    Then <outcome>

    Examples:
      | resource                                                   | metric               | outcome                                                                                |
      | NAT gateway                                                | bytes sent out       | the NAT gateway is not reported as idle                                                |
      | available RDS instance                                     | database connections | the RDS instance is not reported as idle                                               |
      | load balancer with no registered targets, over 30 days old | processed bytes      | the load balancer is reported with confidence 85, without the zero-traffic boost to 95 |

  @id:zombie-detection.usage-metrics.002 @rule:usage-metrics.evidence.zero-activity-total-proves-idle @verified @source:idle_hunter_lib/metrics.py#cw_sum @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario Outline: Zero activity across the last 30 days counts as proof a resource is idle
    Given a <resource> whose <metric> reported a total of 0 over the last 30 days
    When the operator runs a scan
    Then the <resource> is reported as <kind> with confidence <confidence>

    Examples:
      | resource                                                   | metric               | kind           | confidence |
      | NAT gateway                                                | bytes sent out       | nat-idle       | 85         |
      | available RDS instance                                     | database connections | rds-idle       | 80         |
      | load balancer with no registered targets, over 30 days old | processed bytes      | elb-no-targets | 95         |
