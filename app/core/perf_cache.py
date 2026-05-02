from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from time import monotonic, time
from typing import Any, Callable, Hashable

from app.core.config import APP_DATA_DIR, DATABASE_URL

DB_PATH = APP_DATA_DIR / "database.db"
_CACHE: OrderedDict[tuple[Hashable, ...], dict[str, Any]] = OrderedDict()
_MAX_ENTRIES = 128
_POSTGRES_FINGERPRINT_SECONDS = 30


def _database_fingerprint() -> str:
    if DATABASE_URL.lower().startswith("postgres"):
        return f"postgres:{int(time() // _POSTGRES_FINGERPRINT_SECONDS)}"
    db_path = Path(DB_PATH)
    if not db_path.exists():
        return "sqlite:missing"
    parts = []
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if path.exists():
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return "sqlite:" + "|".join(parts)


def cached_result(
    key_parts: tuple[Hashable, ...],
    builder: Callable[[], Any],
    *,
    ttl_seconds: float = 5.0,
) -> Any:
    now = monotonic()
    cache_key = tuple(key_parts)
    fingerprint = _database_fingerprint()
    entry = _CACHE.get(cache_key)
    if entry and entry["expires_at"] > now and entry["fingerprint"] == fingerprint:
        _CACHE.move_to_end(cache_key)
        return entry["value"]

    value = builder()
    _CACHE[cache_key] = {
        "expires_at": now + max(0.5, float(ttl_seconds or 0)),
        "fingerprint": fingerprint,
        "value": value,
    }
    _CACHE.move_to_end(cache_key)
    while len(_CACHE) > _MAX_ENTRIES:
        _CACHE.popitem(last=False)
    return value


def invalidate_cache_domain(domain: str) -> int:
    prefix = str(domain or "").strip()
    if not prefix:
        return 0
    removed = 0
    for key in list(_CACHE.keys()):
        if key and str(key[0]).startswith(prefix):
            _CACHE.pop(key, None)
            removed += 1
    return removed


def invalidate_cache_domains(*domains: str) -> int:
    return sum(invalidate_cache_domain(domain) for domain in domains)


def cache_entry_count() -> int:
    return len(_CACHE)
