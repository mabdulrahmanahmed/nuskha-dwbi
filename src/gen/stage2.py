"""Generator part 4: what changes in the sources between stage 1 and stage 2. SYNTHETIC, seed 472.

Stage 2 is the state of the sources on 31 Oct 2026. Besides the new Sep-Oct 2026 rows
(made by parts 2 and 3, including the late receipts), these edits happen in Sep-Oct:

  * corrected quantities  20 stage-1 receipts: one line's qty corrected
  * corrected panel names 10 stage-1 receipts whose panel name was junk (U01) are fixed
  * cancellations         15 stage-1 receipts VOIDED; 3 stage-1 GRNs CANCELLED
  * hard deletes          3 stage-1 receipts (and their lines) deleted from Sales
  * SCD Type 1 demo       the cough syrup filed under Gastro is corrected to 'Cough and Cold'
  * late-arriving product a new product (Paracetamol 1000 mg, item 500) is added on
                          1 Sep 2026 and sold on 40 Sep-Oct lines

Rule of the till and GRN apps: any edit re-saves the whole document, so the header and
all its lines get the new updated_at (the watermark extract then sees them all).

build_stage2() returns:
  apply(frames)  edits the stage-2 frames in place (called by sources.materialize)
  intended       DataFrame of every row the edits should touch: database, table, key, change, reason
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.common import SEED
from src.gen.defects import WINDOWS, _in_window

N_QTY_FIX, N_PANEL_FIX, N_VOID, N_DELETE, N_GRN_CANCEL, N_NEW_ITEM_LINES = 20, 10, 15, 3, 3, 40
CATEGORY_FIX_DATE = "15/09/2026"
NEW_ITEM = {"item_id": 500, "generic_name": "Paracetamol", "strength": "1000 mg", "true_category": "Analgesics",
            "sell_unit": "STRIP", "item_code": "PAR-1000-STR", "tablets_per_strip": 10, "strips_per_box": 10,
            "unit_price_pkr": 140.0, "std_cost_per_unit": 101.3482, "launched": "2026-09-01"}


def _edit_time(rng) -> datetime:
    """A random moment between 2 Sep and 30 Oct 2026, during working hours."""
    day = datetime(2026, 9, 2) + timedelta(days=int(rng.integers(0, 58)))
    return day + timedelta(seconds=int(rng.integers(9 * 3600, 20 * 3600)))


def build_stage2(ref: dict, tx: dict):
    rng = np.random.default_rng([SEED, 4])
    rec, lin, ledger = tx["receipt"], tx["receipt_line"], tx["ledger"]
    grn, gl = tx["goods_receipt"], tx["grn_line"]

    # Candidates: clean stage-1 receipts (no planted defect, not late, keying-error line excluded).
    flagged = set(ledger.source_key.str.split("|").str[0])
    stage1 = rec[_in_window(rec.updated_at, 1) & (rec.status == "POSTED")]
    big_qty = set(lin.receipt_no[lin.qty >= 50])
    clean = stage1[~stage1.receipt_no.isin(flagged | big_qty)].receipt_no.to_numpy()
    picks = rng.permutation(clean)
    qty_fix = picks[:N_QTY_FIX]
    void = picks[N_QTY_FIX:N_QTY_FIX + N_VOID]
    delete = picks[N_QTY_FIX + N_VOID:N_QTY_FIX + N_VOID + N_DELETE]
    u01 = ledger[(ledger.stage == 1) & (ledger.code == "U01_UNRESOLVED_CUSTOMER")].source_key.str.split("|").str[0]
    panel_fix = rng.permutation(u01.unique())[:N_PANEL_FIX]

    grn_flagged = set(ledger.source_key[ledger.source_table == "grn_line"].str.split("|").str[0])
    grn1 = grn[_in_window(grn.updated_at, 1) & ~grn.grn_no.isin(grn_flagged)].grn_no.to_numpy()
    grn_cancel = rng.permutation(grn1)[:N_GRN_CANCEL]

    edit_ts = {r: _edit_time(rng) for r in [*qty_fix, *void, *panel_fix]}
    grn_ts = {g: _edit_time(rng) for g in grn_cancel}
    company = dict(zip(ref["panel_account"].account_no, ref["panel_account"].company_name))
    account_of = dict(zip(rec.receipt_no, rec._account_no))
    qty_line = {r: int(rng.choice(lin.line_no[lin.receipt_no == r].to_numpy())) for r in qty_fix}

    # New product sold on Sep-Oct Analgesics lines that carry no planted defect.
    new_lines_pool = lin[_in_window(lin.updated_at, 2) & (lin._category == "Analgesics")
                         & ~lin.receipt_no.isin(set(rec.receipt_no[rec._late.astype(bool)]) | flagged)]
    pool_keys = (new_lines_pool.receipt_no + "|" + new_lines_pool.line_no.astype(str)).to_numpy()
    new_item_keys = set(rng.choice(pool_keys, size=N_NEW_ITEM_LINES, replace=False))
    cough = ref["item"].loc[ref["item"].misfiled_stage1, "item_id"].iloc[0]
    items = ref["item"]
    para500 = items[(items.generic_name == "Paracetamol") & (items.strength == "500 mg")].iloc[0]
    new_vendor_code = f"{para500.vendor_item_code.split('-')[0]}-5000"

    intended = []

    def note(db, table, key, change, reason):
        intended.append({"database": db, "table": table, "key": key, "change": change, "reason": reason})

    for r in qty_fix:
        note("sales_db", "receipt", r, "changed", "quantity corrected (receipt re-saved)")
        for ln in lin.line_no[lin.receipt_no == r]:
            note("sales_db", "receipt_line", f"{r}|{ln}", "changed",
                 "quantity corrected" if ln == qty_line[r] else "receipt re-saved (updated_at)")
    for r in panel_fix:
        note("sales_db", "receipt", r, "changed", "panel customer corrected")
        for ln in lin.line_no[lin.receipt_no == r]:
            note("sales_db", "receipt_line", f"{r}|{ln}", "changed", "receipt re-saved (updated_at)")
    for r in void:
        note("sales_db", "receipt", r, "changed", "receipt VOIDED")
        for ln in lin.line_no[lin.receipt_no == r]:
            note("sales_db", "receipt_line", f"{r}|{ln}", "changed", "receipt VOIDED (re-saved)")
    for r in delete:
        note("sales_db", "receipt", r, "deleted", "receipt hard-deleted at the till")
        for ln in lin.line_no[lin.receipt_no == r]:
            note("sales_db", "receipt_line", f"{r}|{ln}", "deleted", "receipt hard-deleted at the till")
    for g in grn_cancel:
        note("purchasing_db", "goods_receipt", g, "changed", "GRN CANCELLED")
        for ln in gl.line_no[gl.grn_no == g]:
            note("purchasing_db", "grn_line", f"{g}|{ln}", "changed", "GRN CANCELLED (re-saved)")
    note("inventory", "item", str(cough), "changed", "category corrected Gastro -> Cough and Cold (SCD1)")
    note("inventory", "item", str(NEW_ITEM["item_id"]), "added", "new product launched 1 Sep 2026")
    note("inventory", "item_cost_history", f"{NEW_ITEM['item_id']}|01/09/2026", "added", "cost of the new product")
    note("sales_db", "pos_item", NEW_ITEM["item_code"], "added", "new product launched 1 Sep 2026")
    note("purchasing_db", "vendor_item", new_vendor_code, "added", "new product launched 1 Sep 2026")

    # Rows that are new in stage 2 because they were created or synced in Sep-Oct 2026.
    for _, r in rec[_in_window(rec.updated_at, 2)].iterrows():
        note("sales_db", "receipt", r.receipt_no, "added", "late receipt" if r._late else "new Sep-Oct receipt")
    for _, ln in lin[_in_window(lin.updated_at, 2)].iterrows():
        note("sales_db", "receipt_line", f"{ln.receipt_no}|{ln.line_no}", "added", "new Sep-Oct or late line")
    for _, p in tx["purchase_order"][_in_window(tx["purchase_order"].updated_at, 2)].iterrows():
        note("purchasing_db", "purchase_order", p.po_no, "added", "new Sep-Oct order")
    for _, g in grn[_in_window(grn.updated_at, 2)].iterrows():
        note("purchasing_db", "goods_receipt", g.grn_no, "added", "new Sep-Oct GRN")
    for _, g in gl[_in_window(gl.updated_at, 2)].iterrows():
        note("purchasing_db", "grn_line", f"{g.grn_no}|{g.line_no}", "added", "new Sep-Oct GRN line")
    for d in pd.date_range("2026-09-01", "2026-10-31"):
        note("finance_db", "fx_rate", d.strftime("%Y-%m-%d"), "added", "daily rate Sep-Oct")
    clean_lines = tx["clean_receipt_line"]
    panel = clean_lines[(clean_lines.customer_type == "PANEL")
                        & pd.to_datetime(clean_lines.receipt_ts).between("2026-09-01", "2026-10-31 23:59:59")]
    for acct, month in set(zip(panel._account_no.astype(int), pd.to_datetime(panel.receipt_ts).dt.strftime("%Y%m"))):
        note("finance_db", "panel_invoice", f"INV-{month}-{acct}", "added", "monthly invoice Sep-Oct")
    for s in ref["branch"].store_code:
        for item_id in ref["item"].item_id:
            note("inventory", "stock_count", f"{s}|{item_id}|30/09/2026", "added", "quarter-end count Sep 2026")

    def apply(frames: dict) -> None:
        """Edit the stage-2 frames in place (raw values; formatting happens afterwards)."""
        r = frames[("sales_db", "receipt")]
        ln = frames[("sales_db", "receipt_line")]
        for rn in qty_fix:
            r.loc[r.receipt_no == rn, "updated_at"] = edit_ts[rn]
            ln.loc[ln.receipt_no == rn, "updated_at"] = edit_ts[rn]
            m = (ln.receipt_no == rn) & (ln.line_no == qty_line[rn])
            q = float(ln.loc[m, "qty"].iloc[0])
            ln.loc[m, "qty"] = q + 1 if q < 3 else q - 1
            ln.loc[m, "discount_pkr"] = ln.loc[m, "discount_pkr"] * ((q + 1 if q < 3 else q - 1) / q)
            ln.loc[m, "discount_pkr"] = ln.loc[m, "discount_pkr"].round(2)
        for rn in panel_fix:
            r.loc[r.receipt_no == rn, ["panel_company_text", "updated_at"]] = [company[int(account_of[rn])], edit_ts[rn]]
            ln.loc[ln.receipt_no == rn, "updated_at"] = edit_ts[rn]
        for rn in void:
            r.loc[r.receipt_no == rn, ["status", "updated_at"]] = ["VOIDED", edit_ts[rn]]
            ln.loc[ln.receipt_no == rn, "updated_at"] = edit_ts[rn]
        frames[("sales_db", "receipt")] = r[~r.receipt_no.isin(delete)]
        frames[("sales_db", "receipt_line")] = ln[~ln.receipt_no.isin(delete)]
        ln = frames[("sales_db", "receipt_line")]
        keys = ln.receipt_no + "|" + ln.line_no.astype(str)
        sel = keys.isin(new_item_keys)
        ln.loc[sel, "item_code"] = NEW_ITEM["item_code"]
        ln.loc[sel, "unit_price_pkr"] = NEW_ITEM["unit_price_pkr"]
        ln.loc[sel & ln.discount_pkr.notna() & (ln.discount_pkr > 0), "discount_pkr"] = (
            0.05 * ln.qty * NEW_ITEM["unit_price_pkr"]).round(2)

        g = frames[("purchasing_db", "goods_receipt")]
        gline = frames[("purchasing_db", "grn_line")]
        for gn in grn_cancel:
            g.loc[g.grn_no == gn, ["status", "updated_at"]] = ["CANCELLED", grn_ts[gn]]
            gline.loc[gline.grn_no == gn, "updated_at"] = grn_ts[gn]

        item = frames[("inventory", "item")]
        item.loc[item.item_id == cough, ["category", "last_updated"]] = ["Cough and Cold", CATEGORY_FIX_DATE]
        frames[("inventory", "item")] = pd.concat([item, pd.DataFrame([{
            "item_id": NEW_ITEM["item_id"], "generic_name": NEW_ITEM["generic_name"], "strength": NEW_ITEM["strength"],
            "category": "Analgesics", "tablets_per_strip": NEW_ITEM["tablets_per_strip"],
            "std_cost_per_strip": NEW_ITEM["std_cost_per_unit"], "pos_code": NEW_ITEM["item_code"],
            "vendor_code": new_vendor_code, "last_updated": "01/09/2026"}])], ignore_index=True)
        frames[("inventory", "item_cost_history")] = pd.concat([frames[("inventory", "item_cost_history")],
            pd.DataFrame([{"item_id": NEW_ITEM["item_id"], "effective_from": "01/09/2026",
                           "std_cost_per_strip": NEW_ITEM["std_cost_per_unit"]}])], ignore_index=True)
        frames[("sales_db", "pos_item")] = pd.concat([frames[("sales_db", "pos_item")], pd.DataFrame([{
            "item_code": NEW_ITEM["item_code"], "item_desc": "Paracetamol 1000 mg", "sell_unit": "STRIP"}])],
            ignore_index=True)
        frames[("purchasing_db", "vendor_item")] = pd.concat([frames[("purchasing_db", "vendor_item")], pd.DataFrame([{
            "vendor_item_code": new_vendor_code, "supplier_id": int(para500.supplier_id),
            "description": "PARACETAMOL 1000MG BOX/10", "strips_per_box": NEW_ITEM["strips_per_box"]}])],
            ignore_index=True)

    intended_df = pd.DataFrame(intended).drop_duplicates(["database", "table", "key"], keep="first")
    # An edited row that is also new in stage 2 is simply 'added' (it did not exist in stage 1).
    return apply, intended_df.reset_index(drop=True)
