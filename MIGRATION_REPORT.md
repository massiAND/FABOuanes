# Migration Report — FABOuanes Flask -> FastAPI

## Scope

Migration of the existing FABOuanes codebase from Flask to a cleaner FastAPI architecture, with functional parity prioritized over rewrite purity.

## What was preserved

- same templates under `templates/`
- same static assets under `static/`
- same UI wording and visual contract
- same business services and repositories, now under `app/`
- same database schema in first pass
- same login flow and role semantics
- same desktop launcher concept
- same `/api/v1` surface for existing mobile/API consumers
- same print/report templates and rendering behavior

## What changed

### Platform

- new primary entrypoint: `app.main:app`
- FastAPI now owns:
  - startup/lifespan
  - sessions
  - HTML routers
  - JSON API routers
  - static mounting
- the global Flask WSGI fallback was removed in phase 2
- remaining compatibility routes are native FastAPI handlers

### Structure

- new `app/` package introduced
- HTTP responsibilities split into:
  - `app/web/*`
  - `app/api/*`
- platform moved into:
  - `app/core/*`
- business modules live in:
  - `app/services/*`
  - `app/repositories/*`

### Auth/session compatibility

- Starlette session middleware added
- auth cookie support introduced so server-rendered routes and API flows share the authenticated user

### Database/migrations

- SQLAlchemy Core engine introduced in `app/core/database.py`
- Alembic baseline added
- existing schema/bootstrap behavior preserved under `app/core/schema.py`

### Tests

- FastAPI coverage is organized under `pytest`
- new test split:
  - web
  - api
  - services
  - printing

### Windows delivery

- FastAPI-compatible launcher/build structure added
- dedicated `installer/windows/` kept as the canonical packaging path
- `deploy/windows/` kept as compatibility wrappers

## Flask Runtime Removal

The Flask runtime layer has been removed:

- `fabouanes/runtime_app.py` and `fabouanes/app_factory.py` were deleted
- `fabouanes/routes/*` was deleted
- the transitional Flask proxy modules under `app/` and `app/api/v1/` were deleted
- the old `fabouanes/` Flask package was removed from the active tree
- business logic was copied into `app/core`, `app/services`, and `app/repositories`

## Key compatibility shims

- `app.py`
- `wsgi.py`
- `run_prod.py`
- `deploy/windows/*.bat`
- root launch shims now point directly at `app.main:app`

## Current verified state

- FastAPI app imports and starts
- sessions work for server-rendered pages
- native FastAPI login works
- dashboard/client/sales/contacts/catalog smoke pages render
- API auth and mobile ping pass through native FastAPI routers
- no global WSGI fallback mount remains
- `pytest` suite passes

Current smoke result at migration time:

```text
22 passed
```

## Recommended next cleanup steps

1. Move the bundled seed database to `data/seed/` and stop referencing the root copy.
2. Clean the remaining Jinja/templating compatibility warnings.
3. Expand pytest coverage around:
   - document multi-lines
   - payments edge cases
   - production flows
   - admin backup flows

## Migration posture

This migration is intentionally conservative.

It is not a greenfield rewrite and it does not replace the metier with generic scaffolding. The project now has a maintainable FastAPI platform around the existing FABOuanes business code, with a clear path to finish the remaining route-by-route conversion safely.
