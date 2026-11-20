#!/usr/bin/env bash
# Closing pass, run once after the human steps in START_HERE.md, part 4. No input needed.
set -uo pipefail
cd "$(dirname "$0")/.."
claude -p "Follow CLAUDE.md exactly. Do the closing step at the end of docs/PLAN.md. Do not ask questions." \
  --dangerously-skip-permissions --max-turns 120
python3 scripts/progress.py summary
