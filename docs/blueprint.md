# DWBI Project Blueprint (CT-472)

Nov 17, 2026 · @Abdullah

Step-by-step implementation, with a check for every step: Build plan

## Status and scope

This blueprint replaces the lab foundation (Practicals 1–10) the group has not built, and fixes every design decision for the project on one scenario: **Nuskha Pharmacies**, a fictional 10-branch pharmacy chain in Karachi. It is the single reference for the build, the slides and the report.

- **Data:** all synthetic, produced by one seeded generator and labelled synthetic in every table, file and chart.
- **History:** 36 completed months, Nov 2023 – Oct 2026. Batch 1 = Nov 2023 – Aug 2026; batch 2 = Sep – Oct 2026 plus corrections and late arrivals.
- **Status:** design complete; nothing built yet.
- **No patient data anywhere.** Products use generic names and categories only; customers are walk-ins, loyalty members (by number) and companies on a credit panel.

**Open items to confirm with the instructor:**

1. Is rebuilding the lab artifacts inside the project acceptable, given the brief says to continue the practicals?
2. Task numbers in Practicals 9 and 10 for the 12 queries (needs the lab manual).
3. The evidence folder list in the project brief (the layout in the last section is a placeholder).
4. The final submission date (the timeline is in relative weeks until then).

## Scenario and planning matrix

Nuskha sells about 150 medicines and health products from 10 branches, buys from local distributors, and imports a few product lines in US dollars. Four of its ten departments are implemented as source systems; six are planned so the warehouse can grow without redesign.

- **Regions and branches:** North (North Nazimabad, Gulberg, Nazimabad, Orangi), East (Gulshan-e-Iqbal, Gulistan-e-Jauhar, Malir), South (Clifton, Saddar, PECHS). Suppliers deliver to each branch directly.
- **Categories (8):** Analgesics, Antibiotics, Cardiovascular, Diabetes Care, Gastro, Cough and Cold, Vitamins and Supplements, Personal Care.
- **Customers:** walk-ins (no identity), loyalty members (card number at the till), panel companies (credit accounts in Finance, billed monthly).
- **Units:** sold by strip, bottle or piece; bought by box; counted by tablet. Canonical unit = the selling unit.
- **Fiscal year:** July–June, alongside the calendar year.

| # | Department | Owns these records | Engine | Status | Feeds |
| --- | --- | --- | --- | --- | --- |
| 1 | Sales (till / POS) | Receipts, receipt lines, loyalty members, typed panel names | MySQL 8 (`sales_db`) | Implemented | fact\_sales, dim\_customer, dim\_branch |
| 2 | Purchasing | Suppliers, purchase orders, goods receipts (GRN), USD invoices | PostgreSQL 14 (`purchasing_db`) | Implemented | fact\_purchase, dim\_supplier, dim\_branch |
| 3 | Inventory | Item master, categories, pack sizes, standard cost, branch codes | SQLite 3 (`inventory.db`) | Implemented | dim\_product, dim\_branch, cost measure |
| 4 | Finance | Panel company accounts, credit terms, daily USD/PKR rates | MySQL 8 (`finance_db`, separate) | Implemented | dim\_customer, FX conversion |
| 5 | Pharmacy Operations | Batch numbers, expiry write-offs, recalls | — | Planned | Future write-off star |
| 6 | Marketing and Loyalty | Promotions, loyalty points | — | Planned | Future promotion dimension |
| 7 | Home Delivery | Delivery orders, riders, times | — | Planned | Future delivery star |
| 8 | Customer Care | Returns, complaints | — | Planned | Future returns star |
| 9 | Human Resources | Pharmacists, staff, shifts | — | Planned | Future staff dimension |
| 10 | IT | Users, access logs | — | Planned | Metadata only |

Four departments on three engines: Sales and Finance share the MySQL engine as separate databases with different identifiers.

## Source systems: ERDs and DDL (lab prerequisite)

These four schemas replace the departmental ERDs and DDL from the labs. Each department identifies products, customers and branches its own way, on purpose, so the ETL has real work to do.

|  | Product key | Branch key | Customer key | Units / money / dates |
| --- | --- | --- | --- | --- |
| Sales (MySQL) | `item_code` 'PCM-500-STR' | free text 'Gulshan', 'GULSHAN-E-IQBAL ' | loyalty `card_no`, typed panel name | selling units, PKR, DATETIME |
| Purchasing (PostgreSQL) | `vendor_item_code` 'DST-1187' | `branch_id` 4 | — | boxes, PKR or USD, TIMESTAMPTZ |
| Inventory (SQLite) | `item_id` 312 (+ partial `pos_code`, `vendor_code`) | `store_code` 'BR-GUL' | — | tablets, cost as REAL, dates as 'DD/MM/YYYY' text, no FKs |
| Finance (MySQL) | — | region name | `account_no` 40021 | PKR, DATE |

**Sales — MySQL `sales_db`**

```sql
CREATE TABLE loyalty_member (
  card_no      VARCHAR(12) PRIMARY KEY,
  member_name  VARCHAR(80),
  joined_on    DATE
);
CREATE TABLE pos_item (
  item_code    VARCHAR(20) PRIMARY KEY,      -- 'PCM-500-STR'
  item_desc    VARCHAR(100),
  sell_unit    VARCHAR(10)                   -- STRIP | BOTTLE | PIECE
);
CREATE TABLE receipt (
  receipt_no         VARCHAR(16) PRIMARY KEY, -- 'GUL-2026-000123'
  branch_name        VARCHAR(60) NOT NULL,    -- typed, inconsistent
  receipt_ts         DATETIME NOT NULL,
  customer_type      ENUM('WALKIN','LOYALTY','PANEL') NOT NULL,
  card_no            VARCHAR(12) NULL REFERENCES loyalty_member(card_no),
  panel_company_text VARCHAR(80) NULL,        -- typed by cashier
  status             ENUM('POSTED','VOIDED') NOT NULL DEFAULT 'POSTED',
  updated_at         DATETIME NOT NULL
);
CREATE TABLE receipt_line (
  receipt_no      VARCHAR(16) NOT NULL REFERENCES receipt(receipt_no),
  line_no         SMALLINT NOT NULL,
  item_code       VARCHAR(20) NOT NULL REFERENCES pos_item(item_code),
  qty             DECIMAL(8,2) NOT NULL,       -- selling units
  unit_price_pkr  DECIMAL(10,2) NOT NULL,
  discount_pkr    DECIMAL(10,2) NULL,
  updated_at      DATETIME NOT NULL,
  PRIMARY KEY (receipt_no, line_no)
);
```

