"""Region x category x month anomaly detection (BQ6; units 4.06 and 4.07). Synthetic data, seed 472.

Reads ONLY dw.vw_region_category_month (24 series x 36 months, features built in SQL).
  calibration: Nov 2023 - Oct 2025        review: Nov 2025 - Oct 2026
  robust_z          transparent rule: robust z-score of ratio_to_trailing, using the median and
                    MAD of the calibration months (all series pooled); flag |z| > 3.5
  isolation_forest  model on (ratio_to_trailing, yoy_ratio, ratio_to_category), fitted on the
                    calibration months only; flag the most isolated points (contamination 2%)
Evaluation (unit 4.07): a separate copy of the review period with 25 injected spikes and drops
(labels kept); features are recomputed in Python exactly as the view computes them (checked
against the view first). Precision, recall and false alerts for both methods.
Region-wide pattern rule: 5+ of a region's 8 categories below z -1.5 in one month (one branch closed
or out of stock moves every category a little; no single cell crosses 3.5).
Case review: flags both methods agree on are traced to receipt lines; a region-wide drop is
traced to branch level (vw_sales_enriched).
Results: ai.model_run and ai.anomaly_result; run_id = hash of config + data batch.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src import charts as ch
from src.common import SEED

CONFIG = {"task": "anomaly", "calibration": ["2023-11-01", "2025-10-01"], "review": ["2025-11-01", "2026-10-01"],
          "z_threshold": 3.5, "if_features": ["ratio_to_trailing", "yoy_ratio", "ratio_to_category"],
          "if_contamination": 0.02, "n_injected": 25, "seed": SEED, "code_version": "1.0"}
FEATS = CONFIG["if_features"]


def load(run_sql) -> pd.DataFrame:
    df = run_sql("SELECT * FROM dw.vw_region_category_month ORDER BY region, category, month_start")
    df["month_start"] = pd.to_datetime(df.month_start)
    for c in ("net_sales_pkr", "trailing_median_6", "ratio_to_trailing", "yoy_ratio", "ratio_to_category"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def features(base: pd.DataFrame) -> pd.DataFrame:
    """The view's features recomputed in pandas (used for the injected copy)."""
    out = []
    for (_, _), s in base.sort_values("month_start").groupby(["region", "category"]):
        s = s.copy()
        v = s.net_sales_pkr.to_numpy()
        med = [np.median(v[max(0, i - 6):i]) if i > 0 else np.nan for i in range(len(v))]
        s["trailing_median_6"] = med
        s["ratio_to_trailing"] = s.net_sales_pkr / s.trailing_median_6.replace(0, np.nan)
        s["yoy_ratio"] = s.net_sales_pkr / s.net_sales_pkr.shift(12).replace(0, np.nan)
        out.append(s)
    out = pd.concat(out)
    avg = out.groupby(["category", "month_start"]).net_sales_pkr.transform("mean")
    out["ratio_to_category"] = out.net_sales_pkr / avg.replace(0, np.nan)
    return out.sort_values(["region", "category", "month_start"]).reset_index(drop=True)


def fit_methods(df: pd.DataFrame):
    cal = df[df.month_start.between(*CONFIG["calibration"])].dropna(subset=FEATS)
    med = float(cal.ratio_to_trailing.median())
    mad = float((cal.ratio_to_trailing - med).abs().median()) * 1.4826
    forest = IsolationForest(n_estimators=300, contamination=CONFIG["if_contamination"], random_state=SEED)
    forest.fit(cal[FEATS])
    return med, mad, forest


def score(df: pd.DataFrame, med, mad, forest) -> pd.DataFrame:
    rev = df[df.month_start.between(*CONFIG["review"])].copy()
    rev["expected"] = rev.trailing_median_6
    z = ((rev.ratio_to_trailing - med) / mad).fillna(0)
    ok = rev[FEATS].notna().all(axis=1)
    if_score = pd.Series(0.0, index=rev.index)
    if_flag = pd.Series(False, index=rev.index)
    if_score[ok] = -forest.score_samples(rev.loc[ok, FEATS])            # higher = more anomalous
    if_flag[ok] = forest.predict(rev.loc[ok, FEATS]) == -1
    a = rev.assign(method="robust_z", score=z.round(4), is_flag=z.abs() > CONFIG["z_threshold"])
    b = rev.assign(method="isolation_forest", score=if_score.round(4), is_flag=if_flag)
    return pd.concat([a, b], ignore_index=True)


