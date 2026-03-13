"""Health service — dependency probing for the enhanced health check endpoint.

Probes database, Mem0, and Claude dependencies in parallel with configurable
timeouts. Each probe is independently isolated so a single failure does not
affect other probes.
"""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.health import DependencyStatus

logger = logging.getLogger("ember")


class HealthService:
    """Probes upstream dependencies and reports their status."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check_dependencies(self) -> DependencyStatus:
        """Probe all dependencies in parallel and return their statuses.

        Each probe has a configurable timeout (default 3s). Probes run
        concurrently via asyncio.gather. Results are mapped to status strings:
          - Response within degraded_threshold seconds: "ok"
          - Response between degraded_threshold and timeout: "degraded"
          - Timeout or exception: "unavailable"
        """
        check_timeout = settings.health_check_timeout
        degraded_threshold = settings.health_check_degraded_threshold

        db_status, mem0_status, claude_status = await asyncio.gather(
            self._probe_database(check_timeout, degraded_threshold),
            self._probe_mem0(check_timeout, degraded_threshold),
            self._probe_claude(check_timeout, degraded_threshold),
            return_exceptions=True,
        )

        # If gather itself returned exceptions, treat as unavailable
        if isinstance(db_status, BaseException):
            db_status = "unavailable"
        if isinstance(mem0_status, BaseException):
            mem0_status = "unavailable"
        if isinstance(claude_status, BaseException):
            claude_status = "unavailable"

        return DependencyStatus(
            database=db_status,
            mem0=mem0_status,
            claude=claude_status,
        )

    async def _probe_database(
        self,
        check_timeout: float,
        degraded_threshold: float,
    ) -> str:
        """Probe database connectivity with SELECT 1."""
        try:
            start = time.monotonic()
            await asyncio.wait_for(
                self.db.execute(text("SELECT 1")),
                timeout=check_timeout,
            )
            elapsed = time.monotonic() - start
            return "degraded" if elapsed > degraded_threshold else "ok"
        except TimeoutError:
            logger.warning("Health check: database probe timed out")
            return "unavailable"
        except Exception:
            logger.warning("Health check: database probe failed", exc_info=True)
            return "unavailable"

    async def _probe_mem0(
        self,
        check_timeout: float,
        degraded_threshold: float,
    ) -> str:
        """Probe Mem0 connectivity with a lightweight search."""
        try:
            from mem0 import MemoryClient

            start = time.monotonic()

            async def _do_probe() -> None:
                client = MemoryClient(api_key=settings.mem0_api_key)
                await asyncio.to_thread(
                    client.search,
                    "health_check",
                    user_id="health_probe",
                    limit=1,
                )

            await asyncio.wait_for(_do_probe(), timeout=check_timeout)
            elapsed = time.monotonic() - start
            return "degraded" if elapsed > degraded_threshold else "ok"
        except TimeoutError:
            logger.warning("Health check: mem0 probe timed out")
            return "unavailable"
        except Exception:
            logger.warning("Health check: mem0 probe failed", exc_info=True)
            return "unavailable"

    async def _probe_claude(
        self,
        check_timeout: float,
        degraded_threshold: float,
    ) -> str:
        """Probe Claude API connectivity with a minimal completion."""
        try:
            from anthropic import AsyncAnthropic

            start = time.monotonic()

            async def _do_probe() -> None:
                client = AsyncAnthropic(api_key=settings.anthropic_api_key)
                await client.messages.create(
                    model=settings.claude_haiku_model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "hi"}],
                )

            await asyncio.wait_for(_do_probe(), timeout=check_timeout)
            elapsed = time.monotonic() - start
            return "degraded" if elapsed > degraded_threshold else "ok"
        except TimeoutError:
            logger.warning("Health check: claude probe timed out")
            return "unavailable"
        except Exception:
            logger.warning("Health check: claude probe failed", exc_info=True)
            return "unavailable"
