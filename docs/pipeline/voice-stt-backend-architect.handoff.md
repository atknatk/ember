# Architect Handoff: Voice STT Backend (P05-02)

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Summary

Designed the POST /api/v1/stt endpoint for speech-to-text transcription using
OpenAI Whisper API. The endpoint downloads audio from S3, validates format and
size, transcribes via Whisper, and returns transcript with language detection.

## Spec Location

`shared/feature-specs/voice-stt-backend.md`

## Key Decisions

- Stateless endpoint: no new database tables needed
- Audio downloaded from S3 (not direct upload to endpoint) to stay consistent
  with the existing media upload flow (P01-10)
- Supported formats: M4A, MP3, WAV, OGG (Whisper supports all four)
- 25MB max file size (Whisper API hard limit)
- OpenAI Whisper SDK calls wrapped in asyncio.to_thread (sync SDK)
- Follows existing TTS route/service patterns for consistency

## Files for Backend Dev

- `backend/app/routes/stt.py` — route handler
- `backend/app/services/stt_service.py` — business logic
- `backend/app/schemas/stt.py` — Pydantic schemas
- `backend/app/main.py` — register router
- `shared/api-contracts/paths/stt.yaml` — OpenAPI path
- `shared/api-contracts/schemas/stt.yaml` — OpenAPI schemas
- `shared/api-contracts/ember-api.yaml` — add STT path reference
