# Nuskha DWBI project: rules for Claude Code

You are building the CT-472 Data Warehouse and BI semester project end to end, with no help from the user.

- Design: `docs/blueprint.md` (scenario, source schemas, generator spec, star schemas, warehouse DDL, ETL rules, AI design, rubric map).
- Work plan: `docs/PLAN.md` (5 phases, 49 units, each with an acceptance check).
- Progress: `progress/state.json`, managed only through `scripts/progress.py`.
- Handover notes between units: `progress/notes.md`.

## Autonomy protocol

1. Never ask the user a question and never wait for input. When something is undecided, follow `docs/blueprint.md`. If it says nothing, choose the simplest option that meets the requirement and record it in `docs/DECISIONS.md` (unit, decision, reason).
2. Work through `docs/PLAN.md` in order. Start a unit with `python scripts/progress.py start <unit>`. When its acceptance check passes, run `python scripts/progress.py done <unit>` and copy the progress line it prints into your output. Then start the next pending unit of the same phase straight away, until the phase is complete.
3. If an acceptance check fails, fix it and check again, up to 3 attempts. Then run `python scripts/progress.py blocked <unit> "<reason>"`, write in `docs/BLOCKERS.md` what failed, what you tried and exactly what a person must do, and continue with the next unit that does not need the blocked one. Never stop the run to wait for a person: every human step is done after the automated build (see `START_HERE.md`), and units that need a blocked unit are skipped automatically.
   Never build anything that requires a person mid-run (an account, a sign-in, a GUI app). If a requirement seems to need one, prepare everything up to that point and add the remaining action to the end-of-run checklist in `START_HERE.md`, part 4.
4. After every DONE unit, append 3–6 lines to `progress/notes.md` (what you built, file paths, anything the next unit must know), then commit: `git add -A && git commit -m "<unit>: <title>"`. Push if a remote is configured. If git is not installed yet, skip the commit and note it in `progress/notes.md`; commit everything once git exists.
5. Never edit raw snapshots after writing them. Never edit `docs/blueprint.md`; record deviations in `docs/DECISIONS.md`.
6. Before starting a unit, read `progress/notes.md` and the files the unit's "Needs" units produced.
7. A unit whose status is already IN_PROGRESS when you are asked to do it was interrupted (laptop switched off, sleep, terminal closed). Inspect what it already created, keep what passes its checks, finish or redo the rest, then run its acceptance check as usual. Never assume an interrupted unit's files are complete.
8. At the start of every unit, run `bash scripts/setup_env.sh` (once unit 1.01 has created it). It must be safe to repeat: it starts MySQL and PostgreSQL if they are stopped, which happens whenever the laptop restarts. Then check that the databases still hold what the DONE units produced. If they do not (for example, after a reinstall), rebuild that state first by rerunning the existing pipeline scripts in order up to the last DONE unit; every script is idempotent and seeded, so the result is identical. Log the rebuild in `progress/notes.md`.

## Engineering rules

- Seed 472 wherever randomness is used.
- Money is NUMERIC(14,2) in SQL; in Python, round to 2 decimals before writing. Ratios (ASP, unit cost, margin %) are always recomputed from sums.
- Every pipeline step writes a CSV log under `evidence/<area>/` and, once the warehouse exists, a row to `etl.batch_stage_log`.
- Loads are upserts on natural or business keys; a rerun of unchanged input must change nothing.
- **This machine is native Windows**, used from Git Bash. Use `python` (not `python3`) from the project virtual environment: `.venv/Scripts/python`, `.venv/Scripts/pip`. MySQL and PostgreSQL are already installed by the person as Windows services that start automatically; never try to install or start them. If a database server is not reachable, say so in one line and stop the unit.
- Write code that runs on both Windows and Linux: `pathlib` for every path, no hard-coded `\\` or `/` separators, UTF-8 everywhere, LF line endings (enforced by `.gitattributes`). The Google Colab setup cell in `pipeline.ipynb` stays Linux-only; `scripts/setup_env.sh` has a `local` mode (connect and create missing databases only) and a `colab` mode (apt install). Anything that cannot be tested on Windows (the Colab setup cell) must be kept short and listed in `docs/DECISIONS.md` as tested only in Colab.
- Connections come from `config/.env` (git-ignored): `SALES_URL`, `FINANCE_URL`, `PURCHASING_URL`, `INVENTORY_PATH`, `DW_URL`.
- The build runs on the user's own machine: Ubuntu under WSL (passwordless sudo is configured) or macOS (use Homebrew, no sudo). `scripts/setup_env.sh` must detect which and work on both, and also on Google Colab (Ubuntu). It is the only place engines are installed and started, and `pipeline.ipynb` calls it.
- Stay inside the project folder. Never touch files outside it, never read or change anything under `/mnt/c`, `~/.ssh` or other personal folders, and never change system settings beyond installing and starting the database engines.
- All data is synthetic: say so in table comments, CSV headers or file notes, and the README. No patient data, no real brand names, no real companies.
- Keep code plain and commented; a student has to explain every file in a viva.

## Progress line format

`[Phase 2] 2.04 done in 13 min · 4/9 units · ~58 min of processing left in this phase`

`scripts/progress.py done` prints this line; the remaining time is the estimate of the pending units, scaled by how long the finished units actually took.
