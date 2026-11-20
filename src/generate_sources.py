"""Synthetic data generator for the four Nuskha source systems (seed 472).

ALL DATA IS SYNTHETIC. Rerunning gives byte-identical output.

Parts (each in src/gen/, each with its own random stream derived from seed 472):
  1 reference.py     master data: products, branches, suppliers, members, panel, FX, prices, costs
  2 transactions.py  clean receipts, receipt lines, POs, GRNs, GRN lines, stock counts
  sources.py         turns them into each source system's tables at a stage

Output of `--stage N` (N = 1 for batch 1, 2 for batch 2):
  data/generated/stage<N>/<database>/<table>.csv   one CSV per source table
  data/generated/stage<N>/inventory.db             the Inventory SQLite file
  evidence/01_sources/...                          counts, monthly totals and chart

Usage:
  python -m src.generate_sources --part reference     # reference data only (unit 1.04)
  python -m src.generate_sources --stage 1            # stage-1 sources
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from src.common import GENERATED_DIR, evidence_dir, write_evidence
from src.create_sources import create_inventory_file
from src.gen.reference import build_reference, check_reference
from src.gen.defects import plant_defects, unknown_vendor_items
from src.gen.sources import CUTOFFS, materialize
from src.gen.transactions import build_transactions

REFERENCE_DIR = GENERATED_DIR / "reference"
SYNTHETIC_NOTE = ("All files here are SYNTHETIC data from src/generate_sources.py (seed 472). "
                  "No patient data, no real brands, no real companies.\n")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write one table as UTF-8 CSV with LF line endings; empty cells mean NULL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def write_readme(folder: Path, title: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "README.md").write_text(f"# {title}\n\n{SYNTHETIC_NOTE}\n{text}", encoding="utf-8", newline="\n")


def stage_dir(stage: int) -> Path:
    return GENERATED_DIR / f"stage{stage}"


# ---------------------------------------------------------------------------
# Part 1: reference data
# ---------------------------------------------------------------------------
def run_reference(ref: dict | None = None) -> dict:
    ref = ref or build_reference()
    for name, df in ref.items():
        write_csv(df, REFERENCE_DIR / f"{name}.csv")
    write_readme(REFERENCE_DIR, "Generator reference data",
                 "The 'true' master data behind the four source systems; each source shows it in its own way.\n"
                 "Used only by the generator and for checking; the ETL never reads these files.\n")
    checks = check_reference(ref)
    write_evidence("01_sources", "reference_counts.csv", checks)
    print(checks.to_string(index=False))
    if (checks["result"] != "PASS").any():
        raise SystemExit("reference check FAILED")
    return ref


# ---------------------------------------------------------------------------
# Writing a stage
# ---------------------------------------------------------------------------
def write_inventory_db(tables: dict, path: Path) -> None:
    """Create the Inventory SQLite file from its DDL and insert the four tables."""
    if path.exists():
        path.unlink()
    create_inventory_file(path)
    con = sqlite3.connect(path)
    try:
        for table, df in tables.items():
            cols = list(df.columns)
            rows = [tuple(None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in row)
                    for row in df.itertuples(index=False)]
            con.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
        con.commit()
    finally:
        con.close()


def write_stage(tables: dict, stage: int) -> pd.DataFrame:
    """Write every source table of a stage; returns a row-count summary."""
    out = stage_dir(stage)
    counts = []
    for db, db_tables in tables.items():
        for table, df in db_tables.items():
            write_csv(df, out / db / f"{table}.csv")
            counts.append({"stage": stage, "database": db, "table": table, "rows": len(df)})
    write_inventory_db(tables["inventory"], out / "inventory.db")
    write_readme(out, f"Generated sources, stage {stage}",
                 "One folder per source database with one CSV per table (columns exactly as the source DDL),\n"
                 "plus `inventory.db`, the Inventory SQLite file. Unit 1.08 loads these into MySQL and PostgreSQL.\n")
    return pd.DataFrame(counts)


def monthly_totals(tables: dict, stage: int) -> pd.DataFrame:
    """Net sales (PKR) per month and category from the Sales tables (receipt-date month).

    A quick look at the raw sources, not the warehouse figure: only POSTED lines with a
    known item, quantity > 0, price > 0 and a receipt date inside the stage are counted,
    so planted defects do not distort the chart.
    """
    from src.gen import catalogue as cat

    rec = tables["sales_db"]["receipt"]
    lines = tables["sales_db"]["receipt_line"].merge(rec[["receipt_no", "receipt_ts", "status"]], on="receipt_no")
    qty = pd.to_numeric(lines.qty, errors="coerce")
    price = pd.to_numeric(lines.unit_price_pkr, errors="coerce")
    disc = pd.to_numeric(lines.discount_pkr, errors="coerce").fillna(0)
    ts = pd.to_datetime(lines.receipt_ts)
    lines = lines.assign(net=qty * price - disc, month=ts.dt.strftime("%Y-%m"))
    lines = lines[(lines.status == "POSTED") & (qty > 0) & (price > 0) & (ts <= pd.Timestamp(CUTOFFS[stage]))]
    # Category through the reference item list (true category); unknown till codes are left out.
    ref_items = pd.read_csv(REFERENCE_DIR / "item.csv")[["item_code", "true_category"]]
    lines = lines.merge(ref_items, on="item_code", how="inner")
    table = lines.pivot_table(index="month", columns="true_category", values="net", aggfunc="sum", fill_value=0)
    table = table[[c for c in cat.CATEGORIES if c in table.columns]]
    table["Total"] = table.sum(axis=1)
    table["receipt_lines"] = lines.groupby("month").size()
    return table.round(2).reset_index()


def monthly_chart(totals: pd.DataFrame, path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    x = totals["month"]
    ax1.plot(x, totals["Total"] / 1e6, marker="o", color="#2b5d8a")
    ax1.set_ylabel("Net sales (PKR million)")
    ax1.set_ylim(bottom=0)
    ax1.set_title(title)
    ax1.grid(alpha=0.3)
    for c in [c for c in totals.columns if c not in ("month", "Total", "receipt_lines")]:
        ax2.plot(x, totals[c] / 1e6, label=c)
    ax2.set_ylabel("Net sales by category (PKR million)")
    ax2.set_ylim(bottom=0)
    ax2.legend(fontsize=8, ncol=4)
    ax2.grid(alpha=0.3)
    ax2.tick_params(axis="x", rotation=90)
    fig.text(0.01, 0.005, "Synthetic data (seed 472). Net sales = qty x price - discount, POSTED receipts, "
             "by receipt month.", fontsize=8)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def build_all(stage: int) -> tuple[dict, dict, dict]:
    """Run every generator part in order and return (reference, transactions, source tables)."""
    ref = build_reference()
    ref["unknown_vendor_item"] = unknown_vendor_items(ref)
    tx = build_transactions(ref)            # part 2: clean history
    tx = plant_defects(ref, tx)             # part 3: planted defects + ledger
    tables = materialize(ref, tx, stage)
    return ref, tx, tables


def run_stage(stage: int) -> dict:
    ref, tx, tables = build_all(stage)
    counts = write_stage(tables, stage)
    write_evidence("01_sources", f"stage{stage}_row_counts.csv", counts)
    print(counts.to_string(index=False))

    # Defect ledger (every planted row) and the till's double-export list for this stage.
    ledger = tx["ledger"][tx["ledger"].stage == stage]
    write_evidence("01_sources", "defect_ledger.csv" if stage == 1 else "defect_ledger_stage2.csv", ledger)
    dup = tx["double_export"]
    write_csv(dup[dup.stage == stage].drop(columns="stage"), stage_dir(stage) / "double_export.csv")

    totals = monthly_totals(tables, stage)
    write_evidence("01_sources", f"stage{stage}_monthly_totals.csv", totals)
    monthly_chart(totals, evidence_dir("01_sources") / f"stage{stage}_monthly_totals.png",
                  f"Nuskha monthly net sales, stage {stage} sources (synthetic)")
    write_evidence("01_sources", "planted_patterns.csv", tx["patterns"])
    return tables


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--part", choices=["reference"], help="build only one generator part")
    parser.add_argument("--stage", type=int, choices=[1, 2], default=1, help="source state to write")
    args = parser.parse_args()
    if args.part == "reference":
        run_reference()
    else:
        run_reference()
        run_stage(args.stage)


if __name__ == "__main__":
    main()
