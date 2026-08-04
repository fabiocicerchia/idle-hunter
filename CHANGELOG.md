# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- AWS zombie-resource scan for unattached EBS volumes, unassociated Elastic
  IPs and empty load balancers, each with a confidence score and a monthly
  cost estimate. `--commands` prints the AWS CLI calls; nothing is deleted.
- Three more checks: idle NAT gateways (CloudWatch `BytesOutToDestination`),
  snapshots whose source volume no longer exists, and self-owned AMIs no
  instance runs.
- CloudWatch traffic signals raise the score of an empty load balancer that
  also saw no bytes in 30 days. No datapoints scores as unknown, never idle.
- Resources tagged as CloudFormation/Terraform/CDK/Pulumi/Beanstalk-managed
  score 30 lower — deleting those by hand only gets reverted.
- `--live-pricing` resolves real per-region prices via the Pricing API,
  falling back to the built-in estimates when the lookup is unavailable.

### Fixed

- `--json` now honours `--min-confidence`, so a cleanup script generated from
  it cannot contain findings the caller filtered out.

Not yet released.
