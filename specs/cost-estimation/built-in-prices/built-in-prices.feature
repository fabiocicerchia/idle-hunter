@domain:cost-estimation @area:built-in-prices @from:idle-hunter-lib/pricing
Feature: Estimating reclaimable cost from built-in prices
  Gives operators a monthly dollar figure for each zombie without extra AWS permissions, so they can rank cleanup by money reclaimed.

  Background:
    Given the operator scans without live pricing

  @id:cost-estimation.built-in-prices.001 @rule:cost.built-in.default-monthly-prices @verified @source:idle_hunter_lib/pricing.py#PRICE_DEFAULTS @test:tests/test_idle_hunter.py#test_price_falls_back_to_estimates_without_live_lookup @test:tests/test_idle_hunter.py#test_rds_price_is_not_live_without_the_flag
  Scenario Outline: Each kind of zombie is priced from a fixed monthly rate
    Given a <resource> zombie of <size> is found
    When the operator runs a scan
    Then the finding's monthly cost is <monthly_usd> USD

    Examples:
      | resource                      | size              | monthly_usd |
      | unattached EBS volume         | 100 GiB           | 8.00        |
      | orphaned snapshot             | 100 GiB           | 5.00        |
      | unassociated Elastic IP       | one address       | 3.60        |
      | load balancer with no targets | one load balancer | 18.00       |
      | idle NAT gateway              | one gateway       | 32.90       |
      | idle RDS instance             | one instance      | 60.00       |
      | detached network interface    | one interface     | 0.00        |

  @id:cost-estimation.built-in-prices.002 @rule:cost.built-in.region-independent @verified @source:idle_hunter_lib/pricing.py#price @test:tests/test_idle_hunter.py#test_price_falls_back_to_estimates_without_live_lookup @questionable
  Scenario Outline: Built-in prices are the same in every region
    Given an idle NAT gateway is found in <region>
    When the operator runs a scan
    Then the finding's monthly cost is 32.90 USD

    Examples:
      | region         |
      | us-east-1      |
      | eu-west-1      |
      | ap-southeast-2 |

  @id:cost-estimation.built-in-prices.003 @rule:cost.built-in.rds-baseline-disclosed @verified @source:idle_hunter_lib/pricing.py#price_is_live @test:tests/test_idle_hunter.py#test_rds_price_is_not_live_without_the_flag
  Scenario: An idle database priced at the baseline says the cost is a baseline
    Given an idle db.r6g.xlarge postgres instance is found
    When the operator runs a scan
    Then the finding's monthly cost is 60.00 USD
    And the finding's note says "cost shown is a db.t3.medium baseline, scale it for db.r6g.xlarge"
