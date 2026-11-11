@domain:reporting @area:cleanup-commands @from:idle-hunter-lib/scan
Feature: Suggesting a cleanup command for each finding
  Gives the operator a ready-to-review AWS CLI command for each zombie, which the tool never runs itself.

  Background:
    Given the operator's AWS account in region eu-west-1

  @id:reporting.cleanup-commands.003 @rule:reporting.cleanup-commands.command-per-kind @inferred @source:idle_hunter_lib/scan.py#scan_rds
  Scenario Outline: Each finding carries the AWS CLI command that would delete it, and a database delete keeps a final snapshot
    Given the region holds a zombie <id> that is reported as <kind>
    When the operator scans the region
    Then the finding's suggested command is "<command>"

    Examples:
      | kind              | id            | command                                                                                                                         |
      | ebs-unattached    | vol-0dead     | aws ec2 delete-volume --region eu-west-1 --volume-id vol-0dead                                                                  |
      | eip-unassociated  | eipalloc-0001 | aws ec2 release-address --region eu-west-1 --allocation-id eipalloc-0001                                                        |
      | eni-unattached    | eni-0orphan   | aws ec2 delete-network-interface --region eu-west-1 --network-interface-id eni-0orphan                                          |
      | rds-idle          | orders-db     | aws rds delete-db-instance --region eu-west-1 --db-instance-identifier orders-db --final-db-snapshot-identifier orders-db-final |
      | elb-no-targets    | legacy-alb    | aws elbv2 delete-load-balancer --region eu-west-1 --load-balancer-arn <the load balancer's ARN>                                 |
      | nat-idle          | nat-0idle     | aws ec2 delete-nat-gateway --region eu-west-1 --nat-gateway-id nat-0idle                                                        |
      | ami-unused        | ami-0base     | aws ec2 deregister-image --region eu-west-1 --image-id ami-0base                                                                |
      | snapshot-orphaned | snap-0orphan  | aws ec2 delete-snapshot --region eu-west-1 --snapshot-id snap-0orphan                                                           |
