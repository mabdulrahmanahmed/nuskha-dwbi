"""Units 5.04/5.05: build report/report.docx (and report.pdf) from report/report.md. Synthetic data.

report.md is plain Markdown (headings, paragraphs, bullet and numbered lists, pipe tables, images,
**bold**, `code`) plus a few conventions:
  lines before the first "## " heading     the cover page (title, course, team, instructor, note)
  Table: <caption>                          numbered caption for the next table
  ![caption](path "w=12")                   numbered figure; optional width in cm (default 14)
  Source: ...                               small italic source note
  <!-- appendix -->                         everything after it is an appendix (not counted in pages)
  <!-- code: path -->                       a SQL file printed in a small monospaced font
  <!-- csv: path -->                        a CSV file printed as a table
  <!-- queries -->                          the 12 analytic queries: reading, SQL and first result rows
  <!-- rejects -->                          reject counts by batch, table and reason

House style (docs/DECISIONS.md, closing): A4, 2.54 cm margins; body Calibri 11 pt, justified, 1.15
line spacing, 6 pt after; headings Cambria bold navy (14/12/11 pt), kept with the next paragraph;
lists with a hanging indent; tables with a navy header row that repeats, light banding, rows never
split, the whole table kept on one page; numbered table captions above and figure captions below;
header with the short title, footer "Page X of Y"; cover page with a table of contents.
After building, Microsoft Word moves any main section that would fit on one page but straddles two
onto a new page (white space is allowed for that), updates the contents and exports the PDF.

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
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from src.common import EVIDENCE_DIR, ROOT

REPORT_DIR = ROOT / "report"
MD = REPORT_DIR / "report.md"
DOCX = REPORT_DIR / "report.docx"
PDF = REPORT_DIR / "report.pdf"
OUT = EVIDENCE_DIR / "09_report"

# ---------- house style ----------
BODY_FONT, HEAD_FONT, CODE_FONT = "Calibri", "Cambria", "Consolas"
NAVY = RGBColor(0x1F, 0x38, 0x64)
GREY = RGBColor(0x59, 0x59, 0x59)
CODE_GREY = RGBColor(0x40, 0x40, 0x40)
HEADER_FILL, BAND_FILL, BORDER = "1F3864", "EEF2F8", "A6A6A6"
SHORT_TITLE = "Nuskha Pharmacies: data warehouse, BI and AI layer"
J, L, C = WD_ALIGN_PARAGRAPH.JUSTIFY, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER
NUM = {"table": 0, "figure": 0}   # caption counters


def set_font(obj, name: str) -> None:
    """Set a font on a style or run for every script, dropping theme fonts that would override it."""
    obj.font.name = name
    rfonts = obj._element.get_or_add_rPr().get_or_add_rFonts()
    for a in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        rfonts.attrib.pop(qn("w:" + a), None)
    for a in ("ascii", "hAnsi", "cs", "eastAsia"):
        rfonts.set(qn("w:" + a), name)


def para_style(doc, name, base="Normal"):
    try:
        return doc.styles[name]
    except KeyError:
        s = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = doc.styles[base]
        return s


def setup_styles(doc) -> None:
    st = doc.styles
    normal = st["Normal"]
    set_font(normal, BODY_FONT)
    normal.font.size = Pt(11)
    pf = normal.paragraph_format
    pf.line_spacing, pf.space_before, pf.space_after, pf.alignment = 1.15, Pt(0), Pt(6), J
    pf.widow_control = True
    for name, size, before, after in (("Heading 1", 14, 16, 6), ("Heading 2", 12, 10, 4), ("Heading 3", 11, 8, 3)):
        h = st[name]
        set_font(h, HEAD_FONT)
        h.font.size, h.font.bold, h.font.italic, h.font.color.rgb = Pt(size), True, False, NAVY
        hp = h.paragraph_format
        hp.space_before, hp.space_after, hp.keep_with_next, hp.alignment, hp.line_spacing = Pt(before), Pt(after), True, L, 1.0
    t = st["Title"]
    set_font(t, HEAD_FONT)
    t.font.size, t.font.bold, t.font.color.rgb = Pt(24), True, NAVY
    t.paragraph_format.alignment = C
    t.paragraph_format.space_after = Pt(12)
    ppr = t._element.get_or_add_pPr()
    for b in ppr.findall(qn("w:pBdr")):          # the default Title style draws a rule under the title
        ppr.remove(b)
    for name in ("List Bullet", "List Number"):
        lp = st[name].paragraph_format
        lp.left_indent, lp.first_line_indent, lp.space_after, lp.alignment = Cm(0.75), Cm(-0.5), Pt(3), L
    cap = para_style(doc, "Report Caption")
    cap.font.size, cap.font.color.rgb = Pt(9.5), GREY
    cap.paragraph_format.alignment, cap.paragraph_format.space_before, cap.paragraph_format.space_after = C, Pt(2), Pt(8)
    note = para_style(doc, "Source Note")
    note.font.size, note.font.italic, note.font.color.rgb = Pt(9), True, GREY
    note.paragraph_format.alignment, note.paragraph_format.space_after = L, Pt(8)
    item = para_style(doc, "Numbered Item")               # "1.<tab>text" with a hanging indent
    ip = item.paragraph_format
    ip.left_indent, ip.first_line_indent, ip.space_after, ip.alignment = Cm(0.75), Cm(-0.5), Pt(3), L
    ip.tab_stops.add_tab_stop(Cm(0.75))
    code = para_style(doc, "Code Block")
    set_font(code, CODE_FONT)
    code.font.size, code.font.color.rgb = Pt(7.5), CODE_GREY
    cp = code.paragraph_format
    cp.alignment, cp.space_after, cp.line_spacing, cp.left_indent = L, Pt(0), 1.0, Cm(0.3)


def add_field(par, instr: str, size=None, color=None) -> None:
    """Insert a Word field (PAGE, NUMPAGES, TOC ...); Word fills in the value when it lays out the page."""
    def run_with(el):
        r = par.add_run()
        r._r.append(el)
        return r
    b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f" {instr} "
    sep = OxmlElement("w:fldChar"); sep.set(qn("w:fldCharType"), "separate")
    e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end")
    runs = [run_with(b), run_with(it), run_with(sep), par.add_run("1"), run_with(e)]
    for r in runs:
        if size:
            r.font.size = size
        if color:
            r.font.color.rgb = color


def setup_page(doc) -> None:
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Cm(2.54)
    sec.header_distance = sec.footer_distance = Cm(1.25)
    sec.different_first_page_header_footer = True     # clean cover page
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = hp.add_run(SHORT_TITLE)
    r.font.size, r.font.color.rgb = Pt(9), GREY
    fp = sec.footer.paragraphs[0]
    fp.alignment = C
    for part in ("Page ", None, " of ", "NUMPAGES"):
        if part in ("Page ", " of "):
            r = fp.add_run(part)
            r.font.size, r.font.color.rgb = Pt(9), GREY
        else:
            add_field(fp, part or "PAGE", Pt(9), GREY)


# ---------- small Markdown helpers ----------

def add_runs(par, text: str, size=None, bold=None, color=None) -> None:
    """Add text to a paragraph, turning **bold** and `code` spans into formatted runs."""
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            r = par.add_run(part[2:-2].replace("`", ""))   # code marks inside a bold lead-in are dropped
            r.bold = True
        elif part.startswith("`"):
            r = par.add_run(part[1:-1])
            set_font(r, CODE_FONT)
            r.font.size = Pt((size.pt if size else 11) - 1.5)
            if color is None:
                r.font.color.rgb = CODE_GREY
        else:
            r = par.add_run(part)
        if size and not part.startswith("`"):
            r.font.size = size
        if bold:
            r.bold = True
        if color is not None:
            r.font.color.rgb = color


def shade(cell, fill: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def caption(doc, kind: str, text: str, keep_next: bool) -> None:
    NUM[kind] += 1
    p = doc.add_paragraph(style="Report Caption")
    p.paragraph_format.keep_with_next = keep_next
    if kind == "table":                                   # table captions sit above the table
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(6), Pt(3)
    r = p.add_run(f"{kind.capitalize()} {NUM[kind]}. ")
    r.bold = True
    add_runs(p, text, size=Pt(9.5))


def add_table(doc, rows: list[list[str]], font_pt: float = 9, title: str | None = None) -> None:
    if title:
        caption(doc, "table", title, keep_next=True)
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblpr = table._tbl.tblPr
    w = OxmlElement("w:tblW"); w.set(qn("w:w"), "5000"); w.set(qn("w:type"), "pct")   # full text width
    for old in tblpr.findall(qn("w:tblW")):
        tblpr.remove(old)
    tblpr.append(w)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "single"); b.set(qn("w:sz"), "4"); b.set(qn("w:color"), BORDER)
        borders.append(b)
    tblpr.append(borders)
    mar = OxmlElement("w:tblCellMar")
    for edge, v in (("top", "28"), ("bottom", "28"), ("left", "85"), ("right", "85")):
        m = OxmlElement(f"w:{edge}"); m.set(qn("w:w"), v); m.set(qn("w:type"), "dxa")
        mar.append(m)
    tblpr.append(mar)
    # column widths follow the content: long text columns get more room, short codes less
    # and no column is narrower than its longest word, so words never break mid-word
    text_w, char_cm = 15.9, 0.021 * font_pt               # rough width of one character at this size
    score, floor = [], []
    for j in range(len(rows[0])):
        cells = [re.sub(r"[*`]", "", str(r[j])) for r in rows]
        body = cells[1:] or cells                         # header words may break at "_" (see below)
        longest_word = max(len(w) for c in body for w in (c.split() or [""]))
        longest_word = max(longest_word, max(len(w) for w in re.split(r"[\s_]+", cells[0]) or [""]))
        score.append(max(min(max(len(c) for c in cells), 45), 4))
        floor.append(longest_word * char_cm + 0.4)        # + cell padding
    if sum(floor) > text_w:                               # very wide tables: shrink the floors to fit
        floor = [f * text_w / sum(floor) for f in floor]
    widths = [text_w * s / sum(score) for s in score]
    for _ in range(len(widths)):                          # lift narrow columns, take the room from the wide ones
        short = [k for k, w in enumerate(widths) if w < floor[k]]
        if not short:
            break
        need = sum(floor[k] - widths[k] for k in short)
        for k in short:
            widths[k] = floor[k]
        donors = [k for k in range(len(widths)) if k not in short]
        pool = sum(widths[k] - floor[k] for k in donors) or 1
        for k in donors:
            widths[k] -= need * (widths[k] - floor[k]) / pool
    widths = [Cm(w) for w in widths]
    layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    for col, wd in zip(table.columns, widths):
        col.width = wd
    n = len(rows)
    for i, row in enumerate(rows):
        trpr = table.rows[i]._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))          # a row never breaks across pages
        if i == 0:
            trpr.append(OxmlElement("w:tblHeader"))      # header row repeats on a new page
        for j, cell in enumerate(row):
            c = table.cell(i, j)
            c.width = widths[j]
            c.text = ""
            p = c.paragraphs[0]
            p.paragraph_format.space_after = p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.line_spacing, p.paragraph_format.alignment = 1.0, L
            p.paragraph_format.keep_with_next = i < n - 1   # keep the table on one page
            if i == 0:
                shade(c, HEADER_FILL)
                head = str(cell).replace("_", "_​")      # long column names may wrap after "_"
                add_runs(p, head, size=Pt(font_pt), bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
            else:
                if i % 2 == 0:
                    shade(c, BAND_FILL)
                add_runs(p, str(cell), size=Pt(font_pt))
    gap = doc.add_paragraph()
    gap.paragraph_format.space_after, gap.paragraph_format.line_spacing = Pt(0), Pt(8)


def add_figure(doc, path: Path, text: str, width_cm: float) -> None:
    p = doc.add_paragraph()
    p.alignment = C
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(6), Pt(2)
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    caption(doc, "figure", text, keep_next=False)


def add_code(doc, text: str) -> None:
    for line in text.rstrip().splitlines():
        doc.add_paragraph(line if line else " ", style="Code Block")
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


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
        doc.add_heading(f"{qid}. {sql.stem[4:].replace('_', ' ')}", level=2)
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
            add_table(doc, rows, 7.5)


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
    # report copy of the star schema: drop the empty left margin and the title (the caption says it)
    from PIL import Image
    im = Image.open(EVIDENCE_DIR / "03_warehouse" / "star_schema.png")
    w, h = im.size
    im.crop((int(w * 0.135), int(h * 0.105), int(w * 0.99), int(h * 0.85))).save(OUT / "star_schema_report.png")


# ---------- build ----------

def cover(doc, lines: list[str]) -> None:
    """Cover page: title, course line, team, instructor, synthetic-data note, then the contents."""
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(60)
    body = [l.strip() for l in lines if l.strip()]
    title = body[0].lstrip("#").strip()
    doc.add_paragraph(title, style="Title")
    looks = [(Pt(12), False, None, 6), (Pt(11.5), True, None, 6), (Pt(11), False, None, 6), (Pt(9.5), False, GREY, 6)]
    for k, text in enumerate(body[1:]):
        size, bold, color, after = looks[min(k, len(looks) - 1)]
        p = doc.add_paragraph()
        p.alignment = C
        p.paragraph_format.space_after = Pt(after)
        if k == 3:
            p.paragraph_format.space_before = Pt(18)
        add_runs(p, text, size=size, bold=bold, color=color)
        if k == 3:
            for r in p.runs:
                r.italic = True
    h = doc.add_paragraph()
    h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(48), Pt(6)
    r = h.add_run("Contents")
    set_font(r, HEAD_FONT)
    r.font.size, r.font.bold, r.font.color.rgb = Pt(13), True, NAVY
    toc = doc.add_paragraph()
    add_field(toc, 'TOC \\o "1-1" \\h \\z \\u')


def build_docx() -> None:
    NUM.update(table=0, figure=0)
    doc = Document()
    setup_styles(doc)
    setup_page(doc)

    lines = MD.read_text(encoding="utf-8").splitlines()
    first = next(k for k, l in enumerate(lines) if l.startswith("## "))
    cover(doc, lines[:first])
    i, in_appendix, pending_title, started = first, False, None, False
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("Table: "):
            pending_title = s[len("Table: "):]
            i += 1
            continue
        m = re.match(r"<!--\s*(\w+)(?::\s*(.+?))?\s*-->", s)
        if m:
            kind, arg = m.group(1), m.group(2)
            if kind == "appendix":
                in_appendix = True
            elif kind == "code":
                p = doc.add_paragraph(style="Source Note")
                p.add_run(arg)
                add_code(doc, (ROOT / arg).read_text(encoding="utf-8"))
            elif kind == "csv":
                add_table(doc, csv_rows(ROOT / arg), 8, pending_title)
                pending_title = None
            elif kind == "queries":
                queries_section(doc)
            elif kind == "rejects":
                rejects_section(doc)
            i += 1
            continue
        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            h = doc.add_heading(s.lstrip("#").strip(), level=max(level - 1, 1))
            if level == 2 and not started:
                h.paragraph_format.page_break_before = True   # section 1 starts after the cover
                started = True
            if in_appendix and level == 2:
                h.paragraph_format.page_break_before = True   # every appendix starts on a new page
            i += 1
            continue
        if s.startswith("!["):
            mm = re.match(r'!\[(.*?)\]\((\S+?)(?:\s+"w=([\d.]+)")?\)', s)
            add_figure(doc, (MD.parent / mm.group(2)).resolve(), mm.group(1), float(mm.group(3) or 14))
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            add_table(doc, rows, title=pending_title)
            pending_title = None
            continue
        if s.startswith("Source:"):
            add_runs(doc.add_paragraph(style="Source Note"), s)
            i += 1
            continue
        if s.startswith("- "):
            add_runs(doc.add_paragraph(style="List Bullet"), s[2:])
            i += 1
            continue
        if re.match(r"^\d+\. ", s):
            # numbered item: the number is taken from the Markdown, so every list starts again at 1
            num, text = s.split(" ", 1)
            p = doc.add_paragraph(style="Numbered Item")
            p.add_run(num + "\t")
            add_runs(p, text)
            i += 1
            continue
        # plain paragraph: join following non-empty, non-special lines
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||!\[|<!--|- |\d+\. |Table: |Source:)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        p = doc.add_paragraph()
        text = " ".join(para)
        add_runs(p, text)
        spans = re.findall(r"`([^`]+)`", text)
        if any(len(c) > 28 for c in spans) or sum(len(c) for c in spans) > 80:
            p.alignment = L        # long file paths cannot break, so justifying would stretch the word gaps
        if p.text.rstrip().endswith(":"):             # an intro line stays with the list or table it introduces
            p.paragraph_format.keep_with_next = True
    doc.save(DOCX)
    print(f"wrote {DOCX.relative_to(ROOT)}")


# Word pass: move a main section that would fit on one page but straddles two onto a new page,
# refresh the contents, save, export the PDF and count the pages before Appendix A.
WORD_PASS = r"""
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$d = $w.Documents.Open('__DOCX__')
$d.Repaginate()
$ps = $d.PageSetup
$top = $ps.TopMargin
$bottom = $ps.PageHeight - $ps.BottomMargin
$bodyH = $bottom - $top
$skip = @{}
$moved = @()
for ($iter = 0; $iter -lt 25; $iter++) {
  $heads = New-Object System.Collections.ArrayList
  foreach ($p in $d.Paragraphs) {
    if ($p.OutlineLevel -eq 1) {
      [void]$heads.Add($p)
      if ($p.Range.Text.Trim() -like 'Appendix A*') { break }
    }
  }
  $changed = $false
  for ($k = 0; $k -lt $heads.Count - 1; $k++) {
    $h = $heads[$k]
    $name = $h.Range.Text.Trim()
    if ($h.Format.PageBreakBefore -or $skip.ContainsKey($name)) { continue }
    $sp = $h.Range.Information(3)
    $ht = $h.Range.Information(6)
    $endPos = $heads[$k + 1].Range.Start - 1
    $er = $d.Range($endPos, $endPos)
    $ep = $er.Information(3)
    $ev = $er.Information(6)
    if ($ep -eq $sp + 1 -and (($bottom - $ht) + ($ev + 14 - $top)) -le $bodyH) {
      $h.Format.PageBreakBefore = $true
      $d.Repaginate()
      if ($d.Range($endPos, $endPos).Information(3) -ne $h.Range.Information(3)) {
        $h.Format.PageBreakBefore = $false
        $d.Repaginate()
        $skip[$name] = $true
      } else {
        $moved += $name
        $changed = $true
        break
      }
    }
  }
  if (-not $changed) { break }
}
$d.TablesOfContents.Item(1).Update()
$d.Repaginate()
$appx = 0
foreach ($p in $d.Paragraphs) {
  if ($p.OutlineLevel -eq 1 -and $p.Range.Text.Trim() -like 'Appendix A*') { $appx = $p.Range.Information(3); break }
}
$total = $d.ComputeStatistics(2)
$d.Save()
$d.ExportAsFixedFormat('__PDF__', 17)
$d.Close(0)
$w.Quit()
Write-Output ("moved: " + ($moved -join ' | '))
Write-Output "$total,$appx"
"""


def build_pdf_and_count() -> None:
    """Run the Word pass (Windows only) and record the page count before Appendix A."""
    ps = WORD_PASS.replace("__DOCX__", str(DOCX)).replace("__PDF__", str(PDF))
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if res.returncode != 0 or "," not in res.stdout:
        print("PDF export skipped (Microsoft Word not available):", (res.stderr or res.stdout).strip()[:400])
        return
    out = res.stdout.strip().splitlines()
    print(next((l for l in out if l.startswith("moved:")), "moved:"))
    total, appx = [int(x) for x in out[-1].split(",")]
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
            # rounded up: 128,333 in the text, 128332.85 in the evidence
            found = found or re.search(rf"(?<![\d.]){int(whole) - 1}\.[5-9]", blob) is not None
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
