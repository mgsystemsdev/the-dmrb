"""Validation helpers and checksum for import service."""
from __future__ import annotations

import hashlib
from typing import Optional

from services.imports.constants import (
    OUTCOME_APPLIED,
    OUTCOME_CONFLICT,
    OUTCOME_SKIPPED_OVERRIDE,
)


def _validation_status_from_outcome(outcome: str) -> str:
    if outcome == OUTCOME_APPLIED:
        return "OK"
    if outcome == OUTCOME_SKIPPED_OVERRIDE:
        return "SKIPPED_OVERRIDE"
    if outcome == OUTCOME_CONFLICT:
        return "CONFLICT"
    return "INVALID"


def _sha256_file(report_type: str, file_path: str) -> str:
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    payload = (report_type + "\n").encode() + file_bytes
    return hashlib.sha256(payload).hexdigest()


def _normalize_date_str(s: Optional[str]) -> Optional[str]:
    """Normalize to YYYY-MM-DD for comparison; None and empty -> None."""
    if not s or not str(s).strip():
        return None
    return str(s).strip()[:10]


def _normalize_status(s: Optional[str]) -> Optional[str]:
    """Normalize status for comparison; None and empty -> None; strip and lowercase."""
    if s is None:
        return None
    t = str(s).strip()
    return t.lower() if t else None
