# Basic Example

What it shows: turning a scan into a cleanup script you review before running
— with a snapshot in front of every volume delete.

## Run

Read-only, safe against any account:

```sh
idle-hunter scan --region eu-west-1
```

Then generate the reviewable script:

```sh
./review.sh eu-west-1 90 > cleanup.sh
```

```bash
#!/usr/bin/env bash
# Generated from: idle-hunter scan --region eu-west-1 --min-confidence 90
# Review every line before running. Delete what you are unsure about.
set -euo pipefail

# [95%] ebs-unattached vol-0abc - 200 GiB, created 210d ago, status=available
#   ~$16.0/mo (estimate, not your price)
aws ec2 create-snapshot --region eu-west-1 --volume-id vol-0abc --description 'pre-delete idle-hunter'
aws ec2 delete-volume --region eu-west-1 --volume-id vol-0abc

# [90%] eip-unassociated eipalloc-0def - elastic IP 52.1.2.3 not associated
#   ~$3.6/mo (estimate, not your price)
aws ec2 release-address --region eu-west-1 --allocation-id eipalloc-0def

# 2 finding(s), ~$20/mo estimated
```

Nothing has run yet. `review.sh` only reads.

## Then actually review it

This is the step the example exists for. For each block, the question is not
"is the score high" but "do I know what this was":

```sh
$EDITOR cleanup.sh          # delete the entries you cannot account for
bash cleanup.sh
```

The snapshot line before each volume delete is deliberate. It costs cents per
month; the volume it protects might be the only copy of something the scanner
has no way to know about. `idle-hunter` caps its confidence at 95 for exactly
this reason — there is no score at which a machine should decide.

## Start high, then widen

```sh
./review.sh eu-west-1 90 > cleanup.sh    # unattached volumes, stranded EIPs
./review.sh eu-west-1 80 > cleanup.sh    # adds long-idle empty load balancers
./review.sh eu-west-1 60 > cleanup.sh    # adds recent empty LBs — read carefully
```

At 60 you are into load balancers created in the last month, which are as
likely to be something half-built as something abandoned.

## Watch it find nothing

On a clean account:

```text
# idle-hunter report — 0 finding(s), ~$0/mo reclaimable
```

Worth confirming, because the failure mode of a scanner with the wrong
credentials is also an empty report. If you expected findings and got none,
check that the role has the `Describe*` permissions and that `--region` is the
region the resources are actually in.
