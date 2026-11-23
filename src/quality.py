"""Integrate, validate, quarantine and de-duplicate fact lines (units 2.07 and 2.08).

For receipt lines and GRN lines this module:
  1. removes exact duplicates: the SAME source key extracted twice (D01). A line with a new
     line number for the same customer, item and day is a real repeat and is kept;
  2. joins each line to its header, the crosswalks and (purchases) the order and supplier,
     logging the row count before and after every join (a join must never add rows);
  3. gives every invalid line ONE reason code, checked in this order, and moves it to rejects:
       R07_ORPHAN_LINE      header receipt / GRN (or its purchase order) is missing
       R03_BAD_DATE         date missing, unparseable or after the batch cut-off
       R05_UNKNOWN_BRANCH   branch text / id matches no crosswalk rule
       R01_MISSING_PRODUCT  item code unknown to every crosswalk
       R02_BAD_QTY          quantity <= 0 (or missing) on a POSTED line
       R04_BAD_AMOUNT       price / cost <= 0 or missing
       R06_NO_FX_RATE       USD line with no rate on or before the GRN date
  4. keeps the rest with canonical codes. An unresolved customer is NOT rejected: it gets
     the Unknown customer and is_customer_unresolved = true (U01).
Reconciliation rule per table: source rows = valid + rejected + duplicates removed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.normalize import convert_purchase_lines

# Header tables are kept across batches (upserted in stg), because a line extracted in this
# batch may belong to a header extracted earlier (e.g. a GRN in Sep for an order placed in Aug).
HEADER_TABLES = {"receipt": "receipt_no", "goods_receipt": "grn_no", "purchase_order": "po_no"}


def accumulate(stg: dict, previous: dict | None) -> dict:
    """Staged headers of earlier batches + this batch (this batch wins on the same key)."""
    if not previous:
        return stg
    out = dict(stg)
    for table, key in HEADER_TABLES.items():
        both = pd.concat([previous[table], stg[table]], ignore_index=True)
        out[table] = both.drop_duplicates(key, keep="last").reset_index(drop=True)
    return out


SALES_ORDER = ["R07_ORPHAN_LINE", "R03_BAD_DATE", "R05_UNKNOWN_BRANCH", "R01_MISSING_PRODUCT",
               "R02_BAD_QTY", "R04_BAD_AMOUNT"]
PURCH_ORDER = SALES_ORDER + ["R06_NO_FX_RATE"]
REASON_TEXT = {
    "R07_ORPHAN_LINE": "header record is missing",
    "R03_BAD_DATE": "date missing, unparseable or after the batch cut-off",
    "R05_UNKNOWN_BRANCH": "branch matches no crosswalk rule",
    "R01_MISSING_PRODUCT": "item code unknown to every crosswalk",
    "R02_BAD_QTY": "quantity <= 0 or missing on a POSTED line",
    "R04_BAD_AMOUNT": "price or cost <= 0 or missing",
    "R06_NO_FX_RATE": "USD line with no FX rate on or before its date",
}


def _join(left: pd.DataFrame, right: pd.DataFrame, on, log: list, step: str, **kw) -> pd.DataFrame:
    """Left join that refuses to multiply rows; the before/after count goes to the join log."""
    before = len(left)
    out = left.merge(right, on=on, how="left", **kw)
    log.append({"step": step, "rows_before": before, "rows_after": len(out), "ok": len(out) == before})
    if len(out) != before:
        raise ValueError(f"join '{step}' changed the row count {before} -> {len(out)}")
    return out


def _dedupe(lines: pd.DataFrame, key_cols: list, source_system: str, table: str, batch_id):
    key = lines[key_cols].astype(str).agg("|".join, axis=1)
    dup_mask = key.duplicated(keep="first")
    dups = pd.DataFrame({"source_system": source_system, "source_table": table, "source_key": key[dup_mask],
                         "batch_id": batch_id})
    lines = lines[~dup_mask].copy()
    lines["source_key"] = key[~dup_mask]
    return lines, dups.reset_index(drop=True)


def _xw(xw: pd.DataFrame, system: str, obj: str, key_name: str, code_name: str) -> pd.DataFrame:
    sub = xw[(xw.source_system == system) & (xw.source_object == obj)]
    return sub[["source_key", "canonical_code", "match_method"]].rename(
        columns={"source_key": key_name, "canonical_code": code_name, "match_method": code_name + "_method"})


def _first_reason(conditions: dict, order: list, index) -> pd.Series:
    reason = pd.Series(None, index=index, dtype=object)
    for code in order:
        cond = conditions[code].fillna(False).astype(bool)
        reason = reason.where(reason.notna() | ~cond, code)
    return reason


def _rejects(df: pd.DataFrame, reason: pd.Series, source_system: str, table: str, batch_id) -> pd.DataFrame:
    bad = df[reason.notna()]
    return pd.DataFrame({"source_system": source_system, "source_table": table, "source_key": bad.source_key,
                         "reason_code": reason[reason.notna()], "reason_text": reason[reason.notna()].map(REASON_TEXT),
                         "raw_record": bad.raw_json, "batch_id": batch_id}).reset_index(drop=True)


def prepare_sales(stg: dict, xw: dict, cutoff, batch_id) -> dict:
    log = []
    lines, dups = _dedupe(stg["receipt_line"], ["receipt_no", "line_no"], "sales_db", "receipt_line", batch_id)
    hdr = stg["receipt"].drop_duplicates("receipt_no").assign(_has_header=True)
    df = _join(lines, hdr.drop(columns=["updated_at"]), "receipt_no", log, "receipt_line -> receipt")
    df = _join(df, _xw(xw["xw_product"], "sales_db", "pos_item", "item_code", "product_code"), "item_code",
               log, "receipt_line -> xw_product")
    df = _join(df, _xw(xw["xw_branch"], "sales_db", "receipt.branch_name", "branch_text", "branch_code"),
               "branch_text", log, "receipt -> xw_branch")
    cards = _xw(xw["xw_customer"], "sales_db", "receipt.card_no", "card_no", "card_customer")
    df = _join(df, cards, "card_no", log, "receipt -> xw_customer (card)")
    panels = _xw(xw["xw_customer"], "sales_db", "receipt.panel_company_text", "panel_text", "panel_customer")
    df = _join(df, panels, "panel_text", log, "receipt -> xw_customer (panel text)")

    posted = df.status.eq("POSTED")
    conditions = {
        "R07_ORPHAN_LINE": df._has_header.isna(),
        "R03_BAD_DATE": df.receipt_ts.isna() | (df.receipt_ts > pd.Timestamp(cutoff)),
        "R05_UNKNOWN_BRANCH": df.branch_code.isna(),
        "R01_MISSING_PRODUCT": df.product_code.isna(),
        "R02_BAD_QTY": posted & ~(df.qty > 0),
        "R04_BAD_AMOUNT": ~(df.unit_price_pkr > 0),
    }
    reason = _first_reason(conditions, SALES_ORDER, df.index)
    rejects = _rejects(df, reason, "sales_db", "receipt_line", batch_id)
    valid = df[reason.isna()].copy()

    customer = np.select([valid.customer_type.eq("WALKIN"), valid.customer_type.eq("LOYALTY"),
                          valid.customer_type.eq("PANEL")],
                         [pd.Series("WALKIN", index=valid.index), valid.card_customer, valid.panel_customer],
                         default=None)
    valid["customer_code"] = pd.Series(customer, index=valid.index).where(lambda s: s.notna(), None)
    valid["is_customer_unresolved"] = valid.customer_code.isna()
    valid["is_cancelled"] = valid.status.eq("VOIDED")
    valid["batch_id"] = batch_id
    return {"valid": valid.reset_index(drop=True), "rejects": rejects, "duplicates": dups,
            "join_log": pd.DataFrame(log).assign(fact="sales"), "source_rows": len(stg["receipt_line"])}


def prepare_purchases(stg: dict, xw: dict, cutoff, batch_id) -> dict:
    log = []
    lines, dups = _dedupe(stg["grn_line"], ["grn_no", "line_no"], "purchasing_db", "grn_line", batch_id)
    hdr = stg["goods_receipt"].drop_duplicates("grn_no")[["grn_no", "po_no", "received_at", "status"]]
    df = _join(lines, hdr.assign(_has_header=True), "grn_no", log, "grn_line -> goods_receipt")
    po = stg["purchase_order"].drop_duplicates("po_no")[["po_no", "supplier_id", "branch_id", "currency"]]
    df = _join(df, po.assign(_has_po=True), "po_no", log, "goods_receipt -> purchase_order")
    vi = stg["vendor_item"].drop_duplicates("vendor_item_code")[["vendor_item_code", "strips_per_box"]]
    df = _join(df, vi, "vendor_item_code", log, "grn_line -> vendor_item")
    df = convert_purchase_lines(df, stg["fx_rate"])           # units and PKR (needs header + order)
    df = _join(df, _xw(xw["xw_product"], "purchasing_db", "vendor_item", "vendor_item_code", "product_code"),
               "vendor_item_code", log, "grn_line -> xw_product")
    br = _xw(xw["xw_branch"], "purchasing_db", "branch", "branch_id_text", "branch_code")
    df["branch_id_text"] = df.branch_id.astype("string")
    df = _join(df, br, "branch_id_text", log, "purchase_order -> xw_branch")
    sup = stg["supplier"].drop_duplicates("supplier_id")[["supplier_id", "is_import"]]
    df = _join(df, sup, "supplier_id", log, "purchase_order -> supplier")

    conditions = {
        "R07_ORPHAN_LINE": df._has_header.isna() | df._has_po.isna(),
        "R03_BAD_DATE": df.received_at.isna() | (df.received_at > pd.Timestamp(cutoff)),
        "R05_UNKNOWN_BRANCH": df.branch_code.isna(),
        "R01_MISSING_PRODUCT": df.product_code.isna(),
        "R02_BAD_QTY": df.status.eq("POSTED") & ~(df.boxes_received > 0),
        "R04_BAD_AMOUNT": ~(df.cost_per_box > 0),
        "R06_NO_FX_RATE": df.currency.eq("USD") & df.fx_rate_used.isna(),
    }
    reason = _first_reason(conditions, PURCH_ORDER, df.index)
    rejects = _rejects(df, reason, "purchasing_db", "grn_line", batch_id)
    valid = df[reason.isna()].copy()
    valid["supplier_code"] = valid.supplier_id.map(lambda s: f"S-{int(s):03d}")
    valid["is_cancelled"] = valid.status.eq("CANCELLED")
    valid["batch_id"] = batch_id
    return {"valid": valid.reset_index(drop=True), "rejects": rejects, "duplicates": dups,
            "join_log": pd.DataFrame(log).assign(fact="purchases"), "source_rows": len(stg["grn_line"])}
