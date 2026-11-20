"""Build warehouse dimension and fact rows from staged data (units 3.02 and 3.03).

This part needs no database: it turns staged, validated data into rows shaped exactly
like the dw tables in docs/blueprint.md. Writing them (upserts on business / natural
keys, one transaction per fact table) is added in units 3.02-3.03 on top of these builders.

Rules applied here:
  * every dimension has an Unknown member (key -1); dim_customer also Walk-in (key 0)
  * surrogate keys are stable integers: product_key = Inventory item_id, supplier_key =
    supplier_id, branch/customer keys are given once in code order and never renumbered
    (pass the existing key map so new members get new keys and old ones keep theirs)
  * missing descriptive attributes become 'Not recorded'
  * cost_amount_pkr = quantity x the Inventory standard cost effective on the receipt date
    (cost history), never the current cost in dim_product (so SCD1 never rewrites margins)
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.common import CONFIG_DIR

DATE_FROM, DATE_TO = date(2023, 11, 1), date(2027, 1, 31)
NOT_RECORDED = "Not recorded"


def _keys(codes, existing: dict | None, start: int = 1) -> dict:
    """Stable surrogate keys: keep existing ones, give new codes the next free numbers."""
    keys = dict(existing or {})
    nxt = max([k for k in keys.values() if k > 0], default=start - 1) + 1
    for c in sorted(set(codes)):
        if c not in keys:
            keys[c] = nxt
            nxt += 1
    return keys


def build_dim_date() -> pd.DataFrame:
    d = pd.date_range(DATE_FROM, DATE_TO, freq="D")
    ram = pd.read_csv(CONFIG_DIR / "ramadan_dates.csv", parse_dates=["start_date", "end_date"])
    is_ramadan = np.zeros(len(d), dtype=bool)
    for r in ram.itertuples():
        is_ramadan |= (d >= r.start_date) & (d <= r.end_date)
    fiscal_year_end = np.where(d.month >= 7, d.year + 1, d.year)          # FY2026 = Jul 2025 - Jun 2026
    return pd.DataFrame({
        "date_key": d.strftime("%Y%m%d").astype(int), "full_date": d.date,
        "month_start": d.to_period("M").to_timestamp().date, "month_name": d.strftime("%B"),
        "quarter": d.quarter, "year": d.year,
        "fiscal_quarter": ((d.month - 7) % 12) // 3 + 1,                    # Jul-Sep = 1
        "fiscal_year": [f"FY{y}" for y in fiscal_year_end], "is_ramadan": is_ramadan})


def build_dim_product(stg: dict, xw: dict, batch_id: int) -> pd.DataFrame:
    item = stg["item"].drop_duplicates("item_id")
    sales_xw = xw["xw_product"][xw["xw_product"].source_system == "sales_db"].dropna(subset=["canonical_code"])
    unit = sales_xw.merge(stg["pos_item"], left_on="source_key", right_on="item_code")
    unit_of = unit.drop_duplicates("canonical_code").set_index("canonical_code").sell_unit
    codes = item.item_id.map(lambda i: f"P-{int(i):04d}")
    dim = pd.DataFrame({
        "product_key": item.item_id.astype(int), "product_code": codes,
        "generic_name": item.generic_name.fillna(NOT_RECORDED), "strength": item.strength.fillna(NOT_RECORDED),
        "category": item.category.fillna(NOT_RECORDED), "selling_unit": codes.map(unit_of).fillna(NOT_RECORDED),
        "tablets_per_unit": item.tablets_per_strip, "std_cost_per_unit": item.std_cost_per_unit.fillna(0.0),
        "updated_batch_id": batch_id})
    unknown = pd.DataFrame.from_records([{
        "product_key": -1, "product_code": "UNKNOWN", "generic_name": "Unknown", "strength": NOT_RECORDED,
        "category": "Unknown", "selling_unit": NOT_RECORDED, "tablets_per_unit": 0, "std_cost_per_unit": 0.0,
        "updated_batch_id": batch_id}])
    out = pd.concat([unknown.astype(dim.dtypes.to_dict()), dim], ignore_index=True)
    out.loc[out.product_key == -1, "tablets_per_unit"] = pd.NA      # not applicable to Unknown
    return out


def build_dim_branch(stg: dict, existing: dict | None = None) -> pd.DataFrame:
    st = stg["store"].drop_duplicates("store_code")
    keys = _keys(st.store_code, existing)
    dim = pd.DataFrame({"branch_key": st.store_code.map(keys), "branch_code": st.store_code,
                        "branch_name": st.store_name.str.replace("Nuskha ", "", regex=False).fillna(NOT_RECORDED),
                        "area": st.area.fillna(NOT_RECORDED), "region": st.region.fillna(NOT_RECORDED)})
    unknown = {"branch_key": -1, "branch_code": "UNKNOWN", "branch_name": "Unknown", "area": "Unknown",
               "region": "Unknown"}
    return pd.concat([pd.DataFrame([unknown]), dim.sort_values("branch_key")], ignore_index=True)


def build_dim_customer(stg: dict, batch_id: int, existing: dict | None = None) -> pd.DataFrame:
    members = stg["loyalty_member"].drop_duplicates("card_no")
    panel = stg["panel_account"].drop_duplicates("account_no")
    records = [{"customer_code": "L-" + "".join(ch for ch in m.card_no if ch.isdigit()), "customer_type": "LOYALTY",
                "customer_name": m.member_name or NOT_RECORDED, "panel_terms_days": None}
               for m in members.itertuples()]
    records += [{"customer_code": f"PANEL-{p.account_no}", "customer_type": "PANEL",
                 "customer_name": p.company_name or NOT_RECORDED, "panel_terms_days": p.terms_days}
                for p in panel.itertuples()]
    keys = _keys([r["customer_code"] for r in records], existing)
    special = [{"customer_key": -1, "customer_code": "UNKNOWN", "customer_type": "UNKNOWN",
                "customer_name": "Unknown", "panel_terms_days": None},
               {"customer_key": 0, "customer_code": "WALKIN", "customer_type": "WALKIN",
                "customer_name": "Walk-in customer", "panel_terms_days": None}]
    rows = special + sorted(({"customer_key": keys[r["customer_code"]], **r} for r in records),
                            key=lambda r: r["customer_key"])
    out = pd.DataFrame.from_records(rows)
    out["panel_terms_days"] = out.panel_terms_days.astype("Int64")
    out["updated_batch_id"] = batch_id
    return out


def build_dim_supplier(stg: dict) -> pd.DataFrame:
    sp = stg["supplier"].drop_duplicates("supplier_id")
    dim = pd.DataFrame({"supplier_key": sp.supplier_id.astype(int),
                        "supplier_code": sp.supplier_id.map(lambda s: f"S-{int(s):03d}"),
                        "supplier_name": sp.supplier_name.fillna(NOT_RECORDED),
                        "origin": np.where(sp.is_import, "IMPORT", "LOCAL")})
    unknown = {"supplier_key": -1, "supplier_code": "UNKNOWN", "supplier_name": "Unknown", "origin": "Unknown"}
    return pd.concat([pd.DataFrame([unknown]), dim], ignore_index=True)


def cost_on_date(item_ids: pd.Series, dates: pd.Series, cost_history: pd.DataFrame) -> pd.Series:
    """Standard cost per unit effective on each date (latest effective_from on or before it)."""
    left = pd.DataFrame({"item_id": item_ids.astype("int64").values, "d": pd.to_datetime(dates).values,
                         "pos": np.arange(len(dates))}).sort_values("d")
    right = cost_history.dropna().astype({"item_id": "int64"}).sort_values("effective_from")
    m = pd.merge_asof(left, right, left_on="d", right_on="effective_from", by="item_id", direction="backward")
    return pd.Series(m.sort_values("pos").std_cost_per_unit.to_numpy(), index=item_ids.index)


def build_fact_sales(valid: pd.DataFrame, stg: dict, dims: dict) -> pd.DataFrame:
    branch_key = dims["dim_branch"].set_index("branch_code").branch_key
    cust_key = dims["dim_customer"].set_index("customer_code").customer_key
    item_id = valid.product_code.str[2:].astype(int)
    unit_cost = cost_on_date(item_id, valid.receipt_date, stg["item_cost_history"])
    cost = (valid.qty * unit_cost).round(2)
    return pd.DataFrame({
        "date_key": valid.receipt_date.dt.strftime("%Y%m%d").astype(int), "product_key": item_id,
        "branch_key": valid.branch_code.map(branch_key).astype(int),
        "customer_key": valid.customer_code.map(cust_key).fillna(-1).astype(int),
        "receipt_no": valid.receipt_no, "line_no": valid.line_no.astype(int), "quantity_units": valid.qty,
        "gross_amount_pkr": valid.gross_amount_pkr, "discount_pkr": valid.discount_pkr,
        "net_amount_pkr": valid.net_amount_pkr, "cost_amount_pkr": cost,
        "gross_margin_pkr": (valid.net_amount_pkr - cost).round(2), "is_cancelled": valid.is_cancelled,
        "is_customer_unresolved": valid.is_customer_unresolved, "source_system": "sales_db",
        "source_key": valid.source_key, "batch_id": valid.batch_id})


def build_fact_purchase(valid: pd.DataFrame, dims: dict) -> pd.DataFrame:
    branch_key = dims["dim_branch"].set_index("branch_code").branch_key
    return pd.DataFrame({
        "date_key": valid.received_at.dt.strftime("%Y%m%d").astype(int),
        "product_key": valid.product_code.str[2:].astype(int),
        "branch_key": valid.branch_code.map(branch_key).astype(int), "supplier_key": valid.supplier_id.astype(int),
        "grn_no": valid.grn_no, "line_no": valid.line_no.astype(int), "quantity_units": valid.quantity_units,
        "currency_code": valid.currency, "fx_rate_used": valid.fx_rate_used.round(4),
        "amount_original": valid.amount_original, "purchase_amount_pkr": valid.purchase_amount_pkr,
        "is_cancelled": valid.is_cancelled, "source_system": "purchasing_db", "source_key": valid.source_key,
        "batch_id": valid.batch_id})
