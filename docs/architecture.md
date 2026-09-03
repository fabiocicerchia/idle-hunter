# Architecture

`idle_hunter.py` is the entrypoint and nothing else — a shebang, the
console-script name, and a call into `idle_hunter_lib/`. The hard line runs
through the package: the half that talks to AWS, and the half that decides what
a finding is worth.

```
idle_hunter.py            the entrypoint; keeps the console-script name
idle_hunter_lib/
    cli.py                argparse, the exit-code table, the one logging setup
    regions.py            scan_region / scan_regions — client wiring and the fan-out
    scan.py               the _scan_* functions: the only code that calls boto3
    score.py              score_* — pure, no AWS, no clock beyond now()
    models.py             Finding, and the one place the IaC penalty is applied
    pricing.py            PRICE_DEFAULTS, the Pricing API lookup and its cache
    metrics.py            cw_sum — CloudWatch, where no datapoints means unknown
    render.py             text and JSON output; prints commands, never runs one
```

One pass reads top to bottom through those modules:

```
scan_region(region)               ← builds the clients, fans out to the _scan_* half
    _scan_volumes                   describe_volumes         (also: the live-volume id set)
    _scan_images                    describe_images/instances (also: the AMI-backing snapshots)
    _scan_eips                      describe_addresses
    _scan_enis                      describe_network_interfaces
    _scan_load_balancers            describe_load_balancers → target_groups → target_health
    _scan_nat_gateways              describe_nat_gateways    + cw_sum(BytesOutToDestination)
    _scan_rds                       describe_db_instances    + cw_sum(DatabaseConnections)
    _scan_snapshots                 describe_snapshots
        │   ← the _scan_* functions are the only code that calls boto3
        │
        └── score_*(resource, signal)  ← pure functions, no AWS, no clock beyond now()
              │
              └── finding(...)      ← a frozen Finding: kind, id, region, confidence,
                                      monthly_usd, note, command. Field order is the
                                      JSON output order. Applies the IaC-managed
                                      penalty, in one place.
                    │
                    └── render()    ← sorts, filters, formats. Prints commands;
                                      never runs one.
```

Two of the checks hand something to a later one, which is why the call order in
`scan_region` is not alphabetical: volumes produce the set of volume ids that
still exist (a snapshot is only orphaned if its source is *not* in it), and
images produce the snapshot ids an AMI still backs (those are the AMI's finding,
not a snapshot finding — reporting both would double-count the same GiB).

## It never deletes, and that is structural

There is no delete path in this codebase. `--commands` puts an `aws` CLI
invocation in the output as a *string* — nothing executes it, and there is no
flag that would.

That is not caution for its own sake. A scanner cannot know intent: a volume
detached six months ago might be the only copy of something. The tool's job is
to find candidates and say how sure it is; the decision to destroy belongs to a
person who can be asked why.

The read-only IAM policy (`ec2:Describe*`,
`elasticloadbalancing:Describe*`) enforces the same thing from outside.

## The scores are deterministic and readable

Every score is a small pure function you can read in ten seconds:

```python
def score_unattached_volume(vol):
    score = 50                                  # unattached: suspicious, not damning
    score += min(age_days(...) // 7 * 5, 35)    # +5/week, capped at +35
    if no Name tag: score += 10                 # unnamed → likely forgotten
    return min(score, 95)
```

Two properties are on purpose:

**Nothing scores 100.** The cap is 95. A scanner cannot know your intent, and a
number that says "certain" invites someone to automate against it — which is
exactly the thing this tool declines to do.

**The inputs are all visible in the report.** The `note` field carries the
facts the score was computed from (size, age, status), so a reader can disagree
with the score without re-querying AWS.

`score_empty_lb` returns 0 when targets exist, and `render()` drops zero-score
findings. "Not a finding" and "a finding I am unsure about" are the same code
path, which keeps the caller from having to know the difference.

## Absent evidence is not evidence

`cw_sum` returns `None` — not `0` — when CloudWatch has no datapoints at all,
and every score treats `None` as *unknown*: `score_idle_nat` returns 0 rather
than flagging the gateway, and `score_empty_lb` skips its traffic bonus.