**Purchasing — PostgreSQL `purchasing_db`**

```sql
CREATE TABLE supplier (
  supplier_id    SERIAL PRIMARY KEY,
  supplier_name  TEXT NOT NULL,
  country        TEXT NOT NULL,
  is_import      BOOLEAN NOT NULL
);
CREATE TABLE branch (
  branch_id      SMALLINT PRIMARY KEY,
  branch_label   TEXT NOT NULL                -- 'Gulshan-e-Iqbal Br.'
);
CREATE TABLE vendor_item (
  vendor_item_code TEXT PRIMARY KEY,          -- 'DST-1187'
  supplier_id      INT NOT NULL REFERENCES supplier,
  description      TEXT,
  strips_per_box   INT NOT NULL
);
CREATE TABLE purchase_order (
  po_no        TEXT PRIMARY KEY,
  supplier_id  INT NOT NULL REFERENCES supplier,
  branch_id    SMALLINT NOT NULL REFERENCES branch,
  ordered_at   TIMESTAMPTZ NOT NULL,
  currency     CHAR(3) NOT NULL CHECK (currency IN ('PKR','USD')),
  updated_at   TIMESTAMPTZ NOT NULL
);
CREATE TABLE goods_receipt (
  grn_no       TEXT PRIMARY KEY,
  po_no        TEXT NOT NULL REFERENCES purchase_order,
  received_at  TIMESTAMPTZ NOT NULL,
  status       TEXT NOT NULL DEFAULT 'POSTED',  -- POSTED | CANCELLED
  updated_at   TIMESTAMPTZ NOT NULL
);
CREATE TABLE grn_line (
  grn_no            TEXT NOT NULL REFERENCES goods_receipt,
  line_no           SMALLINT NOT NULL,
  vendor_item_code  TEXT NOT NULL REFERENCES vendor_item,
  boxes_received    NUMERIC(8,2) NOT NULL,
  cost_per_box      NUMERIC(12,2) NOT NULL,   -- in PO currency
  updated_at        TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (grn_no, line_no)
);
```

**Inventory — SQLite `inventory.db`** (legacy app: no declared foreign keys, text dates, float cost)

```sql
CREATE TABLE item (
  item_id             INTEGER PRIMARY KEY,   -- 312
  generic_name        TEXT,                  -- 'Paracetamol'
  strength            TEXT,                  -- '500 mg'
  category            TEXT,                  -- ' analgesics ', 'ANALGESICS'
  tablets_per_strip   INTEGER,
  std_cost_per_strip  REAL,
  pos_code            TEXT,                  -- partly filled
  vendor_code         TEXT,                  -- partly filled
  last_updated        TEXT                   -- 'DD/MM/YYYY'
);
CREATE TABLE store (
  store_code  TEXT PRIMARY KEY,              -- 'BR-GUL'
  store_name  TEXT,
  area        TEXT,
  region      TEXT                           -- North | East | South
);
CREATE TABLE stock_count (
  store_code       TEXT,
  item_id          INTEGER,
  count_date       TEXT,
  tablets_on_hand  INTEGER
);
```

Inventory also keeps standard cost history, so margins use the cost that applied on the day of each sale:

```sql
CREATE TABLE item_cost_history (
  item_id             INTEGER,               -- no declared FK
  effective_from      TEXT,                  -- 'DD/MM/YYYY'
  std_cost_per_strip  REAL
);
```

**Finance — MySQL `finance_db`**

```sql
CREATE TABLE panel_account (
  account_no        INT PRIMARY KEY,         -- 40021
  company_name      VARCHAR(100) NOT NULL,   -- 'Indus Textiles Ltd'
  credit_limit_pkr  DECIMAL(12,2),
  terms_days        SMALLINT,
  updated_at        DATETIME NOT NULL
);
CREATE TABLE fx_rate (
  rate_date  DATE PRIMARY KEY,
  usd_pkr    DECIMAL(10,4) NOT NULL
);
CREATE TABLE panel_invoice (
  invoice_no   VARCHAR(16) PRIMARY KEY,
  account_no   INT NOT NULL REFERENCES panel_account(account_no),
  month_start  DATE NOT NULL,
  amount_pkr   DECIMAL(12,2) NOT NULL
);
```

**ERDs:** drawn from this DDL in week 1 (one diagram per department, saved as PNG in the sources folder). Declared relationships: Sales receipt → receipt\_line → pos\_item, receipt → loyalty\_member; Purchasing supplier → vendor\_item, purchase\_order → goods\_receipt → grn\_line; Finance panel\_account → panel\_invoice. Inventory declares none; item → stock\_count and store → stock\_count exist only by matching column names (these become the "inferred" links in reverse engineering).

`stock_count` and `panel_invoice` are not loaded into the two stars; they exist for the planned Stock snapshot process and for an optional cross-check of panel sales against invoices.

## Synthetic history: generator spec

One Python script (`generate_sources.py`, seed 472) creates and populates all four databases; rerunning it produces identical data. Every table carries a `synthetic` comment and the README states it. This replaces the labs' population scripts.

