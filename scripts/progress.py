"""Progress tracker for docs/PLAN.md.

Usage:
  python scripts/progress.py init                 # read units from docs/PLAN.md (keeps existing status)
  python scripts/progress.py start 2.04
  python scripts/progress.py done 2.04            # prints the progress line
  python scripts/progress.py blocked 2.04 "reason"
  python scripts/progress.py attempt 2.04         # runner: count a call that ended before the unit finished
  python scripts/progress.py next 2               # next runnable unit id, NONE, or STUCK
  python scripts/progress.py get 2.04             # status of one unit
  python scripts/progress.py status 2             # summary of a phase
  python scripts/progress.py skip 2               # mark units that need a blocked/skipped unit as SKIPPED
  python scripts/progress.py summary              # all phases, plus every BLOCKED or SKIPPED unit
  python scripts/progress.py retry                # reset BLOCKED and SKIPPED units to PENDING
  python scripts/progress.py report               # rewrite progress/PROGRESS.md (human-readable, committed)
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "PLAN.md"
STATE = ROOT / "progress" / "state.json"
MAX_ATTEMPTS = 3
ROW = re.compile(r"^\|\s*(\d\.\d\d)\s*\|(.*)\|\s*$")


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"units": {}}


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


def init():
    state = load()
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        uid = m.group(1)
        cells = [c.strip() for c in m.group(2).split("|")]
        title, est, needs = cells[0], int(cells[-2]), cells[-1]
        needs_list = [] if needs in ("—", "-", "") else [n.strip() for n in needs.split(",")]
        unit = state["units"].setdefault(uid, {"status": "PENDING", "attempts": 0})
        unit.update({"phase": uid[0], "title": title, "est": est, "needs": needs_list})
    save(state)
    return state


def phase_units(state, phase):
    return {k: v for k, v in sorted(state["units"].items()) if v["phase"] == str(phase)}


def speed_ratio(state):
    done = [u for u in state["units"].values() if u["status"] == "DONE" and u.get("minutes")]
    if not done:
        return 1.0
    ratio = sum(u["minutes"] for u in done) / sum(u["est"] for u in done)
    return min(max(ratio, 0.5), 2.0)


def remaining(state, phase):
    pending = [u for u in phase_units(state, phase).values() if u["status"] in ("PENDING", "IN_PROGRESS")]
    return round(sum(u["est"] for u in pending) * speed_ratio(state))


def line(state, uid):
    u = state["units"][uid]
    units = phase_units(state, u["phase"])
    done = sum(1 for x in units.values() if x["status"] == "DONE")
    left = remaining(state, u["phase"])
    took = u.get("minutes", "?")
    tail = "phase complete" if left == 0 else f"~{left} min of processing left in this phase"
    return f"[Phase {u['phase']}] {uid} {u['status'].lower()} in {took} min · {done}/{len(units)} units · {tail}"


def report(state):
    out = ["# Build progress", "",
           f"Last updated: {time.strftime('%Y-%m-%d %H:%M %Z')}. This file is rewritten and pushed after every work unit.", ""]
    total_left = 0
    for ph in "12345":
        units = phase_units(state, ph)
        done = sum(1 for v in units.values() if v["status"] == "DONE")
        left = remaining(state, ph)
        total_left += left
        out.append(f"## Phase {ph}: {done}/{len(units)} units done, ~{left} min of processing left")
        out.append("")
        out.append("| Unit | Title | Status | Minutes |")
        out.append("| --- | --- | --- | --- |")
        for k, v in units.items():
            note = f" ({v['reason']})" if v.get("reason") else ""
            out.append(f"| {k} | {v['title']} | {v['status']}{note} | {v.get('minutes', '')} |")
        out.append("")
    out.insert(4, f"**Overall: ~{total_left} min of Claude Code processing left.** Status values: DONE, IN_PROGRESS (running, or interrupted and will be resumed), PENDING, BLOCKED, SKIPPED.")
    out.insert(5, "")
    (ROOT / "progress" / "PROGRESS.md").write_text("\n".join(out) + "\n")


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    state = init() if cmd == "init" else load()
    if cmd == "init":
        print(f"{len(state['units'])} units loaded")
        return
    if not state["units"]:
        state = init()
    if cmd == "start":
        u = state["units"][args[0]]
        u["status"], u["start"] = "IN_PROGRESS", time.time()
    elif cmd == "done":
        u = state["units"][args[0]]
        u["status"] = "DONE"
        u["minutes"] = round((time.time() - u.get("start", time.time())) / 60, 1)
        save(state)
        print(line(state, args[0]))
        return
    elif cmd == "blocked":
        u = state["units"][args[0]]
        u["status"], u["reason"] = "BLOCKED", " ".join(args[1:])
        save(state)
        print(line(state, args[0]))
        return
    elif cmd == "attempt":
        u = state["units"][args[0]]
        u["attempts"] = u.get("attempts", 0) + 1
        if u["attempts"] >= MAX_ATTEMPTS:
            u["status"], u["reason"] = "BLOCKED", "did not finish after 3 runs"
    elif cmd == "report":
        report(state)
        return
    elif cmd == "line":
        print(line(state, args[0]))
        return
    elif cmd == "get":
        print(state["units"][args[0]]["status"])
        return
    elif cmd == "next":
        units = phase_units(state, args[0])
        status = {k: v["status"] for k, v in state["units"].items()}
        open_units = [k for k, v in units.items() if v["status"] in ("PENDING", "IN_PROGRESS")]
        if not open_units:
            print("NONE")
            return
        for k in open_units:
            if all(status.get(n) == "DONE" for n in units[k]["needs"]):
                print(k)
                return
        print("STUCK")
        return
    elif cmd == "skip":
        changed = True
        while changed:
            changed = False
            status = {k: v["status"] for k, v in state["units"].items()}
            for k, v in phase_units(state, args[0]).items():
                if v["status"] == "PENDING" and any(status.get(n) in ("BLOCKED", "SKIPPED") for n in v["needs"]):
                    v["status"], v["reason"] = "SKIPPED", "needs a blocked unit"
                    changed = True
        # units in later phases that depend on these are skipped when their phase runs
    elif cmd == "summary":
        for ph in "12345":
            units = phase_units(state, ph)
            done = sum(1 for v in units.values() if v["status"] == "DONE")
            print(f"Phase {ph}: {done}/{len(units)} done")
        problems = {k: v for k, v in sorted(state["units"].items()) if v["status"] in ("BLOCKED", "SKIPPED")}
        if problems:
            print("Needs attention (details in docs/BLOCKERS.md):")
            for k, v in problems.items():
                print(f"  {k} {v['status']} {v['title']} - {v.get('reason', '')}")
        else:
            print("No blocked or skipped units.")
        return
    elif cmd == "retry":
        for v in state["units"].values():
            if v["status"] in ("BLOCKED", "SKIPPED"):
                v["status"], v["attempts"] = "PENDING", 0
                v.pop("reason", None)
    elif cmd == "status":
        units = phase_units(state, args[0])
        for k, v in units.items():
            extra = f" ({v.get('minutes')} min)" if v.get("minutes") else ""
            reason = f" - {v['reason']}" if v.get("reason") else ""
            print(f"{k} {v['status']:<11} {v['title']}{extra}{reason}")
        print(f"Phase {args[0]}: ~{remaining(state, args[0])} min of processing left")
        return
    save(state)


if __name__ == "__main__":
    main()
