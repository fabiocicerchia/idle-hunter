#!/usr/bin/env bash
# Turn a scan into a reviewable cleanup script, with a snapshot before every
# volume delete. Nothing here executes an AWS mutation — it writes a file for a
# human to read, edit, and run.
#
#   ./review.sh eu-west-1 90 > cleanup.sh
#
# Then read cleanup.sh line by line, delete the entries you are not sure about,
# and only then `bash cleanup.sh`.
set -euo pipefail

REGION="${1:?usage: review.sh <region> [min-confidence]}"
MIN="${2:-80}"

FINDINGS="$(mktemp)"
trap 'rm -f "$FINDINGS"' EXIT

idle-hunter scan --region "$REGION" --min-confidence "$MIN" --json > "$FINDINGS"

python3 - "$FINDINGS" "$REGION" "$MIN" <<'PY'
import json
import sys

path, region, minimum = sys.argv[1], sys.argv[2], sys.argv[3]

print("#!/usr/bin/env bash")
print(f"# Generated from: idle-hunter scan --region {region} --min-confidence {minimum}")
print("# Review every line before running. Delete what you are unsure about.")
print("set -euo pipefail")
print()

with open(path) as fh:
    findings = json.load(fh)

for f in findings:
    print(f"# [{f['confidence']}%] {f['kind']} {f['id']} - {f['note']}")
    print(f"#   ~${f['monthly_usd']}/mo (estimate, not your price)")
    # A snapshot is cheap; an unrecoverable delete is not. The scanner cannot
    # know that this volume is not the only copy of something.
    if f["kind"] == "ebs-unattached":
        print(f"aws ec2 create-snapshot --region {f['region']} "
              f"--volume-id {f['id']} --description 'pre-delete idle-hunter'")
    print(f["command"] or "# (no command for this finding)")
    print()

print(f"# {len(findings)} finding(s), "
      f"~${sum(f['monthly_usd'] for f in findings):,.0f}/mo estimated")
PY
