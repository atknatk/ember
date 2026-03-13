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

---

<!-- Releases will be added here as phases complete -->
