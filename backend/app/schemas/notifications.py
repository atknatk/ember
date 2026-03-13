"""Pydantic request/response schemas for notification endpoints.

Covers PUT /api/v1/notifications/token and DELETE /api/v1/notifications/token.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FcmTokenRequest(BaseModel):
    """Request body for PUT /api/v1/notifications/token.

    Validates that the FCM token is a non-empty string of at most 4096 characters.
    FCM tokens are typically 150-200 characters; the generous limit prevents abuse
    while accommodating future token format changes.
    """

    fcm_token: str = Field(..., min_length=1, max_length=4096)


class FcmTokenResponse(BaseModel):
    """Response body for PUT /api/v1/notifications/token."""

    status: str
