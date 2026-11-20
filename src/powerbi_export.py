"""Export the data Power BI reads (unit 4.08). Synthetic data.

Power BI Desktop reads CSV exports of the saved views (docs/DECISIONS.md: no live connection
needed). This writes to powerbi/data/:
  one CSV per view (vw_*.csv) and per AI output table (ai_*.csv)
  DATA_DICTIONARY.md   every file and column with its type and meaning
and powerbi/reconciliation.csv: the three report totals computed in SQL and again from the
exported CSVs, which must be equal:
  1. FY2026 net sales
  2. Gulshan-e-Iqbal branch net sales, calendar 2025
  3. October 2026 purchases in PKR

  python -m src.powerbi_export            # from PostgreSQL
  python -m src.powerbi_export --duckdb   # pre-database preview (data/offline_dw_ai.duckdb)
"""
from __future__ import annotations

import sys

import pandas as pd

from src.common import ROOT

OUT = ROOT / "powerbi" / "data"
EXPORTS = {  # file name: (SQL, description)
    "vw_sales_enriched": ("SELECT * FROM dw.vw_sales_enriched ORDER BY sales_line_id",
                          "One row per receipt line with all dimension attributes; cancelled lines excluded."),
    "vw_sales_product_month": ("SELECT * FROM dw.vw_sales_product_month ORDER BY product_code, month_start",
                               "Sales summed to product x month."),
    "vw_purchase_product_month": ("SELECT * FROM dw.vw_purchase_product_month ORDER BY product_code, month_start",
                                  "Purchases summed to product x month (PKR, units, original currency)."),
    "vw_margin_bridge": ("SELECT * FROM dw.vw_margin_bridge ORDER BY product_code, month_start",
                         "Month-on-month margin change per product split into volume, price and cost effects."),
    "vw_forecast_features": ("SELECT * FROM dw.vw_forecast_features ORDER BY month_start",
                             "Company x month net sales with lag and rolling features."),
    "vw_region_category_month": ("SELECT * FROM dw.vw_region_category_month ORDER BY region, category, month_start",
                                 "Region x category x month net sales with trailing statistics."),
    "vw_purchase_enriched": (
        "SELECT f.purchase_line_id, f.grn_no, f.line_no, d.full_date, d.month_start, d.fiscal_year, d.fiscal_quarter, "
        "p.product_code, p.generic_name, p.category, b.branch_name, b.region, s.supplier_name, s.origin, "
        "f.quantity_units, f.currency_code, f.fx_rate_used, f.amount_original, f.purchase_amount_pkr, f.batch_id "
        "FROM dw.fact_purchase f JOIN dw.dim_date d ON d.date_key = f.date_key "
        "JOIN dw.dim_product p ON p.product_key = f.product_key JOIN dw.dim_branch b ON b.branch_key = f.branch_key "
        "JOIN dw.dim_supplier s ON s.supplier_key = f.supplier_key WHERE NOT f.is_cancelled ORDER BY f.purchase_line_id",
        "One row per goods-receipt line with dimension attributes; cancelled GRNs excluded (for the purchases KPI)."),
    "ai_forecast_result": ("SELECT r.*, d.month_start, m.method FROM ai.forecast_result r JOIN ai.model_run m "
                           "USING (run_id) JOIN dw.dim_date d ON d.date_key = r.date_key ORDER BY r.date_key",
                           "Holdout predictions and the Nov 2026 - Jan 2027 forecast."),
    "ai_anomaly_result": ("SELECT a.*, d.month_start FROM ai.anomaly_result a JOIN dw.dim_date d ON d.date_key = "
                          "a.date_key WHERE NOT a.is_injected_copy ORDER BY a.method, a.region, a.category, a.date_key",
                          "Anomaly scores and flags on the real review months."),
    "dim_date": ("SELECT * FROM dw.dim_date ORDER BY date_key", "Conformed date dimension (fiscal year Jul-Jun)."),
    "dim_product": ("SELECT product_code, generic_name, strength, category, selling_unit FROM dw.dim_product "
                    "ORDER BY product_code", "Conformed product dimension (current values, SCD Type 1)."),
    "dim_branch": ("SELECT branch_code, branch_name, area, region FROM dw.dim_branch ORDER BY branch_code",
                   "Conformed branch dimension: branch -> area -> region."),
    "etl_last_batch": ("SELECT max(batch_id) AS last_batch_id FROM dw.fact_sales",
                       "Last batch id loaded (shown in every page footer)."),
}
RECON = [
    ("FY2026 net sales (PKR)",
     "SELECT SUM(net_amount_pkr) FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key) "
     "WHERE NOT f.is_cancelled AND d.fiscal_year = 'FY2026'",
     lambda x: x["vw_sales_enriched"].query("fiscal_year == 'FY2026'").net_amount_pkr.sum()),
    ("Gulshan-e-Iqbal net sales, calendar 2025 (PKR)",
     "SELECT SUM(f.net_amount_pkr) FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key) "
     "JOIN dw.dim_branch b USING (branch_key) WHERE NOT f.is_cancelled AND d.year = 2025 "
     "AND b.branch_name = 'Gulshan-e-Iqbal'",
     lambda x: x["vw_sales_enriched"].query("year == 2025 and branch_name == 'Gulshan-e-Iqbal'").net_amount_pkr.sum()),
    ("October 2026 purchases (PKR)",
     "SELECT SUM(f.purchase_amount_pkr) FROM dw.fact_purchase f JOIN dw.dim_date d USING (date_key) "
     "WHERE NOT f.is_cancelled AND d.month_start = DATE '2026-10-01'",
     lambda x: x["vw_purchase_enriched"].query("month_start == '2026-10-01'").purchase_amount_pkr.sum()),
]


