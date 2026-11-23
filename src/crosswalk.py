"""Crosswalks: map every department's own key to one canonical code (unit 2.06).

  xw_product   till item_code (Sales), vendor_item_code (Purchasing), item_id (Inventory)
               -> canonical product code 'P-0312' (from the Inventory item_id)
  xw_branch    typed branch text (Sales), branch_id (Purchasing), store_code (Inventory)
               -> canonical branch code = Inventory store_code 'BR-GUL'
  xw_customer  loyalty card_no, typed panel name (Sales), account_no (Finance)
               -> 'L-100043', 'PANEL-40011' (walk-ins are the fixed code 'WALKIN')

Every row records how it was matched (match_method), tried in this order:
  exact               the key is written exactly as the master writes it
  rule                equal after trimming / case / punctuation rules
  rule (alias list)   listed in config/branch_aliases.csv or config/panel_aliases.csv
  rule (description)  product description equals Inventory generic name + strength
  manual              listed in config/product_manual_matches.csv
  unmatched           no rule applies: canonical_code is empty and the rows are rejected
                      (R01 product, R05 branch) or loaded to Unknown (U01 customer)
"""
from __future__ import annotations

import re

import pandas as pd

from src.common import CONFIG_DIR

XW_COLUMNS = ["source_system", "source_object", "source_key", "canonical_code", "match_method"]


def product_code(item_id) -> str:
    return f"P-{int(item_id):04d}"


def _squash(v) -> str:
    """Upper case, letters and digits only: 'Paracetamol 500 mg' -> 'PARACETAMOL500MG'."""
    return re.sub(r"[^A-Z0-9]", "", str(v).upper()) if v is not None and not pd.isna(v) else ""


def _company_norm(v) -> str:
    """'Copperleaf Logistics (Pvt) Ltd' -> 'COPPERLEAF LOGISTICS' (legal suffixes dropped)."""
    if v is None or pd.isna(v):
        return ""
    words = re.sub(r"[^A-Z0-9 ]", " ", str(v).upper()).split()
    return " ".join(w for w in words if w not in {"LTD", "PVT", "LIMITED", "PRIVATE"})


def _read_config(name: str, columns: list) -> pd.DataFrame:
    path = CONFIG_DIR / name
    if path.exists():
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.DataFrame(columns=columns)


def _rows(system, obj, keys, codes, methods) -> pd.DataFrame:
    return pd.DataFrame({"source_system": system, "source_object": obj, "source_key": list(keys),
                         "canonical_code": list(codes), "match_method": list(methods)})


def build_xw_product(stg: dict) -> pd.DataFrame:
    item = stg["item"]
    by_desc = {}
    for r in item.itertuples():
        by_desc.setdefault(_squash(f"{r.generic_name} {r.strength}"), []).append(r.item_id)
    manual = _read_config("product_manual_matches.csv", ["source_system", "source_key", "product_code"])
    manual_map = {(m.source_system, m.source_key): m.product_code for m in manual.itertuples()}

    def match(system, key, raw_codes: dict, clean_codes: dict, desc):
        if key in raw_codes:
            return product_code(raw_codes[key]), "exact"
        if key.upper() in clean_codes:
            return product_code(clean_codes[key.upper()]), "rule"
        hits = by_desc.get(_squash(desc), [])
        if len(hits) == 1:
            return product_code(hits[0]), "rule (description)"
        if (system, key) in manual_map:
            return manual_map[(system, key)], "manual"
        return None, "unmatched"

    out = []
    # Inventory itself: item_id is the master key.
    out.append(_rows("inventory", "item", item.item_id.astype(str), item.item_id.map(product_code), ["exact"] * len(item)))

    # Sales till codes: Inventory pos_code (partly filled), then the till description.
    raw_pos = {c: i for c, i in zip(item.pos_code_raw, item.item_id) if c}
    clean_pos = {c: i for c, i in zip(item.pos_code, item.item_id) if c}
    pos = stg["pos_item"]
    keys = sorted(set(pos.item_code) | set(stg["receipt_line"].item_code.dropna()))
    desc = dict(zip(pos.item_code, pos.item_desc))
    res = [match("sales_db", k, raw_pos, clean_pos, desc.get(k)) for k in keys]
    out.append(_rows("sales_db", "pos_item", keys, [r[0] for r in res], [r[1] for r in res]))

    # Purchasing vendor codes: Inventory vendor_code (partly filled), then the vendor description
    # without its pack size ('PARACETAMOL 500MG BOX/20' -> 'PARACETAMOL500MG').
    raw_ven = {c: i for c, i in zip(item.vendor_code_raw, item.item_id) if c}
    clean_ven = {c: i for c, i in zip(item.vendor_code, item.item_id) if c}
    vi = stg["vendor_item"]
    keys = sorted(set(vi.vendor_item_code) | set(stg["grn_line"].vendor_item_code.dropna()))
    vdesc = {k: re.sub(r"\s*BOX/\d+$", "", str(d)) for k, d in zip(vi.vendor_item_code, vi.description)}
    res = [match("purchasing_db", k, raw_ven, clean_ven, vdesc.get(k)) for k in keys]
    out.append(_rows("purchasing_db", "vendor_item", keys, [r[0] for r in res], [r[1] for r in res]))
    return pd.concat(out, ignore_index=True)


