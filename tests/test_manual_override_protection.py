"""
Tests for manual override protection (auto-clear-on-match) and no SLA churn on skipped imports.
"""
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import ensure_database_ready, get_connection
from db import repository
from services import import_service, turnover_service

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
MIG_009 = os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "009_add_legal_and_availability_columns.sql")
MIG_010 = os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "010_add_sla_event_anchor_snapshot.sql")
MIG_011 = os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "011_add_manual_override_timestamps.sql")


def _fresh_db():
    """In-memory DB with schema + 009/010/011 (no phase/building; for AVAILABLE_UNITS/PENDING_MOVE_INS only)."""
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


def _seed_unit_and_turnover(conn, unit_code: str, move_out_iso: str, report_ready_iso: str = None, move_in_iso: str = None):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'P')")
    conn.execute(
        "INSERT OR IGNORE INTO unit (unit_id, property_id, unit_code_raw, unit_code_norm) VALUES (1, 1, ?, ?)",
        (unit_code, unit_code),
    )
    conn.execute(
        """INSERT INTO turnover
           (turnover_id, property_id, unit_id, source_turnover_key, move_out_date, report_ready_date, move_in_date,
            created_at, updated_at, scheduled_move_out_date)
           VALUES (1, 1, 1, 'k1', ?, ?, ?, ?, ?, ?)""",
        (move_out_iso, report_ready_iso, move_in_iso, now, now, move_out_iso),
    )
    conn.commit()




def test_manual_ready_date_then_import_different_does_not_overwrite():
    """Manual edit report_ready_date → import with different ready_date → import does not overwrite."""
    conn = _fresh_db()
    unit_code = "5-A-101"
    _seed_unit_and_turnover(conn, unit_code, "2025-01-15", report_ready_iso="2025-02-01", move_in_iso=None)
    today = date.today()

    turnover_service.update_turnover_dates(
        conn=conn, turnover_id=1, report_ready_date=date(2025, 2, 10), today=today, actor="manager"
    )
    conn.commit()
    row = conn.execute("SELECT report_ready_date, ready_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()
    assert row["report_ready_date"] == "2025-02-10"
    assert row["ready_manual_override_at"] is not None

    csv_body = "\n".join(
        ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "Unit,Status,Available Date,Move-In Ready Date", f"{unit_code},Ready,2025-02-05,2025-02-20", ""]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_body)
        path = f.name
    try:
        import_service.import_report_file(conn=conn, report_type=import_service.AVAILABLE_UNITS, file_path=path, property_id=1, today=today)
        conn.commit()
    finally:
        os.unlink(path)

    row2 = conn.execute("SELECT report_ready_date, ready_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()
    assert row2["report_ready_date"] == "2025-02-10", "Import must not overwrite manual report_ready_date"
    assert row2["ready_manual_override_at"] is not None
    skip_audits = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'import_skipped_due_to_manual_override'"
    ).fetchall()
    assert len(skip_audits) == 1
    assert "report_ready_date" in (skip_audits[0]["new_value"] or "")
    conn.close()


def test_manual_ready_date_then_import_matching_clears_override():
    """Manual edit report_ready_date → later import matches same value → override cleared."""
    conn = _fresh_db()
    unit_code = "5-A-102"
    _seed_unit_and_turnover(conn, unit_code, "2025-01-15", report_ready_iso="2025-02-01", move_in_iso=None)
    today = date.today()

    turnover_service.update_turnover_dates(
        conn=conn, turnover_id=1, report_ready_date=date(2025, 2, 10), today=today, actor="manager"
    )
    conn.commit()
    assert conn.execute("SELECT ready_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()[0] is not None

    csv_body = "\n".join(
        ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "Unit,Status,Available Date,Move-In Ready Date", f"{unit_code},Ready,2025-02-10,2025-02-10", ""]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_body)
        path = f.name
    try:
        import_service.import_report_file(conn=conn, report_type=import_service.AVAILABLE_UNITS, file_path=path, property_id=1, today=today)
        conn.commit()
    finally:
        os.unlink(path)

    row = conn.execute("SELECT report_ready_date, ready_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()
    assert row["report_ready_date"] == "2025-02-10"
    assert row["ready_manual_override_at"] is None, "Override must be cleared when import matches"
    cleared = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'manual_override_cleared' AND new_value LIKE '%report_ready_date%'"
    ).fetchall()
    assert len(cleared) == 1
    conn.close()


