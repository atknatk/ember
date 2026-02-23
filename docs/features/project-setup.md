# Project Setup

> Establishes the foundational FastAPI backend scaffold that all subsequent Ember features build upon.

**Status**: Released
**Added in**: Phase 1 (P01-01)
**Platforms**: Backend
**GitHub Issue**: #3

---

## Overview

Project Setup creates the complete backend development environment for Ember. It produces a working FastAPI application with a health-check endpoint, a configuration system backed by pydantic-settings with optional AWS Secrets Manager integration, an async SQLAlchemy database layer with connection pooling, structured logging, Docker-based local development with PostgreSQL, and a production-ready multi-stage Dockerfile.

This is the first feature in the Ember pipeline. Every subsequent backend feature -- authentication, characters, messaging, memory, voice -- depends on the directory structure, configuration system, database session factory, and application factory established here. Without this scaffold, there is no application to add routes to and no database infrastructure to query against.

The feature intentionally does not create any database tables or run migrations. Alembic is configured and ready so that the next feature (P01-02, database models) can immediately generate its first migration. Similarly, the `get_current_user` authentication dependency is stubbed (returns 501 Not Implemented) and will be implemented in P01-03 (user-auth).

---

## Architecture

### How It Works

1. The `create_app()` factory in `app/main.py` instantiates the FastAPI application with title "Ember API" and a lifespan context manager.
2. On startup, the lifespan calls `setup_logging()` to configure the `ember` logger (JSON format in production, human-readable in development).
3. CORS middleware is registered, parsing allowed origins from the `CORS_ORIGINS` configuration value.
4. The health router is mounted under the `/api/v1` prefix.
5. A global exception handler catches any unhandled exceptions and returns `{"detail": "Internal server error"}` with status 500, logging the error without PII.
6. On shutdown, the lifespan disposes the async SQLAlchemy engine to close all database connections.

### Configuration Flow

Configuration loads through `pydantic-settings` with the following priority (highest first):

1. **Environment variables** -- always checked first.
2. **`.env` file** -- loaded via `SettingsConfigDict(env_file=".env")` for local development.
3. **AWS Secrets Manager** -- loaded in `model_post_init` only when `debug=False`. The function fetches the secret identified by `aws_secret_name` and overlays matching fields onto the settings instance.
4. **Defaults** -- hardcoded in the `Settings` class definition.

The `Settings` instance is cached via `@lru_cache` on `get_settings()`, ensuring a single settings object for the application lifetime. All code accesses configuration through `from app.config import settings` -- never via `os.getenv()` directly.

### Database Infrastructure

The database layer is set up in `app/db/session.py` but no tables or migrations are created at this stage. The infrastructure consists of:

- **AsyncEngine**: Created with `create_async_engine()` using `postgresql+asyncpg://` as the driver, `pool_size=20`, `max_overflow=0`, `pool_pre_ping=True`, and `echo=settings.debug`.
- **AsyncSessionLocal**: An `async_sessionmaker` bound to the engine with `expire_on_commit=False` and `autoflush=False`.
- **Deferred connection pattern**: When `DATABASE_URL` is empty, a placeholder URL (`postgresql+asyncpg://localhost/ember_placeholder`) is used so the module can be imported without error. Actual database operations will fail with a connection error until a real database is configured.

The `get_db` dependency in `app/dependencies.py` yields an `AsyncSession` from `AsyncSessionLocal` and ensures cleanup on exit.

### ORM Base Classes

`app/models/base.py` defines two classes used by all future ORM models:

- **`Base(DeclarativeBase)`** -- the parent class for all SQLAlchemy models.
- **`TimestampMixin`** -- provides `created_at` and `updated_at` columns, both `DateTime(timezone=True)`, both non-nullable, with `server_default=func.now()`. The `updated_at` column also has `onupdate=func.now()`.

### Alembic Migrations

Alembic is configured at `backend/alembic.ini` with migrations located at `app/db/migrations/`. The `env.py` uses the async engine pattern: it reads the database URL from `app.config.settings`, sets `target_metadata` to `Base.metadata`, and runs migrations through `async_engine_from_config` with a `NullPool`. The `versions/` directory is empty (contains only `.gitkeep`), ready for the first migration in P01-02.

