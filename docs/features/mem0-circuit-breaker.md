# Mem0 Circuit Breaker

> Protects the chat system from cascading failures when Mem0 Cloud is unavailable, allowing characters to keep responding using cached memories or no memories while queuing failed memory writes for later retry.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-04)
**Platforms**: Backend
**GitHub Issue**: #86

---

## Overview

The Mem0 circuit breaker is a three-state fault-tolerance mechanism that wraps every Mem0 Cloud API call made by the backend. Before this feature, if Mem0 became unreachable, every chat message would attempt — and wait for — a network call that was doomed to fail. Although the code caught these exceptions and returned empty memory lists, it still paid the full timeout cost on every single message.

The circuit breaker solves this by tracking consecutive failures. After three failures, the circuit opens and Mem0 calls are bypassed entirely for 60 seconds. During that window, chat continues uninterrupted: `_search_memories` serves results from an in-memory cache of recent searches (keyed per `agent_id`, with a 5-minute TTL) or returns an empty list. `_persist_exchange` queues the `mem0.add()` call in a bounded retry queue rather than dropping it. When 60 seconds have elapsed, a single probe request is sent; if it succeeds, the circuit closes, the retry queue is drained as a background task, and normal operation resumes.

User-facing memory management endpoints (list memories, delete a memory, clear all memories) behave differently from the chat path. When a user explicitly requests their memories, returning stale cached data would be misleading. Those endpoints return HTTP 503 immediately if the circuit is OPEN, giving the user a clear signal to try again later. In HALF_OPEN state they are allowed through as an implicit probe.

The implementation uses stdlib-only primitives (`collections.deque`, `time.monotonic`, `enum`). No new dependencies are introduced. The circuit breaker state is in-process and per-ECS-task, consistent with the rate limiter (P1.5-01). The `Mem0CircuitBreaker` class is designed with a clean interface so a Redis-backed replacement can be swapped in without touching the service layer.

---

## Architecture

### How It Works (Data Flow)

**Normal chat message (circuit CLOSED)**:

1. User sends a message; the route handler calls `ChatService.stream_message()`.
2. `asyncio.gather` runs `_search_memories` twice in parallel — one global search (`"global:{mem0_user_id}"` cache key) and one character-scoped search (`agent_id` cache key).
3. Each `_search_memories` call wraps the `MemoryClient.search()` in `breaker.call_with_breaker()`.
4. On success, results are stored in `breaker.set_cached_memories(cache_key, memories)` and returned.
5. After the SSE stream completes, `_persist_exchange` runs as a background task. It calls `breaker.call_with_breaker()` for `mem0.add()`.
6. On success, `record_success()` keeps `failure_count` at 0.

**Circuit opens (CLOSED → OPEN)**:

1. A Mem0 call inside `call_with_breaker` raises an exception.
2. `record_failure()` increments `failure_count`. On the third consecutive failure, `state` transitions to `OPEN` and `_opened_at` is set via `time.monotonic()`.
3. A WARNING log is emitted: `"Mem0 circuit breaker opened after N consecutive failures"`.

**Degraded chat (circuit OPEN)**:

1. `_search_memories` checks `breaker.state` before creating a `MemoryClient`.
2. If OPEN, it reads `breaker.get_cached_memories(cache_key)` — returns the list if within 5-minute TTL, or `None` if expired/absent.
3. The chat stream proceeds with whatever memories (or empty list) were available.
4. `_persist_exchange` checks `breaker.state == OPEN` and calls `breaker.enqueue_retry(messages, user_id, agent_id)` instead of making a Mem0 call.

**Recovery probe (OPEN → HALF_OPEN → CLOSED)**:

1. When the next Mem0 call is attempted and 60 seconds have elapsed since `_opened_at`, `call_with_breaker` transitions the state to `HALF_OPEN` and logs `"Mem0 circuit breaker half-open, probing..."`.
2. The probe call proceeds. On success, `record_success()` transitions to `CLOSED`, clears `_opened_at`, and (if the retry queue has items) schedules `asyncio.create_task(breaker.drain_retry_queue())`.
3. `drain_retry_queue` pops each `RetryItem` and calls `MemoryClient.add()` wrapped in `asyncio.to_thread`. Failures during drain are logged at WARNING but do not reopen the circuit.
4. On probe failure, `record_failure()` transitions back to `OPEN` and resets the 60-second timer.

**Memory management endpoints (any circuit state)**:

