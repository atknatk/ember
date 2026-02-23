# Architect Handoff: Project Setup

**Date**: 2026-02-23
**Agent**: architect
**Status**: COMPLETE
**Feature ID**: P01-01
**GitHub Issue**: #3
**Layer**: backend

---

## What Was Designed

The complete FastAPI project scaffold for Ember backend, including directory structure with all required subdirectories (routes, services, models, schemas, utils, core, db), the application factory with health endpoint, configuration system using pydantic-settings with AWS Secrets Manager integration, async SQLAlchemy engine and session factory, Alembic migration infrastructure, multi-stage Dockerfile, Docker Compose for local development with PostgreSQL, and ruff/mypy/pytest configuration. This is the foundation upon which all subsequent backend features are built.

## Spec Location

`shared/feature-specs/project-setup.md`

## Key Decisions

- **Health endpoint at `/api/v1/health`**: Public (no auth), does not touch database or external services. Used by ECS Fargate health checks. Fast and reliable even during DB failover.
- **`/api/v1/` prefix applied globally**: All routes are mounted under this prefix in `main.py`. Matches the base URL in `docs/04-veri-api.md`.
- **`schemas/` directory added**: The GitHub issue listed `{routes,services,models,utils,core}` but `docs/standards/backend.md` Section 1 mandates a `schemas/` directory for Pydantic request/response models. Added to avoid a follow-up refactor.
- **`db/` as subdirectory of `app/`**: Holds `session.py` and `migrations/`. Follows `docs/standards/backend.md` exactly.
- **Alembic configured but no migrations generated**: Infrastructure is ready so P01-02 (database models) can create migrations immediately.
- **`get_current_user` dependency stubbed**: Returns 501 Not Implemented. Will be implemented in P01-03 (user auth).
- **Non-root Docker user**: Container runs as user `ember`, not root. Security best practice for ECS Fargate.
- **Named Docker volume for PostgreSQL**: Avoids permission issues across macOS/Linux and persists data across `docker compose down`/`up` cycles.

## Assumptions Made

- The `backend/app/` directory and its subdirectories (`routes/`, `services/`, `models/`, `utils/`) already exist as empty directories with `.gitkeep` files from the initial scaffold commit. The `core/`, `schemas/`, and `db/` directories need to be created.
- The `backend/tests/` directory exists but is empty.
- Python 3.12 is the minimum version. No Python 3.11 compatibility is needed.
- PostgreSQL 16 is used locally via Docker (matching the AWS RDS version in `docs/09-dagitim.md`).
- Package versions in `requirements.txt` use range pins (e.g., `>=0.115.0,<1.0.0`) for reproducibility while allowing patch updates.

## Dependencies

- **Requires**: nothing (this is the first feature)
- **Blocks**: All subsequent backend features (P01-02 through P01-08 and beyond)

## File Manifest

```
Backend:
  CREATE  backend/app/__init__.py
  CREATE  backend/app/main.py
  CREATE  backend/app/config.py
  CREATE  backend/app/dependencies.py
  CREATE  backend/app/routes/__init__.py
  CREATE  backend/app/routes/health.py
  CREATE  backend/app/services/__init__.py
  CREATE  backend/app/models/__init__.py
  CREATE  backend/app/models/base.py
  CREATE  backend/app/schemas/__init__.py
  CREATE  backend/app/schemas/health.py
  CREATE  backend/app/db/__init__.py
  CREATE  backend/app/db/session.py
  CREATE  backend/app/db/migrations/env.py
  CREATE  backend/app/db/migrations/script.py.mako
  CREATE  backend/app/db/migrations/versions/.gitkeep
  CREATE  backend/app/utils/__init__.py
  CREATE  backend/app/core/__init__.py
  CREATE  backend/app/core/logging.py
  CREATE  backend/pyproject.toml
  CREATE  backend/requirements.txt
  CREATE  backend/requirements-dev.txt
  CREATE  backend/.env.example
  CREATE  backend/alembic.ini
  CREATE  backend/Dockerfile
  CREATE  backend/docker-compose.yml
  CREATE  backend/.dockerignore
  CREATE  backend/.gitignore
  CREATE  backend/tests/__init__.py
  CREATE  backend/tests/conftest.py
  CREATE  backend/tests/test_health.py
  CREATE  backend/tests/test_config.py
  CREATE  backend/tests/test_app.py

Shared:
  CREATE  shared/feature-specs/project-setup.md
  CREATE  docs/pipeline/project-setup-architect.handoff.md
```

## Notes for Developers

- Read `docs/standards/backend.md` in full before starting. Every pattern in the spec is derived from that document.
- The `create_app()` factory pattern is mandatory. Tests depend on being able to create isolated app instances with dependency overrides.
- Use `from app.config import settings` for all configuration. Never call `os.getenv()` directly.
- All `__init__.py` files should be empty unless explicit re-exports are needed.
- The `.env` file is gitignored. Only `.env.example` is committed with empty values.
- Acceptance criteria #5, #6, and #7 (ruff, mypy, pytest) must all pass with zero errors before the feature is complete.

## Next Steps

backend-dev should read the spec at `shared/feature-specs/project-setup.md` and implement all 30 files listed in the file manifest. backend-tester should then verify all 17 acceptance criteria.
