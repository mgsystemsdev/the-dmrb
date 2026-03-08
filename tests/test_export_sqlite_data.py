import json

from db.connection import ensure_database_ready, get_connection
from scripts.export_sqlite_data import EXPORT_TABLES, export_sqlite_data


def test_export_sqlite_data_writes_expected_files(tmp_path):
    db_path = str(tmp_path / "source.db")
    export_dir = str(tmp_path / "export")
    ensure_database_ready(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute("INSERT INTO property (property_id, name) VALUES (?, ?)", (1, "P"))
        conn.commit()
    finally:
        conn.close()

    counts = export_sqlite_data(db_path, export_dir)
    assert "property" in counts

    manifest_path = tmp_path / "export" / "manifest.json"
    assert manifest_path.exists()
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["table_order"] == EXPORT_TABLES
    assert manifest["tables"]["property"] >= 1