def test_manual_move_in_date_then_import_different_does_not_overwrite():
    """Manual edit move_in_date → import with different move_in_date → import does not overwrite."""
    conn = _fresh_db()
    unit_code = "5-A-201"
    _seed_unit_and_turnover(conn, unit_code, "2025-01-15", report_ready_iso=None, move_in_iso="2025-03-01")
    today = date.today()

    turnover_service.update_turnover_dates(
        conn=conn, turnover_id=1, move_in_date=date(2025, 3, 15), today=today, actor="manager"
    )
    conn.commit()
    row = conn.execute("SELECT move_in_date, move_in_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()
    assert row["move_in_date"] == "2025-03-15"
    assert row["move_in_manual_override_at"] is not None

    csv_body = "\n".join(
        ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "Unit,Move In Date", f"{unit_code},2025-03-01", ""]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_body)
        path = f.name
    try:
        import_service.import_report_file(conn=conn, report_type=import_service.PENDING_MOVE_INS, file_path=path, property_id=1, today=today)
        conn.commit()
    finally:
        os.unlink(path)

    row2 = conn.execute("SELECT move_in_date, move_in_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()
    assert row2["move_in_date"] == "2025-03-15", "Import must not overwrite manual move_in_date"
    assert row2["move_in_manual_override_at"] is not None
    skip_audits = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'import_skipped_due_to_manual_override' AND new_value LIKE '%move_in_date%'"
    ).fetchall()
    assert len(skip_audits) == 1
    conn.close()


def test_manual_move_in_date_then_import_matching_clears_override():
    """Manual edit move_in_date → later import matches same value → override cleared."""
    conn = _fresh_db()
    unit_code = "5-A-202"
    _seed_unit_and_turnover(conn, unit_code, "2025-01-15", report_ready_iso=None, move_in_iso="2025-03-01")
    today = date.today()

    turnover_service.update_turnover_dates(
        conn=conn, turnover_id=1, move_in_date=date(2025, 3, 20), today=today, actor="manager"
    )
    conn.commit()
    assert conn.execute("SELECT move_in_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()[0] is not None

    csv_body = "\n".join(
        ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "Unit,Move In Date", f"{unit_code},2025-03-20", ""]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_body)
        path = f.name
    try:
        import_service.import_report_file(conn=conn, report_type=import_service.PENDING_MOVE_INS, file_path=path, property_id=1, today=today)
        conn.commit()
    finally:
        os.unlink(path)

    row = conn.execute("SELECT move_in_date, move_in_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()
    assert row["move_in_date"] == "2025-03-20"
    assert row["move_in_manual_override_at"] is None, "Override must be cleared when import matches"
    cleared = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'manual_override_cleared' AND new_value LIKE '%move_in_date%'"
    ).fetchall()
    assert len(cleared) == 1
    conn.close()


