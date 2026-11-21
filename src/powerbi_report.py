"""Write the Power BI report definition (PBIR) for powerbi/nuskha.pbip (unit 4.10). Synthetic data.

Three pages and 11 visuals as in docs/blueprint.md ("Power BI report"), plus slicers, a
last-batch card and a footer text on every page:

  Management Overview  1 KPI cards (Net Sales, Margin %, Purchases)   2 monthly net sales + 3-month average
                       3 branch net sales vs last year                4 category share of gross margin per year
  Diagnostic Analysis  5 margin % trend by category                   6 ASP vs purchase unit cost, Diabetes Care
                       7 margin bridge (volume, price, cost effects)  8 top products this year vs last year
  AI Insights          9 forecast vs holdout actuals + next 3 months  10 anomaly scatter (value vs expected)
                       11 flagged region-category-months table

The files follow Microsoft's published JSON schemas (developer.microsoft.com/json-schemas/fabric/
item/report/...). `--validate` downloads those schemas into data/pbir_schemas/ (git-ignored) and
validates every file against them.

  python -m src.powerbi_report              # write powerbi/nuskha.Report/
  python -m src.powerbi_report --validate   # write, then validate against the published schemas
"""
from __future__ import annotations

import json
import shutil
import sys

import pandas as pd

from src.common import ROOT, write_evidence

REPORT = ROOT / "powerbi" / "nuskha.Report"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/"
V_CONTAINER = SCHEMA + "definition/visualContainer/2.4.0/schema.json"
V_PAGE = SCHEMA + "definition/page/2.0.0/schema.json"
FOOTER = ("Synthetic data (seed 472) · Amounts in PKR · Period Nov 2023 – Oct 2026 · Net Sales = sum of net "
          "line amounts (cancelled lines excluded) · Margin % = Gross Margin / Net Sales · ASP = Net Sales / units · "
          "Purchases = GRN amounts converted to PKR at the rate on the receipt date")


# ---------------------------------------------------------------------------
# Field helpers (semantic query expressions)
# ---------------------------------------------------------------------------
def measure(table: str, name: str) -> dict:
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
            "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def column(table: str, name: str) -> dict:
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
            "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def total(table: str, name: str) -> dict:
    """Sum of a column (Function 0 = Sum)."""
    return {"field": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Entity": table}},
                                                                 "Property": name}}, "Function": 0}},
            "queryRef": f"Sum({table}.{name})", "nativeQueryRef": f"Sum of {name}"}


def literal(v: str) -> dict:
    return {"expr": {"Literal": {"Value": v}}}


def title(text: str) -> dict:
    return {"title": [{"properties": {"show": literal("true"), "text": literal(f"'{text}'")}}]}


def category_filter(name: str, table: str, col: str, values: list[str]) -> dict:
    """Visual-level basic filter: table[col] IN values (values written as DAX literals, e.g. "'Diabetes Care'")."""
    return {"filters": [{
        "name": name,
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "type": "Categorical",
        "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                   "Where": [{"Condition": {"In": {
                       "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": col}}],
                       "Values": [[{"Literal": {"Value": v}}] for v in values]}}}]}}]}


def visual(name: str, vtype: str, x, y, w, h, roles: dict | None = None, heading: str | None = None,
           filters: dict | None = None, objects: dict | None = None, sort: dict | None = None) -> dict:
    v = {"visualType": vtype, "drillFilterOtherVisuals": True}
    if roles:
        v["query"] = {"queryState": {role: {"projections": fields} for role, fields in roles.items()}}
        if sort:
            v["query"]["sortDefinition"] = sort
    if objects:
        v["objects"] = objects
    if heading:
        v["visualContainerObjects"] = title(heading)
    out = {"$schema": V_CONTAINER, "name": name,
           "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}, "visual": v}
    if filters:
        out["filterConfig"] = filters
    return out


def textbox(name: str, text: str, x, y, w, h, size: str = "9pt") -> dict:
    return {"$schema": V_CONTAINER, "name": name,
            "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": [
                {"textRuns": [{"value": text, "textStyle": {"fontSize": size}}]}]}}]}}}


def slicer(name: str, table: str, col: str, x, y, w=200, h=60) -> dict:
    """Dates use a 'Between' range slicer (needed for the reconciliation totals); text uses a dropdown."""
    mode = "'Between'" if col in ("month_start", "full_date") else "'Dropdown'"
    return visual(name, "slicer", x, y, w, h, {"Values": [column(table, col)]}, heading=None,
                  objects={"data": [{"properties": {"mode": literal(mode)}}]})


