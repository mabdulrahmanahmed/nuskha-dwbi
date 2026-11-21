"""Batch behaviour tests on the warehouse (units 3.04-3.07). Synthetic data, seed 472.

  python -m src.batch_tests rerun      # 3.04 load batch 1 again: nothing may change
  python -m src.batch_tests batch2     # 3.05 stage-2 sources -> extract by watermark -> load; deletions
  python -m src.batch_tests scd1       # 3.06 category totals before / after the cough-syrup fix
  python -m src.batch_tests failure    # 3.07 FAIL_AT=0.5 rolls back; the rerun equals a clean run

Evidence: evidence/03_warehouse/*.csv and etl.validation_result.
"""
from __future__ import annotations

import sys

import pandas as pd
from sqlalchemy import text

from src.common import ROOT, evidence_dir, get_engine, log_stage, write_evidence
from src.etl_db import check, record_checks
from src.load_db import load, new_batch, warehouse_totals

AREA = "03_warehouse"
SNAP = ROOT / "data" / "snapshots"          # git-ignored working copies used by the before/after checks
CUT2 = "2026-10-31 23:59:59"


def finish(batch_id, rows: list, name: str) -> None:
    record_checks(batch_id, rows)
    df = pd.DataFrame(rows)
    write_evidence(AREA, name, df)
    print(df.to_string(index=False, max_colwidth=100))
    fails = int((df.result == "FAIL").sum())
    print(f"\n{len(df) - fails} PASS, {fails} FAIL")
    if fails:
        raise SystemExit(1)


def _fingerprint_dims_fixed() -> dict:
    """md5 of every row of the stars and of meta.lineage (facts ordered by source key, dims by key)."""
    out = {}
    with get_engine("dw").connect() as con:
        for t, order in (("fact_sales", "source_key"), ("fact_purchase", "source_key"), ("dim_product", "product_key"),
                         ("dim_customer", "customer_key"), ("dim_branch", "branch_key"),
                         ("dim_supplier", "supplier_key")):
            out[t] = con.execute(text(f"SELECT md5(string_agg(row_to_json(x)::text, '' ORDER BY x.{order})) "
                                      f"FROM dw.{t} x")).scalar()
        out["meta.lineage"] = con.execute(text(
            "SELECT md5(string_agg(natural_key || batch_id, '' ORDER BY natural_key)) FROM meta.lineage")).scalar()
    return out


# ---------------------------------------------------------------------------
# 3.04 Rerun of batch 1 on unchanged input
# ---------------------------------------------------------------------------
def rerun() -> None:
    from src.etl_db import crosswalk, quality

    before_t, before_f = warehouse_totals(), _fingerprint_dims_fixed()
    with get_engine("dw").connect() as con:
        rej_before = con.execute(text("SELECT count(*) FROM etl.rejects")).scalar()
    for step in (crosswalk, quality):          # the staging-side upserts again
        try:
            step(1)
        except SystemExit:
            pass
    log = load(1)                              # dimensions and facts again
    after_t, after_f = warehouse_totals(), _fingerprint_dims_fixed()
    with get_engine("dw").connect() as con:
        rej_after = con.execute(text("SELECT count(*) FROM etl.rejects")).scalar()
    rows, out = [], []
    for k in before_t:
        out.append({"measure": k, "before_rerun": before_t[k], "after_rerun": after_t[k],
                    "changed": before_t[k] != after_t[k]})
    for k in before_f:
        out.append({"measure": f"md5 of {k}", "before_rerun": before_f[k], "after_rerun": after_f[k],
                    "changed": before_f[k] != after_f[k]})
    out.append({"measure": "etl.rejects rows", "before_rerun": rej_before, "after_rerun": rej_after,
                "changed": rej_before != rej_after})
    for r in log.itertuples():
        out.append({"measure": f"{r.table}: rows inserted + updated by the rerun", "before_rerun": 0,
                    "after_rerun": r.inserted + r.updated, "changed": (r.inserted + r.updated) != 0})
    df = pd.DataFrame(out)
    write_evidence(AREA, "rerun_log.csv", df)
    check(rows, "rerun of batch 1: 0 rows written by the load", 0, int(log.inserted.sum() + log.updated.sum()),
          int(log.inserted.sum() + log.updated.sum()) == 0)
    check(rows, "rerun of batch 1: totals and table fingerprints unchanged", 0, int(df.changed.sum()),
          not df.changed.any())
    finish(1, rows, "rerun_checks.csv")


