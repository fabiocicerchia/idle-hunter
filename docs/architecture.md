# Architecture

One module, `idle_hunter.py`, with a hard line through the middle of it:
the half that talks to AWS, and the half that decides what a finding is worth.

```
scan_region(region)          ← the only code that calls boto3
    ec2.describe_volumes(status=available)
    ec2.describe_addresses()
    elbv2.describe_load_balancers → target_groups → target_health
        │
        └── score_*(resource)     ← pure functions, no AWS, no clock beyond now()
              │
              └── finding(...)    ← a dict: kind, id, region, confidence,
                                    monthly_usd, note, command
                    │
                    └── render()  ← sorts, filters, formats. Prints commands;
                                    never runs one.
```

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

`score_empty_lb` returns 0 when targets exist, and `render` drops zero-score
findings. "Not a finding" and "a finding I am unsure about" are the same code
path, which keeps the caller from having to know the difference.

## The cost estimates are constants, and they are wrong

`gb * 0.08` for EBS, `3.6` for an Elastic IP, `18.0` for a load balancer.
These are rough us-east-1 list prices, not your prices — they ignore region,
volume type (gp3 vs io2 is not a rounding error), and any discount you have.

They are there to rank findings and to make "is this worth an afternoon"
answerable, not to reconcile against a bill. Real pricing via the Pricing API
is on the roadmap and is the change that would make the totals meaningful.

## Where the API cost is

`describe_volumes` and `describe_addresses` are one call each. Load balancers
are **not**: it is one call per LB for its target groups, then one per target
group for health. On an account with many load balancers, `--all-regions` is
where the time goes.

`--all-regions` enumerates regions via `describe_regions` and scans each
serially. It is the honest implementation and it is slow; that is a known
ceiling, not a subtlety.

## Adding a check

1. A `score_*` pure function next to the others. It takes the AWS response
   shape and returns 0–100, with a cap below 100 and a docstring stating the
   rule in one line.
2. A block in `scan_region` that queries and appends `finding(...)` — including
   the `command`, which must be the exact CLI call a reviewer would run.
3. A test in `tests/` for the scoring function. The AWS half is not unit-tested
   and does not need to be; the scoring is the part with an opinion in it.

The bar for a new check is that a reader can act on it. A finding that is
always present and never worth acting on trains people to skim the report,
which costs more than the check is worth.
