# Database Schema

> Defines all seven SQLAlchemy async ORM models that form the relational data foundation for every Ember feature.

**Status**: Released
**Added in**: Phase 1 (P01-02)
**Platforms**: Backend
**GitHub Issue**: #4

---

## Overview

Database Schema establishes the complete data layer for Ember by creating seven PostgreSQL tables through SQLAlchemy 2.0 async ORM models and an Alembic migration. The tables cover user profiles, AI characters, conversations, messages, user activity tracking, partner connections, and body measurements. Together they support every backend feature from authentication through messaging, notifications, fitness coaching, and partner accountability.

This feature builds on top of the P01-01 project scaffold, which provides `Base`, `TimestampMixin`, `AsyncEngine`, `AsyncSessionLocal`, and the Alembic migration infrastructure. It produces no API endpoints -- it is purely a data layer concern. All subsequent features (user-auth, character CRUD, messaging, and beyond) depend on these models to read and write data.

The schema enforces critical business rules at the database level. A UNIQUE constraint on `conversations.character_id` guarantees the "one conversation per character forever" rule (see ADR-003). CHECK constraints on `messages.role`, `profiles.subscription_tier`, and `partners.status` prevent invalid enum values. Composite indexes with DESC ordering on timestamp columns optimize the two most performance-sensitive queries: cursor-based message pagination and character grid sorting by last activity.

---

## Architecture

### How It Works (Data Flow)

1. The developer defines seven model classes in `backend/app/models/`, each inheriting from `Base` (and optionally `TimestampMixin`).
2. All models are imported in `backend/app/models/__init__.py`, which registers them with `Base.metadata`.
3. The Alembic `env.py` imports all models via `from app.models import *` so that `Base.metadata` contains the full table set.
4. Running `alembic revision --autogenerate` produces a single migration file that creates all seven tables with their columns, constraints, foreign keys, and indexes.
5. Running `alembic upgrade head` applies the migration to PostgreSQL, creating the physical schema.
6. Downstream features import models from `app.models` and use `AsyncSession` to query and persist data.

### TimestampMixin Usage

Five of the seven models use `TimestampMixin`, which provides `created_at` and `updated_at` columns with `server_default=func.now()` and `onupdate=func.now()` on `updated_at`. Two models intentionally opt out:

- **`Message`** does not use `TimestampMixin` because messages are append-only and never updated. Adding `updated_at` would waste 8 bytes per row on the highest-traffic table and create a misleading schema. `created_at` is defined directly on the model.
- **`UserActivity`** does not use `TimestampMixin` because the authoritative spec (`docs/04-veri-api.md`) defines `updated_at` but no `created_at` for this table. The row is created when the user first becomes active, and only `updated_at` matters thereafter.

### Primary Key Strategy

All tables use UUID primary keys. The `profiles.id` column is the AWS Cognito `sub` UUID, set by the application at registration time (not auto-generated). All other tables use `uuid.uuid4` as the default generator. UUIDs prevent ID enumeration attacks, support distributed ID generation without sequence contention, and match the Cognito `sub` format.

### Cascade Deletion Rules

| FK Column | ON DELETE | Rationale |
|-----------|-----------|-----------|
| `characters.user_id` | CASCADE | Deleting a user removes all their characters |
| `conversations.user_id` | CASCADE | Deleting a user removes all their conversations |
| `conversations.character_id` | CASCADE | Deleting a character removes its conversation |
| `messages.conversation_id` | CASCADE | Deleting a conversation removes all its messages |
| `messages.user_id` | CASCADE | Deleting a user removes all their messages |
| `user_activity.user_id` | CASCADE | Deleting a user removes their activity record |
| `partners.user_id_1` | CASCADE | Deleting the inviter removes the partnership entirely |
| `partners.user_id_2` | SET NULL | Deleting the invitee preserves the row with `user_id_2 = NULL` so the inviter sees the disconnection |
| `body_measurements.user_id` | CASCADE | Deleting a user removes all their measurements |

---

## Tables

### `profiles`

