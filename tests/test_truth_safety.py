"""Smoke tests for truth-safety blockers: schema migration, risk/SLA reconciliation, wd_installed."""
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from db import repository
from services import task_service, turnover_service

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "002_add_exposure_risk_type.sql")


def _fresh_db():
    """In-memory DB from canonical schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    return conn


def _seed(conn):
    """Insert minimal property + unit + turnover + tasks for testing."""
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'Test Prop')")
    conn.execute(
        """INSERT INTO unit (unit_id, property_id, unit_code_raw, unit_code_norm)
           VALUES (1, 1, '101', '101')"""
    )
    now = datetime.utcnow().isoformat()
    mo = (date.today() - timedelta(days=15)).isoformat()
    mi = (date.today() + timedelta(days=2)).isoformat()
    rr = (date.today() - timedelta(days=1)).isoformat()
    conn.execute(
        """INSERT INTO turnover
           (turnover_id, property_id, unit_id, source_turnover_key,
            move_out_date, move_in_date, report_ready_date,
            created_at, updated_at)
           VALUES (1, 1, 1, 'test:101:mo', ?, ?, ?, ?, ?)""",
        (mo, mi, rr, now, now),
    )
    # QC task — NOT_STARTED
    conn.execute(
        """INSERT INTO task
           (task_id, turnover_id, task_type, required, blocking,
            execution_status, confirmation_status)
           VALUES (1, 1, 'QC', 1, 1, 'NOT_STARTED', 'PENDING')"""
    )
    # Paint task with past due date
    due = (date.today() - timedelta(days=3)).isoformat()
    conn.execute(
        """INSERT INTO task
           (task_id, turnover_id, task_type, required, blocking,
            vendor_due_date, execution_status, confirmation_status)
           VALUES (2, 1, 'Paint', 1, 0, ?, 'NOT_STARTED', 'PENDING')""",
        (due,),
    )
    conn.commit()
    return conn


# ---------- 1. Schema: EXPOSURE_RISK accepted ----------

def test_exposure_risk_insert():
    conn = _fresh_db()
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
    conn.execute("INSERT INTO unit (unit_id, property_id, unit_code_raw, unit_code_norm) VALUES (1,1,'A','a')")
    conn.execute(
        "INSERT INTO turnover (turnover_id, property_id, unit_id, source_turnover_key, move_out_date, created_at, updated_at) VALUES (1,1,1,'k','2025-01-01',?,?)",
        (now, now),
    )
    # This INSERT would fail on the old schema (missing EXPOSURE_RISK in CHECK)
    conn.execute(
        "INSERT INTO risk_flag (turnover_id, risk_type, severity, triggered_at) VALUES (1, 'EXPOSURE_RISK', 'WARNING', ?)",
        (now,),
    )
    row = conn.execute("SELECT risk_type FROM risk_flag WHERE turnover_id = 1").fetchone()
    assert row["risk_type"] == "EXPOSURE_RISK"
    conn.close()
    print("PASS test_exposure_risk_insert")


# ---------- 2. Migration on old-schema DB ----------

def test_migration_preserves_data():
    """Apply migration 002 to a DB built from the OLD schema (without EXPOSURE_RISK)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    # Build old schema by reading canonical and patching the CHECK back
    with open(SCHEMA_PATH) as f:
        schema = f.read()
    old_schema = schema.replace(
        "'DUPLICATE_OPEN_TURNOVER', 'EXPOSURE_RISK'",
        "'DUPLICATE_OPEN_TURNOVER'",
    )
    conn.executescript(old_schema)
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
    conn.execute("INSERT INTO unit (unit_id, property_id, unit_code_raw, unit_code_norm) VALUES (1,1,'A','a')")
    conn.execute(
        "INSERT INTO turnover (turnover_id, property_id, unit_id, source_turnover_key, move_out_date, created_at, updated_at) VALUES (1,1,1,'k','2025-01-01',?,?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO risk_flag (turnover_id, risk_type, severity, triggered_at) VALUES (1, 'QC_RISK', 'WARNING', ?)",
        (now,),
    )
    conn.commit()

    # Apply migration
    with open(MIGRATION_PATH) as f:
        conn.executescript(f.read())

    # Old row preserved
    row = conn.execute("SELECT risk_type FROM risk_flag WHERE turnover_id = 1").fetchone()
    assert row["risk_type"] == "QC_RISK"
    # EXPOSURE_RISK now accepted
    conn.execute(
        "INSERT INTO risk_flag (turnover_id, risk_type, severity, triggered_at) VALUES (1, 'EXPOSURE_RISK', 'CRITICAL', ?)",
        (now,),
    )
    conn.commit()
    conn.close()
    print("PASS test_migration_preserves_data")


# ---------- 3. Risk reconciliation after task changes ----------

