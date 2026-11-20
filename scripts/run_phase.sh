#!/usr/bin/env bash
# Runs every unit of one phase without human input: one headless Claude Code call per unit.
# A unit that keeps failing is marked BLOCKED; units that need it are SKIPPED; the run never stops to ask.
# Usage: bash scripts/run_phase.sh <phase 1-5>
# Permission prompts are skipped so the run never waits; see START_HERE.md for how to contain that.
set -uo pipefail
PHASE="$1"
cd "$(dirname "$0")/.."
python3 scripts/progress.py init >/dev/null

save_progress() {
  # Saves progress outside the machine after every unit: rewrite PROGRESS.md, commit, push to GitHub.
  python3 scripts/progress.py report
  git add -A >/dev/null 2>&1
  git commit -q -m "progress: $1" >/dev/null 2>&1 || true
  git push -q >/dev/null 2>&1 || true
}

save_progress "phase $PHASE started"
while true; do
  NEXT=$(python3 scripts/progress.py next "$PHASE")
  if [ "$NEXT" = "NONE" ]; then
    echo "[Phase $PHASE] finished."
    python3 scripts/progress.py status "$PHASE"
    exit 0
  fi
  if [ "$NEXT" = "STUCK" ]; then
    python3 scripts/progress.py skip "$PHASE"
    save_progress "phase $PHASE: skipped units that need a blocked unit"
    continue
  fi
  echo "[Phase $PHASE] starting unit $NEXT  ($(date '+%H:%M'))"
  # Heartbeat: a line every 5 minutes so you can see the run is alive.
  ( while true; do sleep 300; echo "  ...still working on $NEXT ($(date '+%H:%M'))"; done ) &
  BEAT=$!
  claude -p "Follow CLAUDE.md exactly. Complete unit $NEXT of docs/PLAN.md: run 'python3 scripts/progress.py start $NEXT', build it, run its acceptance check, then run 'python3 scripts/progress.py done $NEXT' (or 'blocked' after 3 failed attempts, with details in docs/BLOCKERS.md), update progress/notes.md and commit. Do not ask questions and do not start other units." \
    --dangerously-skip-permissions --max-turns 120 > progress/last_call.log 2>&1 || true
  kill "$BEAT" 2>/dev/null
  # Usage or rate limit: wait and retry without counting it as a failed attempt.
  if grep -qiE "usage limit|rate limit|limit reached|overloaded_error" progress/last_call.log \
     && [ "$(python3 scripts/progress.py get "$NEXT")" != "DONE" ]; then
    echo "[Phase $PHASE] Claude usage limit hit; waiting 30 minutes, then retrying $NEXT."
    for i in 1 2 3 4 5 6; do sleep 300; echo "  ...waiting for usage limit to reset ($(date '+%H:%M'))"; done
    continue
  fi
  STATUS=$(python3 scripts/progress.py get "$NEXT")
  if [ "$STATUS" = "DONE" ] || [ "$STATUS" = "BLOCKED" ]; then
    python3 scripts/progress.py line "$NEXT"
  fi
  save_progress "unit $NEXT $STATUS"
  if [ "$STATUS" = "PENDING" ] || [ "$STATUS" = "IN_PROGRESS" ]; then
    python3 scripts/progress.py attempt "$NEXT"
    echo "[Phase $PHASE] unit $NEXT did not finish in that run; retrying."
  fi
done
