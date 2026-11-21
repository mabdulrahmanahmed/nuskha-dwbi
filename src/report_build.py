"""Units 5.04/5.05: build report/report.docx (and report.pdf) from report/report.md. Synthetic data.

report.md is plain Markdown (headings, paragraphs, bullet and numbered lists, pipe tables, images,
**bold**) plus a few directives, each an HTML comment on its own line:
  <!-- appendix -->          page break; everything after it is an appendix (not counted in pages)
  <!-- code: path -->        a SQL file printed in a small monospaced font
  <!-- csv: path -->         a CSV file printed as a table
  <!-- queries -->           the 12 analytic queries: reading, SQL and the first rows of each result
  <!-- rejects -->           reject counts by batch, table and reason, from etl.rejects evidence

  python -m src.report_build            # docx + PDF (PDF through Microsoft Word, Windows only)
  python -m src.report_build --check    # also check that every number in the text is in an evidence file

Writes evidence/09_report/report_numbers_check.csv, report_pages.csv and derived_figures.csv.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_BREAK
from docx.shared import Cm, Pt

from src.common import EVIDENCE_DIR, ROOT

REPORT_DIR = ROOT / "report"
MD = REPORT_DIR / "report.md"
DOCX = REPORT_DIR / "report.docx"
PDF = REPORT_DIR / "report.pdf"
OUT = EVIDENCE_DIR / "09_report"


# ---------- small Markdown helpers ----------

def add_runs(par, text: str) -> None:
    """Add text to a paragraph, turning **bold** and `code` spans into formatted runs."""
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`"):
            r = par.add_run(part[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(9)
        else:
            par.add_run(part)


def add_table(doc, rows: list[list[str]], font_pt: float = 8.5) -> None:
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Light Grid Accent 1"
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            c = table.cell(i, j)
            c.text = ""
            add_runs(c.paragraphs[0], str(cell))
            for r in c.paragraphs[0].runs:
                r.font.size = Pt(font_pt)
                if i == 0:
                    r.bold = True
    doc.add_paragraph()


def add_code(doc, text: str) -> None:
    for line in text.rstrip().splitlines():
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(line if line else " ")
        r.font.name = "Consolas"
        r.font.size = Pt(7)
    doc.add_paragraph()


def csv_rows(path: Path, max_rows: int | None = None) -> list[list[str]]:
    df = pd.read_csv(path, dtype=str).fillna("")
    if max_rows:
        df = df.head(max_rows)
    return [list(df.columns)] + df.values.tolist()


# ---------- directives ----------

def queries_section(doc) -> None:
    readings = (EVIDENCE_DIR / "06_sql" / "readings.md").read_text(encoding="utf-8")
    blocks = re.split(r"^## ", readings, flags=re.M)[1:]
    for sql in sorted((ROOT / "sql" / "04_queries").glob("A*.sql")):
        qid = "A" + str(int(sql.stem[1:3]))
        block = next((b for b in blocks if b.startswith(qid + " ")), "")
        doc.add_heading(f"{qid}. {sql.stem[4:].replace('_', ' ')}", level=3)
        for line in block.splitlines()[1:]:
            line = line.strip()
            if line.startswith("> ") or line.startswith("- Lab"):
                add_runs(doc.add_paragraph(), line.lstrip("> -"))
        add_code(doc, sql.read_text(encoding="utf-8"))
        res = EVIDENCE_DIR / "06_sql" / f"{sql.stem}.csv"
        if res.exists():
            rows = csv_rows(res, 8)
            if len(rows[0]) > 8:  # wide results: keep the first 8 columns so the table fits the page
                rows = [r[:8] for r in rows]
            add_table(doc, rows, 7)


def rejects_section(doc) -> None:
    frames = []
    for f, b in [("rejects.csv", 1), ("rejects_batch_2.csv", 2)]:
        p = EVIDENCE_DIR / "02_etl" / f
        if p.exists():
            frames.append(pd.read_csv(p, dtype=str))
    df = pd.concat(frames)
    s = df.groupby(["batch_id", "source_table", "reason_code"]).size().reset_index(name="rows")
    s.to_csv(OUT / "reject_summary.csv", index=False, lineterminator="\n")
    add_table(doc, [list(s.columns)] + s.astype(str).values.tolist())


def derived_figures() -> None:
    """Figures the report quotes that are sums of evidence values (kept as evidence too)."""
    fc = pd.read_csv(EVIDENCE_DIR / "07_ai" / "forecast_results.csv")
    fut = fc[fc["label"] == "FORECAST"]
    rows = [
        ("forecast Nov 2026 - Jan 2027 total (PKR)", round(fut["prediction"].sum(), 2)),
        ("forecast Nov 2026 - Jan 2027 lower total (PKR)", round(fut["lower"].sum(), 2)),
        ("forecast Nov 2026 - Jan 2027 upper total (PKR)", round(fut["upper"].sum(), 2)),
    ]
    pd.DataFrame(rows, columns=["figure", "value"]).to_csv(OUT / "derived_figures.csv", index=False,
                                                            lineterminator="\n")


# ---------- build ----------

def build_docx() -> None:
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)

    lines = MD.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        m = re.match(r"<!--\s*(\w+)(?::\s*(.+?))?\s*-->", s)
        if m:
            kind, arg = m.group(1), m.group(2)
            if kind == "appendix":
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            elif kind == "code":
                doc.add_paragraph().add_run(arg).italic = True
                add_code(doc, (ROOT / arg).read_text(encoding="utf-8"))
            elif kind == "csv":
                add_table(doc, csv_rows(ROOT / arg), 7.5)
            elif kind == "queries":
                queries_section(doc)
            elif kind == "rejects":
                rejects_section(doc)
            i += 1
            continue
        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            text = s.lstrip("#").strip()
            if level == 1:
                doc.add_heading(text, level=0)
            else:
                if level == 2 and text.startswith("Appendix") and not text.startswith("Appendix A"):
                    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
                doc.add_heading(text, level=level - 1)
            i += 1
            continue
        if s.startswith("!["):
            mm = re.match(r"!\[(.*?)\]\((.*?)\)", s)
            img = (MD.parent / mm.group(2)).resolve()
            doc.add_picture(str(img), width=Cm(13.5))
            cap = doc.add_paragraph()
            r = cap.add_run(mm.group(1))
            r.italic = True
            r.font.size = Pt(9)
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            add_table(doc, rows)
            continue
        if re.match(r"^(- |\d+\. )", s):
            style = "List Bullet" if s.startswith("- ") else "List Number"
            add_runs(doc.add_paragraph(style=style), re.sub(r"^(- |\d+\. )", "", s))
            i += 1
            continue
        # plain paragraph: join following non-empty, non-special lines
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||!\[|<!--|- |\d+\. )", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        add_runs(doc.add_paragraph(), " ".join(para))
    doc.save(DOCX)
    print(f"wrote {DOCX.relative_to(ROOT)}")


def build_pdf_and_count() -> None:
    """Export the PDF with Microsoft Word and count pages before Appendix A (Windows only)."""
    ps = f"""
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$d = $w.Documents.Open('{DOCX}')
$total = $d.ComputeStatistics(2)
$r = $d.Content
$f = $r.Find
$null = $f.Execute('Appendix A. Warehouse DDL')
$appx = $r.Information(3)
$d.ExportAsFixedFormat('{PDF}', 17)
$d.Close(0)
$w.Quit()
Write-Output "$total,$appx"
"""
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if res.returncode != 0 or "," not in res.stdout:
        print("PDF export skipped (Microsoft Word not available):", res.stderr.strip()[:300])
        return
    total, appx = [int(x) for x in res.stdout.strip().splitlines()[-1].split(",")]
    main_pages = appx - 1
    ok = 8 <= main_pages <= 12
    pd.DataFrame([{"total_pages": total, "pages_before_appendices": main_pages,
                   "required": "8-12", "result": "PASS" if ok else "FAIL"}]).to_csv(
        OUT / "report_pages.csv", index=False, lineterminator="\n")
    print(f"wrote {PDF.relative_to(ROOT)}: {total} pages, {main_pages} before the appendices ({'PASS' if ok else 'FAIL'})")


# ---------- number check (5.04 acceptance) ----------

def number_check() -> bool:
    """Every number in the report text (before the appendices) must appear in an evidence file."""
    text = MD.read_text(encoding="utf-8").split("<!-- appendix -->")[0]
    corpus = []
    for p in list(EVIDENCE_DIR.rglob("*.csv")) + list(EVIDENCE_DIR.rglob("*.md")) + \
            [ROOT / "powerbi" / "reconciliation.csv", ROOT / "powerbi" / "model_checks.csv"]:
        if "raw" in p.parts or "preview_duckdb" in p.parts or "offline_dry_run" in p.parts:
            continue
        corpus.append(p.read_text(encoding="utf-8", errors="replace").replace(",", " , "))
    blob = "\n".join(corpus)
    blob_nocomma = blob.replace(" , ", ",")
    rows = []
    for tok in sorted(set(re.findall(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?", text))):
        val = tok.replace(",", "")
        if "." not in val and int(val) <= 100:      # small counts (sections, months, branches)
            continue
        if "." not in val and 2023 <= int(val) <= 2027:   # years
            continue
        whole, _, frac = val.partition(".")
        found = (re.search(rf"(?<![\d.]){re.escape(val)}(?!\d)", blob) is not None
                 or re.search(rf"(?<![\d.]){re.escape(whole)}\.\d", blob) is not None and not frac
                 or re.search(rf"(?<![\d.]){re.escape(val)}\d*", blob) is not None and frac != ""
                 or tok in blob_nocomma)
        if not found and not frac:   # integer in the text may be a rounded decimal (70,806 -> 70806.15)
            found = re.search(rf"(?<![\d.]){re.escape(whole)}(?:\.\d+)?(?!\d)", blob) is not None
        if not found and frac:       # e.g. 0.80 vs 0.8, 25.7 vs 25.70
            found = re.search(rf"(?<![\d.]){re.escape(whole)}\.{re.escape(frac.rstrip('0') or '0')}", blob) is not None
        rows.append({"number": tok, "found_in_evidence": "PASS" if found else "FAIL"})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "report_numbers_check.csv", index=False, lineterminator="\n")
    bad = df[df["found_in_evidence"] == "FAIL"]
    print(f"number check: {len(df) - len(bad)}/{len(df)} numbers found in evidence")
    if len(bad):
        print("missing:", ", ".join(bad["number"]))
    return bad.empty


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    derived_figures()
    build_docx()
    if not a.no_pdf:
        build_pdf_and_count()
    if a.check and not number_check():
        sys.exit(1)
