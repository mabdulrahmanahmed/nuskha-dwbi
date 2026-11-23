"""Generator part 3: plant data-quality defects at the blueprint's rates. SYNTHETIC, seed 472.

Every planted row is written to a ledger (code, table, source key), so the ETL's
reject counts can be checked against what was planted (unit 2.08).

Codes (rates are shares of the lines in the stage window):
  R01_MISSING_PRODUCT    0.6%  till / vendor item code unknown to every crosswalk
  R02_BAD_QTY            0.4%  quantity <= 0 on a POSTED line
  R03_BAD_DATE           0.3%  receipt / GRN date after the batch cut-off (year keyed 10 years ahead)
  R04_BAD_AMOUNT         0.3%  price or cost <= 0
  R05_UNKNOWN_BRANCH     0.2%  branch text matching no crosswalk rule (Sales only)
  R06_NO_FX_RATE         few   USD GRN lines received before the first FX rate (stage 1 only)
  R07_ORPHAN_LINE        0.2%  receipt line whose header is missing (Sales only; Purchasing enforces FKs)
  D01_EXACT_DUPLICATE    0.5%  same source key exported twice (listed in double_export.csv)
  U01_UNRESOLVED_CUSTOMER 1% of panel lines: panel name typed beyond recognition
  LEGIT_REPEAT           1%    same receipt, item and day on a new line number: NOT a defect, must be kept

Each line gets at most one code, so reject counts add up exactly.
Receipt- and GRN-level defects (R03, R05, R07, U01) hit every line of the chosen header.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.common import SEED
from src.gen.transactions import STAGE1_CUTOFF, STAGE2_CUTOFF

RATES_SALES = {"R05_UNKNOWN_BRANCH": 0.002, "R03_BAD_DATE": 0.003, "R07_ORPHAN_LINE": 0.002,
               "R01_MISSING_PRODUCT": 0.006, "R02_BAD_QTY": 0.004, "R04_BAD_AMOUNT": 0.003,
               "D01_EXACT_DUPLICATE": 0.005, "LEGIT_REPEAT": 0.01}
RATE_U01 = 0.01                       # share of panel lines
RATES_PURCH = {"R03_BAD_DATE": 0.003, "R01_MISSING_PRODUCT": 0.006, "R02_BAD_QTY": 0.004,
               "R04_BAD_AMOUNT": 0.003, "D01_EXACT_DUPLICATE": 0.005}
BAD_BRANCH_TEXT = ["Head Office", "TEST BRANCH", "Karachi", "Br 11", "-", "Warehouse"]
JUNK_PANEL_TEXT = ["company", "cash credit", "corp acct", "staff panel", "co.", "credit a/c"]
# Vendor items that exist in Purchasing but match no Inventory item (planted R01 in Purchasing).
UNKNOWN_VENDOR_ITEMS = [("ZZZ-0001", "PROMOTIONAL DISPLAY UNIT", 1), ("ZZZ-0002", "SAMPLE CARTON - NOT STOCKED", 12)]
WINDOWS = {1: (datetime(2000, 1, 1), STAGE1_CUTOFF), 2: (STAGE1_CUTOFF, STAGE2_CUTOFF)}


def _in_window(ts: pd.Series, stage: int) -> pd.Series:
    lo, hi = WINDOWS[stage]
    ts = pd.to_datetime(ts)
    return (ts > pd.Timestamp(lo)) & (ts <= pd.Timestamp(hi))


def _pick_headers(rng, line_counts: pd.Series, target: int, used: set) -> list:
    """Choose whole headers (receipts or GRNs) whose lines add up to the target, never more."""
    chosen, remaining = [], target
    for key in rng.permutation(line_counts.index.to_numpy()):
        if remaining <= 0:
            break
        if key in used or line_counts[key] > remaining:
            continue
        chosen.append(key)
        used.add(key)
        remaining -= int(line_counts[key])
    return chosen


def _plant_sales(rng, rec: pd.DataFrame, lin: pd.DataFrame, stage: int, ledger: list, dup: list):
    win_rec = rec[_in_window(rec.updated_at, stage) & ~rec._late.astype(bool) & (rec.status == "POSTED")]
    win_lines = lin[_in_window(lin.updated_at, stage)]
    n = len(win_lines)
    counts = win_lines[win_lines.receipt_no.isin(win_rec.receipt_no)].groupby("receipt_no").size()
    target = {code: int(round(rate * n)) for code, rate in RATES_SALES.items()}
    used_receipts: set = set()

    def log(code, keys_df, detail):
        for k, ln_no in zip(keys_df.receipt_no, keys_df.line_no):
            ledger.append({"stage": stage, "code": code, "source_system": "sales_db", "source_table": "receipt_line",
                           "source_key": f"{k}|{ln_no}", "detail": detail})

    # --- header-level defects -------------------------------------------------
    for code in ("R05_UNKNOWN_BRANCH", "R03_BAD_DATE", "R07_ORPHAN_LINE"):
        for receipt_no in _pick_headers(rng, counts, target[code], used_receipts):
            i = rec.index[rec.receipt_no == receipt_no][0]
            if code == "R05_UNKNOWN_BRANCH":
                rec.at[i, "branch_name"] = str(rng.choice(BAD_BRANCH_TEXT))
                detail = f"branch typed as '{rec.at[i, 'branch_name']}'"
            elif code == "R03_BAD_DATE":
                old = pd.Timestamp(rec.at[i, "receipt_ts"])
                rec.at[i, "receipt_ts"] = old + pd.DateOffset(years=10)
                detail = f"receipt_ts keyed as {rec.at[i, 'receipt_ts']} (real {old})"
            else:
                rec.at[i, "_drop_header"] = True          # header lost; its lines stay behind
                detail = "header receipt missing"
            log(code, lin[lin.receipt_no == receipt_no], detail)

    # U01: panel name typed beyond recognition (target is 1% of panel lines in the window).
    panel_counts = counts[counts.index.isin(win_rec.receipt_no[win_rec.customer_type == "PANEL"])]
    for receipt_no in _pick_headers(rng, panel_counts, int(round(RATE_U01 * panel_counts.sum())), used_receipts):
        i = rec.index[rec.receipt_no == receipt_no][0]
        rec.at[i, "panel_company_text"] = str(rng.choice(JUNK_PANEL_TEXT))
        log("U01_UNRESOLVED_CUSTOMER", lin[lin.receipt_no == receipt_no],
            f"panel text '{rec.at[i, 'panel_company_text']}' (true account {int(rec.at[i, '_account_no'])})")

    # --- line-level defects ----------------------------------------------------
    free = lin.index[lin.receipt_no.isin(win_rec.receipt_no) & ~lin.receipt_no.isin(used_receipts)
                     & (lin.qty < 50)].to_numpy()                    # leave the keying-error line alone
    order = iter(rng.permutation(free))
    unknown_codes = ["MISC-OPEN", "DISC-0412-STR", "SAMPLE-PCS"]
    new_lines = []
    for code in ("R01_MISSING_PRODUCT", "R02_BAD_QTY", "R04_BAD_AMOUNT", "D01_EXACT_DUPLICATE", "LEGIT_REPEAT"):
        for _ in range(target[code]):
            i = next(order)
            key = f"{lin.at[i, 'receipt_no']}|{lin.at[i, 'line_no']}"
            if code == "R01_MISSING_PRODUCT":
                old = lin.at[i, "item_code"]
                lin.at[i, "item_code"] = str(rng.choice(unknown_codes))
                detail = f"item_code {lin.at[i, 'item_code']} (real {old})"
            elif code == "R02_BAD_QTY":
                lin.at[i, "qty"] = float(rng.choice([0, -1, -2]))
                detail = f"qty {lin.at[i, 'qty']}"
            elif code == "R04_BAD_AMOUNT":
                lin.at[i, "unit_price_pkr"] = float(rng.choice([0.0, -lin.at[i, "unit_price_pkr"]]))
                detail = f"unit_price_pkr {lin.at[i, 'unit_price_pkr']}"
            elif code == "D01_EXACT_DUPLICATE":
                dup.append({"stage": stage, "source_system": "sales_db", "source_table": "receipt_line",
                            "receipt_no": lin.at[i, "receipt_no"], "line_no": int(lin.at[i, "line_no"])})
                detail = "exported twice by the till export job"
            else:                                           # LEGIT_REPEAT: a second line, same item
                row = lin.loc[i].copy()
                taken = lin.line_no[lin.receipt_no == row["receipt_no"]].tolist()
                taken += [r["line_no"] for r in new_lines if r["receipt_no"] == row["receipt_no"]]
                row["line_no"] = int(max(taken)) + 1             # next free line number on the receipt
                new_lines.append(row.to_dict())
                key = f"{row['receipt_no']}|{row['line_no']}"
                detail = f"same item as line {lin.at[i, 'line_no']}, new line number: keep"
            ledger.append({"stage": stage, "code": code, "source_system": "sales_db",
                           "source_table": "receipt_line", "source_key": key, "detail": detail})
    if new_lines:
        lin = pd.concat([lin, pd.DataFrame(new_lines)], ignore_index=True)
    return rec, lin


def _plant_purchases(rng, ref, po, grn, gl, stage: int, ledger: list, dup: list):
    win_grn = grn[_in_window(grn.updated_at, stage)]
    win_lines = gl[_in_window(gl.updated_at, stage)]
    n = len(win_lines)
    target = {code: int(round(rate * n)) for code, rate in RATES_PURCH.items()}
    counts = win_lines.groupby("grn_no").size()
    used: set = set()

    def log(code, rows, detail):
        for g, ln_no in zip(rows.grn_no, rows.line_no):
            ledger.append({"stage": stage, "code": code, "source_system": "purchasing_db", "source_table": "grn_line",
                           "source_key": f"{g}|{ln_no}", "detail": detail})

    for grn_no in _pick_headers(rng, counts, target["R03_BAD_DATE"], used):
        i = grn.index[grn.grn_no == grn_no][0]
        old = pd.Timestamp(grn.at[i, "received_at"])
        grn.at[i, "received_at"] = old + pd.DateOffset(years=10)
        log("R03_BAD_DATE", gl[gl.grn_no == grn_no], f"received_at keyed as {grn.at[i, 'received_at']} (real {old})")

    free = gl.index[gl.grn_no.isin(win_grn.grn_no) & ~gl.grn_no.isin(used)].to_numpy()
    order = iter(rng.permutation(free))
    for code in ("R01_MISSING_PRODUCT", "R02_BAD_QTY", "R04_BAD_AMOUNT", "D01_EXACT_DUPLICATE"):
        for _ in range(target[code]):
            i = next(order)
            if code == "R01_MISSING_PRODUCT":
                old = gl.at[i, "vendor_item_code"]
                gl.at[i, "vendor_item_code"] = str(rng.choice([c for c, _, _ in UNKNOWN_VENDOR_ITEMS]))
                detail = f"vendor_item_code {gl.at[i, 'vendor_item_code']} (real {old})"
            elif code == "R02_BAD_QTY":
                gl.at[i, "boxes_received"] = float(rng.choice([0, -1]))
                detail = f"boxes_received {gl.at[i, 'boxes_received']}"
            elif code == "R04_BAD_AMOUNT":
                gl.at[i, "cost_per_box"] = 0.0
                detail = "cost_per_box 0.00"
            else:
                dup.append({"stage": stage, "source_system": "purchasing_db", "source_table": "grn_line",
                            "receipt_no": gl.at[i, "grn_no"], "line_no": int(gl.at[i, "line_no"])})
                detail = "exported twice"
            log(code, gl.loc[[i]], detail)

    if stage == 1:
        # R06: two opening-stock USD orders received in late Oct 2023, before the first FX rate (1 Nov 2023).
        items, sup = ref["item"], ref["supplier"]
        importer = int(sup.loc[sup.is_import, "supplier_id"].iloc[0])
        their_items = items[items.supplier_id == importer].head(2)
        for k, day in enumerate([27, 30], start=1):
            ordered = datetime(2023, 10, day - 12, 11, 0)
            received = datetime(2023, 10, day, 15, 30)
            po_no, grn_no = f"PO-2023-9000{k}", f"GRN-2023-9000{k}"
            po = pd.concat([po, pd.DataFrame([{"po_no": po_no, "supplier_id": importer, "branch_id": 4,
                                               "ordered_at": ordered, "currency": "USD", "updated_at": ordered}])],
                           ignore_index=True)
            grn = pd.concat([grn, pd.DataFrame([{"grn_no": grn_no, "po_no": po_no, "received_at": received,
                                                 "status": "POSTED", "updated_at": received + timedelta(hours=1)}])],
                            ignore_index=True)
            rows = [{"grn_no": grn_no, "line_no": j, "vendor_item_code": it.vendor_item_code,
                     "boxes_received": 2.0, "cost_per_box": round(it.base_price * it.cost_ratio * it.strips_per_box / 285.0, 2),
                     "updated_at": received + timedelta(hours=1), "_item_id": int(it.item_id),
                     "_category": it.true_category, "_currency": "USD", "received_at": received}
                    for j, it in enumerate(their_items.itertuples(), start=1)]
            gl = pd.concat([gl, pd.DataFrame(rows)], ignore_index=True)
            log("R06_NO_FX_RATE", pd.DataFrame(rows), f"USD GRN received {received:%Y-%m-%d}, first FX rate is 2023-11-01")
    return po, grn, gl


def plant_defects(ref: dict, tx: dict) -> dict:
    """Plant defects in stage-1 and stage-2 windows; returns tx with ledger and duplicate list added."""
    tx = dict(tx)
    tx["clean_receipt_line"] = tx["receipt_line"].copy()          # Finance invoices use the clean truth
    rec = tx["receipt"].copy()
    rec["_drop_header"] = False
    lin = tx["receipt_line"].copy()
    po, grn, gl = tx["purchase_order"].copy(), tx["goods_receipt"].copy(), tx["grn_line"].copy()
    ledger, dup = [], []
    for stage in (1, 2):
        rng = np.random.default_rng([SEED, 3, stage])
        rec, lin = _plant_sales(rng, rec, lin, stage, ledger, dup)
        po, grn, gl = _plant_purchases(rng, ref, po, grn, gl, stage, ledger, dup)
    tx["receipt"] = rec[~rec._drop_header].reset_index(drop=True)
    tx["receipt_line"] = lin.sort_values(["receipt_no", "line_no"]).reset_index(drop=True)
    tx["purchase_order"], tx["goods_receipt"] = po, grn
    tx["grn_line"] = gl.sort_values(["grn_no", "line_no"]).reset_index(drop=True)
    tx["ledger"] = pd.DataFrame(ledger)
    tx["double_export"] = pd.DataFrame(dup)
    return tx


def unknown_vendor_items(ref: dict) -> pd.DataFrame:
    """The two vendor items that no Inventory item points to (owned by the first local supplier)."""
    local = int(ref["supplier"].loc[~ref["supplier"].is_import, "supplier_id"].iloc[0])
    return pd.DataFrame([{"vendor_item_code": c, "supplier_id": local, "description": d, "strips_per_box": s}
                         for c, d, s in UNKNOWN_VENDOR_ITEMS])