def test_scheduled_move_out_override_skip_and_clear():
    """scheduled_move_out_date: override set → import different skips; import same clears."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'P')")
        conn.commit()
        today = date.today()
        unit_code = "5-A-301"
        csv_create = "\n".join(
            ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "hdr6", "Unit,Move-Out Date", f"{unit_code},2025-01-05", ""]
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_create)
            p = f.name
        try:
            import_service.import_report_file(conn=conn, report_type=import_service.MOVE_OUTS, file_path=p, property_id=1, today=today)
            conn.commit()
        finally:
            os.unlink(p)
        unit_row = repository.get_unit_by_norm(conn, property_id=1, unit_code_norm=unit_code)
        open_t = repository.get_open_turnover_by_unit(conn, unit_row["unit_id"])
        tid = open_t["turnover_id"]
        repository.update_turnover_fields(
            conn, tid, {"scheduled_move_out_date": "2025-01-10", "move_out_manual_override_at": "2025-02-01T12:00:00"}
        )
        conn.commit()
        pre_row = conn.execute(
            "SELECT scheduled_move_out_date, move_out_manual_override_at FROM turnover WHERE turnover_id = ?", (tid,)
        ).fetchone()
        assert pre_row["move_out_manual_override_at"] is not None, "Override must be set before second import"

        csv_different = "\n".join(
            ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "hdr6", "Unit,Move-Out Date", f"{unit_code},2025-01-20", ""]
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_different)
            p = f.name
        try:
            res = import_service.import_report_file(conn=conn, report_type=import_service.MOVE_OUTS, file_path=p, property_id=1, today=today)
            conn.commit()
            assert res.get("status") != "NO_OP", "Second import must not be NO_OP (checksum collision)"
        finally:
            os.unlink(p)
        row = conn.execute("SELECT scheduled_move_out_date, move_out_manual_override_at FROM turnover WHERE turnover_id = ?", (tid,)).fetchone()
        assert row["scheduled_move_out_date"] == "2025-01-10", "Import must not overwrite when override set and value differs"
        assert row["move_out_manual_override_at"] is not None
        skip_audits = conn.execute(
            "SELECT * FROM audit_log WHERE entity_type = 'turnover' AND entity_id = ? AND field_name = 'import_skipped_due_to_manual_override'",
            (tid,),
        ).fetchall()
        assert len(skip_audits) >= 1, (
            f"Expected at least one import_skipped_due_to_manual_override audit for turnover_id={tid}; "
            f"audit_log count for entity_id={tid}: "
            f"{conn.execute('SELECT COUNT(*) FROM audit_log WHERE entity_id = ?', (tid,)).fetchone()[0]}"
        )

        csv_same = "\n".join(
            ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "hdr6", "Unit,Move-Out Date", f"{unit_code},2025-01-10", ""]
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_same)
            p = f.name
        try:
            import_service.import_report_file(conn=conn, report_type=import_service.MOVE_OUTS, file_path=p, property_id=1, today=today)
            conn.commit()
        finally:
            os.unlink(p)
        row2 = conn.execute("SELECT scheduled_move_out_date, move_out_manual_override_at FROM turnover WHERE turnover_id = ?", (tid,)).fetchone()
        assert row2["scheduled_move_out_date"] == "2025-01-10"
        assert row2["move_out_manual_override_at"] is None, "Override must be cleared when import matches"
        cleared = conn.execute(
            "SELECT * FROM audit_log WHERE entity_id = ? AND field_name = 'manual_override_cleared' AND new_value LIKE '%scheduled_move_out_date%'",
            (tid,),
        ).fetchall()
        assert len(cleared) >= 1
        conn.close()
    finally:
        os.unlink(path)


def test_skip_scheduled_move_out_does_not_trigger_sla_reconcile():
    """When import skips scheduled_move_out_date due to override, no SLA churn (no new sla_event/breach toggling)."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'P')")
        conn.commit()
        today = date.today()
        unit_code = "5-A-401"
        old_mo = (date.today() - timedelta(days=20)).isoformat()
        csv_create = "\n".join(
            ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "hdr6", "Unit,Move-Out Date", f"{unit_code},{old_mo}", ""]
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_create)
            p = f.name
        try:
            import_service.import_report_file(conn=conn, report_type=import_service.MOVE_OUTS, file_path=p, property_id=1, today=today)
            conn.commit()
        finally:
            os.unlink(p)
        unit_row = repository.get_unit_by_norm(conn, property_id=1, unit_code_norm=unit_code)
        open_t = repository.get_open_turnover_by_unit(conn, unit_row["unit_id"])
        tid = open_t["turnover_id"]
        repository.update_turnover_fields(
            conn, tid,
            {"scheduled_move_out_date": "2025-01-05", "move_out_manual_override_at": "2025-02-01T12:00:00"},
        )
        conn.commit()
        turnover_service.set_manual_ready_status(
            conn=conn, turnover_id=tid, manual_ready_status="Vacant not ready", today=today, actor="manager"
        )
        conn.commit()
        sla_before = conn.execute("SELECT COUNT(*) FROM sla_event WHERE turnover_id = ?", (tid,)).fetchone()[0]
        breach_open_before = conn.execute(
            "SELECT COUNT(*) FROM sla_event WHERE turnover_id = ? AND breach_resolved_at IS NULL", (tid,)
        ).fetchone()[0]

        csv_body = "\n".join(
            ["hdr1", "hdr2", "hdr3", "hdr4", "hdr5", "hdr6", "Unit,Move-Out Date", f"{unit_code},2025-01-25", ""]
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_body)
            p = f.name
        try:
            import_service.import_report_file(conn=conn, report_type=import_service.MOVE_OUTS, file_path=p, property_id=1, today=today)
            conn.commit()
        finally:
            os.unlink(p)

        sla_after = conn.execute("SELECT COUNT(*) FROM sla_event WHERE turnover_id = ?", (tid,)).fetchone()[0]
        breach_open_after = conn.execute(
            "SELECT COUNT(*) FROM sla_event WHERE turnover_id = ? AND breach_resolved_at IS NULL", (tid,)
        ).fetchone()[0]
        assert sla_after == sla_before, "No new SLA event when update skipped"
        assert breach_open_after == breach_open_before, "No SLA breach state change when update skipped"
        conn.close()
    finally:
        os.unlink(path)