---

## API Reference

This feature introduces exactly one endpoint. All future feature routes are registered in `main.py` by their respective features.

### `GET /api/v1/health`

**Auth**: None (public endpoint)
**Purpose**: Health check for ECS Fargate and load balancer probes. Must respond within 5 seconds. Does not touch the database or any external service.

**Response** (`200 OK`):

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

**Response Schema** (`app/schemas/health.py`):

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Always `"ok"` |
| `version` | string | Application version from `settings.app_version` |

**Error Responses**:

| Status | When |
|--------|------|
| 404 | Path does not match `/api/v1/health` |
| 405 | Non-GET method (e.g., POST) |
| 500 | Unhandled exception in the handler (caught by global exception handler) |

---

## Configuration

### Environment Variables

All configuration is managed through `app/config.py` using pydantic-settings. The `.env.example` file documents every variable.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DEBUG` | bool | `false` | Enables debug mode (human-readable logs, SQLAlchemy echo) |
| `LOG_LEVEL` | str | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `DATABASE_URL` | str | `""` | PostgreSQL async connection string |
| `AWS_REGION` | str | `us-east-1` | AWS region for Secrets Manager |
| `AWS_SECRET_NAME` | str | `ember/prod/secrets` | Secrets Manager secret name |
| `COGNITO_USER_POOL_ID` | str | `""` | AWS Cognito user pool ID |
| `COGNITO_APP_CLIENT_ID` | str | `""` | AWS Cognito app client ID |
| `LLM_PROVIDER` | str | `claude` | LLM provider: `claude` or `openai` |
| `CLAUDE_MODEL` | str | `claude-sonnet-4-6` | Default Claude model |
| `ANTHROPIC_API_KEY` | str | `""` | Anthropic API key |
| `OPENAI_API_KEY` | str | `""` | OpenAI API key |
| `OPENAI_MODEL` | str | `gpt-4o` | Default OpenAI model |
| `MEM0_API_KEY` | str | `""` | Mem0.ai API key |
| `ELEVENLABS_API_KEY` | str | `""` | ElevenLabs API key |
| `S3_BUCKET_NAME` | str | `""` | AWS S3 bucket name |
| `FIREBASE_CREDENTIALS_JSON` | str | `""` | Firebase service account JSON |
| `CORS_ORIGINS` | str | `*` | Comma-separated allowed CORS origins |

### Local Development Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. The defaults in `.env.example` are sufficient for local development with Docker Compose. The `DATABASE_URL` points to the Compose PostgreSQL instance. `DEBUG=true` prevents AWS Secrets Manager calls.

---

## Docker Setup

### Production Dockerfile

The `Dockerfile` uses a multi-stage build:

**Stage 1 (Builder)**:
- Base image: `python:3.12-slim`
- Installs `gcc` and `libpq-dev` for building native extensions
- Creates a virtual environment at `/opt/venv`
- Installs Python dependencies from `requirements.txt`

**Stage 2 (Runtime)**:
- Base image: `python:3.12-slim`
- Installs only `libpq5` (runtime) and `curl` (health check)
- Copies the virtual environment from the builder stage
- Copies application source (`app/`) and `alembic.ini`
- Creates a non-root user `ember` who owns `/app`
- Exposes port `8000`
- Health check: `curl -f http://localhost:8000/api/v1/health || exit 1` (every 30s, 5s timeout, 10s start period, 3 retries)
- Entrypoint: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

Build and run:
```bash
cd backend
docker build -t ember-backend .
docker run -p 8000:8000 ember-backend
```

### Docker Compose (Local Development)

The `docker-compose.yml` defines two services:

**`db` (PostgreSQL 16)**:
- Image: `postgres:16-alpine`
- Port: `5432:5432`
- Credentials: `ember` / `ember` / `ember_dev`
- Data persistence: named volume `ember_pgdata`
- Health check: `pg_isready -U ember -d ember_dev`

