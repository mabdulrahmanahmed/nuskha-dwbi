"""Acceptance checks on the generator output (synthetic data, seed 472).

  python -m src.check_generated volumes     # unit 1.05: volumes, USD share, customer mix, trend
  python -m src.check_generated defects     # unit 1.06: planted defects vs blueprint rates
  python -m src.check_generated stage2      # unit 1.07: stage-1 vs stage-2 diff only touches intended rows

Each check writes a CSV to evidence/01_sources/ and exits with an error if any row FAILs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.common import GENERATED_DIR, evidence_dir, write_evidence


def read(stage: int, db: str, table: str) -> pd.DataFrame:
    return pd.read_csv(GENERATED_DIR / f"stage{stage}" / db / f"{table}.csv", keep_default_na=False,
                       na_values=[""], dtype=str)


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def finish(rows: list, filename: str) -> pd.DataFrame:
    out = pd.DataFrame(rows, columns=["check", "expected", "actual", "ok"])
    out["result"] = out.pop("ok").map({True: "PASS", False: "FAIL"})
    write_evidence("01_sources", filename, out)
    print(out.to_string(index=False))
    if (out.result == "FAIL").any():
        sys.exit(f"{filename}: some checks FAILED")
    return out


def check_volumes() -> pd.DataFrame:
    """Unit 1.05: stage-1 volumes and planted business patterns."""
    rl, r = read(1, "sales_db", "receipt_line"), read(1, "sales_db", "receipt")
    gl, gr = read(1, "purchasing_db", "grn_line"), read(1, "purchasing_db", "goods_receipt")
    po = read(1, "purchasing_db", "purchase_order")
    usd = gl.merge(gr, on="grn_no").merge(po[["po_no", "currency"]], on="po_no").currency.eq("USD").mean() * 100
    x = rl.merge(r[["receipt_no", "customer_type"]], on="receipt_no")
    x["net"] = num(x.qty) * num(x.unit_price_pkr) - num(x.discount_pkr).fillna(0)
    share = x.groupby("customer_type").net.sum() / x.net.sum() * 100
    tot = pd.read_csv(evidence_dir("01_sources") / "stage1_monthly_totals.csv")
    growth = tot.Total.tail(12).sum() / tot.Total.head(12).sum()
    chart = evidence_dir("01_sources") / "stage1_monthly_totals.png"
    return finish([
        ("receipt_line rows (target ~28,000, +-10%)", 28000, len(rl), abs(len(rl) - 28000) <= 2800),
        ("grn_line rows (target ~4,700, +-10%)", 4700, len(gl), abs(len(gl) - 4700) <= 470),
        ("lines per receipt (target ~2.2)", 2.2, round(len(rl) / len(r), 2), abs(len(rl) / len(r) - 2.2) <= 0.2),
        ("GRN lines in USD (%, target ~15)", 15, round(usd, 1), 10 <= usd <= 20),
        ("net sales share walk-in (%, ~70)", 70, round(share["WALKIN"], 1), 62 <= share["WALKIN"] <= 78),
        ("net sales share loyalty (%, ~22)", 22, round(share["LOYALTY"], 1), 16 <= share["LOYALTY"] <= 28),
        ("net sales share panel (%, ~8)", 8, round(share["PANEL"], 1), 5 <= share["PANEL"] <= 11),
        ("months in stage 1 (Nov 2023 - Aug 2026)", 34, len(tot), len(tot) == 34),
        ("trend: last 12 vs first 12 months net sales (> 1.15)", 1.15, round(growth, 2), growth > 1.15),
        ("monthly chart saved", 1, int(chart.exists()), chart.exists()),
    ], "stage1_volume_checks.csv")


def _found_defects(stage: int, cutoff: str) -> dict:
    """Find every defective row directly in a stage's CSVs, independently of the ledger.

    Returns {(table, code): set of 'key|line_no'}. Used to prove the ledger is complete
    (nothing defective that is not listed) and true (everything listed is defective).
    """
    ref_items = pd.read_csv(GENERATED_DIR / "reference" / "item.csv", dtype=str)
    branch_texts = set(pd.read_csv(GENERATED_DIR / "reference" / "branch_name_variant.csv", dtype=str,
                                   keep_default_na=False).branch_name_text)
    panel_texts = set(pd.read_csv(GENERATED_DIR / "reference" / "panel_name_variant.csv", dtype=str,
                                  keep_default_na=False).panel_company_text)
    first_fx = pd.read_csv(GENERATED_DIR / "reference" / "fx_rate.csv").rate_date.min()
    rec, rl = read(stage, "sales_db", "receipt"), read(stage, "sales_db", "receipt_line")
    grn, gl = read(stage, "purchasing_db", "goods_receipt"), read(stage, "purchasing_db", "grn_line")
    po = read(stage, "purchasing_db", "purchase_order")
    dup = pd.read_csv(GENERATED_DIR / f"stage{stage}" / "double_export.csv", dtype=str)

    def keys(df, a, b):
        return set(df[a] + "|" + df[b])

    rl = rl.merge(rec, on="receipt_no", how="left", suffixes=("", "_h"))
    gl = gl.merge(grn, on="grn_no", how="left", suffixes=("", "_h")).merge(po[["po_no", "currency"]], on="po_no")
    found = {
        ("receipt_line", "R01_MISSING_PRODUCT"): keys(rl[~rl.item_code.isin(ref_items.item_code)], "receipt_no", "line_no"),
        ("receipt_line", "R02_BAD_QTY"): keys(rl[num(rl.qty) <= 0], "receipt_no", "line_no"),
        ("receipt_line", "R03_BAD_DATE"): keys(rl[pd.to_datetime(rl.receipt_ts) > cutoff], "receipt_no", "line_no"),
        ("receipt_line", "R04_BAD_AMOUNT"): keys(rl[num(rl.unit_price_pkr) <= 0], "receipt_no", "line_no"),
        ("receipt_line", "R05_UNKNOWN_BRANCH"): keys(rl[rl.branch_name.notna() & ~rl.branch_name.isin(branch_texts)],
                                                     "receipt_no", "line_no"),
        ("receipt_line", "R07_ORPHAN_LINE"): keys(rl[rl.branch_name.isna()], "receipt_no", "line_no"),
        ("receipt_line", "U01_UNRESOLVED_CUSTOMER"): keys(rl[(rl.customer_type == "PANEL")
                                                             & ~rl.panel_company_text.isin(panel_texts)],
                                                          "receipt_no", "line_no"),
        ("receipt_line", "D01_EXACT_DUPLICATE"): keys(dup[dup.source_table == "receipt_line"], "receipt_no", "line_no"),
        ("grn_line", "R01_MISSING_PRODUCT"): keys(gl[~gl.vendor_item_code.isin(ref_items.vendor_item_code)],
                                                  "grn_no", "line_no"),
        ("grn_line", "R02_BAD_QTY"): keys(gl[num(gl.boxes_received) <= 0], "grn_no", "line_no"),
        ("grn_line", "R03_BAD_DATE"): keys(gl[pd.to_datetime(gl.received_at.str[:19]) > cutoff], "grn_no", "line_no"),
        ("grn_line", "R04_BAD_AMOUNT"): keys(gl[num(gl.cost_per_box) <= 0], "grn_no", "line_no"),
        ("grn_line", "R06_NO_FX_RATE"): keys(gl[(gl.currency == "USD") & (gl.received_at.str[:10] < first_fx)],
                                             "grn_no", "line_no"),
        ("grn_line", "D01_EXACT_DUPLICATE"): keys(dup[dup.source_table == "grn_line"], "receipt_no", "line_no"),
    }
    # Legitimate repeats: a line whose (known) item already appears on a lower line of the same
    # receipt. Unknown codes are left out: two R01 lines may share the same unknown code.
    same = rl[rl.item_code.isin(ref_items.item_code)].copy()
    same["ln"] = num(same.line_no)
    same = same.sort_values(["receipt_no", "ln"])
    found[("receipt_line", "LEGIT_REPEAT")] = keys(same[same.duplicated(["receipt_no", "item_code"])],
                                                   "receipt_no", "line_no")
    return found


def check_defects() -> pd.DataFrame:
    """Unit 1.06: ledger counts per code within +-10% of the blueprint rates, and ledger == data."""
    from src.gen.defects import RATE_U01, RATES_PURCH, RATES_SALES

    ledger = pd.read_csv(evidence_dir("01_sources") / "defect_ledger.csv", dtype=str)
    rl, rec = read(1, "sales_db", "receipt_line"), read(1, "sales_db", "receipt")
    gl = read(1, "purchasing_db", "grn_line")
    n_rl = len(rl) - (ledger.code == "LEGIT_REPEAT").sum()            # lines before repeats were added
    n_gl = len(gl) - (ledger.code == "R06_NO_FX_RATE").sum()          # lines before R06 orders were added
    panel_lines = rl.merge(rec, on="receipt_no").customer_type.eq("PANEL").sum()
    rows = []
    for table, rates, base in (("receipt_line", RATES_SALES, n_rl), ("grn_line", RATES_PURCH, n_gl)):
        for code, rate in rates.items():
            target, got = rate * base, int(((ledger.source_table == table) & (ledger.code == code)).sum())
            rows.append((f"{table} {code}: count vs {rate:.1%} of {base} lines (+-10%)", round(target, 1), got,
                         abs(got - target) <= 0.10 * target))
    target = RATE_U01 * panel_lines
    got = int((ledger.code == "U01_UNRESOLVED_CUSTOMER").sum())
    rows.append((f"receipt_line U01_UNRESOLVED_CUSTOMER: count vs 1% of {panel_lines} panel lines (+-10%)",
                 round(target, 1), got, abs(got - target) <= 0.10 * target))
    got = int((ledger.code == "R06_NO_FX_RATE").sum())
    rows.append(("grn_line R06_NO_FX_RATE: a few lines (1-10)", "1-10", got, 1 <= got <= 10))

    # The ledger must list exactly the defective rows found in the data.
    found = _found_defects(1, "2026-08-31 23:59:59")
    for (table, code), keys in sorted(found.items()):
        listed = set(ledger.source_key[(ledger.source_table == table) & (ledger.code == code)])
        rows.append((f"{table} {code}: ledger rows = defective rows found in the stage-1 data",
                     len(keys), len(listed), listed == keys))
    write_evidence("01_sources", "defect_ledger_summary.csv",
                   ledger.groupby(["source_table", "code"]).size().rename("rows").reset_index())
    return finish(rows, "defect_rate_checks.csv")


def diff_stages() -> pd.DataFrame:
    """Row-level diff of every source table, stage 1 vs stage 2, by primary key."""
    from src.gen.sources import COLUMNS, KEYS

    rows = []
    for (db, table) in COLUMNS:
        a, b = read(1, db, table).fillna(""), read(2, db, table).fillna("")
        key = KEYS[table]
        a.index = a[key].agg("|".join, axis=1)
        b.index = b[key].agg("|".join, axis=1)
        for k in b.index.difference(a.index):
            rows.append((db, table, k, "added", ""))
        for k in a.index.difference(b.index):
            rows.append((db, table, k, "deleted", ""))
        common = a.index.intersection(b.index)
        aa, bb = a.loc[common], b.loc[common, a.columns]
        changed = (aa != bb).any(axis=1)
        for k in changed[changed].index:
            cols = [c for c in a.columns if aa.at[k, c] != bb.at[k, c]]
            rows.append((db, table, k, "changed", ", ".join(cols)))
    return pd.DataFrame(rows, columns=["database", "table", "key", "change", "columns_changed"])


def check_stage2() -> pd.DataFrame:
    """Unit 1.07: the stage-1 -> stage-2 diff touches exactly the intended rows."""
    intended = pd.read_csv(evidence_dir("01_sources") / "stage2_intended_changes.csv", dtype=str)
    diff = diff_stages()
    merged = diff.merge(intended, on=["database", "table", "key"], how="outer", suffixes=("", "_intended"),
                        indicator=True)
    merged["intended"] = merged["_merge"].map({"both": "yes", "left_only": "NO (unexpected)",
                                               "right_only": "MISSING (intended but not found)"}).astype(str)
    merged.loc[(merged._merge == "both") & (merged.change != merged.change_intended), "intended"] = "WRONG CHANGE TYPE"
    out = merged.drop(columns=["_merge"]).rename(columns={"change_intended": "intended_change"})
    write_evidence("01_sources", "stage2_diff.csv", out)
    summary = out.groupby(["database", "table", "change", "intended"], dropna=False).size().rename("rows").reset_index()
    write_evidence("01_sources", "stage2_diff_summary.csv", summary)
    print(summary.to_string(index=False))

    rows = [("rows in the stage-1 -> stage-2 diff that were not intended", 0, int((out.intended != "yes").sum()),
             (out.intended == "yes").all())]
    for (table, change), n in out[out.intended == "yes"].groupby(["table", "change"]).size().items():
        rows.append((f"{table}: {change} rows (all intended)", n, n, True))
    # Spot checks on the story the diff must tell.
    rec2 = read(2, "sales_db", "receipt")
    rows.append(("receipts VOIDED in stage 2", 15, int((rec2.status == "VOIDED").sum()), (rec2.status == "VOIDED").sum() == 15))
    deleted = out[(out.table == "receipt") & (out.change == "deleted")]
    rows.append(("receipts hard-deleted", 3, len(deleted), len(deleted) == 3))
    late = intended[intended.reason == "late receipt"]
    rows.append(("late receipts: receipt date before 1 Sep 2026, first seen in stage 2", 40,
                 int((pd.to_datetime(rec2.set_index("receipt_no").loc[late.key, "receipt_ts"]) < "2026-09-01").sum()),
                 len(late) == 40))
    item2 = read(2, "inventory", "item")
    syrup = item2[item2.generic_name == "Dextromethorphan Syrup"].category.iloc[0]
    rows.append(("cough syrup category in stage 2", "Cough and Cold", syrup, syrup == "Cough and Cold"))
    return finish(rows, "stage2_checks.csv")


CHECKS = {"volumes": check_volumes, "defects": check_defects, "stage2": check_stage2}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "volumes"
    CHECKS[name]()
