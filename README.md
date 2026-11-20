# Nuskha Pharmacies: Data Warehouse and BI project (CT-472)

> **All data in this repository is synthetic.** It is produced by one seeded generator
> (seed 472). There is no patient data, no real brand and no real company anywhere.

Nuskha Pharmacies is a fictional 10-branch pharmacy chain in Karachi. Four departmental
source systems (Sales and Finance on MySQL, Purchasing on PostgreSQL, Inventory on SQLite)
feed a PostgreSQL warehouse with two stars (sales and purchases), which in turn feeds
saved SQL views, a Power BI report and two AI tasks (a monthly forecast and anomaly detection).

- Design: [`docs/blueprint.md`](docs/blueprint.md)
- Work plan and acceptance checks: [`docs/PLAN.md`](docs/PLAN.md)
- Decisions and deviations: [`docs/DECISIONS.md`](docs/DECISIONS.md)

## Folder layout

| Folder | Holds |
| --- | --- |
| `src/` | Python pipeline code (`common.py` is shared by every step) |
| `src/gen/` | Parts of the synthetic data generator |
| `sql/01_source_ddl/` | DDL of the four source systems |
| `sql/02_warehouse_ddl/` | Warehouse DDL (`dw`, `stg`, `etl`, `meta`, `ai` schemas) |
| `sql/03_views/`, `sql/04_queries/`, `sql/05_traces/` | Saved views, analytic queries A1–A12, lineage traces |
| `config/` | `.env` (git-ignored, connection strings) and mapping/alias CSVs |
| `data/generated/` | Generator output: CSV per source table and the Inventory SQLite file |
| `evidence/` | Logs and outputs of every step, one folder per area |
| `powerbi/` | CSV exports, Power BI project and build guide |
| `report/` | Technical report |

## Run order

The run order, with expected row counts and totals after each step, is completed in unit 5.06.
