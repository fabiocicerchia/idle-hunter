# idle-hunter

[![CI](https://github.com/fabiocicerchia/idle-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiocicerchia/idle-hunter/actions/workflows/ci.yml)
[![Code Quality](https://github.com/fabiocicerchia/idle-hunter/actions/workflows/code-quality.yml/badge.svg)](https://github.com/fabiocicerchia/idle-hunter/actions/workflows/code-quality.yml)
[![Security](https://github.com/fabiocicerchia/idle-hunter/actions/workflows/security.yml/badge.svg)](https://github.com/fabiocicerchia/idle-hunter/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/fabiocicerchia/idle-hunter/badge)](https://securityscorecards.dev/viewer/?uri=github.com/fabiocicerchia/idle-hunter)

A **zombie-resource scanner** for AWS: unattached EBS volumes, unassociated
Elastic IPs, detached network interfaces, load balancers with zero targets,
idle NAT gateways, idle RDS instances, orphaned snapshots and unused AMIs —
each with a **confidence-to-delete score (0–100)** and the monthly cost you'd
reclaim.

`--all-regions` scans regions in parallel (`--workers`, default 8). A region
that fails is named on stderr and the run exits `3`, so a lost region never
reads as a clean estate.

It never deletes anything. `--commands` prints ready-to-review AWS CLI
commands; running them is on you, by design.

```console
$ idle-hunter scan --region eu-west-1 --min-confidence 80 --commands
# idle-hunter report — 3 finding(s), ~$34/mo reclaimable

[ 95%] ebs-unattached  vol-0abc…  (eu-west-1)  ~$16.0/mo
       200 GiB, created 210d ago, status=available
       $ aws ec2 delete-volume --region eu-west-1 --volume-id vol-0abc…
[ 90%] eip-unassociated  eipalloc-0def…  (eu-west-1)  ~$3.6/mo
...
```

## Scoring model

Deterministic and explainable — e.g. an unattached volume starts at 50,
gains +5 per week unattached (capped) and +10 if unnamed, capped at 95:
there is deliberately no 100, because a scanner can't know your intent.

Resources tagged as owned by CloudFormation, Terraform, CDK or Beanstalk score
30 lower: deleting those by hand just gets reverted on the next apply.

## Install

```sh
pipx install .      # or: pip install .
```

## Usage

```sh
pipx install .
idle-hunter scan --region eu-west-1
idle-hunter scan --region eu-west-1 --live-pricing          # real prices, not estimates
idle-hunter scan --all-regions --json > findings.json       # for dashboards
```

IAM: read-only (`ec2:Describe*`, `elasticloadbalancing:Describe*`,
`cloudwatch:GetMetricStatistics`, plus `pricing:GetProducts` for
`--live-pricing`).

## Development

`make dev` then `make test` / `make lint`.

## Documentation

Full docs live in [`docs/`](docs/). Runnable examples live in [`examples/`](examples/).

## License

Apache-2.0 — see [LICENSE](LICENSE).