User profile data. The `id` is the AWS Cognito `sub` (UUID format), serving as both the Cognito identifier and the primary key.

**Model class**: `Profile`
**File**: `backend/app/models/profile.py`
**Inherits**: `Base`, `TimestampMixin`

| Column | Type | Nullable | Default | Constraints |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | (Cognito sub) | PK |
| `email` | TEXT | No | -- | UNIQUE |
| `name` | TEXT | No | -- | -- |
| `mem0_user_id` | TEXT | No | -- | UNIQUE |
| `fcm_token` | TEXT | Yes | `None` | -- |
| `timezone` | TEXT | No | `'UTC'` | -- |
| `avatar_url` | TEXT | Yes | `None` | -- |
| `preferred_language` | TEXT | No | `'en'` | -- |
| `onboarding_completed` | BOOLEAN | No | `False` | -- |
| `subscription_tier` | TEXT | No | `'free'` | CHECK: `free`, `premium` |
| `subscription_expires_at` | TIMESTAMPTZ | Yes | `None` | -- |
| `created_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin) |
| `updated_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin, auto-updated) |

**Relationships**:
- `characters` -- one-to-many to `Character` (`cascade="all, delete-orphan"`)
- `conversations` -- one-to-many to `Conversation` (`cascade="all, delete-orphan"`)

---

### `characters`

AI character instances, one per user per character template.

**Model class**: `Character`
**File**: `backend/app/models/character.py`
**Inherits**: `Base`, `TimestampMixin`

| Column | Type | Nullable | Default | Constraints |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `uuid4()` | PK |
| `user_id` | UUID | No | -- | FK -> `profiles.id` ON DELETE CASCADE |
| `name` | TEXT | No | -- | -- |
| `template` | TEXT | No | -- | -- |
| `description` | TEXT | Yes | `None` | -- |
| `system_prompt` | TEXT | No | -- | -- |
| `mem0_agent_id` | TEXT | No | -- | UNIQUE |
| `avatar_style` | TEXT | No | `'default'` | -- |
| `is_default` | BOOLEAN | No | `False` | -- |
| `is_active` | BOOLEAN | No | `True` | -- |
| `created_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin) |
| `updated_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin, auto-updated) |

**Relationships**:
- `user` -- many-to-one to `Profile`
- `conversation` -- one-to-one to `Conversation` (`uselist=False`)

**Notes**:
- `template` values include `companion`, `english_teacher`, `therapist`, `fitness_coach`, `career_coach`, and `custom`. No CHECK constraint is applied because new templates may be added dynamically. Validation happens at the application layer.
- `mem0_agent_id` format: `{template}_{user_id}` (e.g., `companion_550e8400-e29b-41d4-a716-446655440000`).

---

### `conversations`

One conversation per character, auto-created. Users never see this table directly.

**Model class**: `Conversation`
**File**: `backend/app/models/conversation.py`
**Inherits**: `Base`, `TimestampMixin`

| Column | Type | Nullable | Default | Constraints |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `uuid4()` | PK |
| `user_id` | UUID | No | -- | FK -> `profiles.id` ON DELETE CASCADE |
| `character_id` | UUID | No | -- | FK -> `characters.id` ON DELETE CASCADE, UNIQUE |
| `last_message_at` | TIMESTAMPTZ | Yes | `None` | -- |
| `created_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin) |
| `updated_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin, auto-updated) |

**Relationships**:
- `user` -- many-to-one to `Profile`
- `character` -- one-to-one to `Character`
- `messages` -- one-to-many to `Message` (`cascade="all, delete-orphan"`)

**Notes**:
- The UNIQUE constraint on `character_id` enforces the "one conversation per character" rule at the database level. This is the single most important architectural constraint in Ember (see ADR-003).
- `last_message_at` is nullable because a newly created conversation has no messages yet.

---

### `messages`

The highest-traffic table. Stores every message in every conversation. Append-only -- messages are never updated after creation.

**Model class**: `Message`
**File**: `backend/app/models/message.py`
**Inherits**: `Base` only (does NOT use `TimestampMixin`)

