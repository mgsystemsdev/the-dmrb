from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from db.errors import DatabaseError, DatabaseIntegrityError, DatabaseOperationalError


def _is_quoted(sql: str, index: int) -> bool:
    single = False
    double = False
    i = 0
    while i < index:
        ch = sql[i]
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        i += 1
    return single or double


def qmark_to_percent(sql: str) -> str:
    out = []
    for idx, ch in enumerate(sql):
        if ch == "?" and not _is_quoted(sql, idx):
            out.append("%s")
        else:
            out.append(ch)
    return "".join(out)


def classify_db_error(exc: Exception) -> Exception:
    name = exc.__class__.__name__
    if "IntegrityError" in name:
        return DatabaseIntegrityError(str(exc))
    if "OperationalError" in name or "ProgrammingError" in name or "InterfaceError" in name:
        return DatabaseOperationalError(str(exc))
    return DatabaseError(str(exc))


@dataclass
class DatabaseConfig:
    engine: str
    sqlite_path: str
    postgres_url: str | None = None


class ConnectionWrapper:
    def __init__(self, raw: Any, engine: str):
        self._raw = raw
        self.engine = engine

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        if self.engine == "postgres":
            try:
                sql = qmark_to_percent(sql)
                if params is None:
                    return self._raw.execute(sql)
                return self._raw.execute(sql, tuple(params))
            except Exception as exc:  # pragma: no cover - backend-specific branches
                raise classify_db_error(exc) from exc
        if params is None:
            return self._raw.execute(sql)
        return self._raw.execute(sql, tuple(params))

    def executemany(self, sql: str, seq_of_params: Iterable[Iterable[Any]]):
        if self.engine == "postgres":
            try:
                sql = qmark_to_percent(sql)
                return self._raw.executemany(sql, [tuple(p) for p in seq_of_params])
            except Exception as exc:  # pragma: no cover - backend-specific branches
                raise classify_db_error(exc) from exc
        return self._raw.executemany(sql, [tuple(p) for p in seq_of_params])

    def executescript(self, sql: str):
        if self.engine == "sqlite":
            return self._raw.executescript(sql)
        try:
            with self._raw.cursor() as cur:
                cur.execute(sql)
            return None
        except Exception as exc:  # pragma: no cover - backend-specific branches
            raise classify_db_error(exc) from exc

    def inserted_id(self, table: str, id_column: str, cursor: Any | None = None) -> int:
        if self.engine == "sqlite":
            if cursor is not None:
                lastrowid = getattr(cursor, "lastrowid", None)
                if lastrowid is not None:
                    return int(lastrowid)
            row = self.execute("SELECT last_insert_rowid()").fetchone()
            return int(row[0])
        # Postgres: lastval() returns the last nextval() in this session (works after INSERT with IDENTITY/SERIAL)
        row = self.execute("SELECT lastval()").fetchone()
        if isinstance(row, dict):
            return int(next(iter(row.values())))
        return int(row[0])

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()

    def cursor(self):
        return self._raw.cursor()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._raw, item)


class BaseAdapter:
    engine = "sqlite"

    def connect(self, config: DatabaseConfig) -> ConnectionWrapper:
        raise NotImplementedError
