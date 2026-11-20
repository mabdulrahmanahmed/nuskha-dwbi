#!/usr/bin/env bash
# Starts the build, or resumes it after any interruption (laptop off, sleep, closed terminal).
# Safe to run any number of times: finished units are skipped and an interrupted unit is picked up again.
cd "$(dirname "$0")/.."
if command -v tmux >/dev/null; then
  if tmux has-session -t build 2>/dev/null; then
    echo "The build is already running. Showing it (press Ctrl+B then D to hide it and keep it running)."
  else
    tmux new-session -d -s build "bash scripts/run_all.sh; echo; echo 'Run ended. Press Enter to close.'; read"
    echo "Build started."
  fi
  tmux attach -t build
else
  echo "tmux not found; running in this window. Keep it open."
  bash scripts/run_all.sh
fi
