"""Run the 12 analytic queries A1-A12 (units 4.02 and 4.03). Synthetic data.

For each sql/04_queries/Axx_*.sql this writes to the output folder:
  Axx_<name>.csv   the result table
  Axx_<name>.png   its chart
and one readings.md with, per query: lab practical, analysis type, output grain, SQL feature,
row count and a two-line interpretation computed from the result itself (so the text always
matches the numbers it describes). No chart claims a cause from correlation.

  python -m src.queries                      # against PostgreSQL (DW_URL) -> evidence/06_sql/
  python -m src.queries --duckdb             # against the pre-database DuckDB copy
                                             #   -> evidence/06_sql/preview_duckdb/
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src import charts as ch
from src.common import DATA_DIR, SQL_DIR, evidence_dir

QDIR = SQL_DIR / "04_queries"
META = {  # id: (lab practical, analysis, output grain, main SQL feature)
    "A01": ("P9", "Comparison", "Branch x quarter", "GROUP BY, CASE, FILTER"),
    "A02": ("P9", "Contribution", "Category x fiscal year", "SUM() OVER ()"),
    "A03": ("P9", "Trend", "Category x month", "GROUP BY date hierarchy"),
    "A04": ("P9", "ASP", "Category x month", "SUM(net) / SUM(qty)"),
    "A05": ("P9", "Comparison", "Origin x quarter", "GROUP BY ROLLUP"),
    "A06": ("P9", "Contribution", "Month", "SUM() OVER (ORDER BY)"),
    "A07": ("P10", "Rolling average", "Month", "AVG() OVER (ROWS 2 PRECEDING)"),
    "A08": ("P10", "Growth", "Month", "LAG(1), LAG(12)"),
    "A09": ("P10", "Ranking change", "Product x fiscal year", "RANK(), LAG()"),
    "A10": ("P10", "Relationship", "Product x month", "two summed CTEs, then join"),
    "A11": ("P10", "Volatility", "Category", "STDDEV over a monthly CTE"),
    "A12": ("P10", "Diagnostic", "Product x month (category total)", "CTEs + window functions"),
}


def pkr(v) -> str:
    return f"PKR {float(v):,.0f}"


def month(v) -> str:
    return pd.Timestamp(v).strftime("%b %Y")


# ---------------------------------------------------------------------------
# One function per query: draws the chart and returns the two-line reading.
# ---------------------------------------------------------------------------
def a01(df, png):
    d = df.sort_values("net_this_q")
    fig, ax = ch.figure(10, 5.5)
    y = np.arange(len(d))
    ax.barh(y - 0.2, d.net_same_q_last_year, 0.38, color=ch.SLOTS[0], label="Jul-Sep 2025 (FY2026 Q1)")
    ax.barh(y + 0.2, d.net_this_q, 0.38, color=ch.SLOTS[1], label="Jul-Sep 2026 (FY2027 Q1)")
    ax.set_yticks(y, d.branch_name)
    ax.grid(axis="x", color=ch.GRID)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v / 1e3:.0f}k")
    ch.finish(fig, ax, "A1  Net sales by branch: this quarter vs the same quarter last year", png,
              note="PKR, cancelled lines excluded.")
    grew = df[df.margin_vs_ly == "margin grew"]
    best, worst = df.iloc[0], df.iloc[-1]
    return (f"{len(grew)} of {len(df)} branches grew gross margin vs the same quarter last year; "
            f"{best.branch_name} grew net sales most ({best.net_growth_vs_ly_pct:+.1f}%), "
            f"{worst.branch_name} least ({worst.net_growth_vs_ly_pct:+.1f}%).\n"
            f"Branches that fell are the first to review for stock and pharmacist moves (BQ1); the table "
            f"shows the previous quarter too, so a one-off dip can be told apart from a trend.")


def a02(df, png):
    piv = df.pivot(index="fiscal_year", columns="category", values="share_of_margin_pct").fillna(0)
    fig, ax = ch.figure(10, 4.8)
    left = np.zeros(len(piv))
    for c in [c for c in ch.CATEGORIES if c in piv.columns]:
        ax.barh(piv.index, piv[c], left=left, color=ch.color_of(c), label=c, edgecolor=ch.SURFACE, linewidth=2)
        left += piv[c].to_numpy()
    ax.set_xlim(0, 100)
    ax.grid(axis="x", color=ch.GRID)
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=7, frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ch.finish(fig, ax, "A2  Share of gross margin by category and fiscal year (%)", png, legend=False,
              note="FY2024 and FY2027 are part years.")
    fy = df[df.fiscal_year == "FY2026"].sort_values("share_of_margin_pct", ascending=False)
    fy25 = df[df.fiscal_year == "FY2025"].set_index("category").share_of_margin_pct
    d = fy.set_index("category").share_of_margin_pct
    dia = d.get("Diabetes Care", np.nan)
    return (f"In FY2026 {fy.iloc[0].category} gave the largest share of gross margin ({fy.iloc[0].share_of_margin_pct:.1f}%), "
            f"and the top three categories together gave {fy.head(3).share_of_margin_pct.sum():.1f}%.\n"
            f"Diabetes Care's share went from {fy25.get('Diabetes Care', np.nan):.1f}% (FY2025) to {dia:.1f}% (FY2026); "
            f"FY2026 holds only four months after the March 2026 cost rise, which A12 examines month by month.")


def a03(df, png):
    fig, ax = ch.figure(11, 5)
    for c in ch.CATEGORIES:
        s = df[df.category == c]
        ax.plot(pd.to_datetime(s.month_start), s.net_sales_pkr, color=ch.color_of(c), linewidth=2, label=c)
    ax.set_ylim(bottom=0)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.legend(fontsize=7, frameon=False, ncol=4)
    ch.finish(fig, ax, "A3  Monthly net sales by category", png, ylabel="PKR", legend=False,
              note="Seasons: flu Dec-Feb, dengue/monsoon Aug-Oct, Vitamins before Ramadan.")
    m = df.assign(mo=pd.to_datetime(df.month_start).dt.month)
    def peak(cat, months):
        s = m[m.category == cat]
        return s[s.mo.isin(months)].net_sales_pkr.mean() / s[~s.mo.isin(months)].net_sales_pkr.mean()
    return (f"Cough and Cold sells {peak('Cough and Cold', [12, 1, 2]):.2f}x its other-month average in Dec-Feb, "
            f"Analgesics {peak('Analgesics', [8, 9, 10]):.2f}x and Gastro {peak('Gastro', [8, 9, 10]):.2f}x in Aug-Oct.\n"
            f"Seasonal stock plans (BQ2) should follow these peaks; Vitamins also rise in the month before Ramadan.")


def a04(df, png):
    fig, ax = ch.figure(11, 5)
    for c in ch.CATEGORIES:
        s = df[df.category == c].sort_values("month_start")
        ax.plot(pd.to_datetime(s.month_start), 100 * s.asp_pkr / s.asp_pkr.iloc[:3].mean(),
                color=ch.color_of(c), linewidth=2, label=c)
    ax.axhline(100, color=ch.INK_2, linewidth=0.8)
    ax.legend(fontsize=7, frameon=False, ncol=4)
    ch.finish(fig, ax, "A4  Average selling price per unit, indexed (Nov 2023 - Jan 2024 = 100)", png,
              ylabel="ASP index", legend=False, note="ASP = SUM(net) / SUM(units); indexed so categories share one axis.")
    first = df[pd.to_datetime(df.month_start) < "2024-02-01"].groupby("category")
    last = df[pd.to_datetime(df.month_start) >= "2026-08-01"].groupby("category")
    ch_pct = 100 * ((last.net_sales_pkr.sum() / last.quantity_units.sum())
                    / (first.net_sales_pkr.sum() / first.quantity_units.sum()) - 1)
    return (f"ASP rose most in {ch_pct.idxmax()} ({ch_pct.max():+.1f}% from the first three months to Aug-Oct 2026) "
            f"and least in {ch_pct.idxmin()} ({ch_pct.min():+.1f}%), following the July price rises.\n"
            f"Category ASP also moves with the mix of products sold, so a change is checked at product level "
            f"(A10, A12) before it is called a price change.")


def a05(df, png):
    d = df[df.origin.notna()].copy()
    d["q"] = d.fiscal_year + " Q" + d.fiscal_quarter.astype(int).astype(str)
    piv = d.pivot(index="q", columns="origin", values="purchase_amount_pkr").fillna(0)
    fig, ax = ch.figure(11, 4.8)
    ax.bar(piv.index, piv.get("LOCAL", 0), color=ch.SLOTS[0], label="Local suppliers", edgecolor=ch.SURFACE, linewidth=2)
    ax.bar(piv.index, piv.get("IMPORT", 0), bottom=piv.get("LOCAL", 0), color=ch.SLOTS[1],
           label="Importers (USD, converted)", edgecolor=ch.SURFACE, linewidth=2)
    ch.millions(ax)
    ax.tick_params(axis="x", rotation=45)
    ch.finish(fig, ax, "A5  Purchases in PKR by fiscal quarter: local vs imported", png, ylabel="PKR",
              note="FY2027 Q2 holds October 2026 only.")
    total = df[df.fiscal_year.isna() & df.origin.isna()].purchase_amount_pkr.iloc[0]
    imp = d[d.origin == "IMPORT"].purchase_amount_pkr.sum()
    return (f"Imports were {100 * imp / total:.1f}% of all purchases ({pkr(imp)} of {pkr(total)}); the ROLLUP rows give "
            f"each quarter's subtotal and the grand total.\n"
            f"Imported lines carry exchange-rate risk: their PKR cost moves with USD/PKR even when the USD price is flat.")


def a06(df, png):
    d = df.copy()
    d["fm"] = (pd.to_datetime(d.month_start).dt.month - 7) % 12 + 1
    fig, ax = ch.figure(10, 5)
    for i, (fy, s) in enumerate(d.groupby("fiscal_year")):
        ax.plot(s.fm, s.ytd_net_sales_pkr, linewidth=2, color=ch.SLOTS[i], marker="o", markersize=4, label=fy)
    ax.set_xticks(range(1, 13), ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"])
    ax.set_ylim(bottom=0)
    ch.millions(ax)
    ch.finish(fig, ax, "A6  Fiscal-year-to-date net sales", png, ylabel="PKR",
              note="FY2024 starts in Nov 2023; FY2027 runs to Oct 2026.")
    fy = d.groupby("fiscal_year").ytd_net_sales_pkr.max()
    return (f"FY2025 closed at {pkr(fy.get('FY2025'))} and FY2026 at {pkr(fy.get('FY2026'))} "
            f"({100 * (fy.get('FY2026') / fy.get('FY2025') - 1):+.1f}%).\n"
            f"FY2027 has reached {pkr(fy.get('FY2027'))} after four months; the running total shows "
            f"whether the year is ahead of the last one at the same point.")


def a07(df, png):
    fig, ax = ch.figure(11, 5)
    x = pd.to_datetime(df.month_start)
    ax.plot(x, df.net_sales_pkr, color=ch.SLOTS[0], linewidth=1.2, alpha=0.6, label="Monthly net sales")
    ax.plot(x, df.rolling_3m_avg_pkr, color=ch.SLOTS[1], linewidth=2, label="3-month rolling average")
    ax.set_ylim(bottom=0)
    ch.millions(ax)
    ch.finish(fig, ax, "A7  Company net sales and its 3-month rolling average", png, ylabel="PKR")
    first, last = df.rolling_3m_avg_pkr.iloc[2], df.rolling_3m_avg_pkr.iloc[-1]
    return (f"The 3-month average rose from {pkr(first)} (Jan 2024) to {pkr(last)} (Oct 2026), "
            f"{100 * (last / first - 1):+.0f}% over the period.\n"
            f"Smoothing hides one-off months such as the Jun 2026 stock-out, which is why A8 and the anomaly "
            f"detection look at single months.")


def a08(df, png):
    d = df.dropna(subset=["yoy_growth_pct"])
    fig, ax = ch.figure(11, 4.8)
    ax.bar(pd.to_datetime(d.month_start), d.yoy_growth_pct, width=20, color=ch.SLOTS[0])
    ax.axhline(0, color=ch.INK_2, linewidth=0.8)
    ch.finish(fig, ax, "A8  Year-on-year growth of monthly net sales (%)", png, ylabel="%",
              note="First comparable month: Nov 2024.")
    return (f"Year-on-year growth averaged {d.yoy_growth_pct.mean():.1f}% across months, ranging from "
            f"{d.yoy_growth_pct.min():.1f}% ({month(d.loc[d.yoy_growth_pct.idxmin(), 'month_start'])}) to "
            f"{d.yoy_growth_pct.max():.1f}% ({month(d.loc[d.yoy_growth_pct.idxmax(), 'month_start'])}).\n"
            f"Month-on-month growth mostly reflects seasons; year-on-year compares like with like and is the "
            f"better measure of trend.")


def a09(df, png):
    d = df.sort_values("sales_rank", ascending=False)
    fig, ax = ch.figure(10, 5)
    ax.barh(d["product"], d.net_sales_pkr, color=[ch.color_of(c) for c in d.category])
    for y, (v, chg) in enumerate(zip(d.net_sales_pkr, d.places_gained)):
        txt = "new" if pd.isna(chg) else (f"+{int(chg)}" if chg > 0 else str(int(chg)))
        ax.text(v, y, f"  {txt}", va="center", fontsize=8, color=ch.INK_2)
    ax.grid(axis="x", color=ch.GRID)
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v / 1e3:.0f}k")
    handles = [__import__("matplotlib").patches.Patch(color=ch.color_of(c), label=c) for c in d.category.unique()]
    ax.legend(handles=handles, fontsize=7, frameon=False, loc="lower right")
    ch.finish(fig, ax, "A9  Top-10 products by net sales, FY2026 (label: places gained since FY2025)", png,
              legend=False, note="PKR; colour = category.")
    mover = df.loc[df.places_gained.idxmax()]
    return (f"{df.iloc[0]['product']} stayed the top seller; {mover['product']} climbed the most "
            f"({int(mover.places_gained)} places, from rank {int(mover.rank_last_year)} to {int(mover.sales_rank)}).\n"
            f"{(df.category == 'Diabetes Care').sum()} of the top 10 are Diabetes Care products, so supplier "
            f"terms for this category (A12) matter for a large part of sales.")


def a10(df, png):
    # Purchase cost is valued at the SALES mix: each product-month's purchase unit cost weighted by
    # the units sold, so the comparison is not distorted by buying a different mix than is sold.
    d = df[df.category == "Diabetes Care"].copy()
    d["cost_at_sales_mix"] = d.quantity_units * d.purchase_amount_pkr / d.purchased_units
    g = d.groupby("month_start")[["net_amount_pkr", "quantity_units", "cost_at_sales_mix"]].sum()
    asp = g.net_amount_pkr / g.quantity_units
    puc = g.cost_at_sales_mix / g.quantity_units
    fig, ax = ch.figure(11, 5)
    x = pd.to_datetime(g.index)
    ax.plot(x, asp, color=ch.SLOTS[0], linewidth=2, label="Average selling price per unit")
    ax.plot(x, puc, color=ch.SLOTS[1], linewidth=2, label="Purchase cost per unit, at the sales mix")
    ax.axvline(pd.Timestamp("2026-03-01"), color=ch.INK_2, linewidth=0.8, linestyle=":")
    ax.set_ylim(bottom=0)
    ch.finish(fig, ax, "A10  Diabetes Care: selling price vs purchase unit cost per month", png, ylabel="PKR per unit",
              note="Product-months with both sales and purchases; purchase cost weighted by units sold.")

    def gap(lo, hi):
        w = g[(g.index >= pd.Timestamp(lo)) & (g.index < pd.Timestamp(hi))].sum()
        return 100 * (1 - w.cost_at_sales_mix / w.net_amount_pkr)
    before, after = gap("2025-09-01", "2026-03-01"), gap("2026-03-01", "2026-11-01")
    corr = d[["asp_pkr", "purchase_unit_cost_pkr"]].corr().iloc[0, 1]
    return (f"For Diabetes Care, purchase cost took {100 - before:.1f}% of the selling price in Sep 2025-Feb 2026 and "
            f"{100 - after:.1f}% in Mar-Oct 2026: the price-cost gap narrowed from {before:.1f}% to {after:.1f}%.\n"
            f"Across product-months, price and purchase cost move together (correlation {corr:.2f}), because dearer "
            f"products cost more to buy; the stars were summed separately before joining, so no rows were multiplied.")


def a11(df, png):
    d = df.sort_values("coefficient_of_variation")
    fig, ax = ch.figure(10, 4.8)
    ax.barh(d.category, d.coefficient_of_variation, color=[ch.color_of(c) for c in d.category])
    ax.grid(axis="x", color=ch.GRID)
    ax.grid(axis="y", visible=False)
    ch.finish(fig, ax, "A11  Volatility of monthly net sales: coefficient of variation by category", png,
              legend=False, note="CV = standard deviation / mean of the 36 monthly totals.")
    top, low = df.iloc[0], df.iloc[-1]
    return (f"{top.category} is the most volatile category (CV {top.coefficient_of_variation:.2f}) and "
            f"{low.category} the steadiest (CV {low.coefficient_of_variation:.2f}).\n"
            f"Volatile categories need larger safety stock or seasonal ordering; the CV includes the upward "
            f"trend, so part of it is growth, not risk.")


def a12(df, png):
    import matplotlib.pyplot as plt

    d = df[pd.to_datetime(df.month_start) >= "2025-07-01"].copy()
    x = pd.to_datetime(d.month_start)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, facecolor=ch.SURFACE,
                                   gridspec_kw={"height_ratios": [1, 1.4]})
    for ax in (ax1, ax2):
        ch.style(ax)
    ax1.plot(x, d.margin_pct, color=ch.SLOTS[0], linewidth=2, marker="o", markersize=4)
    ax1.set_ylim(0, max(30, d.margin_pct.max() + 3))
    ax1.set_ylabel("Margin %", fontsize=9)
    ax1.set_title("A12  Diabetes Care: margin % (top) and month-on-month margin bridge (bottom)",
                  color=ch.INK, fontsize=11, loc="left")
    w = 8
    for i, (col, lab) in enumerate((("volume_effect_pkr", "Volume (incl. mix)"), ("price_effect_pkr", "Price"),
                                    ("cost_effect_pkr", "Cost"))):
        ax2.bar(x + pd.to_timedelta((i - 1) * w, "D"), d[col], width=w, color=ch.SLOTS[i], label=lab)
    ax2.axhline(0, color=ch.INK_2, linewidth=0.8)
    ax2.set_ylabel("PKR change vs previous month", fontsize=9)
    ax2.legend(fontsize=8, frameon=False, ncol=3)
    fig.text(0.01, 0.01, "Synthetic data (seed 472). Effects add up to the month's margin change.",
             fontsize=7, color=ch.INK_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(png, dpi=110, facecolor=ch.SURFACE)
    plt.close(fig)
    m = df.set_index(pd.to_datetime(df.month_start))
    feb, mar = m.loc["2026-02-01"], m.loc["2026-03-01"]
    return (f"Diabetes Care margin fell from {feb.margin_pct:.1f}% in Feb 2026 to {mar.margin_pct:.1f}% in Mar 2026: "
            f"the cost effect was {pkr(mar.cost_effect_pkr)}, against {pkr(mar.price_effect_pkr)} from price and "
            f"{pkr(mar.volume_effect_pkr)} from volume.\n"
            f"The drop is mostly cost (standard cost up from 1 Mar 2026 while ASP stayed flat), so renegotiating or "
            f"switching the supplier is the lever (BQ4), not pricing or promotion.")


RENDER = {"A01": a01, "A02": a02, "A03": a03, "A04": a04, "A05": a05, "A06": a06, "A07": a07, "A08": a08,
          "A09": a09, "A10": a10, "A11": a11, "A12": a12}


def run_all(run_sql, out_dir: Path, source_label: str) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = [f"# Analytic queries A1-A12 ({source_label})", "",
          "Synthetic data (seed 472). Task numbers in Practicals 9 and 10 are provisional until the lab manual "
          "is checked. Each reading is generated from the query result.", ""]
    summary = []
    for path in sorted(QDIR.glob("A*.sql")):
        qid = path.name[:3]
        df = run_sql(path.read_text(encoding="utf-8"))
        stem = path.stem
        df.to_csv(out_dir / f"{stem}.csv", index=False, lineterminator="\n")
        reading = RENDER[qid](df, out_dir / f"{stem}.png")
        lab, kind, grain, feature = META[qid]
        md += [f"## {qid.replace('A0', 'A')}  {stem[4:].replace('_', ' ')}", "",
               f"- Lab: {lab} · Analysis: {kind} · Output grain: {grain} · SQL feature: {feature}",
               f"- SQL: `sql/04_queries/{path.name}` · Result: `{stem}.csv` ({len(df)} rows) · Chart: `{stem}.png`",
               "", *[f"> {line}" for line in reading.split("\n")], ""]
        summary.append({"query": qid, "file": path.name, "rows": len(df), "result": "PASS" if len(df) else "FAIL"})
    (out_dir / "readings.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    out = pd.DataFrame(summary)
    out.to_csv(out_dir / "query_run_log.csv", index=False, lineterminator="\n")
    return out


def duckdb_runner():
    import duckdb

    con = duckdb.connect(str(DATA_DIR / "offline_dw.duckdb"), read_only=True)
    return lambda sql: con.execute(sql).df()


def postgres_runner():
    from sqlalchemy import text

    from src.common import get_engine

    eng = get_engine("dw")
    return lambda sql: pd.read_sql(text(sql), eng)


if __name__ == "__main__":
    if "--duckdb" in sys.argv:
        res = run_all(duckdb_runner(), evidence_dir("06_sql") / "preview_duckdb", "pre-database DuckDB preview")
    else:
        res = run_all(postgres_runner(), evidence_dir("06_sql"), "PostgreSQL warehouse")
    print(res.to_string(index=False))
