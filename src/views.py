"""Create the saved views in nuskha_dw and check them (unit 4.01). Synthetic data, seed 472.

Runs every file in sql/03_views/ (CREATE OR REPLACE VIEW, so it is safe to repeat), then checks
that each view's total equals the fact total under the same filter (cancelled rows excluded),
using the same checks that were first run on the DuckDB preview (src/offline_warehouse.py).

  python -m src.views          # -> evidence/06_sql/view_checks.csv and etl.validation_result
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from src.common import SQL_DIR, get_engine, write_evidence
from src.create_sources import split_statements
from src.offline_warehouse import view_checks


class _PgAdapter:
    """Gives a SQLAlchemy connection the .execute(sql).fetchone() shape view_checks() expects."""

    def __init__(self, con):
        self.con = con

    def execute(self, sql):
        return self.con.execute(text(sql))


def create_views() -> list:
    names = []
    with get_engine("dw").begin() as con:
        for path in sorted((SQL_DIR / "03_views").glob("*.sql")):
            for stmt in split_statements(path.read_text(encoding="utf-8")):
                con.execute(text(stmt))
            names.append(path.stem)
    return names


def main() -> pd.DataFrame:
    from src.etl_db import record_checks

    names = create_views()
    print(f"{len(names)} views created: {', '.join(names)}")
    with get_engine("dw").connect() as con:
        out = view_checks(_PgAdapter(con))
        cancelled = con.execute(text(
            "SELECT count(*) FROM dw.vw_sales_enriched v JOIN dw.fact_sales f "
            "ON f.receipt_no = v.receipt_no AND f.line_no = v.line_no WHERE f.is_cancelled")).scalar()
    out.loc[len(out)] = ["vw_sales_enriched: cancelled lines excluded", 0, cancelled,
                         "PASS" if cancelled == 0 else "FAIL"]
    write_evidence("06_sql", "view_checks.csv", out)
    with get_engine("dw").connect() as con:
        last = con.execute(text("SELECT max(batch_id) FROM etl.batch WHERE status = 'SUCCESS'")).scalar()
    record_checks(last, out.to_dict("records"))
    print(out.to_string(index=False))
    if (out.result == "FAIL").any():
        raise SystemExit(1)
    return out


if __name__ == "__main__":
    main()
