"""Generator part 1: reference (master) data. SYNTHETIC, seed 472.

Builds the "true" master data that every source system will show in its own way:
products, branches, suppliers, loyalty members, panel companies, the daily USD/PKR
rate, the shelf-price list and the standard-cost history.

Result: a dict of pandas DataFrames (see build_reference()). Nothing here touches a
database; generate_sources.py turns these into source tables.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.common import SEED
from src.gen import catalogue as cat

HISTORY_START = date(2023, 11, 1)
HISTORY_END = date(2026, 10, 31)             # 36 completed months
PRICE_STEPS = [date(2024, 7, 1), date(2025, 7, 1), date(2026, 7, 1)]   # yearly shelf price rise
PRICE_STEP_FACTOR = 1.08
DIABETES_COST_STEP = date(2026, 3, 1)        # diagnosis story: purchase cost +12%
DIABETES_COST_FACTOR = 1.12

# Till codes that exist in Sales but match no Inventory item (planted R01 rejects).
UNKNOWN_POS_ITEMS = [("MISC-OPEN", "Open item - price keyed at till", "PIECE"),
                     ("DISC-0412-STR", "Discontinued item 412", "STRIP"),
                     ("SAMPLE-PCS", "Free sample", "PIECE")]


def _rng(part: int) -> np.random.Generator:
    """One random generator per generator part, all derived from seed 472.

    Using [472, part] means adding or changing a later part never shifts the
    random numbers of an earlier part.
    """
    return np.random.default_rng([SEED, part])


def _code_strength(strength: str) -> str:
    """'500 mg' -> '500', '2.5 mg' -> '25', 'SPF 50' -> '50', '500/65 mg' -> '500'."""
    m = re.search(r"\d+(\.\d+)?", strength)
    return m.group(0).replace(".", "") if m else "0"


def _item_code(generic: str, strength: str, unit: str, used: set) -> str:
    words = generic.replace("-", " ").split()
    abbr = words[0][:3].upper() + "".join(w[0].upper() for w in words[1:])
    code = f"{abbr}-{_code_strength(strength)}-{cat.UNIT_SUFFIX[unit]}"
    n = 1
    while code in used:                       # make every till code unique
        n += 1
        code = f"{abbr}{n}-{_code_strength(strength)}-{cat.UNIT_SUFFIX[unit]}"
    used.add(code)
    return code


def _messy_category(true_category: str, rng) -> str:
    """How the legacy Inventory app stores a category: case and spaces vary."""
    r = rng.random()
    if r < 0.6:
        return true_category
    if r < 0.8:
        return f" {true_category.lower()} "
    return true_category.upper()


def build_branches() -> pd.DataFrame:
    rows = []
    for b in cat.BRANCHES:
        store_code, store_name, area, region, branch_id, label, prefix, weight, variants = b
        rows.append({"store_code": store_code, "store_name": store_name, "area": area, "region": region,
                     "branch_id": branch_id, "branch_label": label, "receipt_prefix": prefix,
                     "sales_weight": weight, "canonical_name": store_name.replace("Nuskha ", "")})
    return pd.DataFrame(rows)


def build_branch_variants() -> pd.DataFrame:
    rows = []
    for b in cat.BRANCHES:
        for i, v in enumerate(b[8]):
            rows.append({"store_code": b[0], "variant_no": i + 1, "branch_name_text": v,
                         "share": 0.6 if i == 0 else 0.4 / (len(b[8]) - 1)})
    return pd.DataFrame(rows)


def build_suppliers(rng) -> pd.DataFrame:
    import_idx = set(rng.choice(25, size=5, replace=False).tolist())
    rows, country_i = [], 0
    for i, word in enumerate(cat.SUPPLIER_WORDS):
        is_import = i in import_idx
        country = cat.IMPORT_COUNTRIES[country_i] if is_import else "Pakistan"
        country_i += int(is_import)
        rows.append({"supplier_id": i + 1,
                     "supplier_name": f"{word} {cat.SUPPLIER_SUFFIX[i % len(cat.SUPPLIER_SUFFIX)]}",
                     "country": country, "is_import": is_import, "code_prefix": word[:3].upper()})
    return pd.DataFrame(rows)


def build_items(rng, suppliers: pd.DataFrame) -> pd.DataFrame:
    """150 products with codes, pack sizes, base price/cost, popularity and supplier."""
    rows, used_codes = [], set()
    for category, products in cat.PRODUCTS.items():
        for generic, strength, unit in products:
            low, high = cat.PRICE_RANGE.get((category, unit), cat.DEFAULT_PRICE_RANGE[unit])
            rows.append({"generic_name": generic, "strength": strength, "true_category": category,
                         "unit_letter": unit, "sell_unit": cat.UNIT_NAMES[unit],
                         "item_code": _item_code(generic, strength, unit, used_codes),
                         "base_price": float(round(rng.uniform(low, high))),
                         "cost_ratio": rng.uniform(0.68, 0.80)})
    items = pd.DataFrame(rows)
    n = len(items)

    # Inventory item_id: unique 3-digit numbers, like 312.
    items["item_id"] = np.sort(rng.choice(np.arange(101, 500), size=n, replace=False))
    items["product_code"] = items["item_id"].map(lambda i: f"P-{i:04d}")   # canonical code in the DW

    # Pack sizes: tablets per strip (1 for bottles and pieces) and strips (units) per box.
    items["tablets_per_strip"] = [int(rng.choice([10, 10, 10, 14, 20])) if u == "S" else 1
                                  for u in items["unit_letter"]]
    items["strips_per_box"] = [int(rng.choice([10, 20, 30])) if u == "S" else int(rng.choice([6, 12, 24]))
                               for u in items["unit_letter"]]

    # Popularity: random within category, scaled so each category gets its target share of lines.
    # Cheaper products sell more often (popularity falls with price), with random spread.
    pop = rng.lognormal(0.0, 0.5, size=n) / items["base_price"].to_numpy() ** 0.7
    items["popularity"] = pop
    items["popularity"] = items.groupby("true_category")["popularity"].transform(lambda s: s / s.sum())
    items["popularity"] *= items["true_category"].map(cat.CATEGORIES)

    # Suppliers: about 20 items go to the 5 importers, the rest to the 20 local suppliers.
    importers = suppliers.loc[suppliers.is_import, "supplier_id"].to_numpy()
    locals_ = suppliers.loc[~suppliers.is_import, "supplier_id"].to_numpy()
    imported = set(rng.choice(n, size=20, replace=False).tolist())
    items["supplier_id"] = [int(importers[i % 5]) if i in imported else int(rng.choice(locals_))
                            for i in range(n)]

    # Vendor item codes such as 'DST-1187': supplier prefix + unique 4-digit number.
    numbers = rng.choice(np.arange(1000, 10000), size=n, replace=False)
    prefix = suppliers.set_index("supplier_id")["code_prefix"]
    items["vendor_item_code"] = [f"{prefix[s]}-{num}" for s, num in zip(items["supplier_id"], numbers)]

    # Partial cross-references kept in Inventory: 85% have pos_code, 70% have vendor_code.
    # About 1 in 8 filled pos_codes is typed in lower case with a trailing space.
    def exact_share(share: float) -> np.ndarray:
        """Boolean mask with exactly round(share * n) True values in random places."""
        mask = np.zeros(n, dtype=bool)
        mask[rng.choice(n, size=int(round(share * n)), replace=False)] = True
        return mask

    has_pos = exact_share(0.85)
    messy_pos = rng.random(n) < 0.125
    items["inv_pos_code"] = [(c.lower() + " " if m else c) if h else None
                             for c, h, m in zip(items["item_code"], has_pos, messy_pos)]
    has_vendor = exact_share(0.70)
    items["inv_vendor_code"] = [c if h else None for c, h in zip(items["vendor_item_code"], has_vendor)]

    # Category as the legacy Inventory app stores it (case/space variants). The one cough syrup
    # is misfiled under Gastro until stage 2 corrects it.
    items["inv_category_text"] = [_messy_category(c, rng) for c in items["true_category"]]
    misfiled = items["generic_name"].eq("Dextromethorphan Syrup")
    items.loc[misfiled, "inv_category_text"] = "Gastro"
    items["misfiled_stage1"] = misfiled
    return items


def build_price_and_cost(items: pd.DataFrame, rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shelf-price list (Sales prices) and standard-cost history (Inventory).

    Prices and costs rise 8% each July. Diabetes Care cost rises a further 12% from
    1 Mar 2026 while its shelf price stays fixed (no July 2026 rise either), so its
    margin falls: the planted diagnosis story.
    """
    price_rows, cost_rows = [], []
    for it in items.itertuples():
        diabetes = it.true_category == "Diabetes Care"
        price = it.base_price
        cost = it.base_price * it.cost_ratio
        price_rows.append((it.item_code, HISTORY_START, price))
        cost_rows.append((it.item_id, HISTORY_START, cost))
        events = sorted([(d, "step") for d in PRICE_STEPS] + ([(DIABETES_COST_STEP, "diab")] if diabetes else []))
        for d, kind in events:
            if kind == "diab":
                cost *= DIABETES_COST_FACTOR
                cost_rows.append((it.item_id, d, cost))
            elif diabetes and d == date(2026, 7, 1):
                continue                                   # Diabetes Care shelf price frozen
            else:
                price = float(round(price * PRICE_STEP_FACTOR))
                cost *= PRICE_STEP_FACTOR
                price_rows.append((it.item_code, d, price))
                cost_rows.append((it.item_id, d, cost))
    prices = pd.DataFrame(price_rows, columns=["item_code", "effective_from", "unit_price_pkr"])
    costs = pd.DataFrame(cost_rows, columns=["item_id", "effective_from", "std_cost_per_unit"])
    # Inventory keeps cost as REAL with stray decimals (cleaned to NUMERIC(14,2) in the ETL).
    costs["std_cost_per_unit"] = (costs["std_cost_per_unit"] * (1 + rng.normal(0, 0.0004, len(costs)))).round(4)
    return prices, costs


