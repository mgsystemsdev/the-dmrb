from __future__ import annotations

import argparse
import json
from pathlib import Path

from db.adapters.postgres_adapter import PostgresAdapter
from db.adapters.base_adapter import DatabaseConfig

IMPORT_ORDER = [
    "property",
    "phase",
    "building",
    "unit",
    "import_batch",
    "turnover",
    "task_template",
    "task_template_dependency",
    "turnover_task_override",
    "task",
    "task_dependency",
    "note",
    "risk_flag",
    "sla_event",
    "audit_log",
    "import_row",
    "schema_version",
]

PKS = {
    "property": ["property_id"],
    "phase": ["phase_id"],
    "building": ["building_id"],
    "unit": ["unit_id"],
    "import_batch": ["batch_id"],
    "turnover": ["turnover_id"],
    "task_template": ["template_id"],
    "task_template_dependency": ["template_id", "depends_on_template_id"],
    "turnover_task_override": ["turnover_id", "task_type"],
    "task": ["task_id"],
    "task_dependency": ["task_id", "depends_on_task_id"],
    "note": ["note_id"],
    "risk_flag": ["risk_id"],
    "sla_event": ["sla_event_id"],
    "audit_log": ["audit_id"],
    "import_row": ["row_id"],
    "schema_version": ["singleton"],
}

SEQUENCE_COLUMNS = {
    "phase": "phase_id",
    "building": "building_id",
    "unit": "unit_id",
    "import_batch": "batch_id",
    "turnover": "turnover_id",
    "task_template": "template_id",
    "task": "task_id",
    "note": "note_id",
    "risk_flag": "risk_id",
    "sla_event": "sla_event_id",
    "audit_log": "audit_id",
    "import_row": "row_id",
}


def _read_rows(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _upsert_rows(conn, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    columns = list(rows[0].keys())
    quoted_cols = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    pk_cols = PKS[table]
    update_cols = [c for c in columns if c not in pk_cols]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols) if update_cols else ""
    conflict_cols = ", ".join(pk_cols)
    if set_clause:
        sql = (
            f"INSERT INTO {table} ({quoted_cols}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {set_clause}"
        )
    else:
        sql = (
            f"INSERT INTO {table} ({quoted_cols}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_cols}) DO NOTHING"
        )
    params = [tuple(row.get(col) for col in columns) for row in rows]
    conn.executemany(sql, params)
    return len(rows)


def _reset_sequences(conn) -> None:
    for table, col in SEQUENCE_COLUMNS.items():
        conn.execute(
            "SELECT setval(pg_get_serial_sequence(?, ?), COALESCE(MAX(" + col + "), 1), true) FROM " + table,
            (table, col),
        )


def import_postgres_data(export_dir: str, postgres_url: str) -> dict[str, int]:
    adapter = PostgresAdapter()
    conn = adapter.connect(DatabaseConfig(engine="postgres", sqlite_path="", postgres_url=postgres_url))
    counts: dict[str, int] = {}
    try:
        for table in IMPORT_ORDER:
            rows = _read_rows(Path(export_dir) / f"{table}.json")
            counts[table] = _upsert_rows(conn, table, rows)
        _reset_sequences(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Import exported JSON data into Postgres.")
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--postgres-url", required=True)
    args = parser.parse_args()
    counts = import_postgres_data(args.export_dir, args.postgres_url)
    print(json.dumps({"status": "ok", "tables": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
