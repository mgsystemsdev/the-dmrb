"""Tests: task creation on turnover insert and reconciliation backfill."""
import os
import sys
import tempfile
from datetime import date

import pytest

sys_path = os.path.join(os.path.dirname(__file__), "..")
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from db.connection import ensure_database_ready, get_connection
from db import repository
from services import import_service, turnover_service


def _fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    ensure_database_ready(path)
    return path


def _seed(conn, *, phase_code="5", building_code="1", unit_number="101"):
    conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'Test')")
    phase_row = repository.resolve_phase(conn, property_id=1, phase_code=phase_code)
    building_row = repository.resolve_building(conn, phase_id=phase_row["phase_id"], building_code=building_code)
    key = f"{phase_code}-{building_code}-{unit_number}"
    unit_id = repository.insert_unit(
        conn,
        {
            "property_id": 1,
            "unit_code_raw": key,
            "unit_code_norm": key,
            "phase_code": phase_code,
            "building_code": building_code,
            "unit_number": unit_number,
            "unit_identity_key": key,
            "phase_id": phase_row["phase_id"],
            "building_id": building_row["building_id"],
        },
    )
    conn.commit()
    return unit_id


EXPECTED_TASK_TYPES = {"Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW", "QC"}


def test_create_turnover_with_move_out_populates_tasks():
    """Creating a turnover via create_turnover_and_reconcile produces the 9 standard tasks."""
    path = _fresh_db()
    try:
        conn = get_connection(path)
        unit_id = _seed(conn)
        unit_row = dict(repository.get_unit_by_id(conn, unit_id))

        turnover_id = turnover_service.create_turnover_and_reconcile(
            conn=conn,
            unit_id=unit_id,
            unit_row=unit_row,
            property_id=1,
            source_turnover_key=f"test:1:5-1-101:2026-03-15",
            move_out_date=date(2026, 3, 15),
            today=date(2026, 2, 27),
        )
        conn.commit()

        tasks = repository.get_tasks_by_turnover(conn, turnover_id)
        task_types = {t["task_type"] for t in tasks}
        assert task_types == EXPECTED_TASK_TYPES, f"Expected {EXPECTED_TASK_TYPES}, got {task_types}"
        assert len(tasks) == 9
        conn.close()
    finally:
        os.unlink(path)


def test_import_move_out_creates_tasks():
    """Importing a MOVE_OUTS report creates a turnover WITH tasks."""
    path = _fresh_db()
    try:
        conn = get_connection(path)
        conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'Test')")
        conn.commit()

        csv_path = tempfile.mktemp(suffix=".csv")
        with open(csv_path, "w") as f:
            for i in range(6):
                f.write(f"header line {i}\n")
            f.write("Unit,Move-Out Date\n")
            f.write("5-1-101,2026-03-15\n")

        result = import_service.import_report_file(
            conn=conn,
            report_type="MOVE_OUTS",
            file_path=csv_path,
            property_id=1,
        )
        conn.commit()
        os.unlink(csv_path)

        assert result["applied_count"] == 1
        turnovers = conn.execute("SELECT turnover_id FROM turnover").fetchall()
        assert len(turnovers) == 1

        tasks = repository.get_tasks_by_turnover(conn, turnovers[0]["turnover_id"])
        task_types = {t["task_type"] for t in tasks}
        assert task_types == EXPECTED_TASK_TYPES
        conn.close()
    finally:
        os.unlink(path)


def test_reconcile_missing_tasks_backfills():
    """Turnovers inserted without tasks get backfilled by reconcile_missing_tasks."""
    path = _fresh_db()
    try:
        conn = get_connection(path)
        unit_id = _seed(conn)
        now = "2026-02-27T00:00:00"

        # Insert turnover directly (bypassing task instantiation)
        turnover_id = repository.insert_turnover(
            conn,
            {
                "property_id": 1,
                "unit_id": unit_id,
                "source_turnover_key": "orphan:1:5-1-101:2026-03-15",
                "move_out_date": "2026-03-15",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()

        # Confirm no tasks
        tasks = repository.get_tasks_by_turnover(conn, turnover_id)
        assert len(tasks) == 0

        # Reconcile
        count = turnover_service.reconcile_missing_tasks(conn)
        conn.commit()

        assert count == 1
        tasks = repository.get_tasks_by_turnover(conn, turnover_id)
        task_types = {t["task_type"] for t in tasks}
        assert task_types == EXPECTED_TASK_TYPES

        # Idempotent: running again should find 0
        count2 = turnover_service.reconcile_missing_tasks(conn)
        assert count2 == 0
        conn.close()
    finally:
        os.unlink(path)
