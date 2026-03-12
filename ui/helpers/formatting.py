"""Formatting utilities for UI. No DB or Streamlit dependency."""
from __future__ import annotations

import unicodedata


def normalize_label(s: str) -> str:
    """Normalize label for comparison/lookup; avoid KeyError from unicode or whitespace differences."""
    return unicodedata.normalize("NFKC", (s or "").strip())


def normalize_enum(s) -> str:
    """Normalize DB enum value for mapping lookup; case- and whitespace-safe."""
    if not isinstance(s, str):
        return ""
    return unicodedata.normalize("NFKC", s).strip().upper()


def safe_index(options: list, value, default: int = 0) -> int:
    """Index of value in options, or default if missing; avoids ValueError from .index()."""
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default


def operational_state_to_badge(operational_state: str) -> str:
    badge_map = {
        "On Notice - Scheduled": "On Notice - Scheduled",
        "On Notice": "On Notice",
        "Scheduled to Move In": "Scheduled to Move In",
        "Move-In Risk": "Move-In Risk",
        "QC Hold": "QC Hold",
        "Work Stalled": "Work Stalled",
        "Needs Attention": "Needs Attention",
        "In Progress": "In Progress",
        "Pending Start": "Pending Start",
        "Apartment Ready": "Apartment Ready",
        "Out of Scope": "Out of Scope",
    }
    return badge_map.get(operational_state or "", operational_state or "")


def get_attention_badge(row: dict) -> str:
    """Use row's attention_badge if present, else derive from operational_state."""
    if row.get("attention_badge"):
        return row["attention_badge"]
    return operational_state_to_badge(row.get("operational_state", ""))
