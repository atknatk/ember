"""Route-level tests for content moderation integration in the chat endpoint.

Tests that ChatService.validate_send_message raises appropriate HTTP errors
when moderation rejects a message, and that the stream emits the moderation
SSE event for therapist crisis augmentation.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import json  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.content_moderation import ModerationResult  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_character(
    user_id: uuid.UUID = FAKE_USER_ID,
    template: str = "companion",
    is_active: bool = True,
) -> MagicMock:
    char = MagicMock()
    char.id = FAKE_CHARACTER_ID
    char.user_id = user_id
    char.template = template
    char.is_active = is_active
    char.system_prompt = "You are a helpful companion."
    char.mem0_agent_id = f"{template}_{user_id}"
    return char


def _make_conversation(user_id: uuid.UUID = FAKE_USER_ID) -> MagicMock:
    conv = MagicMock()
    conv.id = uuid.uuid4()
    conv.user_id = user_id
    conv.character_id = FAKE_CHARACTER_ID
    conv.last_message_at = None
    return conv


def _make_profile(user_id: uuid.UUID = FAKE_USER_ID) -> MagicMock:
    profile = MagicMock()
    profile.id = user_id
    profile.mem0_user_id = str(user_id)
    profile.timezone = "UTC"
    profile.preferred_language = "en"
    return profile


def _make_allowed_result(augment: str | None = None) -> ModerationResult:
    return ModerationResult(
        allowed=True,
        reason=None,
        category=None,
        severity="none",
        augment_system_prompt=augment,
        blocked_until=None,
    )


def _make_blocked_result(
    reason: str = "Your message could not be sent. Please rephrase and try again.",
    category: str = "violence",
    severity: str = "high",
    blocked_until: datetime | None = None,
) -> ModerationResult:
    return ModerationResult(
        allowed=False,
        reason=reason,
        category=category,
        severity=severity,
        augment_system_prompt=None,
        blocked_until=blocked_until,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    yield AsyncMock()


def _make_auth_override(user_id: uuid.UUID = FAKE_USER_ID) -> Any:
    async def _override() -> MagicMock:
        profile = _make_profile(user_id)
        return profile

    return _override


@pytest_asyncio.fixture
async def auth_client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _make_auth_override()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: Moderation blocks returned as HTTP errors
# ---------------------------------------------------------------------------


class TestChatModerationHTTPErrors:
    """Verify that moderation failures result in correct HTTP status codes."""

    @pytest.mark.asyncio
    async def test_harmful_content_returns_400(
        self, auth_client: AsyncClient,
    ) -> None:
        """Messages blocked for harmful content return HTTP 400."""
        char = _make_character()
        conv = _make_conversation()
        blocked = _make_blocked_result()

        with patch("app.routes.chat.ChatService") as mock_service_cls:
            svc = MagicMock()
            svc.validate_send_message = AsyncMock(
                side_effect=__import__(
                    "fastapi", fromlist=["HTTPException"]
                ).HTTPException(
                    status_code=400,
                    detail="Your message could not be sent. Please rephrase and try again.",
                ),
            )
            mock_service_cls.return_value = svc

            resp = await auth_client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "harmful content"},
            )

        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert "rephrase" in detail.lower() or "could not be sent" in detail.lower()

    @pytest.mark.asyncio
    async def test_length_exceeded_returns_422_from_pydantic(
        self, auth_client: AsyncClient,
    ) -> None:
        """Messages over 4000 chars are rejected at Pydantic validation (422).

        The pydantic SendMessageRequest.content has max_length=4000.
        The moderation service defense-in-depth check is never reached because
        Pydantic rejects the request before it reaches the route handler.
        """
        resp = await auth_client.post(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            json={"content": "x" * 4001},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_length_exceeded_service_layer_returns_400(
        self, auth_client: AsyncClient,
    ) -> None:
        """Service-layer defense-in-depth returns 400 when content is too long.

        This can happen if the Pydantic check is bypassed (e.g., in-process
        calls). The service raises HTTPException(400) in this case.
        """
        from fastapi import HTTPException

        with patch("app.routes.chat.ChatService") as mock_service_cls:
            svc = MagicMock()
            svc.validate_send_message = AsyncMock(
                side_effect=HTTPException(
                    status_code=400,
                    detail="Message content exceeds maximum length of 4000 characters",
                ),
            )
            mock_service_cls.return_value = svc

            resp = await auth_client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "normal length message"},
            )

        assert resp.status_code == 400
        assert "4000" in resp.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_blocked_user_returns_403_with_blocked_until(
        self, auth_client: AsyncClient,
    ) -> None:
        """Blocked users receive HTTP 403 with blocked_until in response body."""
        from fastapi import HTTPException

        future = datetime.now(tz=UTC) + timedelta(minutes=30)
        blocked_until_str = future.isoformat()

        with patch("app.routes.chat.ChatService") as mock_service_cls:
            svc = MagicMock()
            svc.validate_send_message = AsyncMock(
                side_effect=HTTPException(
                    status_code=403,
                    detail={
                        "detail": "Message sending is temporarily disabled. Please try again later.",
                        "blocked_until": blocked_until_str,
                    },
                ),
            )
            mock_service_cls.return_value = svc

            resp = await auth_client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "hello"},
            )

        assert resp.status_code == 403
        body = resp.json()
        assert "blocked_until" in body.get("detail", {}) or "detail" in body

    @pytest.mark.asyncio
    async def test_allowed_message_proceeds_to_stream(
        self, auth_client: AsyncClient,
    ) -> None:
        """Clean message passes moderation and returns 200 with SSE stream."""

        async def _mock_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:
            yield 'data: {"type": "chunk", "content": "Hello!"}\n\n'
            yield 'data: {"type": "done", "message_id": "msg_001"}\n\n'

        with patch("app.routes.chat.ChatService") as mock_service_cls:
            svc = MagicMock()
            context = {
                "character": _make_character(),
                "conversation": _make_conversation(),
                "system_prompt": "You are helpful.",
                "formatted_messages": [{"role": "user", "content": "hello"}],
                "moderation_result": _make_allowed_result(),
            }
            svc.validate_send_message = AsyncMock(return_value=context)
            svc.stream_response = _mock_stream
            mock_service_cls.return_value = svc

            resp = await auth_client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello there"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self) -> None:
        """Request without auth token returns 401 (pre-moderation)."""
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as anon:
            resp = await anon.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests: ChatService.validate_send_message moderation integration
# ---------------------------------------------------------------------------


class TestValidateSendMessageModeration:
    """Unit tests for the moderation path inside ChatService.validate_send_message."""

    @pytest.mark.asyncio
    async def test_blocked_message_raises_400(self) -> None:
        """validate_send_message raises HTTPException(400) for harmful content."""
        from fastapi import HTTPException
        from app.services.chat_service import ChatService

        db = AsyncMock()
        service = ChatService(db)

        # Mock character lookup
        char = _make_character()
        char_result = MagicMock()
        char_result.scalar_one_or_none.return_value = char
        db.execute.return_value = char_result

        blocked = _make_blocked_result()
        with patch(
            "app.services.chat_service.ContentModerationService",
        ) as mock_mod_cls:
            mock_mod = AsyncMock()
            mock_mod.check_message.return_value = blocked
            mock_mod_cls.return_value = mock_mod

            with pytest.raises(HTTPException) as exc_info:
                await service.validate_send_message(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    profile=_make_profile(),
                    content="harmful content",
                )

        assert exc_info.value.status_code == 400
        assert "rephrase" in str(exc_info.value.detail).lower() or \
               "could not be sent" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_blocked_user_raises_403_with_blocked_until(self) -> None:
        """validate_send_message raises HTTPException(403) with blocked_until for blocked user."""
        from fastapi import HTTPException
        from app.services.chat_service import ChatService

        db = AsyncMock()
        service = ChatService(db)

        char = _make_character()
        char_result = MagicMock()
        char_result.scalar_one_or_none.return_value = char
        db.execute.return_value = char_result

        future = datetime.now(tz=UTC) + timedelta(minutes=60)
        blocked = _make_blocked_result(
            reason="Message sending is temporarily disabled. Please try again later.",
            category=None,
            severity="high",
            blocked_until=future,
        )

        with patch(
            "app.services.chat_service.ContentModerationService",
        ) as mock_mod_cls:
            mock_mod = AsyncMock()
            mock_mod.check_message.return_value = blocked
            mock_mod_cls.return_value = mock_mod

            with pytest.raises(HTTPException) as exc_info:
                await service.validate_send_message(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    profile=_make_profile(),
                    content="any message",
                )

        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert "blocked_until" in detail
        assert future.isoformat() == detail["blocked_until"]

    @pytest.mark.asyncio
    async def test_augment_system_prompt_appended(self) -> None:
        """Moderation augment_system_prompt is appended to the system prompt."""
        from app.services.chat_service import ChatService

        db = AsyncMock()
        service = ChatService(db)

        char = _make_character(template="therapist")
        # Support multiple execute() calls (character lookup, conversation lookup, etc.)
        char_result = MagicMock()
        char_result.scalar_one_or_none.return_value = char

        conv = _make_conversation()
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv

        msg_result = MagicMock()
        msg_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [char_result, conv_result, msg_result]

        crisis_augmentation = "CRITICAL SAFETY INSTRUCTION: The user may be in crisis."
        allowed_with_augment = _make_allowed_result(augment=crisis_augmentation)

        with patch(
            "app.services.chat_service.ContentModerationService",
        ) as mock_mod_cls, patch(
            "app.services.chat_service.ChatService._search_memories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            mock_mod = AsyncMock()
            mock_mod.check_message.return_value = allowed_with_augment
            mock_mod_cls.return_value = mock_mod

            context = await service.validate_send_message(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                profile=_make_profile(),
                content="I need help",
            )

        system_prompt = context["system_prompt"]
        assert crisis_augmentation in system_prompt

    @pytest.mark.asyncio
    async def test_moderation_check_runs_after_character_lookup(self) -> None:
        """Moderation check is called AFTER character lookup (needs template)."""
        from app.services.chat_service import ChatService

        db = AsyncMock()
        service = ChatService(db)

        char = _make_character(template="therapist")
        char_result = MagicMock()
        char_result.scalar_one_or_none.return_value = char
        db.execute.return_value = char_result

        call_order: list[str] = []

        original_get_active = service._get_active_character

        async def patched_get_active(cid: uuid.UUID) -> Any:
            call_order.append("character_lookup")
            return await original_get_active(cid)

        service._get_active_character = patched_get_active  # type: ignore[assignment]

        blocked = _make_blocked_result()
        with patch(
            "app.services.chat_service.ContentModerationService",
        ) as mock_mod_cls:
            mock_mod = AsyncMock()

            async def patched_check(*args: Any, **kwargs: Any) -> ModerationResult:
                call_order.append("moderation_check")
                return blocked

            mock_mod.check_message = patched_check
            mock_mod_cls.return_value = mock_mod

            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                await service.validate_send_message(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    profile=_make_profile(),
                    content="blocked content",
                )

        assert call_order == ["character_lookup", "moderation_check"]

    @pytest.mark.asyncio
    async def test_moderation_passed_character_template(self) -> None:
        """ContentModerationService.check_message receives the character's template."""
        from fastapi import HTTPException
        from app.services.chat_service import ChatService

        db = AsyncMock()
        service = ChatService(db)

        char = _make_character(template="therapist")
        char_result = MagicMock()
        char_result.scalar_one_or_none.return_value = char
        db.execute.return_value = char_result

        blocked = _make_blocked_result()
        captured_kwargs: dict[str, Any] = {}

        with patch(
            "app.services.chat_service.ContentModerationService",
        ) as mock_mod_cls:
            mock_mod = AsyncMock()

            async def capture_check(**kwargs: Any) -> ModerationResult:
                captured_kwargs.update(kwargs)
                return blocked

            mock_mod.check_message = capture_check
            mock_mod_cls.return_value = mock_mod

            with pytest.raises(HTTPException):
                await service.validate_send_message(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    profile=_make_profile(),
                    content="test content",
                )

        assert captured_kwargs.get("character_template") == "therapist"

    @pytest.mark.asyncio
    async def test_clean_message_context_contains_moderation_result(self) -> None:
        """Returned context dict includes moderation_result key."""
        from app.services.chat_service import ChatService

        db = AsyncMock()
        service = ChatService(db)

        char = _make_character()
        char_result = MagicMock()
        char_result.scalar_one_or_none.return_value = char

        conv = _make_conversation()
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv

        msg_result = MagicMock()
        msg_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [char_result, conv_result, msg_result]

        allowed = _make_allowed_result()

        with patch(
            "app.services.chat_service.ContentModerationService",
        ) as mock_mod_cls, patch(
            "app.services.chat_service.ChatService._search_memories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            mock_mod = AsyncMock()
            mock_mod.check_message.return_value = allowed
            mock_mod_cls.return_value = mock_mod

            context = await service.validate_send_message(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                profile=_make_profile(),
                content="Hello!",
            )

        assert "moderation_result" in context
        assert context["moderation_result"] is allowed


# ---------------------------------------------------------------------------
# Tests: SSE moderation event emission
# ---------------------------------------------------------------------------


class TestModerationSSEEvent:
    """Verify the moderation SSE event is emitted for therapist crisis.

    ChatService._llm_router is a @property so patch.object on an instance
    does not work. Instead, we pass a mock router via the constructor's
    llm_router parameter (the _llm_router_override path).
    """

    def _make_mock_router(self, chunks: list[str]) -> MagicMock:
        """Build a mock LLM router that yields the given text chunks."""
        mock_provider = MagicMock()

        async def _stream(*args: Any, **kwargs: Any) -> AsyncGenerator[str, None]:
            for chunk in chunks:
                yield chunk

        mock_provider.stream = _stream
        mock_router = MagicMock()
        mock_router.get.return_value = mock_provider
        return mock_router

    @pytest.mark.asyncio
    async def test_moderation_sse_event_emitted_for_therapist_crisis(self) -> None:
        """stream_response emits 'moderation' event for therapist with crisis augmentation."""
        from app.services.chat_service import ChatService

        db = AsyncMock()
        mock_router = self._make_mock_router(["Hello there"])
        service = ChatService(db, llm_router=mock_router)

        char = _make_character(template="therapist")
        conv = _make_conversation()
        profile = _make_profile()

        crisis_augmentation = "CRITICAL SAFETY INSTRUCTION: The user may be in crisis."
        moderation_result = _make_allowed_result(augment=crisis_augmentation)

        context = {
            "character": char,
            "conversation": conv,
            "system_prompt": f"You are a therapist.\n\n{crisis_augmentation}",
            "formatted_messages": [{"role": "user", "content": "I want to end my life"}],
            "moderation_result": moderation_result,
        }

        events: list[dict[str, Any]] = []
        with patch.object(service, "_extract_intent", new_callable=AsyncMock, return_value=None):
            async for raw in service.stream_response(
                context=context,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="I want to end my life",
                media_url=None,
            ):
                if raw.startswith("data: "):
                    events.append(json.loads(raw[6:]))

        moderation_events = [e for e in events if e.get("type") == "moderation"]
        assert len(moderation_events) == 1
        assert "message" in moderation_events[0]
        assert "988" in moderation_events[0]["message"]

    @pytest.mark.asyncio
    async def test_moderation_sse_event_not_emitted_for_non_therapist(self) -> None:
        """stream_response does NOT emit 'moderation' event for non-therapist character."""
        from app.services.chat_service import ChatService

        db = AsyncMock()
        mock_router = self._make_mock_router(["Hi!"])
        service = ChatService(db, llm_router=mock_router)

        char = _make_character(template="companion")  # NOT therapist
        conv = _make_conversation()
        profile = _make_profile()

        crisis_augmentation = "CRITICAL SAFETY INSTRUCTION: The user may be in crisis."
        moderation_result = _make_allowed_result(augment=crisis_augmentation)

        context = {
            "character": char,
            "conversation": conv,
            "system_prompt": "You are a companion.",
            "formatted_messages": [{"role": "user", "content": "hello"}],
            "moderation_result": moderation_result,
        }

        events: list[dict[str, Any]] = []
        with patch.object(service, "_extract_intent", new_callable=AsyncMock, return_value=None):
            async for raw in service.stream_response(
                context=context,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="hello",
                media_url=None,
            ):
                if raw.startswith("data: "):
                    events.append(json.loads(raw[6:]))

        moderation_events = [e for e in events if e.get("type") == "moderation"]
        assert len(moderation_events) == 0

    @pytest.mark.asyncio
    async def test_moderation_sse_event_not_emitted_when_no_augment(self) -> None:
        """stream_response does NOT emit 'moderation' event when no augmentation."""
        from app.services.chat_service import ChatService

        db = AsyncMock()
        mock_router = self._make_mock_router(["I am well!"])
        service = ChatService(db, llm_router=mock_router)

        char = _make_character(template="therapist")
        conv = _make_conversation()
        profile = _make_profile()

        # augment_system_prompt is None — no crisis detected
        moderation_result = _make_allowed_result(augment=None)

        context = {
            "character": char,
            "conversation": conv,
            "system_prompt": "You are a therapist.",
            "formatted_messages": [{"role": "user", "content": "how are you"}],
            "moderation_result": moderation_result,
        }

        events: list[dict[str, Any]] = []
        with patch.object(service, "_extract_intent", new_callable=AsyncMock, return_value=None):
            async for raw in service.stream_response(
                context=context,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="how are you",
                media_url=None,
            ):
                if raw.startswith("data: "):
                    events.append(json.loads(raw[6:]))

        moderation_events = [e for e in events if e.get("type") == "moderation"]
        assert len(moderation_events) == 0

    @pytest.mark.asyncio
    async def test_moderation_sse_event_emitted_before_chunks(self) -> None:
        """Moderation event must appear before chunk events in the stream."""
        from app.services.chat_service import ChatService

        db = AsyncMock()
        mock_router = self._make_mock_router(["chunk1", "chunk2"])
        service = ChatService(db, llm_router=mock_router)

        char = _make_character(template="therapist")
        conv = _make_conversation()
        profile = _make_profile()

        crisis_augmentation = "CRITICAL SAFETY INSTRUCTION"
        moderation_result = _make_allowed_result(augment=crisis_augmentation)

        context = {
            "character": char,
            "conversation": conv,
            "system_prompt": f"Therapist.\n\n{crisis_augmentation}",
            "formatted_messages": [{"role": "user", "content": "crisis msg"}],
            "moderation_result": moderation_result,
        }

        events: list[dict[str, Any]] = []
        with patch.object(service, "_extract_intent", new_callable=AsyncMock, return_value=None):
            async for raw in service.stream_response(
                context=context,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="crisis msg",
                media_url=None,
            ):
                if raw.startswith("data: "):
                    events.append(json.loads(raw[6:]))

        types = [e["type"] for e in events]
        assert types[0] == "moderation", f"Expected moderation first, got: {types}"
        assert "chunk" in types
        assert types[-1] == "done"