1. `MemoryService._check_circuit()` is called at the top of every public method.
2. If `breaker.state == CircuitState.OPEN`, it raises `HTTPException(503, "Memory service temporarily unavailable")` immediately — no Mem0 call is made.
3. If `CLOSED` or `HALF_OPEN`, the call proceeds through `breaker.call_with_breaker()`. A `CircuitOpenError` from the breaker is also caught and converted to 503.

### State Machine

```
               success
  ┌──────────────────────────────┐
  │                              │
  ▼       failure_count >= 3     │
CLOSED ──────────────────────> OPEN
  ▲                              │
  │         60s elapsed          ▼
  │                          HALF_OPEN
  │         probe success        │
  └──────────────────────────────┘
                                 │
             probe failure       │
             ┌───────────────────┘
             ▼
           OPEN (timer reset)
```

State transitions are guarded by `record_success()` and `record_failure()`. A success in CLOSED state simply resets `failure_count` to 0 without changing state. Two failures followed by one success reset `failure_count` to 0 — only consecutive failures count toward the threshold.

### In-Memory Cache

The cache stores the last known memory search results per lookup key. Cache keys follow this format:

| Context | Cache key |
|---------|-----------|
| Character-scoped search | `agent_id` (e.g., `"luna_550e8400-..."`) |
| Global (cross-character) search | `"global:{mem0_user_id}"` |

Entries are stored as `CacheEntry(memories: list[str], cached_at: float)` where `cached_at` uses `time.monotonic()`. The TTL is 300 seconds (configurable). Expiry is checked lazily on read — expired entries are deleted from the dict at access time. There is no background eviction loop; the cache size is naturally bounded by the number of active agent IDs per process.

The cache is keyed by `agent_id` rather than by query text. Per-query caching would have near-zero hit rates because each message is unique content. Caching the last result per character provides a reasonable approximation within the 5-minute degraded window.

### Retry Queue

The retry queue is a `collections.deque(maxlen=100)`. When `maxlen` is reached, `deque` automatically drops the oldest item on `append`. Newer conversation context is more valuable for memory formation than older context, making oldest-drop the correct policy. At the chat rate limit of 10 messages per minute, 100 items covers approximately 10 minutes of conversation before any data is lost.

Each `RetryItem` stores: `messages: list[dict[str, str]]`, `user_id: str`, `agent_id: str`, and `created_at: float`.

### Module Location

The circuit breaker is a cross-cutting concern, placed in `backend/app/core/` alongside `rate_limit.py` and `auth.py`:

| File | Purpose |
|------|---------|
| `backend/app/core/circuit_breaker.py` | `CircuitState`, `Mem0CircuitBreaker`, `CacheEntry`, `RetryItem`, `CircuitOpenError`, `get_mem0_circuit_breaker()` |
| `backend/app/config.py` | Four new config fields (see Configuration section) |
| `backend/app/schemas/health.py` | `CircuitBreakerStatus`, `CircuitBreakerReport` Pydantic models |
| `backend/app/routes/health.py` | Reports circuit state when `check_dependencies=true` |
| `backend/app/services/chat_service.py` | `_search_memories` and `_persist_exchange` modified |
| `backend/app/services/memory_service.py` | All public methods guarded by `_check_circuit()` |
| `backend/app/services/health_service.py` | Includes `get_status()` output in health response |

### Singleton Access

```python
# get_mem0_circuit_breaker() in backend/app/core/circuit_breaker.py
_breaker: Mem0CircuitBreaker | None = None

def get_mem0_circuit_breaker() -> Mem0CircuitBreaker:
    global _breaker
    if _breaker is None:
        _breaker = Mem0CircuitBreaker(
            failure_threshold=settings.mem0_circuit_failure_threshold,
            recovery_timeout=settings.mem0_circuit_recovery_timeout,
            cache_ttl=settings.mem0_cache_ttl,
            max_retry_queue_size=settings.mem0_retry_queue_max_size,
        )
    return _breaker
```

This mirrors the `settings` singleton pattern in `config.py`. Tests reset the singleton by setting `app.core.circuit_breaker._breaker = None`; an autouse fixture in `backend/tests/conftest.py` does this automatically between tests.

### No Database Involvement

The circuit breaker stores no data in PostgreSQL. All state (circuit state, failure counts, cache, retry queue) is held in-process for the lifetime of the ECS task. If the process restarts while the circuit is OPEN, queued retry items are lost. This is acceptable because conversation messages are already persisted in PostgreSQL; the lost Mem0 memories are supplementary context that will be re-derived from future conversations.

