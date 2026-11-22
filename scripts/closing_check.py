"""Closing step helpers (docs/PLAN.md, closing step 1 and 2). Synthetic data only.

1. Reads the totals table printed by the last cell of evidence/colab_run.ipynb and compares it,
   measure by measure, with the headless run (evidence/05_validation/headless_run/run_1_totals.csv).
   Writes evidence/colab_check.csv.
2. Renders each page of powerbi/nuskha.pdf to evidence/08_powerbi/powerbi_page_<n>.png so the
   report can show them (section 7 and Appendix E).

Run: .venv/Scripts/python scripts/closing_check.py
"""
import json
import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "evidence" / "colab_run.ipynb"
LOCAL = ROOT / "evidence" / "05_validation" / "headless_run" / "run_1_totals.csv"
PDF = ROOT / "powerbi" / "nuskha.pdf"
OUT_PBI = ROOT / "evidence" / "08_powerbi"


def colab_totals() -> dict:
    """Parse the pandas table printed by the notebook's last code cell (measure -> value)."""
    nb = json.loads(NB.read_text(encoding="utf-8"))
    last = [c for c in nb["cells"] if c["cell_type"] == "code"][-1]
    text = ""
    for o in last.get("outputs", []):
        text += "".join(o.get("text") or o.get("data", {}).get("text/plain", ""))
    totals = {}
    for line in text.splitlines():
        m = re.match(r"^\s*\d+\s+(.+?)\s+(-?[\d.]+)\s*$", line)  # "<index> <measure> <value>"
        if m:
            totals[m.group(1).strip()] = float(m.group(2))
    return totals


def colab_check() -> pd.DataFrame:
    colab = colab_totals()
    local = pd.read_csv(LOCAL)
    rows = []
    for measure, value in zip(local["measure"], local["value"]):
        c = colab.get(measure)
        same = c is not None and round(c, 2) == round(float(value), 2)
        rows.append({"measure": measure, "headless_local": value, "colab": c,
                     "result": "PASS" if same else "FAIL"})
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "evidence" / "colab_check.csv", index=False, lineterminator="\n")
    print(f"colab_check.csv: {(df.result == 'PASS').sum()}/{len(df)} totals identical")
    return df


def render_pdf() -> list:
    paths = []
    with fitz.open(PDF) as doc:
        for i, page in enumerate(doc, start=1):
            p = OUT_PBI / f"powerbi_page_{i}.png"
            page.get_pixmap(dpi=150).save(p)
            paths.append(p)
    print(f"rendered {len(paths)} Power BI pages to {OUT_PBI.relative_to(ROOT)}")
    return paths


if __name__ == "__main__":
    colab_check()
    render_pdf()