def inject(base: pd.DataFrame, rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Copy of the data with 25 labelled spikes / drops placed in the review period."""
    copy = base.copy()
    review_idx = copy.index[copy.month_start.between(*CONFIG["review"])].to_numpy()
    chosen = rng.choice(review_idx, size=CONFIG["n_injected"], replace=False)
    factors = np.where(rng.random(len(chosen)) < 0.5, rng.uniform(1.8, 2.6, len(chosen)), rng.uniform(0.15, 0.45, len(chosen)))
    copy.loc[chosen, "net_sales_pkr"] = (copy.loc[chosen, "net_sales_pkr"] * factors).round(2)
    labels = copy.loc[chosen, ["region", "category", "month_start"]].assign(
        injected_factor=factors.round(3), kind=np.where(factors > 1, "spike", "drop"))
    return copy, labels


def evaluate(scored: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    key = ["region", "category", "month_start"]
    lab = labels[key].assign(is_injected=True)
    rows = []
    for method, s in scored.groupby("method"):
        m = s.merge(lab, on=key, how="left")
        m["is_injected"] = m.is_injected.astype("boolean").fillna(False).astype(bool)   # unlabelled = normal
        tp = int((m.is_flag & m.is_injected).sum())
        fp = int((m.is_flag & ~m.is_injected).sum())
        fn = int((~m.is_flag & m.is_injected).sum())
        rows.append({"method": method, "flags": tp + fp, "true_positives": tp, "false_alerts": fp, "missed": fn,
                     "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
                     "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0})
    return pd.DataFrame(rows)


def region_month_drops(scored: pd.DataFrame, min_categories: int = 5, z_below: float = -1.5) -> pd.DataFrame:
    """Pattern rule: a region-month where most categories fall together (e.g. one big branch
    closed or out of stock). Each cell may stay under the per-cell threshold, but 5+ of the
    region's 8 categories below z -1.5 in the same month is flagged as one region-wide drop."""
    rz = scored[scored.method == "robust_z"]
    g = rz.assign(low=rz.score < z_below).groupby(["region", "month_start"])
    out = pd.DataFrame({"categories_down": g.low.sum(), "categories": g.size(),
                        "value": g.net_sales_pkr.sum(), "expected": g.expected.sum()}).reset_index()
    out["is_flag"] = out.categories_down >= min_categories
    return out


def trace_lines(run_sql, region, category, month) -> pd.DataFrame:
    """The largest receipt lines behind a flagged region / category / month."""
    return run_sql(f"SELECT receipt_no, line_no, full_date, branch_name, generic_name, strength, quantity_units, "
                   f"net_amount_pkr, source_system, source_key, batch_id FROM dw.vw_sales_enriched "
                   f"WHERE region = '{region}' AND category = '{category}' AND month_start = DATE '{month:%Y-%m-%d}' "
                   f"ORDER BY net_amount_pkr DESC LIMIT 5")


def trace_branches(run_sql, region, month) -> pd.DataFrame:
    """Branch net sales in a flagged region-month vs each branch's average of the 6 months before."""
    return run_sql(
        f"WITH m AS (SELECT branch_name, month_start, SUM(net_amount_pkr) AS net, COUNT(DISTINCT receipt_no) AS receipts "
        f"FROM dw.vw_sales_enriched WHERE region = '{region}' GROUP BY branch_name, month_start) "
        f"SELECT branch_name, "
        f"SUM(CASE WHEN month_start = DATE '{month:%Y-%m-%d}' THEN net END) AS net_flag_month, "
        f"SUM(CASE WHEN month_start = DATE '{month:%Y-%m-%d}' THEN receipts END) AS receipts_flag_month, "
        f"AVG(CASE WHEN month_start < DATE '{month:%Y-%m-%d}' AND month_start >= DATE '{month:%Y-%m-%d}' - INTERVAL '6 months' "
        f"THEN net END) AS avg_net_6_months_before "
        f"FROM m GROUP BY branch_name ORDER BY branch_name")


def case_review(run_sql, scored: pd.DataFrame, region_drops: pd.DataFrame) -> pd.DataFrame:
    """Three cases: flags both methods agree on (strongest first), then the region-wide drop."""
    both = scored[scored.is_flag].groupby(["region", "category", "month_start"]).method.nunique()
    both = both[both == 2].index.tolist()
    z = scored[scored.method == "robust_z"].set_index(["region", "category", "month_start"]).score
    both = sorted(both, key=lambda k: -abs(z.get(k, 0)))
    out = []
    for region, category, month in both[:2]:
        t = trace_lines(run_sql, region, category, month)
        t.insert(0, "case", f"{region} / {category} / {month:%b %Y} (robust z {z.get((region, category, month)):+.1f}, "
                            f"flagged by both methods)")
        out.append(t)
    for r in region_drops[region_drops.is_flag].sort_values("categories_down", ascending=False).head(3 - len(out)).itertuples():
        t = trace_branches(run_sql, r.region, r.month_start)
        t.insert(0, "case", f"{r.region} / all categories / {r.month_start:%b %Y} ({r.categories_down} of "
                            f"{r.categories} categories down together)")
        out.append(t)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def run_id(batch_id: int, df: pd.DataFrame) -> str:
    payload = json.dumps(CONFIG, sort_keys=True) + f"|batch={batch_id}|rows={len(df)}|total={df.net_sales_pkr.sum():.2f}"
    return "an-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def run(run_sql, out_dir, batch_id: int, write_db=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load(run_sql)
    rid = run_id(batch_id, df)

    # The pandas features must equal the view's, or the injected evaluation would not be fair.
    mine = features(df[["region", "category", "month_start", "net_sales_pkr"]])
    feat_ok = all(np.allclose(mine[c].fillna(-9), df[c].fillna(-9), atol=0.002) for c in FEATS)

    med, mad, forest = fit_methods(df)
    scored = score(df, med, mad, forest)
    scored["run_id"], scored["is_injected_copy"] = rid, False

    rng = np.random.default_rng([SEED, 7])
    injected, labels = inject(df[["region", "category", "month_start", "net_sales_pkr"]], rng)
    inj = score(features(injected), med, mad, forest)                 # same fitted methods, injected copy
    inj["run_id"], inj["is_injected_copy"] = rid + "-injected", True      # own run id: same keys as real rows
    metrics = evaluate(inj, labels)

    drops = region_month_drops(scored)
    cases = case_review(run_sql, scored, drops)

    results = pd.concat([scored, inj], ignore_index=True)
    results["date_key"] = results.month_start.dt.strftime("%Y%m%d").astype(int)
    results = results[["run_id", "date_key", "month_start", "region", "category", "net_sales_pkr", "expected", "score",
                       "method", "is_flag", "is_injected_copy"]].rename(columns={"net_sales_pkr": "value"})
    model_run = {"run_id": rid, "task": "anomaly", "method": "robust_z + isolation_forest",
                 "parameters": json.dumps({"median": med, "mad_scaled": mad, **{k: CONFIG[k] for k in
                                           ("z_threshold", "if_features", "if_contamination", "n_injected")}}),
                 "training_window": "calibration 2023-11..2025-10; review 2025-11..2026-10",
                 "data_batch_id": batch_id, "metrics": metrics.to_json(orient="records"),
                 "code_version": CONFIG["code_version"]}

    # Chart: ratio to trailing median for every review point; flags circled.
    rz = scored[scored.method == "robust_z"]
    fig, ax = ch.figure(11, 5)
    for i, (region, s) in enumerate(rz.groupby("region")):
        ax.scatter(s.month_start + pd.to_timedelta((i - 1) * 6, "D"), s.ratio_to_trailing, s=14,
                   color=ch.color_of(region), label=f"{region}", alpha=0.8)
    f = rz[rz.is_flag]
    ax.scatter(f.month_start, f.ratio_to_trailing, s=120, facecolors="none", edgecolors=ch.INK, linewidths=1.2,
               label="Flagged (|robust z| > 3.5)")
    for r in f.itertuples():
        ax.annotate(f"{r.region[0]}-{r.category.split()[0]}", (r.month_start, r.ratio_to_trailing), fontsize=7,
                    color=ch.INK_2, xytext=(6, 4), textcoords="offset points")
    ax.axhline(1, color=ch.INK_2, linewidth=0.8)
    ch.finish(fig, ax, "Region x category months in the review period: value / trailing 6-month median", out_dir /
              "anomaly_scatter.png", ylabel="Ratio to trailing median", note="Colour = region; 8 categories per region.")

    pd.DataFrame([{"check": "pandas features equal the view's features", "result": "PASS" if feat_ok else "FAIL"}]) \
        .to_csv(out_dir / "anomaly_feature_check.csv", index=False, lineterminator="\n")
    metrics.to_csv(out_dir / "anomaly_metrics_injected.csv", index=False, lineterminator="\n")
    labels.to_csv(out_dir / "anomaly_injected_labels.csv", index=False, lineterminator="\n")
    flags_out = scored[scored.is_flag].sort_values(["method", "score"], ascending=[True, False])
    flags_out[["method", "region", "category", "month_start", "net_sales_pkr", "expected", "ratio_to_trailing",
               "yoy_ratio", "score"]].to_csv(out_dir / "anomaly_flags_real.csv", index=False, lineterminator="\n")
    cases.to_csv(out_dir / "anomaly_case_traces.csv", index=False, lineterminator="\n")
    drops.to_csv(out_dir / "anomaly_region_month_drops.csv", index=False, lineterminator="\n")
    results.to_csv(out_dir / "anomaly_results.csv", index=False, lineterminator="\n")
    pd.DataFrame([model_run]).to_csv(out_dir / "anomaly_model_run.csv", index=False, lineterminator="\n")
    if write_db:
        write_db("anomaly", model_run, results)
    return {"run_id": rid, "metrics": metrics, "flags": flags_out, "cases": cases, "feature_check": feat_ok}
