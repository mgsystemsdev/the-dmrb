from __future__ import annotations

from datetime import date
from pathlib import Path

from db import repository
from services import board_query_service
from tests.helpers.db_bootstrap import runtime_db


def _seed_minimal_turnover(conn) -> tuple[int, int]:
    conn.execute("INSERT INTO property (property_id, name) VALUES (1, 'Perf Test')")
    phase = repository.resolve_phase(conn, property_id=1, phase_code="5")
    building = repository.resolve_building(conn, phase_id=phase["phase_id"], building_code="1")
    unit_id = repository.insert_unit(
        conn,
        {
            "property_id": 1,
            "unit_code_raw": "5-1-101",
            "unit_code_norm": "5-1-101",
            "phase_code": "5",
            "building_code": "1",
            "unit_number": "101",
            "unit_identity_key": "5-1-101",
            "phase_id": phase["phase_id"],
            "building_id": building["building_id"],
        },
    )
    turnover_id = repository.insert_turnover(
        conn,
        {
            "property_id": 1,
            "unit_id": unit_id,
            "source_turnover_key": "perf:5-1-101:2026-03-01",
            "move_out_date": "2026-03-01",
            "move_in_date": "2026-03-20",
            "report_ready_date": "2026-03-15",
            "manual_ready_status": "Vacant not ready",
            "created_at": "2026-03-01T00:00:00",
            "updated_at": "2026-03-01T00:00:00",
        },
    )
    task_id = repository.insert_task(
        conn,
        {
            "turnover_id": turnover_id,
            "task_type": "Insp",
            "required": 1,
            "blocking": 1,
            "execution_status": "NOT_STARTED",
            "confirmation_status": "PENDING",
        },
    )
    conn.commit()
    return turnover_id, task_id


def test_board_enrichment_cache_preserves_results_and_reduces_recompute(monkeypatch):
    with runtime_db() as (conn, _):
        _seed_minimal_turnover(conn)
        today = date(2026, 3, 10)
        calls = {"count": 0}
        original = board_query_service.enrichment.enrich_row

        def _counting_enrich(row, day):
            calls["count"] += 1
            return original(row, day)

        monkeypatch.setattr(board_query_service.enrichment, "enrich_row", _counting_enrich)

        rows_first = board_query_service.get_dmrb_board_rows(conn, today=today)
        assert len(rows_first) == 1
        assert calls["count"] == 1

        calls["count"] = 0
        rows_second = board_query_service.get_dmrb_board_rows(conn, today=today)
        assert calls["count"] == 0
        assert rows_second == rows_first


def test_board_enrichment_cache_refreshes_after_task_mutation(monkeypatch):
    with runtime_db() as (conn, _):
        turnover_id, task_id = _seed_minimal_turnover(conn)
        today = date(2026, 3, 10)

        board_query_service.get_dmrb_board_rows(conn, today=today)
        repository.update_task_fields(
            conn,
            task_id,
            {
                "execution_status": "VENDOR_COMPLETED",
                "vendor_completed_at": "2026-03-10T10:00:00",
            },
            strict=False,
        )
        conn.commit()

        calls = {"count": 0}
        original = board_query_service.enrichment.enrich_row

        def _counting_enrich(row, day):
            calls["count"] += 1
            return original(row, day)

        monkeypatch.setattr(board_query_service.enrichment, "enrich_row", _counting_enrich)

        rows_after_mutation = board_query_service.get_dmrb_board_rows(conn, today=today)
        assert calls["count"] == 1
        assert rows_after_mutation[0]["turnover_id"] == turnover_id
        assert rows_after_mutation[0]["task_state"] == "In Progress"

        calls["count"] = 0
        board_query_service.get_dmrb_board_rows(conn, today=today)
        assert calls["count"] == 0


def test_audit_log_indexes_present_and_query_results_unchanged():
    with runtime_db() as (conn, _):
        rows = [
            ("turnover", 101, "move_out_date", "2026-03-10T09:00:00"),
            ("turnover", 101, "move_in_date", "2026-03-11T09:00:00"),
            ("turnover", 102, "move_out_date", "2026-03-11T10:00:00"),
            ("task", 55, "execution_status", "2026-03-12T09:00:00"),
        ]
        for i, (entity_type, entity_id, field_name, changed_at) in enumerate(rows, start=1):
            repository.insert_audit_log(
                conn,
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "field_name": field_name,
                    "old_value": None,
                    "new_value": str(i),
                    "changed_at": changed_at,
                    "actor": "tester",
                    "source": "manual",
                    "correlation_id": None,
                },
            )
        conn.commit()

        filtered = conn.execute(
            """SELECT audit_id, entity_id, field_name FROM audit_log
               WHERE entity_type = 'turnover'
                 AND entity_id = ?
                 AND changed_at >= ?
                 AND field_name = ?
               ORDER BY changed_at DESC""",
            (101, "2026-03-01", "move_in_date"),
        ).fetchall()
        assert len(filtered) == 1
        assert filtered[0]["entity_id"] == 101
        assert filtered[0]["field_name"] == "move_in_date"

        idx_rows = conn.execute("PRAGMA index_list('audit_log')").fetchall()
        idx_names = {r["name"] for r in idx_rows}
        assert "idx_audit_log_entity_id" in idx_names
        assert "idx_audit_log_changed_at" in idx_names
        assert "idx_audit_log_field_name" in idx_names
        assert "idx_audit_log_entity_changed" in idx_names


def test_postgres_schema_includes_performance_structures():
    schema = Path(__file__).resolve().parents[1] / "db" / "postgres_schema.sql"
    text = schema.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS turnover_enrichment_cache" in text
    assert "CREATE INDEX IF NOT EXISTS idx_audit_log_entity_id ON audit_log(entity_id);" in text
    assert "CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON audit_log(changed_at);" in text
    assert "CREATE INDEX IF NOT EXISTS idx_audit_log_field_name ON audit_log(field_name);" in text
