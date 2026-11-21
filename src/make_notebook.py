"""Write pipeline.ipynb from the step list in src/pipeline.py (unit 5.01). Synthetic data.

Every code cell calls repo code (src.pipeline); no pipeline logic is copied into the notebook.
Run it in Google Colab (the setup cell installs MySQL and PostgreSQL there) or locally.

  python -m src.make_notebook
"""
from __future__ import annotations

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from src.common import ROOT
from src.pipeline import STEPS

GROUPS = [  # (first step of a group, heading, plain explanation)
    ("generate_stage_1", "1. Source systems",
     "Four synthetic department databases are generated from seed 472 (FULL_REBUILD only) and loaded into "
     "MySQL (Sales, Finance), PostgreSQL (Purchasing) and SQLite (Inventory). The load is done twice and the "
     "per-table checksums are compared."),
    ("extract_batch_1", "2. Batch 1: extract, clean, match",
     "Transaction tables are extracted by `updated_at` watermark into an untouched raw snapshot. Staging "
     "normalizes dates, units, money and currency; crosswalks give one product, branch and customer identity; "
     "bad rows go to `etl.rejects` with a reason code; rows and amounts are reconciled."),
    ("load_batch_1", "3. Batch 1: warehouse load",
     "Dimensions, then facts, as upserts on natural keys in one transaction per fact table, with lineage."),
    ("rerun_test", "4. Batches, SCD Type 1 and failure handling",
     "An unchanged rerun changes nothing; batch 2 brings late receipts, corrections, cancellations and "
     "deletions; the cough-syrup category fix is an SCD Type 1 overwrite; a forced failure rolls back."),
    ("metadata", "5. Metadata, lineage and traces",
     "The metadata repository, ERDs reverse-engineered from each engine's catalog, and six traces from a "
     "warehouse figure back to a source row."),
    ("views", "6. Analytics and AI", "Six saved views, twelve analytic queries, the sales forecast and anomaly "
     "detection (run twice to show the retry adds no rows)."),
    ("validation", "7. Validation and Power BI package",
     "The 11-check validation suite, then the CSV exports, semantic model and report for Power BI."),
]


def build() -> nbformat.NotebookNode:
    cells = [
        new_markdown_cell(
            "# Nuskha Pharmacies data warehouse: full pipeline\n\n"
            "CT-472 Data Warehousing and BI project. **All data is synthetic (seed 472); no real patients, brands "
            "or companies.**\n\nEach cell below calls code in `src/`; the notebook holds no logic of its own. "
            "Steps print `[OK]`, `[SKIP]` or `[FAILED]` with the last lines of their output."),
        new_markdown_cell("## Setup\nIn Google Colab this installs and starts MySQL and PostgreSQL and creates the "
                          "users (`scripts/setup_env.sh colab`). On a local machine the database services already "
                          "run, so it only checks the five connections."),
        new_code_cell(
            "import os, subprocess, sys\n"
            "IN_COLAB = 'COLAB_RELEASE_TAG' in os.environ or 'COLAB_GPU' in os.environ\n"
            "if IN_COLAB:\n"
            "    if not os.path.exists('src'):\n"
            "        raise SystemExit('Upload or clone the project folder and %cd into it first.')\n"
            "    subprocess.run(['bash', 'scripts/setup_env.sh', 'colab'], check=True)\n"
            "subprocess.run([sys.executable, 'scripts/check_env.py', '--create'], check=True)"),
        new_markdown_cell("## Mode\n`FULL_REBUILD` empties the warehouse and runs everything from the sources; "
                          "`CONTINUE` keeps what exists and only adds what is missing (safe to repeat). The headless "
                          "test run sets it with the environment variable `NUSKHA_MODE`."),
        new_code_cell(
            "import os\n"
            "MODE = os.environ.get('NUSKHA_MODE', 'CONTINUE')   # or 'FULL_REBUILD'\n"
            "from src import pipeline\n"
            "if MODE == 'FULL_REBUILD':\n"
            "    pipeline.reset()\n"
            "print('mode:', MODE)"),
    ]
    starts = {g[0]: g for g in GROUPS}
    for name, what, args, _ in STEPS:
        if name in starts:
            _, head, text = starts[name]
            cells.append(new_markdown_cell(f"## {head}\n{text}"))
        cells.append(new_markdown_cell(f"**{what}** — `python -m {' '.join(args)}`"))
        cells.append(new_code_cell(f"pipeline.run_step({name!r}, MODE)"))
    cells += [
        new_markdown_cell("## Final warehouse totals\nThese must be identical between runs and between this "
                          "machine and Colab."),
        new_code_cell(
            "t = pipeline.totals()\n"
            "out = os.environ.get('NUSKHA_TOTALS_FILE')\n"
            "if out:\n"
            "    t.to_csv(out, index=False, lineterminator='\\n')\n"
            "t"),
    ]
    nb = new_notebook(cells=cells, metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}})
    return nb


if __name__ == "__main__":
    nb = build()
    nbformat.validate(nb)
    path = ROOT / "pipeline.ipynb"
    nbformat.write(nb, path)
    code = sum(c.cell_type == "code" for c in nb.cells)
    print(f"{path.name}: {len(nb.cells)} cells ({code} code), nbformat valid")