| Column | Type | Nullable | Default | Constraints |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `uuid4()` | PK |
| `conversation_id` | UUID | No | -- | FK -> `conversations.id` ON DELETE CASCADE |
| `user_id` | UUID | No | -- | FK -> `profiles.id` ON DELETE CASCADE |
| `role` | TEXT | No | -- | CHECK: `user`, `assistant` |
| `content` | TEXT | No | -- | -- |
| `media_url` | TEXT | Yes | `None` | -- |
| `tts_url` | TEXT | Yes | `None` | -- |
| `metadata` | JSONB | Yes | `None` | -- |
| `created_at` | TIMESTAMPTZ | No | `NOW()` | (defined directly, no mixin) |

**Relationships**:
- `conversation` -- many-to-one to `Conversation`
- `user` -- many-to-one to `Profile`

**Notes**:
- The Python attribute is `metadata_` (with trailing underscore) to avoid collision with SQLAlchemy's built-in `.metadata`. The database column name is `metadata`. Access via `message.metadata_` in Python code.
- `content` has no DB-level max length. The 4000-character limit is enforced at the application layer via Pydantic validators.
- This table has no `updated_at` column. Messages are immutable once written.

---

### `user_activity`

Tracks user activity for proactive notification scheduling. One row per user.

**Model class**: `UserActivity`
**File**: `backend/app/models/user_activity.py`
**Inherits**: `Base` only (does NOT use `TimestampMixin`)

| Column | Type | Nullable | Default | Constraints |
|--------|------|----------|---------|-------------|
| `user_id` | UUID | No | -- | PK, FK -> `profiles.id` ON DELETE CASCADE |
| `last_active_at` | TIMESTAMPTZ | Yes | `None` | -- |
| `last_chat_at` | TIMESTAMPTZ | Yes | `None` | -- |
| `notifications_sent_today` | JSONB | No | `'[]'::jsonb` | -- |
| `updated_at` | TIMESTAMPTZ | No | `NOW()` | (auto-updated via `onupdate=func.now()`) |

**Relationships**:
- `user` -- one-to-one to `Profile`

**Notes**:
- `user_id` is both the primary key and a foreign key. There is no separate `id` column. This guarantees exactly one activity row per user.
- `notifications_sent_today` stores a JSON array of notification type strings (e.g., `["morning_checkin", "evening_reflection"]`). Reset daily by a scheduled task.
- This table has no `created_at` column.

---

### `partners`

Partner connections for the couple/accountability feature (Phase 7).

**Model class**: `Partner`
**File**: `backend/app/models/partner.py`
**Inherits**: `Base`, `TimestampMixin`

| Column | Type | Nullable | Default | Constraints |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `uuid4()` | PK |
| `user_id_1` | UUID | No | -- | FK -> `profiles.id` ON DELETE CASCADE |
| `user_id_2` | UUID | Yes | `None` | FK -> `profiles.id` ON DELETE SET NULL |
| `invite_token` | TEXT | No | -- | UNIQUE |
| `status` | TEXT | No | `'pending'` | CHECK: `pending`, `active`, `disconnected` |
| `created_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin) |
| `updated_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin, auto-updated) |

**Relationships**:
- `inviter` -- many-to-one to `Profile` via `user_id_1`
- `invitee` -- many-to-one to `Profile` via `user_id_2`

**Notes**:
- `user_id_2` is nullable because the invite starts as pending before the other user accepts.
- ON DELETE SET NULL on `user_id_2` preserves the partnership record when the invitee deletes their account. The application layer handles updating `status` to `'disconnected'`.

---

### `body_measurements`

Body tracking data for the fitness coaching character.

**Model class**: `BodyMeasurement`
**File**: `backend/app/models/body_measurement.py`
**Inherits**: `Base`, `TimestampMixin`

