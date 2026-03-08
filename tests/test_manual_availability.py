"""Tests for manual add single unit availability (PART I)."""
import os
import tempfile
from datetime import date

import pytest

sys_path = os.path.join(os.path.dirname(__file__), "..")
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from db.connection import ensure_database_ready, get_connection
from db import repository
from services import manual_availability_service


def _db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _seed_property_phase_building_unit(conn, *, unit_number: str = "0206", phase_code: str = "5", building_code: str = "25"):
    """Create property 1, phase, building, and one unit. Returns unit_id."""
    conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'Test')")
    phase_row = repository.resolve_phase(conn, property_id=1, phase_code=phase_code)
    building_row = repository.resolve_building(conn, phase_id=phase_row["phase_id"], building_code=building_code)
    unit_identity_key = f"{phase_code}-{building_code}-{unit_number}"
    unit_id = repository.insert_unit(
        conn,
        {
            "property_id": 1,
            "unit_code_raw": unit_number,
            "unit_code_norm": unit_identity_key,
            "phase_code": phase_code,
            "building_code": building_code,
            "unit_number": unit_number,
            "unit_identity_key": unit_identity_key,
            "phase_id": phase_row["phase_id"],
            "building_id": building_row["building_id"],
        },
    )
    conn.commit()
    return unit_id


def test_add_manual_availability_unit_not_found():
    """Unit not found for (property, phase, building, unit_number) raises ValueError; no unit created."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'P')")
        repository.resolve_phase(conn, property_id=1, phase_code="5")
        conn.commit()
        # No building, no unit — lookup will fail at building or unit step
        unit_count_before = conn.execute("SELECT COUNT(*) FROM unit").fetchone()[0]

        with pytest.raises(ValueError, match="Unit not found"):
            manual_availability_service.add_manual_availability(
                conn=conn,
                property_id=1,
                phase_code="5",
                building_code="25",
                unit_number="9999",
                move_out_date=date(2025, 3, 1),
            )

        unit_count_after = conn.execute("SELECT COUNT(*) FROM unit").fetchone()[0]
        assert unit_count_after == unit_count_before, "No unit should be created"
        conn.close()
    finally:
        os.unlink(path)


def test_add_manual_availability_open_turnover_exists():
    """Unit already has an open turnover → ValueError; no second turnover."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        unit_id = _seed_property_phase_building_unit(conn, unit_number="0206")
        now = "2025-02-25T12:00:00"
        repository.insert_turnover(
            conn,
            {
                "property_id": 1,
                "unit_id": unit_id,
                "source_turnover_key": "existing:1:5-25-0206:2025-01-01",
                "move_out_date": "2025-01-01",
                "move_in_date": None,
                "report_ready_date": None,
                "created_at": now,
                "updated_at": now,
                "last_seen_moveout_batch_id": None,
                "missing_moveout_count": 0,
            },
        )
        conn.commit()

        with pytest.raises(ValueError, match="already has an open turnover"):
            manual_availability_service.add_manual_availability(
                conn=conn,
                property_id=1,
                phase_code="5",
                building_code="25",
                unit_number="0206",
                move_out_date=date(2025, 3, 1),
            )

        count = conn.execute("SELECT COUNT(*) FROM turnover WHERE unit_id = ?", (unit_id,)).fetchone()[0]
        assert count == 1
        conn.close()
    finally:
        os.unlink(path)


def test_add_manual_availability_success_creates_turnover_and_audit():
    """Success path: one turnover created, audit log entry, open turnover returned for unit."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        _seed_property_phase_building_unit(conn, unit_number="0206")
        conn.commit()

        turnover_id = manual_availability_service.add_manual_availability(
            conn=conn,
            property_id=1,
            phase_code="5",
            building_code="25",
            unit_number="0206",
            move_out_date=date(2025, 3, 1),
            move_in_date=date(2025, 4, 1),
            today=date(2025, 2, 25),
            actor="test",
        )

        assert turnover_id > 0
        row = repository.get_turnover_by_id(conn, turnover_id)
        assert row is not None
        assert row["move_out_date"] == "2025-03-01"
        assert row["move_in_date"] == "2025-04-01"
        assert row["source_turnover_key"].startswith("manual:1:")
        assert "2025-03-01" in row["source_turnover_key"]

        open_turnover = repository.get_open_turnover_by_unit(conn, row["unit_id"])
        assert open_turnover is not None
        assert open_turnover["turnover_id"] == turnover_id

        audit = conn.execute(
            "SELECT * FROM audit_log WHERE entity_type = 'turnover' AND entity_id = ? AND field_name = 'created'",
            (turnover_id,),
        ).fetchone()
        assert audit is not None
        assert audit["new_value"] == "manual_availability"
        assert audit["source"] == "manual"
        assert audit["actor"] == "test"

        # Default task templates are ensured for the phase; turnover should have tasks (schedule populated)
        tasks = repository.get_tasks_by_turnover(conn, turnover_id)
        assert len(tasks) >= 1, "Turnover should have tasks (default templates instantiated when phase had none)"
        task_types = {t["task_type"] for t in tasks}
        assert "QC" in task_types and "Insp" in task_types, "Expected at least Insp and QC in default set"

        conn.close()
    finally:
        os.unlink(path)


def test_add_manual_availability_empty_unit_number_raises():
    """Empty unit number raises ValueError before any DB lookup."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        with pytest.raises(ValueError, match="Unit number is required"):
            manual_availability_service.add_manual_availability(
                conn=conn,
                property_id=1,
                phase_code="5",
                building_code="25",
                unit_number="   ",
                move_out_date=date(2025, 3, 1),
            )
        conn.close()
    finally:
        os.unlink(path)


def test_add_manual_availability_second_call_fails_open_turnover():
    """Idempotency: second add for same unit without closing first fails with open turnover error."""
    path = _db_path()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        _seed_property_phase_building_unit(conn, unit_number="0206")
        conn.commit()

        manual_availability_service.add_manual_availability(
            conn=conn,
            property_id=1,
            phase_code="5",
            building_code="25",
            unit_number="0206",
            move_out_date=date(2025, 3, 1),
            today=date(2025, 2, 25),
        )

        with pytest.raises(ValueError, match="already has an open turnover"):
            manual_availability_service.add_manual_availability(
                conn=conn,
                property_id=1,
                phase_code="5",
                building_code="25",
                unit_number="0206",
                move_out_date=date(2025, 3, 15),
                today=date(2025, 2, 25),
            )

        count = conn.execute("SELECT COUNT(*) FROM turnover").fetchone()[0]
        assert count == 1
        conn.close()
    finally:
        os.unlink(path)