| Table | Planned rows | Notes |
| --- | --- | --- |
| item (Inventory) | 150 | 8 categories; 85% have `pos_code`, 70% have `vendor_code` filled |
| store / branch / branch\_name variants | 10 branches | 2–3 spelling variants per branch in Sales |
| supplier | 25 | 5 importers (USD) |
| loyalty\_member | 1,200 |  |
| panel\_account | 15 | typed 2–3 ways at the till |
| receipt | \~14,000 | about 2.2 lines per receipt |
| receipt\_line | \~30,000 | requirement: 2,000 transaction lines |
| purchase\_order / goods\_receipt | \~1,800 / \~1,800 |  |
| grn\_line | \~5,000 | \~15% in USD |
| fx\_rate | 1,096 days | Nov 2023 – Oct 2026, gradual PKR drift |

**Planted patterns (so analysis has something real to find):**

- Trend: about 1% growth per month in volume, plus price inflation.
- Seasons: Cough and Cold peaks Dec–Feb; Analgesics and Gastro peak in the dengue and monsoon season (Aug–Oct); Vitamins rise before Ramadan.
- Diagnosis story: from Mar 2026, purchase cost of Diabetes Care rises about 12% and Inventory records the higher standard cost from that month, while shelf prices stay fixed, so margin falls.
- Anomalies for review: a one-month Analgesics spike in the East region in Sep 2026 (dengue cluster), a one-month drop at one branch (stock-out), and one keying error (quantity × 10).
- Customer mix: about 70% walk-in, 22% loyalty, 8% panel by value.

**Planted defects and their reject reason codes:**

| Code | Defect | Planted rate | Handling |
| --- | --- | --- | --- |
| R01\_MISSING\_PRODUCT | item code empty or unknown to every crosswalk | \~0.6% of lines | reject |
| R02\_BAD\_QTY | quantity ≤ 0 on a POSTED line | \~0.4% | reject |
| R03\_BAD\_DATE | unparseable date or date after the batch cut-off | \~0.3% | reject |
| R04\_BAD\_AMOUNT | price or cost ≤ 0, or missing | \~0.3% | reject |
| R05\_UNKNOWN\_BRANCH | branch text matches no crosswalk rule | \~0.2% | reject |
| R06\_NO\_FX\_RATE | USD line with no rate on or before the receipt date | a few lines | reject |
| R07\_ORPHAN\_LINE | line whose header receipt or GRN is missing | \~0.2% | reject |
| D01\_EXACT\_DUPLICATE | same source key extracted twice (double export) | \~0.5% | remove, count |
| U01\_UNRESOLVED\_CUSTOMER | panel name or card number not matched | \~1% of panel lines | load to Unknown (−1) and flag |
| — legitimate repeat | same customer, item, day, new line key | \~1% | keep: not a duplicate |

Also planted but fixed rather than rejected: category case and spaces, branch spelling variants, cartons vs strips vs tablets, text dates, float cost, USD amounts.

## Business questions (Q1)

Six questions drive the design; each names its user, measure, grain and decision, and what the warehouse adds over separate departmental reports.

| # | Type | Question | User | Measure | Grain | Decision | What the warehouse and BI add |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BQ1 | Comparison | Which branches grew net sales and gross margin vs the same quarter last year? | Operations Director | Net sales PKR, gross margin PKR | Branch × fiscal quarter | Move stock and pharmacists between branches | Margin needs Sales revenue and Inventory cost on one product and one branch identity; today branch names differ in every system |
| BQ2 | Trend | How do monthly sales move through the flu, dengue and Ramadan seasons? | CEO | Net sales PKR, 3-month rolling average | Category × month | Plan seasonal stock levels | 36 months under one definition; departmental reports change format and units over time |
| BQ3 | Contribution | Which products make up 80% of gross margin? | Category Manager | Gross margin PKR, cumulative share | Product × fiscal year | Negotiate terms, trim the range | One product identity across till codes, vendor codes and item IDs, so a product’s sales and cost add up |
| BQ4 | Diagnosis | Why did Diabetes Care margin fall in 2026: price, cost or mix? | Finance Controller | ASP, purchase unit cost PKR, margin % | Product × month (each star summed separately, then compared) | Renegotiate or switch supplier | Puts selling price (Sales) next to purchase cost converted to PKR (Purchasing + Finance FX); impossible across three engines and two currencies by hand |
| BQ5 | Forecast | What will company-wide net sales be in each of the next three months? | Procurement Head and Finance | Forecast net sales PKR with error range | Company × month | Set the flu-season purchase budget and cash plan | A clean, complete monthly series built in SQL, with lineage, so the forecast input can be defended |
| BQ6 | Anomaly | Which region-category months moved abnormally? | Internal Audit / Pharmacy Ops | Net sales vs expected | Region × category × month | Investigate an outbreak, theft, stock-out or keying error | Flags are traceable to the exact receipt lines, so a flag can be explained, not just reported |

## Architecture, stack and evidence convention

Data moves one way through seven layers, run in order by one Colab notebook, and every layer leaves a saved log.

1. **Sources:** MySQL (Sales, Finance), PostgreSQL (Purchasing), SQLite (Inventory), installed and populated in Colab by the generator.
2. **Raw snapshots:** each extract saved unchanged as CSV per table per batch, never edited.
3. **Staging:** typed and normalized copies, plus the rejects table.
4. **Integration:** crosswalks to canonical product, customer and branch.
5. **Warehouse:** PostgreSQL, schemas `dw` (stars), `stg` (staging, crosswalks), `etl` (batches, rejects, logs), `meta` (metadata, lineage), `ai` (model outputs).
6. **Analytics views:** saved SQL views feeding Power BI and AI.
7. **Consumers:** Power BI (3 pages) and the AI notebooks, which write results back to `ai`.

| Layer | Tool | Why |
| --- | --- | --- |
| Orchestration | Google Colab, Python 3, pandas, SQLAlchemy | Required; one notebook runs end to end |
| Sources | MySQL 8, PostgreSQL 14, SQLite 3 | Three engines, all installable in Colab |
| Warehouse | PostgreSQL, hosted free tier (Neon or Supabase) | Colab writes, Power BI reads; Colab-local databases vanish with the session |
| AI | scikit-learn | Ridge / gradient boosting, Isolation Forest |
| BI | Power BI Desktop (.pbix) | Required |
| Secrets | Colab Secrets | Connection string never appears in the notebook |

