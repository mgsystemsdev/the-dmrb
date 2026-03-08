"""Tests for Unit Master Bootstrap Import: structure-only, canonical parser, strict/repair modes."""
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection, ensure_database_ready
from db import repository
from services import unit_master_import_service


def _db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _schema_path():
    return os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def test_parse_units_csv_requires_columns():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("L1\nL2\nL3\nL4\n")
        f.write("Other,Cols\n")
        f.write("a,b\n")
        f.flush()
        path = f.name
    try:
        with pytest.raises(ValueError, match="missing required column"):
            unit_master_import_service._parse_units_csv(path)
    finally:
        os.unlink(path)


def test_parse_units_csv_skips_metadata():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("Line 1\nLine 2\nLine 3\nLine 4\n")
        f.write("Unit,Floor Plan,Gross Sq. Ft.,Status\n")
        f.write("  5-1-101, 4a2 - 4a2,672,Occupied\n")
        f.write("  7-2-201, 7B1 - 7B1,780,Occupied\n")
        f.flush()
        path = f.name
    try:
        rows = unit_master_import_service._parse_units_csv(path)
        assert len(rows) == 2
        assert rows[0]["unit_identity_key"] == "5-1-101"
        assert rows[0]["floor_plan"] == "4a2 - 4a2"
        assert rows[0]["gross_sq_ft"] == 672
        assert rows[1]["unit_identity_key"] == "7-2-201"
    finally:
        os.unlink(path)


def test_run_unit_master_import_strict_mode_fails_missing_unit():
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
        conn.commit()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("L1\nL2\nL3\nL4\n")
            f.write("Unit,Floor Plan,Gross Sq. Ft.,Status\n")
            f.write("  5-1-101, 4a2,672,Ok\n")
            f.flush()
            csv_path = f.name
        try:
            result = unit_master_import_service.run_unit_master_import(
                conn, csv_path, property_id=1, strict_mode=True
            )
            assert result["status"] == "FAILED"
            assert result["conflict_count"] == 1
            assert result["applied_count"] == 0
        finally:
            os.unlink(csv_path)
        conn.close()
    finally:
        os.unlink(path)


def test_run_unit_master_import_repair_mode_creates_and_idempotent():
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
        conn.commit()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("L1\nL2\nL3\nL4\n")
            f.write("Unit,Floor Plan,Gross Sq. Ft.,Status\n")
            f.write("  5-1-101, 4a2,672,Ok\n")
            f.write("  7-2-201, 7B1,780,Ok\n")
            f.flush()
            csv_path = f.name
        try:
            result = unit_master_import_service.run_unit_master_import(
                conn, csv_path, property_id=1, strict_mode=False
            )
            assert result["status"] == "SUCCESS"
            assert result["applied_count"] == 2
            assert result["conflict_count"] == 0
            u1 = repository.get_unit_by_identity_key(conn, property_id=1, unit_identity_key="5-1-101")
            assert u1 is not None
            assert u1["floor_plan"] == "4a2"
            assert u1["gross_sq_ft"] == 672
            # Idempotent: run again — checksum match → NO_OP
            result2 = unit_master_import_service.run_unit_master_import(
                conn, csv_path, property_id=1, strict_mode=False
            )
            assert result2["status"] == "NO_OP"
            assert result2["applied_count"] == 0
            u1_again = repository.get_unit_by_identity_key(conn, property_id=1, unit_identity_key="5-1-101")
            assert u1_again["unit_id"] == u1["unit_id"]
            # No turnover created
            count = conn.execute("SELECT COUNT(*) FROM turnover").fetchone()[0]
            assert count == 0
        finally:
            os.unlink(csv_path)
        conn.close()
    finally:
        os.unlink(path)