**`backend` (Ember API)**:
- Builds from the local `Dockerfile`
- Port: `8000:8000`
- Reads environment from `.env`
- Depends on `db` being healthy before starting
- Bind-mounts `./app` to `/app/app` for hot reload
- Command override: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`

Start the full stack:
```bash
cd backend
docker compose up
```

Verify the health endpoint:
```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","version":"1.0.0"}
```

---

## Directory Structure

```
backend/
  app/
    __init__.py
    main.py              # Application factory (create_app), lifespan, CORS, exception handler
    config.py            # pydantic-settings configuration with AWS Secrets Manager
    dependencies.py      # get_db session dependency, get_current_user stub (501)
    core/
      __init__.py
      logging.py         # Structured logging setup (JSON prod, human-readable dev)
    db/
      __init__.py
      session.py         # AsyncEngine (pool_size=20) + AsyncSessionLocal
      migrations/
        env.py           # Async Alembic environment
        script.py.mako   # Migration file template
        versions/
          .gitkeep       # Empty — migrations added by subsequent features
    models/
      __init__.py
      base.py            # Base(DeclarativeBase) + TimestampMixin
    routes/
      __init__.py
      health.py          # GET /api/v1/health
    schemas/
      __init__.py
      health.py          # HealthResponse Pydantic model
    services/
      __init__.py
    utils/
      __init__.py
  tests/
    __init__.py
    conftest.py          # AsyncClient fixture, mock DB override, test env setup
    test_app.py          # App factory, CORS, 404, title, version, exception handler, lifespan
    test_config.py       # Settings defaults, env vars, .env.example, secret fields, pyproject
    test_health.py       # Health 200, no auth, schema shape, content type, POST 405
    test_dependencies.py # get_current_user 501, get_db async generator
    test_models_base.py  # Base, TimestampMixin columns, timezone, nullable, defaults
    test_db_session.py   # Engine type, pool_size, pool_pre_ping, sessionmaker config
    test_logging.py      # Handler creation, log levels, formats, deduplication
    test_docker.py       # Dockerfile and docker-compose.yml structural validation
    test_schemas.py      # HealthResponse validation
  pyproject.toml         # ruff, mypy, pytest configuration
  requirements.txt       # 13 production dependencies
  requirements-dev.txt   # 5 development dependencies
  alembic.ini            # Alembic configuration
  Dockerfile             # Multi-stage production build
  docker-compose.yml     # Local dev: PostgreSQL + backend with hot reload
  .dockerignore
  .gitignore
  .env.example           # All env vars documented, secrets empty
```

---

## Development Workflow

### Prerequisites

- Python 3.12+
- Docker and Docker Compose (for local PostgreSQL)
- A copy of `.env` based on `.env.example`

### Running Locally (without Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Running Locally (with Docker Compose)

```bash
cd backend
cp .env.example .env
docker compose up
```

### Code Quality

Ruff (linter and formatter), mypy (type checker), and pytest must all pass with zero errors before any feature is considered complete.

```bash
# Lint
ruff check app/ tests/

# Type check
mypy app/

