"""Database run of the ETL for one batch (units 2.03-2.09). Synthetic data, seed 472.

The cleaning logic lives in the pure-pandas modules (normalize, crosswalk, quality), which
were first tested in the offline dry run. This file runs them on the raw snapshot that
src/extract.py wrote for a batch, and writes the results to the warehouse and to evidence:

  python -m src.etl_db profile-before --batch 1   # 2.03  evidence/02_etl/profile_before[_batch_N].csv
  python -m src.etl_db stage          --batch 1   # 2.04  stg.<table> (typed columns, NUMERIC money)
  python -m src.etl_db profile-after  --batch 1   # 2.05  profile_after + profile_before_after
  python -m src.etl_db crosswalk      --batch 1   # 2.06  stg.xw_product / xw_branch / xw_customer
  python -m src.etl_db prejoin        --batch 1   # 2.07  key uniqueness + join row counts -> etl.validation_result
  python -m src.etl_db quality        --batch 1   # 2.08  etl.rejects, duplicates, compared with the defect ledger
  python -m src.etl_db reconcile      --batch 1   # 2.09  source = staged + rejected + duplicates (rows, amounts/month)

Staging is rebuilt from the raw snapshots, which are never edited: header tables (receipt,
goods_receipt, purchase_order) are cumulative over all batches up to this one, because a
September goods receipt can belong to an August purchase order.
"""
from __future__ import annotations

import argparse

import pandas as pd
from sqlalchemy import Numeric, text

from src.common import evidence_dir, get_engine, log_stage, write_evidence
from src.crosswalk import build_crosswalks, crosswalk_checks
from src.normalize import STAGING_OF, normalize
from src.profile import compare, profile_tables
from src.quality import accumulate, prepare_purchases, prepare_sales
from src.raw import read_raw