def page_frame(prefix: str, slicers: list[tuple[str, str]]) -> list[dict]:
    """Slicers along the top, last-batch card and footer text at the bottom (every page)."""
    out = [slicer(f"{prefix}_slicer_{i}", t, c, 20 + 215 * i, 10) for i, (t, c) in enumerate(slicers)]
    out.append(visual(f"{prefix}_last_batch", "card", 1100, 10, 160, 60, {"Values": [measure("Sales", "Last Batch")]},
                      heading="Last batch id"))
    out.append(textbox(f"{prefix}_footer", FOOTER, 20, 680, 1240, 34, "8pt"))
    return out


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
SLICERS = [("Date", "month_start"), ("Branch", "region"), ("Product", "category")]


def pages() -> dict:
    overview = page_frame("ov", SLICERS) + [
        visual("ov_kpis", "multiRowCard", 20, 85, 1240, 90,
               {"Values": [measure("Sales", "Net Sales"), measure("Sales", "Margin %"),
                           measure("Purchases", "Purchases")]}, "KPIs: Net Sales, Margin %, Purchases (PKR)"),
        visual("ov_monthly", "lineChart", 20, 185, 620, 240,
               {"Category": [column("Date", "month_start")],
                "Y": [measure("Sales", "Net Sales"), measure("Sales", "Net Sales 3M Avg")]},
               "Monthly net sales with 3-month rolling average (PKR)"),
        visual("ov_branch", "clusteredBarChart", 650, 185, 610, 240,
               {"Category": [column("Branch", "branch_name")],
                "Y": [measure("Sales", "Net Sales"), measure("Sales", "Net Sales LY")]},
               "Branch net sales vs same period last year (PKR)"),
        visual("ov_category", "hundredPercentStackedBarChart", 20, 435, 1240, 235,
               {"Category": [column("Date", "fiscal_year")], "Y": [measure("Sales", "Gross Margin")],
                "Series": [column("Product", "category")]},
               "Category contribution to gross margin by fiscal year (share of PKR)"),
    ]
    diagnostic = page_frame("dg", SLICERS) + [
        visual("dg_margin_trend", "lineChart", 20, 85, 620, 290,
               {"Category": [column("Date", "month_start")], "Y": [measure("Sales", "Margin %")],
                "Series": [column("Product", "category")]}, "Margin % by category over time"),
        visual("dg_asp_cost", "lineChart", 650, 85, 610, 290,
               {"Category": [column("Date", "month_start")],
                "Y": [measure("Sales", "ASP"), measure("Purchases", "Purchase Unit Cost")]},
               "Diabetes Care: ASP vs purchase unit cost (PKR per unit)",
               filters=category_filter("dg_asp_cost_dc", "Product", "category", ["'Diabetes Care'"])),
        visual("dg_bridge", "clusteredColumnChart", 20, 385, 620, 285,
               {"Category": [column("Margin Bridge", "month_start")],
                "Y": [total("Margin Bridge", "volume_effect_pkr"), total("Margin Bridge", "price_effect_pkr"),
                      total("Margin Bridge", "cost_effect_pkr")]},
               "Diabetes Care margin bridge: volume, price and cost effects (PKR)",
               filters=category_filter("dg_bridge_dc", "Margin Bridge", "category", ["'Diabetes Care'"])),
        visual("dg_top", "tableEx", 650, 385, 610, 285,
               {"Values": [column("Product", "generic_name"), column("Product", "strength"),
                           measure("Sales", "Net Sales"), measure("Sales", "Net Sales LY")]},
               "Top products: net sales this period vs last year (sorted by net sales)",
               sort={"sort": [{"field": measure("Sales", "Net Sales")["field"], "direction": "Descending"}],
                     "isDefaultSort": True}),
    ]
    ai = page_frame("ai", [("Anomaly", "region"), ("Anomaly", "category")]) + [
        visual("ai_forecast", "lineChart", 20, 85, 1240, 250,
               {"Category": [column("Forecast", "month_start")],
                "Y": [total("Forecast", "actual"), total("Forecast", "prediction"), total("Forecast", "lower"),
                      total("Forecast", "upper")]},
               "Forecast vs holdout actuals (Aug-Oct 2026) and next 3 months (Nov 2026-Jan 2027), PKR"),
        visual("ai_scatter", "scatterChart", 20, 345, 620, 325,
               {"Category": [column("Anomaly", "region"), column("Anomaly", "category"), column("Anomaly", "month_start")],
                "Series": [column("Anomaly", "is_flag")],
                "X": [total("Anomaly", "expected")], "Y": [total("Anomaly", "value")]},
               "Region x category x month: net sales vs expected (flags highlighted)",
               filters=category_filter("ai_scatter_real", "Anomaly", "is_injected_copy", ["false"])),
        visual("ai_flags", "tableEx", 650, 345, 610, 325,
               {"Values": [column("Anomaly", "region"), column("Anomaly", "category"), column("Anomaly", "month_start"),
                           column("Anomaly", "method"), total("Anomaly", "value"), total("Anomaly", "expected"),
                           total("Anomaly", "score")]},
               "Flagged cases (receipt-line traces: evidence/07_ai/anomaly_case_traces.csv)",
               filters={"filters": category_filter("ai_flags_flag", "Anomaly", "is_flag", ["true"])["filters"]
                        + category_filter("ai_flags_real", "Anomaly", "is_injected_copy", ["false"])["filters"]}),
    ]
    return {"overview": ("Management Overview", overview), "diagnostic": ("Diagnostic Analysis", diagnostic),
            "ai": ("AI Insights", ai)}