def build_loyalty(rng) -> pd.DataFrame:
    n = 1200
    old = rng.random(n) < 0.65
    start_old, start_new = date(2020, 1, 1), HISTORY_START
    days_old = (HISTORY_START - start_old).days
    days_new = (date(2026, 8, 31) - start_new).days
    joined = [start_old + timedelta(days=int(rng.integers(0, days_old))) if o
              else start_new + timedelta(days=int(rng.integers(0, days_new))) for o in old]
    names = [f"{rng.choice(cat.FIRST_NAMES)} {rng.choice(cat.LAST_NAMES)}" for _ in range(n)]
    return pd.DataFrame({"card_no": [f"LC-{100001 + i}" for i in range(n)],
                         "member_name": names, "joined_on": joined})


def build_panel(rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    """15 fictional panel companies and the 2-3 ways cashiers type each name."""
    rows, variants = [], []
    for i, (word, trade) in enumerate(zip(cat.COMPANY_WORDS, cat.COMPANY_TRADES)):
        account_no = 40011 + i
        name = f"{word} {trade}"
        rows.append({"account_no": account_no, "company_name": name,
                     "credit_limit_pkr": float(rng.choice([200000, 300000, 500000, 750000, 1000000, 1500000])),
                     "terms_days": int(rng.choice([15, 30, 45])),
                     "updated_at": pd.Timestamp("2023-10-02 10:00:00") + pd.Timedelta(minutes=int(rng.integers(0, 40000))),
                     "weight": rng.uniform(0.5, 1.5)})
        short = re.sub(r"\s*\(Pvt\)|\s+Ltd", "", name)               # 'Bluewater Textiles'
        options = [name, short.upper(), word.lower() + " " + trade.split()[0].lower()[:4]]
        k = int(rng.choice([2, 3]))
        for j, text in enumerate(options[:k]):
            variants.append({"account_no": account_no, "variant_no": j + 1, "panel_company_text": text})
    return pd.DataFrame(rows), pd.DataFrame(variants)


def build_fx(rng) -> pd.DataFrame:
    """Daily USD/PKR for 1,096 days with a gradual PKR drift (285 -> about 305)."""
    days = pd.date_range(HISTORY_START, HISTORY_END, freq="D")
    n = len(days)
    trend = 285.2 * (305.0 / 285.2) ** (np.arange(n) / (n - 1))
    noise = np.zeros(n)
    shocks = rng.normal(0, 0.0018, n)
    for t in range(1, n):
        noise[t] = 0.97 * noise[t - 1] + shocks[t]               # small, mean-reverting wiggle
    return pd.DataFrame({"rate_date": days.date, "usd_pkr": np.round(trend * np.exp(noise), 4)})


def build_reference() -> dict[str, pd.DataFrame]:
    """All reference tables, deterministic for seed 472."""
    rng = _rng(1)
    suppliers = build_suppliers(rng)
    items = build_items(rng, suppliers)
    prices, costs = build_price_and_cost(items, rng)
    panel, panel_variants = build_panel(rng)
    return {
        "branch": build_branches(),
        "branch_name_variant": build_branch_variants(),
        "supplier": suppliers,
        "item": items,
        "unknown_pos_item": pd.DataFrame(UNKNOWN_POS_ITEMS, columns=["item_code", "item_desc", "sell_unit"]),
        "shelf_price": prices,
        "cost_history": costs,
        "loyalty_member": build_loyalty(rng),
        "panel_account": panel,
        "panel_name_variant": panel_variants,
        "fx_rate": build_fx(rng),
        "ramadan": pd.DataFrame(cat.RAMADAN, columns=["start_date", "end_date"]),
    }


def check_reference(ref: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compare reference row counts with the blueprint's generator table."""
    items, branches, variants = ref["item"], ref["branch"], ref["branch_name_variant"]
    per_branch = variants.groupby("store_code").size()
    per_panel = ref["panel_name_variant"].groupby("account_no").size()
    checks = [
        ("item rows", 150, len(items)),
        ("item categories", 8, items["true_category"].nunique()),
        ("item share with pos_code (%, target 85)", 85, round(100 * items["inv_pos_code"].notna().mean())),
        ("item share with vendor_code (%, target 70)", 70, round(100 * items["inv_vendor_code"].notna().mean())),
        ("branches", 10, len(branches)),
        ("branches with 2-3 spelling variants", 10, int(per_branch.between(2, 3).sum())),
        ("suppliers", 25, len(ref["supplier"])),
        ("import suppliers", 5, int(ref["supplier"]["is_import"].sum())),
        ("loyalty members", 1200, len(ref["loyalty_member"])),
        ("panel accounts", 15, len(ref["panel_account"])),
        ("panel accounts typed 2-3 ways", 15, int(per_panel.between(2, 3).sum())),
        ("fx_rate days (Nov 2023 - Oct 2026)", 1096, len(ref["fx_rate"])),
        ("items with a cost step-up on 2026-03-01 (Diabetes Care)", int((items.true_category == "Diabetes Care").sum()),
         int((pd.to_datetime(ref["cost_history"]["effective_from"]) == "2026-03-01").sum())),
    ]
    out = pd.DataFrame(checks, columns=["check", "expected", "actual"])
    # The two percentage checks allow +-5 points; all others must match exactly.
    tol = out["check"].str.contains("%").map({True: 5, False: 0})
    out["result"] = np.where((out["expected"] - out["actual"]).abs() <= tol, "PASS", "FAIL")
    return out
