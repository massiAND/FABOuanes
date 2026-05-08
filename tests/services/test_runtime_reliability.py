from __future__ import annotations

import os
import subprocess
import sys

import pytest

from app.core.config import validate_single_worker_runtime
from app.core.db import postgres_pool_status
from app.core.perf_cache import bump_cache_generation, cached_result, clear_cache


def _run_config_probe(env_updates: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_updates)
    return subprocess.run(
        [sys.executable, "-c", "import app.core.config as c; print(c.DATABASE_URL)"],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_server_mode_requires_database_url():
    result = _run_config_probe({"DATABASE_URL": "", "FAB_DESKTOP": "0"})
    assert result.returncode != 0
    assert "DATABASE_URL PostgreSQL est requis" in (result.stderr + result.stdout)


def test_desktop_mode_allows_sqlite_fallback():
    result = _run_config_probe({"DATABASE_URL": "", "FAB_DESKTOP": "1"})
    assert result.returncode == 0
    assert "sqlite:///" in result.stdout


def test_multi_worker_runtime_is_rejected_without_override(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.delenv("FAB_ALLOW_MULTI_WORKER", raising=False)
    with pytest.raises(RuntimeError, match="1 seul worker"):
        validate_single_worker_runtime()


def test_cache_generation_invalidates_cached_value():
    clear_cache()
    calls = {"count": 0}

    def build_value():
        calls["count"] += 1
        return calls["count"]

    assert cached_result(("runtime_test",), build_value, ttl_seconds=60) == 1
    assert cached_result(("runtime_test",), build_value, ttl_seconds=60) == 1
    bump_cache_generation()
    assert cached_result(("runtime_test",), build_value, ttl_seconds=60) == 2


def test_pool_status_reports_sqlite_in_sqlite_mode():
    assert postgres_pool_status()["engine"] == "sqlite"