# ---------------------------------------------------------------------------
# 3.05 Batch 2
# ---------------------------------------------------------------------------
def batch2() -> None:
    from src import etl_db
    from src.extract import run_extract

    SNAP.mkdir(parents=True, exist_ok=True)
    # Before batch 2: keep copies of dim_product and fact_sales for the SCD1 and deletion checks.
    with get_engine("dw").connect() as con:
        done = con.execute(text("SELECT count(*) FROM etl.batch WHERE batch_id = 2")).scalar()
        if not done:
            pd.read_sql(text("SELECT * FROM dw.dim_product ORDER BY product_key"), con).to_csv(
                evidence_dir(AREA) / "dim_product_before_batch_2.csv", index=False, lineterminator="\n")
            pd.read_sql(text("SELECT source_key, product_key, date_key, net_amount_pkr, gross_margin_pkr, "
                             "is_cancelled, batch_id FROM dw.fact_sales"), con).to_csv(
                SNAP / "fact_sales_before_batch_2.csv", index=False, lineterminator="\n")
    if not done:
        import subprocess
        subprocess.run([sys.executable, "-m", "src.load_sources", "--stage", "2"], check=True, cwd=ROOT)
        run_extract(pd.Timestamp(CUT2).to_pydatetime(), ROOT / "data" / "generated" / "stage2" / "double_export.csv")
    for step in ("profile_before", "stage", "profile_after", "crosswalk", "prejoin", "quality", "reconcile"):
        print(f"--- {step} (batch 2)")
        getattr(etl_db, step)(2)
    load(2)

    # Deletion check: receipts in the warehouse whose key no longer exists in the source.
    with get_engine("sales").connect() as con:
        source_keys = set(con.execute(text("SELECT receipt_no FROM receipt")).scalars())
    with get_engine("dw").begin() as con:
        dw_keys = set(con.execute(text("SELECT DISTINCT receipt_no FROM dw.fact_sales")).scalars())
        gone = sorted(dw_keys - source_keys)
        for k in gone:
            con.execute(text("INSERT INTO etl.deletion_log (batch_id, source_system, source_table, source_key, note) "
                             "VALUES (2, 'sales_db', 'receipt', :k, 'key missing from source; warehouse rows kept') "
                             "ON CONFLICT (source_system, source_table, source_key) DO NOTHING"), {"k": k})
        kept = con.execute(text("SELECT count(*) FROM dw.fact_sales WHERE receipt_no = ANY(:k)"), {"k": gone}).scalar()
        logged = con.execute(text("SELECT count(*) FROM etl.deletion_log")).scalar()
    log_stage("deletion_check", "sales_db.receipt", rows_in=len(dw_keys), rows_out=len(gone), batch_id=2, area=AREA)
    write_evidence(AREA, "deletion_log_batch_2.csv", pd.DataFrame({"receipt_no": gone}))

    intended = pd.read_csv(evidence_dir("01_sources") / "stage2_intended_changes.csv", dtype=str)
    planned = sorted(intended.key[(intended.table == "receipt") & (intended.change == "deleted")])
    before = pd.read_csv(SNAP / "fact_sales_before_batch_2.csv", dtype={"source_key": str})
    rows = []
    check(rows, "deleted receipts found by key comparison = the 3 planted deletions", planned, gone, gone == planned)
    check(rows, "deletions logged in etl.deletion_log", 3, logged, logged == 3)
    check(rows, "deleted receipts' rows kept in fact_sales (none removed)", "> 0", kept, kept > 0)
    with get_engine("dw").connect() as con:
        q = lambda s, **p: con.execute(text(s), p).scalar()  # noqa: E731
        late = q("SELECT count(DISTINCT receipt_no) FROM dw.fact_sales WHERE batch_id = 2 AND date_key < 20260901 "
                 "AND NOT (receipt_no = ANY(:old))", old=list(set(before.source_key.str.split('|').str[0])))
        late_months = q("SELECT string_agg(DISTINCT (date_key / 100)::text, ', ') FROM dw.fact_sales WHERE batch_id = 2 "
                        "AND date_key < 20260901 AND NOT (receipt_no = ANY(:old))",
                        old=list(set(before.source_key.str.split('|').str[0])))
        updated = q("SELECT count(*) FROM dw.fact_sales WHERE batch_id = 2 AND source_key = ANY(:k)",
                    k=before.source_key.tolist())
        voided = q("SELECT count(*) FROM dw.fact_sales WHERE is_cancelled")
        cancelled_grn = q("SELECT count(*) FROM dw.fact_purchase WHERE is_cancelled")
        p500 = q("SELECT count(*) FROM dw.fact_sales WHERE product_key = 500")
        p500_dim = q("SELECT product_code FROM dw.dim_product WHERE product_key = 500")
        batches = q("SELECT string_agg(batch_id || ':' || status, ', ' ORDER BY batch_id) FROM etl.batch")
        wm = q("SELECT watermark_from::text FROM etl.batch WHERE batch_id = 2")
    # Lines whose warehouse values change: corrected quantities, voids, and every line of a receipt whose
    # panel customer was corrected (new customer_key). Other lines of a re-saved receipt only get a new
    # updated_at; the upsert must leave those rows untouched.
    lines = intended[(intended.table == "receipt_line") & (intended.change == "changed")]
    panel_receipts = set(intended.key[intended.reason == "panel customer corrected"])
    value_change = lines.reason.isin(["quantity corrected", "receipt VOIDED (re-saved)"]) | \
        lines.key.str.split("|").str[0].isin(panel_receipts)
    n_changed = int(value_change.sum())
    with get_engine("dw").connect() as con:
        untouched = con.execute(text("SELECT count(*) FROM dw.fact_sales WHERE batch_id = 1 AND source_key = ANY(:k)"),
                                {"k": lines.key[~value_change].tolist()}).scalar()
    n_void = int((intended.reason == "receipt VOIDED (re-saved)").sum())
    n_grn_cancel = int((intended.reason == "GRN CANCELLED (re-saved)").sum())
    check(rows, "batch 2 extracted by watermark (from = batch 1 cut-off)", "2026-08-31 23:59:59", wm,
          wm == "2026-08-31 23:59:59")
    check(rows, "late receipts loaded into their real month (Jul-Aug 2026)", "40 receipts", f"{late} receipts in {late_months}",
          late == 40 and set(late_months.split(", ")) <= {"202607", "202608"})
    check(rows, "stage-1 lines with a value change updated in place (qty fixes, panel fixes, voids)", n_changed,
          updated, updated == n_changed)
    check(rows, "re-saved lines with no value change left untouched (still batch 1)", int((~value_change).sum()),
          untouched, untouched == int((~value_change).sum()))
    check(rows, "VOIDED receipt lines flagged is_cancelled (kept, not deleted)", n_void, voided, voided == n_void)
    views = sorted(p.name for p in (ROOT / "sql" / "03_views").glob("0[1-3]*.sql")
                   if "NOT f.is_cancelled" in p.read_text(encoding="utf-8"))
    check(rows, "cancelled lines excluded from the sales/purchase views (WHERE NOT f.is_cancelled; counted in 4.01)",
          3, len(views), len(views) == 3)
    check(rows, "CANCELLED GRN lines flagged in fact_purchase", n_grn_cancel, cancelled_grn,
          cancelled_grn == n_grn_cancel)
    check(rows, "new product P-0500 in dim_product and in facts (late-arriving dimension)", "P-0500 with rows",
          f"{p500_dim} with {p500} rows", p500_dim == "P-0500" and p500 > 0)
    check(rows, "etl.batch: batches 1 and 2 SUCCESS", "1:SUCCESS, 2:SUCCESS", batches,
          batches.startswith("1:SUCCESS, 2:SUCCESS"))
    finish(2, rows, "batch2_checks.csv")


