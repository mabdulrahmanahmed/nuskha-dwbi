"""Acceptance checks on the loaded warehouse (units 3.02 and 3.03), run as SQL. Synthetic data.

  python -m src.dw_checks dims  --batch 1    # 3.02 special members, unique keys, date range
  python -m src.dw_checks facts --batch 1    # 3.03 fact rows = valid staged rows, keys, Diabetes Care margin

Results go to evidence/03_warehouse/ and etl.validation_result.
"""
from __future__ import annotations

import argparse

import pandas as pd
from sqlalchemy import text

from src.common import get_engine, write_evidence
from src.etl_db import check, record_checks

AREA = "03_warehouse"


def q(sql: str, **params):
    with get_engine("dw").connect() as con:
        return con.execute(text(sql), params).scalar()


def finish(batch_id: int, rows: list, name: str) -> None:
    record_checks(batch_id, rows)
    df = pd.DataFrame(rows)
    write_evidence(AREA, name, df)
    print(df.to_string(index=False, max_colwidth=90))
    fails = int((df.result == "FAIL").sum())
    print(f"\n{len(df) - fails} PASS, {fails} FAIL")
    if fails:
        raise SystemExit(1)


def dims(batch_id: int) -> None:
    rows = []
    for table, key, code, special in (("dim_product", "product_key", "product_code", [-1]),
                                      ("dim_branch", "branch_key", "branch_code", [-1]),
                                      ("dim_customer", "customer_key", "customer_code", [-1, 0]),
                                      ("dim_supplier", "supplier_key", "supplier_code", [-1])):
        n = q(f"SELECT count(*) FROM dw.{table} WHERE {key} IN ({', '.join(map(str, special))})")
        check(rows, f"{table}: special members {special} present", len(special), n, n == len(special))
        d = q(f"SELECT count(*) - count(DISTINCT {code}) FROM dw.{table}")
        check(rows, f"{table}: business key {code} unique", 0, d, d == 0)
        nr = q(f"SELECT count(*) FROM dw.{table} WHERE {code} IS NULL")
        check(rows, f"{table}: no NULL business keys", 0, nr, nr == 0)
    n = q("SELECT count(*) FROM dw.dim_date")
    rng = q("SELECT min(full_date)::text || ' to ' || max(full_date)::text FROM dw.dim_date")
    check(rows, "dim_date: 2023-11-01 to 2027-01-31, one row per day", "1188 rows, 2023-11-01 to 2027-01-31",
          f"{n} rows, {rng}", n == 1188 and rng == "2023-11-01 to 2027-01-31")
    r = q("SELECT count(*) FROM dw.dim_date WHERE is_ramadan")
    check(rows, "dim_date: Ramadan days flagged (3 Ramadans)", 89, r, r == 89)
    fy = q("SELECT fiscal_year || ' Q' || fiscal_quarter FROM dw.dim_date WHERE full_date = '2025-07-01'")
    check(rows, "dim_date: fiscal year Jul-Jun (2025-07-01 is FY2026 Q1)", "FY2026 Q1", fy, fy == "FY2026 Q1")
    w = q("SELECT customer_name FROM dw.dim_customer WHERE customer_key = 0")
    check(rows, "dim_customer: key 0 is the Walk-in member", "Walk-in customer", w, w == "Walk-in customer")
    finish(batch_id, rows, f"dimension_checks_batch_{batch_id}.csv")


def facts(batch_id: int) -> None:
    from src.etl_db import run

    res = run(batch_id)
    rows = []
    for table, part, key in (("fact_sales", res["sales"], "receipt_no"), ("fact_purchase", res["purch"], "grn_no")):
        n = q(f"SELECT count(*) FROM dw.{table} WHERE batch_id <= :b", b=batch_id)
        check(rows, f"{table}: rows = valid staged rows", len(part["valid"]), n, n == len(part["valid"]))
        d = q(f"SELECT count(*) - count(DISTINCT (source_system, {key}, line_no)) FROM dw.{table}")
        check(rows, f"{table}: natural key unique", 0, d, d == 0)
        lin = q(f"SELECT count(*) FROM dw.{table} f LEFT JOIN meta.lineage l ON l.warehouse_table = 'dw.{table}' "
                f"AND l.natural_key = f.source_system || '|' || f.source_key WHERE l.natural_key IS NULL")
        check(rows, f"{table}: every row has a lineage row", 0, lin, lin == 0)
    amt = q("SELECT sum(net_amount_pkr) FROM dw.fact_sales WHERE batch_id <= :b", b=batch_id)
    exp = round(float(res["sales"]["valid"].net_amount_pkr.sum()), 2)
    check(rows, "fact_sales: net amount = valid staged net amount (to the paisa)", exp, float(amt),
          abs(float(amt) - exp) < 0.005)
    mm = q("SELECT count(*) FROM dw.fact_sales WHERE gross_margin_pkr <> net_amount_pkr - cost_amount_pkr")
    check(rows, "fact_sales: gross margin = net - cost on every row", 0, mm, mm == 0)
    unk = q("SELECT round(100.0 * avg((customer_key = -1)::int), 3) FROM dw.fact_sales")
    check(rows, "fact_sales: Unknown customer share below 1%", "< 1", float(unk), float(unk) < 1)
    # Diagnosis story: Diabetes Care margin % falls after the March 2026 cost step-up.
    sql = ("SELECT round(100 * sum(f.gross_margin_pkr) / sum(f.net_amount_pkr), 2) FROM dw.fact_sales f "
           "JOIN dw.dim_product p USING (product_key) WHERE p.category = 'Diabetes Care' AND NOT f.is_cancelled "
           "AND f.date_key BETWEEN :a AND :b")
    pre, post = float(q(sql, a=20250901, b=20260228)), float(q(sql, a=20260301, b=20260831))
    check(rows, "Diabetes Care margin % Mar-Aug 2026 below Sep 2025-Feb 2026 by > 5 points",
          f"{pre} -> lower", post, pre - post > 5)
    with get_engine("dw").connect() as con:
        trend = pd.read_sql(text(
            "SELECT p.category, f.date_key / 100 AS month, sum(f.net_amount_pkr) AS net_pkr, "
            "sum(f.gross_margin_pkr) AS margin_pkr, round(100 * sum(f.gross_margin_pkr) / sum(f.net_amount_pkr), 2) "
            "AS margin_pct FROM dw.fact_sales f JOIN dw.dim_product p USING (product_key) "
            "WHERE NOT f.is_cancelled GROUP BY 1, 2 ORDER BY 1, 2"), con)
    write_evidence(AREA, f"margin_by_category_month_batch_{batch_id}.csv", trend)
    finish(batch_id, rows, f"fact_checks_batch_{batch_id}.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["dims", "facts"])
    ap.add_argument("--batch", type=int, required=True)
    a = ap.parse_args()
    {"dims": dims, "facts": facts}[a.what](a.batch)
