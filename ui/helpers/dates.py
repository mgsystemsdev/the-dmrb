"""Date parsing, coercion, and formatting for UI. No Streamlit dependency."""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd


def parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def to_date(v) -> Optional[date]:
    """Coerce value (date, Timestamp, str, None, NaT) to plain date or None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "date") and callable(v.date) and type(v) is not date:
        result = v.date()
        try:
            if pd.isna(result):
                return None
        except (TypeError, ValueError):
            pass
        return result
    if isinstance(v, date):
        return v
    return parse_date(str(v))


def dates_equal(a, b) -> bool:
    """Compare two date-like values for equality (handles None, NaT, date, Timestamp)."""
    da = to_date(a)
    db = to_date(b)
    return da == db


def fmt_date(s, default="—"):
    """Format date string as MM/DD/YYYY."""
    if not s:
        return default
    try:
        d = date.fromisoformat(str(s)[:10])
        return d.strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return default


def parse_date_for_input(s):
    """Return date or today for st.date_input."""
    if not s:
        return date.today()
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return date.today()


def iso_to_date(value: str) -> date:
    return date.fromisoformat(value)
