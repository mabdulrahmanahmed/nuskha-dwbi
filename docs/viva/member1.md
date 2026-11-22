> All data in this project is synthetic (fictional "Nuskha Pharmacies", one generator, seed 472). No real patients, brands or companies.

# Viva guide: Member 1, Sources and ETL (criterion C1)
Lead for this criterion: **Muhammad Abdulrahman Ahmed (DT-022)** (assigned at random after balancing difficulty and time; all four members built every component together and share the work equally, see report section 10).

You own the generator, the four source systems, extraction, profiling, cleaning (normalization), crosswalks, rejects and reconciliation. In short: everything from "where does the data come from?" up to "here are clean, checked, staged rows ready to load".

## 1. Your component in plain words

**What it does.** Nuskha is a fictional chain of 10 Karachi pharmacies. Its records sit in four departmental systems on three database engines, and they disagree on how a branch, a product or a customer is named. Your part creates those systems, pulls the data out, cleans it, gives every product, branch and customer one identity, throws out bad rows with a reason, and proves that nothing was lost on the way.

**Why.** A warehouse is only as good as what goes into it. If a branch is spelt three ways or a USD purchase is added to PKR sales, every later figure is wrong. Your job is to make the inputs trustworthy and to prove it with numbers, not by eye.

**The steps, in order:**

1. **Generate** (`src/generate_sources.py`, `src/gen/*.py`): one seeded generator (seed 472) writes two full snapshots: stage 1 (up to 31 Aug 2026) and stage 2 (up to 31 Oct 2026). It plants business patterns (seasons, Diabetes Care cost rise, East Analgesics spike, a stock-out, a keying error) and data defects with known keys, all listed in a defect ledger.
2. **Load the sources** (`src/load_sources.py`, DDL in `sql/01_source_ddl/`): Sales (MySQL `sales_db`), Finance (MySQL `finance_db`), Purchasing (PostgreSQL `purchasing_db`), Inventory (SQLite `inventory.db`). Loaded twice and checksummed to prove reproducibility.
3. **Extract** (`src/extract.py`): transaction tables by watermark on `updated_at` (`watermark_from < updated_at <= watermark_to`), master tables in full. Every extract is saved unchanged as text CSV in `evidence/02_etl/raw/batch_<n>/` and never edited. Row counts and amounts are cross-checked against `COUNT/SUM` on the source.
4. **Profile before / normalize / profile after** (`src/profile.py`, `src/normalize.py`): parse dates (MySQL text, PostgreSQL TIMESTAMPTZ, Inventory `DD/MM/YYYY`), trim and standardize text, convert boxes to selling units, round money to NUMERIC(14,2), convert USD to PKR at the Finance rate on or before the GRN date.
5. **Crosswalks** (`src/crosswalk.py`, `config/branch_aliases.csv`, `config/panel_aliases.csv`, `config/product_manual_matches.csv`): `xw_product`, `xw_branch`, `xw_customer`, each row recording its match method (exact, rule, alias list, description, manual).
6. **Pre-join checks, quality, de-duplication** (`src/quality.py`, run by `src/etl_db.py`): keys unique, crosswalks many-to-one, row counts kept across joins; invalid rows go to `etl.rejects` with one reason code; only the same source key extracted twice is removed as a duplicate.
7. **Reconcile** (`src/etl_db.py reconcile`): source rows = loaded + rejected + duplicates, and amounts per month to the paisa.

**Key files to name:** `src/generate_sources.py`, `src/gen/defects.py`, `src/load_sources.py`, `src/extract.py`, `src/normalize.py`, `src/crosswalk.py`, `src/quality.py`, `src/etl_db.py`, `config/transform_rules.csv`; evidence in `evidence/01_sources/` and `evidence/02_etl/`.

## 2. How it connects to the others

- **You receive:** nothing from another member. You are the start of the pipeline. You do use the control tables `etl.batch` and `etl.batch_stage_log` that Member 2's DDL creates (`sql/02_warehouse_ddl/01_schemas_and_control.sql`): the extract reads the last SUCCESS watermark from `etl.batch`.
- **You hand to Member 2 (warehouse):** staged, crosswalked, validated rows from `src.etl_db.run(batch)`. `src/load_db.py` builds the dimensions and facts directly from these. Your crosswalks decide the canonical codes (product `P-0<item_id>`, branch = Inventory `store_code`) and Member 2 turns them into surrogate keys. Your reject counts are the "rejected" column in the balance that Member 2's load must match.
- **You hand to Member 3 (lineage and validation):** the raw snapshots and staging rows are steps 3 and 4 of every trace (e.g. `traces/T1.md` goes fact → lineage → `stg.receipt_line` → raw CSV → MySQL row). Validation checks 5 and 6 (row and amount reconciliation) re-run your balance. Your transform rule ids (R-DATE-01, R-UNIT-01, R-FX-01, ...) fill `meta.transform_rule`.
- **You hand to Member 4 (SQL and BI):** indirectly. Every PKR figure on the dashboard is only right because you converted USD and removed duplicates. The planted patterns you generated are what A3, A12 and the AI find.
- **Batch 2 link:** for batch 2 the extract starts from the batch-1 watermark (2026-08-31 23:59:59), which only exists because Member 2 closed batch 1 as SUCCESS.