---

## API Reference

This feature introduces no new endpoints. It modifies the existing health endpoint's response shape.

### Modified: `GET /api/v1/health?check_dependencies=true`

**Auth**: Not required

When `check_dependencies=true`, the response now includes a `circuit_breaker` object:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": {
    "database": "ok",
    "mem0": "ok",
    "claude": "ok"
  },
  "circuit_breaker": {
    "mem0": {
      "state": "closed",
      "failure_count": 0,
      "last_failure_at": null,
      "last_success_at": "2026-03-13T10:00:00Z",
      "retry_queue_size": 0,
      "cache_entries": 5
    }
  }
}
```

The `circuit_breaker` field is absent when `check_dependencies` is omitted or `false`.

**Circuit state values**:

| Value | Meaning |
|-------|---------|
| `"closed"` | Normal operation — all Mem0 calls proceed |
| `"open"` | Mem0 considered down — calls skipped, cache/queue used |
| `"half_open"` | Probing Mem0 with a single request |

**Status fields**:

| Field | Type | Description |
|-------|------|-------------|
| `state` | string | One of `closed`, `open`, `half_open` |
| `failure_count` | integer | Consecutive failures since last success |
| `last_failure_at` | ISO 8601 string or null | UTC time of most recent failure |
| `last_success_at` | ISO 8601 string or null | UTC time of most recent success |
| `retry_queue_size` | integer | Number of queued `mem0.add()` operations |
| `cache_entries` | integer | Number of non-expired cache entries |

Note: The health endpoint's own Mem0 probe (`_probe_mem0`) bypasses the circuit breaker to provide an independent, ground-truth assessment of Mem0 availability. The `dependencies.mem0` field reflects the live probe result; `circuit_breaker.mem0` reflects the breaker's internal state. These can differ — for example, `dependencies.mem0` could be `"ok"` while `circuit_breaker.mem0.state` is `"open"` if Mem0 recovered between the probe and the last chat message.

### 503 Responses from Memory Management Endpoints

When the circuit is OPEN, all explicit memory management endpoints return:

```
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"detail": "Memory service temporarily unavailable"}
```

Affected endpoints:
- `GET /api/v1/characters/{character_id}/memories`
- `DELETE /api/v1/characters/{character_id}/memories/{memory_id}`
- `DELETE /api/v1/characters/{character_id}/memories`
- `GET /api/v1/users/me/memories`

---

## Configuration

Four environment variables control circuit breaker behavior. They are read at first call to `get_mem0_circuit_breaker()`:

| Environment Variable | Config Field | Type | Default | Description |
|---------------------|-------------|------|---------|-------------|
| `MEM0_CIRCUIT_FAILURE_THRESHOLD` | `mem0_circuit_failure_threshold` | `int` | `3` | Consecutive failures before opening circuit |
| `MEM0_CIRCUIT_RECOVERY_TIMEOUT` | `mem0_circuit_recovery_timeout` | `float` | `60.0` | Seconds to wait before probing in half-open |
| `MEM0_CACHE_TTL` | `mem0_cache_ttl` | `float` | `300.0` | TTL in seconds for cached memory search results |
| `MEM0_RETRY_QUEUE_MAX_SIZE` | `mem0_retry_queue_max_size` | `int` | `100` | Maximum queued `mem0.add()` operations |

The defaults implement the values documented in `docs/05-ai-bellek.md` ("3 ardisik Mem0 hatasi -> circuit acilir (60s)").

---

## Testing

### Coverage Summary

| Module | Lines | Coverage |
|--------|-------|----------|
| `app/core/circuit_breaker.py` | 118 | 100% |
| `app/routes/health.py` | 20 | 100% |
| `app/schemas/health.py` | 20 | 100% |
| `app/services/memory_service.py` | 100 | 100% |
| `app/services/chat_service.py` | 240 | 99% |
| `app/services/health_service.py` | 67 | 94% |

All targets (>= 80%) exceeded. The two uncovered lines in `chat_service.py` (432–433) are covered by existing chat integration tests. The 6% gap in `health_service.py` is inside `_probe_mem0` and `_probe_claude` inner function bodies that require live external service instantiation.

### Test Files

| File | Author | Tests | What It Covers |
|------|--------|-------|----------------|
| `backend/tests/services/test_circuit_breaker.py` | backend-dev | 35 | Core spec scenarios T1–T33: state machine, cache, retry queue, service integrations, health |
| `backend/tests/services/test_circuit_breaker_extended.py` | backend-tester | 57 | Edge cases: singleton factory, TTL boundaries, partial drain failures, per-service 503 paths, schema validation, config defaults |

### Running Tests

Circuit breaker tests only:

```bash
cd backend && python -m pytest tests/services/test_circuit_breaker.py tests/services/test_circuit_breaker_extended.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v
```

### Test Patterns

**Time control**: Patch `app.core.circuit_breaker.time.monotonic` to advance the clock without real waits. Required for recovery timeout and TTL boundary tests.

**Singleton isolation**: The autouse `_reset_circuit_breaker` fixture in `conftest.py` sets `app.core.circuit_breaker._breaker = None` before each test. Tests can also pre-inject a custom-configured instance directly: `cb_module._breaker = Mem0CircuitBreaker(failure_threshold=1)`.

**Mem0 mocking**: Mock `app.services.chat_service.MemoryClient` for chat service tests, `app.services.memory_service.MemoryClient` for memory service tests, and `mem0.MemoryClient` for drain retry queue tests.

---

## Known Limitations

- **In-memory state is not shared across ECS tasks**: Like the rate limiter (P1.5-01), the circuit breaker is per-process. If Ember scales to multiple ECS tasks, each task has its own independent circuit state and cache. A future Redis-backed implementation can be swapped in behind the same `get_mem0_circuit_breaker()` interface.
- **Retry queue is lost on process restart**: If the process restarts while the circuit is OPEN, all queued `mem0.add()` operations are lost. Conversation messages are already persisted in PostgreSQL; the lost memories are supplementary and will be re-derived from future conversations.
- **Cache serves stale results, not fresh ones**: When the circuit is OPEN, `_search_memories` returns the last known results for that `agent_id`, not a fresh semantic search against the current message content. This is a degraded experience — memories may be less contextually relevant. The TTL (default 5 minutes) bounds the staleness window.
- **No distributed coordination**: Opening the circuit on one task does not open it on sibling tasks. Multi-task deployments could have split behavior where some tasks serve live Mem0 and others serve from cache simultaneously.

---

## Extending This Feature

**Changing thresholds per environment**: Set `MEM0_CIRCUIT_FAILURE_THRESHOLD`, `MEM0_CIRCUIT_RECOVERY_TIMEOUT`, `MEM0_CACHE_TTL`, or `MEM0_RETRY_QUEUE_MAX_SIZE` in the environment. Changes take effect on next process start (the singleton is created on first access).

**Adding a new Mem0 operation to the circuit**: Wrap the call in `breaker.call_with_breaker(lambda: asyncio.to_thread(client.some_method, ...))`. Decide whether it should degrade gracefully (catch `CircuitOpenError` and return a safe default) or fail explicitly (let `CircuitOpenError` propagate and convert to 503 in the service layer). Use `_check_circuit()` in the service as a fast early-exit before creating a `MemoryClient`.

**Replacing with a Redis-backed implementation**: Create a new class that exposes the same interface as `Mem0CircuitBreaker` (`call_with_breaker`, `get_cached_memories`, `set_cached_memories`, `enqueue_retry`, `drain_retry_queue`, `get_status`, `record_success`, `record_failure`). Replace the `Mem0CircuitBreaker(...)` instantiation inside `get_mem0_circuit_breaker()` with the new class. No changes to the service layer or health endpoint are required.

**Observing circuit state in production**: Poll `GET /api/v1/health?check_dependencies=true` and monitor `circuit_breaker.mem0.state`. A CloudWatch alarm on `state != "closed"` for more than 60 seconds indicates a sustained Mem0 outage. Monitor `retry_queue_size` to detect memory write backlog.

---

## Related Documentation

- [AI Memory System](../05-ai-bellek.md) — Mem0 degradation strategy that defines the 3-failure / 60-second defaults
- [Database Schema and API Endpoints](../04-veri-api.md) — Chat and memory endpoint contracts
- [Chat Streaming](./chat-streaming.md) — P01-06, the chat service this feature protects
- [Memory Endpoints](./memory-endpoints.md) — P01-08, the memory management service that returns 503 when circuit is open
- [Observability Stack](./observability-stack.md) — P1.5-03, structured logging context for circuit state transitions
- [Rate Limiting Middleware](./rate-limiting-middleware.md) — P1.5-01, the parallel in-memory singleton pattern this feature follows
