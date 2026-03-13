# Architect Handoff: Mem0 Circuit Breaker

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A circuit breaker pattern for all Mem0 Cloud API calls that protects the chat system from cascading failures. The design includes three circuit states (closed/open/half-open), a local in-memory cache of memory search results per agent_id with 5-minute TTL, a bounded retry queue for failed mem0.add() operations, and circuit breaker status reporting through the existing health endpoint.

## Key Decisions

- **Chat degrades gracefully, memory management returns 503**: Chat-path Mem0 calls (search for context enrichment, add for memory formation) fall back to cached or empty results when the circuit is open, so users can always talk to their characters. User-facing memory management endpoints (list, delete) return HTTP 503 because returning stale data for explicit "show my memories" requests would be misleading.
- **Cache keyed by agent_id, not by query**: Per-query caching would have near-zero hit rates because each message is unique. Caching the last search result per agent_id provides a reasonable approximation for the 5-minute degraded window.
- **In-memory singleton, not Redis-backed**: Consistent with the rate limiter (P1.5-01), a single-process in-memory circuit breaker is appropriate for Phase 1.5 with one ECS task. The interface is designed for future Redis replacement.
- **Bounded retry queue with oldest-drop policy**: 100-item limit prevents memory exhaustion during extended outages. Oldest entries are dropped first because newer conversation context is more valuable for memory formation.
- **Health endpoint probe bypasses circuit breaker**: The health check independently probes Mem0 to provide ground-truth status, while also reporting the circuit breaker's own state for operational visibility.

## Spec Location

`shared/feature-specs/mem0-circuit-breaker.md`

## Assumptions Made

- The Mem0 SDK `MemoryClient` is synchronous and all calls are wrapped in `asyncio.to_thread()` (confirmed by reading existing code).
- A single ECS task deployment means in-memory state is sufficient (no distributed coordination needed).
- Lost retry queue items on process restart are acceptable because conversation messages are already persisted in PostgreSQL and memories are supplementary.

## Dependencies

- Requires: P01-06 (chat-streaming), P01-08 (memory-endpoints), P01-04 (observability-stack) -- all already implemented
- Blocks: backend-dev (implements the circuit breaker)

## Next Steps

backend-dev should read the spec and implement. This is a backend-only feature -- no iOS or Android work required.
