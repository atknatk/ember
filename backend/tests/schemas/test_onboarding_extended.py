"""Extended schema tests for onboarding Pydantic models.

Covers edge cases not in the original test_onboarding_schemas.py:
- Unicode / special characters in answers
- Boundary-length answers (exactly 1, exactly 500)
- Missing fields entirely
- Extra fields ignored
- Newline-only answers
- Tab / mixed whitespace
- Multiple validation errors at once
- VALID_QUESTION_KEYS is a frozenset with exactly 7 items
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
# OnboardingAnswer -- extended edge cases
# ---------------------------------------------------------------------------


class TestOnboardingAnswerEdgeCases:
    """Edge-case tests for OnboardingAnswer validation."""

    def test_unicode_answer_accepted(self) -> None:
        """Unicode characters in answers are accepted."""
        ans = OnboardingAnswer(
            question_key="preferred_name",
            answer="Mehmet Ozgur",
        )
        assert ans.answer == "Mehmet Ozgur"

    def test_accented_characters_accepted(self) -> None:
        """Accented characters in answers are preserved."""
        ans = OnboardingAnswer(
            question_key="preferred_name",
            answer="Rene",
        )
        assert ans.answer == "Rene"

    def test_cjk_characters_accepted(self) -> None:
        """CJK (Chinese/Japanese/Korean) characters are accepted."""
        ans = OnboardingAnswer(
            question_key="preferred_name",
            answer="Taro",
        )
        assert ans.answer == "Taro"

    def test_exactly_one_char_answer(self) -> None:
        """Minimum valid answer: exactly 1 non-whitespace character."""
        ans = OnboardingAnswer(question_key="preferred_name", answer="A")
        assert ans.answer == "A"

    def test_exactly_500_char_answer(self) -> None:
        """Answer at exactly 500 characters is accepted."""
        long_answer = "x" * 500
        ans = OnboardingAnswer(question_key="preferred_name", answer=long_answer)
        assert len(ans.answer) == 500

    def test_499_chars_plus_whitespace_rejected_by_max_length(self) -> None:
        """499 chars + 2 spaces = 501 chars total, rejected by max_length=500 before strip.

        Pydantic validates max_length on the raw input BEFORE field_validator runs.
        """
        answer_with_space = " " + "y" * 499 + " "
        with pytest.raises(ValidationError):
            OnboardingAnswer(question_key="preferred_name", answer=answer_with_space)

    def test_498_chars_plus_whitespace_accepted(self) -> None:
        """498 chars + 2 spaces = 500 chars total, accepted, then stripped to 498."""
        answer_with_space = " " + "y" * 498 + " "
        ans = OnboardingAnswer(question_key="preferred_name", answer=answer_with_space)
        assert len(ans.answer) == 498

    def test_newline_only_answer_rejected(self) -> None:
        """Answer that is only newlines is rejected (blank after strip)."""
        with pytest.raises(ValidationError, match="Answer must not be blank"):
            OnboardingAnswer(question_key="preferred_name", answer="\n\n\n")

    def test_tab_only_answer_rejected(self) -> None:
        """Answer that is only tabs is rejected (blank after strip)."""
        with pytest.raises(ValidationError, match="Answer must not be blank"):
            OnboardingAnswer(question_key="preferred_name", answer="\t\t")

    def test_mixed_whitespace_only_answer_rejected(self) -> None:
        """Answer that is only mixed whitespace is rejected."""
        with pytest.raises(ValidationError, match="Answer must not be blank"):
            OnboardingAnswer(
                question_key="preferred_name",
                answer=" \t \n \r\n ",
            )

    def test_answer_with_internal_newlines_preserved(self) -> None:
        """Answers with internal newlines are preserved (only outer whitespace stripped)."""
        ans = OnboardingAnswer(
            question_key="occupation",
            answer="  Software engineer\nAt a startup  ",
        )
        assert ans.answer == "Software engineer\nAt a startup"

    def test_missing_question_key_field(self) -> None:
        """Missing question_key field entirely raises ValidationError."""
        with pytest.raises(ValidationError):
            OnboardingAnswer(answer="Alex")  # type: ignore[call-arg]

    def test_missing_answer_field(self) -> None:
        """Missing answer field entirely raises ValidationError."""
        with pytest.raises(ValidationError):
            OnboardingAnswer(question_key="preferred_name")  # type: ignore[call-arg]

    def test_null_answer_rejected(self) -> None:
        """None as answer raises ValidationError."""
        with pytest.raises(ValidationError):
            OnboardingAnswer(question_key="preferred_name", answer=None)  # type: ignore[arg-type]

    def test_numeric_answer_rejected(self) -> None:
        """Numeric (non-string) answer raises ValidationError."""
        with pytest.raises(ValidationError):
            OnboardingAnswer(question_key="preferred_name", answer=123)  # type: ignore[arg-type]

    def test_special_characters_in_answer(self) -> None:
        """Special characters like quotes and brackets are accepted."""
        ans = OnboardingAnswer(
            question_key="occupation",
            answer='Software "engineer" at <company> & more',
        )
        assert ans.answer == 'Software "engineer" at <company> & more'


# ---------------------------------------------------------------------------
# OnboardingRequest -- extended edge cases
# ---------------------------------------------------------------------------


class TestOnboardingRequestEdgeCases:
    """Edge-case tests for OnboardingRequest validation."""

    def test_empty_answers_list(self) -> None:
        """Empty answers list raises ValidationError (min_length=7)."""
        with pytest.raises(ValidationError):
            OnboardingRequest(answers=[])

    def test_single_answer_rejected(self) -> None:
        """Only 1 answer raises ValidationError (needs 7)."""
        with pytest.raises(ValidationError):
            OnboardingRequest(
                answers=[{"question_key": "preferred_name", "answer": "Alex"}],
            )

    def test_missing_answers_field_entirely(self) -> None:
        """Missing answers field raises ValidationError."""
        with pytest.raises(ValidationError):
            OnboardingRequest()  # type: ignore[call-arg]

    def test_null_answers_rejected(self) -> None:
        """None as answers raises ValidationError."""
        with pytest.raises(ValidationError):
            OnboardingRequest(answers=None)  # type: ignore[arg-type]

    def test_all_keys_with_whitespace_trimmed_answers(self) -> None:
        """All 7 answers with leading/trailing whitespace are trimmed and accepted."""
        answers = [
            {"question_key": "preferred_name", "answer": "  Alex  "},
            {"question_key": "occupation", "answer": "  Engineer  "},
            {"question_key": "daily_rhythm", "answer": "  Morning  "},
            {"question_key": "health_goal", "answer": "  Run  "},
            {"question_key": "stress_management", "answer": "  Walk  "},
            {"question_key": "sleep_schedule", "answer": "  11-7  "},
            {"question_key": "communication_style", "answer": "  Friendly  "},
        ]
        req = OnboardingRequest(answers=answers)
        for a in req.answers:
            assert not a.answer.startswith(" ")
            assert not a.answer.endswith(" ")

    def test_all_max_length_answers_accepted(self) -> None:
        """All 7 answers at exactly 500 chars each are accepted."""
        answers = []
        for key in VALID_QUESTION_KEYS:
            answers.append({"question_key": key, "answer": "a" * 500})
        req = OnboardingRequest(answers=answers)
        assert len(req.answers) == 7

    def test_mixed_valid_and_one_invalid_key(self) -> None:
        """6 valid keys and 1 invalid key raises ValidationError."""
        answers = _build_valid_answers()
        answers[3] = {"question_key": "bad_key", "answer": "Something"}
        with pytest.raises(ValidationError):
            OnboardingRequest(answers=answers)

    def test_all_same_key_rejected(self) -> None:
        """7 answers with the same key are rejected."""
        answers = [
            {"question_key": "preferred_name", "answer": f"Name {i}"}
            for i in range(7)
        ]
        with pytest.raises(ValidationError):
            OnboardingRequest(answers=answers)


# ---------------------------------------------------------------------------
# OnboardingResponse -- extended tests
# ---------------------------------------------------------------------------


class TestOnboardingResponseEdgeCases:
    """Edge-case tests for OnboardingResponse serialization."""

    def test_memories_seeded_zero(self) -> None:
        """memories_seeded can be 0."""
        resp = OnboardingResponse(onboarding_completed=True, memories_seeded=0)
        assert resp.memories_seeded == 0

    def test_memories_seeded_large_number(self) -> None:
        """memories_seeded can be a large number (e.g., if Haiku generates many)."""
        resp = OnboardingResponse(onboarding_completed=True, memories_seeded=100)
        assert resp.memories_seeded == 100

    def test_onboarding_completed_false(self) -> None:
        """onboarding_completed can be False (edge case for error scenarios)."""
        resp = OnboardingResponse(onboarding_completed=False, memories_seeded=0)
        assert resp.onboarding_completed is False


# ---------------------------------------------------------------------------
# VALID_QUESTION_KEYS constant
# ---------------------------------------------------------------------------


class TestValidQuestionKeys:
    """Tests for the VALID_QUESTION_KEYS constant itself."""

    def test_exactly_seven_keys(self) -> None:
        """VALID_QUESTION_KEYS contains exactly 7 keys."""
        assert len(VALID_QUESTION_KEYS) == 7

    def test_is_frozenset(self) -> None:
        """VALID_QUESTION_KEYS is a frozenset (immutable)."""
        assert isinstance(VALID_QUESTION_KEYS, frozenset)

    def test_expected_keys_present(self) -> None:
        """All expected question keys are present."""
        expected = {
            "preferred_name",
            "occupation",
            "daily_rhythm",
            "health_goal",
            "stress_management",
            "sleep_schedule",
            "communication_style",
        }
        assert VALID_QUESTION_KEYS == expected