**Fallback:** if Power BI cannot reach the hosted database, restore a `pg_dump` into local PostgreSQL on the Power BI laptop. Tested in week 1.

**Evidence and logging convention** (the rubric caps screenshot-only work at 1 mark):

- Every notebook step writes a CSV log to its evidence folder and a row to `etl.batch_stage_log` (batch, stage, table, rows in, rows out, amount in, amount out, status, timestamp).
- Every validation check writes a row to `etl.validation_result` (check, expected, actual, pass/fail, batch).
- Every model run writes to `ai.model_run`; every chart in the report is regenerated from saved CSVs, not pasted.
- Before-and-after cleaning profiles (null counts, distinct spellings, unit mix, min/max dates) are saved for each source table.
- The README lists the run order and the expected row counts and totals after each step.

## Dimensional design (Q6)

Two related processes, selling and buying the same products, form two stars that share Date, Product and Branch.

**Declared grains:**

- `dw.fact_sales`: one row per till receipt line (one product on one receipt). Natural key: (source\_system, receipt\_no, line\_no).
- `dw.fact_purchase`: one row per goods-receipt line (one product received on one GRN). Natural key: (source\_system, grn\_no, line\_no).

| Fact | Measure | Additivity | Derivation |
| --- | --- | --- | --- |
| fact\_sales | quantity\_units | Additive | qty in selling units |
| fact\_sales | gross\_amount\_pkr | Additive | qty × unit price |
| fact\_sales | discount\_pkr | Additive | missing → 0 |
| fact\_sales | net\_amount\_pkr | Additive | gross − discount |
| fact\_sales | cost\_amount\_pkr | Additive | qty × Inventory standard cost effective on the receipt date (cost history) |
| fact\_sales | gross\_margin\_pkr | Additive (derived) | net − cost |
| fact\_purchase | quantity\_units | Additive | boxes × strips per box |
| fact\_purchase | amount\_original | Additive within one currency only | boxes × cost per box |
| fact\_purchase | purchase\_amount\_pkr | Additive | original × rate (1 for PKR) |
| views only | ASP, unit cost, margin % | Non-additive | always recomputed from sums |

| Dimension | Shared | Hierarchy | Built from |
| --- | --- | --- | --- |
| dim\_date | Both (conformed) | Date → month → quarter → year; fiscal quarter → fiscal year (Jul–Jun) | Generated, 2023-11-01 to 2027-01-31 |
| dim\_product | Both (conformed) | SKU → generic → category | Inventory item + crosswalk |
| dim\_branch | Both (conformed) | Branch → area → region | Inventory store + crosswalk |
| dim\_customer | Sales only | Customer → customer type (walk-in, loyalty, panel) | Sales + Finance |
| dim\_supplier | Purchasing only | Supplier → origin (local, import) | Purchasing |

**Null and member policy:**

- Every dimension has an Unknown member (key −1). dim\_customer also has a Walk-in member (key 0): walk-ins are known, just anonymous.
- Fact foreign keys are never null. A missing required value (product, date, quantity, amount, branch) → rejects. An unresolvable customer → Unknown plus `is_customer_unresolved = true`.
- Measures are never null. Descriptive attributes that are missing become 'Not recorded', not null.
- SCD Type 1 on dim\_product and dim\_customer: corrections overwrite. None of the six questions needs history.

**Bus matrix:**

| Process | Date | Product | Branch | Customer | Supplier | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Sales | ✓ | ✓ | ✓ | ✓ |  | Built |
| Purchasing | ✓ | ✓ | ✓ |  | ✓ | Built |
| Stock snapshot | ✓ | ✓ | ✓ |  |  | Planned |
| Returns | ✓ | ✓ | ✓ | ✓ |  | Planned |
| Home delivery | ✓ |  | ✓ | ✓ |  | Planned |

**Departmental source coverage matrix:**

| Department | fact\_sales | fact\_purchase | dim\_product | dim\_branch | dim\_customer | dim\_supplier |
| --- | --- | --- | --- | --- | --- | --- |
| Sales | rows, measures |  | till codes (crosswalk) | branch text (crosswalk) | loyalty, typed panel names |  |
| Purchasing |  | rows, measures | vendor codes (crosswalk) | branch\_id (crosswalk) |  | all |
| Inventory | cost\_amount\_pkr |  | master attributes | master attributes |  |  |
| Finance |  | FX for purchase\_amount\_pkr |  |  | panel accounts |  |

Four departments feed the two stars (requirement: three). Star diagrams are drawn in the deck and in the report.

## Warehouse DDL (Q7)

The dimensional design as PostgreSQL tables: money is NUMERIC(14,2), keys are stable integers, and every fact row carries its lineage columns.

