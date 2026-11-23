"""Pre-database dry run of the ETL on the generated sources (synthetic data, seed 472).

Runs the pure-Python parts of the pipeline exactly as the database run will, but on
in-memory frames built from data/generated/ instead of extracts from the servers:

  batch 1: stage-1 sources up to 31 Aug 2026  -> profile, normalize, crosswalks, quality,
           dimensions and facts (as DataFrames)
  batch 2: stage-2 rows changed after the batch-1 watermark -> same steps, then the
           deletion check, late arrivals and the SCD Type 1 category effect

and checks the results against the generator's defect ledger and stage-2 change list.
Output: evidence/02_etl/offline_dry_run/*.csv (labelled as a dry run; the real evidence
of units 2.02-3.06 is produced from the databases).

Usage: python -m src.offline_dry_run
"""
from __future__ import annotations

import pandas as pd

from src.common import evidence_dir
from src.crosswalk import build_crosswalks, crosswalk_checks
from src.load import (build_dim_branch, build_dim_customer, build_dim_date, build_dim_product, build_dim_supplier,
                      build_fact_purchase, build_fact_sales)
from src.normalize import STAGING_OF, normalize
from src.profile import compare, profile_tables
from src.quality import accumulate, prepare_purchases, prepare_sales
from src.raw import raw_from_generated

CUT1, CUT2 = pd.Timestamp("2026-08-31 23:59:59"), pd.Timestamp("2026-10-31 23:59:59")
AREA = "02_etl/offline_dry_run"


def check(rows: list, name: str, expected, actual, ok: bool) -> None:
    rows.append({"check": name, "expected": expected, "actual": actual, "result": "PASS" if ok else "FAIL"})


def run_batch(raw: dict, cutoff, batch_id: int, dims_before: dict | None = None, previous_stg: dict | None = None) -> dict:
    stg = accumulate(normalize(raw), previous_stg)        # headers of earlier batches stay in staging
    xw = build_crosswalks(stg)
    sales = prepare_sales(stg, xw, cutoff, batch_id)
    purch = prepare_purchases(stg, xw, cutoff, batch_id)
    existing = dims_before or {}
    dims = {
        "dim_date": build_dim_date(),
        "dim_product": build_dim_product(stg, xw, batch_id),
        "dim_branch": build_dim_branch(stg, existing.get("branch_keys")),
        "dim_customer": build_dim_customer(stg, batch_id, existing.get("customer_keys")),
        "dim_supplier": build_dim_supplier(stg),
    }
    facts = {"fact_sales": build_fact_sales(sales["valid"], stg, dims),
             "fact_purchase": build_fact_purchase(purch["valid"], dims)}
    return {"raw": raw, "stg": stg, "xw": xw, "sales": sales, "purch": purch, "dims": dims, "facts": facts}


def ledger_checks(rows: list, res: dict, ledger: pd.DataFrame, label: str) -> pd.DataFrame:
    """Rejects, duplicates and unresolved customers must equal the planted ledger, key for key."""
    found = pd.concat([res["sales"]["rejects"], res["purch"]["rejects"]])
    out = []
    for table, part in (("receipt_line", res["sales"]), ("grn_line", res["purch"])):
        led = ledger[ledger.source_table == table]
        codes = sorted(set(led.code) | set(part["rejects"].reason_code))
        for code in codes:
            planted = set(led.source_key[led.code == code])
            if code == "D01_EXACT_DUPLICATE":
                got = set(part["duplicates"].source_key)
            elif code == "U01_UNRESOLVED_CUSTOMER":
                v = part["valid"]
                got = set(v.source_key[v.is_customer_unresolved]) if "is_customer_unresolved" in v else set()
            elif code == "LEGIT_REPEAT":
                got = planted & set(part["valid"].source_key)              # must all be kept
            else:
                got = set(part["rejects"].source_key[part["rejects"].reason_code == code])
            out.append({"batch": label, "table": table, "code": code, "planted": len(planted), "found": len(got),
                        "same_keys": planted == got})
            check(rows, f"{label} {table} {code}: ETL result = planted ledger (key for key)",
                  len(planted), len(got), planted == got)
    return pd.DataFrame(out)


