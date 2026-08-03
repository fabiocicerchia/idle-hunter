# Getting Started

## Prerequisites

Python 3.10+, and AWS credentials with read-only access. `boto3` is the only
dependency.

## Install

```sh
pipx install .
```

Or for development:

```sh
make dev      # pip install -e . pytest ruff
```

## IAM

Read-only. Attach this and nothing more:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ec2:DescribeVolumes",
      "ec2:DescribeAddresses",
      "ec2:DescribeRegions",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetHealth"
    ],
    "Resource": "*"
  }]
}
```

There is no delete path in the tool, so there is no reason for the credentials
to have one. Running this with an admin role gives up the one guarantee it
offers.

## First scan

```sh
idle-hunter scan --region eu-west-1
```

```text
# idle-hunter report — 3 finding(s), ~$34/mo reclaimable

[ 95%] ebs-unattached  vol-0abc…  (eu-west-1)  ~$16.0/mo
       200 GiB, created 210d ago, status=available
[ 90%] eip-unassociated  eipalloc-0def…  (eu-west-1)  ~$3.6/mo
       elastic IP 52.1.2.3 not associated
[ 85%] elb-no-targets  legacy-api-alb  (eu-west-1)  ~$18.0/mo
       application LB with 0 registered targets
```

Sorted by confidence, then by cost.

## Get the commands, review them, run them yourself

```sh
idle-hunter scan --region eu-west-1 --min-confidence 80 --commands
```

```text
[ 95%] ebs-unattached  vol-0abc…  (eu-west-1)  ~$16.0/mo
       200 GiB, created 210d ago, status=available
       $ aws ec2 delete-volume --region eu-west-1 --volume-id vol-0abc…
```

The tool prints them and stops. It has no delete path and no `--yes`, by
design: a scanner cannot know that the volume detached six months ago is not
the only copy of something.

Before running any of them, take the cheap insurance:

```sh
aws ec2 create-snapshot --volume-id vol-0abc --description "pre-delete, idle-hunter"
```

## Reading the confidence score

The scores are deterministic and small enough to check by hand:

| Finding | How the score is built |
|---|---|
| `ebs-unattached` | 50 base, +5 per week unattached (cap +35), +10 if it has no `Name` tag, capped at 95 |
| `eip-unassociated` | flat 90 — it costs money and has no state to lose |
| `elb-no-targets` | 85 if older than 30 days, 60 if newer; 0 (not reported) if it has targets |

**Nothing ever scores 100.** The cap is deliberate: a scanner cannot know your
intent, and a number that reads as "certain" invites automation this tool does
not want to enable.

An unnamed volume scoring higher than a named one is the strongest signal here.
Resources someone cared about get tagged.

## Scan everything

```sh
idle-hunter scan --all-regions --min-confidence 80
```

Expect it to take a while. Volumes and Elastic IPs are one API call per region;
load balancers are one call per LB plus one per target group, so an account
with many of them dominates the runtime.

## Feed it to something else

```sh
idle-hunter scan --all-regions --json > findings.json
```

The JSON has the full finding — `kind`, `id`, `region`, `confidence`,
`monthly_usd`, `note`, `command` — and is unfiltered by `--min-confidence`
formatting, so downstream can apply its own threshold.

## The costs are estimates, and not yours

`$0.08/GiB` for EBS, `$3.60` for an Elastic IP, `$18` for a load balancer.
Rough us-east-1 list prices, ignoring region, volume type and any discount you
have negotiated.

Use them to rank findings and to decide whether the cleanup is worth an
afternoon. Do not put the total in a document that will be compared against a
bill. Real pricing is on the roadmap.

## Development

```sh
make dev      # editable install + pytest + ruff
make test     # pytest -q
make lint     # ruff check .
```

The tests cover the scoring functions, which is where the opinions are. The
boto3 calls are not mocked and do not need to be.
