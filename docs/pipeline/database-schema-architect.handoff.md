# Architect Handoff: Database Schema

**Date**: 2026-02-23
**Agent**: architect
**Status**: COMPLETE
**Feature ID**: P01-02
**GitHub Issue**: #4
**Layer**: backend

---

## What Was Designed

All seven SQLAlchemy async ORM models for the Ember database: `profiles`, `characters`, `conversations`, `messages`, `user_activity`, `partners`, and `body_measurements`. The spec defines every column with its exact type, nullability, default value, and constraints. It specifies eight explicit indexes (including the two critical composite indexes for cursor-based message pagination and character grid sorting), three CHECK constraints, and the complete Alembic migration strategy. This is the data foundation for all Ember features.

## Spec Location

`shared/feature-specs/database-schema.md`

## Key Decisions

- **`messages` table does not use `TimestampMixin`**: Messages are append-only and never updated. Omitting `updated_at` saves 8 bytes per row on the hottest table and avoids a misleading schema. `created_at` is defined directly on the model.
- **`user_activity` table does not use `TimestampMixin`**: Per `docs/04-veri-api.md`, this table has `updated_at` but no `created_at`. Using the mixin would add a column not in the spec.
- **CHECK constraints instead of PostgreSQL ENUM types**: CHECK constraints are easier to modify than ENUMs (no `ALTER TYPE` needed). Used for `profiles.subscription_tier`, `messages.role`, and `partners.status`. The `characters.template` column intentionally has no CHECK because new templates are expected.
- **`NUMERIC` instead of `FLOAT` for body measurements**: Exact decimal storage prevents rounding errors for health data. `NUMERIC(5,2)` for weight, `NUMERIC(4,1)` for body fat percentage.
- **ON DELETE SET NULL for `partners.user_id_2`**: Preserves partnership records when the invitee deletes their account, allowing the inviter to see the disconnection. ON DELETE CASCADE is used for `user_id_1` (inviter).
- **Single migration for all seven tables**: All tables are new with no pre-existing data. One migration is simpler and equally reversible.
- **`profiles.id` is the Cognito `sub`, not auto-generated**: The UUID is provided by Cognito at registration time and used as the PK. All other tables use `uuid4()` default generation.
- **Unique constraint on `(user_id, date)` for `body_measurements`**: Enforces one measurement per user per day at the database level.

## Assumptions Made

- P01-01 is complete: `Base`, `TimestampMixin`, `AsyncEngine`, `AsyncSessionLocal`, Alembic env.py, and the `models/` directory all exist.
- The `backend/app/models/__init__.py` file exists but is empty (or nearly empty). It will be modified to import all model classes.
- The `backend/app/db/migrations/env.py` file exists and is configured for async. It will be modified to add the wildcard model import.
- PostgreSQL 16 is available via Docker Compose (from P01-01) for migration testing.
- No pgvector extension is needed at this stage. Vector search is handled by Mem0 cloud.

## Dependencies

- **Requires**: P01-01 (project-setup -- Base, TimestampMixin, Alembic infrastructure)
- **Blocks**: P01-03 (user-auth), P01-04 (character CRUD), P01-05 (basic messaging), and all subsequent backend features

## File Manifest

```
Backend:
  CREATE  backend/app/models/profile.py
  CREATE  backend/app/models/character.py
  CREATE  backend/app/models/conversation.py
  CREATE  backend/app/models/message.py
  CREATE  backend/app/models/user_activity.py
  CREATE  backend/app/models/partner.py
  CREATE  backend/app/models/body_measurement.py
  MODIFY  backend/app/models/__init__.py
  MODIFY  backend/app/db/migrations/env.py
  CREATE  backend/app/db/migrations/versions/{timestamp}_create_initial_tables.py
  CREATE  backend/tests/test_models.py
  CREATE  backend/tests/test_migration.py

Shared:
  CREATE  shared/feature-specs/database-schema.md
  CREATE  docs/pipeline/database-schema-architect.handoff.md
```

## Notes for Developers

- Read the full spec at `shared/feature-specs/database-schema.md` before starting.
- Use `Mapped[]` with `mapped_column()` (SQLAlchemy 2.0 style), not the old `Column()` style.
- The `Message` model defines `created_at` directly (no mixin). The `UserActivity` model defines `updated_at` directly (no mixin). All other models use `TimestampMixin`.
- After creating all model files, update `models/__init__.py` to import all classes, then update `env.py` to add `from app.models import *`, then run `alembic revision --autogenerate`.
- Review the generated migration file to verify CHECK constraints and named indexes are included. Alembic autogenerate sometimes misses named constraints.
- Test migration round-trip: `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head`.
- All CHECK constraint names follow the pattern `ck_{table}_{column}` (e.g., `ck_messages_role`).
- All explicit index names follow the pattern `idx_{table}_{columns}` (e.g., `idx_messages_conv_time`).

## Next Steps

backend-dev should read the spec at `shared/feature-specs/database-schema.md` and implement all 13 files (7 model files, 2 modifications, 1 migration, 2 test files, plus the migration generation step). backend-tester should then verify all 18 acceptance criteria.