# ---------------------------------------------------------------------------
# 3.06 SCD Type 1
# ---------------------------------------------------------------------------
def scd1() -> None:
    before_dim = pd.read_csv(evidence_dir(AREA) / "dim_product_before_batch_2.csv")
    with get_engine("dw").connect() as con:
        facts = pd.read_sql(text("SELECT source_key, product_key, date_key, net_amount_pkr, gross_margin_pkr, batch_id "
                                 "FROM dw.fact_sales WHERE NOT is_cancelled"), con)
        after_dim = pd.read_sql(text("SELECT product_key, product_code, generic_name, category FROM dw.dim_product"), con)
    cat_before = after_dim.set_index("product_key").category.copy()        # new products keep their category
    cat_before.update(before_dim.set_index("product_key").category)
    cat_after = after_dim.set_index("product_key").category
    t = pd.DataFrame({
        "net_before_fix": facts.groupby(facts.product_key.map(cat_before)).net_amount_pkr.sum(),
        "net_after_fix": facts.groupby(facts.product_key.map(cat_after)).net_amount_pkr.sum(),
        "margin_before_fix": facts.groupby(facts.product_key.map(cat_before)).gross_margin_pkr.sum(),
        "margin_after_fix": facts.groupby(facts.product_key.map(cat_after)).gross_margin_pkr.sum()}).fillna(0).round(2)
    t["net_change"] = (t.net_after_fix - t.net_before_fix).round(2)
    t.loc["Company total"] = t.sum().round(2)
    t = t.reset_index(names="category")
    changed = before_dim.merge(after_dim, on="product_key", suffixes=("_before", "_after"))
    changed = changed[changed.category_before != changed.category_after][
        ["product_key", "product_code_after", "generic_name_after", "category_before", "category_after"]]
    write_evidence(AREA, "scd1_evidence.csv", t)
    write_evidence(AREA, "scd1_changed_products.csv", changed)
    # Past margins: stored margins of rows not touched by batch 2 are identical to before batch 2.
    snap = pd.read_csv(SNAP / "fact_sales_before_batch_2.csv", dtype={"source_key": str})
    m = snap.merge(facts[facts.batch_id == 1], on="source_key", suffixes=("_b", "_a"))
    margin_diff = int((m.gross_margin_pkr_b.round(2) != m.gross_margin_pkr_a.round(2)).sum())
    past = facts[facts.date_key < 20260901]
    month_b = past.groupby(past.date_key // 100).gross_margin_pkr.sum().round(2)
    rows = []
    moved = sorted(t.category[(t.category != "Company total") & (t.net_change.abs() > 0.005)])
    check(rows, "SCD1: exactly two category totals move (Gastro, Cough and Cold)", ["Cough and Cold", "Gastro"], moved,
          moved == ["Cough and Cold", "Gastro"])
    comp = float(t.loc[t.category == "Company total", "net_change"].iloc[0])
    check(rows, "SCD1: company total unchanged", 0.0, comp, abs(comp) < 0.005)
    check(rows, "SCD1: one product changed category (overwritten, no history row)", 1, len(changed), len(changed) == 1)
    check(rows, "SCD1: stored margins of untouched batch-1 rows unchanged", 0, margin_diff, margin_diff == 0)
    write_evidence(AREA, "scd1_company_margin_by_month.csv", month_b.rename_axis("month").reset_index())
    finish(2, rows, "scd1_checks.csv")


# ---------------------------------------------------------------------------
# 3.07 Controlled failure
# ---------------------------------------------------------------------------
def failure() -> None:
    clean_t, clean_f = warehouse_totals(), _fingerprint_dims_fixed()
    b_fail = new_batch(2, "controlled failure test (FAIL_AT=0.5)")
    error = ""
    try:
        load(2, b_fail, fail_at=0.5)
    except RuntimeError as exc:
        error = str(exc)
    mid_t, mid_f = warehouse_totals(), _fingerprint_dims_fixed()
    with get_engine("dw").connect() as con:
        status = con.execute(text("SELECT status FROM etl.batch WHERE batch_id = :b"), {"b": b_fail}).scalar()
    b_rerun = new_batch(2, "rerun after controlled failure")
    log = load(2, b_rerun)
    end_t, end_f = warehouse_totals(), _fingerprint_dims_fixed()
    out = [{"measure": k, "clean_run": clean_t[k], "after_failure": mid_t[k], "after_rerun": end_t[k]} for k in clean_t]
    out += [{"measure": f"md5 of {k}", "clean_run": clean_f[k], "after_failure": mid_f[k], "after_rerun": end_f[k]}
            for k in clean_f]
    df = pd.DataFrame(out)
    df["unchanged"] = (df.clean_run == df.after_failure) & (df.clean_run == df.after_rerun)
    write_evidence(AREA, "failure_log.csv", pd.concat([df, pd.DataFrame([
        {"measure": "error raised", "clean_run": "", "after_failure": error, "after_rerun": "", "unchanged": True},
        {"measure": "failed batch status", "clean_run": "", "after_failure": f"batch {b_fail}: {status}",
         "after_rerun": f"batch {b_rerun}: SUCCESS", "unchanged": True}])]))
    rows = []
    check(rows, "FAIL_AT=0.5 raised an error halfway through a fact load", "error", error[:60] or "none",
          error.startswith("FAIL_AT"))
    check(rows, "failed batch recorded as FAILED in etl.batch", "FAILED", status, status == "FAILED")
    check(rows, "rollback: totals and fingerprints unchanged after the failure", 0,
          int((df.clean_run != df.after_failure).sum()), (df.clean_run == df.after_failure).all())
    check(rows, "rerun after the failure matches the clean run", 0, int((df.clean_run != df.after_rerun).sum()),
          (df.clean_run == df.after_rerun).all())
    check(rows, "rerun wrote 0 rows (input unchanged)", 0, int(log.inserted.sum() + log.updated.sum()),
          int(log.inserted.sum() + log.updated.sum()) == 0)
    finish(b_rerun, rows, "failure_checks.csv")


if __name__ == "__main__":
    {"rerun": rerun, "batch2": batch2, "scd1": scd1, "failure": failure}[sys.argv[1]]()
