import os
import sqlite3
import sys
from datetime import date, datetime, timedelta

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import turnover_service, sla_service

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def _fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    return conn


def _seed_turnover(conn, *, move_out_date_iso: str):
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
    conn.execute("INSERT INTO unit (unit_id, property_id, unit_code_raw, unit_code_norm) VALUES (1,1,'A','a')")
    conn.execute(
        """INSERT INTO turnover
           (turnover_id, property_id, unit_id, source_turnover_key, move_out_date, created_at, updated_at)
           VALUES (1, 1, 1, 'k', ?, ?, ?)""",
        (move_out_date_iso, now, now),
    )
    conn.commit()


def _get_sla_reconcile_audits(conn):
    return conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'sla_reconcile' ORDER BY audit_id"
    ).fetchall()


def test_anchor_change_closes_sla_without_churn():
    conn = _fresh_db()
    old_mo = (date.today() - timedelta(days=15)).isoformat()
    _seed_turnover(conn, move_out_date_iso=old_mo)

    today = date.today()
    turnover_service.set_manual_ready_status(
        conn=conn,
        turnover_id=1,
        manual_ready_status="Vacant not ready",
        today=today,
        actor="manager",
    )
    conn.commit()
    open_row = conn.execute(
        "SELECT sla_event_id FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL"
    ).fetchone()
    assert open_row is not None, "Expected SLA breach opened"

    new_mo = date.today() - timedelta(days=5)
    turnover_service.update_turnover_dates(
        conn=conn,
        turnover_id=1,
        move_out_date=new_mo,
        today=today,
        actor="manager",
    )
    conn.commit()

    still_open = conn.execute(
        "SELECT 1 FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL"
    ).fetchone()
    assert still_open is None, "Expected SLA breach to be resolved under new anchor"

    events = conn.execute("SELECT * FROM sla_event WHERE turnover_id = 1").fetchall()
    assert len(events) == 1, f"Expected no churn events, got {len(events)} rows"
    assert events[0]["breach_resolved_at"] is not None, "Expected breach_resolved_at set"

    audits = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id = 1 AND field_name = 'effective_move_out_date'"
    ).fetchall()
    assert len(audits) == 1
    assert audits[0]["old_value"] == old_mo
    assert audits[0]["new_value"] == new_mo.isoformat()
    assert audits[0]["source"] == "manual"

    conn.close()


def test_anchor_change_keeps_open_breach_no_churn():
    conn = _fresh_db()
    old_mo = (date.today() - timedelta(days=20)).isoformat()
    _seed_turnover(conn, move_out_date_iso=old_mo)

    today = date.today()
    turnover_service.set_manual_ready_status(
        conn=conn,
        turnover_id=1,
        manual_ready_status="Vacant not ready",
        today=today,
        actor="manager",
    )
    conn.commit()

    open_row = conn.execute(
        "SELECT sla_event_id FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL"
    ).fetchone()
    assert open_row is not None
    open_id = open_row["sla_event_id"]

    new_mo = date.today() - timedelta(days=12)
    turnover_service.update_turnover_dates(
        conn=conn,
        turnover_id=1,
        move_out_date=new_mo,
        today=today,
        actor="manager",
    )
    conn.commit()

    open_row2 = conn.execute(
        "SELECT sla_event_id FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL"
    ).fetchone()
    assert open_row2 is not None
    assert open_row2["sla_event_id"] == open_id, "Expected breach to stay open without churn"

    events = conn.execute("SELECT * FROM sla_event WHERE turnover_id = 1").fetchall()
    assert len(events) == 1, f"Expected no churn events, got {len(events)} rows"

    conn.close()


def test_sla_reconcile_opened_on_anchor_change():
    conn = _fresh_db()
    # Start with non-breach anchor, then move anchor back past threshold so breach opens.
    initial_mo = (date.today() - timedelta(days=5)).isoformat()
    _seed_turnover(conn, move_out_date_iso=initial_mo)

    today = date.today()
    new_mo = date.today() - timedelta(days=15)
    turnover_service.update_turnover_dates(
        conn=conn,
        turnover_id=1,
        move_out_date=new_mo,
        today=today,
        actor="manager",
    )
    conn.commit()

    audits = _get_sla_reconcile_audits(conn)
    assert len(audits) == 1
    assert audits[0]["new_value"] == "OPENED"

    conn.close()


def test_sla_reconcile_resolved_on_manual_ready_confirm():
    conn = _fresh_db()
    old_mo = (date.today() - timedelta(days=15)).isoformat()
    _seed_turnover(conn, move_out_date_iso=old_mo)

    today = date.today()
    turnover_service.set_manual_ready_status(
        conn=conn,
        turnover_id=1,
        manual_ready_status="Vacant not ready",
        today=today,
        actor="manager",
    )
    conn.commit()

    turnover_service.confirm_manual_ready(
        conn=conn,
        turnover_id=1,
        today=today,
        actor="manager",
    )
    conn.commit()

    audits = _get_sla_reconcile_audits(conn)
    assert len(audits) == 2
    assert audits[0]["new_value"] == "OPENED"
    assert audits[1]["new_value"] == "RESOLVED"

    conn.close()


