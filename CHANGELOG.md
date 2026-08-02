# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- AWS zombie-resource scan for unattached EBS volumes, unassociated Elastic
  IPs and empty load balancers, each with a confidence score and a monthly
  cost estimate. `--commands` prints the AWS CLI calls; nothing is deleted.

Not yet released.
