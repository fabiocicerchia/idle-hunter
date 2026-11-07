@domain:zombie-detection @area:databases @from:idle-hunter-lib/scan
Feature: Finding idle databases
  Lets an operator see RDS instances nobody connects to, without ever flagging a database on missing evidence.

  Background:
    Given Given the operator's AWS account in region eu-west-1

  @id:zombie-detection.databases.001 @rule:zombie-detection.databases.idle-rds-requires-available-and-evidence @verified @source:idle_hunter_lib/scan.py#scan_rds @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario Outline: A database is reported idle only when it is available and CloudWatch shows almost no connections
    Given RDS instance orders-db is <status>
    And CloudWatch reports <connections> over the last 30 days
    When the operator scans the region
    Then orders-db is <outcome>

    Examples:
      | status    | connections          | outcome                                                         |
      | available | 0 connections        | reported as rds-idle, note says it took 0 connection(s) in 30d  |
      | available | 12 connections       | reported as rds-idle, note says it took 12 connection(s) in 30d |
      | available | 500 connections      | not reported                                                    |
      | available | no datapoints at all | not reported                                                    |
      | creating  | 0 connections        | not reported                                                    |

  @id:zombie-detection.databases.002 @rule:zombie-detection.databases.rds-cost-says-whether-priced-or-baseline @inferred @source:idle_hunter_lib/scan.py#scan_rds
  Scenario Outline: An idle database's note says whether its cost is its real price or a baseline
    Given available db.r6g.large postgres instance orders-db, Multi-AZ, with 0 connections in 30 days
    And <pricing>
    When the operator scans the region
    Then the note for orders-db ends "(<cost note>)"

    Examples:
      | pricing                         | cost note                                                        |
      | live pricing resolved its price | priced as db.r6g.large Multi-AZ on-demand                        |
      | no live price was resolved      | cost shown is a db.t3.medium baseline, scale it for db.r6g.large |
