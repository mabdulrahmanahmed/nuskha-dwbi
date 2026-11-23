# Evidence: source systems (C1)

**All data is synthetic**, produced by `src/generate_sources.py` with seed 472. There is no patient data, no real brands and no real companies.

| File | What it shows | Made by |
| --- | --- | --- |
| `erd/<dept>_erd.png`, `erd/<dept>_erd.dot` | One ERD per department, drawn from `sql/01_source_ddl/`. Arrows are declared FKs. Inventory declares none, so its dashed links are only implied by column names. | `python -m src.erd` |
| `erd_summary.csv` | Tables, columns and declared or implied relationships per department | `python -m src.erd` |
| `reference_counts.csv` | Master-data row counts against the blueprint's generator table | `python -m src.generate_sources --part reference` |
| `stage1_row_counts.csv`, `stage2_row_counts.csv` | Rows per source table at each stage | `python -m src.generate_sources --stage N` |
| `stage1_monthly_totals.{csv,png}`, `stage2_monthly_totals.{csv,png}` | Monthly net sales by category: trend, seasons and the planted anomalies | same |
| `planted_patterns.csv` | Planted business patterns (East Analgesics spike, stock-out, keying error, late receipts) | same |
| `stage1_volume_checks.csv` | Unit 1.05 check: volumes, USD share, customer mix, trend | `python -m src.check_generated volumes` |
| `defect_ledger.csv`, `defect_ledger_stage2.csv` | Every planted defect row with its reason code and source key | generator |
| `defect_ledger_summary.csv`, `defect_rate_checks.csv` | Unit 1.06 check: rates within ±10%, and ledger = defective rows found in the data | `python -m src.check_generated defects` |
| `stage2_intended_changes.csv`, `stage2_diff.csv`, `stage2_diff_summary.csv`, `stage2_checks.csv` | Unit 1.07 check: the stage-1 → stage-2 diff touches only the intended rows | `python -m src.check_generated stage2` |

The source snapshots themselves (`data/generated/stage1/`, `stage2/`) are not committed because they are rebuilt identically from the seed.
