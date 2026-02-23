"""Tests for the configuration system.

Verifies settings defaults, environment variable loading, and that
.env.example contains no actual secrets.
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