AREA = "02_etl"
LEDGER_OF = {1: "defect_ledger.csv", 2: "defect_ledger_stage2.csv"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def batch_cutoff(batch_id: int) -> pd.Timestamp:
    """watermark_to of the batch = the cut-off used by the R03 date rule."""
    with get_engine("dw").connect() as con:
        wm = con.execute(text("SELECT watermark_to FROM etl.batch WHERE batch_id = :b"), {"b": batch_id}).scalar()
    if wm is None:
        raise SystemExit(f"batch {batch_id} not found in etl.batch: run src.extract first")
    return pd.Timestamp(wm)


def staged(batch_id: int) -> dict:
    """Normalized staging for this batch; header tables accumulate over earlier batches."""
    stg = None
    for b in range(1, batch_id + 1):
        stg = accumulate(normalize(read_raw(b)), stg)
    return stg


def run(batch_id: int) -> dict:
    """Everything the quality step needs: staging, crosswalks, valid / rejected / duplicate rows."""
    stg = staged(batch_id)
    xw = build_crosswalks(stg)
    cut = batch_cutoff(batch_id)
    return {"stg": stg, "xw": xw, "cutoff": cut,
            "sales": prepare_sales(stg, xw, cut, batch_id), "purch": prepare_purchases(stg, xw, cut, batch_id)}


def suffix(batch_id: int) -> str:
    return "" if batch_id == 1 else f"_batch_{batch_id}"


def record_checks(batch_id: int, rows: list) -> pd.DataFrame:
    """Write checks to etl.validation_result (a rerun replaces the same check names) and return them."""
    df = pd.DataFrame(rows)
    df["passed"] = df.result.eq("PASS")
    with get_engine("dw").begin() as con:
        for r in df.itertuples():
            con.execute(text("DELETE FROM etl.validation_result WHERE batch_id = :b AND check_name = :c"),
                        {"b": batch_id, "c": r.check})
            con.execute(text("INSERT INTO etl.validation_result (batch_id, check_name, expected, actual, passed) "
                             "VALUES (:b, :c, :e, :a, :p)"),
                        {"b": batch_id, "c": r.check, "e": str(r.expected), "a": str(r.actual), "p": bool(r.passed)})
    return df


def check(rows: list, name: str, expected, actual, ok) -> None:
    rows.append({"check": name, "expected": expected, "actual": actual, "result": "PASS" if ok else "FAIL"})


def finish(df: pd.DataFrame, filename: str) -> None:
    write_evidence(AREA, filename, df)
    pd.set_option("display.width", 220)
    print(df.to_string(index=False, max_colwidth=90))
    fails = int((df.result == "FAIL").sum()) if "result" in df else 0
    print(f"\n{len(df) - fails} PASS, {fails} FAIL")
    if fails:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# 2.03 / 2.05 Profiles
# ---------------------------------------------------------------------------
def profile_before(batch_id: int) -> None:
    raw = read_raw(batch_id)
    prof = profile_tables(raw, "before (raw)")
    write_evidence(AREA, f"profile_before{suffix(batch_id)}.csv", prof)
    log_stage("profile_before", "all source tables", rows_in=len(raw), rows_out=len(prof), batch_id=batch_id)
    rows = []
    check(rows, "profile_before covers every source table", 17, prof.table.nunique(), prof.table.nunique() == 17)
    finish(pd.DataFrame(rows), f"profile_before_checks{suffix(batch_id)}.csv")


def profile_after(batch_id: int) -> None:
    before = pd.read_csv(evidence_dir(AREA) / f"profile_before{suffix(batch_id)}.csv", dtype=str)
    for c in ("rows", "nulls", "distinct"):
        before[c] = before[c].astype(int)
    stg = staged(batch_id)
    after = profile_tables({("stg", k): v.drop(columns=["raw_json"], errors="ignore") for k, v in stg.items()},
                           "after (staged)")
    write_evidence(AREA, f"profile_after{suffix(batch_id)}.csv", after)
    pairs = compare(before, after, STAGING_OF)
    write_evidence(AREA, f"profile_before_after{suffix(batch_id)}.csv", pairs)
    log_stage("profile_after", "all staged tables", rows_in=len(stg), rows_out=len(after), batch_id=batch_id)
    rows = []
    check(rows, "profile_before_after has a before/after pair per table", 34, len(pairs), len(pairs) == 34)
    finish(pd.DataFrame(rows), f"profile_after_checks{suffix(batch_id)}.csv")


# ---------------------------------------------------------------------------
# 2.04 Staging tables
# ---------------------------------------------------------------------------
def _sql_types(df: pd.DataFrame) -> dict:
    """Float columns become NUMERIC: rates with 4 decimals, money and quantities with 2."""
    out = {}
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            out[c] = Numeric(10, 4) if c in ("usd_pkr", "fx_rate_used") else Numeric(14, 2)
    return out


def stage(batch_id: int) -> None:
    stg = staged(batch_id)
    eng = get_engine("dw")
    with eng.begin() as con:
        for name, df in stg.items():
            df.to_sql(name, con, schema="stg", if_exists="replace", index=False, dtype=_sql_types(df),
                      method="multi", chunksize=2000)
            con.execute(text(f"COMMENT ON TABLE stg.{name} IS "
                             f"'Staged (normalized) copy, batch {batch_id}; synthetic data'"))
    for name, df in stg.items():
        log_stage("normalize", f"stg.{name}", rows_in=len(df), rows_out=len(df), batch_id=batch_id)

    rows = []
    with eng.connect() as con:
        cols = pd.read_sql(text("SELECT table_name, column_name, data_type FROM information_schema.columns "
                                "WHERE table_schema = 'stg' AND table_name NOT LIKE 'xw\\_%'"), con)
        cats = con.execute(text("SELECT count(*) FROM stg.item WHERE category NOT IN ('Analgesics','Antibiotics',"
                                "'Cardiovascular','Diabetes Care','Gastro','Cough and Cold',"
                                "'Vitamins and Supplements','Personal Care')")).scalar()
    write_evidence(AREA, f"stg_column_types{suffix(batch_id)}.csv", cols)
    datey = cols.column_name.str.endswith(("_ts", "_date", "_at", "_from", "_on", "_updated")) | \
        cols.column_name.isin(["month_start"])
    text_dates = cols[datey & cols.data_type.isin(["text", "character varying"])]
    floats = cols[cols.data_type.isin(["double precision", "real"])]
    check(rows, "stg tables written", len(stg), cols.table_name.nunique(), cols.table_name.nunique() == len(stg))
    check(rows, "no text date columns in stg", 0, len(text_dates), len(text_dates) == 0)
    check(rows, "no float (double/real) columns in stg: money is NUMERIC", 0, len(floats), len(floats) == 0)
    check(rows, "Inventory categories all canonical (8 names or 'Not recorded')", 0, cats, cats == 0)
    record_checks(batch_id, rows)
    finish(pd.DataFrame(rows), f"stage_checks{suffix(batch_id)}.csv")


# ---------------------------------------------------------------------------
# 2.06 Crosswalks
# ---------------------------------------------------------------------------
def crosswalk(batch_id: int) -> None:
    xw = build_crosswalks(staged(batch_id))
    with get_engine("dw").begin() as con:
        for name, df in xw.items():
            for r in df.itertuples():
                # Upsert on the source key; batch_id only changes when the mapping itself changes.
                con.execute(text(
                    f"INSERT INTO stg.{name} (source_system, source_object, source_key, canonical_code, "
                    f"match_method, batch_id) VALUES (:s, :o, :k, :c, :m, :b) "
                    f"ON CONFLICT (source_system, source_object, source_key) DO UPDATE SET "
                    f"canonical_code = EXCLUDED.canonical_code, match_method = EXCLUDED.match_method, "
                    f"batch_id = EXCLUDED.batch_id WHERE (stg.{name}.canonical_code, stg.{name}.match_method) "
                    f"IS DISTINCT FROM (EXCLUDED.canonical_code, EXCLUDED.match_method)"),
                    {"s": r.source_system, "o": r.source_object, "k": str(r.source_key),
                     "c": None if pd.isna(r.canonical_code) else r.canonical_code, "m": r.match_method,
                     "b": batch_id})
            write_evidence(AREA, f"{name}{suffix(batch_id)}.csv", df)
            log_stage("crosswalk", f"stg.{name}", rows_in=len(df), rows_out=len(df), batch_id=batch_id,
                      note=f"{int(df.canonical_code.isna().sum())} unmatched (flagged for rejection)")
    xc = crosswalk_checks(xw)
    write_evidence(AREA, f"crosswalk_checks{suffix(batch_id)}.csv", xc)
    summary = pd.concat([df.assign(crosswalk=n) for n, df in xw.items()]).groupby(
        ["crosswalk", "source_system", "source_object", "match_method"]).size().reset_index(name="keys")
    write_evidence(AREA, f"crosswalk_match_methods{suffix(batch_id)}.csv", summary)
    rows = [{"check": f"crosswalk: {r.check}" if "check" in xc else "crosswalk", "expected": r.expected,
             "actual": r.actual, "result": r.result} for r in xc.itertuples()]
    record_checks(batch_id, rows)
    print(summary.to_string(index=False))
    finish(pd.DataFrame(rows), f"crosswalk_checks_result{suffix(batch_id)}.csv")


# ---------------------------------------------------------------------------
# 2.07 Pre-join checks
# ---------------------------------------------------------------------------
def prejoin(batch_id: int) -> None:
    res = run(batch_id)
    stg, rows = res["stg"], []
    for name, key in (("receipt", ["receipt_no"]), ("goods_receipt", ["grn_no"]), ("purchase_order", ["po_no"]),
                      ("item", ["item_id"]), ("pos_item", ["item_code"]), ("vendor_item", ["vendor_item_code"]),
                      ("store", ["store_code"]), ("supplier", ["supplier_id"]), ("branch", ["branch_id"]),
                      ("loyalty_member", ["card_no"]), ("panel_account", ["account_no"]), ("fx_rate", ["rate_date"])):
        n = int(stg[name].duplicated(key).sum())
        check(rows, f"pre-join: key {'+'.join(key)} unique in stg.{name}", 0, n, n == 0)
    for name, df in res["xw"].items():
        n = int(df.duplicated(["source_system", "source_object", "source_key"]).sum())
        check(rows, f"pre-join: {name} is many-to-one (each source key once)", 0, n, n == 0)
    joins = pd.concat([res["sales"]["join_log"], res["purch"]["join_log"]], ignore_index=True)
    write_evidence(AREA, f"join_log{suffix(batch_id)}.csv", joins)
    for j in joins.itertuples():
        check(rows, f"join '{j.step}' keeps the row count", j.rows_before, j.rows_after, j.ok)
        log_stage("prejoin", j.step, rows_in=j.rows_before, rows_out=j.rows_after, batch_id=batch_id,
                  status="OK" if j.ok else "FAIL")
    record_checks(batch_id, rows)
    finish(pd.DataFrame(rows), f"prejoin_checks{suffix(batch_id)}.csv")


# ---------------------------------------------------------------------------
# 2.08 Rejects and duplicates
# ---------------------------------------------------------------------------
def quality(batch_id: int) -> None:
    res = run(batch_id)
    rejects = pd.concat([res["sales"]["rejects"], res["purch"]["rejects"]], ignore_index=True)
    dups = pd.concat([res["sales"]["duplicates"], res["purch"]["duplicates"]], ignore_index=True)
    with get_engine("dw").begin() as con:
        for r in rejects.itertuples():
            con.execute(text(
                "INSERT INTO etl.rejects (batch_id, source_system, source_table, source_key, reason_code, "
                "reason_text, raw_record) VALUES (:b, :s, :t, :k, :c, :x, CAST(:j AS JSONB)) "
                "ON CONFLICT (batch_id, source_system, source_table, source_key) DO UPDATE SET "
                "reason_code = EXCLUDED.reason_code, reason_text = EXCLUDED.reason_text, raw_record = EXCLUDED.raw_record"),
                {"b": batch_id, "s": r.source_system, "t": r.source_table, "k": r.source_key, "c": r.reason_code,
                 "x": r.reason_text, "j": r.raw_record})
    write_evidence(AREA, f"rejects{suffix(batch_id)}.csv", rejects.drop(columns=["raw_record"]))
    write_evidence(AREA, f"duplicates_removed{suffix(batch_id)}.csv", dups)
    for table, part in (("receipt_line", res["sales"]), ("grn_line", res["purch"])):
        log_stage("quality", table, rows_in=part["source_rows"], rows_out=len(part["valid"]), batch_id=batch_id,
                  note=f"{len(part['rejects'])} rejected, {len(part['duplicates'])} duplicates removed")

    # Compare with the generator's planted-defect ledger, key for key.
    ledger = pd.read_csv(evidence_dir("01_sources") / LEDGER_OF[batch_id], dtype=str)
    rows, detail = [], []
    for table, part in (("receipt_line", res["sales"]), ("grn_line", res["purch"])):
        led = ledger[ledger.source_table == table]
        for code in sorted(set(led.code) | set(part["rejects"].reason_code)):
            planted = set(led.source_key[led.code == code])
            if code == "D01_EXACT_DUPLICATE":
                got = set(part["duplicates"].source_key)
            elif code == "U01_UNRESOLVED_CUSTOMER":
                v = part["valid"]
                got = set(v.source_key[v.is_customer_unresolved]) if "is_customer_unresolved" in v else set()
            elif code == "LEGIT_REPEAT":
                got = planted & set(part["valid"].source_key)        # legitimate repeats must all be kept
            else:
                got = set(part["rejects"].source_key[part["rejects"].reason_code == code])
            same = planted == got
            detail.append({"table": table, "code": code, "planted": len(planted), "found": len(got),
                           "same_keys": same,
                           "explanation": "identical key sets" if same else
                           f"missing {sorted(planted - got)[:5]} extra {sorted(got - planted)[:5]}"})
            check(rows, f"{table} {code}: ETL result = planted ledger (key for key)", len(planted), len(got), same)
    write_evidence(AREA, f"rejects_vs_ledger{suffix(batch_id)}.csv", pd.DataFrame(detail))
    with get_engine("dw").connect() as con:
        n_db = con.execute(text("SELECT count(*) FROM etl.rejects WHERE batch_id = :b"), {"b": batch_id}).scalar()
    check(rows, "etl.rejects holds every reject of this batch once", len(rejects), n_db, n_db == len(rejects))
    record_checks(batch_id, rows)
    finish(pd.DataFrame(rows), f"quality_checks{suffix(batch_id)}.csv")


# ---------------------------------------------------------------------------
# 2.09 Reconciliation
# ---------------------------------------------------------------------------
def _classify(lines: pd.DataFrame, key_cols: list, part: dict) -> pd.Series:
    key = lines[key_cols].astype(str).agg("|".join, axis=1)
    outcome = pd.Series("valid", index=lines.index)
    outcome[key.isin(set(part["rejects"].source_key))] = "rejected"
    outcome[key.duplicated(keep="first")] = "duplicate"
    return outcome


def reconcile(batch_id: int) -> None:
    res = run(batch_id)
    stg, rows, out_rows, months = res["stg"], [], [], []
    raw = read_raw(batch_id)
    specs = (("sales_db", "receipt_line", res["sales"], ["receipt_no", "line_no"], "net_amount_pkr",
              stg["receipt"].set_index("receipt_no").receipt_ts, "receipt_no"),
             ("purchasing_db", "grn_line", res["purch"], ["grn_no", "line_no"], "amount_original",
              stg["goods_receipt"].set_index("grn_no").received_at, "grn_no"))
    for db, table, part, key_cols, amount_col, header_ts, hkey in specs:
        lines = stg[table]
        src = len(raw[(db, table)])
        valid, rej, dup = len(part["valid"]), len(part["rejects"]), len(part["duplicates"])
        out_rows.append({"batch_id": batch_id, "table": f"{db}.{table}", "source_rows": src, "staged_valid": valid,
                         "rejected": rej, "duplicates_removed": dup, "balanced": src == valid + rej + dup})
        check(rows, f"{table}: source rows = staged valid + rejected + duplicates", src, valid + rej + dup,
              src == valid + rej + dup)
        # Amounts per month: every snapshot line is in exactly one bucket.
        df = pd.DataFrame({"outcome": _classify(lines, key_cols, part),
                           "amount": lines[amount_col].fillna(0.0),
                           "month": lines[hkey].map(header_ts).dt.strftime("%Y-%m").fillna("no header/date")})
        m = df.pivot_table(index="month", columns="outcome", values="amount", aggfunc="sum", fill_value=0.0)
        for c in ("valid", "rejected", "duplicate"):
            if c not in m:
                m[c] = 0.0
        m["source_amount"] = df.groupby("month").amount.sum()
        m["difference"] = (m.source_amount - m.valid - m.rejected - m.duplicate).round(2)
        months.append(m.round(2).reset_index().assign(table=f"{db}.{table}", batch_id=batch_id))
        bad = int((m.difference.abs() > 0.005).sum())
        check(rows, f"{table}: amount per month source = valid + rejected + duplicates", 0, bad, bad == 0)
        raw_amount = (pd.to_numeric(raw[(db, table)].qty) * pd.to_numeric(raw[(db, table)].unit_price_pkr)
                      - pd.to_numeric(raw[(db, table)].discount_pkr).fillna(0)).sum() if table == "receipt_line" else \
            (pd.to_numeric(raw[(db, table)].boxes_received) * pd.to_numeric(raw[(db, table)].cost_per_box)).sum()
        check(rows, f"{table}: staged amount total = raw snapshot amount", round(raw_amount, 2),
              round(df.amount.sum(), 2), abs(raw_amount - df.amount.sum()) < 0.01)
        log_stage("reconcile", table, rows_in=src, rows_out=valid, amount_in=df.amount.sum(),
                  amount_out=df.amount[df.outcome == "valid"].sum(), batch_id=batch_id)
    rec = pd.DataFrame(out_rows)
    write_evidence(AREA, f"reconciliation_batch_{batch_id}.csv", rec)
    write_evidence(AREA, f"reconciliation_amounts_by_month_batch_{batch_id}.csv", pd.concat(months))
    print(rec.to_string(index=False))
    record_checks(batch_id, rows)
    finish(pd.DataFrame(rows), f"reconciliation_checks_batch_{batch_id}.csv")


STEPS = {"profile-before": profile_before, "stage": stage, "profile-after": profile_after,
         "crosswalk": crosswalk, "prejoin": prejoin, "quality": quality, "reconcile": reconcile}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=list(STEPS))
    ap.add_argument("--batch", type=int, required=True)
    a = ap.parse_args()
    STEPS[a.step](a.batch)
