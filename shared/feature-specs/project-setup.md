# Feature Spec: P01-01 -- Project Setup

**Feature ID**: P01-01
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #3
**Date**: 2026-02-23
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature establishes the foundational FastAPI project scaffold for the Ember backend. It creates the complete directory structure, installs all required dependencies, configures code quality tooling (ruff, mypy), sets up Docker-based local development (Docker Compose with PostgreSQL), and produces a production-ready multi-stage Dockerfile. It also creates the configuration layer (pydantic-settings), the database session factory (SQLAlchemy async), the FastAPI application factory with lifespan management, and a health-check endpoint.

### Why It Exists

Every subsequent backend feature (auth, characters, messages, memory, voice) depends on this scaffold. Without it, there is no application to add routes to, no database session to query, no configuration system to read secrets from, and no local development environment. This is the prerequisite for all Phase 1 work.

### Dependencies

None. This is the first feature in the project.

### What This Feature Does NOT Do

- It does not implement any business-logic endpoints (auth, characters, messages). Those are separate features.
- It does not create database tables or run migrations. Table creation happens in subsequent features (P01-02 onward).
- It does not configure CI/CD pipelines. GitHub Actions workflows are tracked in a separate infra feature.

---

## 2. API Changes

### New Endpoints

This feature introduces exactly one endpoint. All future feature routes will be registered in `main.py` by their respective features.

```
GET /api/v1/health
Auth: None (public)
Request headers: none required
Request body: none
Response 200:
{
  "status": "ok",
  "version": "1.0.0"
}
Notes: Used by ECS Fargate health checks and load balancer.
       Must respond within 5 seconds. Must not touch the
       database or any external service.
```

### No Modified Endpoints

No existing endpoints are modified because none exist yet.

---

## 3. DB Changes

### No New Tables

This feature does not create any database tables. It establishes the async SQLAlchemy engine, session factory, and declarative base class that subsequent features will use to define models.

### Infrastructure Created

The following database infrastructure is set up in code but no DDL is executed at this stage:

- `Base` (DeclarativeBase) -- the parent class for all ORM models
- `TimestampMixin` -- provides `created_at` and `updated_at` columns to any model that inherits it
- `AsyncEngine` -- configured with `postgresql+asyncpg://` connection string, pool_size=20, pool_pre_ping=True
- `AsyncSessionLocal` -- async session factory with `expire_on_commit=False`
- Alembic configuration files -- ready for migrations once models are defined

The database URL pattern is: `postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}`

For local development via Docker Compose, the database is: `postgresql+asyncpg://ember:ember@localhost:5432/ember_dev`

---

## 4. Backend Logic

### Application Factory (`create_app`)

The `create_app()` function in `app/main.py` is responsible for:

1. Creating the FastAPI instance with title "Ember API", version "1.0.0", and the `/api/v1` prefix.
2. Attaching the lifespan context manager that disposes the database engine on shutdown.
3. Adding CORS middleware (permissive in development, tightened via config in production).
4. Registering the health router.
5. Registering a global exception handler that catches unhandled exceptions, logs them (without PII), and returns `{"detail": "Internal server error"}` with status 500.

The module-level `app = create_app()` line allows Uvicorn to import the app directly.

### Configuration (`config.py`)

Uses `pydantic-settings` BaseSettings to load configuration from:
1. Environment variables (highest priority)
2. `.env` file (local development)
3. AWS Secrets Manager (production, loaded in `model_post_init` when `debug=False`)

Settings fields (all with type annotations and defaults):

| Field | Type | Default | Source in Prod |
|-------|------|---------|---------------|
| `app_name` | str | "Ember" | hardcoded |
| `app_version` | str | "1.0.0" | hardcoded |
| `debug` | bool | False | env |
| `aws_region` | str | "us-east-1" | Parameter Store |
| `aws_secret_name` | str | "ember/prod/secrets" | Parameter Store |
| `database_url` | str | "" | Secrets Manager |
| `cognito_user_pool_id` | str | "" | Parameter Store |
| `cognito_app_client_id` | str | "" | Parameter Store |
| `llm_provider` | str | "claude" | env |
| `claude_model` | str | "claude-sonnet-4-6" | env |
| `anthropic_api_key` | str | "" | Secrets Manager |
| `openai_api_key` | str | "" | Secrets Manager |
| `openai_model` | str | "gpt-4o" | env |
| `mem0_api_key` | str | "" | Secrets Manager |
| `elevenlabs_api_key` | str | "" | Secrets Manager |
| `s3_bucket_name` | str | "" | Parameter Store |
| `firebase_credentials_json` | str | "" | Secrets Manager |
| `log_level` | str | "INFO" | env |
| `cors_origins` | str | "*" | env |

The `model_post_init` method conditionally loads from AWS Secrets Manager only when `debug=False`. In local development (`debug=True`), all values come from `.env`.

