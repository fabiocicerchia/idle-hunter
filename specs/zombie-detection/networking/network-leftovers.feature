@domain:zombie-detection @area:networking @from:idle-hunter-lib/scan
Feature: Finding network leftovers
  Lets an operator see Elastic IPs, network interfaces and NAT gateways that are billing or pinning resources without doing any work.

  Background:
    Given the operator's AWS account in region eu-west-1

  @id:zombie-detection.networking.001 @rule:zombie-detection.networking.unassociated-eip-reported @verified @source:idle_hunter_lib/scan.py#scan_eips @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario: An Elastic IP not associated with anything is reported, an associated one is not
    Given Elastic IP 198.51.100.10 (eipalloc-0001) has no association
    And Elastic IP 198.51.100.11 (eipalloc-0002) is associated
    When the operator scans the region
    Then eipalloc-0001 is reported as eip-unassociated at the per-address monthly price
    And its note reads "elastic IP 198.51.100.10 not associated"
    And eipalloc-0002 is not reported

  @id:zombie-detection.networking.002 @rule:zombie-detection.networking.detached-eni-reported-free-unless-service-owned @verified @source:idle_hunter_lib/scan.py#scan_enis @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario: A detached network interface you own is reported at no cost, one an AWS service owns never is
    Given detached network interface eni-0orphan in subnet-0a1b with no description
    And detached network interface eni-0rds created and managed by RDS
    When the operator scans the region
    Then eni-0orphan is reported as eni-unattached with a monthly cost of 0.00
    And its note reads "detached network interface in subnet-0a1b (no description) — free, but it pins its subnet and security groups"
    And eni-0rds is not reported

  @id:zombie-detection.networking.003 @rule:zombie-detection.networking.idle-nat-requires-traffic-evidence @verified @source:idle_hunter_lib/scan.py#scan_nat_gateways @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario Outline: An available NAT gateway is reported only when CloudWatch shows it sent little or nothing in 30 days
    Given available NAT gateway nat-0idle, up for 300 days
    And CloudWatch reports <traffic> sent to destinations over the last 30 days
    When the operator scans the region
    Then nat-0idle is <outcome>

    Examples:
      | traffic              | outcome                                                                   |
      | 0 bytes              | reported as nat-idle with note "NAT gateway sent 0.0 MiB in 30d, up 300d" |
      | 5 MiB                | reported as nat-idle with note "NAT gateway sent 5.0 MiB in 30d, up 300d" |
      | 50 MiB               | not reported                                                              |
      | no datapoints at all | not reported                                                              |
