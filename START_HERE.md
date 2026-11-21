# Start here

Synthetic data (seed 472). This page is the way in for the group: what exists, where to look, and the few things only a person can do.

## Part 1. What has been built

The full CT-472 project, end to end and automated:
- **Sources:** four departmental source systems on three engines.
- **ETL and warehouse:** ETL with rejects and reconciliation feeding a PostgreSQL warehouse with two stars, two batches, a rerun test, a controlled failure and SCD Type 1.
- **Metadata and validation:** a metadata repository with lineage, six traces and an 11-check validation suite.
- **Analytics:** 12 analytic queries and 6 saved views.
- **AI:** a forecast and anomaly detection, both evaluated against baselines.
- **Power BI:** a 3-page Power BI project.
- **Documents:** the technical report, recommendations, a demo run-sheet and four viva guides.

`pipeline.ipynb` ran headless twice from an empty warehouse, and the totals were identical (`evidence/05_validation/headless_run/totals_comparison.csv`).

## Part 2. Where to look

| You want | Open |
| --- | --- |
| The report (8–12 pages + appendices) | `report/report.pdf` (Word: `report/report.docx`, source: `report/report.md`) |
| Which file proves each rubric item | `evidence/INDEX.md` |
| Requirement-by-requirement audit | `docs/AUDIT.md` |
| How to run everything, expected numbers | `README.md` |
| The 12-minute demo | `docs/demo.md` |
| Your viva preparation | `docs/viva/member1.md` … `member4.md` |
| The three recommendations | `docs/recommendations.md` |
| Why something differs from the blueprint | `docs/DECISIONS.md` |

## Part 3. Rerun everything on this laptop

```bash
bash scripts/setup_env.sh                          # must print OK five times
.venv/Scripts/python -m src.pipeline --mode FULL_REBUILD
.venv/Scripts/python -m src.report_build --check   # rebuild report.docx / report.pdf
```

## Part 4. Human checklist (only a person can do these)

1. **Power BI.** Open `powerbi/nuskha.pbip` in Power BI Desktop.
   - If it opens: check the three pages and the three totals in `powerbi/reconciliation.csv` (FY2026 net sales 6,230,294.70; Gulshan-e-Iqbal 2025 745,398.10; Oct 2026 purchases 599,167.14), then **File → Save as** `powerbi/nuskha.pbix` and **Export → PDF** to `powerbi/nuskha.pdf`.
   - If it does not open, or a visual errors: build the report from `powerbi/BUILD_GUIDE.md` (about 45 minutes) and save it to the same file names.
   - On visual 8 (top 10 products), add the Top N = 10 filter by hand (BUILD_GUIDE).
2. **Google Colab run** (about 10 minutes; the setup cell apt-installs MySQL and PostgreSQL).
   - In Colab: **File → Upload notebook** → `pipeline.ipynb`. Then, in the file panel (folder icon), upload `dist/nuskha-dwbi-colab.zip`, a clean copy of the repo without the venv or secrets.
   - Insert a new cell at the very top of the notebook containing:
     ```
     !unzip -oq /content/nuskha-dwbi-colab.zip -d /content/nuskha-dwbi
     %cd /content/nuskha-dwbi
     import os; os.environ['NUSKHA_MODE'] = 'FULL_REBUILD'
     ```
   - Choose **Runtime → Run all**.
   - Check that the last cell's totals equal the table in `README.md` (e.g. FY2026 net sales 6230294.70).
   - Save it with **File → Download → .ipynb** as `evidence/colab_run.ipynb`.
   - If a setup step fails in Colab, note the error. The local headless run (`evidence/05_validation/headless_run/`) already proves the notebook runs end to end.
3. **Contribution statement.** Names (from the title slide) are filled in as a *draft* assignment in section 10 of `report/report.md` and at the top of each `docs/viva/member*.md`. Confirm or swap who owns which criterion, fill in the hours, then run `.venv/Scripts/python -m src.report_build --check` to rebuild the docx and PDF.
4. **Open items with the instructor:**
   - Rebuilding the lab artifacts inside the project.
   - Practical 9/10 task numbers for A1–A12 (provisional in `evidence/06_sql/readings.md`).
   - The evidence folder names required by the brief.
5. **Viva rehearsal.** Each member presents another member's component once, using `docs/viva/`.
6. **Closing step.** When 1–3 are done, run `bash scripts/finalize.sh`. It compares the Colab totals, adds the Power BI PDF to the report, reruns the audit and tags `v1.1`.
