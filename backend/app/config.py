"""Application configuration using pydantic-settings.

Loads configuration from environment variables, .env file (local development),
and AWS Secrets Manager (production when debug=False).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("ember")


def _load_secret(secret_name: str, region: str) -> dict[str, object]:
    """Load secrets from AWS Secrets Manager."""
    import boto3  # noqa: ANN001

    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])  # type: ignore[no-any-return]


class Settings(BaseSettings):
    """Ember backend configuration.

    Priority: environment variables > .env file > defaults.
    In production (debug=False), secrets are loaded from AWS Secrets Manager.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    app_name: str = "Ember"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # AWS
    aws_region: str = "us-east-1"
    aws_secret_name: str = "ember/prod/secrets"

    # Database
    database_url: str = ""

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""

    # LLM
    llm_provider: str = "claude"
    claude_model: str = "claude-sonnet-4-6"
    claude_haiku_model: str = "claude-haiku-4-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_fast_model: str = "gpt-4o-mini"

    # Memory
    mem0_api_key: str = ""

    # Circuit Breaker
    mem0_circuit_failure_threshold: int = 3
    mem0_circuit_recovery_timeout: float = 60.0
    mem0_cache_ttl: float = 300.0
    mem0_retry_queue_max_size: int = 100

    # Chat context
    max_context_messages: int = 50

    # Voice
    elevenlabs_api_key: str = ""

    # Storage
    s3_bucket_name: str = ""

    # Push Notifications
    firebase_credentials_json: str = ""

    # Rate Limiting
    rate_limit_chat: int = 10
    rate_limit_write: int = 20
    rate_limit_read: int = 60

    # CORS
    cors_origins: str = "*"

    # Observability — Sentry
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1

    # Observability — Health Check
    health_check_timeout: float = 3.0
    health_check_degraded_threshold: float = 1.0

    # Notification Scheduler
    notification_scheduler_enabled: bool = True
    notification_scheduler_interval_minutes: int = 30
    notification_batch_size: int = 100

    # Content Moderation
    moderation_enabled: bool = True
    moderation_fail_open: bool = True
    moderation_abuse_window_hours: int = 24
    moderation_block_duration_short_minutes: int = 15
    moderation_block_duration_long_minutes: int = 60

    # Observability — Logging
    log_request_body: bool = False

    def model_post_init(self, __context: object) -> None:
        """Load secrets from AWS Secrets Manager in production."""
        if not self.debug and self.aws_secret_name:
            try:
                secrets = _load_secret(self.aws_secret_name, self.aws_region)
                for key, value in secrets.items():
                    if hasattr(self, key):
                        object.__setattr__(self, key, value)
            except Exception:
                logger.warning(
                    "Failed to load secrets from AWS Secrets Manager. "
                    "Falling back to environment variables.",
                    exc_info=True,
                )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


settings = get_settings()
