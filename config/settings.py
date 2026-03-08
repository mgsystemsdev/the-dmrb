from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_ALLOWED_PHASES = ("5", "7", "8")


@dataclass(frozen=True)
class Settings:
    database_engine: str
    database_path: str
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
    return Settings(
        database_engine=(os.environ.get("DMRB_DATABASE_ENGINE") or "sqlite").strip().lower(),
        database_path=database_path,
        default_property_id=int(os.environ.get("DMRB_DEFAULT_PROPERTY_ID", "1")),
        allowed_phases=_parse_allowed_phases(os.environ.get("DMRB_ALLOWED_PHASES")),
        timezone=(os.environ.get("DMRB_TIMEZONE") or "UTC").strip(),
        enable_db_writes_default=_parse_bool(os.environ.get("DMRB_ENABLE_DB_WRITES_DEFAULT"), False),
        default_actor=(os.environ.get("DMRB_DEFAULT_ACTOR") or "manager").strip(),
    )
