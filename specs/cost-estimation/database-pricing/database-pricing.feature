@domain:cost-estimation @area:database-pricing @from:idle-hunter-lib/pricing
Feature: Pricing idle databases by their real shape
  Gives operators the actual monthly cost of an idle RDS instance, based on its class, engine, deployment and licence, and refuses to guess a price when the shape cannot be named.

  Background:
    Given the operator scans with live pricing

  @id:cost-estimation.database-pricing.001 @rule:cost.database.instance-shape-priced @verified @source:idle_hunter_lib/pricing.py#rds_shape @test:tests/test_idle_hunter.py#test_rds_shape_carries_class_engine_deployment_and_licence @test:tests/test_idle_hunter.py#test_rds_engine_name_maps_families_and_refuses_to_guess @test:tests/test_idle_hunter.py#test_rds_live_pricing_queries_the_instance_shape_not_a_flat_rate
  Scenario Outline: An idle database is priced by its class, engine, deployment and licence
    Given an idle <class> instance runs engine <engine> with Multi-AZ <multi_az> and licence <licence>
    When the operator runs a scan
    Then its price is the on-demand rate for <class>, <engine_name>, <deployment>, <licence_name> times 730 hours

    Examples:
      | class         | engine       | multi_az | licence                | engine_name  | deployment | licence_name           |
      | db.m5.large   | mysql        | off      | general-public-license | MySQL        | Single-AZ  | No license required    |
      | db.r6g.xlarge | postgres     | on       | postgresql-license     | PostgreSQL   | Multi-AZ   | No license required    |
      | db.r5.large   | aurora-mysql | off      | general-public-license | Aurora MySQL | Single-AZ  | No license required    |
      | db.m5.large   | oracle-ee    | off      | bring-your-own-license | Oracle       | Single-AZ  | Bring your own license |
      | db.m5.xlarge  | sqlserver-ex | off      | license-included       | SQL Server   | Single-AZ  | License included       |

  @id:cost-estimation.database-pricing.002 @rule:cost.database.unknown-shape-not-guessed @verified @source:idle_hunter_lib/pricing.py#rds_engine_name @test:tests/test_idle_hunter.py#test_rds_unnameable_engine_falls_back_without_querying @test:tests/test_idle_hunter.py#test_rds_engine_name_maps_families_and_refuses_to_guess
  Scenario Outline: A database whose shape cannot be named is priced at the baseline, never as some other engine
    Given an idle instance has <problem>
    When the operator runs a scan
    Then no live price is looked up for it
    And its monthly cost is 60.00 USD
    And its note says the cost shown is a db.t3.medium baseline

    Examples:
      | problem                    |
      | engine neptune             |
      | no engine reported         |
      | no instance class reported |

  @id:cost-estimation.database-pricing.003 @rule:cost.database.live-price-disclosed @verified @source:idle_hunter_lib/pricing.py#price_is_live @test:tests/test_idle_hunter.py#test_rds_live_pricing_queries_the_instance_shape_not_a_flat_rate
  Scenario: A database priced from the Pricing API says which shape it was priced as
    Given an idle db.m5.large mysql Single-AZ instance is found
    And the Pricing API lists 0.171 USD per hour for that shape
    When the operator runs a scan
    Then its monthly cost is 124.83 USD
    And its note says "priced as db.m5.large Single-AZ on-demand"
