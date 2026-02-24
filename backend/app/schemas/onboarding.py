"""Pydantic request/response schemas for the onboarding endpoint.

Covers the POST /api/v1/onboarding/complete request validation
(7 required Q&A pairs) and the success response.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_QUESTION_KEYS: frozenset[str] = frozenset({
    "preferred_name",
    "occupation",
    "daily_rhythm",
    "health_goal",
    "stress_management",
    "sleep_schedule",
    "communication_style",
})

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class OnboardingAnswer(BaseModel):
    """A single Q&A pair from the onboarding flow."""

    question_key: str
    answer: str = Field(..., min_length=1, max_length=500)

    @field_validator("question_key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Reject unknown question keys."""
        if v not in VALID_QUESTION_KEYS:
            msg = f"Invalid question_key: {v}"
            raise ValueError(msg)
        return v

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, v: str) -> str:
        """Strip whitespace and reject blank answers."""
        stripped = v.strip()
        if not stripped:
            msg = "Answer must not be blank"
            raise ValueError(msg)
        return stripped


class OnboardingRequest(BaseModel):
    """Request body for POST /api/v1/onboarding/complete."""

    answers: list[OnboardingAnswer] = Field(..., min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_all_keys_present(self) -> Self:
        """Ensure all 7 question keys are present with no duplicates."""
        keys = {a.question_key for a in self.answers}
        if keys != VALID_QUESTION_KEYS:
            missing = VALID_QUESTION_KEYS - keys
            msg = f"Missing question keys: {', '.join(sorted(missing))}"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class OnboardingResponse(BaseModel):
    """Response for POST /api/v1/onboarding/complete."""

    onboarding_completed: bool
    memories_seeded: int