def export(run_sql, source_label: str) -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    frames, dictionary = {}, ["# Power BI data dictionary", "",
                              f"Synthetic data (seed 472). Exported from the {source_label}. Money in PKR, "
                              "2 decimals; ratios are recomputed from sums in the measures.", ""]
    for name, (sql, desc) in EXPORTS.items():
        df = run_sql(sql)
        df.to_csv(OUT / f"{name}.csv", index=False, lineterminator="\n", encoding="utf-8")
        frames[name] = pd.read_csv(OUT / f"{name}.csv")                # read back: check the files themselves
        dictionary += [f"## {name}.csv ({len(df)} rows)", "", desc, "", "| Column | Type |", "| --- | --- |",
                       *[f"| {c} | {str(t)} |" for c, t in df.dtypes.items()], ""]
    (OUT / "DATA_DICTIONARY.md").write_text("\n".join(dictionary), encoding="utf-8", newline="\n")
    rows = []
    for label, sql, from_csv in RECON:
        sql_total = round(float(run_sql(sql).iloc[0, 0]), 2)
        csv_total = round(float(from_csv(frames)), 2)
        rows.append({"total": label, "sql_total": sql_total, "csv_total": csv_total,
                     "power_bi_total": "", "result": "PASS" if abs(sql_total - csv_total) < 0.005 else "FAIL"})
    recon = pd.DataFrame(rows)
    recon.to_csv(ROOT / "powerbi" / "reconciliation.csv", index=False, lineterminator="\n")
    return recon


if __name__ == "__main__":
    if "--duckdb" in sys.argv:
        import duckdb

        from src.common import DATA_DIR

        con = duckdb.connect(str(DATA_DIR / "offline_dw_ai.duckdb"), read_only=True)
        res = export(lambda sql: con.execute(sql).df(), "pre-database DuckDB preview (rerun from PostgreSQL in 4.08)")
    else:
        from sqlalchemy import text

        from src.common import get_engine

        eng = get_engine("dw")
        res = export(lambda sql: pd.read_sql(text(sql), eng), "PostgreSQL warehouse")
    print(res.to_string(index=False))
