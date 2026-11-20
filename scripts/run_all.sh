#!/usr/bin/env bash
# Runs phases 1 to 5 in order, unattended, and never stops to ask.
# Every human step comes after this script finishes (START_HERE.md, part 4).
set -uo pipefail
cd "$(dirname "$0")/.."
for P in 1 2 3 4 5; do
  bash scripts/run_phase.sh "$P"
done
echo
echo "Automated build finished."
python3 scripts/progress.py summary
echo "Next: the end-of-run checklist in START_HERE.md, part 4."
