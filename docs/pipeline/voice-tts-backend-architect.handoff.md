# Architect Handoff: Voice TTS Backend

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Design Decisions

1. ElevenLabs Flash v2.5 as primary TTS provider (multilingual, 135ms TTFA)
2. AWS Polly Neural as fallback (Burcu for Turkish, Joanna for English)
3. Hybrid routing: short texts (< 150 chars) go to Polly, longer to ElevenLabs
4. Dedicated circuit breaker for ElevenLabs (separate from Mem0)
5. Hash-based S3 caching for audio deduplication
6. Single endpoint: POST /api/v1/tts

## Spec Location

`shared/feature-specs/voice-tts-backend.md`
