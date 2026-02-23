"""Tests for the configuration system.

Verifies settings defaults, environment variable loading, that
.env.example contains no actual secrets, and that pyproject.toml
and requirements.txt match the spec.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import Settings


@pytest.mark.asyncio
async def test_settings_defaults_are_correct() -> None:
    """Settings should have correct default values when no env vars are set."""
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        debug=False,
        database_url="",
    )
    assert s.debug is False
    assert s.llm_provider == "claude"
    assert s.aws_region == "us-east-1"
    assert s.app_name == "Ember"
    assert s.app_version == "1.0.0"
    assert s.claude_model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_settings_loads_from_env_vars() -> None:
    """Settings should read DATABASE_URL from environment variables."""
    test_url = "postgresql+asyncpg://test:test@localhost/test_db"
    os.environ["DATABASE_URL"] = test_url
    try:
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            debug=True,
        )
        assert s.database_url == test_url
    finally:
        del os.environ["DATABASE_URL"]


@pytest.mark.asyncio
async def test_env_example_has_no_secrets() -> None:
    """The .env.example file should not contain any actual secret values."""
    env_example_path = Path(__file__).parent.parent / ".env.example"
    assert env_example_path.exists(), ".env.example file must exist"

    sensitive_keys = {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "MEM0_API_KEY",
        "ELEVENLABS_API_KEY",
        "FIREBASE_CREDENTIALS_JSON",
        "AWS_SECRET_NAME",
        "COGNITO_USER_POOL_ID",
        "COGNITO_APP_CLIENT_ID",
        "S3_BUCKET_NAME",
    }

    content = env_example_path.read_text()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key in sensitive_keys:
            assert value == "", f"{key} in .env.example should be empty, got: {value!r}"


@pytest.mark.asyncio
async def test_settings_all_secret_fields_default_to_empty() -> None:
    """All API key and secret fields must default to empty string when no env vars set."""
    secret_fields = [
        "anthropic_api_key",
        "openai_api_key",
        "mem0_api_key",
        "elevenlabs_api_key",
        "firebase_credentials_json",
    ]
    # Temporarily remove secret env vars so we see pure defaults
    saved = {}
    env_keys = [f.upper() for f in secret_fields]
    for key in env_keys:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            debug=True,
        )
        for field in secret_fields:
            assert getattr(s, field) == "", f"{field} should default to empty string"
    finally:
        os.environ.update(saved)


@pytest.mark.asyncio
async def test_settings_cors_origins_default_is_wildcard() -> None:
    """CORS origins should default to '*' for permissive local dev."""
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        debug=True,
    )
    assert s.cors_origins == "*"


@pytest.mark.asyncio
async def test_settings_log_level_default_is_info() -> None:
    """Log level should default to INFO."""
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        debug=True,
    )
    assert s.log_level == "INFO"


@pytest.mark.asyncio
async def test_settings_uses_pydantic_settings_base() -> None:
    """Settings must be a pydantic-settings BaseSettings subclass."""
    from pydantic_settings import BaseSettings

    assert issubclass(Settings, BaseSettings)


@pytest.mark.asyncio
async def test_pyproject_toml_ruff_config() -> None:
    """pyproject.toml must have correct ruff configuration per spec."""
    import tomllib

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    ruff = data["tool"]["ruff"]
    assert ruff["line-length"] == 100
    assert ruff["target-version"] == "py312"

    lint_rules = data["tool"]["ruff"]["lint"]["select"]
    expected_rules = ["E", "F", "I", "N", "UP", "ANN", "ASYNC"]
    assert lint_rules == expected_rules


@pytest.mark.asyncio
async def test_pyproject_toml_pytest_config() -> None:
    """pyproject.toml must have correct pytest configuration."""
    import tomllib

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    pytest_config = data["tool"]["pytest"]["ini_options"]
    assert pytest_config["asyncio_mode"] == "auto"
    assert pytest_config["testpaths"] == ["tests"]


@pytest.mark.asyncio
async def test_requirements_contains_all_packages() -> None:
    """requirements.txt must contain all 13 required production packages."""
    req_path = Path(__file__).parent.parent / "requirements.txt"
    assert req_path.exists(), "requirements.txt must exist"

    content = req_path.read_text()

    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "asyncpg",
        "pydantic-settings",
        "python-jose",
        "boto3",
        "mem0ai",
        "anthropic",
        "firebase-admin",
        "python-multipart",
        "httpx",
        "alembic",
    ]

    for package in required_packages:
        assert package in content, f"{package} must be in requirements.txt"
