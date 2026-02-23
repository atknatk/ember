# Backend Dev Agent Memory

## Project Setup Patterns

- `config.py` at module level triggers AWS Secrets Manager when `debug=False`. Tests MUST set `os.environ["DEBUG"] = "true"` BEFORE importing any app modules.
- `db/session.py` creates engine at module level. Use a placeholder URL (`postgresql+asyncpg://localhost/ember_placeholder`) when `DATABASE_URL` is empty so import succeeds (deferred connection pattern).
- Tests `conftest.py` sets env vars via `os.environ.setdefault()` at the TOP of the file, before any `from app...` imports. Requires `# noqa: E402` on subsequent imports.
- Ruff has removed ANN101/ANN102 rules. Do NOT add them to the `ignore` list in pyproject.toml.
- Use `collections.abc.AsyncGenerator` (not `typing.AsyncGenerator`) per UP035.
- `model_post_init` signature uses `__context: object` (not `Any`) to avoid ANN401.
- Import order for stdlib: alphabetical within the block (`collections.abc` before `contextlib`).

## Key File Paths

- App entry: `/Users/atakan/Documents/GitHub/atknatk/ember/backend/app/main.py`
- Config: `/Users/atakan/Documents/GitHub/atknatk/ember/backend/app/config.py`
- Dependencies: `/Users/atakan/Documents/GitHub/atknatk/ember/backend/app/dependencies.py`
- DB session: `/Users/atakan/Documents/GitHub/atknatk/ember/backend/app/db/session.py`
- Base model: `/Users/atakan/Documents/GitHub/atknatk/ember/backend/app/models/base.py`
- Health route: `/Users/atakan/Documents/GitHub/atknatk/ember/backend/app/routes/health.py`
- Test conftest: `/Users/atakan/Documents/GitHub/atknatk/ember/backend/tests/conftest.py`

## Quality Check Commands

```bash
cd /Users/atakan/Documents/GitHub/atknatk/ember/backend && source .venv/bin/activate
ruff check app/ tests/
mypy app/ --ignore-missing-imports
python -m pytest tests/ -x -v
```
