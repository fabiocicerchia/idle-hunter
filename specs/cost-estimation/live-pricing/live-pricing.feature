@domain:cost-estimation @area:live-pricing @from:idle-hunter-lib/pricing
Feature: Pricing findings from the AWS Pricing API
  Lets operators replace the rough estimates with real on-demand prices for the region being scanned, without losing the report when the lookup fails.

  Background:
    Given the operator scans with live pricing

  @id:cost-estimation.live-pricing.001 @rule:cost.live.scan-region-monthly-rate @verified @source:idle_hunter_lib/pricing.py#price @test:tests/test_idle_hunter.py#test_rds_live_pricing_queries_the_instance_shape_not_a_flat_rate
  Scenario Outline: A live price is the scanned region's on-demand rate, turned into a monthly cost
    Given the Pricing API lists <rate> USD <unit> for a <resource> in eu-west-2
    When the operator runs a scan of eu-west-2
    Then the finding's monthly cost is <monthly_usd> USD

    Examples:
      | resource            | rate   | unit          | monthly_usd |
      | Elastic IP          | 0.005  | per hour      | 3.65        |
      | NAT gateway         | 0.050  | per hour      | 36.50       |
      | load balancer       | 0.0252 | per hour      | 18.40       |
      | EBS volume of 1 GiB | 0.088  | per GiB-month | 0.09        |
      | snapshot of 1 GiB   | 0.053  | per GiB-month | 0.05        |

  @id:cost-estimation.live-pricing.002 @rule:cost.live.lookup-failure-falls-back @verified @source:idle_hunter_lib/pricing.py#price @test:tests/test_idle_hunter.py#test_price_falls_back_to_estimates_without_live_lookup @questionable
  Scenario: A failed live price lookup falls back to the built-in price
    Given the operator's credentials are refused the Pricing API
    When the operator runs a scan
    Then a load balancer with no targets is reported at 18.00 USD a month
    And the scan still reports every finding

  @id:cost-estimation.live-pricing.003 @rule:cost.live.one-product-per-kind @inferred @source:idle_hunter_lib/pricing.py#PRICE_QUERIES @questionable
  Scenario Outline: Live pricing prices every volume as gp3 and every load balancer as an Application Load Balancer
    Given a <resource> zombie is found
    When the operator runs a scan
    Then its monthly cost uses the <priced_as> price

    Examples:
      | resource                              | priced_as                 |
      | io2 EBS volume                        | gp3 storage               |
      | gp2 EBS volume                        | gp3 storage               |
      | Network Load Balancer with no targets | Application Load Balancer |
      | Gateway Load Balancer with no targets | Application Load Balancer |
