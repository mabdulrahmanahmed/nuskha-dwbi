"""Draw one ERD per source department straight from its DDL file (sql/01_source_ddl/).

For each department this writes, under evidence/01_sources/erd/:
  <dept>_erd.dot   Graphviz description (tables, columns, PK/FK, relationships)
  <dept>_erd.png   the picture: rendered by Graphviz `dot` when it is installed,
                   otherwise drawn with matplotlib (same content, simpler layout)

Relationships come only from declared REFERENCES clauses ("declared"). The legacy
Inventory database declares none; links implied by matching column names
(item_id, store_code) are drawn dashed and labelled "not declared" so the picture
shows what reverse engineering (unit 3.09) will have to infer.

Usage: python -m src.erd
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.common import SQL_DIR, evidence_dir

DEPARTMENTS = {   # department -> (DDL file, engine label for the title)
    "sales": ("sales_mysql.sql", "MySQL sales_db"),
    "finance": ("finance_mysql.sql", "MySQL finance_db"),
    "purchasing": ("purchasing_postgres.sql", "PostgreSQL purchasing_db"),
    "inventory": ("inventory_sqlite.sql", "SQLite inventory.db"),
}
TYPE_STOP = {"PRIMARY", "NOT", "NULL", "REFERENCES", "DEFAULT", "CHECK", "UNIQUE"}


@dataclass
class Column:
    name: str
    type: str
    pk: bool = False
    fk: tuple | None = None          # (table, column) it references


@dataclass
class Table:
    name: str
    columns: list = field(default_factory=list)

    def col(self, name):
        return next(c for c in self.columns if c.name == name)


def parse_ddl(sql_text: str) -> dict:
    """Read CREATE TABLE statements into Table objects (enough for these four DDL files)."""
    text = re.sub(r"--[^\n]*", "", sql_text)                       # drop comments
    tables = {}
    pattern = r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?([\w.]+)\s*\((.*?)\)\s*(?:COMMENT[^;]*)?;"
    for m in re.finditer(pattern, text, re.S | re.I):
        t = Table(m.group(1))
        body = m.group(2)
        # Split the body on commas that are not inside parentheses.
        parts, depth, cur = [], 0, ""
        for ch in body:
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        for raw in (p.strip() for p in parts if p.strip()):
            pk_m = re.match(r"PRIMARY KEY\s*\(([^)]*)\)", raw, re.I)
            if pk_m:                                                   # table-level composite key
                for name in pk_m.group(1).split(","):
                    t.col(name.strip()).pk = True
                continue
            if re.match(r"(UNIQUE|CONSTRAINT|CHECK|FOREIGN KEY)\b", raw, re.I):
                continue                                               # table-level constraint, not a column
            tokens = raw.split()
            name, type_words = tokens[0], []
            for tok in tokens[1:]:
                if tok.upper() in TYPE_STOP:
                    break
                type_words.append(tok)
            col = Column(name, " ".join(type_words))
            col.pk = bool(re.search(r"PRIMARY KEY", raw, re.I))
            ref = re.search(r"REFERENCES\s+([\w.]+)\s*(?:\((\w+)\))?", raw, re.I)
            if ref:
                col.fk = (ref.group(1), ref.group(2))                  # column None = parent's PK
            t.columns.append(col)
        tables[t.name] = t
    for t in tables.values():                                          # fill implied PK column names
        for c in t.columns:
            if c.fk and c.fk[1] is None and c.fk[0] in tables:
                pk = [p.name for p in tables[c.fk[0]].columns if p.pk]
                c.fk = (c.fk[0], pk[0] if pk else None)
    return tables


def implied_links(tables: dict) -> list:
    """Links a person would guess from matching names when nothing is declared:
    a column named like another table's single-column primary key."""
    pks = {t.name: [c.name for c in t.columns if c.pk] for t in tables.values()}
    links = []
    for t in tables.values():
        for c in t.columns:
            if c.fk or c.pk:
                continue
            for parent, cols in pks.items():
                if parent != t.name and cols == [c.name]:
                    links.append((t.name, c.name, parent, c.name))
    return links


