"""Synthetic data generator for the four Nuskha source systems (seed 472).

ALL DATA IS SYNTHETIC. Rerunning gives byte-identical output.

Parts (each in src/gen/):
  reference     master data: products, branches, suppliers, members, panel, FX, prices, costs
Output: data/generated/reference/*.csv, plus a row-count check in evidence/01_sources/.

Usage:
  python -m src.generate_sources --part reference
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.common import GENERATED_DIR, write_evidence
from src.gen.reference import build_reference, check_reference

REFERENCE_DIR = GENERATED_DIR / "reference"


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write one table as UTF-8 CSV with LF line endings; empty cells mean NULL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def write_readme(folder: Path, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "README.md").write_text(text, encoding="utf-8", newline="\n")


def run_reference() -> dict[str, pd.DataFrame]:
    ref = build_reference()
    for name, df in ref.items():
        write_csv(df, REFERENCE_DIR / f"{name}.csv")
    write_readme(REFERENCE_DIR,
                 "# Generator reference data (SYNTHETIC, seed 472)\n\n"
                 "The 'true' master data behind the four source systems: every source shows it in its own way.\n"
                 "Used only by the generator and for checking; the ETL never reads these files.\n")
    checks = check_reference(ref)
    write_evidence("01_sources", "reference_counts.csv", checks)
    print(checks.to_string(index=False))
    if (checks["result"] != "PASS").any():
        raise SystemExit("reference check FAILED")
    return ref


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--part", choices=["reference"], default="reference")
    args = parser.parse_args()
    if args.part == "reference":
        run_reference()


if __name__ == "__main__":
    main()
