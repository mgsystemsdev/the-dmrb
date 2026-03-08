from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

EXPORT_TABLES = [
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


def export_sqlite_data(sqlite_path: str, output_dir: str) -> dict[str, int]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    try:
        for table in EXPORT_TABLES:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            data = [dict(r) for r in rows]
            counts[table] = len(data)
            with open(out / f"{table}.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    finally:
        conn.close()

    with open(out / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "sqlite_path": os.path.abspath(sqlite_path),
                "tables": counts,
                "table_order": EXPORT_TABLES,
            },
            f,
            indent=2,
        )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Export SQLite tables as JSON files.")
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    counts = export_sqlite_data(args.sqlite_path, args.output_dir)
    print(json.dumps({"status": "ok", "tables": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
