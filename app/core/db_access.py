from __future__ import annotations

import os
import re
from time import monotonic
from contextlib import contextmanager

from app.core.config import DATABASE_URL, APP_DATA_DIR
from app.core.db import connect_database
from app.core.perf_cache import invalidate_cache_domains
from app.core.request_state import ensure_request_state, get_request_state

DB_PATH = APP_DATA_DIR / "database.db"
_SLOW_SQL_THRESHOLD_MS = float(os.environ.get("FAB_SLOW_SQL_MS", "100") or "100")

def get_db():
    state = get_request_state()
    if state is not None and getattr(state, "db", None) is not None:
        return state.db
    state = ensure_request_state()
    if getattr(state, "db", None) is None:
        state.db = connect_database(_database_url(), DB_PATH)
    return state.db


def _database_url() -> str:
    try:
        from app.core.config import settings

        return settings.database_url
    except Exception:
        return DATABASE_URL


def _tx_depth() -> int:
    state = get_request_state()
    if state is not None:
        return int(getattr(state, "db_tx_depth", 0) or 0)
    return 0


def _set_tx_depth(value: int) -> None:
    state = ensure_request_state()
    state.db_tx_depth = value

def _route_label() -> str:
    state = get_request_state()
    state_request = getattr(state, "request", None) if state is not None else None
    if state_request is None:
        return ""
    route = state_request.scope.get("route")
    endpoint = getattr(route, "name", "") or state_request.scope.get("endpoint_name", "")
    path = state_request.url.path
    return f"{state_request.method} {path}" if not endpoint else f"{state_request.method} {path} ({endpoint})"


def _record_performance_event(kind: str, name: str, elapsed_ms: float, details: str = "") -> None:
    if "performance_logs" in name.lower() or elapsed_ms <= 0:
        return
    try:
        db = get_db()
        cur = db.execute(
            """
            INSERT INTO performance_logs (kind, name, elapsed_ms, route, details, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (kind, name[:240], float(elapsed_ms), _route_label(), details[:1000]),
        )
        cur.close()
        if _tx_depth() == 0:
            db.commit()
    except Exception:
        pass


def _record_sql_timing(query: str, params: tuple, elapsed_ms: float) -> None:
    if elapsed_ms < _SLOW_SQL_THRESHOLD_MS:
        return
    normalized = " ".join(str(query or "").split())
    _record_performance_event("sql", normalized, elapsed_ms, f"params={len(params or ())}")


def _invalidate_after_write(query: str) -> None:
    q = f" {str(query or '').lower()} "
    if not any(token in q for token in (" insert ", " update ", " delete ", " replace ")):
        return
    domains: set[str] = set()
    if any(table in q for table in (" clients", " sales", " raw_sales", " payments")):
        domains.update({"clients", "client_detail", "dashboard", "payments", "sales", "transactions", "contacts"})
    if any(table in q for table in (" raw_materials", " finished_products")):
        domains.update({"catalog", "dashboard", "sales", "purchases", "productions", "transactions"})
    if " purchases" in q or " suppliers" in q:
        domains.update({"purchases", "transactions", "contacts", "dashboard"})
    if " production_batches" in q or " production_batch_items" in q:
        domains.update({"productions", "dashboard", "sales", "catalog"})
    if any(table in q for table in (" users", " backup_jobs", " audit_logs", " activity_logs", " system_logs", " error_logs")):
        domains.add("admin")
    if domains:
        invalidate_cache_domains(*domains)


def query_db(query: str, params: tuple = (), one: bool = False):
    started = monotonic()
    cur = get_db().execute(query, params)
    try:
        if one:
            result = cur.fetchone()
        else:
            result = cur.fetchall()
        _record_sql_timing(query, params, (monotonic() - started) * 1000.0)
        return result
    finally:
        cur.close()

def execute_db(query: str, params: tuple = ()) -> int:
    db = get_db()
    started = monotonic()
    cur = db.execute(query, params)
    if _tx_depth() == 0:
        db.commit()
    last_id = cur.lastrowid
    cur.close()
    if not last_id and getattr(db, "dialect", "sqlite") == "postgres":
        last_id = _postgres_last_insert_id(db, query)
    _record_sql_timing(query, params, (monotonic() - started) * 1000.0)
    _invalidate_after_write(query)
    return int(last_id or 0)


def _postgres_last_insert_id(db, query: str) -> int:
    match = re.match(r"\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", str(query or ""), flags=re.I)
    if not match:
        return 0
    table = match.group(1)
    if table in {"app_settings", "schema_migrations"}:
        return 0
    try:
        cur = db.execute("SELECT currval(pg_get_serial_sequence(?, 'id')) AS id", (table,))
        row = cur.fetchone()
        cur.close()
        return int(row["id"] if row else 0)
    except Exception:
        return 0


def explain_query_plan(query: str, params: tuple = ()) -> list[dict]:
    db = get_db()
    prefix = "EXPLAIN QUERY PLAN " if getattr(db, "dialect", "sqlite") == "sqlite" else "EXPLAIN "
    cur = db.execute(prefix + query, params)
    try:
        rows = cur.fetchall()
        return [dict(row) if hasattr(row, "keys") else {"plan": str(row)} for row in rows]
    finally:
        cur.close()

@contextmanager
def db_transaction():
    db = get_db()
    previous_depth = _tx_depth()
    _set_tx_depth(previous_depth + 1)
    try:
        yield db
    except Exception:
        if previous_depth == 0:
            try:
                db.rollback()
            except Exception:
                pass
        raise
    else:
        if previous_depth == 0:
            db.commit()
    finally:
        _set_tx_depth(previous_depth)

def get_setting(key: str, default: str = '') -> str:
    try:
        row = query_db('SELECT value FROM app_settings WHERE key = ?', (key,), one=True)
        return row['value'] if row and row['value'] is not None else default
    except Exception:
        return default

def set_setting(key: str, value: str) -> None:
    execute_db('INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP', (key, value))
