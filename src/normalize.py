"""Normalize raw snapshots into typed staging tables (unit 2.04). Synthetic data.

What happens to the data (the transform rules, also listed in meta.transform_rule):
  R-DATE-01  MySQL DATETIME / PostgreSQL TIMESTAMPTZ / Inventory 'DD/MM/YYYY' text -> real dates
             (TIMESTAMPTZ is kept as Karachi local time; unparseable -> empty, rejected later as R03)
  R-TEXT-01  trim spaces; branch text compared in upper case without dots and hyphens
  R-CAT-01   Inventory category: trim + case-insensitive match to the 8 canonical names
  R-UNIT-01  boxes -> selling units: boxes_received x strips_per_box (vendor_item)
  R-UNIT-02  tablets -> selling units: tablets_on_hand / tablets_per_strip (stock counts)
  R-MONEY-01 REAL cost -> 2 decimals; every amount rounded to 2 decimals
  R-MONEY-02 missing discount -> 0
  R-FX-01    USD -> PKR at the Finance rate on or before the GRN received date (none -> R06)

Input: {(database, table): DataFrame of text} from src.raw.read_raw().
Output: {staging table name: DataFrame}, names as in the stg schema (without 'stg.').
Nothing is dropped here; rows that cannot be cleaned keep empty values and are
rejected by src/quality.py with a reason code.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

CATEGORIES = ["Analgesics", "Antibiotics", "Cardiovascular", "Diabetes Care", "Gastro", "Cough and Cold",
              "Vitamins and Supplements", "Personal Care"]
_CATEGORY_LOOKUP = {c.casefold(): c for c in CATEGORIES}


def text(s: pd.Series) -> pd.Series:
    """Trim spaces and collapse inner runs of spaces; None stays None."""
    return s.map(lambda v: " ".join(str(v).split()) if v is not None and not pd.isna(v) else None)


def branch_norm(s: pd.Series) -> pd.Series:
    """Comparable form of a branch name: upper case, no dots, hyphens as spaces, single spaces."""
    return s.map(lambda v: " ".join(str(v).upper().replace(".", "").replace("-", " ").split())
                 if v is not None and not pd.isna(v) else None)


def to_ts(s: pd.Series) -> pd.Series:
    """Text timestamp -> pandas Timestamp (local time). '+05:00' offsets are dropped (all Karachi)."""
    return pd.to_datetime(s.astype("string").str[:19], format="%Y-%m-%d %H:%M:%S", errors="coerce")


def to_date_dmy(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype("string"), format="%d/%m/%Y", errors="coerce")


def to_num(s: pd.Series, decimals: int | None = 2) -> pd.Series:
    n = pd.to_numeric(s, errors="coerce")
    return n.round(decimals) if decimals is not None else n


def to_int(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def raw_json(df: pd.DataFrame) -> pd.Series:
    """The raw row as JSON text, kept for etl.rejects."""
    cols = list(df.columns)
    return pd.Series([json.dumps(dict(zip(cols, row)), ensure_ascii=False) for row in df.itertuples(index=False)],
                     index=df.index)


def canonical_category(s: pd.Series) -> pd.Series:
    return text(s).map(lambda v: _CATEGORY_LOOKUP.get(v.casefold(), "Not recorded") if v else "Not recorded")


def fx_on_or_before(dates: pd.Series, fx: pd.DataFrame) -> pd.Series:
    """For each date, the USD/PKR rate on that day or the latest earlier day (NaN if none)."""
    left = pd.DataFrame({"d": dates.values, "pos": np.arange(len(dates))}).dropna(subset=["d"])
    left = left.sort_values("d")
    right = fx[["rate_date", "usd_pkr"]].dropna().sort_values("rate_date")
    m = pd.merge_asof(left, right, left_on="d", right_on="rate_date", direction="backward")
    out = pd.Series(np.nan, index=range(len(dates)))
    out.loc[m["pos"].to_numpy()] = m["usd_pkr"].to_numpy()
    out.index = dates.index
    return out


def normalize(raw: dict) -> dict:
    stg = {}
    g = raw.get

    # ---------------- Sales ----------------
    r = g(("sales_db", "receipt"))
    stg["receipt"] = pd.DataFrame({
        "receipt_no": text(r.receipt_no), "branch_text": text(r.branch_name),
        "branch_norm": branch_norm(r.branch_name), "receipt_ts": to_ts(r.receipt_ts),
        "customer_type": text(r.customer_type), "card_no": text(r.card_no),
        "panel_text": text(r.panel_company_text), "status": text(r.status), "updated_at": to_ts(r.updated_at)})
    stg["receipt"]["receipt_date"] = stg["receipt"].receipt_ts.dt.normalize()

    ln = g(("sales_db", "receipt_line"))
    qty, price = to_num(ln.qty), to_num(ln.unit_price_pkr)
    disc = to_num(ln.discount_pkr)
    gross = (qty * price).round(2)
    stg["receipt_line"] = pd.DataFrame({
        "receipt_no": text(ln.receipt_no), "line_no": to_int(ln.line_no), "item_code": text(ln.item_code),
        "qty": qty, "unit_price_pkr": price, "discount_pkr": disc.fillna(0.0),
        "discount_was_missing": disc.isna(), "gross_amount_pkr": gross,
        "net_amount_pkr": (gross - disc.fillna(0.0)).round(2), "updated_at": to_ts(ln.updated_at),
        "raw_json": raw_json(ln)})

    pi = g(("sales_db", "pos_item"))
    stg["pos_item"] = pd.DataFrame({"item_code": text(pi.item_code), "item_desc": text(pi.item_desc),
                                    "sell_unit": text(pi.sell_unit).str.upper()})
    lm = g(("sales_db", "loyalty_member"))
    stg["loyalty_member"] = pd.DataFrame({"card_no": text(lm.card_no), "member_name": text(lm.member_name),
                                          "joined_on": pd.to_datetime(lm.joined_on, errors="coerce")})

    # ---------------- Finance ----------------
    fx_raw = g(("finance_db", "fx_rate"))
    fx = pd.DataFrame({"rate_date": pd.to_datetime(fx_raw.rate_date, errors="coerce"),
                       "usd_pkr": to_num(fx_raw.usd_pkr, 4)})
    stg["fx_rate"] = fx
    pa = g(("finance_db", "panel_account"))
    stg["panel_account"] = pd.DataFrame({
        "account_no": to_int(pa.account_no), "company_name": text(pa.company_name),
        "credit_limit_pkr": to_num(pa.credit_limit_pkr), "terms_days": to_int(pa.terms_days),
        "updated_at": to_ts(pa.updated_at)})
    pv = g(("finance_db", "panel_invoice"))
    stg["panel_invoice"] = pd.DataFrame({
        "invoice_no": text(pv.invoice_no), "account_no": to_int(pv.account_no),
        "month_start": pd.to_datetime(pv.month_start, errors="coerce"), "amount_pkr": to_num(pv.amount_pkr)})

    # ---------------- Inventory ----------------
    it = g(("inventory", "item"))
    stg["item"] = pd.DataFrame({
        "item_id": to_int(it.item_id), "generic_name": text(it.generic_name), "strength": text(it.strength),
        "category_raw": it.category, "category": canonical_category(it.category),
        "tablets_per_strip": to_int(it.tablets_per_strip), "std_cost_per_unit": to_num(it.std_cost_per_strip),
        "pos_code": text(it.pos_code).str.upper(), "vendor_code": text(it.vendor_code).str.upper(),
        "pos_code_raw": it.pos_code, "vendor_code_raw": it.vendor_code,      # as typed (exact matching)
        "last_updated": to_date_dmy(it.last_updated)})
    ch = g(("inventory", "item_cost_history"))
    stg["item_cost_history"] = pd.DataFrame({
        "item_id": to_int(ch.item_id), "effective_from": to_date_dmy(ch.effective_from),
        "std_cost_per_unit": to_num(ch.std_cost_per_strip)})
    st = g(("inventory", "store"))
    stg["store"] = pd.DataFrame({"store_code": text(st.store_code), "store_name": text(st.store_name),
                                 "area": text(st.area), "region": text(st.region)})
    sc = g(("inventory", "stock_count"))
    tps = stg["item"].set_index("item_id").tablets_per_strip
    sc_item = to_int(sc.item_id)
    tablets = to_int(sc.tablets_on_hand)
    stg["stock_count"] = pd.DataFrame({
        "store_code": text(sc.store_code), "item_id": sc_item, "count_date": to_date_dmy(sc.count_date),
        "tablets_on_hand": tablets,
        "units_on_hand": (tablets.astype(float) / sc_item.map(tps).astype(float)).round(2)})

    # ---------------- Purchasing ----------------
    sp = g(("purchasing_db", "supplier"))
    stg["supplier"] = pd.DataFrame({"supplier_id": to_int(sp.supplier_id), "supplier_name": text(sp.supplier_name),
                                    "country": text(sp.country), "is_import": sp.is_import.str.lower().eq("true")})
    br = g(("purchasing_db", "branch"))
    label = text(br.branch_label)
    stg["branch"] = pd.DataFrame({"branch_id": to_int(br.branch_id), "branch_label": label,
                                  "branch_norm": branch_norm(label.str.replace(r"\s*Br\.?$", "", regex=True))})
    vi = g(("purchasing_db", "vendor_item"))
    stg["vendor_item"] = pd.DataFrame({"vendor_item_code": text(vi.vendor_item_code).str.upper(),
                                       "supplier_id": to_int(vi.supplier_id), "description": text(vi.description),
                                       "strips_per_box": to_int(vi.strips_per_box)})
    po = g(("purchasing_db", "purchase_order"))
    stg["purchase_order"] = pd.DataFrame({
        "po_no": text(po.po_no), "supplier_id": to_int(po.supplier_id), "branch_id": to_int(po.branch_id),
        "ordered_at": to_ts(po.ordered_at), "currency": text(po.currency).str.upper(),
        "updated_at": to_ts(po.updated_at)})
    gr = g(("purchasing_db", "goods_receipt"))
    stg["goods_receipt"] = pd.DataFrame({
        "grn_no": text(gr.grn_no), "po_no": text(gr.po_no), "received_at": to_ts(gr.received_at),
        "status": text(gr.status).str.upper(), "updated_at": to_ts(gr.updated_at)})
    stg["goods_receipt"]["received_date"] = stg["goods_receipt"].received_at.dt.normalize()

    gl = g(("purchasing_db", "grn_line"))
    boxes, cost_box = to_num(gl.boxes_received), to_num(gl.cost_per_box)
    stg["grn_line"] = pd.DataFrame({
        "grn_no": text(gl.grn_no), "line_no": to_int(gl.line_no),
        "vendor_item_code": text(gl.vendor_item_code).str.upper(), "boxes_received": boxes,
        "cost_per_box": cost_box, "amount_original": (boxes * cost_box).round(2),
        "updated_at": to_ts(gl.updated_at), "raw_json": raw_json(gl)})
    return stg


def convert_purchase_lines(lines: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    """R-UNIT-01 and R-FX-01 on GRN lines that already carry their header and order columns.

    Needs: boxes_received, strips_per_box, amount_original, received_at, currency.
    Runs after the joins in quality.py because a GRN line's order may have been extracted in
    an earlier batch (an order placed in August and received in September).
    """
    out = lines.copy()
    out["received_date"] = out.received_at.dt.normalize()
    out["quantity_units"] = (out.boxes_received * out.strips_per_box.astype(float)).round(2)
    usd_rate = fx_on_or_before(out.received_date, fx)
    out["fx_rate_used"] = np.where(out.currency.eq("PKR"), 1.0, usd_rate)
    out["purchase_amount_pkr"] = (out.amount_original * out.fx_rate_used).round(2)
    return out


# Which staging table each raw table becomes (for the before/after profile pairs).
STAGING_OF = {
    ("sales_db", "receipt"): "receipt", ("sales_db", "receipt_line"): "receipt_line",
    ("sales_db", "pos_item"): "pos_item", ("sales_db", "loyalty_member"): "loyalty_member",
    ("finance_db", "fx_rate"): "fx_rate", ("finance_db", "panel_account"): "panel_account",
    ("finance_db", "panel_invoice"): "panel_invoice", ("inventory", "item"): "item",
    ("inventory", "item_cost_history"): "item_cost_history", ("inventory", "store"): "store",
    ("inventory", "stock_count"): "stock_count", ("purchasing_db", "supplier"): "supplier",
    ("purchasing_db", "branch"): "branch", ("purchasing_db", "vendor_item"): "vendor_item",
    ("purchasing_db", "purchase_order"): "purchase_order", ("purchasing_db", "goods_receipt"): "goods_receipt",
    ("purchasing_db", "grn_line"): "grn_line",
}
