# Power BI build guide (fallback, about 45 minutes)

Use this if `powerbi/nuskha.pbip` will not open. It builds the same report by hand from the CSV
files in `powerbi/data/`. **All data is synthetic (seed 472).** Every number on the report must
match `powerbi/reconciliation.csv`.

You need Power BI Desktop on Windows and the folder `powerbi\data` copied to the PC.

## 1. Load the data (10 min)

1. Open Power BI Desktop and choose **Blank report**.
2. **Home → Transform data → New Source → Blank Query**, then open **Advanced Editor** and paste
   `"C:\full\path\to\powerbi\data"`, using your real path. Name the query `DataFolder`.
3. For each file below choose **Home → New Source → Text/CSV**, pick the file, and click
   **Transform Data**. Check that the types match the table (the column headers in the first row
   are promoted automatically). Rename each query as shown:

   | File | Query name | Columns to type as Date |
   | --- | --- | --- |
   | `vw_sales_enriched.csv` | Sales | full_date, month_start |
   | `vw_purchase_enriched.csv` | Purchases | full_date, month_start |
   | `dim_date.csv` | Date | full_date, month_start |
   | `dim_product.csv` | Product | - |
   | `dim_branch.csv` | Branch | - |
   | `vw_margin_bridge.csv` | Margin Bridge | month_start, prev_month |
   | `vw_region_category_month.csv` | Region Category Month | month_start |
   | `ai_forecast_result.csv` | Forecast | month_start |
   | `ai_anomaly_result.csv` | Anomaly | month_start |
   | `etl_last_batch.csv` | Last Batch | - |

4. **Close & Apply**.

## 2. Model (5 min)

1. Open **Model view** and create these relationships (many-to-one, single direction):
   - Sales[full_date] → Date[full_date]; Purchases[full_date] → Date[full_date]
   - Sales[product_code] → Product[product_code]; Purchases[product_code] → Product[product_code]
   - Sales[branch_name] → Branch[branch_name]; Purchases[branch_name] → Branch[branch_name]
2. Select the Date table, choose **Table tools → Mark as date table**, and pick `full_date`.

## 3. Measures (5 min)

Select the Sales table, choose **New measure**, and add each line below. Do the same on the
Purchases table for the last three. Ratios always use DIVIDE and are recomputed from sums.

```
Net Sales = SUM(Sales[net_amount_pkr])
Gross Margin = SUM(Sales[gross_margin_pkr])
Margin % = DIVIDE([Gross Margin], [Net Sales])
Units Sold = SUM(Sales[quantity_units])
ASP = DIVIDE([Net Sales], [Units Sold])
Net Sales LY = CALCULATE([Net Sales], SAMEPERIODLASTYEAR('Date'[full_date]))
Net Sales 3M Avg = DIVIDE(CALCULATE([Net Sales], DATESINPERIOD('Date'[full_date], MAX('Date'[full_date]), -3, MONTH)), 3)
Last Batch = MAX('Last Batch'[last_batch_id])
Purchases = SUM(Purchases[purchase_amount_pkr])
Units Purchased = SUM(Purchases[quantity_units])
Purchase Unit Cost = DIVIDE([Purchases], [Units Purchased])
```

Format: Net Sales, Gross Margin, Purchases and Net Sales LY as whole numbers with a thousands separator; Margin % as a percentage with 1 decimal.

## 4. Page 1: Management Overview (8 min)

Slicers (top row): **Date** (Date[month_start], "Between" style), **Region** (Branch[region]) and **Category** (Product[category]).

| # | Visual | Fields |
| --- | --- | --- |
| 1 | Card ×3 (counts as one KPI visual) | Net Sales; Margin %; Purchases |
| 2 | Line chart: monthly net sales and 3-month average | X: Date[month_start]; Y: Net Sales, Net Sales 3M Avg |
| 3 | Clustered bar: branch vs last year | Y: Branch[branch_name]; X: Net Sales, Net Sales LY |
| 4 | 100% stacked bar: category contribution | Y: Date[fiscal_year]; X: Gross Margin; Legend: Product[category] |

## 5. Page 2: Diagnostic Analysis (8 min)

Use the same three slicers (select each, copy, paste, and choose **Sync** when asked).

| # | Visual | Fields |
| --- | --- | --- |
| 5 | Line chart: margin % trend by category | X: Date[month_start]; Y: Margin %; Legend: Product[category] |
| 6 | Line chart: ASP vs unit cost, Diabetes Care | X: Date[month_start]; Y: ASP, Purchase Unit Cost; visual filter Product[category] = Diabetes Care |
| 7 | Clustered column: margin bridge | X: Margin Bridge[month_start]; Y: volume_effect_pkr, price_effect_pkr, cost_effect_pkr (Sum); visual filter category = Diabetes Care |
| 8 | Table: top-10 rank change | Product[generic_name], Product[strength], Net Sales; Top N filter = 10 by Net Sales; add Date[fiscal_year] slicer set to FY2026 |

## 6. Page 3: AI Insights (6 min)

Slicers: **Region** (Region Category Month[region]) and **Category** (Region Category Month[category]).

| # | Visual | Fields |
| --- | --- | --- |
| 9 | Line chart: forecast vs holdout actuals + next 3 months | X: Forecast[month_start]; Y: actual, prediction, lower, upper (Sum); title says "Forecast, not actual" for Nov 2026 - Jan 2027 |
| 10 | Scatter: anomaly score by region-category-month | X: Anomaly[month_start]; Y: Anomaly[score]; Legend: Anomaly[is_flag]; Details: region, category; visual filter method = robust_z |
| 11 | Table: flagged cases with source links | Anomaly[region], [category], [date_key], [value], [expected], [score], [method]; filter is_flag = True; add a text box pointing to `evidence/07_ai/anomaly_case_traces.csv` for the receipt lines |

## 7. Footer on every page (2 min)

Add a text box: "Synthetic data (seed 472). Units: PKR. Period: Nov 2023 – Oct 2026. Net sales =
quantity × price − discount; cancelled lines excluded. Margin % = gross margin ÷ net sales." Next to
it, add a card showing **Last Batch**. Bar axes start at zero (the Power BI default; do not change it).

## 8. Reconcile and save (3 min)

1. On page 1 check the three totals against `powerbi/reconciliation.csv`:
   - FY2026 net sales: set the Date slicer to Jul 2025 – Jun 2026 and read the Net Sales card.
   - Gulshan-e-Iqbal, calendar 2025: Date Jan–Dec 2025, select the branch in visual 3.
   - October 2026 purchases: Date = Oct 2026 and read the Purchases card.
2. Type the three Power BI values into the `power_bi_total` column of `reconciliation.csv`.
3. **File → Save as** `powerbi/nuskha.pbix`, then **File → Export → PDF** to `powerbi/nuskha.pdf`.
