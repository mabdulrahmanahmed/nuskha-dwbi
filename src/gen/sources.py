"""Turn generator data into the source tables, as each system holds them at a stage. SYNTHETIC.

A stage is the state of the four source systems on a given day:
  stage 1 = 31 Aug 2026 23:59:59 (batch 1 extract), stage 2 = 31 Oct 2026 23:59:59 (batch 2).
A transaction row belongs to a stage when its updated_at is on or before the stage cut-off;
master tables (items, cost history, FX...) keep only what existed by then.

materialize() returns {database: {table: DataFrame}} with exactly the blueprint's columns,
formatted the way each engine stores them:
  MySQL DATETIME 'YYYY-MM-DD HH:MM:SS', PostgreSQL TIMESTAMPTZ '...+05:00',
  Inventory (legacy SQLite) dates as 'DD/MM/YYYY' text and cost as REAL.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from src.gen.transactions import STAGE1_CUTOFF, STAGE2_CUTOFF

CUTOFFS = {1: STAGE1_CUTOFF, 2: STAGE2_CUTOFF}

# Exact source columns per table (blueprint DDL order).
COLUMNS = {
    ("sales_db", "loyalty_member"): ["card_no", "member_name", "joined_on"],
    ("sales_db", "pos_item"): ["item_code", "item_desc", "sell_unit"],
    ("sales_db", "receipt"): ["receipt_no", "branch_name", "receipt_ts", "customer_type", "card_no",
                              "panel_company_text", "status", "updated_at"],
    ("sales_db", "receipt_line"): ["receipt_no", "line_no", "item_code", "qty", "unit_price_pkr",
                                   "discount_pkr", "updated_at"],
    ("purchasing_db", "supplier"): ["supplier_id", "supplier_name", "country", "is_import"],
    ("purchasing_db", "branch"): ["branch_id", "branch_label"],
    ("purchasing_db", "vendor_item"): ["vendor_item_code", "supplier_id", "description", "strips_per_box"],
    ("purchasing_db", "purchase_order"): ["po_no", "supplier_id", "branch_id", "ordered_at", "currency", "updated_at"],
    ("purchasing_db", "goods_receipt"): ["grn_no", "po_no", "received_at", "status", "updated_at"],
    ("purchasing_db", "grn_line"): ["grn_no", "line_no", "vendor_item_code", "boxes_received", "cost_per_box",
                                    "updated_at"],
    ("inventory", "item"): ["item_id", "generic_name", "strength", "category", "tablets_per_strip",
                            "std_cost_per_strip", "pos_code", "vendor_code", "last_updated"],
    ("inventory", "store"): ["store_code", "store_name", "area", "region"],
    ("inventory", "stock_count"): ["store_code", "item_id", "count_date", "tablets_on_hand"],
    ("inventory", "item_cost_history"): ["item_id", "effective_from", "std_cost_per_strip"],
    ("finance_db", "panel_account"): ["account_no", "company_name", "credit_limit_pkr", "terms_days", "updated_at"],
    ("finance_db", "fx_rate"): ["rate_date", "usd_pkr"],
    ("finance_db", "panel_invoice"): ["invoice_no", "account_no", "month_start", "amount_pkr"],
}

# Primary (or identifying) key per table, used for diffs and checksums.
KEYS = {
    "loyalty_member": ["card_no"], "pos_item": ["item_code"], "receipt": ["receipt_no"],
    "receipt_line": ["receipt_no", "line_no"], "supplier": ["supplier_id"], "branch": ["branch_id"],
    "vendor_item": ["vendor_item_code"], "purchase_order": ["po_no"], "goods_receipt": ["grn_no"],
    "grn_line": ["grn_no", "line_no"], "item": ["item_id"], "store": ["store_code"],
    "stock_count": ["store_code", "item_id", "count_date"], "item_cost_history": ["item_id", "effective_from"],
    "panel_account": ["account_no"], "fx_rate": ["rate_date"], "panel_invoice": ["invoice_no"],
}


def mysql_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.strftime("%Y-%m-%d %H:%M:%S")


def pg_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.strftime("%Y-%m-%d %H:%M:%S") + "+05:00"


def dmy(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.strftime("%d/%m/%Y")


def money_text(s: pd.Series) -> pd.Series:
    """Format numbers with 2 decimals; missing stays empty (NULL)."""
    return s.map(lambda v: "" if pd.isna(v) else f"{v:.2f}")


def _upto(df: pd.DataFrame, col: str, cutoff) -> pd.DataFrame:
    return df[pd.to_datetime(df[col]) <= pd.Timestamp(cutoff)]


def panel_invoices(lines: pd.DataFrame) -> pd.DataFrame:
    """Monthly invoice per panel company: what its staff bought that month (net PKR)."""
    p = lines[lines.customer_type == "PANEL"].copy()
    p["net"] = p.qty * p.unit_price_pkr - p.discount_pkr.fillna(0)
    p["month_start"] = pd.to_datetime(p.receipt_ts).dt.to_period("M").dt.to_timestamp()
    inv = p.groupby(["_account_no", "month_start"], as_index=False)["net"].sum()
    inv["account_no"] = inv["_account_no"].astype(int)
    inv["invoice_no"] = "INV-" + inv.month_start.dt.strftime("%Y%m") + "-" + inv.account_no.astype(str)
    inv["amount_pkr"] = inv.net.round(2)
    inv["month_end"] = inv.month_start + pd.offsets.MonthEnd(0)
    return inv


def materialize(ref: dict, tx: dict, stage: int, changes=None) -> dict:
    """Source tables as they stand at the end of a stage.

    `changes` (generator part 4, stage 2 only) is a function that edits the stage-2
    frames in place: corrections, cancellations, deletions, the category fix.
    """
    cutoff = CUTOFFS[stage]
    items = ref["item"]
    out: dict = {}

    # ---------------- Sales (MySQL sales_db) ----------------
    members = ref["loyalty_member"].copy()
    members["joined_on"] = pd.to_datetime(members.joined_on).dt.strftime("%Y-%m-%d")
    pos_item = pd.DataFrame({"item_code": items.item_code,
                             "item_desc": items.generic_name + " " + items.strength,
                             "sell_unit": items.sell_unit})
    pos_item = pd.concat([pos_item, ref["unknown_pos_item"]], ignore_index=True)
    receipts = _upto(tx["receipt"], "updated_at", cutoff).copy()
    lines = _upto(tx["receipt_line"], "updated_at", cutoff).copy()

    # ---------------- Purchasing (PostgreSQL purchasing_db) ----------------
    suppliers = ref["supplier"][["supplier_id", "supplier_name", "country", "is_import"]].copy()
    branch = ref["branch"][["branch_id", "branch_label"]].sort_values("branch_id")
    vendor_item = pd.DataFrame({
        "vendor_item_code": items.vendor_item_code, "supplier_id": items.supplier_id,
        "description": items.generic_name.str.upper() + " " + items.strength.str.replace(" ", "").str.upper()
        + " BOX/" + items.strips_per_box.astype(str),
        "strips_per_box": items.strips_per_box})
    if "unknown_vendor_item" in ref:
        vendor_item = pd.concat([vendor_item, ref["unknown_vendor_item"]], ignore_index=True)
    po = _upto(tx["purchase_order"], "updated_at", cutoff).copy()
    grn = _upto(tx["goods_receipt"], "updated_at", cutoff).copy()
    gl = _upto(tx["grn_line"], "updated_at", cutoff).copy()

    # ---------------- Inventory (SQLite) ----------------
    costs = ref["cost_history"].copy()
    costs = costs[pd.to_datetime(costs.effective_from) <= pd.Timestamp(cutoff)]
    latest = costs.sort_values("effective_from").groupby("item_id").last()
    inv_item = pd.DataFrame({
        "item_id": items.item_id, "generic_name": items.generic_name, "strength": items.strength,
        "category": items.inv_category_text, "tablets_per_strip": items.tablets_per_strip,
        "std_cost_per_strip": items.item_id.map(latest.std_cost_per_unit),
        "pos_code": items.inv_pos_code, "vendor_code": items.inv_vendor_code,
        "last_updated": dmy(items.item_id.map(latest.effective_from))})
    store = ref["branch"][["store_code", "store_name", "area", "region"]].copy()
    stock = tx["stock_count"]
    stock = stock[pd.to_datetime(stock._count_date) <= pd.Timestamp(cutoff)].copy()
    stock["count_date"] = dmy(stock._count_date)
    cost_hist = pd.DataFrame({"item_id": costs.item_id, "effective_from": dmy(costs.effective_from),
                              "std_cost_per_strip": costs.std_cost_per_unit})

    # ---------------- Finance (MySQL finance_db) ----------------
    panel = ref["panel_account"].copy()
    panel["updated_at"] = mysql_ts(panel.updated_at)
    fx = ref["fx_rate"][pd.to_datetime(ref["fx_rate"].rate_date) <= pd.Timestamp(cutoff)].copy()
    fx["rate_date"] = pd.to_datetime(fx.rate_date).dt.strftime("%Y-%m-%d")
    fx["usd_pkr"] = fx.usd_pkr.map(lambda v: f"{v:.4f}")
    inv = panel_invoices(tx["clean_receipt_line"] if "clean_receipt_line" in tx else tx["receipt_line"])
    inv = inv[inv.month_end <= pd.Timestamp(cutoff)].copy()
    inv["month_start"] = inv.month_start.dt.strftime("%Y-%m-%d")

    frames = {
        ("sales_db", "loyalty_member"): members, ("sales_db", "pos_item"): pos_item,
        ("sales_db", "receipt"): receipts, ("sales_db", "receipt_line"): lines,
        ("purchasing_db", "supplier"): suppliers, ("purchasing_db", "branch"): branch,
        ("purchasing_db", "vendor_item"): vendor_item, ("purchasing_db", "purchase_order"): po,
        ("purchasing_db", "goods_receipt"): grn, ("purchasing_db", "grn_line"): gl,
        ("inventory", "item"): inv_item, ("inventory", "store"): store,
        ("inventory", "stock_count"): stock, ("inventory", "item_cost_history"): cost_hist,
        ("finance_db", "panel_account"): panel, ("finance_db", "fx_rate"): fx,
        ("finance_db", "panel_invoice"): inv,
    }
    if changes is not None and stage == 2:
        changes(frames)

    # Final formatting per engine, then keep only the source columns.
    r = frames[("sales_db", "receipt")]
    r["receipt_ts"], r["updated_at"] = mysql_ts(r.receipt_ts), mysql_ts(r.updated_at)
    ln = frames[("sales_db", "receipt_line")]
    ln["updated_at"] = mysql_ts(ln.updated_at)
    for c in ("qty", "unit_price_pkr", "discount_pkr"):
        ln[c] = money_text(ln[c])
    p = frames[("purchasing_db", "purchase_order")]
    p["ordered_at"], p["updated_at"] = pg_ts(p.ordered_at), pg_ts(p.updated_at)
    g = frames[("purchasing_db", "goods_receipt")]
    g["received_at"], g["updated_at"] = pg_ts(g.received_at), pg_ts(g.updated_at)
    gl = frames[("purchasing_db", "grn_line")]
    gl["updated_at"] = pg_ts(gl.updated_at)
    for c in ("boxes_received", "cost_per_box"):
        gl[c] = money_text(gl[c])
    s = frames[("purchasing_db", "supplier")]
    s["is_import"] = s.is_import.map({True: "true", False: "false"})
    pa = frames[("finance_db", "panel_account")]
    pa["credit_limit_pkr"] = money_text(pa.credit_limit_pkr)
    pi = frames[("finance_db", "panel_invoice")]
    pi["amount_pkr"] = money_text(pi.amount_pkr)

    for (db, table), df in frames.items():
        cols = COLUMNS[(db, table)]
        df = df[cols].sort_values(KEYS[table]).reset_index(drop=True)
        out.setdefault(db, {})[table] = df
    return out
