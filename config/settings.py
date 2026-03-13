from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import streamlit as st


DEFAULT_ALLOWED_PHASES = ("5", "7", "8")


def get_setting(name: str, default=None):
    """Read from Streamlit secrets first, then fall back to environment variables."""
    try:
        if hasattr(st, "secrets") and name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    database_engine: str
    database_path: str
    database_url: str | None
    default_property_id: int
    allowed_phases: tuple[str, ...]
    timezone: str
    enable_db_writes_default: bool
    default_actor: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_allowed_phases(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_ALLOWED_PHASES
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    return parts or DEFAULT_ALLOWED_PHASES


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_db_path = _repo_root() / "data" / "cockpit.db"
    database_path = os.environ.get("COCKPIT_DB_PATH") or os.environ.get("DMRB_DATABASE_PATH") or str(default_db_path)
    database_engine = (get_setting("DB_ENGINE") or get_setting("DMRB_DATABASE_ENGINE") or "postgres").strip().lower()
    database_url = get_setting("DATABASE_URL") or None
    _writes_default = os.environ.get("DMRB_ENABLE_DB_WRITES_DEFAULT")
    if _writes_default is not None:
        enable_db_writes_default = _parse_bool(_writes_default, False)
    else:
        enable_db_writes_default = True
    # default_property_id must be an int; if misconfigured (e.g. set to a name),
    # fall back to 1 instead of raising and breaking imports.
    raw_default_pid = os.environ.get("DMRB_DEFAULT_PROPERTY_ID", "1")
    try:
        default_property_id = int(str(raw_default_pid).strip())
    except (ValueError, TypeError):
        default_property_id = 1

    return Settings(
        database_engine=database_engine,
        database_path=database_path,
        database_url=database_url,
        default_property_id=default_property_id,
        allowed_phases=_parse_allowed_phases(os.environ.get("DMRB_ALLOWED_PHASES")),
        timezone=(os.environ.get("DMRB_TIMEZONE") or "UTC").strip(),
        enable_db_writes_default=enable_db_writes_default,
        default_actor=(os.environ.get("DMRB_DEFAULT_ACTOR") or "manager").strip(),
    )