### Database Session (`db/session.py`)

Creates the async engine and session factory exactly as specified in `docs/standards/backend.md` Section 3. The `get_db` dependency yields a session and ensures cleanup.

### Dependency Injection (`dependencies.py`)

Provides the `get_db` generator dependency. The `get_current_user` dependency is stubbed as a placeholder that raises 501 Not Implemented -- it will be implemented in the auth feature (P01-03).

### Logging

Structured logging is configured at the application level:
- Format: JSON in production (`debug=False`), human-readable in development (`debug=True`)
- Logger name: `ember`
- Level: configurable via `LOG_LEVEL` env var, defaults to `INFO`
- No PII (email, name, message content) is ever logged. User IDs (UUIDs) are acceptable.

---

## 5. Configuration and Tooling

### pyproject.toml

The `pyproject.toml` file serves as the single configuration point for all Python tooling. It includes:

```toml
[project]
name = "ember-backend"
version = "1.0.0"
requires-python = ">=3.12"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "ANN", "ASYNC"]
ignore = ["ANN101", "ANN102"]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.mypy]
strict = true
python_version = "3.12"
ignore_missing_imports = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

These rules match `docs/standards/backend.md` Section 16 exactly.

### requirements.txt

Pinned to major.minor versions for reproducibility:

```
fastapi>=0.115.0,<1.0.0
uvicorn[standard]>=0.34.0,<1.0.0
sqlalchemy[asyncio]>=2.0.0,<3.0.0
asyncpg>=0.30.0,<1.0.0
pydantic-settings>=2.7.0,<3.0.0
python-jose[cryptography]>=3.3.0,<4.0.0
boto3>=1.36.0,<2.0.0
mem0ai>=0.1.0
anthropic>=0.43.0,<1.0.0
firebase-admin>=6.0.0,<7.0.0
python-multipart>=0.0.18
httpx>=0.28.0,<1.0.0
alembic>=1.14.0,<2.0.0
```

### requirements-dev.txt

Development-only dependencies:

```
pytest>=8.0.0,<9.0.0
pytest-asyncio>=0.25.0,<1.0.0
httpx>=0.28.0,<1.0.0
ruff>=0.9.0
mypy>=1.14.0
```

### .env.example

Committed to git with empty values, serving as documentation of all required environment variables:

```bash
# Ember Backend — Environment Variables
# Copy to .env and fill in values for local development

# App
DEBUG=true
LOG_LEVEL=DEBUG

# Database (local Docker Compose provides this)
DATABASE_URL=postgresql+asyncpg://ember:ember@localhost:5432/ember_dev

# AWS
AWS_REGION=us-east-1
AWS_SECRET_NAME=

# Cognito
COGNITO_USER_POOL_ID=
COGNITO_APP_CLIENT_ID=

# LLM
LLM_PROVIDER=claude
CLAUDE_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# Memory
MEM0_API_KEY=

# Voice
ELEVENLABS_API_KEY=

# Storage
S3_BUCKET_NAME=

# Push Notifications
FIREBASE_CREDENTIALS_JSON=

# CORS
CORS_ORIGINS=*
```

### .gitignore (backend-specific additions)

```
.env
.env.*
!.env.example
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
.pytest_cache/
*.egg-info/
dist/
build/
```

### Dockerfile (Multi-Stage Build)

Stage 1 -- Builder:
- Base image: `python:3.12-slim`
- Install build dependencies
- Copy `requirements.txt` and install Python packages into a virtual environment
- No source code copied in this stage (for layer caching)

Stage 2 -- Runtime:
- Base image: `python:3.12-slim`
- Copy virtual environment from builder
- Copy application source code
- Create non-root user `ember` to run the application
- Expose port 8000
- Health check: `curl -f http://localhost:8000/api/v1/health || exit 1`
- Entrypoint: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

The Dockerfile must NOT contain any secrets, API keys, or environment variable values.

### docker-compose.yml (Local Development)

Services:

1. **db** (PostgreSQL 16):
   - Image: `postgres:16-alpine`
   - Port: `5432:5432`
   - Environment: `POSTGRES_USER=ember`, `POSTGRES_PASSWORD=ember`, `POSTGRES_DB=ember_dev`
   - Volume: `ember_pgdata:/var/lib/postgresql/data` (persistent across restarts)
   - Health check: `pg_isready -U ember -d ember_dev`

2. **backend** (Ember API):
   - Build context: `.` (backend directory)
   - Port: `8000:8000`
   - Environment file: `.env`
   - Depends on: `db` (condition: service_healthy)
   - Volume mount: `./app:/app/app` (hot reload in development)
   - Command override: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

Volumes:
- `ember_pgdata` (named volume for PostgreSQL data persistence)

### Alembic Configuration

