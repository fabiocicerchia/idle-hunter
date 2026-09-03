# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0](https://github.com/fabiocicerchia/idle-hunter/compare/v1.1.0...v1.2.0) (2026-09-03)


### Features

* **pricing:** wire --live-pricing into the RDS check ([#33](https://github.com/fabiocicerchia/idle-hunter/issues/33)) ([684bf3f](https://github.com/fabiocicerchia/idle-hunter/commit/684bf3fa32a9cb73339260896126f1709b3fe730))

## [1.1.0](https://github.com/fabiocicerchia/idle-hunter/compare/v1.0.0...v1.1.0) (2026-08-30)


### Features

* **docs:** build the docs site in Actions and drop Read the Docs ([#25](https://github.com/fabiocicerchia/idle-hunter/issues/25)) ([4afb888](https://github.com/fabiocicerchia/idle-hunter/commit/4afb888f4acab0ea24d493052af2c5460a69b57f))

## 1.0.0 (2026-08-06)


### Features

* **pricing:** resolve real prices via the Pricing API under --live-pricing ([5b66162](https://github.com/fabiocicerchia/idle-hunter/commit/5b661624a2b43a7dd542880736cfa2b628418f6e))
* scan regions in parallel, and find idle RDS and detached ENIs ([34c5967](https://github.com/fabiocicerchia/idle-hunter/commit/34c5967ffdc18ceeb331c72878acfbdc14e8932d))
* scan regions in parallel, and find idle RDS and detached ENIs ([16aef40](https://github.com/fabiocicerchia/idle-hunter/commit/16aef404b7abf62ba8cc4902213cab508aa786c8))
* **scan:** add idle NAT gateway check with CloudWatch traffic signals ([c80acec](https://github.com/fabiocicerchia/idle-hunter/commit/c80acec4dd9eadb8cabae8361123782d8e9de9fa))
* **scan:** add orphaned snapshot and unused AMI checks ([87208b6](https://github.com/fabiocicerchia/idle-hunter/commit/87208b6547f844945327a85c66fd3023bd9b51c6))
* **score:** lower confidence for IaC-managed resources ([2c61aed](https://github.com/fabiocicerchia/idle-hunter/commit/2c61aed6efa2dffc4690427170aa1a1ca6202791))


### Bug Fixes

* **ci:** install pytest even when the package has no [dev] extra ([99713b8](https://github.com/fabiocicerchia/idle-hunter/commit/99713b89131f1063770481cfdb8fb364093186dd))
* **ci:** stop security workflows failing on private repos ([#7](https://github.com/fabiocicerchia/idle-hunter/issues/7)) ([a20d52b](https://github.com/fabiocicerchia/idle-hunter/commit/a20d52b13130567807f8d90a83052025a855b0cb))
* **cli:** apply --min-confidence to --json output ([d16c3fa](https://github.com/fabiocicerchia/idle-hunter/commit/d16c3fa3941d5e74d87580e5211c4d68ec3f124f))
* **pre-commit:** stop check-yaml failing on Helm templates and multi-doc manifests ([4afa954](https://github.com/fabiocicerchia/idle-hunter/commit/4afa954b312257e6a3982fbf97cf1f2963f79345))

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
