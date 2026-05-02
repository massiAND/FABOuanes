from __future__ import annotations

import os
import queue
import re
import sqlite3
from collections import OrderedDict
from contextlib import closing
from pathlib import Path
from urllib.parse import unquote, urlparse
from threading import Lock
from typing import Any, Callable

try:
    import pg8000.dbapi as pg_dbapi
except Exception:
    pg_dbapi = None


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
    def __init__(self, conn, dialect: str, on_close: Callable[[Any], None] | None = None):
        self.conn = conn
        self.dialect = dialect
        self._on_close = on_close
        self._closed = False
        if dialect == "sqlite":
            self.conn.row_factory = sqlite3.Row
            for pragma in (
                "PRAGMA foreign_keys = ON",
                "PRAGMA busy_timeout = 5000",
                "PRAGMA journal_mode = WAL",
                "PRAGMA synchronous = NORMAL",
                "PRAGMA temp_store = MEMORY",
                "PRAGMA cache_size = -50000",
                "PRAGMA mmap_size = 268435456",
                "PRAGMA wal_autocheckpoint = 1000",
            ):
                try:
                    self.conn.execute(pragma)
                except sqlite3.DatabaseError:
                    pass

    def execute(self, query: str, params: tuple = ()):
        q = adapt_query(query, self.dialect)
        cur = self.conn.cursor()
        cur.execute(q, params)
        return CompatCursor(cur, self.dialect)

    def executescript(self, script: str):
        if self.dialect == "sqlite":
            return self.conn.executescript(script)
        for statement in split_sql_script(script):
            stmt = adapt_query(statement, self.dialect)
            if stmt.strip():
                cur = self.conn.cursor()
                cur.execute(stmt)
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


def _postgres_connect(database_url: str):
    if pg_dbapi is None:
        raise RuntimeError("pg8000 n'est pas installé. Ajoute-le dans requirements.txt.")
    parsed = urlparse(database_url)
    return pg_dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=int(parsed.port or 5432),
        database=(parsed.path or "/")[1:],
    )


_PG_POOLS: dict[str, queue.LifoQueue] = {}
_PG_POOL_LOCK = Lock()


def _postgres_pool_size() -> int:
    try:
        return max(0, int(os.environ.get("FAB_PG_POOL_SIZE", "5") or "5"))
    except Exception:
        return 5


def _postgres_from_pool(database_url: str):
    pool_size = _postgres_pool_size()
    if pool_size <= 0:
        return _postgres_connect(database_url), None

    with _PG_POOL_LOCK:
        pool = _PG_POOLS.setdefault(database_url, queue.LifoQueue(maxsize=pool_size))

    try:
        conn = pool.get_nowait()
    except queue.Empty:
        conn = _postgres_connect(database_url)

    def release(pg_conn) -> None:
        try:
            pg_conn.rollback()
        except Exception:
            try:
                pg_conn.close()
            except Exception:
                pass
            return
        try:
            pool.put_nowait(pg_conn)
        except queue.Full:
            pg_conn.close()

    return conn, release


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
    if str(database_url or "").lower().startswith("postgres"):
        pg_conn, release = _postgres_from_pool(database_url)
        return CompatConnection(pg_conn, "postgres", on_close=release)
    resolved_sqlite_path = _sqlite_path_from_url(database_url, sqlite_path)
    Path(resolved_sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    return CompatConnection(sqlite3.connect(str(resolved_sqlite_path), timeout=30), "sqlite")


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