| Column | Type | Nullable | Default | Constraints |
|--------|------|----------|---------|-------------|
| `id` | UUID | No | `uuid4()` | PK |
| `user_id` | UUID | No | -- | FK -> `profiles.id` ON DELETE CASCADE |
| `date` | DATE | No | -- | -- |
| `weight_kg` | NUMERIC(5,2) | Yes | `None` | -- |
| `body_fat_pct` | NUMERIC(4,1) | Yes | `None` | -- |
| `notes` | TEXT | Yes | `None` | -- |
| `created_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin) |
| `updated_at` | TIMESTAMPTZ | No | `NOW()` | (from TimestampMixin, auto-updated) |

**Relationships**:
- `user` -- many-to-one to `Profile`

**Notes**:
- `NUMERIC(5,2)` supports weights from 0.00 to 999.99 kg with exact decimal storage (no floating-point rounding).
- `NUMERIC(4,1)` supports body fat percentages from 0.0 to 999.9.
- The unique constraint `uq_body_measurements_user_date` on `(user_id, date)` prevents multiple entries for the same day. Updates should use an upsert pattern.

---

## Indexes

### Explicit Indexes (ordered by performance criticality)

| Index Name | Table | Columns | Type | Purpose |
|-----------|-------|---------|------|---------|
| `idx_messages_conv_time` | `messages` | `(conversation_id, created_at DESC)` | B-tree composite | Cursor-based message pagination -- the hottest query in the system |
| `idx_conversations_user_time` | `conversations` | `(user_id, last_message_at DESC)` | B-tree composite | Character grid sorting by last activity |
| `idx_characters_user_active` | `characters` | `(user_id, is_active)` | B-tree composite | Listing active characters for a user |
| `idx_messages_user_id` | `messages` | `(user_id)` | B-tree | GDPR user data deletion and activity queries |
| `idx_body_measurements_user_date` | `body_measurements` | `(user_id, date)` | B-tree composite | Measurement history retrieval |
| `idx_partners_user1` | `partners` | `(user_id_1)` | B-tree | Finding partnerships by inviter |
| `idx_partners_user2` | `partners` | `(user_id_2)` | B-tree | Finding partnerships by invitee |

### Unique Constraints (which also create implicit indexes)

| Constraint | Table | Columns |
|-----------|-------|---------|
| `uq_body_measurements_user_date` | `body_measurements` | `(user_id, date)` |
| (auto) | `profiles` | `email` |
| (auto) | `profiles` | `mem0_user_id` |
| (auto) | `characters` | `mem0_agent_id` |
| (auto) | `conversations` | `character_id` |
| (auto) | `partners` | `invite_token` |

### CHECK Constraints

| Constraint Name | Table | Rule |
|----------------|-------|------|
| `ck_profiles_subscription_tier` | `profiles` | `subscription_tier IN ('free', 'premium')` |
| `ck_messages_role` | `messages` | `role IN ('user', 'assistant')` |
| `ck_partners_status` | `partners` | `status IN ('pending', 'active', 'disconnected')` |

CHECK constraints were chosen over PostgreSQL ENUM types because they are easier to modify (drop and recreate) without requiring `ALTER TYPE` migrations.

---

## Relationships (Entity Diagram)

```
profiles (PK: id)
  |
  |-- 1:N --> characters (FK: user_id, CASCADE)
  |              |
  |              |-- 1:1 --> conversations (FK: character_id, CASCADE, UNIQUE)
  |                             |
  |                             |-- 1:N --> messages (FK: conversation_id, CASCADE)
  |
  |-- 1:N --> conversations (FK: user_id, CASCADE)
  |
  |-- 1:N --> messages (FK: user_id, CASCADE)
  |
  |-- 1:1 --> user_activity (FK/PK: user_id, CASCADE)
  |
  |-- 1:N --> partners (FK: user_id_1, CASCADE)
  |
  |-- 1:N --> partners (FK: user_id_2, SET NULL)
  |
  |-- 1:N --> body_measurements (FK: user_id, CASCADE)
