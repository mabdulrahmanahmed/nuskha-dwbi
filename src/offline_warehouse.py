"""Pre-database stand-in warehouse in DuckDB (synthetic data, seed 472).

Builds the warehouse state after batch 1 and batch 2 from the offline dry run (dimension and
fact rows from src/load.py, batch 2 upserted over batch 1 on the natural key), stores it in
data/offline_dw.duckdb with the same schema and table names as PostgreSQL (dw.*), and runs the
real view files in sql/03_views/ against it. DuckDB understands the PostgreSQL SQL used in the
views (window functions, FILTER, ROLLUP, percentile_cont WITHIN GROUP, INTERVAL).

It lets the SQL views, the 12 queries and the AI code be developed and checked before the
PostgreSQL warehouse exists. Its outputs are previews; the official ones come from PostgreSQL.

  python -m src.offline_warehouse            # build data/offline_dw.duckdb and check the views
"""
from __future__ import annotations

import pandas as pd

from src.common import DATA_DIR, SQL_DIR, evidence_dir
from src.create_sources import split_statements
from src.offline_dry_run import CUT1, CUT2, run_batch
from src.raw import raw_from_generated

DUCK_PATH = DATA_DIR / "offline_dw.duckdb"
DECIMALS = {"quantity_units": "DECIMAL(10,2)", "fx_rate_used": "DECIMAL(10,4)"}


def _sql_type(col: str) -> str | None:
    if col in DECIMALS:
        return DECIMALS[col]
    if col.endswith("_pkr") or col in ("amount_original", "std_cost_per_unit"):
        return "DECIMAL(14,2)"
    return None


def final_state() -> dict:
    """Dimension and fact frames as the warehouse holds them after batch 2."""
    b1 = run_batch(raw_from_generated(1, until=CUT1), CUT1, 1)
    d1 = b1["dims"]
    b2 = run_batch(raw_from_generated(2, since=CUT1, until=CUT2), CUT2, 2,
                   {"branch_keys": dict(zip(d1["dim_branch"].branch_code, d1["dim_branch"].branch_key)),
                    "customer_keys": dict(zip(d1["dim_customer"].customer_code, d1["dim_customer"].customer_key))},
                   previous_stg=b1["stg"])
    tables = dict(b2["dims"])
    # Dimension upserts: batch-2 rows win; members only seen in batch 1 stay.
    for name, key in (("dim_customer", "customer_code"), ("dim_product", "product_code"),
                      ("dim_branch", "branch_code"), ("dim_supplier", "supplier_code")):
        tables[name] = (pd.concat([d1[name], b2["dims"][name]]).drop_duplicates(key, keep="last")
                        .sort_values(name.replace("dim_", "") + "_key").reset_index(drop=True))
    for fact, nk in (("fact_sales", ["receipt_no", "line_no"]), ("fact_purchase", ["grn_no", "line_no"])):
        both = pd.concat([b1["facts"][fact], b2["facts"][fact]]).drop_duplicates(nk, keep="last")
        both = both.sort_values(["batch_id", *nk]).reset_index(drop=True)
        both.insert(0, "sales_line_id" if fact == "fact_sales" else "purchase_line_id", range(1, len(both) + 1))
        tables[fact] = both
    return tables


def build_duckdb(tables: dict | None = None):
    import duckdb

    tables = tables or final_state()
    if DUCK_PATH.exists():
        DUCK_PATH.unlink()
    con = duckdb.connect(str(DUCK_PATH))
    con.execute("CREATE SCHEMA dw")
    for name, df in tables.items():
        con.register("frame", df)
        cols = ", ".join(f"CAST({c} AS {_sql_type(c)}) AS {c}" if _sql_type(c) else c for c in df.columns)
        if name == "dim_date":
            cols = cols.replace("full_date", "CAST(full_date AS DATE) AS full_date", 1).replace(
                "month_start", "CAST(month_start AS DATE) AS month_start", 1)
        con.execute(f"CREATE TABLE dw.{name} AS SELECT {cols} FROM frame")
        con.unregister("frame")
    for path in sorted((SQL_DIR / "03_views").glob("*.sql")):
        for stmt in split_statements(path.read_text(encoding="utf-8")):
            con.execute(stmt)
    return con


def view_checks(con) -> pd.DataFrame:
    """Unit 4.01 check: each view's total equals the fact total under the same filter."""
    q = lambda sql: con.execute(sql).fetchone()[0]                   # noqa: E731
    fact_net = q("SELECT SUM(net_amount_pkr) FROM dw.fact_sales WHERE NOT is_cancelled")
    fact_pur = q("SELECT SUM(purchase_amount_pkr) FROM dw.fact_purchase WHERE NOT is_cancelled")
    fact_margin = q("SELECT SUM(gross_margin_pkr) FROM dw.fact_sales WHERE NOT is_cancelled")
    rows = [
        ("vw_sales_enriched net = fact_sales net (not cancelled)", fact_net,
         q("SELECT SUM(net_amount_pkr) FROM dw.vw_sales_enriched")),
        ("vw_sales_product_month net = fact_sales net", fact_net, q("SELECT SUM(net_amount_pkr) FROM dw.vw_sales_product_month")),
        ("vw_sales_product_month margin = fact_sales margin", fact_margin,
         q("SELECT SUM(gross_margin_pkr) FROM dw.vw_sales_product_month")),
        ("vw_purchase_product_month PKR = fact_purchase PKR (not cancelled)", fact_pur,
         q("SELECT SUM(purchase_amount_pkr) FROM dw.vw_purchase_product_month")),
        ("vw_forecast_features net = fact_sales net", fact_net, q("SELECT SUM(net_sales_pkr) FROM dw.vw_forecast_features")),
        ("vw_region_category_month net = fact_sales net", fact_net,
         q("SELECT SUM(net_sales_pkr) FROM dw.vw_region_category_month")),
        ("vw_margin_bridge: volume + price + cost effects = margin change",
         q("SELECT SUM(margin_change_pkr) FROM dw.vw_margin_bridge"),
         q("SELECT SUM(volume_effect_pkr + price_effect_pkr + cost_effect_pkr) FROM dw.vw_margin_bridge")),
        ("vw_region_category_month: complete grid 3 regions x 8 categories x 36 months", 864,
         q("SELECT COUNT(*) FROM dw.vw_region_category_month")),
        ("vw_forecast_features: 36 months", 36, q("SELECT COUNT(*) FROM dw.vw_forecast_features")),
    ]
    out = pd.DataFrame(rows, columns=["check", "expected", "actual"])
    tol = [1.0 if "effects" in c else 0.005 for c in out.check]           # bridge: rounding of 3 terms per row
    out["result"] = ["PASS" if abs(float(e) - float(a)) <= t else "FAIL" for e, a, t in zip(out.expected, out.actual, tol)]
    return out


if __name__ == "__main__":
    con = build_duckdb()
    out = view_checks(con)
    out.to_csv(evidence_dir("02_etl/offline_dry_run") / "view_checks_duckdb.csv", index=False, lineterminator="\n")
    print(out.to_string(index=False))
    con.close()