```sql
CREATE TABLE dw.dim_date (
  date_key       INT PRIMARY KEY,              -- 20260315
  full_date      DATE NOT NULL UNIQUE,
  month_start    DATE NOT NULL,
  month_name     TEXT NOT NULL,
  quarter        SMALLINT NOT NULL,
  year           SMALLINT NOT NULL,
  fiscal_quarter SMALLINT NOT NULL,            -- Jul-Sep = 1
  fiscal_year    TEXT NOT NULL,                -- 'FY2026' = Jul 2025-Jun 2026
  is_ramadan     BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE dw.dim_product (
  product_key        INT PRIMARY KEY,          -- -1 = Unknown
  product_code       TEXT NOT NULL UNIQUE,     -- canonical 'P-0312'
  generic_name       TEXT NOT NULL,
  strength           TEXT NOT NULL,
  category           TEXT NOT NULL,
  selling_unit       TEXT NOT NULL,            -- STRIP | BOTTLE | PIECE
  tablets_per_unit   INT,
  std_cost_per_unit  NUMERIC(14,2) NOT NULL,
  updated_batch_id   INT NOT NULL
);
CREATE TABLE dw.dim_branch (
  branch_key     INT PRIMARY KEY,              -- -1 = Unknown
  branch_code    TEXT NOT NULL UNIQUE,         -- 'BR-GUL'
  branch_name    TEXT NOT NULL,
  area           TEXT NOT NULL,
  region         TEXT NOT NULL
);
CREATE TABLE dw.dim_customer (
  customer_key   INT PRIMARY KEY,              -- 0 = Walk-in, -1 = Unknown
  customer_code  TEXT NOT NULL UNIQUE,         -- 'L-1043', 'PANEL-40021'
  customer_type  TEXT NOT NULL,                -- WALKIN | LOYALTY | PANEL
  customer_name  TEXT NOT NULL,
  panel_terms_days SMALLINT,
  updated_batch_id INT NOT NULL
);
CREATE TABLE dw.dim_supplier (
  supplier_key   INT PRIMARY KEY,
  supplier_code  TEXT NOT NULL UNIQUE,
  supplier_name  TEXT NOT NULL,
  origin         TEXT NOT NULL                 -- LOCAL | IMPORT
);
CREATE TABLE dw.fact_sales (
  sales_line_id      BIGSERIAL PRIMARY KEY,
  date_key           INT NOT NULL REFERENCES dw.dim_date,
  product_key        INT NOT NULL REFERENCES dw.dim_product,
  branch_key         INT NOT NULL REFERENCES dw.dim_branch,
  customer_key       INT NOT NULL REFERENCES dw.dim_customer,
  receipt_no         TEXT NOT NULL,             -- degenerate
  line_no            SMALLINT NOT NULL,
  quantity_units     NUMERIC(10,2) NOT NULL,
  gross_amount_pkr   NUMERIC(14,2) NOT NULL,
  discount_pkr       NUMERIC(14,2) NOT NULL,
  net_amount_pkr     NUMERIC(14,2) NOT NULL,
  cost_amount_pkr    NUMERIC(14,2) NOT NULL,
  gross_margin_pkr   NUMERIC(14,2) NOT NULL,
  is_cancelled       BOOLEAN NOT NULL DEFAULT false,
  is_customer_unresolved BOOLEAN NOT NULL DEFAULT false,
  source_system      TEXT NOT NULL,             -- 'sales_db'
  source_key         TEXT NOT NULL,             -- 'GUL-2026-000123|2'
  batch_id           INT NOT NULL,
  UNIQUE (source_system, receipt_no, line_no)
);
CREATE TABLE dw.fact_purchase (
  purchase_line_id     BIGSERIAL PRIMARY KEY,
  date_key             INT NOT NULL REFERENCES dw.dim_date,
  product_key          INT NOT NULL REFERENCES dw.dim_product,
  branch_key           INT NOT NULL REFERENCES dw.dim_branch,
  supplier_key         INT NOT NULL REFERENCES dw.dim_supplier,
  grn_no               TEXT NOT NULL,
  line_no              SMALLINT NOT NULL,
  quantity_units       NUMERIC(10,2) NOT NULL,
  currency_code        CHAR(3) NOT NULL,
  fx_rate_used         NUMERIC(10,4) NOT NULL,   -- 1 for PKR
  amount_original      NUMERIC(14,2) NOT NULL,
  purchase_amount_pkr  NUMERIC(14,2) NOT NULL,
  is_cancelled         BOOLEAN NOT NULL DEFAULT false,
  source_system        TEXT NOT NULL,
  source_key           TEXT NOT NULL,
  batch_id             INT NOT NULL,
  UNIQUE (source_system, grn_no, line_no)
);
```

Supporting tables (DDL written in week 2): `stg.xw_product`, `stg.xw_customer`, `stg.xw_branch` (source system, source key, canonical code, match method, batch); `etl.batch`, `etl.batch_stage_log`, `etl.rejects`, `etl.deletion_log`, `etl.validation_result`; the `meta` tables in the metadata section; the `ai` tables in the AI section.

**Cost rule:** `cost_amount_pkr` is computed at load time from Inventory’s cost history (the cost effective on the receipt date), never from `dim_product.std_cost_per_unit`, which only shows the current cost. That way the SCD Type 1 overwrite of a product never rewrites past margins.

## ETL, quality and loading (Q3, Q4, Q5, Q7)

The pipeline runs in a fixed order, and each step must reconcile with the step before it before the next one runs.

1. **Extract (Colab):** connect to each engine, save raw CSV snapshots unchanged, log row counts and amount totals per table.
2. **Profile (before):** save null counts, distinct spellings of branch and category, unit mix, date formats and min/max dates per table.
3. **Normalize:** parse 'DD/MM/YYYY' text and timestamps to dates; trim and standardize category and branch text; convert boxes and tablets to selling units (`strips_per_box`, `tablets_per_strip`); convert REAL cost to NUMERIC(14,2); convert USD to PKR at the Finance rate on or before the receipt date.
4. **Profile (after):** the same profile again, saved beside the first. These pairs are the before-and-after cleaning evidence.
5. **Crosswalks:** `xw_product` (till code, vendor code, item\_id → canonical product), `xw_branch` (spelling variants, branch\_id, store\_code → canonical branch), `xw_customer` (card number, typed panel name, account number → canonical customer). Each row records its match method: exact, rule (trim/case/alias list) or manual.
6. **Pre-integration checks:** source keys unique per table; every crosswalk many-to-one (no source key maps to two canonical codes); row counts checked before and after every join, so a join can never multiply rows.
7. **Validate and quarantine:** invalid rows go to `etl.rejects` (source system, table, source key, reason code, reason text, raw record as JSON, batch id) using the reason codes in the generator section.
8. **De-duplicate:** only the same source key extracted twice is a duplicate. Same customer, product and day with a new line key is a real repeat and stays.
9. **Load:** dimensions first (upsert on business key, surrogate keys never change), then facts (upsert on natural key).

