"""Schema-level tests for media upload Pydantic models.

Tests UploadUrlRequest validation (filename, content_type, type) and
UploadUrlResponse serialization.
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

from app.schemas.media import UploadUrlRequest, UploadUrlResponse  # noqa: E402


class TestUploadUrlRequest:
    """Tests for UploadUrlRequest schema validation."""

    def test_valid_request(self) -> None:
        """T1: All valid fields parse successfully."""
        req = UploadUrlRequest(
            filename="meal.jpg",
            content_type="image/jpeg",
            type="photo",
        )
        assert req.filename == "meal.jpg"
        assert req.content_type == "image/jpeg"
        assert req.type == "photo"

    def test_missing_filename_raises(self) -> None:
        """T2: Missing filename raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                content_type="image/jpeg",
                type="photo",
            )  # type: ignore[call-arg]

    def test_missing_content_type_raises(self) -> None:
        """T3: Missing content_type raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="meal.jpg",
                type="photo",
            )  # type: ignore[call-arg]

    def test_missing_type_raises(self) -> None:
        """T4: Missing type raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="meal.jpg",
                content_type="image/jpeg",
            )  # type: ignore[call-arg]

    def test_invalid_type_raises(self) -> None:
        """T5: type='video' (invalid) raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="video.mp4",
                content_type="video/mp4",
                type="video",  # type: ignore[arg-type]
            )

    def test_empty_filename_raises(self) -> None:
        """T6: Empty filename raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="",
                content_type="image/jpeg",
                type="photo",
            )

    def test_filename_with_path_traversal_raises(self) -> None:
        """T7: Filename containing '..' raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="../../etc/passwd",
                content_type="image/jpeg",
                type="photo",
            )

    def test_response_serializes_correctly(self) -> None:
        """T8: UploadUrlResponse serializes both fields as strings."""
        resp = UploadUrlResponse(
            upload_url="https://bucket.s3.us-east-1.amazonaws.com/photo/uid/uuid_file.jpg?sig=abc",
            file_url="https://bucket.s3.us-east-1.amazonaws.com/photo/uid/uuid_file.jpg",
        )
        data = resp.model_dump()
        assert isinstance(data["upload_url"], str)
        assert isinstance(data["file_url"], str)
        assert "sig=abc" in data["upload_url"]
        assert "sig=abc" not in data["file_url"]

    def test_filename_exceeding_255_chars_raises(self) -> None:
        """T9: Filename exceeding 255 chars raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="a" * 256,
                content_type="image/jpeg",
                type="photo",
            )

    def test_filename_strips_whitespace(self) -> None:
        """T10: Filename with leading/trailing whitespace is trimmed."""
        req = UploadUrlRequest(
            filename="  meal.jpg  ",
            content_type="image/jpeg",
            type="photo",
        )
        assert req.filename == "meal.jpg"

    def test_filename_whitespace_only_raises(self) -> None:
        """T11: Filename that is only whitespace raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="   ",
                content_type="image/jpeg",
                type="photo",
            )

    def test_filename_with_forward_slash_raises(self) -> None:
        """T12: Filename with forward slash raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="path/file.jpg",
                content_type="image/jpeg",
                type="photo",
            )

    def test_filename_with_backslash_raises(self) -> None:
        """T13: Filename with backslash raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="path\\file.jpg",
                content_type="image/jpeg",
                type="photo",
            )

    def test_filename_with_null_byte_raises(self) -> None:
        """T14: Filename with null byte raises ValidationError."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="file\x00.jpg",
                content_type="image/jpeg",
                type="photo",
            )

    def test_all_valid_types(self) -> None:
        """T15: All three valid types parse successfully."""
        for media_type in ("photo", "audio", "tts"):
            req = UploadUrlRequest(
                filename="test.file",
                content_type="image/jpeg",
                type=media_type,  # type: ignore[arg-type]
            )
            assert req.type == media_type
