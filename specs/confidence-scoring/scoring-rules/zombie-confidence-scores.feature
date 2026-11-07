@domain:confidence-scoring @area:scoring-rules @from:idle-hunter-lib/score
Feature: Scoring how safe a zombie resource is to delete
  Gives operators a 0–100 confidence-to-delete score per zombie resource, rising with evidence of abandonment and never reaching 100, so they can decide what to clean up first and what to leave alone.

  Background:
    Given Given the operator's AWS account has resources in region eu-west-1

  @id:confidence-scoring.scoring-rules.001 @rule:scoring.ebs.unattached-volume-score-grows-with-age-and-namelessness @verified @source:idle_hunter_lib/score.py#score_unattached_volume @test:tests/test_idle_hunter.py#test_volume_score_grows_with_age_and_caps @questionable
  Scenario Outline: An unattached volume scores higher the older it is and when it has no Name tag
    Given Given an unattached EBS volume vol-0a1b2c created <age> days ago
    And And the volume <name_tag> a Name tag
    When When the operator scans eu-west-1
    Then Then vol-0a1b2c is reported as ebs-unattached with confidence <confidence>

    Examples:
      | age | name_tag      | confidence |
      | 1   | has           | 50         |
      | 1   | does not have | 60         |
      | 14  | has           | 60         |
      | 365 | has           | 85         |
      | 365 | does not have | 95         |

  @id:confidence-scoring.scoring-rules.002 @rule:scoring.eip.unassociated-address-scores-90 @inferred @source:idle_hunter_lib/score.py#score_unassociated_eip
  Scenario: An unassociated Elastic IP always scores 90
    Given Given Elastic IP 203.0.113.10 is not associated with anything
    When When the operator scans eu-west-1
    Then Then 203.0.113.10 is reported as eip-unassociated with confidence 90

  @id:confidence-scoring.scoring-rules.003 @rule:scoring.eni.service-owned-interface-never-reported @verified @source:idle_hunter_lib/score.py#score_unattached_eni @test:tests/test_idle_hunter.py#test_eni_score_zero_when_a_service_owns_it
  Scenario Outline: A detached network interface owned by an AWS service is never reported
    Given Given a detached network interface eni-0f1e2d that <owner> created
    When When the operator scans eu-west-1
    Then Then the scan reports <outcome> for eni-0f1e2d

    Examples:
      | owner                                                              | outcome                                      |
      | the operator                                                       | an eni-unattached finding with confidence 85 |
      | an AWS service (RDS, Lambda, a load balancer node, a VPC endpoint) | no finding                                   |

  @id:confidence-scoring.scoring-rules.004 @rule:scoring.rds.idle-only-on-proven-low-connections @verified @source:idle_hunter_lib/score.py#score_idle_rds @test:tests/test_idle_hunter.py#test_rds_score_treats_missing_metrics_as_unknown
  Scenario Outline: A database is scored idle only when its connection count proves it, never on missing metrics
    Given Given an available RDS instance orders-db
    And And CloudWatch shows <connections> connections to it over the last 30 days
    When When the operator scans eu-west-1
    Then Then the scan reports <outcome> for orders-db

    Examples:
      | connections | outcome                                |
      | 0           | an rds-idle finding with confidence 80 |
      | 5           | an rds-idle finding with confidence 55 |
      | 30          | an rds-idle finding with confidence 55 |
      | 31          | no finding                             |
      | 5000        | no finding                             |
      | no data     | no finding                             |

  @id:confidence-scoring.scoring-rules.005 @rule:scoring.elb.empty-lb-score-by-age-and-traffic @verified @source:idle_hunter_lib/score.py#score_empty_lb @test:tests/test_idle_hunter.py#test_lb_score_zero_when_targets_exist @test:tests/test_idle_hunter.py#test_lb_score_boosted_by_zero_traffic
  Scenario Outline: A load balancer with no targets scores by age, with a bonus when it carried no traffic
    Given Given load balancer web-alb was created <age> days ago and has <targets> registered targets
    And And CloudWatch shows <traffic> processed over the last 30 days
    When When the operator scans eu-west-1
    Then Then the scan reports <outcome> for web-alb

    Examples:
      | age | targets | traffic     | outcome                                      |
      | 90  | 3       | any traffic | no finding                                   |
      | 90  | 0       | no data     | an elb-no-targets finding with confidence 85 |
      | 90  | 0       | 10000 bytes | an elb-no-targets finding with confidence 85 |
      | 90  | 0       | 0 bytes     | an elb-no-targets finding with confidence 95 |
      | 30  | 0       | no data     | an elb-no-targets finding with confidence 60 |
      | 10  | 0       | 0 bytes     | an elb-no-targets finding with confidence 70 |

  @id:confidence-scoring.scoring-rules.006 @rule:scoring.nat.idle-only-on-proven-low-traffic @verified @source:idle_hunter_lib/score.py#score_idle_nat @test:tests/test_idle_hunter.py#test_nat_score_needs_a_metric
  Scenario Outline: A NAT gateway is scored idle only when its outbound traffic proves it, never on missing metrics
    Given Given an available NAT gateway nat-0123abcd
    And And CloudWatch shows <bytes_out> sent to destinations over the last 30 days
    When When the operator scans eu-west-1
    Then Then the scan reports <outcome> for nat-0123abcd

    Examples:
      | bytes_out         | outcome                               |
      | 0 bytes           | a nat-idle finding with confidence 85 |
      | just under 10 MiB | a nat-idle finding with confidence 65 |
      | 10 MiB exactly    | a nat-idle finding with confidence 65 |
      | just over 10 MiB  | no finding                            |
      | no data           | no finding                            |

  @id:confidence-scoring.scoring-rules.007 @rule:scoring.snapshot.orphaned-snapshot-score-grows-with-age @verified @source:idle_hunter_lib/score.py#score_stale_snapshot @test:tests/test_idle_hunter.py#test_snapshot_and_ami_scores
  Scenario Outline: A snapshot whose source volume is gone scores higher with age, and one with a live source is not reported
    Given Given snapshot snap-0aa11bb was taken <age> days ago
    And And its source volume <source>
    When When the operator scans eu-west-1
    Then Then the scan reports <outcome> for snap-0aa11bb

    Examples:
      | age | source           | outcome                                        |
      | 400 | still exists     | no finding                                     |
      | 1   | no longer exists | a snapshot-orphaned finding with confidence 45 |
      | 90  | no longer exists | a snapshot-orphaned finding with confidence 60 |
      | 400 | no longer exists | a snapshot-orphaned finding with confidence 80 |

  @id:confidence-scoring.scoring-rules.008 @rule:scoring.ami.unused-image-score-grows-with-age @verified @source:idle_hunter_lib/score.py#score_unused_ami @test:tests/test_idle_hunter.py#test_snapshot_and_ami_scores
  Scenario Outline: An image no instance runs scores higher with age, and one in use is not reported
    Given Given self-owned image ami-0c0ffee registered <age> days ago
    And And <usage>
    When When the operator scans eu-west-1
    Then Then the scan reports <outcome> for ami-0c0ffee

    Examples:
      | age  | usage                             | outcome                                  |
      | 2000 | a non-terminated instance runs it | no finding                               |
      | 1    | no instance runs it               | an ami-unused finding with confidence 40 |
      | 90   | no instance runs it               | an ami-unused finding with confidence 55 |
      | 2000 | no instance runs it               | an ami-unused finding with confidence 75 |
