import os
import sys
import tempfile
from datetime import date, datetime, timedelta

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import import_service, turnover_service
from db import repository
from domain import unit_identity
from tests.helpers.db_bootstrap import bootstrap_runtime_db

def _fresh_db_with_migrations_009_010():
    return bootstrap_runtime_db()


def _dispose_db(conn, db_path: str):
    conn.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


def test_pending_fas_first_confirmation_triggers_sla_reconcile_and_does_not_overwrite_move_out_date():
    conn, db_path = _fresh_db_with_migrations_009_010()
    now = datetime.utcnow().isoformat()
    today = date.today()

    # Seed property + unit + open turnover with an old move_out_date (breach opens).
    old_mo = (today - timedelta(days=15)).isoformat()
    unit_code = "5-A-101"
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'P')")
    phase_code, building_code, unit_number = unit_identity.parse_unit_parts(unit_code)
    unit_key = unit_identity.compose_identity_key(phase_code, building_code, unit_number)
    unit_row = repository.resolve_unit(
        conn,
        property_id=1,
        phase_code=phase_code,
        building_code=building_code,
        unit_number=unit_number,
        unit_code_raw=unit_code,
        unit_code_norm=unit_code,
        unit_identity_key=unit_key,
    )
    conn.execute(
        """INSERT INTO turnover
           (turnover_id, property_id, unit_id, source_turnover_key, move_out_date, created_at, updated_at)
           VALUES (1, 1, ?, 'k', ?, ?, ?)""",
        (unit_row["unit_id"], old_mo, now, now),
    )
    conn.commit()

    turnover_service.set_manual_ready_status(
        conn=conn,
        turnover_id=1,
        manual_ready_status="Vacant not ready",
        today=today,
        actor="manager",
    )
    conn.commit()
    open_sla = conn.execute(
        "SELECT * FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL"
    ).fetchone()
    assert open_sla is not None, "Expected SLA breach opened under old anchor"

    # Import PENDING_FAS with a later confirmed move-out date that should close the breach.
    confirmed_mo = (today - timedelta(days=5)).isoformat()
    csv_body = "\n".join(
        [
            "hdr1",
            "hdr2",
            "hdr3",
            "hdr4",
            "Unit,MO / Cancel Date",
            f"{unit_code},{confirmed_mo}",
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
            correlation_id="corr-1",
            today=today,
        )
        assert res["status"] == "SUCCESS"
        conn.commit()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    t = conn.execute("SELECT * FROM turnover WHERE turnover_id = 1").fetchone()
    assert t["legal_confirmation_source"] == "fas"
    assert t["confirmed_move_out_date"] == confirmed_mo
    assert t["move_out_date"] == old_mo, "MOVE_OUTS/PENDING_FAS must not overwrite legacy move_out_date"

    open_sla2 = conn.execute(
        "SELECT * FROM sla_event WHERE turnover_id = 1 AND breach_resolved_at IS NULL"
    ).fetchone()
    assert open_sla2 is None, "Expected SLA breach resolved after confirmation anchor change"

    audits = conn.execute(
        """SELECT * FROM audit_log
           WHERE entity_id = 1 AND field_name = 'effective_move_out_date'
           ORDER BY audit_id"""
    ).fetchall()
    assert len(audits) == 1
    assert audits[0]["source"] == "import"
    assert audits[0]["correlation_id"] == "corr-1"
    assert audits[0]["old_value"] == old_mo
    assert audits[0]["new_value"] == confirmed_mo

    _dispose_db(conn, db_path)

