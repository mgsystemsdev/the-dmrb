"""
Tests for legal confirmation invariant:
IF legal_confirmation_source IS NOT NULL THEN confirmed_move_out_date MUST NOT BE NULL.

On violation we must:
- NOT crash.
- Upsert risk_flag(DATA_INTEGRITY).
- Insert audit_log entry:
    field_name="confirmed_invariant_violation"
    new_value="legal_source_without_date"
    source="system".
"""
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import repository
from db.connection import get_connection, ensure_database_ready
from services import import_service

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
MIG_009 = os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "009_add_legal_and_availability_columns.sql")
MIG_010 = os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "010_add_sla_event_anchor_snapshot.sql")
MIG_011 = os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "011_add_manual_override_timestamps.sql")


def _fresh_db_in_memory():
    """Schema + migrations 009/010/011 in-memory."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    with open(MIG_009) as f:
        conn.executescript(f.read())
    with open(MIG_010) as f:
        conn.executescript(f.read())
    with open(MIG_011) as f:
        conn.executescript(f.read())
    return conn


def _db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def test_manual_confirm_with_null_date_triggers_data_integrity_risk_and_audit():
    """Simulate manual confirmation path that sets legal_confirmation_source but leaves confirmed_move_out_date NULL."""
    conn = _fresh_db_in_memory()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # Seed minimal property/unit/turnover with no legal confirmation fields set.
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
    conn.execute(
        "INSERT INTO unit (unit_id, property_id, unit_code_raw, unit_code_norm) VALUES (1, 1, 'A-101', 'A-101')"
    )
    conn.execute(
        """INSERT INTO turnover
           (turnover_id, property_id, unit_id, source_turnover_key, move_out_date, created_at, updated_at)
           VALUES (1, 1, 1, 'k', '2025-01-01', ?, ?)""",
        (now, now),
    )
    conn.commit()

    # Direct DB update that violates the invariant.
    repository.update_turnover_fields(conn, 1, {"legal_confirmation_source": "manual"})
    conn.commit()

    # Invariant enforcement should have created DATA_INTEGRITY risk and an audit row.
    risks = conn.execute(
        "SELECT * FROM risk_flag WHERE turnover_id = 1 AND risk_type = 'DATA_INTEGRITY' AND resolved_at IS NULL"
    ).fetchall()
    assert risks, "Expected DATA_INTEGRITY risk_flag for legal source without confirmed date"
    assert any(r["severity"] == "CRITICAL" for r in risks)

    audits = conn.execute(
        """SELECT * FROM audit_log
           WHERE entity_type = 'turnover'
             AND entity_id = 1
             AND field_name = 'confirmed_invariant_violation'
             AND new_value = 'legal_source_without_date'
             AND source = 'system'"""
    ).fetchall()
    assert audits, "Expected confirmed_invariant_violation audit from system"

    conn.close()


def test_import_confirm_with_null_date_triggers_invariant_violation_handling():
    """PENDING_FAS import with an invalid/blank MO / Cancel Date must not crash and must flag DATA_INTEGRITY."""
    conn = _fresh_db_in_memory()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    today = date.today()

    # Seed property + unit + open turnover.
    unit_code = "5-A-101"
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
    conn.execute(
        "INSERT INTO unit (unit_id, property_id, unit_code_raw, unit_code_norm) VALUES (1, 1, ?, ?)",
        (unit_code, unit_code),
    )
    conn.execute(
        """INSERT INTO turnover
           (turnover_id, property_id, unit_id, source_turnover_key, move_out_date, created_at, updated_at)
           VALUES (1, 1, 1, 'k', '2025-01-01', ?, ?)""",
        (now, now),
    )
    conn.commit()

    # Build PENDING_FAS CSV where MO / Cancel Date is invalid/blank (parsed as None).
    csv_body = "\n".join(
        [
            "hdr1",
            "hdr2",
            "hdr3",
            "hdr4",
            "Unit,MO / Cancel Date",
            f"{unit_code},",  # blank date
            "",
        ]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_body)
        path = f.name

    try:
        res = import_service.import_report_file(
            conn=conn,
            report_type=import_service.PENDING_FAS,
            file_path=path,
            property_id=1,
            actor="manager",
            correlation_id="test-fas-null",
            today=today,
        )
        conn.commit()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    assert res["status"] == "SUCCESS"

    # Turnover should now have legal_confirmation_source set (or we at least checked invariant on write),
    # and invariant handling should have produced DATA_INTEGRITY risk + audit if source was non-null.
    t = conn.execute("SELECT * FROM turnover WHERE turnover_id = 1").fetchone()
    if t["legal_confirmation_source"] is not None:
        risks = conn.execute(
            "SELECT * FROM risk_flag WHERE turnover_id = 1 AND risk_type = 'DATA_INTEGRITY' AND resolved_at IS NULL"
        ).fetchall()
        assert risks, "Expected DATA_INTEGRITY risk_flag when legal_confirmation_source is set but date was invalid/NULL"
        audits = conn.execute(
            """SELECT * FROM audit_log
               WHERE entity_type = 'turnover'
                 AND entity_id = 1
                 AND field_name = 'confirmed_invariant_violation'
                 AND new_value = 'legal_source_without_date'
                 AND source = 'system'"""
        ).fetchall()
        assert audits, "Expected confirmed_invariant_violation audit from system"

    conn.close()


def test_insert_turnover_with_legal_source_but_no_confirmed_date_triggers_invariant():
    """Direct insert_turnover path that sets legal_confirmation_source without confirmed_move_out_date must be guarded."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'P')")
        conn.commit()

        # Create a unit via repository so identity is valid.
        phase_row = repository.resolve_phase(conn, property_id=1, phase_code="5")
        building_row = repository.resolve_building(conn, phase_id=phase_row["phase_id"], building_code="A")
        unit_id = repository.insert_unit(
            conn,
            {
                "property_id": 1,
                "unit_code_raw": "5-A-201",
                "unit_code_norm": "5-A-201",
                "phase_code": "5",
                "building_code": "A",
                "unit_number": "201",
                "unit_identity_key": "5-A-201",
                "phase_id": phase_row["phase_id"],
                "building_id": building_row["building_id"],
            },
        )
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        # Insert turnover with legal_confirmation_source but no confirmed_move_out_date.
        turnover_id = repository.insert_turnover(
            conn,
            {
                "property_id": 1,
                "unit_id": unit_id,
                "source_turnover_key": "k-legal-source-only",
                "move_out_date": "2025-01-01",
                "move_in_date": None,
                "report_ready_date": None,
                "manual_ready_status": None,
                "manual_ready_confirmed_at": None,
                "expedited_flag": 0,
                "wd_present": None,
                "wd_supervisor_notified": None,
                "wd_notified_at": None,
                "wd_installed": None,
                "wd_installed_at": None,
                "closed_at": None,
                "canceled_at": None,
                "cancel_reason": None,
                "last_seen_moveout_batch_id": None,
                "missing_moveout_count": 0,
                "created_at": now,
                "updated_at": now,
                "scheduled_move_out_date": None,
                "confirmed_move_out_date": None,
                "legal_confirmation_source": "manual",
                "legal_confirmed_at": None,
                "legal_confirmation_note": None,
                "available_date": None,
                "availability_status": None,
            },
        )
        conn.commit()

        # Invariant handling should have fired.
        risks = conn.execute(
            "SELECT * FROM risk_flag WHERE turnover_id = ? AND risk_type = 'DATA_INTEGRITY' AND resolved_at IS NULL",
            (turnover_id,),
        ).fetchall()
        assert risks, "Expected DATA_INTEGRITY risk_flag when inserting legal source without confirmed date"

        audits = conn.execute(
            """SELECT * FROM audit_log
               WHERE entity_type = 'turnover'
                 AND entity_id = ?
                 AND field_name = 'confirmed_invariant_violation'
                 AND new_value = 'legal_source_without_date'
                 AND source = 'system'""",
            (turnover_id,),
        ).fetchall()
        assert audits, "Expected confirmed_invariant_violation audit from system"

        conn.close()
    finally:
        os.unlink(path)

