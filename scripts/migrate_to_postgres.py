from __future__ import annotations

import argparse
import json
import tempfile

from db.adapters.base_adapter import DatabaseConfig
from db.adapters.postgres_adapter import PostgresAdapter
from db.postgres_bootstrap import ensure_postgres_ready
from scripts.export_sqlite_data import export_sqlite_data
from scripts.import_postgres_data import import_postgres_data
from scripts.migration_verify import verify_migration


def migrate_to_postgres(sqlite_path: str, postgres_url: str, export_dir: str | None = None) -> dict:
    temp_dir = tempfile.mkdtemp(prefix="dmrb_pg_export_")
    output_dir = export_dir or temp_dir

    pg_conn = PostgresAdapter().connect(
        DatabaseConfig(engine="postgres", sqlite_path="", postgres_url=postgres_url)
    )
    try:
        ensure_postgres_ready(pg_conn)
    finally:
        pg_conn.close()

    export_counts = export_sqlite_data(sqlite_path, output_dir)
    import_counts = import_postgres_data(output_dir, postgres_url)
    ok, errors = verify_migration(sqlite_path, postgres_url)

    return {
        "export_dir": output_dir,
        "export_counts": export_counts,
        "import_counts": import_counts,
        "verified": ok,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-command DMRB SQLite -> Postgres migration workflow."
    )
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--export-dir", required=False)
    args = parser.parse_args()

    result = migrate_to_postgres(
        sqlite_path=args.sqlite_path,
        postgres_url=args.postgres_url,
        export_dir=args.export_dir,
    )
    print(json.dumps(result, indent=2))
    if not result["verified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
