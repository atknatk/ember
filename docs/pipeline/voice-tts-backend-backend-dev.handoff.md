# Backend Dev Handoff: Voice TTS Backend

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files
- `backend/app/routes/tts.py` -- 1 endpoint (POST /api/v1/tts)
- `backend/app/services/tts_service.py` -- TTSService + ElevenLabsCircuitBreaker
- `backend/app/schemas/tts.py` -- 2 schemas (TTSRequest, TTSResponse)
- `backend/app/main.py` -- Updated to register tts router
- `shared/api-contracts/paths/tts.yaml` -- OpenAPI path definition
- `shared/api-contracts/schemas/tts.yaml` -- OpenAPI schema definitions
- `shared/api-contracts/ember-api.yaml` -- Updated with /tts path and tts tag
- `docs/standards/backend.md` -- Updated project structure

## Endpoints Implemented
- `POST /api/v1/tts` -- Convert text to speech, returns S3 audio URL

## Test Results
- pytest: 42 new tests passed (2499 total, 0 failed)
- ruff: clean
- mypy: clean
- No hardcoded secrets

## Test Files
- `backend/tests/schemas/test_tts.py` -- 15 schema validation tests
- `backend/tests/services/test_tts.py` -- 18 service tests (circuit breaker, synthesis, caching, ownership)
- `backend/tests/routes/test_tts.py` -- 9 route integration tests
- `backend/tests/test_openapi_validation.py` -- Updated endpoint count (16 -> 17)
- `backend/tests/test_openapi_yaml.py` -- Updated endpoint count (22 -> 23) and tags

## Known Issues / Deviations from Spec
- `duration_seconds` is always `null` in current implementation. ElevenLabs does not return duration in the streaming response. Future enhancement could compute duration from the MP3 data or add ffprobe.
- The GitHub issue #37 description mentions STT (stt-endpoint), not TTS. The task description from the pipeline run specifies TTS implementation which is what was built.

## Notes for Backend Tester
- Mock `app.services.tts_service._s3_client` for all S3 tests
- Mock `app.services.tts_service._polly_client` for Polly tests
- Mock `app.services.tts_service.httpx.AsyncClient` for ElevenLabs tests
- Reset `app.services.tts_service._elevenlabs_breaker = None` before each circuit breaker test
- The `_synthesize_audio` method has the hybrid routing logic (short vs long text) -- test both paths
- Test ElevenLabs -> Polly fallback by making httpx mock raise an exception
