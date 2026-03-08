import os
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import ensure_database_ready, get_connection
from services import import_service
from imports.validation.schema_validator import ImportValidationError


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    ensure_database_ready(path)
    return path


def _seed_property(conn):
    conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'Test')")
    conn.commit()


def _write_temp_csv(contents: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(contents)
        return f.name


def test_import_fails_when_required_column_missing_and_stops_mutation():
    db_path = _fresh_db()
    try:
        conn = get_connection(db_path)
        _seed_property(conn)
        csv_path = _write_temp_csv(
            "\n".join(
                [
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "Unit,Wrong Date Column",
                    "5-1-101,2026-03-15",
                    "",
                ]
            )
        )
        try:
            with pytest.raises(ImportValidationError) as exc:
                import_service.import_report_file(
                    conn=conn,
                    report_type=import_service.MOVE_OUTS,
                    file_path=csv_path,
                    property_id=1,
                )
            payload = exc.value.to_dict()
            assert payload["error_type"] == "IMPORT_VALIDATION_FAILED"
            assert any(e["error_type"] == "MISSING_REQUIRED_COLUMN" for e in payload["errors"])
        finally:
            os.unlink(csv_path)

        batch = conn.execute("SELECT * FROM import_batch ORDER BY batch_id DESC LIMIT 1").fetchone()
        assert batch is not None
        assert batch["status"] == "FAILED"
        assert conn.execute("SELECT COUNT(*) FROM turnover").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM unit").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM task").fetchone()[0] == 0
        conn.close()
    finally:
        os.unlink(db_path)


def test_import_fails_when_date_invalid_and_stops_mutation():
    db_path = _fresh_db()
    try:
        conn = get_connection(db_path)
        _seed_property(conn)
        csv_path = _write_temp_csv(
            "\n".join(
                [
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "Unit,Move-Out Date",
                    "5-1-101,not-a-date",
                    "",
                ]
            )
        )
        try:
            with pytest.raises(ImportValidationError) as exc:
                import_service.import_report_file(
                    conn=conn,
                    report_type=import_service.MOVE_OUTS,
                    file_path=csv_path,
                    property_id=1,
                )
            payload = exc.value.to_dict()
            assert any(e["error_type"] == "INVALID_DATE_FORMAT" for e in payload["errors"])
        finally:
            os.unlink(csv_path)

        assert conn.execute("SELECT COUNT(*) FROM turnover").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM unit").fetchone()[0] == 0
        conn.close()
    finally:
        os.unlink(db_path)


def test_import_fails_when_required_sheet_missing():
    db_path = _fresh_db()
    try:
        conn = get_connection(db_path)
        _seed_property(conn)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            xlsx_path = f.name
        try:
            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                pd.DataFrame(
                    [{"Unit": "5-1-101", "Ready_Date": "2026-03-15", "Move_out": "2026-03-10", "Move_in": None, "Status": "Ready"}]
                ).to_excel(writer, sheet_name="Other", index=False)
            with pytest.raises(ImportValidationError) as exc:
                import_service.import_report_file(
                    conn=conn,
                    report_type=import_service.DMRB,
                    file_path=xlsx_path,
                    property_id=1,
                )
            payload = exc.value.to_dict()
            assert any(e["error_type"] == "MISSING_REQUIRED_SHEET" for e in payload["errors"])
        finally:
            os.unlink(xlsx_path)

        assert conn.execute("SELECT COUNT(*) FROM turnover").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM unit").fetchone()[0] == 0
        conn.close()
    finally:
        os.unlink(db_path)


def test_valid_file_passes_validation_and_imports():
    db_path = _fresh_db()
    try:
        conn = get_connection(db_path)
        _seed_property(conn)
        csv_path = _write_temp_csv(
            "\n".join(
                [
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "Unit,Move-Out Date",
                    "5-1-101,2026-03-15",
                    "",
                ]
            )
        )
        try:
            result = import_service.import_report_file(
                conn=conn,
                report_type=import_service.MOVE_OUTS,
                file_path=csv_path,
                property_id=1,
            )
            conn.commit()
        finally:
            os.unlink(csv_path)

        assert result["status"] == "SUCCESS"
        assert result["applied_count"] == 1
        assert result["invalid_count"] == 0
        assert result["diagnostics"] == []
        assert conn.execute("SELECT COUNT(*) FROM turnover").fetchone()[0] == 1
        conn.close()
    finally:
        os.unlink(db_path)
