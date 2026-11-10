# Specifications of idle-hunter

What this code does, one atomic Gherkin scenario per behaviour, read from the code by code-atlas.
Tags: `@verified` a test asserts it · `@inferred` read from the code only · `@gap` an entry point no test covers · `@human` written or amended by a person, never rewritten.

## Command line
How users run idle-hunter from a terminal.

- **Exit status and diagnostics**: [Telling a complete scan from a partial one](command-line/exit-status/scan-exit-status.feature) (3)
- **Launcher**: [Launching idle-hunter](command-line/launcher/launching-idle-hunter.feature) (1)
- **Scan command**: [Running a scan](command-line/scan-command/scan-command.feature) (4)

## Confidence scoring
The 0–100 confidence-to-delete score attached to every finding.

- **Infrastructure-as-code ownership**: [Lowering confidence for resources owned by infrastructure-as-code](confidence-scoring/iac-ownership/iac-owned-resources.feature) (3)
- **Scoring rules**: [Scoring how safe a zombie resource is to delete](confidence-scoring/scoring-rules/zombie-confidence-scores.feature) (7)

## Cost estimation
Estimating the monthly spend you would get back by removing each finding.

- **Built-in prices**: [Estimating reclaimable cost from built-in prices](cost-estimation/built-in-prices/built-in-prices.feature) (3)
- **Database pricing**: [Pricing idle databases by their real shape](cost-estimation/database-pricing/database-pricing.feature) (3)
- **Live pricing**: [Pricing findings from the AWS Pricing API](cost-estimation/live-pricing/live-pricing.feature) (3)

## Reporting
Showing findings to people and to other tools.

- **Cleanup commands**: [Suggesting a cleanup command for each finding](reporting/cleanup-commands/cleanup-commands-per-kind.feature) (1), [Reviewing cleanup commands](reporting/cleanup-commands/cleanup-commands.feature) (1)
- **Cleanup review script**: [Turning a scan into a cleanup script for review](reporting/cleanup-review-script/cleanup-review-script.feature) (7)
- **Findings**: [What each finding reports](reporting/findings/finding-record.feature) (1)
- **JSON output**: [Machine-readable findings](reporting/json-output/json-output.feature) (2)
- **Text report**: [Reading the scan report](reporting/text-report/text-report.feature) (3)

## Scan coverage
Which AWS regions a scan covers and how it copes when some fail.

- **Partial failures**: [Sweeping several regions at once](scan-coverage/partial-failures/all-regions-sweep.feature) (1)
- **Single-region scan**: [Scanning one region](scan-coverage/single-region/single-region-scan.feature) (1)

## Zombie detection
Finding AWS resources that cost money but are no longer used.

- **Idle databases**: [Finding idle databases](zombie-detection/databases/idle-databases.feature) (1)
- **Empty load balancers**: [Finding empty load balancers](zombie-detection/load-balancers/empty-load-balancers.feature) (1)
- **Network leftovers**: [Finding network leftovers](zombie-detection/networking/network-leftovers.feature) (3)
- **Storage leftovers**: [Finding storage leftovers](zombie-detection/storage/storage-leftovers.feature) (3)
