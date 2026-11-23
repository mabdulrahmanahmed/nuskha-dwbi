"""Extract every source table into a raw snapshot for one batch (unit 2.02). Synthetic data.

  python -m src.extract --to "2026-08-31 23:59:59" --double-export data/generated/stage1/double_export.csv

* Transaction tables (receipt, receipt_line, purchase_order, goods_receipt, grn_line) are read
  where watermark_from < updated_at <= watermark_to; watermark_from is the watermark_to of the
  last SUCCESS batch in etl.batch (none for the first batch).
* Master tables (items, cost history, stores, suppliers, accounts, FX rates...) are read in full.
* Values are written as the text the source holds (DATETIME 'YYYY-MM-DD hh:mm:ss', TIMESTAMPTZ
  with '+05:00', DECIMAL with its scale, SQLite REAL as stored), so the snapshot is unchanged data.
* The till / GRN export job sends some keys twice (D01): rows listed in the double-export file
  are written a second time, as the export job does.
* Each table logs rows and amount totals (log_stage), and the logged counts are compared with
  COUNT(*) / SUM() queries run against the source with the same filter.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.common import get_engine, log_stage, start_batch, write_evidence
from src.gen.sources import COLUMNS, KEYS
from src.raw import TRANSACTION_TABLES, read_csv_text, write_raw

ENGINE_OF = {"sales_db": "sales", "finance_db": "finance", "purchasing_db": "purchasing", "inventory": "inventory"}
# Amount logged per table (SQL expression valid on every engine), None = rows only.
AMOUNT_SQL = {"receipt_line": "qty * unit_price_pkr - COALESCE(discount_pkr, 0)",
              "grn_line": "boxes_received * cost_per_box", "panel_invoice": "amount_pkr"}


def as_source_text(v):
    """Python value from a driver -> the text the source shows (None stays None)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")                       # tz-aware gives '...+05:00'
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


def _where(db: str, table: str, wm_from, wm_to) -> tuple[str, dict]:
    if (db, table) not in TRANSACTION_TABLES:
        return "", {}
    if wm_from is None:
        return " WHERE updated_at <= :wm_to", {"wm_to": wm_to}
    return " WHERE updated_at > :wm_from AND updated_at <= :wm_to", {"wm_from": wm_from, "wm_to": wm_to}


def _connect(db: str):
    con = get_engine(ENGINE_OF[db]).connect()
    if con.dialect.name == "postgresql":
        from sqlalchemy import text
        con.execute(text("SET TIME ZONE 'Asia/Karachi'"))  # TIMESTAMPTZ read and compared as Karachi time
    return con


def extract_table(db: str, table: str, wm_from, wm_to) -> tuple[pd.DataFrame, dict]:
    from sqlalchemy import text

    cols = COLUMNS[(db, table)]
    where, params = _where(db, table, wm_from, wm_to)
    amount = AMOUNT_SQL.get(table)
    with _connect(db) as con:
        rows = con.execute(text(f"SELECT {', '.join(cols)} FROM {table}{where} ORDER BY {', '.join(KEYS[table])}"),
                           params).fetchall()
        check = con.execute(text(f"SELECT COUNT(*), {('SUM(' + amount + ')') if amount else 'NULL'} "
                                 f"FROM {table}{where}"), params).first()
    df = pd.DataFrame([[as_source_text(v) for v in r] for r in rows], columns=cols, dtype=object)
    return df, {"source_count": int(check[0]), "source_amount": float(check[1]) if check[1] is not None else None}


def add_double_export(raw: dict, double_export: Path | None) -> dict:
    """Append the rows the export job sends twice (only keys present in this extract)."""
    if not double_export or not Path(double_export).exists():
        return raw
    dup = read_csv_text(Path(double_export))
    for db, table, key_cols in (("sales_db", "receipt_line", ["receipt_no", "line_no"]),
                                ("purchasing_db", "grn_line", ["grn_no", "line_no"])):
        if (db, table) not in raw:
            continue
        keys = dup[dup.source_table == table][["receipt_no", "line_no"]]
        keys.columns = key_cols
        df = raw[(db, table)]
        raw[(db, table)] = pd.concat([df, df.merge(keys, on=key_cols, how="inner")], ignore_index=True)
    return raw


def amount_of(df: pd.DataFrame, table: str):
    if table == "receipt_line":
        return float((pd.to_numeric(df.qty) * pd.to_numeric(df.unit_price_pkr)
                      - pd.to_numeric(df.discount_pkr).fillna(0)).sum())
    if table == "grn_line":
        return float((pd.to_numeric(df.boxes_received) * pd.to_numeric(df.cost_per_box)).sum())
    if table == "panel_invoice":
        return float(pd.to_numeric(df.amount_pkr).sum())
    return None


def last_watermark():
    from sqlalchemy import text

    with get_engine("dw").connect() as con:
        return con.execute(text("SELECT max(watermark_to) FROM etl.batch WHERE status = 'SUCCESS'")).scalar()


def run_extract(wm_to, double_export: Path | None, batch_id: int | None = None, wm_from="auto",
                tables=None) -> tuple[int | None, dict, pd.DataFrame]:
    if wm_from == "auto":
        wm_from = last_watermark()
    if batch_id is None:
        batch_id = start_batch(wm_from, wm_to, note="extract")
    raw, log = {}, []
    for (db, table) in tables or COLUMNS:
        df, src = extract_table(db, table, wm_from, wm_to)
        raw[(db, table)] = df
        log.append({"batch_id": batch_id, "database": db, "table": table, "rows_extracted": len(df),
                    "source_count": src["source_count"], "amount_extracted": amount_of(df, table),
                    "source_amount": src["source_amount"]})
    raw = add_double_export(raw, double_export)
    folder = write_raw(raw, batch_id)
    out = pd.DataFrame(log)
    out["rows_in_snapshot"] = [len(raw[(r.database, r.table)]) for r in out.itertuples()]
    out["counts_match"] = out.rows_extracted == out.source_count
    # Tables without an amount have NaN on both sides (pandas turns None into NaN).
    out["amounts_match"] = [(pd.isna(a) and pd.isna(b)) or (not pd.isna(a) and not pd.isna(b) and abs(a - b) < 0.005)
                            for a, b in zip(out.amount_extracted, out.source_amount)]
    for r in out.itertuples():
        log_stage("extract", f"{r.database}.{r.table}", rows_in=r.source_count, rows_out=r.rows_in_snapshot,
                  amount_in=r.source_amount, amount_out=r.amount_extracted,
                  status="OK" if r.counts_match and r.amounts_match else "MISMATCH", batch_id=batch_id,
                  note="double export appended" if r.rows_in_snapshot != r.rows_extracted else "")
    write_evidence("02_etl", f"extract_log_batch_{batch_id}.csv", out)
    print(f"raw snapshot written to {folder}")
    return batch_id, raw, out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--to", required=True, help="watermark_to (batch cut-off), e.g. '2026-08-31 23:59:59'")
    parser.add_argument("--double-export", type=Path, help="generator's double_export.csv for this stage")
    args = parser.parse_args()
    _, _, out = run_extract(pd.Timestamp(args.to).to_pydatetime(), args.double_export)
    print(out.to_string(index=False))
    if not (out.counts_match.all() and out.amounts_match.all()):
        raise SystemExit("extract check FAILED")


if __name__ == "__main__":
    main()
