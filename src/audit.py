"""Units 5.06/5.09: check that every file named in evidence/INDEX.md and docs/AUDIT.md exists. Synthetic data.

A "file" is any backticked path that starts with a top-level project folder or file name
(evidence/, sql/, src/, docs/, report/, powerbi/, config/, pipeline.ipynb, README.md, ...).
A path ending in "/" must be a non-empty folder. Paths written as "T1.md … T6.md" are expanded.

  python -m src.audit           # writes evidence/09_report/index_check.csv (and audit_check.csv)
"""
from __future__ import annotations

import re
import sys

import pandas as pd

from src.common import EVIDENCE_DIR, ROOT

TOP = ("evidence/", "sql/", "src/", "docs/", "report/", "powerbi/", "config/", "scripts/",
       "pipeline.ipynb", "README.md", "START_HERE.md")


def paths_in(md_text: str) -> list[str]:
    found = []
    for p in re.findall(r"`([^`\s]+)`", md_text):
        if p.startswith(TOP):
            found.append(p)
    # expand "traces/T1.md … traces/T6.md"
    if "T1.md` … `" in md_text:
        base = "evidence/04_metadata_lineage/traces/"
        found += [f"{base}T{i}.md" for i in range(1, 7)]
    return sorted(set(found))


def check(md_rel: str, out_name: str) -> bool:
    md = ROOT / md_rel
    if not md.exists():
        print(f"{md_rel} missing")
        return False
    rows = []
    for p in paths_in(md.read_text(encoding="utf-8")):
        target = ROOT / p
        ok = (target.is_dir() and any(target.iterdir())) if p.endswith("/") else target.exists()
        rows.append({"path": p, "exists": "PASS" if ok else "FAIL"})
    df = pd.DataFrame(rows)
    df.to_csv(EVIDENCE_DIR / "09_report" / out_name, index=False, lineterminator="\n")
    bad = df[df["exists"] == "FAIL"]
    print(f"{md_rel}: {len(df) - len(bad)}/{len(df)} paths exist")
    for p in bad["path"]:
        print("  missing:", p)
    return bad.empty


if __name__ == "__main__":
    ok = check("evidence/INDEX.md", "index_check.csv")
    if (ROOT / "docs" / "AUDIT.md").exists():
        ok = check("docs/AUDIT.md", "audit_check.csv") and ok
    sys.exit(0 if ok else 1)