**Reconciliation (per table, per batch, saved to `etl.batch_stage_log`):**

- Rows: source rows = loaded + rejected + duplicates removed.
- Amounts: source net amount of valid rows = warehouse net amount, under the same month filter, to the paisa. Purchases reconciled in original currency and in PKR.

**Batches:**

- **Watermark:** transaction tables (receipts, receipt lines, GRNs, GRN lines) are extracted when `updated_at` is after the last successful watermark, stored in `etl.batch`; Inventory’s text dates are parsed before comparing. Master tables (items, cost history, stores, suppliers, accounts, FX rates) are small, so they are extracted in full every batch and compared with the previous snapshot.
- **Rerun:** rerunning batch 1 on unchanged input must change 0 rows and 0 totals, because every load is an upsert.
- **Batch 2:** new rows for Sep–Oct 2026; changed rows (a corrected quantity, a corrected panel customer); late arrivals; cancellations.
- **Late-arrival policy:** a fact dated in an earlier month loads into its real date, not the load date; affected months are listed in the batch log.
- **Deletion policy:** sources void or cancel rather than delete. The fact row keeps `is_cancelled = true` and all views exclude it. A row that disappears from a source is logged in `etl.deletion_log` and not deleted automatically.
- **Late-arriving dimension:** a fact whose product is new but valid in Inventory triggers the dimension upsert first, in the same batch.
- **Controlled failure:** batch 2’s fact load raises a planned exception after half the rows, inside one transaction. Show the rollback, the FAILED status, unchanged totals, then the successful rerun matching a clean run.

**SCD Type 1 demo:** one cough syrup filed under Gastro in Inventory is corrected to Cough and Cold. Batch 2 overwrites `dim_product.category`; show both category totals before and after, and an unchanged company total.

## Metadata, lineage, validation and architecture analysis (Q8, Q9)

Every fact row carries its source system, source key and batch id, so tracing a figure is a lookup, not a reconstruction.

**Metadata repository (replaces Practical 8, `meta` schema):**

| Table | Records |
| --- | --- |
| meta.source\_system | Engine, database, department, owner, synthetic flag |
| meta.source\_object | Each source table, primary key, row count per batch |
| meta.column\_map | Source column → staging column → warehouse column |
| meta.transform\_rule | Rule id, plain-language rule, code reference (e.g. R-UNIT-01 boxes to strips) |
| etl.batch | Batch id, watermark range, start/end, status, row and amount totals |
| meta.lineage | Warehouse table + natural key → source system, table, source key, batch id |

**Reverse engineering (one department per engine):** Sales (MySQL), Purchasing (PostgreSQL), Inventory (SQLite). A script reads each catalog through SQLAlchemy and writes an ERD image and draft DDL. Declared keys are marked **observed**; links guessed from matching names (Inventory’s `item_id`, `store_code`) are marked **inferred**.

**Traces to source (each shown end to end, with SQL):**

1. A normal till receipt line: fact row → staging row → raw CSV → MySQL `receipt_line`.
2. A USD purchase line: fact row → rate used → PostgreSQL `grn_line` and Finance `fx_rate`.
3. A late receipt loaded in batch 2.
4. Derived measure: gross\_margin\_pkr = net (Sales) − quantity × standard cost (Inventory).
5. Dashboard total: FY2026 net sales card → view → fact rows → batches → source rows.
6. AI input series: `vw_forecast_features` → fact rows per month.

**Validation suite (each check saved with expected, actual, pass/fail):**

| Check | Expected |
| --- | --- |
| Grain uniqueness | 0 duplicate natural keys in each fact |
| Foreign keys | 0 orphan keys in either star |
| Unknown members | Count and share reported; below 1% of rows |
| Completeness | All 36 months present in both facts, every branch every month |
| Row reconciliation | Source = loaded + rejected + duplicates, per table and batch |
| Amount reconciliation | Source and warehouse totals equal per month |
| Join safety | Totals equal before and after joining every dimension |
| Lineage coverage | 100% of fact rows have source system, key and batch |
| Rerun safety | Unchanged rerun changes 0 rows, 0 totals |
| SCD Type 1 | Category totals move; company total unchanged |
| AI outputs | 0 duplicate rows after a retried run |

**Cross-star rule:** Sales and Purchasing are each summed to product × month first, then compared. Joining two fact tables directly would multiply rows.

**Architecture analysis outline (written from our own evidence in week 6):**

- *Advantages to show:* one product, customer and branch identity across four systems; reruns are safe (rerun log); every figure is traceable (trace outputs); one set of views feeds both BI and AI.
- *Problem areas to show:* crosswalk upkeep (count of manual matches); dependence on the FX table (R06 rejects); a single hosted database as a point of failure and its free-tier limits; batch latency (data is only as fresh as the last batch); Colab session limits; synthetic data hides real-world mess.
- Each point cites a number from our logs: reject rate by reason, run time per step, manual-match count, rerun result.

## Analytic SQL and Power BI (Q10, Q11)

Twelve queries cover every required analysis type; each is presented with its task number, SQL, output grain, result table, chart and a two-line interpretation.

| # | Lab | Analysis | Query | Output grain | Main SQL feature |
| --- | --- | --- | --- | --- | --- |
| A1 | P9 | Comparison | Net sales and margin by branch, this vs last fiscal quarter | Branch × quarter | GROUP BY, CASE, FILTER |
| A2 | P9 | Contribution | Category share of gross margin | Category × fiscal year | SUM() OVER () |
| A3 | P9 | Trend | Monthly net sales by category | Category × month | GROUP BY date hierarchy |
| A4 | P9 | ASP | Average selling price per unit by category | Category × month | SUM(net) / SUM(qty) |
| A5 | P9 | Comparison | Local vs imported purchases in PKR | Origin × quarter | GROUP BY ROLLUP |
| A6 | P9 | Contribution | Year-to-date running net sales | Month | SUM() OVER (ORDER BY) |
| A7 | P10 | Rolling average | 3-month rolling net sales | Month | AVG() OVER (ROWS 2 PRECEDING) |
| A8 | P10 | Growth | Month-on-month and year-on-year growth | Month | LAG(1), LAG(12) |
| A9 | P10 | Ranking change | Top-10 products, rank this year vs last | Product × fiscal year | RANK(), LAG() |
| A10 | P10 | Relationship | Selling price vs purchase unit cost | Product × month | two summed CTEs, then join |
| A11 | P10 | Volatility | Standard deviation and coefficient of variation of monthly sales | Category | STDDEV over a monthly CTE |
| A12 | P10 | Diagnostic | Diabetes Care margin drop split into price, cost and volume effects | Product × month | CTEs + window functions |