## 3. Numbers to know

| # | Figure | Source file |
| --- | --- | --- |
| 1 | 4 departments, 3 engines, 17 source tables; both builds give identical md5 on 17/17 tables | `evidence/01_sources/reproducibility.csv` |
| 2 | Stage 1: 12,767 receipts, 28,099 receipt lines, 1,717 GRNs, 4,683 GRN lines, 1,035 FX days | `evidence/01_sources/stage1_row_counts.csv` |
| 3 | Stage 2: 13,833 receipts, 30,417 receipt lines, 5,002 GRN lines, 151 items (new product added) | `evidence/01_sources/stage2_row_counts.csv` |
| 4 | Batch-1 receipt-line snapshot = 28,238 rows (28,099 extracted + 139 double-exported D01 keys); source amount PKR 15,202,472.15 matched | `evidence/02_etl/extract_log_batch_1.csv` |
| 5 | Batch 1 sales: 28,238 = 27,543 loaded + 556 rejected + 139 duplicates | `evidence/02_etl/reconciliation_batch_1.csv` |
| 6 | Batch 1 purchases: 4,706 = 4,604 + 79 + 23 | `evidence/02_etl/reconciliation_batch_1.csv` |
| 7 | Batch 2: sales 2,428 = 2,369 + 47 + 12; purchases 328 = 321 + 5 + 2 | `evidence/02_etl/reconciliation_batch_2.csv` |
| 8 | 635 batch-1 rejects; all 15 code/table pairs match the ledger key for key (e.g. R01 167 receipt lines, R06 4 GRN lines) | `evidence/02_etl/rejects_vs_ledger.csv` |
| 9 | 278 legitimate repeats kept (not removed as duplicates) | `evidence/02_etl/rejects_vs_ledger.csv` |
| 10 | Products: 105 vendor codes exact + 45 by description + 2 unmatched; till codes 114 exact + 14 rule + 22 description + 3 unmatched | `evidence/02_etl/crosswalk_match_methods.csv` |
| 11 | 687 rows in `etl.rejects` after both batches (635 + 52) | `evidence/05_validation/headless_run/totals_comparison.csv` |

## 4. 15 likely questions with answers

1. **Why generate data instead of using a public dataset?**
   We needed four related departmental systems on three engines with the same products and branches, and we needed defects whose exact keys we know. A public dataset would not give us a known answer to check the ETL against. With the defect ledger (`evidence/01_sources/defect_ledger.csv`) we can say "the ETL rejected exactly the 167 planted R01 lines", not "it looks about right".

2. **How do you know the generator is reproducible?**
   It uses `numpy.random.default_rng([472, part])`, one part number per generator part, so changing a later part never shifts the random numbers of an earlier one. We loaded the sources twice and compared md5 checksums: 17 of 17 tables are identical (`reproducibility.csv`).

3. **What is a watermark and why use it?**
   It is the `updated_at` cut-off of the last successful batch, stored in `etl.batch`. Batch 2 extracts only rows with `updated_at` after 2026-08-31 23:59:59 and up to 2026-10-31 23:59:59. That way we only move new or changed rows, and an edited receipt is picked up because any edit re-saves the header and all its lines with a new `updated_at`.

4. **Why are master tables extracted in full, not by watermark?**
   They are small (150 items, 10 stores, 25 suppliers, about 1,000 FX days) and some, like Inventory, have no reliable change timestamp. A full extract is cheap and lets us compare with the previous snapshot.

5. **Why keep raw snapshots as text, unchanged?**
   They are the proof of what the source held at extraction time. Staging is rebuilt from them each step, so every step is deterministic and rerunnable, and traces can show the raw CSV row next to the source row (step 4 of `traces/T1.md`).

6. **What is the difference between a duplicate and a legitimate repeat?**
   A duplicate (D01) is the same source key, for example `receipt_no|line_no`, extracted twice because the till export job sends it twice. A legitimate repeat is the same customer buying the same product on the same day under a new line key: that is a real sale and stays. We removed 139 + 23 duplicates in batch 1 and kept all 278 legitimate repeats.

7. **A row has two problems, say a bad date and an unknown product. How many rejects?**
   One. `src/quality.py` applies reason codes in a fixed precedence (`SALES_ORDER`: R07 orphan, R03 date, R05 branch, R01 product, R02 quantity, R04 amount; Purchasing adds R06). The first one that applies wins, so counts per code add up exactly to the total rejected and can be compared one-to-one with the ledger.

