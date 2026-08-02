# idle-hunter

A **zombie-resource scanner** for AWS: unattached EBS volumes, unassociated
Elastic IPs, load balancers with zero targets — each with a
**confidence-to-delete score (0–100)** and the monthly cost you'd reclaim.

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

## Usage

```sh
pipx install .
idle-hunter scan --region eu-west-1
idle-hunter scan --all-regions --json > findings.json    # for dashboards
```

IAM: read-only (`ec2:Describe*`, `elasticloadbalancing:Describe*`).

## Status & roadmap

- [x] EBS volumes, EIPs, empty LBs with scores + costs
- [ ] Idle NAT gateways (CloudWatch bytes), stale snapshots, unused AMIs
- [ ] CloudWatch-based "no I/O in 90d" signals to push scores higher
- [ ] Terraform/CloudFormation ownership detection (managed = lower score)
- [ ] Real pricing via the Pricing API instead of built-in estimates

## Development

`make dev` then `make test` / `make lint`.

## License

MIT — see [LICENSE](LICENSE).