```

All foreign keys reference `profiles.id`. The `profiles` table is the root of the entire foreign key graph. Deleting a profile cascades through all dependent tables (except `partners.user_id_2`, which uses SET NULL).

---

## Migration

### Migration File

The single initial migration is located at:

```
backend/app/db/migrations/versions/20260223_0001_9aa7d5e9535b_create_initial_tables.py
```

**Revision ID**: `9aa7d5e9535b`
**Down Revision**: `None` (initial migration)

The `upgrade()` function creates all seven tables in dependency order (profiles first, then tables that reference profiles, etc.) with all columns, constraints, foreign keys, and indexes. The `downgrade()` function drops tables in reverse dependency order.

### Alembic Commands

Apply the migration:

```bash
cd backend
alembic upgrade head
```

Revert the migration:

```bash
cd backend
alembic downgrade base
```

Verify round-trip stability (should produce identical schema):

```bash
cd backend
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Generate a new migration after model changes:

```bash
cd backend
alembic revision --autogenerate -m "description_of_change"
```

### Migration Environment

The `env.py` at `backend/app/db/migrations/env.py` uses the async engine pattern. It imports all models via `from app.models import *` (with `# noqa: F403`) to ensure `Base.metadata` contains every table definition. The database URL is read from `app.config.settings`.

---

## Configuration

No new configuration variables were introduced by this feature. The database connection uses the `DATABASE_URL` configured in P01-01. See the [Project Setup documentation](./project-setup.md) for the full configuration reference.

---

## Development Workflow

### Importing Models

All seven model classes and the base classes are importable from the canonical location:

```python
from app.models import (
    Base,
    BodyMeasurement,
    Character,
    Conversation,
    Message,
    Partner,
    Profile,
    TimestampMixin,
    UserActivity,
)
```

### Adding a New Table

1. Create the model file at `backend/app/models/{name}.py`, inheriting from `Base` and optionally `TimestampMixin`.
2. Import the new model in `backend/app/models/__init__.py` and add it to `__all__`.
3. Generate a migration: `alembic revision --autogenerate -m "add {name} table"`.
4. Review the generated migration file (Alembic sometimes misses named constraints).
5. Apply it: `alembic upgrade head`.
6. Test round-trip: `alembic downgrade -1 && alembic upgrade head`.

### Modifying an Existing Table

1. Edit the model file to add/change/remove columns.
2. Generate a migration: `alembic revision --autogenerate -m "alter {table} {change}"`.
3. Review the migration carefully -- Alembic autogenerate does not always detect constraint name changes.
4. Apply and test as above.

### SQLAlchemy 2.0 Style

All models use the SQLAlchemy 2.0 `Mapped[]` type annotation style with `mapped_column()`. The older `Column()` style is not used. Circular imports between model files are handled via the `TYPE_CHECKING` guard and `from __future__ import annotations`.

---

## Testing

### Coverage Summary

| File | Stmts | Covered | Coverage |
|------|-------|---------|----------|
| `app/models/__init__.py` | 9 | 9 | 100% |
| `app/models/base.py` | 8 | 8 | 100% |
| `app/models/profile.py` | 24 | 24 | 100% |
| `app/models/character.py` | 22 | 22 | 100% |
| `app/models/conversation.py` | 18 | 18 | 100% |
| `app/models/message.py` | 23 | 23 | 100% |
| `app/models/user_activity.py` | 17 | 17 | 100% |
| `app/models/partner.py` | 17 | 17 | 100% |
| `app/models/body_measurement.py` | 19 | 19 | 100% |
| **Total** | **157** | **157** | **100%** |

### Test Files

| Test File | Count | What It Covers |
|-----------|-------|----------------|
| `tests/test_models.py` | 76 | Model definitions, column presence, table names, basic metadata |
| `tests/test_models_extended.py` | 221 | Column types, nullability, defaults, server defaults, CHECK constraint SQL text, index compositions and DESC ordering, relationships, metadata mapping, unique constraints, topological order, model instantiation |
| `tests/test_models_base.py` | 9 | Base class, TimestampMixin columns, timezone awareness, server defaults |
| `tests/test_migration.py` | -- | DB round-trip, constraint violations, index existence (requires running PostgreSQL, marked `@pytest.mark.db`) |

