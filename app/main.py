from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from app.api.router import router as api_router
from app.core.config import settings
from app.core.database import bootstrap_and_migrate, create_request_connection
from app.core.logging import configure_logging
from app.core.request_state import push_request_state, reset_request_state, set_state_value
from app.core.runtime_paths import ensure_runtime_dirs, paths
from app.core.security import security_headers
from app.services.backup_service import start_background_services
from app.web.deps import ensure_csrf_token, load_user_from_session
from app.web.router import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_runtime_dirs()
    configure_logging()
    bootstrap_and_migrate()
    start_background_services(app)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/static/"):
            response = await call_next(request)
            return security_headers(response)

        db = create_request_connection()
        token = push_request_state(
            request=request,
            db=db,
            session=request.session,
            request_id=secrets.token_hex(12),
            audit_source="api" if request.url.path.startswith("/api/v1/") else "web",
            user=None,
            g=SimpleNamespace(user=None),
        )
        try:
            ensure_csrf_token(request)
            user = load_user_from_session(request)
            request.state.user = user
            set_state_value("user", user)
            set_state_value("g", SimpleNamespace(user=user))
            response = await call_next(request)
        finally:
            try:
                db.close()
            except Exception:
                pass
            reset_request_state(token)
        return security_headers(response)


app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or secrets.token_hex(32),
    session_cookie="fabouanes_session",
    same_site="lax",
    https_only=settings.session_cookie_secure,
    max_age=settings.session_max_age,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    if isinstance(exc, ValueError):
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"error": "Erreur interne."}, status_code=500)


app.mount("/static", StaticFiles(directory=str(paths.static_dir)), name="static")
app.include_router(web_router)
app.include_router(api_router)
