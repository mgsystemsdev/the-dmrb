from __future__ import annotations

import sqlite3

from db.adapters.base_adapter import DatabaseConfig
from db.adapters.postgres_adapter import PostgresAdapter

VERIFY_TABLES = [
    ("turnover", "turnover_id"),
    ("task", "task_id"),
    ("audit_log", "audit_id"),
    ("note", "note_id"),
    ("import_batch", "batch_id"),
    ("import_row", "row_id"),
]

REQUIRED_FIELDS = {
    "turnover": ["property_id", "unit_id", "source_turnover_key", "move_out_date", "created_at", "updated_at"],
    "task": ["turnover_id", "task_type", "execution_status", "confirmation_status"],
    "note": ["turnover_id", "note_type", "description", "created_at"],
    "audit_log": ["entity_type", "entity_id", "field_name", "changed_at", "actor", "source"],
}


def _sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _postgres_count(conn, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"] if isinstance(row, dict) else row[0])


def verify_migration(sqlite_path: str, postgres_url: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    sqlite_conn = sqlite3.connect(sqlite_path)
    pg_conn = PostgresAdapter().connect(
        DatabaseConfig(engine="postgres", sqlite_path="", postgres_url=postgres_url)
    )
    try:
        for table, id_col in VERIFY_TABLES:
            sqlite_count = _sqlite_count(sqlite_conn, table)
            pg_count = _postgres_count(pg_conn, table)
            if sqlite_count != pg_count:
                errors.append(f"{table}: count mismatch sqlite={sqlite_count} postgres={pg_count}")

            sqlite_ids = {r[0] for r in sqlite_conn.execute(f"SELECT {id_col} FROM {table}")}
            pg_rows = pg_conn.execute(f"SELECT {id_col} FROM {table}").fetchall()
            pg_ids = {r[id_col] if isinstance(r, dict) else r[0] for r in pg_rows}
            if sqlite_ids != pg_ids:
                errors.append(f"{table}: primary-entity mismatch for {id_col}")

        for table, fields in REQUIRED_FIELDS.items():
            for field in fields:
                s_nulls = sqlite_conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {field} IS NULL"
                ).fetchone()[0]
                p_row = pg_conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE {field} IS NULL"
                ).fetchone()
                p_nulls = p_row["n"] if isinstance(p_row, dict) else p_row[0]
                if int(s_nulls) != int(p_nulls):
                    errors.append(
                        f"{table}.{field}: required-field null mismatch sqlite={s_nulls} postgres={p_nulls}"
                    )
    finally:
        sqlite_conn.close()
        pg_conn.close()
    return (len(errors) == 0, errors)
