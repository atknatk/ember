"""Chat streaming route handlers.

Provides endpoints for sending messages (SSE streaming response) and
retrieving paginated message history. All endpoints require JWT
authentication. Business logic is delegated to ChatService.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.chat import MessageListResponse, SendMessageRequest
from app.services.chat_service import ChatService, MessageCursor, _decode_cursor

router = APIRouter()


@router.post("/{character_id}/messages")
async def send_message(
    character_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send a message to a character and stream the AI response via SSE.

    Validation (character lookup, ownership check, context gathering) runs
    BEFORE the StreamingResponse is created so that HTTPExceptions result
    in proper 4xx JSON error responses. The streaming generator only runs
    after validation succeeds.
    """
    service = ChatService(db)

    # Validate and prepare context — may raise 403/404
    context = await service.validate_send_message(
        character_id=character_id,
        user_id=current_user.id,
        profile=current_user,
        content=body.content,
    )

    return StreamingResponse(
        service.stream_response(
            context=context,
            user_id=current_user.id,
            profile=current_user,
            content=body.content,
            media_url=body.media_url,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{character_id}/messages",
    response_model=MessageListResponse,
)
async def get_messages(
    character_id: uuid.UUID,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> MessageListResponse:
    """Retrieve paginated message history for a character's conversation.

    Uses cursor-based pagination with composite (created_at, id) cursors
    encoded as base64 URL-safe JSON. Messages are returned newest-first.
    Pass the ``next_cursor`` from a previous response as the ``cursor``
    query parameter to load the next page.
    """
    # Decode composite cursor from base64 JSON — raises 400 on invalid format
    parsed_cursor: MessageCursor | None = None
    if cursor is not None:
        parsed_cursor = _decode_cursor(cursor)

    service = ChatService(db)
    return await service.get_messages(
        character_id=character_id,
        user_id=current_user.id,
        cursor=parsed_cursor,
        limit=limit,
    )
