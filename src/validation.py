"""Validation suite: the 11 checks of docs/blueprint.md (unit 3.11). Synthetic data, seed 472.

Each check is saved with expected, actual and PASS / FAIL in etl.validation_result and in
evidence/05_validation/validation_results.csv. Checks 5, 9 and 10 read the results their units
already proved (reconciliation, rerun, SCD1) and confirm them; the others are computed here.
Check 11 (AI outputs after a retried run) needs the AI tables; until phase 4 has filled them it is
reported as NOT RUN, and the suite is run again in the final audit (5.09).

  python -m src.validation
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from src.common import evidence_dir, get_engine, write_evidence

AREA = "05_validation"


def q(engine: str, sql: str, **p):
    with get_engine(engine).connect() as con:
        if engine == "purchasing":
            con.execute(text("SET TIME ZONE 'Asia/Karachi'"))
        return pd.read_sql(text(sql), con, params=p)


def v(sql: str, **p):
    return q("dw", sql, **p).iloc[0, 0]


def run() -> pd.DataFrame:
    rows = []

    def add(no, name, expected, actual, ok):
        rows.append({"no": no, "check": name, "expected": expected, "actual": actual,
                     "result": ok if isinstance(ok, str) else ("PASS" if ok else "FAIL")})

    # 1 Grain uniqueness
    for t, k in (("fact_sales", "receipt_no"), ("fact_purchase", "grn_no")):
        d = int(v(f"SELECT count(*) - count(DISTINCT (source_system, {k}, line_no)) FROM dw.{t}"))
        add(1, f"grain: duplicate natural keys in dw.{t}", 0, d, d == 0)
    # 2 Foreign keys
    for t, dims in (("fact_sales", ["date", "product", "branch", "customer"]),
                    ("fact_purchase", ["date", "product", "branch", "supplier"])):
        n = sum(int(v(f"SELECT count(*) FROM dw.{t} f LEFT JOIN dw.dim_{d} x USING ({d}_key) "
                      f"WHERE x.{d}_key IS NULL")) for d in dims)
        add(2, f"foreign keys: orphan keys in dw.{t} ({', '.join(dims)})", 0, n, n == 0)
    # 3 Unknown members
    for t, keys in (("fact_sales", ["product", "branch", "customer"]), ("fact_purchase", ["product", "branch", "supplier"])):
        total = int(v(f"SELECT count(*) FROM dw.{t}"))
        for k in keys:
            n = int(v(f"SELECT count(*) FROM dw.{t} WHERE {k}_key = -1"))
            share = round(100 * n / total, 3)
            add(3, f"unknown members: dw.{t}.{k}_key = -1 (count, share %)", "< 1%", f"{n} rows, {share}%", share < 1)
    # 4 Completeness
    for t in ("fact_sales", "fact_purchase"):
        m = int(v(f"SELECT count(DISTINCT date_key / 100) FROM dw.{t}"))
        add(4, f"completeness: months present in dw.{t} (Nov 2023 - Oct 2026)", 36, m, m == 36)
    gaps = q("dw", "SELECT b.branch_code, d.month_start FROM dw.dim_branch b CROSS JOIN "
                   "(SELECT DISTINCT month_start FROM dw.dim_date WHERE full_date BETWEEN '2023-11-01' AND '2026-10-31') d "
                   "WHERE b.branch_key > 0 AND NOT EXISTS (SELECT 1 FROM dw.fact_sales f JOIN dw.dim_date x USING (date_key) "
                   "WHERE f.branch_key = b.branch_key AND x.month_start = d.month_start)")
    add(4, "completeness: every branch has sales every month (10 branches x 36 months)", 0, len(gaps), len(gaps) == 0)
    # 5 Row reconciliation (per table and batch, from unit 2.09 and the batch-2 run)
    for b in (1, 2):
        rec = pd.read_csv(evidence_dir("02_etl") / f"reconciliation_batch_{b}.csv")
        for r in rec.itertuples():
            add(5, f"row reconciliation batch {b} {r.table}: source = loaded + rejected + duplicates", r.source_rows,
                r.staged_valid + r.rejected + r.duplicates_removed, bool(r.balanced))
    # 6 Amount reconciliation: source (now) vs warehouse per month
    src = q("sales", "SELECT l.receipt_no, l.line_no, DATE_FORMAT(r.receipt_ts, '%Y%m') AS month, "
                     "l.qty * l.unit_price_pkr - COALESCE(l.discount_pkr, 0) AS net "
                     "FROM receipt_line l JOIN receipt r USING (receipt_no) "
                     "WHERE r.receipt_ts <= '2026-10-31 23:59:59'")
    src["source_key"] = src.receipt_no + "|" + src.line_no.astype(str)
    fact = q("dw", "SELECT source_key, receipt_no, (date_key / 100)::text AS month, net_amount_pkr FROM dw.fact_sales")
    rejected = set(q("dw", "SELECT source_key FROM etl.rejects WHERE source_table = 'receipt_line'").source_key)
    deleted = set(q("dw", "SELECT source_key FROM etl.deletion_log").source_key)
    keep = ~src.source_key.isin(rejected - set(fact.source_key))
    s_m = src[keep].groupby("month").net.sum().astype(float)
    d_m = fact[fact.receipt_no.isin(deleted)].groupby("month").net_amount_pkr.sum().astype(float)
    f_m = fact.groupby("month").net_amount_pkr.sum().astype(float)
    cmp = pd.DataFrame({"source_valid_pkr": s_m, "deleted_kept_pkr": d_m, "warehouse_pkr": f_m}).fillna(0).round(2)
    cmp["difference"] = (cmp.source_valid_pkr + cmp.deleted_kept_pkr - cmp.warehouse_pkr).round(2)
    write_evidence(AREA, "amount_reconciliation_sales_by_month.csv", cmp.reset_index(names="month"))
    bad = int((cmp.difference.abs() > 0.005).sum())
    add(6, "amounts: MySQL valid lines (+ deleted receipts kept) = fact_sales, per month", f"0 of {len(cmp)} months differ",
        f"{bad} months differ", bad == 0)
    psrc = q("purchasing", "SELECT g.grn_no || '|' || g.line_no AS source_key, to_char(gr.received_at, 'YYYYMM') AS month, "
                           "g.boxes_received * g.cost_per_box AS amount FROM grn_line g JOIN goods_receipt gr USING (grn_no) "
                           "WHERE gr.received_at <= '2026-10-31 23:59:59'")
    pfact = q("dw", "SELECT source_key, (date_key / 100)::text AS month, amount_original FROM dw.fact_purchase")
    prej = set(q("dw", "SELECT source_key FROM etl.rejects WHERE source_table = 'grn_line'").source_key)
    pk = ~psrc.source_key.isin(prej - set(pfact.source_key))
    pc = pd.DataFrame({"source_valid": psrc[pk].groupby("month").amount.sum().astype(float),
                       "warehouse": pfact.groupby("month").amount_original.sum().astype(float)}).fillna(0).round(2)
    pc["difference"] = (pc.source_valid - pc.warehouse).round(2)
    write_evidence(AREA, "amount_reconciliation_purchases_by_month.csv", pc.reset_index(names="month"))
    bad = int((pc.difference.abs() > 0.005).sum())
    add(6, "amounts: PostgreSQL valid GRN lines = fact_purchase (original currency), per month",
        f"0 of {len(pc)} months differ", f"{bad} months differ", bad == 0)
    # 7 Join safety
    for t, dims, m in (("fact_sales", ["date", "product", "branch", "customer"], "net_amount_pkr"),
                       ("fact_purchase", ["date", "product", "branch", "supplier"], "purchase_amount_pkr")):
        a = float(v(f"SELECT sum({m}) FROM dw.{t}"))
        joins = " ".join(f"JOIN dw.dim_{d} USING ({d}_key)" for d in dims)
        b = float(v(f"SELECT sum({m}) FROM dw.{t} {joins}"))
        add(7, f"join safety: dw.{t} total before = after joining every dimension", round(a, 2), round(b, 2),
            abs(a - b) < 0.005)
    # 8 Lineage coverage
    for t in ("fact_sales", "fact_purchase"):
        pct = float(v(f"SELECT round(100.0 * count(l.natural_key) / count(*), 2) FROM dw.{t} f LEFT JOIN meta.lineage l "
                      f"ON l.warehouse_table = 'dw.{t}' AND l.natural_key = f.source_system || '|' || f.source_key "
                      f"WHERE f.source_system IS NOT NULL AND f.source_key IS NOT NULL AND f.batch_id IS NOT NULL"))
        add(8, f"lineage: % of dw.{t} rows with source system, key and batch", 100, pct, pct == 100)
    # 9 Rerun safety (3.04 and the rerun after the controlled failure, 3.07)
    for f, label in (("rerun_checks.csv", "3.04 rerun of batch 1"), ("failure_checks.csv", "3.07 rerun after failure")):
        c = pd.read_csv(evidence_dir("03_warehouse") / f)
        add(9, f"rerun safety: {label} (rows and totals changed)", "all PASS",
            f"{(c.result == 'PASS').sum()}/{len(c)} PASS", (c.result == "PASS").all())
    # 10 SCD Type 1
    c = pd.read_csv(evidence_dir("03_warehouse") / "scd1_checks.csv")
    s = pd.read_csv(evidence_dir("03_warehouse") / "scd1_evidence.csv")
    comp = float(s.loc[s.category == "Company total", "net_change"].iloc[0])
    add(10, "SCD1: Gastro and Cough and Cold move; company total unchanged", "2 categories move, 0.00",
        f"{int((s.net_change.abs() > 0.005).sum())} categories move, {comp:.2f}", (c.result == "PASS").all())
    # 11 AI outputs
    runs = int(v("SELECT count(*) FROM ai.model_run"))
    if runs == 0:
        add(11, "AI outputs: duplicate rows after a retried run", 0, "AI tables empty until phase 4", "NOT RUN")
    else:
        d1 = int(v("SELECT count(*) - count(DISTINCT (run_id, date_key)) FROM ai.forecast_result"))
        d2 = int(v("SELECT count(*) - count(DISTINCT (run_id, date_key, region, category, method, is_injected_copy)) "
                   "FROM ai.anomaly_result"))
        add(11, "AI outputs: duplicate rows after a retried run (forecast + anomaly)", 0, d1 + d2, d1 + d2 == 0)
    return pd.DataFrame(rows)


def main() -> pd.DataFrame:
    from src.etl_db import record_checks

    out = run()
    write_evidence(AREA, "validation_results.csv", out)
    last = int(v("SELECT max(batch_id) FROM etl.batch WHERE status = 'SUCCESS'"))
    done = out[out.result != "NOT RUN"]
    record_checks(last, [{"check": f"V{r.no:02d} {r.check}", "expected": r.expected, "actual": r.actual,
                          "result": r.result} for r in done.itertuples()])
    pd.set_option("display.width", 230)
    print(out.to_string(index=False, max_colwidth=95))
    print(f"\n{(out.result == 'PASS').sum()} PASS, {(out.result == 'FAIL').sum()} FAIL, "
          f"{(out.result == 'NOT RUN').sum()} NOT RUN")
    if (out.result == "FAIL").any():
        raise SystemExit(1)
    return out


if __name__ == "__main__":
    main()
