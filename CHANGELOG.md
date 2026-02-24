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

---

<!-- Releases will be added here as phases complete -->
