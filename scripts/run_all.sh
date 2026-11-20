#!/usr/bin/env bash
# Runs phases 1 to 5 in order, unattended, and never stops to ask.
# Every human step comes after this script finishes (START_HERE.md, part 4).
set -uo pipefail
cd "$(dirname "$0")/.."
# Python: project venv on Windows (Scripts/) or Linux/macOS (bin/), else the system python.
PY=.venv/Scripts/python; [ -x "$PY" ] || PY=.venv/bin/python; [ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
for P in 1 2 3 4 5; do
  bash scripts/run_phase.sh "$P"
done
echo
echo "Automated build finished."
"$PY" scripts/progress.py summary
echo "Next: the end-of-run checklist in START_HERE.md, part 4."
