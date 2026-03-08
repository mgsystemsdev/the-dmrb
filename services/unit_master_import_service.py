"""
Unit Master Bootstrap Import: structure-only import from Units.csv.
Writes only to unit (and phase/building hierarchy). Does NOT touch turnover, task, risk, sla.
Uses canonical unit_identity parser. Idempotent: checksum-based NO_OP, upsert by identity.
Logs import_batch + import_row for full audit trail (same pattern as import_service).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from db import repository
from domain import unit_identity

REPORT_TYPE = "UNIT_MASTER"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(file_path: str) -> str:
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    payload = (REPORT_TYPE + "\n").encode() + file_bytes
    return hashlib.sha256(payload).hexdigest()


def _parse_units_csv(file_path: str) -> list[dict[str, Any]]:
    """
    Parse Units.csv: skip metadata rows (first 4), header on line 5.
    Columns used: Unit, Floor Plan, Gross Sq. Ft.
    Returns list of dicts with: unit_raw, unit_norm, phase_code, building_code, unit_number,
    unit_identity_key, floor_plan, gross_sq_ft, parse_error (if any).
    Rows that fail parse have parse_error set and are excluded from upsert (or fail in strict).
    """
    df = pd.read_csv(file_path, skiprows=4)
    df.columns = df.columns.str.strip()
    required = ["Unit", "Floor Plan", "Gross Sq. Ft."]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Unit Master CSV missing required column: {c}")
    rows = []
    for _, r in df.iterrows():
        unit_raw = str(r["Unit"]).strip() if pd.notna(r["Unit"]) else ""
        floor_plan = str(r["Floor Plan"]).strip() if pd.notna(r["Floor Plan"]) else ""
        try:
            gross_val = r["Gross Sq. Ft."]
            if pd.isna(gross_val):
                gross_sq_ft = None
            else:
                gross_sq_ft = int(float(gross_val))
        except (ValueError, TypeError):
            gross_sq_ft = None
        raw_json = json.dumps({
            "Unit": unit_raw,
            "Floor Plan": floor_plan,
            "Gross Sq. Ft.": gross_sq_ft,
        })
        if not unit_raw:
            rows.append({
                "unit_raw": unit_raw,
                "unit_norm": "",
                "phase_code": "",
                "building_code": "",
                "unit_number": "",
                "unit_identity_key": "",
                "floor_plan": floor_plan,
                "gross_sq_ft": gross_sq_ft,
                "raw_json": raw_json,
                "parse_error": "Unit is blank",
            })
            continue
        unit_norm = unit_identity.normalize_unit_code(unit_raw)
        if not unit_norm:
            rows.append({
                "unit_raw": unit_raw,
                "unit_norm": "",
                "phase_code": "",
                "building_code": "",
                "unit_number": "",
                "unit_identity_key": "",
                "floor_plan": floor_plan,
                "gross_sq_ft": gross_sq_ft,
                "raw_json": raw_json,
                "parse_error": "Unit normalizes to empty",
            })
            continue
        try:
            phase_code, building_code, unit_number = unit_identity.parse_unit_parts(unit_norm)
            unit_identity_key = unit_identity.compose_identity_key(phase_code, building_code, unit_number)
        except ValueError as e:
            rows.append({
                "unit_raw": unit_raw,
                "unit_norm": unit_norm,
                "phase_code": "",
                "building_code": "",
                "unit_number": "",
                "unit_identity_key": "",
                "floor_plan": floor_plan,
                "gross_sq_ft": gross_sq_ft,
                "raw_json": raw_json,
                "parse_error": str(e),
            })
            continue
        rows.append({
            "unit_raw": unit_raw,
            "unit_norm": unit_norm,
            "phase_code": phase_code,
            "building_code": building_code,
            "unit_number": unit_number,
            "unit_identity_key": unit_identity_key,
            "floor_plan": floor_plan or None,
            "gross_sq_ft": gross_sq_ft,
            "raw_json": raw_json,
            "parse_error": None,
        })
    return rows


def _write_import_row(
    conn,
    batch_id: int,
    row: dict,
    validation_status: str,
    conflict_flag: int = 0,
    conflict_reason: Optional[str] = None,
) -> None:
    repository.insert_import_row(conn, {
        "batch_id": batch_id,
        "raw_json": row.get("raw_json", "{}"),
        "unit_code_raw": row.get("unit_raw", ""),
        "unit_code_norm": row.get("unit_norm", ""),
        "move_out_date": None,
        "move_in_date": None,
        "validation_status": validation_status,
        "conflict_flag": conflict_flag,
        "conflict_reason": conflict_reason,
    })


def run_unit_master_import(
    conn,
    file_path: str,
    property_id: int,
    *,
    strict_mode: bool = False,
) -> dict[str, Any]:
    """
    Run Unit Master Bootstrap Import. Structure-only: writes only to unit (and phase/building).
    strict_mode=True: fail row if unit not found; no creates.
    strict_mode=False: get-or-create unit via hierarchy resolver; upsert floor_plan, gross_sq_ft.
    Logs import_batch and import_row for audit trail. Checksum idempotency (NO_OP on duplicate).
    Caller owns connection and transaction; this module does not commit.
    """
    import os
    source_file_name = os.path.basename(file_path)
    checksum = _sha256_file(file_path)
    now_iso = _now_iso()

    existing = repository.get_import_batch_by_checksum(conn, checksum)
    if existing is not None:
        return {
            "status": "NO_OP",
            "batch_id": existing["batch_id"],
            "applied_count": 0,
            "conflict_count": 0,
            "error_count": 0,
            "errors": [],
            "record_count": 0,
        }

    try:
        rows = _parse_units_csv(file_path)
    except Exception:
        repository.insert_import_batch(conn, {
            "report_type": REPORT_TYPE,
            "checksum": checksum,
            "source_file_name": source_file_name,
            "record_count": 0,
            "status": "FAILED",
            "imported_at": now_iso,
        })
        raise

    batch_id = repository.insert_import_batch(conn, {
        "report_type": REPORT_TYPE,
        "checksum": checksum,
        "source_file_name": source_file_name,
        "record_count": len(rows),
        "status": "SUCCESS",
        "imported_at": now_iso,
    })

    applied_count = 0
    conflict_count = 0
    error_count = 0
    errors: list[str] = []

    for i, row in enumerate(rows):
        if row.get("parse_error"):
            error_count += 1
            errors.append(f"Row {i + 1}: {row['parse_error']} (unit={row.get('unit_raw', '')!r})")
            _write_import_row(conn, batch_id, row, "INVALID", conflict_flag=1, conflict_reason=row["parse_error"])
            continue
        unit_identity_key = row["unit_identity_key"]
        if strict_mode:
            existing_unit = repository.get_unit_by_identity_key(
                conn, property_id=property_id, unit_identity_key=unit_identity_key
            )
            if existing_unit is None:
                conflict_count += 1
                errors.append(f"Row {i + 1}: Unit not found (strict_mode): {unit_identity_key!r}")
                _write_import_row(conn, batch_id, row, "CONFLICT", conflict_flag=1, conflict_reason="UNIT_NOT_FOUND_STRICT")
                continue
            updates = {}
            if row.get("floor_plan") is not None:
                updates["floor_plan"] = row["floor_plan"]
            if row.get("gross_sq_ft") is not None:
                updates["gross_sq_ft"] = row["gross_sq_ft"]
            if row["unit_raw"] and row["unit_raw"] != existing_unit.get("unit_code_raw"):
                updates["unit_code_raw"] = row["unit_raw"]
            if updates:
                repository.update_unit_fields(conn, existing_unit["unit_id"], updates)
            applied_count += 1
            _write_import_row(conn, batch_id, row, "OK")
        else:
            unit_row = repository.resolve_unit(
                conn,
                property_id=property_id,
                phase_code=row["phase_code"],
                building_code=row["building_code"],
                unit_number=row["unit_number"],
                unit_code_raw=row["unit_raw"],
                unit_code_norm=row["unit_norm"],
                unit_identity_key=unit_identity_key,
                floor_plan=row.get("floor_plan"),
                gross_sq_ft=row.get("gross_sq_ft"),
            )
            updates = {}
            if row.get("floor_plan") is not None and row["floor_plan"] != unit_row.get("floor_plan"):
                updates["floor_plan"] = row["floor_plan"]
            if row.get("gross_sq_ft") is not None and row["gross_sq_ft"] != unit_row.get("gross_sq_ft"):
                updates["gross_sq_ft"] = row["gross_sq_ft"]
            if row["unit_raw"] and row["unit_raw"] != unit_row.get("unit_code_raw"):
                updates["unit_code_raw"] = row["unit_raw"]
            if updates:
                repository.update_unit_fields(conn, unit_row["unit_id"], updates)
            applied_count += 1
            _write_import_row(conn, batch_id, row, "OK")

    status = "FAILED" if (strict_mode and conflict_count > 0) or error_count > 0 else "SUCCESS"
    return {
        "status": status,
        "batch_id": batch_id,
        "applied_count": applied_count,
        "conflict_count": conflict_count,
        "error_count": error_count,
        "errors": errors,
        "record_count": len(rows),
    }
