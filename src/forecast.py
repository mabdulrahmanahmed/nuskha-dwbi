"""Monthly company net sales forecast (BQ5; units 4.04 and 4.05). Synthetic data, seed 472.

Reads ONLY dw.vw_forecast_features (features built in SQL). Steps:
  1. leakage test: lag_1, lag_12 and rolling_3_prior of every month use earlier months only
  2. split in time order: training Nov 2023 - Jul 2026, untouched holdout Aug - Oct 2026
  3. baselines: seasonal naive (same month last year) and last-month naive
  4. model: ridge regression on lag_1, lag_12, rolling_3_prior, month of year (as sine/cosine)
     and Ramadan days; alpha tuned by rolling-origin validation INSIDE the training months
     (origins from month 24, three months ahead each)
  5. holdout scored by MAE and RMSE in PKR, model vs both baselines, all forecasting the three
     months from the same origin (recursive: a predicted month feeds the next month's lag_1)
  6. refit on all 36 months, forecast Nov 2026 - Jan 2027 with a range from validation errors
Stated limitation: lag_12 leaves only 21 usable training rows.

Results: ai.model_run and ai.forecast_result (run_id = hash of config + data batch, so a retried
run upserts the same rows) and CSV/PNG evidence.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from src import charts as ch
from src.common import SEED

CONFIG = {"task": "forecast", "method": "ridge", "features": ["lag_1", "lag_12", "rolling_3_prior", "month_sin",
                                                              "month_cos", "ramadan_days"],
          "alphas": [0.1, 1.0, 10.0, 100.0, 1000.0], "train_end": "2026-07-01", "holdout": ["2026-08-01", "2026-10-01"],
          "first_origin_month": 24, "horizon": 3, "interval_z": 1.28, "seed": SEED, "code_version": "1.0"}


def load_features(run_sql) -> pd.DataFrame:
    df = run_sql("SELECT * FROM dw.vw_forecast_features ORDER BY month_start")
    df["month_start"] = pd.to_datetime(df.month_start)
    for c in ("net_sales_pkr", "lag_1", "lag_12", "rolling_3_prior", "month_of_year", "ramadan_days"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df.reset_index(drop=True)


def leakage_test(df: pd.DataFrame) -> pd.DataFrame:
    """Every feature of month t must be computable from months before t only."""
    y = df.net_sales_pkr
    exp_lag1, exp_lag12 = y.shift(1), y.shift(12)
    exp_roll = y.shift(1).rolling(3, min_periods=1).mean()
    rows = []
    for name, got, exp in (("lag_1 = previous month", df.lag_1, exp_lag1), ("lag_12 = same month last year", df.lag_12,
                                                                             exp_lag12),
                           ("rolling_3_prior = mean of the 3 previous months", df.rolling_3_prior, exp_roll)):
        ok = np.allclose(got.fillna(-1), exp.fillna(-1), atol=0.01)
        rows.append({"check": f"no leakage: {name}", "result": "PASS" if ok else "FAIL"})
    return pd.DataFrame(rows)


def add_month_terms(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["month_sin"] = np.sin(2 * np.pi * df.month_of_year / 12)
    df["month_cos"] = np.cos(2 * np.pi * df.month_of_year / 12)
    return df


def fit(train: pd.DataFrame, alpha: float):
    rows = train.dropna(subset=CONFIG["features"])
    scaler = StandardScaler().fit(rows[CONFIG["features"]])
    model = Ridge(alpha=alpha).fit(scaler.transform(rows[CONFIG["features"]]), rows.net_sales_pkr)
    return scaler, model, len(rows)


def recursive_forecast(history: pd.DataFrame, future: pd.DataFrame, scaler, model) -> np.ndarray:
    """Forecast the future months one by one; each prediction becomes the next month's lag_1."""
    y = list(history.net_sales_pkr)
    preds = []
    for _, row in future.iterrows():
        feats = {"lag_1": y[-1], "lag_12": y[-12], "rolling_3_prior": float(np.mean(y[-3:])),
                 "month_sin": row.month_sin, "month_cos": row.month_cos, "ramadan_days": row.ramadan_days}
        x = scaler.transform(pd.DataFrame([feats])[CONFIG["features"]])
        p = float(model.predict(x)[0])
        preds.append(p)
        y.append(p)
    return np.array(preds)


def baselines(history: pd.DataFrame, future: pd.DataFrame) -> dict:
    y = history.net_sales_pkr.to_numpy()
    n = len(future)
    return {"seasonal_naive": np.array([y[-12 + i] for i in range(n)]), "last_month_naive": np.repeat(y[-1], n)}


def mae(a, b):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def rolling_origin(train: pd.DataFrame, alpha: float) -> list:
    """Errors of 3-month-ahead forecasts from each origin month 24.. inside the training months."""
    errors = []
    h = CONFIG["horizon"]
    for origin in range(CONFIG["first_origin_month"], len(train) - h + 1):
        hist, fut = train.iloc[:origin], train.iloc[origin:origin + h]
        scaler, model, _ = fit(hist, alpha)
        errors += list(fut.net_sales_pkr.to_numpy() - recursive_forecast(hist, fut, scaler, model))
    return errors


