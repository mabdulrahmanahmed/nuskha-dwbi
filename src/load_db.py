"""Load one batch into the warehouse stars (units 3.02-3.07). Synthetic data, seed 472.

  python -m src.load_db --batch 1                 # dimensions, then facts, then close the batch
  FAIL_AT=0.5 python -m src.load_db --batch 2 --new-batch "controlled failure test"

* Rows come from src.etl_db.run(batch): staged, crosswalked, validated rows of that batch.
* Dimensions load first (so a new product exists before its facts) as upserts on the
  surrogate key. Branch and customer keys are read back from the warehouse and never renumbered.
* Each fact table loads in ONE transaction as an upsert on its natural key
  (source_system, receipt_no / grn_no, line_no). A row is only rewritten when a value changed,
  so a rerun of unchanged input changes nothing. Rows are never deleted.
* meta.lineage gets one row per fact row (natural key -> source table and key, batch) in the
  same transaction as the facts.
* FAIL_AT=<fraction> raises an error after that share of a fact table has been written; the
  transaction rolls back, the batch is marked FAILED and the warehouse is left unchanged.
* --new-batch "<note>" loads the snapshot of --batch under a new etl.batch row (same
  watermarks), used by the controlled-failure test and its rerun.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
from sqlalchemy import text

from src.common import finish_batch, get_engine, log_stage, write_evidence
from src.etl_db import run
from src.load import (build_dim_branch, build_dim_customer, build_dim_date, build_dim_product, build_dim_supplier,
                      build_fact_purchase, build_fact_sales)

AREA = "03_warehouse"
# table -> (conflict key columns, columns never compared or overwritten)
DIMS = {"dim_date": (["date_key"], []), "dim_product": (["product_key"], ["updated_batch_id"]),
        "dim_branch": (["branch_key"], []), "dim_customer": (["customer_key"], ["updated_batch_id"]),
        "dim_supplier": (["supplier_key"], [])}
FACTS = {"fact_sales": (["source_system", "receipt_no", "line_no"], ["batch_id"]),
         "fact_purchase": (["source_system", "grn_no", "line_no"], ["batch_id"])}


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of plain-Python dicts (NaN/NA -> None, numpy scalars -> Python)."""
    out = df.astype(object).where(df.notna(), None).to_dict("records")
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()} for r in out]


def upsert(con, table: str, df: pd.DataFrame, keys: list, quiet: list, fail_at: float | None = None) -> dict:
    """INSERT ... ON CONFLICT DO UPDATE only where a value differs. Returns inserted / updated counts.

    Columns in `quiet` (batch ids) are written with the change but do not count as a change.
    """
    cols = list(df.columns)
    compare = [c for c in cols if c not in keys and c not in quiet]
    update = [c for c in cols if c not in keys]
    con.execute(text(f"CREATE TEMP TABLE tmp_load ON COMMIT DROP AS SELECT {', '.join(cols)} "
                     f"FROM dw.{table} WITH NO DATA"))
    rows = records(df)
    stop = int(len(rows) * fail_at) if fail_at is not None else None
    insert_tmp = text(f"INSERT INTO tmp_load ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
    for start in range(0, len(rows), 5000):
        chunk = rows[start:start + 5000]
        if stop is not None and start + len(chunk) > stop:
            # Controlled failure: write the first `stop` rows into the real table, then raise
            # inside the open transaction, which must roll all of them back.
            if stop > start:
                con.execute(insert_tmp, chunk[: stop - start])
            con.execute(text(f"INSERT INTO dw.{table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM tmp_load "
                             f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET "
                             + ", ".join(f"{c} = EXCLUDED.{c}" for c in update)))
            raise RuntimeError(f"FAIL_AT={fail_at}: controlled failure after {stop} of {len(rows)} rows of {table}")
        con.execute(insert_tmp, chunk)
    where = (f" WHERE ({', '.join('t.' + c for c in compare)}) IS DISTINCT FROM "
             f"({', '.join('EXCLUDED.' + c for c in compare)})") if compare else ""
    res = con.execute(text(
        f"INSERT INTO dw.{table} AS t ({', '.join(cols)}) SELECT {', '.join(cols)} FROM tmp_load "
        f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in update)
        + where + " RETURNING (xmax = 0) AS inserted")).scalars().all()
    con.execute(text("DROP TABLE tmp_load"))
    return {"rows_sent": len(rows), "inserted": sum(res), "updated": len(res) - sum(res)}


def existing_keys(table: str, code: str, key: str) -> dict:
    with get_engine("dw").connect() as con:
        rows = con.execute(text(f"SELECT {code}, {key} FROM dw.{table} WHERE {key} > 0")).fetchall()
    return dict(rows)


