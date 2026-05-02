from __future__ import annotations

import re
import time
from collections import defaultdict

from app.core.request_state import get_state_value


_rl_store: dict[str, list[float]] = defaultdict(list)


def _prune(key: str, window: float) -> list[float]:
    now = time.time()
    hits = [hit for hit in _rl_store.get(key, []) if now - hit < window]
    _rl_store[key] = hits
    return hits


def consume_rate_limit(key: str, limit: int, window: float) -> bool:
    hits = _prune(key, window)
    if len(hits) >= limit:
        return False
    hits.append(time.time())
    _rl_store[key] = hits
    return True


def client_ip() -> str:
    request = get_state_value("request")
    if request is None:
        return "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or "unknown"
    return getattr(getattr(request, "client", None), "host", None) or "unknown"


def validate_password_strength(password: str) -> tuple[bool, str]:
    normalized = str(password or "").strip()
    if not re.fullmatch(r"\d{4}", normalized):
        return False, "Le mot de passe doit contenir exactement 4 chiffres."
    return True, ""


def security_headers(response):
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    csp = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https:; img-src 'self' data: blob: https:; connect-src 'self' https:;"
    response.headers.setdefault("Content-Security-Policy", csp)
    return response
