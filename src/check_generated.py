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


CHECKS = {"volumes": check_volumes}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "volumes"
    CHECKS[name]()
