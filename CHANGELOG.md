# Changelog

All notable changes to Ember will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [Unreleased]

### Added
- Initial project scaffold (monorepo: backend + ios + android)
- Architecture documentation (17 docs, 6 ADRs)
- AI agent pipeline setup (.claude/agents/ + pipeline-run skill)
- Feature queue for all 12 phases
- [P01-01] FastAPI project scaffold with health endpoint, Docker setup, and dev tooling
- [P01-02] SQLAlchemy async models for all 7 domain tables with Alembic migration
- [P01-03] AWS Cognito JWT authentication middleware with JWKS caching
- [P01-04] Auth endpoints: register, login, refresh with Cognito integration
- [P01-05] Character CRUD endpoints with Claude Haiku prompt generation
- [P01-06] SSE streaming chat endpoint with Claude AI integration, Mem0 memory, and device action intents
- [P01-07] Composite cursor-based message pagination with (created_at, id) tiebreaker
- [P01-08] Mem0 memory management endpoints (list, delete, clear per character + global memories)
- [P01-09] Onboarding endpoint with Claude Haiku memory conversion and Mem0 seeding
- [P01-10] S3 presigned URL media upload endpoint with content type validation and filename sanitization
- [P1.5-01] Per-user rate limiting middleware with configurable limits per endpoint group (chat/write/read)
- [P1.5-02] Profile CRUD endpoints (GET/PUT profile, DELETE account with GDPR-compliant cascading deletion)
- [P1.5-03] Observability stack: structured logging (structlog), request ID middleware, Sentry error tracking, external API call timing
- [P1.5-04] Mem0 circuit breaker with local cache fallback and retry queue
- [P1.5-05] LLM provider abstraction layer (ADR-006) with Anthropic/OpenAI providers and router
- [P1.5-06] OpenAPI 3.1 specs for all 19 endpoints with drift detection CI
- [P1.5-07] Resolve 26 doc-code contradictions and add CI drift detection
- [P1.5-08] Global memory deletion endpoint with ownership validation
- [P02-01] Activity tracking middleware with background upsert for user_activity
- [P02-05] Content moderation pipeline with abuse escalation and therapist crisis detection
- [P02-02] APScheduler-based notification scheduler with timezone-aware triggers and midnight reset
- [P02-03] Firebase Cloud Messaging push notification service with token management endpoints
- [P02-04] Proactive message generator with Mem0 + Claude Haiku personalization and in-memory caching
- [P03-01] iOS scaffold with SwiftUI app entry, tab navigation, and design system
- [P03-02] iOS network layer with APIClient, SSE streaming, and 401 retry
- [P03-03] iOS Cognito auth with Keychain token storage, LoginView, SignUpView, and transparent token refresh
- [P03-04] iOS onboarding flow with 3-page welcome carousel and 7-question personalization cards that seed Mem0 memories before the first AI conversation
- [P03-05] iOS auth screen polish: animated Login/SignUp transitions, error shake micro-animation, fade-in on appear, inline email validation, password visibility toggles, and VoiceOver accessibility hints
- [P03-06] iOS Home View with character grid, daily summary card, and add-character navigation
- [P03-07] iOS Chat View with SSE streaming, message bubbles, typing indicator, and cursor-based message pagination
- [P03-08] iOS Memory List with per-character and global Mem0 memories, segment picker, and swipe-to-delete
- [P03-09] iOS Profile View with user info, preferences, notification toggles, sign out, and account deletion
- [P03-10] iOS design polish with shimmer skeletons, card shadows, scale button style, pull-to-refresh, and micro-interactions
- [P03-11] iOS error handling with EmberError enum, error banners, network monitor, offline detection, and retry logic
- [P04-01] Android scaffold with Jetpack Compose, Material 3 dark theme, bottom navigation, and design system tokens matching iOS
- [P04-02] Android auth with login/sign-up screens, EncryptedSharedPreferences token storage, OkHttp 401 auto-refresh interceptor
- [P04-03] Android onboarding with 3-page welcome carousel, 7 personalization question cards, and Mem0 memory seeding
- [P04-04] Android home screen with character grid, daily summary card, greeting header, and unread tracking
- [P04-05] Android chat with OkHttp SSE streaming, message bubbles, typing indicator, and cursor-based pagination
- [P04-06] Android memory list with per-character and global Mem0 memories, segment picker, and swipe-to-delete
- [P04-07] Android profile with user info, timezone picker, notification toggles, avatar upload, sign out, and account deletion
- [P04-08] Android design polish with shimmer skeletons, card elevation, scale button effects, and micro-interactions
- [P04-09] Android error handling with EmberError sealed class, error banners, network monitor, offline detection, and retry logic
- [P05-01] Backend TTS service with ElevenLabs Flash v2.5 primary and AWS Polly fallback, circuit breaker, and S3 audio caching

---

<!-- Releases will be added here as phases complete -->