def test_mark_vendor_completed_reconciles_risks():
    conn = _seed(_fresh_db())
    today = date.today()
    # Paint task (id=2) is overdue → EXECUTION_OVERDUE should exist after reconcile
    task_service.mark_vendor_completed(conn=conn, task_id=2, today=today)
    conn.commit()
    risks = [r["risk_type"] for r in repository.get_active_risks_by_turnover(conn, 1)]
    # EXECUTION_OVERDUE should be resolved (Paint now completed), QC_RISK should appear (move_in ≤ 3)
    assert "EXECUTION_OVERDUE" not in risks, f"EXECUTION_OVERDUE should be resolved, got {risks}"
    assert "QC_RISK" in risks, f"QC_RISK should be active, got {risks}"
    conn.close()
    print("PASS test_mark_vendor_completed_reconciles_risks")


def test_confirm_task_reconciles_risks():
    conn = _seed(_fresh_db())
    today = date.today()
    # First mark QC vendor completed, then confirm
    task_service.mark_vendor_completed(conn=conn, task_id=1, today=today)
    task_service.confirm_task(conn=conn, task_id=1, today=today)
    conn.commit()
    risks = [r["risk_type"] for r in repository.get_active_risks_by_turnover(conn, 1)]
    assert "QC_RISK" not in risks, f"QC_RISK should be resolved after confirm, got {risks}"
    conn.close()
    print("PASS test_confirm_task_reconciles_risks")


def test_reject_task_reconciles_risks():
    conn = _seed(_fresh_db())
    today = date.today()
    task_service.mark_vendor_completed(conn=conn, task_id=1, today=today)
    task_service.confirm_task(conn=conn, task_id=1, today=today)
    task_service.reject_task(conn=conn, task_id=1, today=today)
    conn.commit()
    risks = [r["risk_type"] for r in repository.get_active_risks_by_turnover(conn, 1)]
    # QC_RISK should reappear after rejection (execution reset to IN_PROGRESS)
    assert "QC_RISK" in risks, f"QC_RISK should reappear after reject, got {risks}"
    conn.close()
    print("PASS test_reject_task_reconciles_risks")


# ---------- 4. SLA reconciliation from set_manual_ready_status ----------

def test_set_manual_ready_status_triggers_sla():
    conn = _seed(_fresh_db())
    today = date.today()
    # Move-out 15 days ago, no manual_ready_confirmed_at → SLA breach should open
    turnover_service.set_manual_ready_status(
        conn=conn, turnover_id=1, manual_ready_status="Vacant not ready", today=today,
    )
    conn.commit()
    sla = conn.execute("SELECT * FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL").fetchone()
    assert sla is not None, "SLA breach should have been opened"
    conn.close()
    print("PASS test_set_manual_ready_status_triggers_sla")


# ---------- 5. wd_installed support ----------

def test_wd_installed_sets_timestamp():
    conn = _seed(_fresh_db())
    today = date.today()
    turnover_service.update_wd_panel(conn=conn, turnover_id=1, today=today, wd_installed=True)
    conn.commit()
    row = repository.get_turnover_by_id(conn, 1)
    assert row["wd_installed"] == 1
    assert row["wd_installed_at"] is not None, "wd_installed_at should be set"
    # Audit log
    audits = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'wd_installed'"
    ).fetchall()
    assert len(audits) == 1
    conn.close()
    print("PASS test_wd_installed_sets_timestamp")


def test_wd_installed_no_timestamp_on_false():
    conn = _seed(_fresh_db())
    today = date.today()
    turnover_service.update_wd_panel(conn=conn, turnover_id=1, today=today, wd_installed=False)
    conn.commit()
    row = repository.get_turnover_by_id(conn, 1)
    assert row["wd_installed"] == 0
    assert row["wd_installed_at"] is None, "wd_installed_at should remain None when set to False"
    conn.close()
    print("PASS test_wd_installed_no_timestamp_on_false")


# ---------- 6. EXPOSURE_RISK end-to-end ----------

def test_exposure_risk_reconciled():
    conn = _seed(_fresh_db())
    today = date.today()
    # report_ready_date is yesterday, no manual_ready_confirmed_at → EXPOSURE_RISK
    turnover_service.set_manual_ready_status(
        conn=conn, turnover_id=1, manual_ready_status="Vacant not ready", today=today,
    )
    conn.commit()
    risks = [r["risk_type"] for r in repository.get_active_risks_by_turnover(conn, 1)]
    assert "EXPOSURE_RISK" in risks, f"EXPOSURE_RISK should be active, got {risks}"
    conn.close()
    print("PASS test_exposure_risk_reconciled")


if __name__ == "__main__":
    test_exposure_risk_insert()
    test_migration_preserves_data()
    test_mark_vendor_completed_reconciles_risks()
    test_confirm_task_reconciles_risks()
    test_reject_task_reconciles_risks()
    test_set_manual_ready_status_triggers_sla()
    test_wd_installed_sets_timestamp()
    test_wd_installed_no_timestamp_on_false()
    test_exposure_risk_reconciled()
    print("\nAll truth-safety smoke tests passed.")