def files() -> dict:
    """Relative path -> JSON content for the whole report folder."""
    out = {
        "definition.pbir": {"$schema": SCHEMA + "definitionProperties/2.0.0/schema.json", "version": "4.0",
                            "datasetReference": {"byPath": {"path": "../nuskha.SemanticModel"}}},
        "definition/version.json": {"$schema": SCHEMA + "definition/versionMetadata/1.0.0/schema.json",
                                    "version": "2.0.0"},
        "definition/report.json": {"$schema": SCHEMA + "definition/report/3.0.0/schema.json", "themeCollection": {},
                                   "settings": {"useStylableVisualContainerHeader": True}},
    }
    pg = pages()
    out["definition/pages/pages.json"] = {"$schema": SCHEMA + "definition/pagesMetadata/1.0.0/schema.json",
                                          "pageOrder": list(pg), "activePageName": "overview"}
    for key, (display, visuals) in pg.items():
        out[f"definition/pages/{key}/page.json"] = {"$schema": V_PAGE, "name": key, "displayName": display,
                                                    "displayOption": "FitToPage", "height": 720, "width": 1280}
        for i, v in enumerate(visuals):
            v["position"]["tabOrder"] = i
            out[f"definition/pages/{key}/visuals/{v['name']}/visual.json"] = v
    return out


def write() -> dict:
    if REPORT.exists():
        shutil.rmtree(REPORT)
    content = files()
    for rel, data in content.items():
        p = REPORT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return content


# ---------------------------------------------------------------------------
# Validation against Microsoft's published schemas
# ---------------------------------------------------------------------------
RAW = "https://raw.githubusercontent.com/microsoft/json-schemas/main/"
CACHE = ROOT / "data" / "pbir_schemas"


def _fetch(uri: str) -> dict:
    """Schema by its developer.microsoft.com URI, cached; the same files are published on GitHub."""
    import urllib.request

    rel = uri.split("json-schemas/", 1)[1]
    path = CACHE / rel
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(RAW + rel, timeout=60) as r:      # noqa: S310 (fixed https host)
            path.write_bytes(r.read())
    return json.loads(path.read_text(encoding="utf-8"))


def validate(content: dict) -> pd.DataFrame:
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7

    def retrieve(uri: str):
        return Resource.from_contents(_fetch(uri), default_specification=DRAFT7)

    registry = Registry(retrieve=retrieve)
    rows = []
    for rel, data in content.items():
        schema = _fetch(data["$schema"])
        cls = Draft7Validator
        errors = sorted(cls(schema, registry=registry).iter_errors(data), key=lambda e: list(e.path))
        rows.append({"file": rel, "schema": data["$schema"].split("item/report/")[1], "errors": len(errors),
                     "first_error": (f"{'/'.join(map(str, errors[0].path))}: {errors[0].message[:160]}"
                                     if errors else ""), "result": "PASS" if not errors else "FAIL"})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    content = write()
    n_vis = sum(1 for k in content if k.endswith("visual.json"))
    print(f"report written to {REPORT} ({len(content)} files, {n_vis} visual containers)")
    if "--validate" in sys.argv:
        res = validate(content)
        write_evidence("08_powerbi", "report_schema_validation.csv", res)
        pd.set_option("display.width", 250)
        print(res[res.result == "FAIL"].to_string(index=False, max_colwidth=160) if (res.result == "FAIL").any()
              else res.to_string(index=False, max_colwidth=70))
        print(f"\n{(res.result == 'PASS').sum()} PASS, {(res.result == 'FAIL').sum()} FAIL")
        if (res.result == "FAIL").any():
            raise SystemExit(1)
