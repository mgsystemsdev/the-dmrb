"""Report types and outcome constants for import service."""
from __future__ import annotations

from config.settings import get_settings

MOVE_OUTS = "MOVE_OUTS"
PENDING_MOVE_INS = "PENDING_MOVE_INS"
AVAILABLE_UNITS = "AVAILABLE_UNITS"
PENDING_FAS = "PENDING_FAS"
DMRB = "DMRB"

APP_SETTINGS = get_settings()
VALID_PHASES = tuple(int(p) for p in APP_SETTINGS.allowed_phases if str(p).strip().isdigit())

OUTCOME_APPLIED = "APPLIED"
OUTCOME_SKIPPED_OVERRIDE = "SKIPPED_OVERRIDE"
OUTCOME_CONFLICT = "CONFLICT"
