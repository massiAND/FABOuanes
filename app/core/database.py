from __future__ import annotations

import importlib
import sys
from pathlib import Path
from threading import RLock

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.core.runtime_paths import ensure_runtime_dirs
from app.core.schema_bootstrap import bootstrap_schema
from app.core.db import connect_database, get_database_engine, sqlalchemy_database_url


def create_sqlalchemy_engine() -> Engine:
    return get_database_engine(settings.database_url)


engine = create_sqlalchemy_engine()
_BOOTSTRAP_LOCK = RLock()
_BOOTSTRAPPED = False


def create_request_connection():
    ensure_runtime_dirs()
    return connect_database(settings.database_url)


def _load_alembic():
    original_sys_path = list(sys.path)
    base_dir = str(settings.base_dir.resolve())
    try:
        sys.path = [entry for entry in sys.path if str(Path(entry).resolve()) != base_dir]
        command = importlib.import_module("alembic.command")
        config_mod = importlib.import_module("alembic.config")
        return command, config_mod.Config
    finally:
        sys.path = original_sys_path


def _alembic_config():
    _, Config = _load_alembic()
    cfg = Config(str(settings.base_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_database_url(settings.database_url))
    return cfg


def _alembic_version_exists() -> bool:
    try:
        return inspect(engine).has_table("alembic_version")
    except Exception:
        return False


def run_alembic_upgrade() -> None:
    if not (settings.base_dir / "alembic.ini").exists():
        return
    command, _ = _load_alembic()
    cfg = _alembic_config()
    if not _alembic_version_exists():
        command.stamp(cfg, "base")
    command.upgrade(cfg, "head")


def bootstrap_and_migrate() -> None:
    global _BOOTSTRAPPED
    with _BOOTSTRAP_LOCK:
        if _BOOTSTRAPPED:
            return
        ensure_runtime_dirs()
        bootstrap_schema()
        run_alembic_upgrade()
        _BOOTSTRAPPED = True


def healthcheck() -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