def relationships(tables: dict) -> list:
    """(child, child column, parent, parent column, declared?) for every link to draw."""
    rels = [(t.name, c.name, c.fk[0], c.fk[1], True) for t in tables.values() for c in t.columns if c.fk]
    if not rels:
        rels = [(*link, False) for link in implied_links(tables)]
    return rels


def to_dot(tables: dict, title: str) -> str:
    lines = ["digraph ERD {", "  graph [rankdir=LR, fontname=Helvetica, labelloc=t, fontsize=16,",
             f'         label="{title}\\nSynthetic data (seed 472)"];', "  node [shape=plain, fontname=Helvetica];",
             "  edge [fontname=Helvetica, fontsize=10];"]
    for t in tables.values():
        rows = "".join(
            f'<tr><td align="left" port="{c.name}">{"PK " if c.pk else ""}{"FK " if c.fk else ""}'
            f'<b>{c.name}</b></td><td align="left">{c.type}</td></tr>' for c in t.columns)
        lines.append(f'  {t.name} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="3">'
                     f'<tr><td colspan="2" bgcolor="#dbe7f3"><b>{t.name}</b></td></tr>{rows}</table>>];')
    for child, ccol, parent, pcol, declared in relationships(tables):
        style = 'label="N : 1"' if declared else 'style=dashed, color=gray40, label="not declared\\n(name match)"'
        lines.append(f"  {child}:{ccol} -> {parent}:{pcol} [{style}];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def draw_matplotlib(tables: dict, title: str, path: Path, positions: dict | None = None) -> None:
    """Fallback renderer: tables as boxes (parents on the left), arrows child -> parent.

    positions (optional): {table: (column, order)} to place tables by hand, e.g. for star schemas.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, Rectangle

    rels = relationships(tables)
    # Column (level) of each table: 0 for tables with no parent, else 1 + level of its parent.
    level = {name: 0 for name in tables}
    for _ in range(len(tables)):
        for child, _, parent, _, _ in rels:
            level[child] = max(level[child], level[parent] + 1)
    row_h, box_w, gap_x, gap_y = 0.32, 3.4, 1.6, 0.6
    pos, y_next = {}, {}
    order = {n: n for n in tables}
    if positions:
        level = {n: positions[n][0] for n in tables}
        order = {n: positions[n][1] for n in tables}
    for name in sorted(tables, key=lambda n: (level[n], order[n])):
        x = level[name] * (box_w + gap_x)
        h = (len(tables[name].columns) + 1) * row_h
        y_top = y_next.get(level[name], 0.0)
        pos[name] = (x, y_top, h)
        y_next[level[name]] = y_top - h - gap_y
    width = (max(level.values()) + 1) * (box_w + gap_x)
    height = -min(y - h for (_, y, h) in pos.values()) + 1.2
    fig, ax = plt.subplots(figsize=(max(7, width * 1.05), max(4, height * 1.05)))
    ax.set_xlim(-0.3, width - gap_x + 0.3)
    ax.set_ylim(-height + 0.6, 1.0)
    ax.axis("off")
    ax.set_title(f"{title}\nSynthetic data (seed 472)", fontsize=13)

    def row_y(table, col):
        x, y, h = pos[table]
        i = [c.name for c in tables[table].columns].index(col)
        return y - (i + 1.5) * row_h

    for name, (x, y, h) in pos.items():
        ax.add_patch(Rectangle((x, y - h), box_w, h, fill=False, lw=1.2))
        ax.add_patch(Rectangle((x, y - row_h), box_w, row_h, color="#dbe7f3"))
        ax.text(x + 0.1, y - row_h / 2, name, va="center", fontsize=10, fontweight="bold")
        for c in tables[name].columns:
            mark = ("PK " if c.pk else "") + ("FK " if c.fk else "")
            ax.text(x + 0.1, row_y(name, c.name), f"{mark}{c.name}", va="center", fontsize=8,
                    fontweight="bold" if c.pk else "normal")
            ax.text(x + box_w - 0.1, row_y(name, c.name), c.type, va="center", ha="right", fontsize=7,
                    color="gray")
    for child, ccol, parent, pcol, declared in rels:
        cx, _, _ = pos[child]
        px, _, _ = pos[parent]
        start = (cx, row_y(child, ccol)) if cx > px else (cx + box_w, row_y(child, ccol))
        end = (px + box_w, row_y(parent, pcol)) if cx > px else (px, row_y(parent, pcol))
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=12,
                                     connectionstyle="arc3,rad=0.15", lw=1.1,
                                     color="black" if declared else "gray", linestyle="-" if declared else "--"))
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.12)
        ax.text(*mid, "N : 1" if declared else "not declared (name match)", fontsize=7, ha="center",
                color="black" if declared else "gray")
    note = ("Arrows point from child to parent (many-to-one). PK = primary key, FK = declared foreign key."
            if any(r[4] for r in rels) else
            "No foreign keys are declared in this legacy database. Dashed links are only implied by matching "
            "column names.")
    fig.text(0.01, 0.01, note, fontsize=8)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def build_erds() -> list:
    out_dir = evidence_dir("01_sources") / "erd"
    out_dir.mkdir(parents=True, exist_ok=True)
    dot_exe = shutil.which("dot")
    results = []
    for dept, (ddl_file, engine) in DEPARTMENTS.items():
        tables = parse_ddl((SQL_DIR / "01_source_ddl" / ddl_file).read_text(encoding="utf-8"))
        title = f"{dept.capitalize()} department ({engine})"
        dot_path = out_dir / f"{dept}_erd.dot"
        png_path = out_dir / f"{dept}_erd.png"
        dot_path.write_text(to_dot(tables, title), encoding="utf-8", newline="\n")
        if dot_exe:
            subprocess.run([dot_exe, "-Tpng", str(dot_path), "-o", str(png_path)], check=True)
            renderer = "graphviz"
        else:
            draw_matplotlib(tables, title, png_path)
            renderer = "matplotlib (graphviz not installed)"
        rels = relationships(tables)
        results.append({"department": dept, "engine": engine, "tables": len(tables),
                        "columns": sum(len(t.columns) for t in tables.values()),
                        "declared_relationships": sum(r[4] for r in rels),
                        "implied_relationships": sum(not r[4] for r in rels),
                        "png": png_path.relative_to(evidence_dir("01_sources")).as_posix(), "renderer": renderer})
    return results


def build_star_diagram() -> Path:
    """Both stars from sql/02_warehouse_ddl/02_dw_stars.sql (dimensions left, facts right)."""
    tables = parse_ddl((SQL_DIR / "02_warehouse_ddl" / "02_dw_stars.sql").read_text(encoding="utf-8"))
    tables = {k.replace("dw.", ""): t for k, t in tables.items()}
    for t in tables.values():
        t.name = t.name.replace("dw.", "")
        for c in t.columns:
            if c.fk:
                c.fk = (c.fk[0].replace("dw.", ""), c.fk[1])
    for t in tables.values():                                          # implied PK column names
        for c in t.columns:
            if c.fk and c.fk[1] is None:
                c.fk = (c.fk[0], next(p.name for p in tables[c.fk[0]].columns if p.pk))
    out = evidence_dir("03_warehouse")
    title = "Nuskha warehouse: sales and purchase stars (conformed date, product, branch)"
    (out / "star_schema.dot").write_text(to_dot(tables, title), encoding="utf-8", newline="\n")
    layout = {"dim_customer": (0, 0), "fact_sales": (1, 0), "dim_date": (2, 0), "dim_product": (2, 1),
              "dim_branch": (2, 2), "fact_purchase": (3, 0), "dim_supplier": (4, 0)}
    draw_matplotlib(tables, title, out / "star_schema.png", layout)
    return out / "star_schema.png"


if __name__ == "__main__":
    import pandas as pd

    from src.common import write_evidence

    res = pd.DataFrame(build_erds())
    write_evidence("01_sources", "erd_summary.csv", res)
    print(res.to_string(index=False))
    print(f"star diagram: {build_star_diagram()}")
