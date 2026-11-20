#!/usr/bin/env bash
# Closing pass, run once after the human steps in START_HERE.md, part 4. No input needed.
set -uo pipefail
cd "$(dirname "$0")/.."
# Python: project venv on Windows (Scripts/) or Linux/macOS (bin/), else the system python.
PY=.venv/Scripts/python; [ -x "$PY" ] || PY=.venv/bin/python; [ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
claude -p "Follow CLAUDE.md exactly. Do the closing step at the end of docs/PLAN.md. Do not ask questions." \
  --dangerously-skip-permissions --max-turns 120
"$PY" scripts/progress.py summary
