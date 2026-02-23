# Backend Dev Handoff: Database Schema

**Date**: 2026-02-23
**Agent**: backend-dev
**Status**: COMPLETE
**Feature ID**: P01-02
**GitHub Issue**: #4

## Implemented Files

- `backend/app/models/profile.py` -- Profile model (13 columns, TimestampMixin, CHECK on subscription_tier)
- `backend/app/models/character.py` -- Character model (12 columns, TimestampMixin, composite index)
- `backend/app/models/conversation.py` -- Conversation model (6 columns, TimestampMixin, UNIQUE on character_id)
- `backend/app/models/message.py` -- Message model (9 columns, NO TimestampMixin, CHECK on role, DESC index)
- `backend/app/models/user_activity.py` -- UserActivity model (5 columns, NO TimestampMixin, user_id as PK)
- `backend/app/models/partner.py` -- Partner model (7 columns, TimestampMixin, CHECK on status, ON DELETE SET NULL)
- `backend/app/models/body_measurement.py` -- BodyMeasurement model (8 columns, TimestampMixin, NUMERIC types, composite unique)
- `backend/app/models/__init__.py` -- Canonical import point for all 7 models + Base + TimestampMixin
- `backend/app/db/migrations/env.py` -- Added `from app.models import *` for Alembic autogenerate
- `backend/app/db/migrations/versions/20260223_0001_9aa7d5e9535b_create_initial_tables.py` -- Initial migration (all 7 tables)
- `backend/tests/test_models.py` -- 76 model definition/metadata tests (no DB required)
- `backend/tests/test_migration.py` -- DB round-trip and constraint tests (requires PostgreSQL)

## Tables Created

| Table | Model Class | Columns | Mixin | Special |
|-------|-------------|---------|-------|---------|
| `profiles` | `Profile` | 13 | TimestampMixin | PK = Cognito sub (not auto-generated), CHECK on subscription_tier |
| `characters` | `Character` | 12 | TimestampMixin | UNIQUE on mem0_agent_id, idx_characters_user_active |
| `conversations` | `Conversation` | 6 | TimestampMixin | UNIQUE on character_id, idx_conversations_user_time (DESC) |
| `messages` | `Message` | 9 | None | CHECK on role, idx_messages_conv_time (DESC), idx_messages_user_id |
| `user_activity` | `UserActivity` | 5 | None | user_id is PK+FK, no created_at, JSONB server_default='[]'::jsonb |
| `partners` | `Partner` | 7 | TimestampMixin | CHECK on status, user_id_2 ON DELETE SET NULL, idx_partners_user1/user2 |
| `body_measurements` | `BodyMeasurement` | 8 | TimestampMixin | NUMERIC(5,2) weight, NUMERIC(4,1) body_fat, uq_body_measurements_user_date |

## Indexes Created

| Index Name | Table | Columns | Notes |
|-----------|-------|---------|-------|
| `idx_messages_conv_time` | messages | (conversation_id, created_at DESC) | Cursor-based pagination |
| `idx_conversations_user_time` | conversations | (user_id, last_message_at DESC) | Character grid sorting |
| `idx_characters_user_active` | characters | (user_id, is_active) | Active character listing |
| `idx_messages_user_id` | messages | (user_id) | GDPR deletion |
| `idx_body_measurements_user_date` | body_measurements | (user_id, date) | Measurement history |
| `idx_partners_user1` | partners | (user_id_1) | Partnership lookup |
| `idx_partners_user2` | partners | (user_id_2) | Partnership lookup |

## CHECK Constraints

- `ck_profiles_subscription_tier`: `subscription_tier IN ('free', 'premium')`
- `ck_messages_role`: `role IN ('user', 'assistant')`
- `ck_partners_status`: `status IN ('pending', 'active', 'disconnected')`

## Test Results

- pytest: 149 passed, 0 failed (76 new model tests + 73 existing)
- ruff: clean (0 errors)
- mypy: clean (0 errors in 9 source files)

## Test Commands

```bash
# Model definition tests (no DB required)
cd backend && .venv/bin/python -m pytest tests/test_models.py -v

# All tests except DB-required migration tests
cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_migration.py

# Migration tests (requires running PostgreSQL)
cd backend && .venv/bin/python -m pytest tests/test_migration.py -v -m db
```

## Known Issues / Deviations from Spec

- None. All 7 tables match the spec exactly.

## Notes for Backend Tester

- `test_models.py` tests inspect SQLAlchemy metadata objects in-memory. No database needed.
- `test_migration.py` requires a running PostgreSQL instance. Tests are marked with `@pytest.mark.db` and will need the `db` marker registered in `pyproject.toml` or a running test database to execute.
- The `Message.metadata_` attribute maps to the `metadata` column (renamed to avoid collision with SQLAlchemy's built-in `.metadata`). Access via `message.metadata_` in Python but the column name in SQL is `metadata`.
- `UserActivity.notifications_sent_today` has a server_default of `'[]'::jsonb` (empty JSON array), using `sa.text()` wrapper.
- The `idx_messages_conv_time` and `idx_conversations_user_time` indexes use `DESC` ordering on the timestamp column for optimal cursor-based pagination.
- Circular imports between model files are handled via `TYPE_CHECKING` guard and `from __future__ import annotations`.
- The migration file was manually created (no running PostgreSQL for autogenerate) but matches the model definitions exactly.