def test_availability_status_override_skip_and_clear():
    """availability_status follows same override pattern: manual status → feed mismatch skips; feed match clears."""
    conn = _fresh_db()
    unit_code = "5-A-101"
    _seed_unit_and_turnover(conn, unit_code, "2025-01-15", report_ready_iso="2025-02-01", move_in_iso=None)
    today = date.today()

    turnover_service.set_manual_ready_status(
        conn=conn, turnover_id=1, manual_ready_status="Vacant ready", today=today, actor="manager"
    )
    repository.update_turnover_fields(conn, 1, {"availability_status": "Custom"})
    conn.commit()
    row = conn.execute(
        "SELECT availability_status, status_manual_override_at FROM turnover WHERE turnover_id = 1"
    ).fetchone()
    assert row["availability_status"] == "Custom"
    assert row["status_manual_override_at"] is not None

    csv_mismatch = "\n".join(
        [
            "hdr1", "hdr2", "hdr3", "hdr4", "hdr5",
            "Unit,Status,Available Date,Move-In Ready Date",
            f"{unit_code},Ready,2025-02-01,2025-02-01",
            "",
        ]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_mismatch)
        path = f.name
    try:
        import_service.import_report_file(
            conn=conn, report_type=import_service.AVAILABLE_UNITS, file_path=path, property_id=1, today=today
        )
        conn.commit()
    finally:
        os.unlink(path)

    row2 = conn.execute(
        "SELECT availability_status, status_manual_override_at FROM turnover WHERE turnover_id = 1"
    ).fetchone()
    assert row2["availability_status"] == "Custom", "Import must not overwrite when status_manual_override_at set and feed differs"
    assert row2["status_manual_override_at"] is not None
    skip_audits = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'import_skipped_due_to_manual_override' AND new_value LIKE '%availability_status%'"
    ).fetchall()
    assert len(skip_audits) >= 1

    csv_match = "\n".join(
        [
            "hdr1", "hdr2", "hdr3", "hdr4", "hdr5",
            "Unit,Status,Available Date,Move-In Ready Date",
            f"{unit_code},Custom,2025-02-01,2025-02-01",
            "",
        ]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_match)
        path = f.name
    try:
        import_service.import_report_file(
            conn=conn, report_type=import_service.AVAILABLE_UNITS, file_path=path, property_id=1, today=today
        )
        conn.commit()
    finally:
        os.unlink(path)

    row3 = conn.execute(
        "SELECT availability_status, status_manual_override_at FROM turnover WHERE turnover_id = 1"
    ).fetchone()
    assert row3["availability_status"] == "Custom"
    assert row3["status_manual_override_at"] is None, "Override must be cleared when feed matches"
    cleared = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'manual_override_cleared' AND new_value LIKE '%availability_status%'"
    ).fetchall()
    assert len(cleared) >= 1
    conn.close()


def test_two_identical_imports_with_override_active_only_one_skip_audit():
    """Two consecutive identical imports while override active: only one skip audit row for that field+value."""
    conn = _fresh_db()
    unit_code = "5-A-101"
    _seed_unit_and_turnover(conn, unit_code, "2025-01-15", report_ready_iso="2025-02-01", move_in_iso=None)
    today = date.today()

    turnover_service.update_turnover_dates(
        conn=conn, turnover_id=1, report_ready_date=date(2025, 2, 10), today=today, actor="manager"
    )
    conn.commit()
    assert conn.execute("SELECT ready_manual_override_at FROM turnover WHERE turnover_id = 1").fetchone()[0] is not None

    csv_same = "\n".join(
        [
            "hdr1", "hdr2", "hdr3", "hdr4", "hdr5",
            "Unit,Status,Available Date,Move-In Ready Date",
            f"{unit_code},Ready,2025-02-05,2025-02-20",
            "",
        ]
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_same)
        path1 = f.name
    try:
        import_service.import_report_file(
            conn=conn, report_type=import_service.AVAILABLE_UNITS, file_path=path1, property_id=1, today=today
        )
        conn.commit()
    finally:
        os.unlink(path1)

    csv_same_again = csv_same + "\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_same_again)
        path2 = f.name
    try:
        import_service.import_report_file(
            conn=conn, report_type=import_service.AVAILABLE_UNITS, file_path=path2, property_id=1, today=today
        )
        conn.commit()
    finally:
        os.unlink(path2)

    skip_audits = conn.execute(
        """SELECT * FROM audit_log
           WHERE entity_id = 1 AND field_name = 'import_skipped_due_to_manual_override'
             AND new_value LIKE 'report_ready_date|%'"""
    ).fetchall()
    assert len(skip_audits) == 1, "Expected exactly one skip audit for same field+value across two identical imports"
    conn.close()