The P9/P10 split and task numbers are provisional until the lab manual is checked.

**Saved views:**

| View | Grain | Used by |
| --- | --- | --- |
| vw\_sales\_enriched | Receipt line with all dimension attributes, cancelled excluded | Power BI, A1–A4 |
| vw\_purchase\_product\_month | Product × month (purchases summed) | A10, A12 |
| vw\_sales\_product\_month | Product × month (sales summed) | A10, A12 |
| vw\_margin\_bridge | Product × month price, cost, volume effects | Diagnostic page, A12 |
| vw\_forecast\_features | Company × month with lag and rolling features | Forecast |
| vw\_region\_category\_month | Region × category × month with trailing statistics | Anomaly detection |

**Power BI report (11 visuals, slicers not counted):**

| Page | Visuals | Slicers |
| --- | --- | --- |
| Management Overview | KPI cards (net sales, margin %, purchases); monthly net sales with 3-month rolling average; branch comparison vs last year; category contribution | Date, region, category |
| Diagnostic Analysis | Margin % trend by category; ASP vs unit cost for Diabetes Care; margin bridge (price, cost, volume); top-10 rank change | Date, region, category |
| AI Insights | Forecast vs holdout actuals plus next 3 months; anomaly scatter by region-category-month; flagged-case table with source links | Region, category |

Every page shows units (PKR), period (Nov 2023–Oct 2026), measure definitions and the last batch id. Three totals reconciled against warehouse SQL under the same filters: FY2026 net sales; Gulshan-e-Iqbal branch net sales for calendar 2025; October 2026 purchases in PKR. No chart claims a cause from correlation; bar axes start at zero.

**Defensible diagnostic finding (planted):** Diabetes Care margin falls from March 2026 because purchase cost rises while ASP is flat; the bridge attributes the drop mostly to cost, not to volume or mix.

## AI layer (Q12, Q13, Q14)

Both AI tasks read only from SQL views, are evaluated in time order against a simple baseline, and write to their own tables.

**Forecast features are built in SQL, not Python** (the brief requires analytic SQL feature views):

```sql
CREATE VIEW dw.vw_forecast_features AS
WITH m AS (
  SELECT d.month_start, SUM(f.net_amount_pkr) AS net_sales_pkr
  FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key)
  WHERE NOT f.is_cancelled
  GROUP BY d.month_start
)
SELECT month_start,
       net_sales_pkr,
       LAG(net_sales_pkr, 1)  OVER w AS lag_1,
       LAG(net_sales_pkr, 12) OVER w AS lag_12,
       AVG(net_sales_pkr) OVER (ORDER BY month_start ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS rolling_3_prior,
       EXTRACT(MONTH FROM month_start) AS month_of_year
FROM m
WINDOW w AS (ORDER BY month_start);
```

The rolling feature uses only prior months, so no value leaks from the month being predicted.

**Monthly forecast (BQ5):**

- Target: company-wide monthly net sales in PKR.
- Split: training Nov 2023 – Jul 2026 (33 months); untouched holdout Aug–Oct 2026. No random split anywhere.
- Baselines: seasonal naive (same month last year) and last-month naive.
- Model: ridge regression or gradient boosting on lag\_1, lag\_12, rolling\_3\_prior, month of year and a Ramadan flag.
- Tuning: rolling-origin validation inside the training months only (origins from month 24, three months ahead each).
- Scoring: MAE and RMSE in PKR on the holdout, model vs both baselines. The model does not need to win; the comparison must be honest.
- Output: refit on all 36 months, forecast Nov 2026 – Jan 2027, labelled as a forecast, with a range from the validation errors.
- Stated limitation: lag\_12 leaves about 21 usable training rows.

**Anomaly detection (BQ6):**

- Series grain: region × category × month net sales, from `vw_region_category_month` (3 × 8 = 24 series, 864 points), built with window functions (trailing 6-month median, year-on-year ratio).
- Calibration: Nov 2023 – Oct 2025. Review: Nov 2025 – Oct 2026.
- Transparent threshold: robust z-score (median and MAD from calibration) of the ratio to the trailing median; flag above 3.5.
- Model: Isolation Forest on ratio to trailing median, year-on-year ratio and ratio to category average; fitted on calibration only.
- Evaluation: a separate copy of the review period with about 25 injected spikes and drops (labels kept). Report precision, recall and false alerts for both methods.
- Case review: three flags on the real data (planted: East Analgesics Sep 2026, one branch stock-out, one keying error), each traced to its receipt lines.

**AI output tables:**

| Table | Holds | Duplicate protection |
| --- | --- | --- |
| ai.model\_run | run id, task, method, parameters, training window, data batch id, metrics, code version | run id = hash of config + data batch |
| ai.forecast\_result | run id, date key, prediction, lower, upper, actual, is\_holdout | unique (run\_id, date\_key) |
| ai.anomaly\_result | run id, date key, region, category, value, expected, score, method, is\_flag, is\_injected\_copy | unique (run\_id, date\_key, region, category, method) |

They link to `dim_date` and `dim_branch` region values but never sit inside fact tables. A retried run upserts on the same keys.

