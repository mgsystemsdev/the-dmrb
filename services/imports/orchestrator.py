"""Main import entrypoint: checksum, validate, parse, apply, post-process, backup."""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Optional

from db import connection as db_connection
from db import repository
from imports.validation.file_validator import validate_import_file
from imports.validation.schema_validator import validate_import_schema

from services.imports.available_units import (
    _parse_available_units,
    apply_available_units,
    reconcile_available_units_vacancy_invariant,
)
from services.imports.constants import (
    APP_SETTINGS,
    AVAILABLE_UNITS,
    DMRB,
    MOVE_OUTS,
    PENDING_FAS,
    PENDING_MOVE_INS,
)
from services.imports.dmrb import _parse_dmrb, apply_dmrb
from services.imports.move_ins import _parse_pending_move_ins, apply_pending_move_ins
from services.imports.move_outs import (
    _parse_move_outs,
    apply_move_outs,
    post_process_after_move_outs,
)
from services.imports.pending_fas import _parse_pending_fas, apply_pending_fas
from services.imports.common import _now_iso
from services.imports.tasks import instantiate_tasks_for_turnover
from services.imports.validation import _sha256_file


def import_report_file(
    *,
    conn,
    report_type: str,
    file_path: str,
    property_id: int = APP_SETTINGS.default_property_id,
    actor: str = APP_SETTINGS.default_actor,
    correlation_id: Optional[str] = None,
    db_path: Optional[str] = None,
    backup_dir: Optional[str] = None,
    today: Optional[date] = None,
) -> dict:
    if today is None:
        today = date.today()
    source_file_name = os.path.basename(file_path)
    checksum = _sha256_file(report_type, file_path)

    # For AVAILABLE_UNITS we must allow multiple imports of the same physical
    # file (same bytes) to create new batches so that updated importer rules
    # can be applied over time. The schema enforces a UNIQUE constraint on
    # checksum, so we salt the checksum with a timestamp to keep it unique
    # per import while still retaining the underlying file checksum prefix.
    if report_type == AVAILABLE_UNITS:
        checksum = f"{checksum}:{_now_iso()}"

    # Checksum-based NO_OP short-circuit is preserved for most report types,
    # but AVAILABLE_UNITS must always create a new batch so that importer
    # rule changes (e.g. vacancy invariants) can be re-applied even when
    # the underlying file is identical.
    if report_type != AVAILABLE_UNITS:
        existing = repository.get_import_batch_by_checksum(conn, checksum)
        if existing is not None:
            return {
                "report_type": report_type,
                "checksum": checksum,
                "status": "NO_OP",
                "batch_id": existing["batch_id"],
                "record_count": 0,
                "applied_count": 0,
                "conflict_count": 0,
                "invalid_count": 0,
                "diagnostics": [],
            }

    try:
        validate_import_file(report_type, file_path)
        validate_import_schema(report_type, file_path)
        if report_type == MOVE_OUTS:
            rows = _parse_move_outs(file_path)
        elif report_type == PENDING_MOVE_INS:
            rows = _parse_pending_move_ins(file_path)
        elif report_type == AVAILABLE_UNITS:
            rows = _parse_available_units(file_path)
        elif report_type == PENDING_FAS:
            rows = _parse_pending_fas(file_path)
        elif report_type == DMRB:
            rows = _parse_dmrb(file_path)
        else:
            raise ValueError(f"Unknown report_type: {report_type}")
    except Exception:
        repository.insert_import_batch(conn, {
            "report_type": report_type,
            "checksum": checksum,
            "source_file_name": source_file_name,
            "record_count": 0,
            "status": "FAILED",
            "imported_at": _now_iso(),
        })
        raise

    now_iso = _now_iso()
    batch_id = repository.insert_import_batch(conn, {
        "report_type": report_type,
        "checksum": checksum,
        "source_file_name": source_file_name,
        "record_count": len(rows),
        "status": "SUCCESS",
        "imported_at": now_iso,
    })
    corr_id = correlation_id or f"batch:{batch_id}"

    applied_count = 0
    conflict_count = 0
    invalid_count = 0
    diagnostics: list[dict[str, Any]] = []
    seen_unit_ids_move_outs: set[int] = set()

    if report_type == MOVE_OUTS:
        applied_count, conflict_count, invalid_count, diagnostics, seen_unit_ids_move_outs = apply_move_outs(
            conn, batch_id, rows, property_id, now_iso, actor, corr_id
        )
        post_process_after_move_outs(conn, property_id, batch_id, seen_unit_ids_move_outs, now_iso, actor, corr_id)
    elif report_type == PENDING_MOVE_INS:
        applied_count, conflict_count, invalid_count, diagnostics = apply_pending_move_ins(
            conn, batch_id, rows, property_id, now_iso, actor, corr_id
        )
    elif report_type == PENDING_FAS:
        applied_count, conflict_count, invalid_count, diagnostics = apply_pending_fas(
            conn, batch_id, rows, property_id, now_iso, actor, corr_id, today=today
        )
    elif report_type == AVAILABLE_UNITS:
        applied_count, conflict_count, invalid_count, diagnostics = apply_available_units(
            conn, batch_id, rows, property_id, now_iso, actor, corr_id
        )
        # After applying AVAILABLE_UNITS, reconcile the vacancy invariant so that
        # legacy batches with Vacant rows and Available Date but no open turnover
        # are brought into alignment with the current rules.
        reconcile_available_units_vacancy_invariant(
            conn,
            property_id=property_id,
            today=today,
            actor=actor,
        )
    elif report_type == DMRB:
        applied_count, conflict_count, invalid_count, diagnostics = apply_dmrb(
            conn, batch_id, rows, property_id, now_iso, actor, corr_id
        )

    if db_path and backup_dir:
        db_connection.backup_database(db_path, backup_dir, batch_id)

    return {
        "report_type": report_type,
        "checksum": checksum,
        "status": "SUCCESS",
        "batch_id": batch_id,
        "record_count": len(rows),
        "applied_count": applied_count,
        "conflict_count": conflict_count,
        "invalid_count": invalid_count,
        "diagnostics": diagnostics,
    }