The distinction matters because the two cases look identical from the API and
mean opposite things. A NAT gateway created yesterday, or one in an account
where the metric is not published, reports nothing — and "nothing" read as
"idle" is exactly the false positive that gets a production egress path deleted.

## IaC ownership is a penalty, applied once

`finding()` in `models.py` checks the resource's tags for CloudFormation,
Terraform, CDK, Pulumi and Beanstalk markers, and subtracts 30 (floored at 5,
never to 0 — it stays visible, just not near the top).

It lives in `finding()` rather than in each `score_*` because every check routes
through it, so a new check gets the behaviour without knowing it exists. The
scores stay pure functions of the resource; ownership is a fact about who is
allowed to delete it, not about how dead it is. And that is the point: deleting
a Terraform-owned volume by hand does not save the money, it just makes the next
`apply` recreate it and someone spend an afternoon on the diff.

## The cost estimates are constants until you ask for better

`PRICE_DEFAULTS` holds rough us-east-1 list prices — `0.08`/GiB for EBS, `3.6`
for an Elastic IP, `18.0` for a load balancer. Not your prices: they ignore
region, volume type (gp3 vs io2 is not a rounding error), and any discount.

`--live-pricing` swaps them for a Pricing API lookup per `(key, region)`,
cached in `_PRICE_CACHE` in `pricing.py` for the process, so `--all-regions`
costs one lookup per price per region and no more. Every check reaches prices
through the same `price_of` partial, so a check does not know or care which
mode it is in.

RDS is the one price that is not a per-unit rate. A gigabyte costs a gigabyte,
but a database costs whatever its instance class, engine, deployment option and
licence model add up to — none of which is known until the instance is in hand.
So `PRICE_QUERIES["rds"]` leaves those four filters as `None` holes, and
`rds_shape()` fills them from the `DBInstance` at the call site; the cache key
widens to include them, so a `db.r6g.xlarge` and a `db.t3.small` in the same
region are two lookups, not one.

Two rules keep that from pricing the wrong thing:

- **A hole left unfilled is not queried.** `rds_engine_name()` returns `None`
  for an engine it cannot name rather than guessing, and `price()` falls back to
  the constant instead of sending a partial filter set — which would match some
  other shape's SKU and return a confident wrong number.
- **The finding says which number it is.** `price_is_live()` reads back whether
  the lookup landed, so a live-priced instance reads `priced as db.m5.large
  Single-AZ on-demand` and an estimated one keeps the honest `cost shown is a
  db.t3.medium baseline, scale it for db.m5.large`.

The lookup is deliberately failure-tolerant: a missing `pricing:GetProducts`,
or a product shape the filters do not match, falls back to the constant instead
of raising. A scan that dies because it could not price a volume it correctly
found is a worse tool than one that prints an approximate number. Discounts are
still invisible — nothing public knows them — so the totals get closer to the
bill without ever being it.

## Where the API cost is

Most checks are one paginated call per region. Load balancers are **not**: it is
one call per LB for its target groups, then one per target group for health, and
one `describe_tags` per LB that turns out to be a finding (tags do not come back
with the LB). NAT gateways and empty LBs each add a CloudWatch
`get_metric_statistics`. On an account with many load balancers, `--all-regions`
is where the time goes.

`--all-regions` enumerates regions via `describe_regions` and scans them in a
thread pool (`--workers`, default 8), each worker with its own boto3 Session.
A region that raises is collected into `failed`, reported, and the run exits 3.

## Adding a check

1. A `score_*` pure function in `idle_hunter_lib/score.py`, next to the
   others. It takes the AWS response shape (plus any CloudWatch signal, where
   `None` must mean *unknown*) and returns 0–100, with a cap below 100 and a
   docstring stating the rule in one line.
2. A `_scan_*` function in `idle_hunter_lib/scan.py` that queries and appends
   `finding(...)` — including the
   `command`, which must be the exact CLI call a reviewer would run, and the
   resource's tags, which is how it inherits the IaC penalty for free. Call it
   from `scan_region` in `regions.py`.
3. A test in `tests/` for the scoring function. The AWS half is not unit-tested
   and does not need to be; the scoring is the part with an opinion in it.

The bar for a new check is that a reader can act on it. A finding that is
always present and never worth acting on trains people to skim the report,
which costs more than the check is worth.
