@domain:zombie-detection @area:load-balancers @from:idle-hunter-lib/scan
Feature: Finding empty load balancers
  Lets an operator see load balancers that are billing hourly while routing to nothing.

  Background:
    Given the operator's AWS account in region eu-west-1

  @id:zombie-detection.load-balancers.001 @rule:zombie-detection.load-balancers.no-registered-targets @verified @source:idle_hunter_lib/scan.py#scan_load_balancers @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario Outline: A load balancer with no registered targets in any target group is reported, and says when it also had no traffic
    Given application load balancer legacy-alb has no targets registered in any of its target groups
    And CloudWatch reports <traffic> processed in the last 30 days
    When the operator scans the region
    Then legacy-alb is reported as elb-no-targets at the load balancer monthly price
    And its note reads "<note>"

    Examples:
      | traffic              | note                                                        |
      | 0 bytes              | application LB with 0 registered targets, no traffic in 30d |
      | no datapoints at all | application LB with 0 registered targets                    |

  @id:zombie-detection.load-balancers.002 @rule:zombie-detection.load-balancers.with-targets-not-reported @inferred @source:idle_hunter_lib/scan.py#scan_load_balancers
  Scenario: A load balancer with at least one registered target is not reported
    Given network load balancer api-nlb has 2 targets registered
    When the operator scans the region
    Then api-nlb is not reported
