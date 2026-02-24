"""Unit tests for onboarding Pydantic schemas.

Tests validation of OnboardingAnswer, OnboardingRequest, and
OnboardingResponse models, covering all edge cases for question keys,
answer content, and the 7-key completeness constraint.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.onboarding import (  # noqa: E402
    VALID_QUESTION_KEYS,
    OnboardingAnswer,
    OnboardingRequest,
    OnboardingResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_valid_answers() -> list[dict[str, str]]:
    """Return a minimal valid set of 7 onboarding answers as dicts."""
    return [
        {"question_key": "preferred_name", "answer": "Alex"},
        {"question_key": "occupation", "answer": "Software engineer"},
        {"question_key": "daily_rhythm", "answer": "Morning person"},
        {"question_key": "health_goal", "answer": "Lose 10 kg"},
        {"question_key": "stress_management", "answer": "Walks and podcasts"},
        {"question_key": "sleep_schedule", "answer": "11 PM to 6:30 AM"},
        {"question_key": "communication_style", "answer": "Check in but don't overwhelm"},
    ]


# ---------------------------------------------------------------------------
# OnboardingAnswer tests
# ---------------------------------------------------------------------------


class TestOnboardingAnswer:
    """Tests for the OnboardingAnswer model."""

    def test_valid_answer(self) -> None:
        """T1 partial: A valid answer is accepted."""
        ans = OnboardingAnswer(question_key="preferred_name", answer="Alex")
        assert ans.question_key == "preferred_name"
        assert ans.answer == "Alex"

    def test_invalid_question_key(self) -> None:
        """T4: Invalid question_key raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid question_key"):
            OnboardingAnswer(question_key="favorite_color", answer="Blue")

    def test_whitespace_only_answer(self) -> None:
        """T5: Answer that is whitespace only raises ValidationError."""
        with pytest.raises(ValidationError, match="Answer must not be blank"):
            OnboardingAnswer(question_key="preferred_name", answer="   ")

    def test_answer_exceeding_500_chars(self) -> None:
        """T6: Answer exceeding 500 characters raises ValidationError."""
        long_answer = "x" * 501
        with pytest.raises(ValidationError):
            OnboardingAnswer(question_key="preferred_name", answer=long_answer)

    def test_strip_answer_trims_whitespace(self) -> None:
        """T7: Whitespace is stripped from valid answers."""
        ans = OnboardingAnswer(question_key="preferred_name", answer="  Alex  ")
        assert ans.answer == "Alex"

    def test_empty_string_answer(self) -> None:
        """Empty string answer raises ValidationError."""
        with pytest.raises(ValidationError):
            OnboardingAnswer(question_key="preferred_name", answer="")

    def test_all_valid_keys_accepted(self) -> None:
        """Every valid question key is accepted."""
        for key in VALID_QUESTION_KEYS:
            ans = OnboardingAnswer(question_key=key, answer="Some answer")
            assert ans.question_key == key


# ---------------------------------------------------------------------------
# OnboardingRequest tests
# ---------------------------------------------------------------------------


class TestOnboardingRequest:
    """Tests for the OnboardingRequest model."""

    def test_valid_request_with_all_keys(self) -> None:
        """T1: Valid request with all 7 keys passes validation."""
        req = OnboardingRequest(answers=_build_valid_answers())
        assert len(req.answers) == 7

    def test_missing_one_key(self) -> None:
        """T2: 6 answers (missing one key) raises ValidationError."""
        answers = _build_valid_answers()[:6]
        with pytest.raises(ValidationError):
            OnboardingRequest(answers=answers)

    def test_duplicate_key(self) -> None:
        """T3: 8 answers (duplicate key) raises ValidationError due to max_length=7."""
        answers = _build_valid_answers()
        answers.append({"question_key": "preferred_name", "answer": "Another Name"})
        with pytest.raises(ValidationError):
            OnboardingRequest(answers=answers)

    def test_duplicate_key_same_count(self) -> None:
        """Duplicate key with 7 items but missing another key raises ValidationError."""
        answers = _build_valid_answers()
        # Replace communication_style with a duplicate preferred_name
        answers[6] = {"question_key": "preferred_name", "answer": "Duplicate"}
        with pytest.raises(ValidationError, match="Missing question keys"):
            OnboardingRequest(answers=answers)

    def test_invalid_key_in_answers(self) -> None:
        """T4: Invalid question_key within the answers raises ValidationError."""
        answers = _build_valid_answers()
        answers[0] = {"question_key": "invalid_key", "answer": "Value"}
        with pytest.raises(ValidationError):
            OnboardingRequest(answers=answers)

    def test_order_does_not_matter(self) -> None:
        """Answers can be in any order and still validate."""
        answers = list(reversed(_build_valid_answers()))
        req = OnboardingRequest(answers=answers)
        assert len(req.answers) == 7


# ---------------------------------------------------------------------------
# OnboardingResponse tests
# ---------------------------------------------------------------------------


class TestOnboardingResponse:
    """Tests for the OnboardingResponse model."""

    def test_response_serializes_correctly(self) -> None:
        """T8: Response serializes as expected."""
        resp = OnboardingResponse(onboarding_completed=True, memories_seeded=7)
        data = resp.model_dump()
        assert data == {"onboarding_completed": True, "memories_seeded": 7}

    def test_response_json(self) -> None:
        """Response produces correct JSON string."""
        resp = OnboardingResponse(onboarding_completed=True, memories_seeded=7)
        json_str = resp.model_dump_json()
        assert '"onboarding_completed":true' in json_str
        assert '"memories_seeded":7' in json_str