**Decision support (Q14):** each recommendation states the decision, the evidence (dashboard visual, SQL result, AI output), its trace to source, and its limitation. Planned: (1) set the Nov–Jan purchase budget from the forecast range, weighted to Cough and Cold; (2) renegotiate or switch the Diabetes Care supplier, using the margin bridge; (3) investigate the East Analgesics spike with Pharmacy Ops before the next dengue season.

## Deliverables, report and demo

Five deliverables are submitted; the report and the demo are planned now so the build produces their evidence as it goes.

| Deliverable | Contents |
| --- | --- |
| Colab notebook + SQL scripts + README | Runs the whole pipeline in order from a fresh session; README lists run order, expected counts and totals; secrets in Colab Secrets only |
| Evidence folders | Source, ETL, warehouse, metadata, validation and AI evidence (folder names to match the project brief) |
| Power BI file (.pbix) | Three pages, reconciled totals documented |
| Technical report | 8–12 pages excluding appendices, with member contribution statement |
| Live demo + individual viva | Run-sheet below; every member explains every criterion at connection level |

**Report outline (8–12 pages):**

1. Problem, scenario and the six business questions (1 page)
2. Sources, generator and planning matrix (1 page)
3. Architecture and ETL, with reconciliation results (1.5 pages)
4. Dimensional design: star diagrams, grains, bus matrix, coverage matrix (1.5 pages)
5. Data quality, batches, rerun, failure recovery, SCD (1 page)
6. Metadata, lineage traces and validation results (1.5 pages)
7. Analytic SQL highlights and Power BI report (1.5 pages)
8. Forecast and anomaly results vs baselines (1.5 pages)
9. Recommendations, architecture analysis, limitations (1 page)
10. Member contribution statement: a table of member, components owned, criteria, commits or notebook sections, and hours (half page)

Appendices: full DDL, all 12 queries with outputs, validation table, reject summary.

**Demo run-sheet (about 12 minutes):**

1. Fresh Colab session: run the generator; show row counts in the four sources (1 min).
2. Run batch 1; show the reconciliation table and rejects by reason (2 min).
3. Rerun batch 1; show 0 changes (1 min).
4. Run batch 2 with the planned failure; show rollback and FAILED status; rerun; show matching totals and the SCD Type 1 effect (2 min).
5. Trace the FY2026 net sales card to a till receipt line (2 min).
6. Power BI: three pages, one reconciled total checked live in SQL (2 min).
7. AI: holdout scores vs baselines, next-3-month forecast, one flagged case traced (2 min).

## Ownership, timeline, rubric coverage and risks

Each member owns one rubric criterion end to end, because the viva gives 0 for a criterion when a student cannot explain their own component in it, and at most 1 when they cannot explain how it connects to the rest.

| Member | Owns | Criterion | AI share |
| --- | --- | --- | --- |
| \[Member 1\] | Generator, four sources, extraction, profiling, cleaning, crosswalks, rejects, reconciliation | C1 Sources and ETL | — |
| \[Member 2\] | Warehouse DDL, loading, surrogate keys, batch 2, SCD Type 1, failure recovery | C2 Warehouse | Forecast |
| \[Member 3\] | Metadata, reverse engineering, lineage traces, validation suite, architecture analysis | C3 Lineage and validation | Anomaly detection |
| \[Member 4\] | 12 queries, saved views, Power BI, reconciliation of totals | C4 SQL and BI | AI output tables, recommendations |

**Build order (relative weeks; real dates once the deadline is known):**

1. Week 1: generator and four sources in Colab; hosted warehouse created; Power BI connection tested; source ERDs drawn.
2. Week 2: extract, profile, normalize, crosswalks, rejects, reconciliation.
3. Week 3: warehouse DDL, both stars loaded, rerun test, batch 2, SCD Type 1, controlled failure.
4. Week 4: metadata, reverse engineering, lineage traces, validation suite; 12 queries and views.
5. Week 5: forecast, anomaly detection, AI tables; Power BI report.
6. Week 6: recommendations, report, README, clean full rerun from a fresh session, demo and viva rehearsal (each member presents another member’s part once).

**Rubric coverage (every Score 2 item → where it is produced):**

| Criterion | Score 2 needs | Produced in |
| --- | --- | --- |
| C1 | 4 departments on 3 engines; cleaning with before/after evidence; crosswalks; rejects; reconciled counts and amounts; unchanged rerun; batch 2; failure recovery | Source systems; Generator; ETL sections |
| C2 | Two stars from 3+ departments; grains passing uniqueness; valid keys; Date + conformed dims; unknown members; SCD 1; measures equal before/after joins | Dimensional design; Warehouse DDL; Validation |
| C3 | Metadata repository; ERD + DDL per engine; 6 traces; expected/actual/pass for every check; evidence-based architecture analysis | Metadata, lineage, validation section |
| C4 | 12 queries with chart and interpretation; saved views; 3 pages; 10+ visuals; date/region/category filters; 3 reconciled totals; one diagnostic finding | Analytic SQL and Power BI |
| C5 | Both tasks from SQL views; baseline vs model MAE/RMSE on 3-month holdout; threshold vs model precision/recall on injected labels; 3 cases; versioned outputs; a named decision | AI layer |

**Risks and fallbacks:**

| Risk | Fallback |
| --- | --- |
| Power BI cannot reach the hosted warehouse | Local PostgreSQL restored from `pg_dump`; tested in week 1 |
| MySQL will not install in Colab | MariaDB (same SQL) via apt |
| Free-tier database sleeps or hits limits | Nightly `pg_dump`; the notebook rebuilds everything from the seed |
| Too few training rows for the forecast | State it; compare honestly with baselines |
| A member cannot explain another part | Week 6 rehearsal: each member presents someone else’s component |

**Placeholder repository layout** (replace with the project brief’s folder list): `01_sources/`, `02_etl/`, `03_warehouse/`, `04_metadata_lineage/`, `05_validation/`, `06_sql/`, `07_ai/`, `08_powerbi/`, `09_report/`, plus `pipeline.ipynb` and `README.md`.