- `alembic.ini` at backend root, pointing `sqlalchemy.url` to the `DATABASE_URL` env var
- `app/db/migrations/env.py` configured for async engine as shown in `docs/standards/backend.md` Section 14
- `app/db/migrations/versions/` directory created empty (migrations added by subsequent features)

---

## 6. Test Requirements

### What Must Be Tested

Since this is a scaffold feature with minimal runtime logic, the test suite focuses on verifying the scaffold works correctly.

#### Health Endpoint Tests (`tests/test_health.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `GET /api/v1/health` returns 200 | Response body is `{"status": "ok", "version": "1.0.0"}` |
| 2 | Health endpoint requires no auth | No `Authorization` header needed, still returns 200 |

#### Configuration Tests (`tests/test_config.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Settings loads from environment variables | Setting a `DATABASE_URL` env var populates `settings.database_url` |
| 2 | Settings defaults are correct | `debug` is False, `llm_provider` is "claude", `aws_region` is "us-east-1" |
| 3 | `.env.example` has no actual secrets | Parse `.env.example` and verify all sensitive fields are empty strings |

#### Smoke Tests (`tests/test_app.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `create_app()` returns a FastAPI instance | `isinstance(app, FastAPI)` is True |
| 2 | App has CORS middleware registered | CORS headers present in response |
| 3 | Unknown routes return 404 | `GET /api/v1/nonexistent` returns 404 |

#### Test Infrastructure (`tests/conftest.py`)

- Provides an `AsyncClient` fixture using `httpx.ASGITransport`
- Does NOT require a running database (health endpoint tests do not touch DB)
- Sets up dependency overrides for `get_db` that yield a mock/test session (for future use by other features)

### Edge Cases

- Verify the app starts without a `.env` file (all defaults apply)
- Verify the app handles missing `DATABASE_URL` gracefully at import time (deferred connection)

### Code Quality Checks

The following must pass with zero errors before the feature is considered complete:

```bash
ruff check backend/app backend/tests
mypy backend/app
pytest backend/tests -v
```

---

## 7. File Manifest

Every file to be created or modified, grouped by purpose.

### Application Core

```
Backend:
  CREATE  backend/app/__init__.py
  CREATE  backend/app/main.py
  CREATE  backend/app/config.py
  CREATE  backend/app/dependencies.py
```

### Routes

```
Backend:
  CREATE  backend/app/routes/__init__.py
  CREATE  backend/app/routes/health.py
```

### Services

```
Backend:
  CREATE  backend/app/services/__init__.py
```

### Models and Schemas

```
Backend:
  CREATE  backend/app/models/__init__.py
  CREATE  backend/app/models/base.py
  CREATE  backend/app/schemas/__init__.py
  CREATE  backend/app/schemas/health.py
```

### Database

```
Backend:
  CREATE  backend/app/db/__init__.py
  CREATE  backend/app/db/session.py
  CREATE  backend/app/db/migrations/env.py
  CREATE  backend/app/db/migrations/script.py.mako
  CREATE  backend/app/db/migrations/versions/.gitkeep
```

### Utilities

```
Backend:
  CREATE  backend/app/utils/__init__.py
```

### Core (Application-Wide Concerns)

```
Backend:
  CREATE  backend/app/core/__init__.py
  CREATE  backend/app/core/logging.py
```

### Configuration and Tooling

```
Backend:
  CREATE  backend/pyproject.toml
  CREATE  backend/requirements.txt
  CREATE  backend/requirements-dev.txt
  CREATE  backend/.env.example
  CREATE  backend/alembic.ini
```

### Docker

```
Backend:
  CREATE  backend/Dockerfile
  CREATE  backend/docker-compose.yml
  CREATE  backend/.dockerignore
```

### Tests

```
Backend:
  CREATE  backend/tests/__init__.py
  CREATE  backend/tests/conftest.py
  CREATE  backend/tests/test_health.py
  CREATE  backend/tests/test_config.py
  CREATE  backend/tests/test_app.py
```

### Git

```
Backend:
  CREATE  backend/.gitignore
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/project-setup.md         (this file)
  CREATE  docs/pipeline/project-setup-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 30 |
| MODIFY | 0 |
| DELETE | 0 |

---

## 8. Acceptance Criteria

1. Given a developer clones the repository, when they run `docker compose up` from the `backend/` directory, then PostgreSQL starts on port 5432 and the FastAPI app starts on port 8000 within 60 seconds.

2. Given the backend is running, when a client sends `GET /api/v1/health`, then the response status is 200 and the body is `{"status": "ok", "version": "1.0.0"}`.

3. Given the backend is running, when a client sends `GET /api/v1/health` without an `Authorization` header, then the response status is still 200 (no auth required on health).

4. Given the backend is running, when a client sends `GET /api/v1/nonexistent`, then the response status is 404.

5. Given the backend source code, when a developer runs `ruff check backend/app backend/tests`, then zero errors are reported.

6. Given the backend source code, when a developer runs `mypy backend/app`, then zero errors are reported.

7. Given the backend source code, when a developer runs `pytest backend/tests -v`, then all tests pass with exit code 0.

8. Given the `backend/Dockerfile`, when a developer runs `docker build -t ember-backend .` from the `backend/` directory, then the image builds successfully and is under 200MB.

9. Given the built Docker image, when a developer runs the container with `docker run -p 8000:8000 ember-backend`, then `curl http://localhost:8000/api/v1/health` returns 200.

