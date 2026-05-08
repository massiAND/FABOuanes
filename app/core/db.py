from __future__ import annotations

import os
import re
import sqlite3
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError


def _env_int(name: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except Exception:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _sqlite_pragmas() -> tuple[str, ...]:
    busy_timeout = _env_int("FAB_SQLITE_BUSY_TIMEOUT_MS", 15000, 1000, 60000)
    cache_kib = _env_int("FAB_SQLITE_CACHE_KIB", 131072, 8192, 1048576)
    mmap_size = _env_int("FAB_SQLITE_MMAP_BYTES", 536870912, 0, 2147483647)
    wal_autocheckpoint = _env_int("FAB_SQLITE_WAL_AUTOCHECKPOINT", 2000, 100, 10000)
    return (
        "PRAGMA foreign_keys = ON",
        f"PRAGMA busy_timeout = {busy_timeout}",
        "PRAGMA journal_mode = WAL",
        "PRAGMA synchronous = NORMAL",
        "PRAGMA temp_store = MEMORY",
        f"PRAGMA cache_size = -{cache_kib}",
        f"PRAGMA mmap_size = {mmap_size}",
        f"PRAGMA wal_autocheckpoint = {wal_autocheckpoint}",
        "PRAGMA analysis_limit = 1000",
        "PRAGMA optimize",
    )


class CompatRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class CompatCursor:
    def __init__(self, cursor, dialect: str, description=None):
        self.cursor = cursor
        self.dialect = dialect
        self.description = description or getattr(cursor, "description", None)

    def fetchall(self):
        rows = self.cursor.fetchall()
        return _wrap_rows(rows, self.description, self.dialect)

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return _wrap_rows([row], self.description, self.dialect)[0]

    def close(self):
        try:
            self.cursor.close()
        except Exception:
            pass

    @property
    def lastrowid(self):
        return getattr(self.cursor, "lastrowid", None)


class CompatConnection:
    def __init__(
        self,
        conn,
        dialect: str,
        on_close: Callable[[Any], None] | None = None,
        reconnect: Callable[[], Any] | None = None,
    ):
        self.conn = conn
        self.dialect = dialect
        self._on_close = on_close
        self._reconnect = reconnect
        self._closed = False
        if dialect == "sqlite":
            self.conn.row_factory = sqlite3.Row
            for pragma in _sqlite_pragmas():
                try:
                    cur = self.conn.execute(pragma)
                    cur.close()
                except sqlite3.DatabaseError:
                    pass

    def execute(self, query: str, params: tuple = ()):
        q = adapt_query(query, self.dialect)
        retried = False
        while True:
            cur = self.conn.cursor()
            try:
                cur.execute(q, params)
                return CompatCursor(cur, self.dialect)
            except Exception as exc:
                try:
                    cur.close()
                except Exception:
                    pass
                if self.dialect == "postgres" and not retried and _is_operational_error(exc):
                    self._reset_postgres_connection()
                    retried = True
                    continue
                raise

    def executescript(self, script: str):
        if self.dialect == "sqlite":
            return self.conn.executescript(script)
        for statement in split_sql_script(script):
            stmt = adapt_query(statement, self.dialect)
            if stmt.strip():
                cur = self.conn.cursor()
                try:
                    cur.execute(stmt)
                finally:
                    cur.close()
        return None

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._on_close is not None:
            self._on_close(self.conn)
            return
        self.conn.close()

    def _reset_postgres_connection(self) -> None:
        if self._reconnect is None:
            raise RuntimeError("Connexion PostgreSQL perdue et reconnexion indisponible.")
        try:
            invalidate = getattr(self.conn, "invalidate", None)
            if callable(invalidate):
                invalidate()
            else:
                self.conn.close()
        except Exception:
            pass
        self.conn = self._reconnect()


def _wrap_rows(rows, description, dialect):
    if dialect == "sqlite":
        return rows
    if not description:
        return rows
    cols = [c[0] for c in description]
    wrapped = []
    for row in rows:
        wrapped.append(CompatRow(OrderedDict(zip(cols, row))))
    return wrapped


_ENGINES: dict[str, Engine] = {}
_ENGINE_LOCK = Lock()


def sqlalchemy_database_url(database_url: str) -> str:
    url = str(database_url or "").strip()
    if url.startswith("postgresql://"):
        return "postgresql+pg8000://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+pg8000://" + url[len("postgres://") :]
    return url


def _resolve_database_url(database_url: str = "") -> str:
    raw = str(database_url or "").strip()
    if raw:
        return raw
    from app.core.config import settings

    return settings.database_url


def create_database_engine(database_url: str = "") -> Engine:
    raw_url = _resolve_database_url(database_url)
    engine_url = sqlalchemy_database_url(raw_url)
    if not raw_url.lower().startswith("postgres"):
        return create_engine(engine_url, future=True)
    return create_engine(
        engine_url,
        future=True,
        pool_pre_ping=True,
        pool_size=_env_int("FAB_PG_POOL_SIZE", 10, 1, 200),
        max_overflow=_env_int("FAB_PG_POOL_MAX_OVERFLOW", 10, 0, 500),
        pool_timeout=_env_int("FAB_PG_POOL_TIMEOUT", 30, 1, 300),
        pool_recycle=_env_int("FAB_PG_POOL_RECYCLE_SECONDS", 1800, 60, 86400),
    )


def get_database_engine(database_url: str = "") -> Engine:
    raw_url = _resolve_database_url(database_url)
    with _ENGINE_LOCK:
        engine = _ENGINES.get(raw_url)
        if engine is None:
            engine = create_database_engine(raw_url)
            _ENGINES[raw_url] = engine
        return engine


def _postgres_raw_connection(database_url: str):
    return get_database_engine(database_url).raw_connection()


def _is_operational_error(exc: Exception) -> bool:
    if isinstance(exc, (OperationalError, DBAPIError)):
        return True
    names = {type(exc).__name__.lower()}
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        names.add(type(cause).__name__.lower())
    return any(name in names for name in ("operationalerror", "interfaceerror", "databaseerror"))


def postgres_pool_status(database_url: str = "") -> dict[str, int | str]:
    raw_url = _resolve_database_url(database_url)
    if not raw_url.lower().startswith("postgres"):
        return {"engine": "sqlite"}
    pool = get_database_engine(raw_url).pool
    status: dict[str, int | str] = {"engine": "postgres"}
    for key, method_name in (
        ("size", "size"),
        ("checkedin", "checkedin"),
        ("checkedout", "checkedout"),
        ("overflow", "overflow"),
    ):
        method = getattr(pool, method_name, None)
        if callable(method):
            try:
                status[key] = int(method())
            except Exception:
                pass
    return status


def _sqlite_path_from_url(database_url: str, sqlite_path: str | Path | None) -> str | Path:
    raw = str(database_url or "").strip()
    if raw.lower().startswith("sqlite:///"):
        parsed = urlparse(raw)
        if parsed.netloc:
            return Path(f"//{parsed.netloc}{unquote(parsed.path)}")
        path = unquote(parsed.path)
        if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path)
    if sqlite_path is not None:
        return sqlite_path
    data_dir = os.environ.get("FAB_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "database.db"
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "FABOuanes" / "database.db"
    return Path.cwd() / "database.db"


def connect_database(database_url: str = "", sqlite_path: str | Path | None = None):
    raw_url = _resolve_database_url(database_url)
    if raw_url.lower().startswith("postgres"):
        return CompatConnection(
            _postgres_raw_connection(raw_url),
            "postgres",
            reconnect=lambda: _postgres_raw_connection(raw_url),
        )
    if not raw_url.lower().startswith("sqlite"):
        raise RuntimeError(f"DATABASE_URL non supportee: {raw_url}")
    from app.core.config import settings

    if not settings.desktop_mode:
        raise RuntimeError("SQLite est reserve au fallback desktop (FAB_DESKTOP=1).")
    resolved_sqlite_path = _sqlite_path_from_url(raw_url, sqlite_path)
    Path(resolved_sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    cached_statements = _env_int("FAB_SQLITE_CACHED_STATEMENTS", 512, 64, 4096)
    return CompatConnection(sqlite3.connect(str(resolved_sqlite_path), timeout=30, cached_statements=cached_statements), "sqlite")


def adapt_query(query: str, dialect: str) -> str:
    q = query
    if dialect == "sqlite":
        q = q.replace("CURRENT_TIMESTAMP::text", "CURRENT_TIMESTAMP")
    if dialect == "postgres":
        q = q.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        q = re.sub(r"\bAUTOINCREMENT\b", "", q, flags=re.I)
        q = q.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        q = re.sub(r"INSERT INTO ([^(\s]+) \(([^)]+)\) VALUES \(([^)]+)\)$", r"INSERT INTO \1 (\2) VALUES (\3) ON CONFLICT DO NOTHING", q, flags=re.I)
        q = q.replace("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP")
        q = q.replace("?", "%s")
    return q


def split_sql_script(script: str):
    return [s.strip() for s in script.split(";") if s.strip()]


def list_columns(conn: CompatConnection, table: str) -> set[str]:
    if conn.dialect == "sqlite":
        cur = conn.execute(f"PRAGMA table_info({table})")
        rows = cur.fetchall()
        cur.close()
        return {row[1] for row in rows}
    cur = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    rows = cur.fetchall()
    cur.close()
    return {row["column_name"] for row in rows}


def server_default_now() -> str:
    return "CURRENT_TIMESTAMP"