def test_anchor_change_does_not_reopen_after_ready_confirm():
    conn = _fresh_db()
    # Seed with old move-out so SLA breach opens.
    old_mo = (date.today() - timedelta(days=15)).isoformat()
    _seed_turnover(conn, move_out_date_iso=old_mo)

    today = date.today()
    # First reconcile via manual ready status to open breach.
    turnover_service.set_manual_ready_status(
        conn=conn,
        turnover_id=1,
        manual_ready_status="Vacant not ready",
        today=today,
        actor="manager",
    )
    conn.commit()

    # Confirm manual ready to close breach (stop condition).
    turnover_service.confirm_manual_ready(
        conn=conn,
        turnover_id=1,
        today=today,
        actor="manager",
    )
    conn.commit()

    # Move anchor further back in time; stop dominance must prevent reopen.
    new_mo = date.today() - timedelta(days=30)
    turnover_service.update_turnover_dates(
        conn=conn,
        turnover_id=1,
        move_out_date=new_mo,
        today=today,
        actor="manager",
    )
    conn.commit()

    # Breach must remain closed: no new open events.
    open_row = conn.execute(
        "SELECT sla_event_id FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL"
    ).fetchone()
    assert open_row is None, "Anchor change after ready confirm must not reopen SLA breach"

    # Exactly three reconcile calls: OPENED, RESOLVED, then NOOP on anchor change.
    audits = _get_sla_reconcile_audits(conn)
    assert len(audits) == 3
    assert audits[0]["new_value"] == "OPENED"
    assert audits[1]["new_value"] == "RESOLVED"
    assert audits[2]["new_value"] == "NOOP"

    conn.close()


def test_sla_reconcile_noop_when_state_unchanged():
    conn = _fresh_db()
    today = date.today()
    mo_iso = today.isoformat()
    _seed_turnover(conn, move_out_date_iso=mo_iso)

    sla_service.reconcile_sla_for_turnover(
        conn=conn,
        turnover_id=1,
        move_out_date=today,
        manual_ready_confirmed_at=None,
        today=today,
        actor="manager",
        source="manual",
        correlation_id="test-noop",
    )
    conn.commit()

    audits = _get_sla_reconcile_audits(conn)
    assert len(audits) == 1
    assert audits[0]["new_value"] == "NOOP"

    conn.close()


def test_sla_reconcile_failed_on_convergence_mismatch(monkeypatch):
    conn = _fresh_db()
    audits: list[dict] = []

    # Stub repository calls inside sla_service to manufacture a convergence mismatch safely.
    def fake_get_open_sla_event(conn_arg, turnover_id):
        # First call (evaluation) pretends there is an open event; second call (convergence check) returns None.
        if not hasattr(fake_get_open_sla_event, "count"):
            fake_get_open_sla_event.count = 0  # type: ignore[attr-defined]
        fake_get_open_sla_event.count += 1  # type: ignore[attr-defined]
        if fake_get_open_sla_event.count == 1:  # type: ignore[attr-defined]
            class Row:
                pass

            return Row()
        return None

    def fake_insert_audit_log(conn_arg, data):
        audits.append(data)
        return 1

    # Patch repository functions used by sla_service.
    monkeypatch.setattr(sla_service, "repository", sla_service.repository)
    monkeypatch.setattr(sla_service.repository, "get_open_sla_event", fake_get_open_sla_event)
    monkeypatch.setattr(sla_service.repository, "insert_audit_log", fake_insert_audit_log)
    monkeypatch.setattr(sla_service.repository, "upsert_risk", lambda *args, **kwargs: None)
    monkeypatch.setattr(sla_service.repository, "insert_sla_event", lambda *args, **kwargs: 1)
    monkeypatch.setattr(sla_service.repository, "close_sla_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(sla_service.repository, "update_sla_event_current_anchor", lambda *args, **kwargs: None)

    today = date.today()
    move_out_date = today - timedelta(days=30)

    sla_service.reconcile_sla_for_turnover(
        conn=conn,
        turnover_id=1,
        move_out_date=move_out_date,
        manual_ready_confirmed_at=None,
        today=today,
        actor="manager",
        source="manual",
        correlation_id="test-failed",
    )

    sla_audits = [a for a in audits if a["field_name"] == "sla_reconcile"]
    assert len(sla_audits) == 1
    assert sla_audits[0]["new_value"] == "FAILED"