def build_xw_branch(stg: dict) -> pd.DataFrame:
    store = stg["store"]
    canonical = {s: n.replace("Nuskha ", "") for s, n in zip(store.store_code, store.store_name)}
    norm_to_code = {" ".join(n.upper().replace(".", "").replace("-", " ").split()): s for s, n in canonical.items()}
    aliases = _read_config("branch_aliases.csv", ["alias_text", "store_code"])
    alias_map = dict(zip(aliases.alias_text.str.upper().str.strip(), aliases.store_code))

    def match(text_value, norm_value):
        if text_value in canonical.values():
            return next(s for s, n in canonical.items() if n == text_value), "exact"
        if norm_value in norm_to_code:
            return norm_to_code[norm_value], "rule"
        if norm_value in alias_map:
            return alias_map[norm_value], "rule (alias list)"
        return None, "unmatched"

    out = [_rows("inventory", "store", store.store_code, store.store_code, ["exact"] * len(store))]
    rec = stg["receipt"][["branch_text", "branch_norm"]].drop_duplicates().dropna(subset=["branch_text"])
    rec = rec.sort_values("branch_text")
    res = [match(t, n) for t, n in zip(rec.branch_text, rec.branch_norm)]
    out.append(_rows("sales_db", "receipt.branch_name", rec.branch_text, [r[0] for r in res], [r[1] for r in res]))
    br = stg["branch"].sort_values("branch_id")
    res = [match(None, n) for n in br.branch_norm]
    out.append(_rows("purchasing_db", "branch", br.branch_id.astype(str), [r[0] for r in res], [r[1] for r in res]))
    return pd.concat(out, ignore_index=True)


def loyalty_code(card_no: str) -> str:
    return "L-" + re.sub(r"\D", "", card_no)


def build_xw_customer(stg: dict) -> pd.DataFrame:
    members = set(stg["loyalty_member"].card_no.dropna())
    accounts = stg["panel_account"]
    exact = dict(zip(accounts.company_name, accounts.account_no))
    normed = {_company_norm(n): a for n, a in exact.items()}
    aliases = _read_config("panel_aliases.csv", ["alias_text", "account_no"])
    alias_map = {a.strip().upper(): int(n) for a, n in zip(aliases.alias_text, aliases.account_no)}

    out = [_rows("finance_db", "panel_account", accounts.account_no.astype(str),
                 accounts.account_no.map(lambda a: f"PANEL-{a}"), ["exact"] * len(accounts))]
    cards = sorted(members | set(stg["receipt"].card_no.dropna()))
    out.append(_rows("sales_db", "receipt.card_no", cards,
                     [loyalty_code(c) if c in members else None for c in cards],
                     ["exact" if c in members else "unmatched" for c in cards]))
    texts = sorted(set(stg["receipt"].loc[stg["receipt"].customer_type == "PANEL", "panel_text"].dropna()))
    codes, methods = [], []
    for t in texts:
        if t in exact:
            codes.append(f"PANEL-{exact[t]}"), methods.append("exact")
        elif _company_norm(t) in normed:
            codes.append(f"PANEL-{normed[_company_norm(t)]}"), methods.append("rule")
        elif t.upper() in alias_map:
            codes.append(f"PANEL-{alias_map[t.upper()]}"), methods.append("rule (alias list)")
        else:
            codes.append(None), methods.append("unmatched")
    out.append(_rows("sales_db", "receipt.panel_company_text", texts, codes, methods))
    return pd.concat(out, ignore_index=True)


def build_crosswalks(stg: dict) -> dict:
    return {"xw_product": build_xw_product(stg), "xw_branch": build_xw_branch(stg),
            "xw_customer": build_xw_customer(stg)}


def crosswalk_checks(xw: dict) -> pd.DataFrame:
    """Every source key appears once (so it maps to one canonical code) and is mapped or flagged."""
    rows = []
    for name, df in xw.items():
        dup = int(df.duplicated(["source_system", "source_object", "source_key"]).sum())
        rows.append((f"{name}: source keys mapping to more than one canonical code", 0, dup, dup == 0))
        bad = int((df.canonical_code.isna() & (df.match_method != "unmatched")).sum())
        rows.append((f"{name}: keys with neither a code nor the 'unmatched' flag", 0, bad, bad == 0))
        for (system, method), n in df.groupby(["source_system", "match_method"]).size().items():
            rows.append((f"{name}: {system} keys matched by '{method}'", "info", int(n), True))
    out = pd.DataFrame(rows, columns=["check", "expected", "actual", "ok"])
    out["result"] = out.pop("ok").map({True: "PASS", False: "FAIL"})
    return out