8. **What happens to a USD purchase line with no exchange rate?**
   It is rejected with R06_NO_FX_RATE. Rule R-FX-01 uses the Finance USD/PKR rate on or before the GRN date; there were 4 planted lines on two GRNs received before the first rate. Guessing a rate would put a wrong PKR cost into the warehouse silently.

9. **How does the product crosswalk work?**
   Inventory `item_id` is the master, canonical code `P-0<item_id>`. Till codes and vendor codes are matched exactly first, then by rule (trim, case), then by description, then by a manual list in `config/product_manual_matches.csv`. Each row records its method. The only unmatched codes are the planted R01 codes (2 vendor, 3 till), so their lines go to rejects.

10. **How do you prove a join did not multiply rows?**
    Before joining, `prejoin_checks.csv` confirms every key is unique and every crosswalk is many-to-one (each source key maps once). Then the row count is checked before and after each join, e.g. `receipt_line -> receipt` keeps 28,099 rows.

11. **What does reconciliation prove, and to what precision?**
    For each table and batch: source rows = loaded + rejected + duplicates removed, which balanced in both batches. Amounts are compared month by month to the paisa in `reconciliation_amounts_by_month_batch_1.csv` with a `difference` column of 0.0. So no row disappeared and no amount changed without being accounted for.

12. **Why are R07 orphan lines only in Sales?**
    PostgreSQL enforces foreign keys, so Purchasing would refuse a line without its header. MySQL Sales is loaded with `SET FOREIGN_KEY_CHECKS=0` to imitate a legacy till sync that lost headers (`docs/DECISIONS.md`, unit 1.06).

13. **What about panel customers whose name you cannot match (U01)?**
    They are not rejected, because the sale itself is valid. They load against the Unknown customer (key -1) with a flag. In batch 1 that was 0.073% of rows (`fact_checks_batch_1.csv`); batch 2 corrected the panel names, so only 1 row (0.003%) remains on Unknown at the end (`validation_results.csv`).

14. **Why apply unit and FX conversion after joining the GRN line to its header and PO?**
    The conversion needs the GRN date and currency from the header, and a September GRN can belong to an August purchase order extracted in batch 1. So header tables in staging are cumulative across batches, and `normalize.convert_purchase_lines` runs after the joins (`docs/DECISIONS.md`, pre-DB).

15. **What if a new till code appears tomorrow?**
    If no rule or description matches, its lines are rejected as R01 and show up in `etl.rejects` and the crosswalk checks. Someone adds a manual match to `config/product_manual_matches.csv` and reruns; because loads are upserts, the rerun only adds the newly valid rows. This upkeep is listed as a problem area in the architecture analysis (81 product codes matched by rule or description).

## 5. Show me

1. **Batch 1 ETL live (after step 1 of `docs/demo.md` has rebuilt the sources):**
   `.venv/Scripts/python -m src.pipeline --from extract_batch_1 --to etl_reconcile_1`
   Then open `evidence/02_etl/reconciliation_batch_1.csv` and `evidence/02_etl/rejects_vs_ledger.csv`.
2. **Rejects by reason in psql** (`psql postgresql://nuskha:nuskha@localhost:5432/nuskha_dw`):
   ```sql
   SELECT batch_id, reason_code, count(*) FROM etl.rejects GROUP BY 1, 2 ORDER BY 1, 3 DESC;
   SELECT source_object, match_method, count(*) FROM stg.xw_product GROUP BY 1, 2 ORDER BY 1, 2;
   SELECT batch_id, watermark_from, watermark_to, status FROM etl.batch ORDER BY 1;
   ```
3. **Before/after cleaning evidence:** `evidence/02_etl/profile_before_after.csv` (e.g. `sales_db.receipt` mixed-format columns 1 before, 0 after) and `evidence/02_etl/crosswalk_match_methods.csv`.
4. **The defect ledger vs the ETL:** open `evidence/01_sources/defect_ledger_summary.csv` beside `rejects_vs_ledger.csv` and point out that planted = found with identical key sets for every code.

## Key terms to say correctly

- **Watermark:** the `updated_at` cut-off of the last SUCCESS batch in `etl.batch`; batch 1 ended at 2026-08-31 23:59:59, batch 2 at 2026-10-31 23:59:59.
- **Raw snapshot:** the unchanged text extract of one table for one batch (`evidence/02_etl/raw/batch_<n>/<db>.<table>.csv`).
- **Staging (`stg`):** typed, normalized copies rebuilt from the raw snapshots; header tables are cumulative across batches.
- **Crosswalk:** a mapping table from every source code to one canonical code, with the match method recorded.
- **Defect ledger:** the generator's list of every planted defect and its key; the answer sheet the ETL is checked against.
- **D01 vs LEGIT_REPEAT:** same source key twice (remove) vs a new line key for the same purchase pattern (keep).
- **Reason precedence:** R07, R03, R05, R01, R02, R04 (then R06 for purchases); one code per rejected row.
