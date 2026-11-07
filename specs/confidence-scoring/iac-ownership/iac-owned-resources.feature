@domain:confidence-scoring @area:iac-ownership @from:idle-hunter-lib/models
Feature: Lowering confidence for resources owned by infrastructure-as-code
  Operators need resources owned by Terraform, CloudFormation, CDK and similar tools to score lower and say so, because deleting them by hand just gets reverted by the next deploy.

  Background:
    Given the operator scans an AWS account in region eu-west-1

  @id:confidence-scoring.iac-ownership.001 @rule:confidence-scoring.iac-ownership.penalty-with-floor @verified @source:idle_hunter_lib/models.py#finding @test:tests/test_idle_hunter.py#test_iac_managed_tags_lower_the_score @test:tests/test_scan_wiring.py#test_scan_region_finds_one_of_each_kind
  Scenario Outline: An IaC-owned zombie loses 30 confidence points, never dropping below 5, and is flagged for stack deletion
    Given an unattached EBS volume vol-0abc1234 that would score <base> confidence
    And the volume is tagged "terraform:module" = "vpc"
    When the operator runs a scan
    Then the finding for vol-0abc1234 shows confidence <shown>
    And its note ends with "— IaC-managed (delete via the stack, not the CLI)"

    Examples:
      | base | shown |
      | 90   | 60    |
      | 95   | 65    |
      | 30   | 5     |
      | 20   | 5     |

  @id:confidence-scoring.iac-ownership.002 @rule:confidence-scoring.iac-ownership.recognised-ownership-tags @verified @source:idle_hunter_lib/models.py#iac_managed @test:tests/test_idle_hunter.py#test_iac_managed_tags_lower_the_score
  Scenario Outline: Ownership by an IaC tool is recognised from the resource's tags, regardless of letter case
    Given an unattached EBS volume vol-0abc1234 that would score 90 confidence
    And the volume is tagged "<key>" = "<value>"
    When the operator runs a scan
    Then the finding for vol-0abc1234 shows confidence <shown>
    And the note <mentions> "IaC-managed"

    Examples:
      | key                               | value             | shown | mentions         |
      | aws:cloudformation:stack-name     | prod              | 60    | contains         |
      | elasticbeanstalk:environment-name | web               | 60    | contains         |
      | eks:cluster-name                  | main              | 60    | contains         |
      | kubernetes.io/cluster/main        | owned             | 60    | contains         |
      | terraform:module                  | vpc               | 60    | contains         |
      | pulumi:project                    | billing           | 60    | contains         |
      | CDK-App                           | api               | 60    | contains         |
      | managed_by                        | Terraform         | 60    | contains         |
      | Provisioner                       | Ansible           | 60    | contains         |
      | created-by                        | CloudFormation    | 60    | contains         |
      | managed-by                        | ops-team          | 90    | does not contain |
      | Name                              | terraforming-mars | 90    | does not contain |

  @id:confidence-scoring.iac-ownership.003 @rule:confidence-scoring.iac-ownership.untagged-unchanged @verified @source:idle_hunter_lib/models.py#finding @test:tests/test_idle_hunter.py#test_iac_managed_tags_lower_the_score
  Scenario: A resource without IaC ownership tags keeps its full score and plain note
    Given an unassociated Elastic IP eipalloc-0abc1234 that would score 90 confidence
    And the address has no tags
    When the operator runs a scan
    Then the finding for eipalloc-0abc1234 shows confidence 90
    And its note does not mention "IaC-managed"
