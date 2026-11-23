"""Generate the Power BI project (PBIP) semantic model in TMDL (unit 4.09). Synthetic data.

Writes powerbi/nuskha.pbip and powerbi/nuskha.SemanticModel/ from the exported CSV headers in
powerbi/data/, so the model's columns always match the files. Every table is imported from its
CSV through the DataFolder parameter (set it to the full path of powerbi/data on the Power BI PC).

Model: Sales and Purchases facts share Date, Product and Branch dimension tables, so the date,
region and category slicers filter both. Measures (ratios always through DIVIDE, recomputed from sums):
  Net Sales, Gross Margin, Margin %, Units Sold, ASP, Purchases, Purchase Unit Cost,
  Net Sales LY, Net Sales 3M Avg, Last Batch.

  python -m src.powerbi_model           # write the files, then run the checks
"""
from __future__ import annotations

import json
import re
import uuid

import pandas as pd

from src.common import ROOT

PBI = ROOT / "powerbi"
DATA = PBI / "data"
SM = PBI / "nuskha.SemanticModel"
TABLES = {  # model table name: (csv file, columns to keep or None for all)
    "Sales": ("vw_sales_enriched", None),
    "Purchases": ("vw_purchase_enriched", None),
    "Date": ("dim_date", None),
    "Product": ("dim_product", None),
    "Branch": ("dim_branch", None),
    "Margin Bridge": ("vw_margin_bridge", None),
    "Region Category Month": ("vw_region_category_month", None),
    "Forecast": ("ai_forecast_result", None),
    "Anomaly": ("ai_anomaly_result", None),
    "Last Batch": ("etl_last_batch", None),
}
RELATIONSHIPS = [  # (from table, from column, to table, to column)
    ("Sales", "full_date", "Date", "full_date"), ("Purchases", "full_date", "Date", "full_date"),
    ("Sales", "product_code", "Product", "product_code"), ("Purchases", "product_code", "Product", "product_code"),
    ("Sales", "branch_name", "Branch", "branch_name"), ("Purchases", "branch_name", "Branch", "branch_name"),
]
MEASURES = {  # table: [(name, DAX, format)]
    "Sales": [
        ("Net Sales", "SUM(Sales[net_amount_pkr])", "#,0"),
        ("Gross Margin", "SUM(Sales[gross_margin_pkr])", "#,0"),
        ("Margin %", "DIVIDE([Gross Margin], [Net Sales])", "0.0%"),
        ("Units Sold", "SUM(Sales[quantity_units])", "#,0"),
        ("ASP", "DIVIDE([Net Sales], [Units Sold])", "#,0.00"),
        ("Net Sales LY", "CALCULATE([Net Sales], SAMEPERIODLASTYEAR('Date'[full_date]))", "#,0"),
        # 3-month average over the months that have sales: the first months average over 1-2 months
        # instead of dividing by 3, and months with no sales (after Oct 2026) stay blank.
        ("Net Sales 3M Avg", "VAR w = DATESINPERIOD('Date'[full_date], MAX('Date'[full_date]), -3, MONTH) "
                             "VAR months = CALCULATE(COUNTROWS(FILTER(VALUES('Date'[month_start]), "
                             "NOT ISBLANK([Net Sales]))), w) "
                             "RETURN IF(NOT ISBLANK([Net Sales]), DIVIDE(CALCULATE([Net Sales], w), months))", "#,0"),
        ("Last Batch", "MAX('Last Batch'[last_batch_id])", "0"),
    ],
    "Purchases": [
        ("Purchases", "SUM(Purchases[purchase_amount_pkr])", "#,0"),
        ("Units Purchased", "SUM(Purchases[quantity_units])", "#,0"),
        ("Purchase Unit Cost", "DIVIDE([Purchases], [Units Purchased])", "#,0.00"),
    ],
}


def q(name: str) -> str:
    """TMDL object name: quoted when it has spaces or symbols."""
    if name in {"Date"} or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):   # Date is also a DAX function
        return "'" + name.replace("'", "''") + "'"
    return name


def col_type(series: pd.Series, name: str) -> tuple[str, str]:
    """(TMDL dataType, Power Query type) from the exported CSV column."""
    if name in ("full_date", "month_start", "prev_month") or name.endswith("_date"):
        return "dateTime", "type date"
    if pd.api.types.is_bool_dtype(series) or set(series.dropna().astype(str).str.lower().unique()) <= {"true", "false"}:
        if series.notna().any():
            return "boolean", "type logical"
    if pd.api.types.is_integer_dtype(series):
        return "int64", "Int64.Type"
    if pd.api.types.is_float_dtype(series):
        return "double", "type number"
    return "string", "type text"


