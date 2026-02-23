# Backend Tester Memory

## SQLAlchemy 2.0 Testing Patterns

### uuid4 default identity
- `from __future__ import annotations` causes `uuid.uuid4` references to differ across modules
- Never use `is uuid.uuid4` to check defaults; use `col.default.arg.__name__ == "uuid4"` instead

### mapped_column defaults NOT applied at __init__
- `mapped_column(default="free")` does NOT set the value on Python object instantiation
- Defaults are only applied at flush/insert time
- Test defaults via metadata: `col.default.arg == "free"`, not `instance.field == "free"`

### Nullable columns with default=None
- SQLAlchemy may not create a `ColumnDefault` for `nullable=True, default=None`
- `col.default` can be `None` even when `default=None` was specified
- Verify nullability via `col.nullable is True` instead of checking `col.default.arg is None`

### Cascade "all, delete-orphan"
- SQLAlchemy expands `cascade="all, delete-orphan"` into individual options
- `rel.cascade` is a `CascadeOptions` set: `{'delete', 'delete-orphan', 'save-update', 'merge', 'expunge', 'refresh-expire'}`
- Test with `"delete" in rel.cascade` and `"delete-orphan" in rel.cascade`, not `"all" in rel.cascade`

### DESC index expressions
- `idx.columns` does not include DESC-wrapped expressions
- Use `idx.expressions` and convert to strings: `[str(expr) for expr in idx.expressions]`
- Check for "DESC" in the joined expression string

## Project Structure
- Backend venv: `backend/.venv/bin/python`
- Run tests: `cd backend && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_migration.py`
- Coverage: `cd backend && .venv/bin/python -m pytest tests/ --cov=app.models --cov-report=term-missing`
- test_migration.py has `@pytest.mark.db` -- requires running PostgreSQL

## Key Conventions
- Test file naming: `test_{feature}_extended.py` when adding to existing test files
- Use `sa_inspect(ModelClass)` for relationship introspection
- Use `model.__table__.columns`, `model.__table__.indexes`, `model.__table__.constraints` for metadata
- conftest.py uses `os.environ.setdefault("DEBUG", "true")` before any app imports