def run_id(batch_id: int, df: pd.DataFrame) -> str:
    """Same config + same data batch + same data -> same id, so a retry upserts the same rows."""
    payload = json.dumps(CONFIG, sort_keys=True) + f"|batch={batch_id}|rows={len(df)}|total={df.net_sales_pkr.sum():.2f}"
    return "fc-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def run(run_sql, out_dir, batch_id: int, write_db=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = add_month_terms(load_features(run_sql))
    leak = leakage_test(df)

    train = df[df.month_start <= CONFIG["train_end"]].reset_index(drop=True)
    hold = df[df.month_start.between(*CONFIG["holdout"])].reset_index(drop=True)
    tuning = pd.DataFrame([{"alpha": a, "rolling_origin_rmse": rmse(rolling_origin(train, a), 0)}
                           for a in CONFIG["alphas"]])
    alpha = float(tuning.loc[tuning.rolling_origin_rmse.idxmin(), "alpha"])
    val_errors = rolling_origin(train, alpha)

    scaler, model, n_train = fit(train, alpha)
    preds = {"ridge": recursive_forecast(train, hold, scaler, model), **baselines(train, hold)}
    actual = hold.net_sales_pkr.to_numpy()
    metrics = pd.DataFrame([{"method": k, "holdout_mae_pkr": round(mae(actual, v), 2),
                             "holdout_rmse_pkr": round(rmse(actual, v), 2)} for k, v in preds.items()])
    metrics["usable_training_rows"] = n_train

    # Refit on all 36 months; forecast Nov 2026 - Jan 2027 with a range from validation errors.
    future = pd.DataFrame({"month_start": pd.date_range("2026-11-01", periods=3, freq="MS")})
    future["month_of_year"] = future.month_start.dt.month
    future["ramadan_days"] = 0.0                                     # no Ramadan days Nov 2026 - Jan 2027
    future = add_month_terms(future)
    s_all, m_all, _ = fit(df, alpha)
    fc = recursive_forecast(df, future, s_all, m_all)
    half = CONFIG["interval_z"] * rmse(val_errors, 0)
    rid = run_id(batch_id, df)
    results = pd.concat([
        pd.DataFrame({"run_id": rid, "month_start": hold.month_start, "prediction": preds["ridge"].round(2),
                      "lower": (preds["ridge"] - half).round(2), "upper": (preds["ridge"] + half).round(2),
                      "actual": actual.round(2), "is_holdout": True}),
        pd.DataFrame({"run_id": rid, "month_start": future.month_start, "prediction": fc.round(2),
                      "lower": (fc - half).round(2), "upper": (fc + half).round(2), "actual": np.nan,
                      "is_holdout": False})], ignore_index=True)
    results["date_key"] = results.month_start.dt.strftime("%Y%m%d").astype(int)
    results["label"] = np.where(results.is_holdout, "holdout prediction", "FORECAST")
    model_run = {"run_id": rid, "task": "forecast", "method": "ridge",
                 "parameters": json.dumps({"alpha": alpha, "features": CONFIG["features"]}),
                 "training_window": "2023-11..2026-07 (holdout 2026-08..2026-10); final refit 2023-11..2026-10",
                 "data_batch_id": batch_id, "metrics": metrics.to_json(orient="records"),
                 "code_version": CONFIG["code_version"]}

    # Chart: actuals, holdout predictions of all three methods, and the forecast with its range.
    fig, ax = ch.figure(11, 5)
    ax.plot(df.month_start, df.net_sales_pkr, color=ch.INK_2, linewidth=2, label="Actual net sales")
    ax.plot(hold.month_start, preds["ridge"], color=ch.SLOTS[0], linewidth=2, marker="o", label="Ridge (holdout)")
    ax.plot(hold.month_start, preds["seasonal_naive"], color=ch.SLOTS[1], linewidth=2, linestyle="--",
            marker="o", label="Seasonal naive (holdout)")
    ax.plot(hold.month_start, preds["last_month_naive"], color=ch.SLOTS[2], linewidth=2, linestyle=":",
            marker="o", label="Last-month naive (holdout)")
    ax.plot(future.month_start, fc, color=ch.SLOTS[0], linewidth=2, marker="s", label="Forecast Nov 2026 - Jan 2027")
    ax.fill_between(future.month_start, fc - half, fc + half, color=ch.SLOTS[0], alpha=0.15, label="Forecast range")
    ax.set_ylim(bottom=0)
    ch.millions(ax)
    ch.finish(fig, ax, "Monthly net sales: holdout test (Aug-Oct 2026) and 3-month forecast", out_dir / "forecast.png",
              ylabel="PKR", note=f"Range = +/-{CONFIG['interval_z']} x rolling-origin RMSE. Forecasts are estimates.")

    leak.to_csv(out_dir / "forecast_leakage_test.csv", index=False, lineterminator="\n")
    tuning.to_csv(out_dir / "forecast_tuning.csv", index=False, lineterminator="\n")
    metrics.to_csv(out_dir / "forecast_metrics.csv", index=False, lineterminator="\n")
    results.to_csv(out_dir / "forecast_results.csv", index=False, lineterminator="\n")
    pd.DataFrame([model_run]).to_csv(out_dir / "forecast_model_run.csv", index=False, lineterminator="\n")
    if write_db:
        write_db("forecast", model_run, results)
    return {"run_id": rid, "alpha": alpha, "metrics": metrics, "results": results, "leakage": leak}
