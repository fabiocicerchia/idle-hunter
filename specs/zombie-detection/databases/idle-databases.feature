@domain:zombie-detection @area:databases @from:idle-hunter-lib/scan
Feature: Finding idle databases
  Lets an operator see RDS instances nobody connects to, without ever flagging a database on missing evidence.

  Background:
    Given the operator's AWS account in region eu-west-1

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
