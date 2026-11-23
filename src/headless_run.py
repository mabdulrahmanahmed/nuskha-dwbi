"""Unit 5.02: execute pipeline.ipynb headless, twice, each time from an empty warehouse. Synthetic data.

Each run sets NUSKHA_MODE=FULL_REBUILD (the notebook then drops the warehouse schemas and
regenerates every source from seed 472) and NUSKHA_TOTALS_FILE (the last cell writes the warehouse
totals there). Afterwards the two totals files are compared measure by measure.

  python -m src.headless_run            # two runs + comparison
  python -m src.headless_run --runs 1   # one run only

Writes evidence/05_validation/headless_run/:
  run_<n>_totals.csv, run_<n>_seconds.txt, totals_comparison.csv
and evidence/05_validation/headless_run/pipeline_executed.ipynb (the executed copy of run 2).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

import pandas as pd

from src.common import EVIDENCE_DIR, ROOT

OUT = EVIDENCE_DIR / "05_validation" / "headless_run"


def run_once(n: int) -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    totals = OUT / f"run_{n}_totals.csv"
    executed = OUT / f"pipeline_run_{n}.ipynb"
    env = dict(os.environ, NUSKHA_MODE="FULL_REBUILD", NUSKHA_TOTALS_FILE=str(totals))
    t0 = time.time()
    cmd = [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
           "--ExecutePreprocessor.timeout=3600", "--output", str(executed), str(ROOT / "pipeline.ipynb")]
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    secs = round(time.time() - t0, 1)
    (OUT / f"run_{n}_seconds.txt").write_text(f"{secs}\n", encoding="utf-8")
    print(f"run {n} finished in {secs} s")
    return pd.read_csv(totals, dtype=str)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    a = ap.parse_args()
    results = [run_once(n) for n in range(1, a.runs + 1)]
    if a.runs >= 2:
        cmp = results[0].merge(results[1], on="measure", suffixes=("_run1", "_run2"))
        cmp["identical"] = (cmp["value_run1"] == cmp["value_run2"]).map({True: "PASS", False: "FAIL"})
        cmp.to_csv(OUT / "totals_comparison.csv", index=False, lineterminator="\n")
        print(cmp.to_string(index=False))
        # keep the last executed notebook under a stable name; drop the run-1 copy (same content, other timings)
        shutil.copy(OUT / f"pipeline_run_{a.runs}.ipynb", OUT / "pipeline_executed.ipynb")
        (OUT / "pipeline_run_1.ipynb").unlink(missing_ok=True)
        (OUT / f"pipeline_run_{a.runs}.ipynb").unlink(missing_ok=True)
        if (cmp["identical"] != "PASS").any():
            sys.exit("totals differ between runs")


if __name__ == "__main__":
    main()