def warehouse_totals() -> dict:
    with get_engine("dw").connect() as con:
        r = con.execute(text(
            "SELECT (SELECT count(*) FROM dw.fact_sales), (SELECT coalesce(sum(net_amount_pkr),0) FROM dw.fact_sales),"
            " (SELECT coalesce(sum(gross_margin_pkr),0) FROM dw.fact_sales), (SELECT count(*) FROM dw.fact_purchase),"
            " (SELECT coalesce(sum(purchase_amount_pkr),0) FROM dw.fact_purchase),"
            " (SELECT count(*) FROM meta.lineage)")).first()
    return {"fact_sales_rows": r[0], "fact_sales_net_pkr": float(r[1]), "fact_sales_margin_pkr": float(r[2]),
            "fact_purchase_rows": r[3], "fact_purchase_pkr": float(r[4]), "lineage_rows": r[5]}


def new_batch(like: int, note: str) -> int:
    with get_engine("dw").begin() as con:
        return con.execute(text(
            "INSERT INTO etl.batch (watermark_from, watermark_to, status, note) SELECT watermark_from, watermark_to, "
            "'RUNNING', :n FROM etl.batch WHERE batch_id = :b RETURNING batch_id"), {"n": note, "b": like}).scalar_one()


def load(batch_id: int, load_as: int | None = None, fail_at: float | None = None) -> pd.DataFrame:
    """Load the snapshot of `batch_id`; rows are stamped with `load_as` (default: the same batch)."""
    stamp = load_as or batch_id
    res = run(batch_id)
    stg, xw = res["stg"], res["xw"]
    for part in (res["sales"], res["purch"]):
        part["valid"]["batch_id"] = stamp
    dims = {"dim_date": build_dim_date(),
            "dim_product": build_dim_product(stg, xw, stamp),
            "dim_branch": build_dim_branch(stg, existing_keys("dim_branch", "branch_code", "branch_key")),
            "dim_customer": build_dim_customer(stg, stamp, existing_keys("dim_customer", "customer_code", "customer_key")),
            "dim_supplier": build_dim_supplier(stg)}
    facts = {"fact_sales": build_fact_sales(res["sales"]["valid"], stg, dims),
             "fact_purchase": build_fact_purchase(res["purch"]["valid"], dims)}
    log = []
    try:
        with get_engine("dw").begin() as con:                      # all dimensions together
            for name, (keys, quiet) in DIMS.items():
                r = upsert(con, name, dims[name], keys, quiet)
                log.append({"batch_id": stamp, "table": f"dw.{name}", **r})
        for name, (keys, quiet) in FACTS.items():
            df = facts[name]
            with get_engine("dw").begin() as con:                  # one transaction per fact table
                r = upsert(con, name, df, keys, quiet, fail_at)
                lin = pd.DataFrame({"warehouse_table": f"dw.{name}",
                                    "natural_key": df.source_system + "|" + df.source_key,
                                    "source_system": df.source_system,
                                    "source_table": "receipt_line" if name == "fact_sales" else "grn_line",
                                    "source_key": df.source_key, "batch_id": df.batch_id})
                con.execute(text("CREATE TEMP TABLE tmp_lin ON COMMIT DROP AS SELECT * FROM meta.lineage WITH NO DATA"))
                con.execute(text("INSERT INTO tmp_lin VALUES (:warehouse_table, :natural_key, :source_system, "
                                 ":source_table, :source_key, :batch_id)"), records(lin))
                con.execute(text("INSERT INTO meta.lineage AS l SELECT * FROM tmp_lin "
                                 "ON CONFLICT (warehouse_table, natural_key) DO UPDATE SET batch_id = EXCLUDED.batch_id "
                                 "WHERE l.source_key IS DISTINCT FROM EXCLUDED.source_key"))
            log.append({"batch_id": stamp, "table": f"dw.{name}", **r})
    except Exception as exc:
        finish_batch(stamp, "FAILED")
        log_stage("load_fact", "load aborted", status="FAILED", batch_id=stamp, area=AREA, note=str(exc)[:200])
        raise
    for r in log:
        log_stage("load_dim" if "dim_" in r["table"] else "load_fact", r["table"], rows_in=r["rows_sent"],
                  rows_out=r["inserted"] + r["updated"], batch_id=stamp, area=AREA,
                  note=f"{r['inserted']} inserted, {r['updated']} updated")
    fs = facts["fact_sales"]
    finish_batch(stamp, "SUCCESS", rows_loaded=len(fs) + len(facts["fact_purchase"]),
                 amount_loaded=round(float(fs.net_amount_pkr.sum()), 2))
    out = pd.DataFrame(log)
    write_evidence(AREA, f"load_log_batch_{stamp}.csv", out)
    print(out.to_string(index=False))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", type=int, required=True, help="raw snapshot (batch) to load")
    ap.add_argument("--new-batch", help="load under a new etl.batch row with this note")
    a = ap.parse_args()
    fail = float(os.environ["FAIL_AT"]) if os.environ.get("FAIL_AT") else None
    stamp = new_batch(a.batch, a.new_batch) if a.new_batch else None
    load(a.batch, stamp, fail)
