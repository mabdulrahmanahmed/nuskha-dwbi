"""Generator part 2: clean transactions for the full history. SYNTHETIC, seed 472.

Builds till receipts and lines (Sales) and purchase orders, goods receipts and GRN
lines (Purchasing) for Nov 2023 - Oct 2026, before any defect is planted.

Planted patterns (so the analysis has something real to find):
  * trend: about 1% more receipts every month, plus the yearly July price rise
  * seasons: Cough and Cold peaks Dec-Feb; Analgesics and Gastro peak Aug-Oct;
    Vitamins rise before Ramadan
  * customer mix: about 70% walk-in, 22% loyalty, 8% panel by value
  * anomalies: East-region Analgesics spike in Sep 2026 (dengue cluster); one branch
    (Gulshan-e-Iqbal, the largest East branch) almost without sales in Jun 2026 (stock-out); one keying error
    (quantity x 10) on a South-region line in Apr 2026
  * late arrivals: about 40 receipts from Jul-Aug 2026 reach the Sales database only
    in Sep-Oct 2026 (till offline), so they first appear in stage 2

Every frame keeps helper columns starting with '_' (true branch, item, account...).
They are dropped before the source tables are written.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from src.common import SEED
from src.gen import catalogue as cat
from src.gen.reference import HISTORY_START

N_MONTHS = 36
BASE_RECEIPTS = 300          # receipts in the first month before seasons (about 14,000 in total)
GROWTH = 1.01                # +1% a month
BASE_POS = 43                # purchase orders in the first month (about 1,800 in total)
CUSTOMER_MIX = {"WALKIN": 0.705, "LOYALTY": 0.225, "PANEL": 0.07}
STAGE1_CUTOFF = datetime(2026, 8, 31, 23, 59, 59)
STAGE2_CUTOFF = datetime(2026, 10, 31, 23, 59, 59)

STOCKOUT = ("BR-GUL", 2026, 6, 0.05)      # branch, year, month, share of normal receipts kept
SPIKE = ("East", "Analgesics", 2026, 9, 1.3)  # region, category, year, month, extra lines vs normal
KEYING_ERROR = ("South", "Cardiovascular", 2026, 4)
N_LATE_RECEIPTS = 40


def month_starts() -> list[date]:
    out, d = [], HISTORY_START
    for _ in range(N_MONTHS):
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def days_in_month(d: date) -> int:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - d).days


def season_factor(category: str, d: date) -> float:
    f = cat.SEASONS.get(category, {}).get(d.month, 1.0)
    if category == "Vitamins and Supplements":
        f *= cat.PRE_RAMADAN_MONTHS.get((d.year, d.month), 1.0)
    return f


def price_lookup(shelf_price: pd.DataFrame):
    """Return f(item_code, day) -> shelf price effective on that day."""
    table = {}
    for code, grp in shelf_price.sort_values("effective_from").groupby("item_code"):
        table[code] = list(zip(pd.to_datetime(grp["effective_from"]).dt.date, grp["unit_price_pkr"]))

    def price(code: str, day: date) -> float:
        value = None
        for eff, p in table[code]:
            if eff <= day:
                value = p
        return value
    return price


def cost_lookup(cost_history: pd.DataFrame):
    """Return f(item_id, day) -> standard cost effective on that day."""
    table = {}
    for item_id, grp in cost_history.sort_values("effective_from").groupby("item_id"):
        table[item_id] = list(zip(pd.to_datetime(grp["effective_from"]).dt.date, grp["std_cost_per_unit"]))

    def cost(item_id: int, day: date) -> float:
        value = None
        for eff, c in table[item_id]:
            if eff <= day:
                value = c
        return value
    return cost


def fx_lookup(fx: pd.DataFrame):
    rates = dict(zip(pd.to_datetime(fx["rate_date"]).dt.date, fx["usd_pkr"]))
    return lambda day: rates.get(day)


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------
def _quantity(rng, unit: str, customer_type: str) -> int:
    lam = {"STRIP": 1.3, "BOTTLE": 0.3, "PIECE": 0.5}[unit]
    q = 1 + rng.poisson(lam)
    if customer_type == "PANEL":
        q += rng.poisson(0.5)
    return int(q)


def build_sales(ref: dict, rng) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    items = ref["item"].reset_index(drop=True)
    branches = ref["branch"]
    variants = ref["branch_name_variant"]
    members = ref["loyalty_member"]
    panel = ref["panel_account"]
    panel_variants = ref["panel_name_variant"]
    price = price_lookup(ref["shelf_price"])

    region_of = dict(zip(branches.store_code, branches.region))
    branch_w = branches.sales_weight.to_numpy() / branches.sales_weight.sum()
    variant_map = {s: (g.branch_name_text.tolist(), (g.share / g.share.sum()).tolist())
                   for s, g in variants.groupby("store_code")}
    member_join = pd.to_datetime(members.joined_on).dt.date.to_numpy()
    member_w = rng.lognormal(0, 1.0, len(members))           # some members shop far more often
    panel_w = panel.weight.to_numpy() / panel.weight.sum()
    panel_text = {a: (g.panel_company_text.tolist(), [0.5] + [0.5 / (len(g) - 1)] * (len(g) - 1))
                  for a, g in panel_variants.groupby("account_no")}
    item_cat = items.true_category.to_numpy()
    analgesic_idx = np.flatnonzero(item_cat == "Analgesics")

    receipts, lines, patterns = [], [], []

    def add_receipt(store: str, ts: datetime, ctype: str, item_idx, late: bool = False) -> None:
        names, probs = variant_map[store]
        r = {"_store_code": store, "_region": region_of[store], "branch_name": str(rng.choice(names, p=probs)),
             "receipt_ts": ts, "customer_type": ctype, "card_no": None, "panel_company_text": None,
             "_account_no": None, "status": "POSTED", "_late": late}
        if ctype == "LOYALTY":
            ok = member_join <= ts.date()
            w = member_w * ok
            r["card_no"] = members.card_no.iloc[int(rng.choice(len(members), p=w / w.sum()))]
        elif ctype == "PANEL":
            acct = int(panel.account_no.iloc[int(rng.choice(len(panel), p=panel_w))])
            texts, tp = panel_text[acct]
            r["_account_no"], r["panel_company_text"] = acct, str(rng.choice(texts, p=tp))
        sync = timedelta(minutes=int(rng.integers(1, 31)), seconds=int(rng.integers(0, 60)))
        r["updated_at"] = ts + sync
        r["_rid"] = len(receipts)
        receipts.append(r)
        for line_no, i in enumerate(item_idx, start=1):
            it = items.iloc[int(i)]
            qty = _quantity(rng, it.sell_unit, ctype)
            unit_price = price(it.item_code, ts.date())
            gross = round(qty * unit_price, 2)
            if ctype == "LOYALTY":
                discount = round(0.05 * gross, 2) if rng.random() < 0.7 else None
            elif ctype == "WALKIN":
                discount = 0.0 if rng.random() < 0.15 else None
            else:
                discount = None
            lines.append({"_rid": r["_rid"], "line_no": line_no, "item_code": it.item_code, "qty": float(qty),
                          "unit_price_pkr": unit_price, "discount_pkr": discount,
                          "_item_id": int(it.item_id), "_category": it.true_category})

    for m, ms in enumerate(month_starts()):
        # Item probabilities this month: popularity x season.
        p = items.popularity.to_numpy() * np.array([season_factor(c, ms) for c in item_cat])
        p = p / p.sum()
        overall = sum(share * season_factor(c, ms) for c, share in cat.CATEGORIES.items())
        n_receipts = int(round(BASE_RECEIPTS * GROWTH ** m * overall * rng.uniform(0.97, 1.03)))
        for _ in range(n_receipts):
            store = branches.store_code.iloc[int(rng.choice(len(branches), p=branch_w))]
            if (store, ms.year, ms.month) == STOCKOUT[:3] and rng.random() > STOCKOUT[3]:
                continue                                   # stock-out month: most receipts never happen
            ts = datetime(ms.year, ms.month, 1) + timedelta(days=int(rng.integers(0, days_in_month(ms))),
                                                            seconds=int(rng.integers(9 * 3600, 22 * 3600)))
            ctype = str(rng.choice(list(CUSTOMER_MIX), p=list(CUSTOMER_MIX.values())))
            k = min(1 + rng.poisson(1.2), 6)
            add_receipt(store, ts, ctype, rng.choice(len(items), size=k, replace=False, p=p))

        # Sep 2026: dengue cluster in the East: extra receipts with only Analgesics.
        if (ms.year, ms.month) == SPIKE[2:4]:
            east_now = sum(1 for ln in lines if ln["_category"] == "Analgesics"
                           and receipts[ln["_rid"]]["_region"] == "East"
                           and receipts[ln["_rid"]]["receipt_ts"].strftime("%Y-%m") == ms.strftime("%Y-%m"))
            target = int(round(east_now * SPIKE[4]))
            east = branches[branches.region == "East"].store_code.tolist()
            pa = items.popularity.to_numpy()[analgesic_idx]
            added = 0
            while added < target:
                ts = datetime(ms.year, ms.month, 1) + timedelta(days=int(rng.integers(0, 30)),
                                                                seconds=int(rng.integers(9 * 3600, 22 * 3600)))
                k = int(rng.choice([1, 2]))
                add_receipt(str(rng.choice(east)), ts, "WALKIN", rng.choice(analgesic_idx, size=k, replace=False,
                                                                            p=pa / pa.sum()))
                added += k
            patterns.append({"pattern": "East Analgesics spike", "month": ms.strftime("%Y-%m"),
                             "detail": f"{added} extra Analgesics lines at East branches (normal: {east_now})"})

    rec = pd.DataFrame(receipts)
    lin = pd.DataFrame(lines)

    # Receipt numbers 'GUL-2026-000123': per branch prefix and year, in time order.
    prefix = dict(zip(branches.store_code, branches.receipt_prefix))
    rec = rec.sort_values(["receipt_ts", "_rid"]).reset_index(drop=True)
    rec["_year"] = rec.receipt_ts.dt.year
    rec["_seq"] = rec.groupby(["_store_code", "_year"]).cumcount() + 1
    rec["receipt_no"] = [f"{prefix[s]}-{y}-{q:06d}" for s, y, q in zip(rec._store_code, rec._year, rec._seq)]
    lin = lin.merge(rec[["_rid", "receipt_no", "updated_at", "receipt_ts", "_store_code", "_region",
                         "customer_type", "_account_no"]], on="_rid")

    # Late arrivals: receipts from Jul-Aug 2026 that the till synced only in Sep-Oct 2026.
    cand = rec[(rec.receipt_ts >= "2026-07-01") & (rec.receipt_ts <= "2026-08-31 23:00")].index.to_numpy()
    late = rng.choice(cand, size=N_LATE_RECEIPTS, replace=False)
    for idx in late:
        delay = timedelta(days=int(rng.integers(3, 55)), minutes=int(rng.integers(0, 600)))
        new_ts = max(rec.at[idx, "receipt_ts"] + delay, datetime(2026, 9, 1, 9, 0))
        rec.at[idx, "updated_at"] = min(new_ts, datetime(2026, 10, 30, 20, 0))
        rec.at[idx, "_late"] = True
    lin = lin.drop(columns=["updated_at"]).merge(rec[["receipt_no", "updated_at"]], on="receipt_no")
    patterns.append({"pattern": "Late receipts", "month": "2026-07/08",
                     "detail": f"{N_LATE_RECEIPTS} receipts dated Jul-Aug 2026 first reach Sales in Sep-Oct 2026"})

    # Keying error: one South Cardiovascular strip line in Apr 2026 gets quantity x 10.
    region, category, y, mth = KEYING_ERROR
    mask = ((lin._region == region) & (lin._category == category) & (lin.receipt_ts.dt.year == y)
            & (lin.receipt_ts.dt.month == mth) & (lin.customer_type == "WALKIN"))
    target = lin[mask].sort_values(["receipt_no", "line_no"]).index[0]
    lin.at[target, "qty"] = 60.0                                         # cashier keyed 60 instead of 6
    lin.at[target, "discount_pkr"] = None
    patterns.append({"pattern": "Keying error (qty x 10)", "month": f"{y}-{mth:02d}",
                     "detail": f"{lin.at[target, 'receipt_no']} line {lin.at[target, 'line_no']}: qty 60 instead of 6"})

    st, yy, mm, keep = STOCKOUT
    patterns.append({"pattern": "Branch stock-out", "month": f"{yy}-{mm:02d}",
                     "detail": f"{st} kept only about {int(keep * 100)}% of its normal receipts"})

    lin = lin.sort_values(["receipt_no", "line_no"]).reset_index(drop=True)
    return rec, lin, patterns


# ---------------------------------------------------------------------------
# Purchasing
# ---------------------------------------------------------------------------
TZ = "+05:00"


def build_purchases(ref: dict, rng) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    items = ref["item"]
    suppliers = ref["supplier"]
    branches = ref["branch"]
    cost = cost_lookup(ref["cost_history"])
    fx = fx_lookup(ref["fx_rate"])

    items_by_supplier = {s: g for s, g in items.groupby("supplier_id")}
    sup_ids = suppliers.supplier_id.to_numpy()
    is_imp = suppliers.is_import.to_numpy()
    n_items = np.array([len(items_by_supplier.get(s, [])) for s in sup_ids], dtype=float)
    # Importers get about 15% of orders between them; local suppliers share the rest by range size.
    w = np.where(is_imp, 0.15 / is_imp.sum(), 0.85 * n_items / n_items[~is_imp].sum())
    w = w / w.sum()
    branch_ids = branches.branch_id.to_numpy()
    branch_w = branches.sales_weight.to_numpy() / branches.sales_weight.sum()

    pos, grns, glines = [], [], []
    for m, ms in enumerate(month_starts()):
        n_po = int(round(BASE_POS * GROWTH ** m * rng.uniform(0.95, 1.05)))
        for _ in range(n_po):
            s_i = int(rng.choice(len(sup_ids), p=w))
            sid, imported = int(sup_ids[s_i]), bool(is_imp[s_i])
            ordered = datetime(ms.year, ms.month, 1) + timedelta(days=int(rng.integers(0, days_in_month(ms))),
                                                                 seconds=int(rng.integers(9 * 3600, 17 * 3600)))
            lead = int(rng.integers(10, 21)) if imported else int(rng.integers(2, 7))
            received = ordered + timedelta(days=lead, minutes=int(rng.integers(-120, 240)))
            po = {"_pid": len(pos), "supplier_id": sid, "branch_id": int(rng.choice(branch_ids, p=branch_w)),
                  "ordered_at": ordered, "currency": "USD" if imported else "PKR", "updated_at": ordered}
            pos.append(po)
            g_upd = received + timedelta(minutes=int(rng.integers(5, 120)))
            grns.append({"_pid": po["_pid"], "received_at": received, "status": "POSTED", "updated_at": g_upd})
            sup_items = items_by_supplier[sid]
            k = min(1 + rng.poisson(1.8), len(sup_items))
            pick = sup_items.sample(n=k, weights=sup_items.popularity, random_state=rng)
            for line_no, it in enumerate(pick.itertuples(), start=1):
                pkr_box = cost(it.item_id, received.date()) * it.strips_per_box * (1 + rng.normal(0, 0.02))
                cost_box = pkr_box / fx(ordered.date()) if imported else pkr_box
                glines.append({"_pid": po["_pid"], "line_no": line_no, "vendor_item_code": it.vendor_item_code,
                               "boxes_received": float(1 + rng.poisson(0.6)), "cost_per_box": round(cost_box, 2),
                               "_item_id": int(it.item_id), "_category": it.true_category,
                               "_currency": po["currency"]})

    po_df = pd.DataFrame(pos).sort_values(["ordered_at", "_pid"]).reset_index(drop=True)
    po_df["po_no"] = [f"PO-{t.year}-{i:05d}" for t, i in
                      zip(po_df.ordered_at, po_df.groupby(po_df.ordered_at.dt.year).cumcount() + 1)]
    grn_df = pd.DataFrame(grns).merge(po_df[["_pid", "po_no"]], on="_pid")
    grn_df = grn_df.sort_values(["received_at", "_pid"]).reset_index(drop=True)
    grn_df["grn_no"] = [f"GRN-{t.year}-{i:05d}" for t, i in
                        zip(grn_df.received_at, grn_df.groupby(grn_df.received_at.dt.year).cumcount() + 1)]
    gl_df = pd.DataFrame(glines).merge(grn_df[["_pid", "grn_no", "updated_at", "received_at"]], on="_pid")
    gl_df = gl_df.sort_values(["grn_no", "line_no"]).reset_index(drop=True)
    return po_df, grn_df, gl_df


def build_stock_counts(ref: dict, rng) -> pd.DataFrame:
    """Quarter-end stock counts in tablets per store and item (Inventory, not loaded to the stars)."""
    items, branches = ref["item"], ref["branch"]
    quarter_ends = pd.date_range("2023-12-31", "2026-09-30", freq="QE").date
    rows = []
    for qd in quarter_ends:
        for b in branches.itertuples():
            for it in items.itertuples():
                units = max(0, int(rng.normal(it.popularity * 4000 * b.sales_weight, 8)))
                rows.append({"store_code": b.store_code, "item_id": int(it.item_id), "_count_date": qd,
                             "tablets_on_hand": units * int(it.tablets_per_strip)})
    return pd.DataFrame(rows)


def build_transactions(ref: dict) -> dict:
    """All clean transactions, deterministic for seed 472 (generator part 2)."""
    rng = np.random.default_rng([SEED, 2])
    receipts, lines, patterns = build_sales(ref, rng)
    po, grn, grn_lines = build_purchases(ref, rng)
    stock = build_stock_counts(ref, rng)
    return {"receipt": receipts, "receipt_line": lines, "purchase_order": po, "goods_receipt": grn,
            "grn_line": grn_lines, "stock_count": stock, "patterns": pd.DataFrame(patterns)}
