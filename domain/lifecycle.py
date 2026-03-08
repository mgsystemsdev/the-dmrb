from datetime import date, timedelta
from typing import Optional

CANCELED = "CANCELED"
CLOSED = "CLOSED"
STABILIZATION = "STABILIZATION"
MOVE_IN_COMPLETE = "MOVE_IN_COMPLETE"
SMI = "SMI"
VACANT = "VACANT"
NOTICE_SMI = "NOTICE_SMI"
NOTICE = "NOTICE"


def _parse_iso_date(value) -> Optional[date]:
    """
    Parse YYYY-MM-DD (or full ISO datetime string) into a date.
    Accepts date passthrough; returns None on missing/invalid inputs.
    """
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        s = str(value).strip()
        if len(s) < 10:
            return None
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def effective_move_out_date(row: dict) -> Optional[date]:
    """
    Effective anchor date for lifecycle/SLA evaluation.

    Priority:
    1) Manager manual override (move_out_manual_override_at + move_out_date) — manager said so, wins.
    2) Legal confirmed (legal_confirmation_source → confirmed_move_out_date).
    3) Scheduled (scheduled_move_out_date).
    4) Legacy/fallback (move_out_date).
    """
    manual_override_at = row.get("move_out_manual_override_at")
    manual_move_out = _parse_iso_date(row.get("move_out_date"))
    if manual_override_at is not None and manual_move_out is not None:
        return manual_move_out

    legal_source = row.get("legal_confirmation_source")
    if legal_source is not None:
        legal_source = str(legal_source).strip() or None
    if legal_source:
        return _parse_iso_date(row.get("confirmed_move_out_date"))
    scheduled = _parse_iso_date(row.get("scheduled_move_out_date"))
    if scheduled is not None:
        return scheduled
    return manual_move_out


def derive_lifecycle_phase(
    *,
    move_out_date: Optional[date],
    move_in_date: Optional[date],
    closed_at: Optional[str],
    canceled_at: Optional[str],
    today: date,
) -> str:
    if move_out_date is None:
        return NOTICE

    if canceled_at is not None:
        return CANCELED
    if closed_at is not None:
        return CLOSED

    if move_in_date is not None:
        if today > move_in_date and today <= move_in_date + timedelta(days=14):
            return STABILIZATION
        if today >= move_in_date and not (today > move_in_date + timedelta(days=14)):
            return MOVE_IN_COMPLETE
        if today >= move_out_date and today < move_in_date:
            return SMI

    if today >= move_out_date:
        if move_in_date is None or today < move_in_date:
            return VACANT

    if today < move_out_date:
        if move_in_date is not None and today < move_in_date:
            return NOTICE_SMI
        return NOTICE

    return NOTICE


def derive_nvm(phase: str) -> str:
    """Lifecycle display label from phase constant."""
    _PHASE_TO_NVM = {
        NOTICE: "Notice",
        NOTICE_SMI: "Notice + SMI",
        VACANT: "Vacant",
        SMI: "SMI",
        MOVE_IN_COMPLETE: "Move-In",
        STABILIZATION: "Move-In",
    }
    return _PHASE_TO_NVM.get(phase, "—")