def table_tmdl(name: str, csv_name: str) -> str:
    df = pd.read_csv(DATA / f"{csv_name}.csv", nrows=2000)
    lines = [f"table {q(name)}", f"\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, 'nuskha/' + name)}", ""]
    for m_name, dax, fmt in MEASURES.get(name, []):
        lines += [f"\tmeasure {q(m_name)} = {dax}", f"\t\tformatString: {fmt}",
                  f"\t\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, 'nuskha/m/' + m_name)}", ""]
    types = []
    for c in df.columns:
        dt, pq = col_type(df[c], c)
        types.append(f'{{"{c}", {pq}}}')
        summarize = "sum" if dt in ("double", "int64") and not c.endswith(("_key", "_id", "line_no", "year",
                                                                           "quarter", "rank")) else "none"
        lines += [f"\tcolumn {q(c)}", f"\t\tdataType: {dt}", f"\t\tsummarizeBy: {summarize}",
                  f"\t\tsourceColumn: {c}", *(["\t\tisKey"] if name == "Date" and c == "full_date" else []),
                  f"\t\tlineageTag: {uuid.uuid5(uuid.NAMESPACE_URL, f'nuskha/{name}/{c}')}", ""]
    m = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "\\{csv_name}.csv"), '
        '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{", ".join(types)}}}, "en-US")',
        "in",
        "    Typed",
    ]
    lines += [f"\tpartition {q(name)} = m", "\t\tmode: import", "\t\tsource =", *[f"\t\t\t\t{x}" for x in m], ""]
    if name == "Date":
        lines.insert(2, "\tdataCategory: Time")
    return "\n".join(lines) + "\n"


def write_model() -> list:
    defn = SM / "definition"
    (defn / "tables").mkdir(parents=True, exist_ok=True)
    (PBI / "nuskha.pbip").write_text(json.dumps({
        "version": "1.0", "artifacts": [{"report": {"path": "nuskha.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2) + "\n", encoding="utf-8", newline="\n")
    (SM / "definition.pbism").write_text(json.dumps({"version": "4.0", "settings": {}}, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
    (defn / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n", encoding="utf-8", newline="\n")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
             "", *[f"ref table {q(t)}" for t in TABLES], ""]
    (defn / "model.tmdl").write_text("\n".join(model), encoding="utf-8", newline="\n")
    # DataFolder defaults to this checkout's powerbi/data (absolute Windows path), so the .pbip opens
    # with data on the machine that generated it; elsewhere, edit the parameter in Power BI.
    data_folder = str((PBI / "data").resolve()).replace("/", "\\").replace('"', '""')
    (defn / "expressions.tmdl").write_text(
        f'expression DataFolder = "{data_folder}" meta [IsParameterQuery = true, Type = "Text", '
        'IsParameterQueryRequired = true]\n\tlineageTag: ' + str(uuid.uuid5(uuid.NAMESPACE_URL, "nuskha/DataFolder"))
        + "\n\n\tannotation PBI_ResultType = Text\n", encoding="utf-8", newline="\n")
    rels = []
    for f_t, f_c, t_t, t_c in RELATIONSHIPS:
        rid = uuid.uuid5(uuid.NAMESPACE_URL, f"nuskha/rel/{f_t}/{f_c}/{t_t}")
        rels += [f"relationship {rid}", f"\tfromColumn: {q(f_t)}.{q(f_c)}", f"\ttoColumn: {q(t_t)}.{q(t_c)}", ""]
    (defn / "relationships.tmdl").write_text("\n".join(rels), encoding="utf-8", newline="\n")
    written = []
    for name, (csv_name, _) in TABLES.items():
        path = defn / "tables" / f"{name}.tmdl"
        path.write_text(table_tmdl(name, csv_name), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def checks() -> pd.DataFrame:
    """Text-level checks: indentation uses tabs, every ratio measure uses DIVIDE, columns exist."""
    rows = []
    files = list((SM / "definition").rglob("*.tmdl"))
    bad_indent = [f.name for f in files for ln in f.read_text(encoding="utf-8").splitlines() if ln.startswith(" ")]
    rows.append(("TMDL files indent with tabs only", 0, len(bad_indent), not bad_indent))
    ratio = [m for ms in MEASURES.values() for m in ms if m[0] in ("Margin %", "ASP", "Purchase Unit Cost",
                                                                  "Net Sales 3M Avg")]
    no_div = [m[0] for m in ratio if "DIVIDE(" not in m[1] or "/" in m[1]]
    rows.append(("ratio measures use DIVIDE (no '/')", 0, len(no_div), not no_div))
    missing = []
    for f_t, f_c, t_t, t_c in RELATIONSHIPS:
        for t, c in ((f_t, f_c), (t_t, t_c)):
            if c not in pd.read_csv(DATA / f"{TABLES[t][0]}.csv", nrows=1).columns:
                missing.append(f"{t}.{c}")
    rows.append(("relationship columns exist in the CSVs", 0, len(missing), not missing))
    for m_t, ms in MEASURES.items():
        for name, dax, _ in ms:
            for t, c in re.findall(r"'?([A-Za-z ]+)'?\[([a-z_]+)\]", dax):
                if c not in pd.read_csv(DATA / f"{TABLES[t.strip()][0]}.csv", nrows=1).columns:
                    missing.append(f"{name}: {t}[{c}]")
    rows.append(("measure columns exist in the CSVs", 0, len(missing), not missing))
    rows.append(("tables written", len(TABLES), len(list((SM / "definition" / "tables").glob("*.tmdl"))),
                 len(list((SM / "definition" / "tables").glob("*.tmdl"))) == len(TABLES)))
    out = pd.DataFrame(rows, columns=["check", "expected", "actual", "ok"])
    out["result"] = out.pop("ok").map({True: "PASS", False: "FAIL"})
    return out


if __name__ == "__main__":
    write_model()
    res = checks()
    res.to_csv(PBI / "model_checks.csv", index=False, lineterminator="\n")
    print(res.to_string(index=False))