# Run tests
python -m pytest tests/ -v
```

The `pyproject.toml` configures:
- **ruff**: `line-length = 100`, `target-version = "py312"`, rules `["E", "F", "I", "N", "UP", "ANN", "ASYNC"]`
- **mypy**: `strict = true`, `python_version = "3.12"`, `ignore_missing_imports = true`, pydantic plugin enabled
- **pytest**: `asyncio_mode = "auto"`, `testpaths = ["tests"]`

### Running Alembic Migrations

No migrations exist yet, but the infrastructure is ready. Once models are defined (P01-02), generate and run migrations with:

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

## Testing

### Coverage Summary

| File | Coverage | Uncovered Paths |
|------|----------|-----------------|
| `app/main.py` | 100% | -- |
| `app/config.py` | 91% | AWS Secrets Manager loading (requires real AWS credentials) |
| `app/core/logging.py` | 100% | -- |
| `app/db/session.py` | 100% | -- |
| `app/dependencies.py` | 82% | `get_db` session yield body (requires real async DB) |
| `app/models/base.py` | 100% | -- |
| `app/routes/health.py` | 100% | -- |
| `app/schemas/health.py` | 100% | -- |
| **Overall** | **95%** | |

### Test Suite

73 tests total, 0 failures, 0 skipped.

| Test File | Count | What It Covers |
|-----------|-------|----------------|
| `test_health.py` | 5 | Response 200, no auth required, schema shape, content type, POST 405 |
| `test_config.py` | 10 | Defaults, env var loading, .env.example no secrets, secret defaults, CORS, log level, pydantic base, pyproject ruff rules, pyproject pytest config, requirements |
| `test_app.py` | 12 | App factory, CORS middleware + methods + headers + credentials, 404, title/version, API prefix, module-level app, global exception handler 500, lifespan |
| `test_dependencies.py` | 3 | `get_current_user` 501, detail message, `get_db` is async generator |
| `test_models_base.py` | 9 | `Base` is `DeclarativeBase`, `TimestampMixin` columns, timezone-aware, not nullable, server_default, onupdate |
| `test_db_session.py` | 7 | Engine type, pool_size=20, pool_pre_ping, sessionmaker type, expire_on_commit, autoflush, session class |
| `test_logging.py` | 9 | Handler creation, log levels (DEBUG/INFO/WARNING), debug format, JSON format, no duplicate handlers, invalid level fallback, uvicorn suppressed |
| `test_docker.py` | 15 | Dockerfile: exists, multi-stage, python 3.12-slim, non-root user, port 8000, health check, uvicorn, no secrets. docker-compose: exists, db service, backend service, named volume, depends_on, db healthcheck, hot reload |
| `test_schemas.py` | 3 | HealthResponse is BaseModel, required fields, serialization |

### Running Tests

```bash
cd backend && python -m pytest tests/ -v
```

Tests run without a real database or AWS credentials. The `conftest.py` sets `DEBUG=true` via `os.environ.setdefault()` before importing the app (preventing AWS Secrets Manager calls) and overrides the `get_db` dependency with an `AsyncMock`.

---

## Known Limitations

- **No database tables or migrations**: This scaffold provides the infrastructure only. Table creation happens in P01-02.
- **`get_current_user` is a stub**: Returns 501 Not Implemented. JWT authentication is implemented in P01-03.
- **No CI/CD pipelines**: GitHub Actions workflows are tracked in a separate infrastructure feature.
- **AWS Secrets Manager code is not unit-tested**: The `model_post_init` branch that calls boto3 requires real AWS credentials. This path should be covered in integration tests against a staging environment.
- **`get_db` yield body is not tested**: Requires a real async database connection. The function's type signature and async generator nature are verified but the session yield/cleanup is not exercised in unit tests.

### Implementation Deviations from Spec

- **ANN101/ANN102 ruff ignore list**: The spec listed `ignore = ["ANN101", "ANN102"]` in pyproject.toml, but these rules have been removed from ruff in recent versions. The implementation uses `ignore = []` instead. This is correct behavior.
- **Deferred DB connection**: `db/session.py` uses a placeholder URL (`ember_placeholder`) when `DATABASE_URL` is empty, allowing module import without error. The spec required graceful handling of missing `DATABASE_URL` at import time, and this approach satisfies that requirement.

---

## Extending This Feature

### Adding a New Route Module

1. Create the route file at `app/routes/{feature}.py` with an `APIRouter()`.
2. Register it in `app/main.py` by importing and calling `app.include_router(feature.router, prefix="/api/v1", tags=["feature"])`.

### Adding a New Configuration Variable

1. Add the field with type annotation and default to the `Settings` class in `app/config.py`.
2. Add the corresponding entry to `.env.example` with an empty value and a comment.
3. If the value is a secret loaded from AWS Secrets Manager, ensure the key name in Secrets Manager matches the field name.

### Adding a New ORM Model

1. Define the model in `app/models/{name}.py`, inheriting from `Base` and optionally `TimestampMixin`.
2. Import it in `app/models/__init__.py` so Alembic's `Base.metadata` picks it up.
3. Generate a migration: `alembic revision --autogenerate -m "add {name} table"`.
4. Apply it: `alembic upgrade head`.

### Adding a New Dependency

1. Add the dependency function to `app/dependencies.py` (or create a feature-specific dependencies file).
2. Use `Depends()` in route function signatures to inject it.

---

## Related Documentation

- [System Architecture](../03-mimari.md)
- [Database Schema and API Endpoints](../04-veri-api.md)
- [Security and Performance](../08-guvenlik-performans.md)
- [Deployment (AWS ECS, RDS, S3)](../09-dagitim.md)
- [Backend Standards](../standards/backend.md)