def reconciliation(rows: list, res: dict, label: str) -> pd.DataFrame:
    out = []
    for table, part, fact in (("receipt_line", res["sales"], "fact_sales"),
                              ("grn_line", res["purch"], "fact_purchase")):
        src, valid = part["source_rows"], len(part["valid"])
        rej, dup = len(part["rejects"]), len(part["duplicates"])
        out.append({"batch": label, "table": table, "source_rows": src, "valid": valid, "rejected": rej,
                    "duplicates_removed": dup, "balanced": src == valid + rej + dup,
                    "fact_rows": len(res["facts"][fact])})
        check(rows, f"{label} {table}: source rows = valid + rejected + duplicates", src, valid + rej + dup,
              src == valid + rej + dup)
    # Amounts per month: raw text recomputed independently vs the fact rows built by the pipeline.
    raw_l = res["raw"][("sales_db", "receipt_line")].drop_duplicates(["receipt_no", "line_no"]).copy()
    raw_l["source_key"] = raw_l.receipt_no + "|" + raw_l.line_no
    raw_h = res["raw"][("sales_db", "receipt")][["receipt_no", "receipt_ts"]]
    raw_l = raw_l.merge(raw_h, on="receipt_no")
    raw_l = raw_l[raw_l.source_key.isin(res["sales"]["valid"].source_key)]
    q, p = pd.to_numeric(raw_l.qty), pd.to_numeric(raw_l.unit_price_pkr)
    d = pd.to_numeric(raw_l.discount_pkr).fillna(0)
    raw_l["net"] = (q * p).round(2) - d
    src_m = raw_l.groupby(raw_l.receipt_ts.str[:7]).net.sum().round(2)
    f = res["facts"]["fact_sales"]
    fact_m = f.groupby(f.date_key.astype(str).str[:4] + "-" + f.date_key.astype(str).str[4:6]).net_amount_pkr.sum().round(2)
    months = pd.DataFrame({"source_net_pkr": src_m, "fact_net_pkr": fact_m}).fillna(0)
    months["difference"] = (months.source_net_pkr - months.fact_net_pkr).round(2)
    bad = int((months.difference.abs() > 0.005).sum())
    check(rows, f"{label} sales net amount per month: source valid rows = fact rows (to the paisa)", 0, bad, bad == 0)
    return pd.DataFrame(out), months.reset_index(names="month").assign(batch=label)


