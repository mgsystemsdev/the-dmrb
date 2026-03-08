"""Tests for canonical unit identity: normalization, parsing, compose_identity_key, migration 004, import regression."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain import unit_identity


# ---------- normalize_unit_code ----------

def test_normalize_strip_uppercase():
    assert unit_identity.normalize_unit_code("  5-1-101  ") == "5-1-101"
    assert unit_identity.normalize_unit_code("5-1-101") == "5-1-101"
    assert unit_identity.normalize_unit_code("abc") == "ABC"


def test_normalize_unit_prefix():
    assert unit_identity.normalize_unit_code("UNIT 5-1-101") == "5-1-101"
    assert unit_identity.normalize_unit_code("unit 5-1-101") == "5-1-101"
    assert unit_identity.normalize_unit_code("  UNIT   5-1-101  ") == "5-1-101"


def test_normalize_whitespace_collapse():
    assert unit_identity.normalize_unit_code("5  -  1  -  101") == "5 - 1 - 101"
    assert unit_identity.normalize_unit_code("  a   b  ") == "A B"


def test_normalize_empty():
    assert unit_identity.normalize_unit_code("") == ""
    assert unit_identity.normalize_unit_code(None) == ""


# ---------- parse_unit_parts ----------

def test_parse_three_segments():
    assert unit_identity.parse_unit_parts("5-1-101") == ("5", "1", "101")
    assert unit_identity.parse_unit_parts("7-2-201") == ("7", "2", "201")
    assert unit_identity.parse_unit_parts("5-18-0206") == ("5", "18", "0206")


def test_parse_two_segments():
    assert unit_identity.parse_unit_parts("5-101") == ("5", "", "101")
    assert unit_identity.parse_unit_parts("7-201") == ("7", "", "201")


def test_parse_one_segment():
    assert unit_identity.parse_unit_parts("101") == ("", "", "101")
    assert unit_identity.parse_unit_parts("A") == ("", "", "A")


def test_parse_rejects_empty_unit_number():
    try:
        unit_identity.parse_unit_parts("5-1-")
    except ValueError as e:
        assert "empty" in str(e).lower() or "unit_number" in str(e)
    else:
        raise AssertionError("expected ValueError")
    try:
        unit_identity.parse_unit_parts("")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty string")


def test_parse_strips_segments():
    assert unit_identity.parse_unit_parts("  5  -  1  -  101  ") == ("5", "1", "101")


# ---------- compose_identity_key ----------

def test_compose_with_phase():
    assert unit_identity.compose_identity_key("5", "1", "101") == "5-1-101"
    # building empty yields literal "{phase}-{building}-{unit}" = "5--101"
    assert unit_identity.compose_identity_key("5", "", "101") == "5--101"
    assert unit_identity.compose_identity_key("7", "2", "201") == "7-2-201"


def test_compose_without_phase():
    assert unit_identity.compose_identity_key("", "", "101") == "101"
    assert unit_identity.compose_identity_key("", "", "A") == "A"


def test_compose_rejects_empty_unit_number():
    try:
        unit_identity.compose_identity_key("5", "1", "")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


# ---------- idempotency: same logical unit -> same identity key ----------

def test_idempotency_same_key():
    raw1 = "  UNIT  5-1-101  "
    raw2 = "5-1-101"
    n1 = unit_identity.normalize_unit_code(raw1)
    n2 = unit_identity.normalize_unit_code(raw2)
    assert n1 == n2 == "5-1-101"
    p1 = unit_identity.parse_unit_parts(n1)
    p2 = unit_identity.parse_unit_parts(n2)
    assert p1 == p2
    k1 = unit_identity.compose_identity_key(*p1)
    k2 = unit_identity.compose_identity_key(*p2)
    assert k1 == k2 == "5-1-101"


# ---------- migration 004 + uniqueness (requires DB with migrations) ----------

def _db_with_schema_and_version_3():
    """Create a temp DB with schema.sql and schema_version=3 so ensure_database_ready runs only 004."""
    from db.connection import get_connection

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    conn = get_connection(path)
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path) as fp:
        conn.executescript(fp.read())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (singleton INTEGER PRIMARY KEY CHECK (singleton=1), version INTEGER NOT NULL)"
    )
    conn.execute("INSERT OR REPLACE INTO schema_version (singleton, version) VALUES (1, 3)")
    conn.commit()
    conn.close()
    return path


def test_migration_004_applies_and_enforces_unique():
    """Ensure database_ready applies 004; then UNIQUE(property_id, unit_identity_key) is enforced."""
    from db.connection import ensure_database_ready, get_connection

    path = _db_with_schema_and_version_3()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        try:
            conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
            conn.execute(
                """INSERT INTO unit (
                   property_id, unit_code_raw, unit_code_norm, has_carpet, has_wd_expected, is_active,
                   phase_code, building_code, unit_number, unit_identity_key
                   ) VALUES (1, '5-1-101', '5-1-101', 0, 0, 1, '5', '1', '101', '5-1-101')"""
            )
            conn.commit()
            # Second unit with same (property_id, unit_identity_key) must fail
            try:
                conn.execute(
                    """INSERT INTO unit (
                       property_id, unit_code_raw, unit_code_norm, has_carpet, has_wd_expected, is_active,
                       phase_code, building_code, unit_number, unit_identity_key
                       ) VALUES (1, 'other', '5-1-101', 0, 0, 1, '5', '1', '101', '5-1-101')"""
                )
                conn.commit()
                raise AssertionError("expected UNIQUE constraint to fail")
            except sqlite3.IntegrityError:
                pass
        finally:
            conn.close()
    finally:
        os.unlink(path)


# ---------- regression: operational import flow ----------

def test_import_ensure_unit_after_migration():
    """After migration 004, _ensure_unit (used by import) still works and sets identity columns."""
    from db.connection import ensure_database_ready, get_connection
    from services import import_service

    path = _db_with_schema_and_version_3()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        try:
            conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
            conn.commit()
            row = import_service._ensure_unit(conn, property_id=1, unit_raw="5-1-101", unit_norm="5-1-101")
            conn.commit()
            assert row is not None
            assert row["unit_identity_key"] == "5-1-101"
            assert row["phase_code"] == "5"
            assert row["building_code"] == "1"
            assert row["unit_number"] == "101"
            # Idempotent: same norm again returns same unit
            row2 = import_service._ensure_unit(conn, property_id=1, unit_raw=" 5-1-101 ", unit_norm="5-1-101")
            assert row2["unit_id"] == row["unit_id"]
        finally:
            conn.close()
    finally:
        os.unlink(path)
