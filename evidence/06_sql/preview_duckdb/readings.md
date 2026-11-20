# Analytic queries A1-A12 (pre-database DuckDB preview)

Synthetic data (seed 472). Task numbers in Practicals 9 and 10 are provisional until the lab manual is checked. Each reading is generated from the query result.

## A1  branch quarter comparison

- Lab: P9 · Analysis: Comparison · Output grain: Branch x quarter · SQL feature: GROUP BY, CASE, FILTER
- SQL: `sql/04_queries/A01_branch_quarter_comparison.sql` · Result: `A01_branch_quarter_comparison.csv` (10 rows) · Chart: `A01_branch_quarter_comparison.png`

> 7 of 10 branches grew gross margin vs the same quarter last year; Gulberg grew net sales most (+72.3%), North Nazimabad least (-24.2%).
> Branches that fell are the first to review for stock and pharmacist moves (BQ1); the table shows the previous quarter too, so a one-off dip can be told apart from a trend.

## A2  category margin share

- Lab: P9 · Analysis: Contribution · Output grain: Category x fiscal year · SQL feature: SUM() OVER ()
- SQL: `sql/04_queries/A02_category_margin_share.sql` · Result: `A02_category_margin_share.csv` (32 rows) · Chart: `A02_category_margin_share.png`

> In FY2026 Vitamins and Supplements gave the largest share of gross margin (21.1%), and the top three categories together gave 53.4%.
> Diabetes Care's share went from 17.7% (FY2025) to 17.4% (FY2026); FY2026 holds only four months after the March 2026 cost rise, which A12 examines month by month.

## A3  monthly category trend

- Lab: P9 · Analysis: Trend · Output grain: Category x month · SQL feature: GROUP BY date hierarchy
- SQL: `sql/04_queries/A03_monthly_category_trend.sql` · Result: `A03_monthly_category_trend.csv` (288 rows) · Chart: `A03_monthly_category_trend.png`

> Cough and Cold sells 1.52x its other-month average in Dec-Feb, Analgesics 1.66x and Gastro 1.46x in Aug-Oct.
> Seasonal stock plans (BQ2) should follow these peaks; Vitamins also rise in the month before Ramadan.

## A4  asp by category

- Lab: P9 · Analysis: ASP · Output grain: Category x month · SQL feature: SUM(net) / SUM(qty)
- SQL: `sql/04_queries/A04_asp_by_category.sql` · Result: `A04_asp_by_category.csv` (288 rows) · Chart: `A04_asp_by_category.png`

> ASP rose most in Gastro (+31.0% from the first three months to Aug-Oct 2026) and least in Antibiotics (+16.0%), following the July price rises.
> Category ASP also moves with the mix of products sold, so a change is checked at product level (A10, A12) before it is called a price change.

## A5  local vs import purchases

- Lab: P9 · Analysis: Comparison · Output grain: Origin x quarter · SQL feature: GROUP BY ROLLUP
- SQL: `sql/04_queries/A05_local_vs_import_purchases.sql` · Result: `A05_local_vs_import_purchases.csv` (40 rows) · Chart: `A05_local_vs_import_purchases.png`

> Imports were 17.1% of all purchases (PKR 2,824,860 of PKR 16,546,049); the ROLLUP rows give each quarter's subtotal and the grand total.
> Imported lines carry exchange-rate risk: their PKR cost moves with USD/PKR even when the USD price is flat.

## A6  ytd running sales

- Lab: P9 · Analysis: Contribution · Output grain: Month · SQL feature: SUM() OVER (ORDER BY)
- SQL: `sql/04_queries/A06_ytd_running_sales.sql` · Result: `A06_ytd_running_sales.csv` (36 rows) · Chart: `A06_ytd_running_sales.png`

> FY2025 closed at PKR 4,957,885 and FY2026 at PKR 6,216,936 (+25.4%).
> FY2027 has reached PKR 2,381,915 after four months; the running total shows whether the year is ahead of the last one at the same point.

## A7  rolling 3 month

- Lab: P10 · Analysis: Rolling average · Output grain: Month · SQL feature: AVG() OVER (ROWS 2 PRECEDING)
- SQL: `sql/04_queries/A07_rolling_3_month.sql` · Result: `A07_rolling_3_month.csv` (36 rows) · Chart: `A07_rolling_3_month.png`

> The 3-month average rose from PKR 346,028 (Jan 2024) to PKR 597,292 (Oct 2026), +73% over the period.
> Smoothing hides one-off months such as the Jun 2026 stock-out, which is why A8 and the anomaly detection look at single months.

## A8  growth mom yoy

- Lab: P10 · Analysis: Growth · Output grain: Month · SQL feature: LAG(1), LAG(12)
- SQL: `sql/04_queries/A08_growth_mom_yoy.sql` · Result: `A08_growth_mom_yoy.csv` (36 rows) · Chart: `A08_growth_mom_yoy.png`

> Year-on-year growth averaged 23.2% across months, ranging from -7.1% (Aug 2026) to 47.0% (Aug 2025).
> Month-on-month growth mostly reflects seasons; year-on-year compares like with like and is the better measure of trend.

## A9  top10 rank change

- Lab: P10 · Analysis: Ranking change · Output grain: Product x fiscal year · SQL feature: RANK(), LAG()
- SQL: `sql/04_queries/A09_top10_rank_change.sql` · Result: `A09_top10_rank_change.csv` (10 rows) · Chart: `A09_top10_rank_change.png`

> Ferrous Sulphate 200 mg stayed the top seller; Lancets 100 pcs climbed the most (40 places, from rank 44 to 4).
> 4 of the top 10 are Diabetes Care products, so supplier terms for this category (A12) matter for a large part of sales.

## A10  price vs purchase cost

- Lab: P10 · Analysis: Relationship · Output grain: Product x month · SQL feature: two summed CTEs, then join
- SQL: `sql/04_queries/A10_price_vs_purchase_cost.sql` · Result: `A10_price_vs_purchase_cost.csv` (3049 rows) · Chart: `A10_price_vs_purchase_cost.png`

> For Diabetes Care, purchase cost took 73.8% of the selling price in Sep 2025-Feb 2026 and 83.2% in Mar-Oct 2026: the price-cost gap narrowed from 26.2% to 16.8%.
> Across product-months, price and purchase cost move together (correlation 0.99), because dearer products cost more to buy; the stars were summed separately before joining, so no rows were multiplied.

## A11  volatility

- Lab: P10 · Analysis: Volatility · Output grain: Category · SQL feature: STDDEV over a monthly CTE
- SQL: `sql/04_queries/A11_volatility.sql` · Result: `A11_volatility.csv` (8 rows) · Chart: `A11_volatility.png`

> Analgesics is the most volatile category (CV 0.40) and Personal Care the steadiest (CV 0.20).
> Volatile categories need larger safety stock or seasonal ordering; the CV includes the upward trend, so part of it is growth, not risk.

## A12  diabetes margin bridge

- Lab: P10 · Analysis: Diagnostic · Output grain: Product x month (category total) · SQL feature: CTEs + window functions
- SQL: `sql/04_queries/A12_diabetes_margin_bridge.sql` · Result: `A12_diabetes_margin_bridge.csv` (36 rows) · Chart: `A12_diabetes_margin_bridge.png`

> Diabetes Care margin fell from 26.8% in Feb 2026 to 17.2% in Mar 2026: the cost effect was PKR -8,294, against PKR -70 from price and PKR 3,782 from volume.
> The drop is mostly cost (standard cost up from 1 Mar 2026 while ASP stayed flat), so renegotiating or switching the supplier is the lever (BQ4), not pricing or promotion.