def main() -> None:
    rows: list = []
    ledger1 = pd.read_csv(evidence_dir("01_sources") / "defect_ledger.csv", dtype=str)
    ledger2 = pd.read_csv(evidence_dir("01_sources") / "defect_ledger_stage2.csv", dtype=str)
    intended = pd.read_csv(evidence_dir("01_sources") / "stage2_intended_changes.csv", dtype=str)

    # ---------------- Batch 1 ----------------
    b1 = run_batch(raw_from_generated(1, until=CUT1), CUT1, 1)
    before = profile_tables(b1["raw"], "before (raw)")
    after = profile_tables({("stg", k): v.drop(columns=["raw_json"], errors="ignore") for k, v in b1["stg"].items()},
                           "after (staged)")
    ev = evidence_dir(AREA)
    before.to_csv(ev / "profile_before.csv", index=False, lineterminator="\n")
    after.to_csv(ev / "profile_after.csv", index=False, lineterminator="\n")
    pairs = compare(before, after, STAGING_OF)
    pairs.to_csv(ev / "profile_before_after.csv", index=False, lineterminator="\n")
    check(rows, "profile_before covers every source table", 17, before.table.nunique(), before.table.nunique() == 17)
    check(rows, "profile_before_after has a before/after pair per table", 34, len(pairs), len(pairs) == 34)

    stg = b1["stg"]
    leftovers = {
        "text dates left in staging (object columns named *_ts/_date/_at)": sum(
            int(df[c].map(lambda v: isinstance(v, str)).sum()) for df in stg.values() for c in df.columns
            if c.endswith(("_ts", "_date", "_at", "_from", "_on")) and df[c].dtype == object),
        "float money with more than 2 decimals in staging": sum(
            int((df[c].dropna() != df[c].dropna().round(2)).sum()) for df in stg.values() for c in df.columns
            if (c.endswith(("_pkr", "_cost_per_unit", "cost_per_box", "amount_original")) or c == "std_cost_per_unit")
            and c != "usd_pkr"),   # the FX rate is NUMERIC(10,4) by design
        "Inventory categories outside the 8 canonical names": int((~stg["item"].category.isin(
            ["Analgesics", "Antibiotics", "Cardiovascular", "Diabetes Care", "Gastro", "Cough and Cold",
             "Vitamins and Supplements", "Personal Care"])).sum()),
    }
    for name, n in leftovers.items():
        check(rows, name, 0, n, n == 0)

    xw_checks = crosswalk_checks(b1["xw"])
    xw_checks.to_csv(ev / "crosswalk_checks.csv", index=False, lineterminator="\n")
    for k, df in b1["xw"].items():
        df.to_csv(ev / f"{k}.csv", index=False, lineterminator="\n")
    fails = int((xw_checks.result == "FAIL").sum())
    check(rows, "crosswalks: every key maps to one canonical code or is flagged unmatched", 0, fails, fails == 0)
    unmatched_branch = b1["xw"]["xw_branch"].query("match_method == 'unmatched'").source_key.tolist()
    check(rows, "unmatched branch texts are exactly the planted bad texts", 6, len(unmatched_branch),
          set(unmatched_branch) == {"Head Office", "TEST BRANCH", "Karachi", "Br 11", "-", "Warehouse"})

    joins = pd.concat([b1["sales"]["join_log"], b1["purch"]["join_log"]])
    joins.to_csv(ev / "join_log_batch_1.csv", index=False, lineterminator="\n")
    check(rows, "pre-join: no join changed a row count (batch 1)", 0, int((~joins.ok).sum()), joins.ok.all())
    for name, df, key in (("receipt", stg["receipt"], ["receipt_no"]), ("goods_receipt", stg["goods_receipt"], ["grn_no"]),
                          ("purchase_order", stg["purchase_order"], ["po_no"]), ("item", stg["item"], ["item_id"]),
                          ("pos_item", stg["pos_item"], ["item_code"]), ("vendor_item", stg["vendor_item"], ["vendor_item_code"])):
        n = int(df.duplicated(key).sum())
        check(rows, f"pre-join: source key unique in {name}", 0, n, n == 0)

    led1 = ledger_checks(rows, b1, ledger1, "batch 1")
    rec1, months1 = reconciliation(rows, b1, "batch 1")
    rej1 = pd.concat([b1["sales"]["rejects"], b1["purch"]["rejects"]])
    rej1.drop(columns=["raw_record"]).to_csv(ev / "rejects_batch_1.csv", index=False, lineterminator="\n")

    # Dimensions and facts.
    dims = b1["dims"]
    for name, key, special in (("dim_product", "product_key", [-1]), ("dim_branch", "branch_key", [-1]),
                               ("dim_customer", "customer_key", [-1, 0]), ("dim_supplier", "supplier_key", [-1])):
        d = dims[name]
        ok = set(special) <= set(d[key]) and not d[key].duplicated().any() and not d.iloc[:, 1].duplicated().any()
        check(rows, f"{name}: special members present, keys and business keys unique", special, len(d), ok)
    dd = dims["dim_date"]
    check(rows, "dim_date covers 2023-11-01 to 2027-01-31 with Ramadan days flagged", 1188, len(dd),
          len(dd) == 1188 and dd.is_ramadan.sum() == 89)
    fs = b1["facts"]["fact_sales"]
    for col in ("date_key", "product_key", "branch_key", "customer_key"):
        check(rows, f"fact_sales.{col}: no missing keys", 0, int(fs[col].isna().sum()), fs[col].notna().all())
    orphan = int((~fs.product_key.isin(dims["dim_product"].product_key)).sum()
                 + (~fs.branch_key.isin(dims["dim_branch"].branch_key)).sum()
                 + (~fs.customer_key.isin(dims["dim_customer"].customer_key)).sum()
                 + (~fs.date_key.isin(dd.date_key)).sum())
    check(rows, "fact_sales: every key exists in its dimension", 0, orphan, orphan == 0)
    fp = b1["facts"]["fact_purchase"]
    orphan = int((~fp.date_key.isin(dd.date_key)).sum() + (~fp.supplier_key.isin(dims["dim_supplier"].supplier_key)).sum())
    check(rows, "fact_purchase: every key exists in its dimension", 0, orphan, orphan == 0)
    check(rows, "fact_sales natural key (receipt_no, line_no) unique", 0,
          int(fs.duplicated(["receipt_no", "line_no"]).sum()), not fs.duplicated(["receipt_no", "line_no"]).any())

    # Diagnosis story: Diabetes Care margin % falls from March 2026.
    cat = dims["dim_product"].set_index("product_key").category
    fs2 = fs[~fs.is_cancelled].assign(category=fs.product_key.map(cat), month=fs.date_key // 100)
    m = fs2.groupby(["category", "month"])[["net_amount_pkr", "gross_margin_pkr"]].sum()
    m["margin_pct"] = (100 * m.gross_margin_pkr / m.net_amount_pkr).round(2)
    m.reset_index().to_csv(ev / "margin_by_category_month_batch_1.csv", index=False, lineterminator="\n")
    dia = m.loc["Diabetes Care"]
    pre = dia.loc[202509:202602]
    post = dia.loc[202603:202608]
    pre_pct = round(100 * pre.gross_margin_pkr.sum() / pre.net_amount_pkr.sum(), 2)
    post_pct = round(100 * post.gross_margin_pkr.sum() / post.net_amount_pkr.sum(), 2)
    check(rows, "Diabetes Care margin % Mar-Aug 2026 below Sep 2025-Feb 2026 by > 5 points",
          f"{pre_pct} -> lower", post_pct, pre_pct - post_pct > 5)
    unknown_share = round(100 * (fs.customer_key == -1).mean(), 3)
    check(rows, "Unknown customer share of fact rows below 1%", "< 1", unknown_share, unknown_share < 1)

    # ---------------- Batch 2 (watermark = batch-1 cut-off) ----------------
    b2 = run_batch(raw_from_generated(2, since=CUT1, until=CUT2), CUT2, 2,
                   {"branch_keys": dict(zip(dims["dim_branch"].branch_code, dims["dim_branch"].branch_key)),
                    "customer_keys": dict(zip(dims["dim_customer"].customer_code, dims["dim_customer"].customer_key))},
                   previous_stg=b1["stg"])
    led2 = ledger_checks(rows, b2, ledger2, "batch 2")
    rec2, months2 = reconciliation(rows, b2, "batch 2")
    joins2 = pd.concat([b2["sales"]["join_log"], b2["purch"]["join_log"]])
    check(rows, "pre-join: no join changed a row count (batch 2)", 0, int((~joins2.ok).sum()), joins2.ok.all())

    # Upsert batch-2 facts over batch-1 facts on the natural key.
    fs_all = pd.concat([fs, b2["facts"]["fact_sales"]]).drop_duplicates(["receipt_no", "line_no"], keep="last")
    upd = b2["facts"]["fact_sales"].merge(fs[["receipt_no", "line_no"]], on=["receipt_no", "line_no"])
    check(rows, "batch 2: stage-1 lines updated in place (qty fixes, panel fixes, voids)",
          int(((intended.change == "changed") & (intended.table == "receipt_line")).sum()), len(upd),
          len(upd) == int(((intended.change == "changed") & (intended.table == "receipt_line")).sum()))
    late = b2["facts"]["fact_sales"]
    late = late[(late.date_key < 20260901) & ~late.receipt_no.isin(fs.receipt_no)]
    check(rows, "batch 2: late receipts load into their real (Jul-Aug 2026) dates", 40, late.receipt_no.nunique(),
          late.receipt_no.nunique() == 40)
    voided = int(fs_all.is_cancelled.sum())
    check(rows, "batch 2: lines of VOIDED receipts flagged is_cancelled (kept, not deleted)",
          int(((intended.reason == "receipt VOIDED (re-saved)")).sum()), voided,
          voided == int((intended.reason == "receipt VOIDED (re-saved)").sum()))
    # Deletion check: keys of batch-1 receipts no longer present in the full stage-2 key list.
    keys2 = set(raw_from_generated(2)[("sales_db", "receipt")].receipt_no)
    gone = sorted(set(b1["stg"]["receipt"].receipt_no) - keys2)
    planned = sorted(intended.key[(intended.table == "receipt") & (intended.change == "deleted")])
    pd.DataFrame({"receipt_no": gone}).to_csv(ev / "deletion_log_batch_2.csv", index=False, lineterminator="\n")
    check(rows, "batch 2: deleted receipts found by key comparison", planned, gone, gone == planned)
    # Late-arriving dimension: the new product appears in dim_product and in facts.
    new_prod = b2["dims"]["dim_product"]
    check(rows, "batch 2: new product P-0500 added to dim_product before its facts load", "P-0500",
          "P-0500" if "P-0500" in set(new_prod.product_code) else "missing",
          "P-0500" in set(new_prod.product_code) and (b2["facts"]["fact_sales"].product_key == 500).any())

    # SCD Type 1: category totals before and after the cough-syrup correction.
    live = fs_all[~fs_all.is_cancelled]
    cat2 = b2["dims"]["dim_product"].set_index("product_key").category
    cat1 = cat2.copy()                         # before: batch-1 values for products that existed then
    cat1.update(dims["dim_product"].set_index("product_key").category)
    scd = pd.DataFrame({"before_batch_2_dim": live.groupby(live.product_key.map(cat1)).net_amount_pkr.sum(),
                        "after_batch_2_dim": live.groupby(live.product_key.map(cat2)).net_amount_pkr.sum()}).round(2)
    scd["change"] = (scd.after_batch_2_dim - scd.before_batch_2_dim).round(2)
    scd.loc["Company total"] = scd.sum().round(2)
    scd.reset_index(names="category").to_csv(ev / "scd1_category_totals.csv", index=False, lineterminator="\n")
    moved = scd.drop("Company total")
    moved = sorted(moved.index[moved.change.abs() > 0.005])
    check(rows, "SCD1: exactly Gastro and Cough and Cold totals move; company total unchanged",
          ["Cough and Cold", "Gastro"], moved,
          moved == ["Cough and Cold", "Gastro"] and abs(scd.loc["Company total", "change"]) < 0.005)

    # Rerun safety (pure functions): batch 1 again gives identical fact rows.
    again = run_batch(raw_from_generated(1, until=CUT1), CUT1, 1)["facts"]["fact_sales"]
    check(rows, "rerun of batch 1 on unchanged input gives identical fact rows", True,
          bool(again.equals(fs)), again.equals(fs))

    pd.concat([led1, led2]).to_csv(ev / "rejects_vs_ledger.csv", index=False, lineterminator="\n")
    pd.concat([rec1, rec2]).to_csv(ev / "reconciliation_rows.csv", index=False, lineterminator="\n")
    pd.concat([months1, months2]).to_csv(ev / "reconciliation_amounts_by_month.csv", index=False, lineterminator="\n")
    out = pd.DataFrame(rows)
    out.to_csv(ev / "dry_run_checks.csv", index=False, lineterminator="\n")
    (ev / "README.md").write_text(
        "# Pre-database dry run (synthetic data)\n\nProduced by `python -m src.offline_dry_run` before the databases "
        "were available. It runs the pure-Python ETL (profile, normalize, crosswalks, quality, dimensions, facts) "
        "on the generated sources and checks the results against the generator's defect ledger and stage-2 "
        "change list. The official evidence of units 2.02-3.06 is produced later from the databases.\n",
        encoding="utf-8", newline="\n")
    pd.set_option("display.width", 250)
    print(out.to_string(index=False, max_colwidth=95))
    print(f"\n{(out.result == 'PASS').sum()} PASS, {(out.result == 'FAIL').sum()} FAIL")


if __name__ == "__main__":
    main()