10. Given the `backend/.env.example` file, when a developer inspects it, then all secret fields (API keys, passwords) have empty string values and a comment documenting the variable's purpose.

11. Given the `backend/pyproject.toml` file, when a developer inspects it, then ruff is configured with `line-length = 100`, `target-version = "py312"`, and the lint rules `["E", "F", "I", "N", "UP", "ANN", "ASYNC"]` are selected.

12. Given the `backend/requirements.txt` file, when a developer inspects it, then it contains all 13 required packages: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, pydantic-settings, python-jose[cryptography], boto3, mem0ai, anthropic, firebase-admin, python-multipart, httpx, and alembic.

13. Given the `backend/app/main.py` file, when a developer inspects it, then the `create_app()` function exists and returns a FastAPI instance, CORS middleware is registered, the health router is included, and a global exception handler is present.

14. Given the `backend/app/config.py` file, when a developer inspects it, then it uses `pydantic-settings.BaseSettings` with `SettingsConfigDict(env_file=".env")` and conditionally loads from AWS Secrets Manager when `debug=False`.

15. Given the `backend/app/models/base.py` file, when a developer inspects it, then it defines `Base(DeclarativeBase)` and `TimestampMixin` with `created_at` and `updated_at` mapped columns using `DateTime(timezone=True)`.

16. Given the `backend/app/db/session.py` file, when a developer inspects it, then it creates an `AsyncEngine` with `pool_size=20`, `pool_pre_ping=True`, and an `AsyncSessionLocal` with `expire_on_commit=False`.

17. Given the directory structure after implementation, when a developer lists `backend/app/`, then all subdirectories exist: `routes/`, `services/`, `models/`, `schemas/`, `utils/`, `core/`, `db/`.

---

## 9. Design Decisions and Rationale

### Why `/api/v1/` prefix on all routes

The API versioning prefix is applied at the router level in `main.py` so that future breaking changes can be served at `/api/v2/` without disrupting existing clients. This matches the base URL defined in `docs/04-veri-api.md`: `https://api.{app-domain}.com/api/v1`.

### Why Alembic is included but no migrations are created

Alembic is configured and ready so that the very next feature (P01-02, database models) can immediately generate its first migration. Including Alembic in this scaffold avoids duplication of setup work across multiple features.

### Why `core/` directory is added beyond the original spec

The issue description specifies `backend/app/{routes,services,models,utils,core}`. The `core/` directory hosts application-wide concerns like logging configuration that do not fit into `utils/` (which holds stateless helper functions). The `schemas/` directory is added because `docs/standards/backend.md` Section 1 mandates it for Pydantic request/response models.

### Why `db/` is a subdirectory of `app/`

Following `docs/standards/backend.md` Section 1, the `db/` directory holds `session.py` (engine and session factory) and the `migrations/` subdirectory for Alembic. This keeps database infrastructure colocated and clearly separated from business logic.

### Why health check does not touch the database

The ECS Fargate health check must be fast and reliable. If the database is temporarily unreachable (e.g., during a failover), the health check should still pass so the container is not killed. A separate readiness endpoint can be added later if needed.

---

## 10. Notes for Developers

### For backend-dev

- The directory structure in `docs/standards/backend.md` Section 1 is the authoritative reference. This spec aligns with it, including the `schemas/` directory which the GitHub issue description did not mention but the standard requires.
- Use `from app.config import settings` everywhere -- never read env vars directly with `os.getenv()`.
- The `create_app()` factory pattern must be used so that tests can create isolated app instances.
- All `__init__.py` files should be empty (just the file, no imports) unless re-exports are explicitly needed.
- The `.env` file must be gitignored. Only `.env.example` is committed.
- When writing the Dockerfile, ensure the non-root user `ember` owns the application directory.
- The `docker-compose.yml` must use a named volume for PostgreSQL data, not a bind mount, to avoid permission issues across operating systems.

### For backend-tester

- Tests at this stage do not require a real database. Use `httpx.AsyncClient` with `ASGITransport` to test the health endpoint directly.
- Override `get_db` in `conftest.py` even though no tests use it yet -- subsequent features will depend on this fixture.
- Verify that `ruff check` and `mypy` pass with zero errors as part of the test suite validation.