**Total**: 306 model tests passing, 0 failures.

### Running Tests

Model definition tests (no database required):

```bash
cd backend && python -m pytest tests/test_models.py tests/test_models_extended.py tests/test_models_base.py -v
```

Model tests with coverage report:

```bash
cd backend && python -m pytest tests/test_models.py tests/test_models_extended.py tests/test_models_base.py --cov=app.models --cov-report=term-missing
```

Migration tests (requires running PostgreSQL):

```bash
cd backend && python -m pytest tests/test_migration.py -v -m db
```

Code quality checks:

```bash
cd backend && ruff check app/models/
cd backend && mypy app/models/
```

---

## Known Limitations

- **No pgvector extension**: Vector search is handled entirely by Mem0 cloud. No vector columns exist in the database schema.
- **No data seeding**: Default character templates and initial data are not created by this feature. Seeding is handled by later features.
- **Migration was manually written**: The migration file was created by hand (no running PostgreSQL was available for autogenerate at build time) but matches the model definitions exactly. All structural tests confirm the correspondence.
- **DB-dependent tests require PostgreSQL**: The `test_migration.py` tests (CHECK constraint violations, index existence in a live database, cascade deletion behavior) require a running PostgreSQL instance and are marked with `@pytest.mark.db`.

---

## Design Decisions

### CHECK constraints instead of PostgreSQL ENUM types

PostgreSQL ENUMs require `ALTER TYPE` to add new values, which is cumbersome and requires careful migration ordering. CHECK constraints can be dropped and recreated more easily. The `characters.template` column intentionally has no CHECK constraint because new templates are expected to be added dynamically.

### NUMERIC instead of FLOAT for body measurements

Floating-point types (`FLOAT`, `REAL`, `DOUBLE PRECISION`) cause rounding errors with decimal values (e.g., 75.5 kg stored as 75.4999...). `NUMERIC(5,2)` and `NUMERIC(4,1)` store exact decimal values, which is essential for health data that users expect to see exactly as entered.

### Single migration for all seven tables

All tables are new with no pre-existing data. One migration file is simpler and equally reversible. Future schema changes will each get their own migration.

### ON DELETE SET NULL for partners.user_id_2

When an invitee deletes their account, the partnership record is preserved (with `user_id_2 = NULL`) so the inviter can see that the partnership was disconnected. The application layer is responsible for updating `status` to `'disconnected'`.

### Message.metadata_ attribute naming

The Python attribute is named `metadata_` (with trailing underscore) because `metadata` collides with SQLAlchemy's built-in `DeclarativeBase.metadata` property. The first positional argument to `mapped_column("metadata", ...)` maps it to the `metadata` column name in the database.

---

## Extending This Feature

To add a new column to an existing table, edit the model file, regenerate the migration with `alembic revision --autogenerate`, review the output, and apply with `alembic upgrade head`. Always review autogenerated migrations because Alembic sometimes misses named constraints or index changes.

To add a new table, follow the development workflow described above. Remember to import the model in `backend/app/models/__init__.py` and add it to `__all__`.

When adding relationships, use `TYPE_CHECKING` guards and `from __future__ import annotations` to avoid circular import issues. SQLAlchemy resolves class names in `relationship()` via the mapper registry at runtime.

All CHECK constraint names follow the pattern `ck_{table}_{column}`. All explicit index names follow the pattern `idx_{table}_{columns}`. All unique constraint names follow the pattern `uq_{table}_{columns}`.

---

## Related Documentation

- [Project Setup](./project-setup.md) -- the scaffold this feature builds on
- [Database Schema and API Endpoints](../04-veri-api.md) -- authoritative source for table definitions
- [System Architecture](../03-mimari.md) -- overall system design
- [ADR-003: Single Conversation](../adr/ADR-003-single-conversation.md) -- why one conversation per character
- [Backend Standards](../standards/backend.md) -- coding conventions for model files
