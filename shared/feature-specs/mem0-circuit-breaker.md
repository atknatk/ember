# Feature Spec: P1.5-04 -- Mem0 Circuit Breaker

**Feature ID**: P1.5-04
**Phase**: 1.5
**Layer**: backend
**GitHub Issue**: #86
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature wraps all Mem0 Cloud API calls behind a circuit breaker that protects the chat system from cascading failures when Mem0 is down or degraded. It introduces three circuit states (closed, open, half-open), a local in-memory cache of recent memory search results per `agent_id`, and a retry queue for failed `mem0.add()` operations. The existing `/api/v1/health` endpoint is enhanced to report the circuit breaker state.

When the circuit is **closed** (normal), Mem0 calls proceed as today. When the circuit is **open** (Mem0 is down), chat continues without live Mem0 calls -- memory search results are served from the local cache (if available) or omitted entirely, and `mem0.add()` operations are queued for later retry. When the circuit is **half-open**, a single probe request is sent to Mem0; success resets the circuit to closed, failure reopens it.

### Why It Exists

The chat service (`POST /characters/:id/messages`) currently makes two Mem0 `search()` calls per message (global + character-scoped, in parallel via `asyncio.gather`) and one `mem0.add()` call in the background task. If Mem0 Cloud becomes unreachable, the search calls either time out (adding seconds of latency) or raise exceptions. While the current code handles individual exceptions gracefully (returning empty memory lists), it still attempts the full network call on every single message, wasting time and resources.

Per `docs/05-ai-bellek.md` Section "Mem0 Degradation Stratejisi": the system must implement a circuit breaker that opens after 3 consecutive failures, stays open for 60 seconds, then probes in half-open mode. This spec implements that exact behavior.

### Dependencies

- **Requires**: P01-06 (chat-streaming) -- the chat service that calls Mem0
- **Requires**: P01-08 (memory-endpoints) -- the memory service that calls Mem0
- **Requires**: P01-04 (observability-stack) -- the health endpoint that will report circuit state

### What This Feature Does NOT Do

- It does not persist the retry queue to disk or database. If the process restarts while the circuit is open, queued `mem0.add()` operations are lost. This is acceptable because Mem0 memories are supplementary context -- the conversation messages themselves are already persisted in PostgreSQL. Lost memories will be re-derived from future conversations.
- It does not implement distributed circuit breaker state. Like the rate limiter (P1.5-01), the circuit breaker is in-memory and per-process. Multi-instance coordination via Redis is a future enhancement.
- It does not add a new API endpoint. The circuit state is exposed through the existing health endpoint.
- It does not change the Mem0 SDK client instantiation pattern. It wraps the calls, not the client.

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables. All circuit breaker state and memory cache are stored in-process memory only.

### No New Columns

No database changes required.

### Mem0 Operations Affected

All existing Mem0 operations are routed through the circuit breaker:

| Operation | Where Called | Effect When Circuit Open |
|-----------|-------------|--------------------------|
| `mem0.search()` | `ChatService._search_memories()` | Return cached results (if available within 5min TTL) or empty list |
| `mem0.add()` | `_persist_exchange()` background task | Queued for retry when circuit closes |
| `mem0.get_all()` | `MemoryService.get_character_memories()`, `MemoryService.get_global_memories()` | Return HTTP 503 (these are explicit user-facing memory list requests, not background enrichment) |
| `mem0.delete()` | `MemoryService.delete_character_memory()` | Return HTTP 503 |
| `mem0.delete_all()` | `MemoryService.delete_all_character_memories()` | Return HTTP 503 |
| Health probe `mem0.search()` | `HealthService._probe_mem0()` | Bypasses circuit breaker (uses direct Mem0 call) |

**Key distinction**: Chat-path memory operations degrade gracefully (cache or empty). User-facing memory management endpoints (list, delete) return 503 because the user explicitly requested a Mem0 operation and should know it failed.

---

## 3. API Changes

### No New Endpoints

This feature does not introduce new API endpoints.

### Modified Endpoint: GET /api/v1/health

The existing health endpoint already returns `dependencies.mem0` with values `"ok"`, `"degraded"`, or `"unavailable"`. This feature adds a `circuit_breaker` field to the response when `check_dependencies=true`.

```
GET /api/v1/health?check_dependencies=true
Auth: Not required

Response 200:
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

The `circuit_breaker.mem0.state` field has three possible values:
- `"closed"` -- normal operation, all Mem0 calls proceed
- `"open"` -- Mem0 is considered down, calls are skipped
- `"half_open"` -- probing Mem0 with a single request

The `retry_queue_size` indicates how many `mem0.add()` operations are waiting to be sent. The `cache_entries` indicates how many agent_id keys have cached memory search results.

---

## 4. Backend Logic

### Circuit Breaker State Machine

```
                 success
    ┌──────────────────────────────┐
    │                              │
    ▼          failure_count >= 3  │
 CLOSED ──────────────────────> OPEN
    ▲                              │
    │          60s elapsed         ▼
    │                          HALF_OPEN
    │          probe success       │
    └──────────────────────────────┘
                                   │
               probe failure       │
               ┌───────────────────┘
               ▼
             OPEN (reset 60s timer)
```

**State transitions**:

1. **CLOSED -> OPEN**: When `failure_count` reaches 3 consecutive failures. Any Mem0 API call that raises an exception or times out increments `failure_count`. Any successful call resets `failure_count` to 0.

2. **OPEN -> HALF_OPEN**: When 60 seconds have elapsed since the circuit opened. The next Mem0 call attempt transitions to HALF_OPEN and sends a single probe request.

3. **HALF_OPEN -> CLOSED**: If the probe request succeeds. `failure_count` resets to 0. The retry queue is drained asynchronously.

4. **HALF_OPEN -> OPEN**: If the probe request fails. The 60-second timer restarts.

### Module: `backend/app/core/circuit_breaker.py`

This module contains the circuit breaker logic. Placed in `core/` alongside `rate_limit.py` and `auth.py` as an application-wide cross-cutting concern.

**Enum: `CircuitState`**

```
Values: CLOSED, OPEN, HALF_OPEN
```

**Class: `Mem0CircuitBreaker`**

A singleton that manages the circuit state, memory cache, and retry queue. Thread-safe for asyncio (single-threaded event loop, no locks needed).

```
Constructor:
    __init__(
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        cache_ttl: float = 300.0,
        max_retry_queue_size: int = 100,
    )

Attributes:
    state: CircuitState
    failure_count: int
    last_failure_at: float | None       (time.monotonic)
    last_success_at: datetime | None    (UTC datetime for reporting)
    _opened_at: float | None            (time.monotonic when circuit opened)
    _cache: dict[str, CacheEntry]       (keyed by agent_id or "global:{user_id}")
    _retry_queue: deque[RetryItem]      (bounded deque, maxlen=max_retry_queue_size)

Methods:
    async def call_with_breaker(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T
        Execute a Mem0 operation through the circuit breaker.
        - CLOSED: execute func, on success reset failure_count and return result,
          on failure increment failure_count and potentially open circuit, then raise.
        - OPEN: check if recovery_timeout elapsed. If yes, transition to HALF_OPEN
          and execute func as probe. If no, raise CircuitOpenError.
        - HALF_OPEN: execute func. On success, transition to CLOSED and drain retry
          queue. On failure, transition back to OPEN.

    def get_cached_memories(
        self,
        cache_key: str,
    ) -> list[str] | None
        Return cached memory search results for the given key if they exist
        and are within TTL. Returns None if not cached or expired.

    def set_cached_memories(
        self,
        cache_key: str,
        memories: list[str],
    ) -> None
        Store memory search results in cache with current timestamp.

    def enqueue_retry(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        agent_id: str,
    ) -> None
        Add a mem0.add() operation to the retry queue. If queue is at
        max_retry_queue_size, the oldest entry is dropped (deque maxlen behavior).

    async def drain_retry_queue(self) -> None
        Process all items in the retry queue by calling mem0.add() for each.
        Failures during drain are logged but do not re-open the circuit.
        Called as a background task after circuit transitions to CLOSED.

    def get_status(self) -> dict[str, Any]
        Return a dict with state, failure_count, last_failure_at, last_success_at,
        retry_queue_size, and cache_entries for the health endpoint.

    def record_success(self) -> None
        Reset failure_count to 0, update last_success_at, state -> CLOSED if HALF_OPEN.

    def record_failure(self) -> None
        Increment failure_count, update last_failure_at.
        If failure_count >= failure_threshold and state is CLOSED, open circuit.
        If state is HALF_OPEN, reopen circuit.

    def _is_recovery_timeout_elapsed(self) -> bool
        Check if enough time has passed since the circuit opened to attempt a probe.
```

**Dataclass: `CacheEntry`**

```
Attributes:
    memories: list[str]
    cached_at: float        (time.monotonic)
```

**Dataclass: `RetryItem`**

```
Attributes:
    messages: list[dict[str, str]]
    user_id: str
    agent_id: str
    created_at: float       (time.monotonic)
```

**Exception: `CircuitOpenError`**

Raised when a call is attempted while the circuit is open and recovery timeout has not elapsed. Callers catch this to serve cached/empty results.

### Integration with ChatService

The `ChatService._search_memories()` method is modified to use the circuit breaker. The method signature remains the same.

**Current behavior** (before this feature):
```
1. Create MemoryClient
2. Call client.search() via asyncio.to_thread()
3. On exception: log error, return []
```

**New behavior** (after this feature):
```
1. Check if circuit breaker allows the call
2. If circuit is OPEN:
   a. Try local cache (keyed by agent_id or "global:{user_id}")
   b. If cache hit and within TTL: return cached memories
   c. If cache miss or expired: return []
3. If circuit is CLOSED or HALF_OPEN:
   a. Create MemoryClient
   b. Call client.search() via circuit_breaker.call_with_breaker()
   c. On success: cache the results, return them
   d. On failure: circuit breaker records failure,
      try local cache as fallback, return cached or []
```

Cache key format:
- Character-scoped search: `"{agent_id}"` (e.g., `"luna_550e8400-..."`)
- Global search: `"global:{mem0_user_id}"`

### Integration with _persist_exchange (Background Task)

The `_persist_exchange()` function's Mem0 add section is modified:

**Current behavior**:
```
1. Create MemoryClient
2. Call client.add() via asyncio.to_thread()
3. On exception: log error (fire-and-forget)
```

**New behavior**:
```
1. If circuit is OPEN:
   a. Enqueue the add operation to retry queue
   b. Log at DEBUG level
   c. Return (skip Mem0 call entirely)
2. If circuit is CLOSED or HALF_OPEN:
   a. Create MemoryClient
   b. Call client.add() via circuit_breaker.call_with_breaker()
   c. On success: circuit records success
   d. On failure: circuit records failure, enqueue for retry
```

### Integration with MemoryService

The `MemoryService` methods (`get_character_memories`, `delete_character_memory`, `delete_all_character_memories`, `get_global_memories`) are modified to check circuit state:

**Behavior when circuit is OPEN or HALF_OPEN**:
- These are explicit user-facing operations (not background enrichment)
- They raise `HTTPException(503, detail="Memory service temporarily unavailable")` immediately without attempting the Mem0 call
- Exception: in HALF_OPEN state, allow the call to proceed as a probe. Success closes the circuit; failure reopens it.

### Integration with HealthService

The `HealthService._probe_mem0()` method is NOT routed through the circuit breaker. It makes a direct Mem0 call to provide an independent assessment of Mem0 availability. However, after probing, the health endpoint also reports the circuit breaker status via `circuit_breaker.get_status()`.

### Singleton Access Pattern

The circuit breaker is a module-level singleton in `core/circuit_breaker.py`, similar to how `settings` is a module-level singleton in `config.py`:

```
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

This pattern allows tests to replace the singleton with a mock/configured instance.

### New Config Fields

Four new fields in `backend/app/config.py`:

| Field | Type | Default | Env Variable | Description |
|-------|------|---------|-------------|-------------|
| `mem0_circuit_failure_threshold` | `int` | `3` | `MEM0_CIRCUIT_FAILURE_THRESHOLD` | Consecutive failures before opening circuit |
| `mem0_circuit_recovery_timeout` | `float` | `60.0` | `MEM0_CIRCUIT_RECOVERY_TIMEOUT` | Seconds to wait before probing in half-open |
| `mem0_cache_ttl` | `float` | `300.0` | `MEM0_CACHE_TTL` | TTL in seconds for cached memory search results |
| `mem0_retry_queue_max_size` | `int` | `100` | `MEM0_RETRY_QUEUE_MAX_SIZE` | Maximum queued mem0.add() operations |

### Error Handling

- `CircuitOpenError` is always caught by the calling service. It never propagates to the route handler (for chat-path calls) or is converted to HTTP 503 (for memory management endpoints).
- Retry queue drain failures are logged at WARNING level but do not affect the circuit state. The drain is best-effort.
- Cache eviction is passive (checked on read). No background cleanup thread is needed because the number of cache entries is bounded by the number of active `agent_id` values, which is bounded by the number of active characters.

### Logging

All circuit state transitions are logged at WARNING level:

```
"Mem0 circuit breaker opened after %d consecutive failures"
"Mem0 circuit breaker half-open, probing..."
"Mem0 circuit breaker closed, draining %d queued operations"
"Mem0 circuit breaker probe failed, reopening"
```

Individual Mem0 call failures that contribute to the failure count are logged at ERROR level (existing behavior). Cache hits during open circuit are logged at DEBUG level.

---

## 5. Test Requirements

### What Must Be Tested

#### Circuit Breaker Unit Tests (`tests/services/test_circuit_breaker.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Initial state | `state == CLOSED`, `failure_count == 0` |
| 2 | Successful call through breaker | `failure_count` stays 0, result returned |
| 3 | Single failure does not open circuit | `failure_count == 1`, `state == CLOSED` |
| 4 | 3 consecutive failures open circuit | `state == OPEN`, `failure_count == 3` |
| 5 | Success resets failure count | After 2 failures then 1 success, `failure_count == 0` |
| 6 | Call while circuit OPEN raises CircuitOpenError | Before recovery timeout elapses |
| 7 | After recovery_timeout, circuit transitions to HALF_OPEN | Mock time.monotonic to advance 60s |
| 8 | Successful probe in HALF_OPEN closes circuit | `state == CLOSED`, `failure_count == 0` |
| 9 | Failed probe in HALF_OPEN reopens circuit | `state == OPEN`, timer restarted |
| 10 | Retry queue drain is called after circuit closes from HALF_OPEN | Verify drain_retry_queue is triggered |

#### Memory Cache Unit Tests (`tests/services/test_circuit_breaker.py` continued)

| # | Scenario | Expected |
|---|----------|----------|
| 11 | `set_cached_memories` stores memories | `get_cached_memories` returns them |
| 12 | Cache entry expires after TTL | After TTL, `get_cached_memories` returns `None` |
| 13 | Cache entries for different keys are independent | Key A update does not affect key B |
| 14 | Cache key format for character-scoped vs global | Character: `agent_id`, Global: `"global:{user_id}"` |

#### Retry Queue Unit Tests (`tests/services/test_circuit_breaker.py` continued)

| # | Scenario | Expected |
|---|----------|----------|
| 15 | `enqueue_retry` adds item to queue | `retry_queue_size` increments |
| 16 | Queue respects max size (oldest dropped) | After max+1 enqueues, size stays at max, oldest is gone |
| 17 | `drain_retry_queue` processes all items | All items removed, mem0.add called for each |
| 18 | `drain_retry_queue` with failing items logs but continues | Queue is drained, errors logged, circuit state unchanged |

#### Chat Service Integration Tests (`tests/services/test_chat_service.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 19 | Search memories with circuit CLOSED and Mem0 succeeds | Memories returned and cached |
| 20 | Search memories with circuit CLOSED and Mem0 fails 3 times | Circuit opens, empty memories returned |
| 21 | Search memories with circuit OPEN and cache hit | Cached memories returned without Mem0 call |
| 22 | Search memories with circuit OPEN and cache miss | Empty list returned without Mem0 call |
| 23 | `_persist_exchange` with circuit OPEN | mem0.add queued, no Mem0 call made |
| 24 | `_persist_exchange` with circuit CLOSED | mem0.add called normally via breaker |

#### Memory Service Integration Tests (`tests/services/test_memory_service.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 25 | `get_character_memories` with circuit OPEN | Returns HTTP 503 |
| 26 | `delete_character_memory` with circuit OPEN | Returns HTTP 503 |
| 27 | `get_character_memories` with circuit CLOSED | Normal Mem0 call proceeds |

#### Health Endpoint Tests (`tests/routes/test_health.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 28 | Health with `check_dependencies=true` includes `circuit_breaker` | Response contains `circuit_breaker.mem0` object |
| 29 | Circuit breaker status reports correct state | `state`, `failure_count`, `retry_queue_size` match actual state |
| 30 | Health without `check_dependencies` does not include circuit_breaker | `circuit_breaker` field is absent |

#### Status Reporting Tests (`tests/services/test_circuit_breaker.py` continued)

| # | Scenario | Expected |
|---|----------|----------|
| 31 | `get_status()` in CLOSED state | `{"state": "closed", "failure_count": 0, ...}` |
| 32 | `get_status()` in OPEN state with queued items | `retry_queue_size > 0` |
| 33 | `get_status()` reports `cache_entries` correctly | Matches number of non-expired cache entries |

### How to Mock

- **time.monotonic()**: Use `unittest.mock.patch("app.core.circuit_breaker.time.monotonic")` to control time progression for recovery timeout tests.
- **Mem0 calls**: Mock the `MemoryClient` methods (`search`, `add`, `get_all`, `delete`, `delete_all`) via `unittest.mock.patch("app.services.chat_service.MemoryClient")` and similar.
- **Circuit breaker singleton**: Use `unittest.mock.patch("app.core.circuit_breaker._breaker")` to inject a test-configured instance, or call the constructor directly in unit tests.

### Code Quality Checks

```bash
ruff check backend/app/core/circuit_breaker.py
mypy backend/app/core/circuit_breaker.py
pytest backend/tests/services/test_circuit_breaker.py -v
```

---

## 6. File Manifest

### Circuit Breaker Core Logic

```
Backend:
  CREATE  backend/app/core/circuit_breaker.py
```

Contains `CircuitState` enum, `Mem0CircuitBreaker` class, `CacheEntry` and `RetryItem` dataclasses, `CircuitOpenError` exception, and `get_mem0_circuit_breaker()` singleton factory.

### Configuration

```
Backend:
  MODIFY  backend/app/config.py
```

Add four new fields: `mem0_circuit_failure_threshold`, `mem0_circuit_recovery_timeout`, `mem0_cache_ttl`, `mem0_retry_queue_max_size`.

### Service Modifications

```
Backend:
  MODIFY  backend/app/services/chat_service.py
  MODIFY  backend/app/services/memory_service.py
  MODIFY  backend/app/services/health_service.py
```

- `chat_service.py`: Modify `_search_memories()` to use circuit breaker and cache. Modify `_persist_exchange()` to use circuit breaker and retry queue.
- `memory_service.py`: Modify all public methods to check circuit state before calling Mem0.
- `health_service.py`: Add circuit breaker status to the response.

### Schema Modifications

```
Backend:
  MODIFY  backend/app/schemas/health.py
```

Add `CircuitBreakerStatus` and `CircuitBreakerReport` Pydantic models. Add optional `circuit_breaker` field to `HealthResponse`.

### Route Modifications

```
Backend:
  MODIFY  backend/app/routes/health.py
```

Pass circuit breaker status to the response when `check_dependencies=true`.

### Tests

```
Backend:
  CREATE  backend/tests/services/test_circuit_breaker.py
```

Unit and integration tests for the circuit breaker, cache, retry queue, and service integrations.

Existing test files may also need updates:
```
Backend:
  MODIFY  backend/tests/services/test_chat_service.py       (if exists)
  MODIFY  backend/tests/services/test_memory_service.py     (if exists)
  MODIFY  backend/tests/routes/test_health.py               (if exists)
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/mem0-circuit-breaker.md         (this file)
  CREATE  docs/pipeline/mem0-circuit-breaker-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 3 |
| MODIFY | 5-8 (depending on existing test files) |
| DELETE | 0 |
| **Total** | **8-11** |

### Files NOT Modified

- `backend/requirements.txt` -- no new dependencies. Uses only stdlib (`time`, `enum`, `collections.deque`, `dataclasses`).
- `backend/app/main.py` -- no changes needed. The circuit breaker is accessed via the singleton factory, not registered as middleware.
- `backend/app/routes/chat.py` -- route handler is unchanged. The circuit breaker integration is in the service layer.
- `backend/app/routes/memories.py` -- route handler is unchanged. The circuit breaker check is in `MemoryService`.

---

## 7. Acceptance Criteria

1. Given Mem0 Cloud is healthy, when a user sends a message via `POST /characters/:id/messages`, then Mem0 search is called normally and memories are included in the AI response context.

2. Given Mem0 Cloud returns errors on 3 consecutive calls, when the 3rd failure occurs, then the circuit breaker transitions to OPEN state and subsequent Mem0 search calls return cached results (if available) or empty lists without making network requests.

3. Given the circuit breaker is OPEN, when a user sends a message via `POST /characters/:id/messages`, then the message is processed and the AI responds (without memories), and the SSE stream completes successfully.

4. Given the circuit breaker is OPEN and cached memories exist for the character's agent_id (within 5-minute TTL), when a user sends a message, then the cached memories are included in the AI response context.

5. Given the circuit breaker is OPEN and cached memories have expired (older than 5 minutes), when a user sends a message, then the AI responds without any memories.

6. Given the circuit breaker is OPEN, when `_persist_exchange` runs the Mem0 add step, then the add operation is queued in the retry queue instead of calling Mem0.

7. Given the circuit breaker is OPEN, when 60 seconds have elapsed since the circuit opened, then the next Mem0 call transitions the circuit to HALF_OPEN and sends a probe request.

8. Given the circuit breaker is HALF_OPEN and the probe succeeds, then the circuit transitions to CLOSED and the retry queue is drained asynchronously.

9. Given the circuit breaker is HALF_OPEN and the probe fails, then the circuit transitions back to OPEN and the 60-second timer restarts.

10. Given the circuit breaker is OPEN, when a user requests `GET /characters/:id/memories`, then the response is HTTP 503 with body `{"detail": "Memory service temporarily unavailable"}`.

11. Given the circuit breaker is OPEN, when a user requests `DELETE /characters/:id/memories/:memId`, then the response is HTTP 503.

12. Given the circuit breaker is in any state, when `GET /api/v1/health?check_dependencies=true` is called, then the response includes a `circuit_breaker.mem0` object with `state`, `failure_count`, `retry_queue_size`, and `cache_entries`.

13. Given the retry queue has reached its maximum size (100), when another add operation is enqueued, then the oldest entry is dropped and the queue size remains at 100.

14. Given the circuit breaker transitions from OPEN to CLOSED, when the retry queue is drained, then `mem0.add()` is called for each queued item, and failures during drain are logged but do not reopen the circuit.

15. Given a Mem0 call succeeds after 2 consecutive failures, when the success is recorded, then `failure_count` resets to 0 and the circuit remains CLOSED.

16. Given the backend configuration, when a developer sets `MEM0_CIRCUIT_FAILURE_THRESHOLD=5` in the environment, then the circuit opens after 5 failures instead of 3.

17. Given the backend test suite, when a developer runs `pytest backend/tests/services/test_circuit_breaker.py -v`, then all tests pass with exit code 0.

---

## 8. Design Decisions and Rationale

### Why in-memory instead of Redis-backed circuit breaker

Same rationale as the rate limiter (P1.5-01): Ember runs a single ECS task in Phase 1.5. An in-memory circuit breaker has zero latency overhead and no external dependencies. If Ember scales to multiple tasks, the `Mem0CircuitBreaker` can be replaced with a Redis-backed implementation exposing the same interface.

### Why 3 failures / 60 seconds

Per `docs/05-ai-bellek.md`: "3 ardisik Mem0 hatasi -> circuit acilir (60s)". These are the documented values. They are configurable via environment variables for production tuning.

### Why cache per agent_id and not per query

Mem0 search results are query-dependent (semantic search), so ideally the cache key would include the query. However, caching per query would result in very low cache hit rates (each message has unique content). Instead, caching the last search result per agent_id provides a reasonable approximation: the most recent memories for this character are likely still relevant for the next message within a 5-minute window. This is a degraded experience, not a substitute for live search.

### Why explicit 503 for memory management endpoints but graceful degradation for chat

Chat is the critical path -- users must always be able to talk to their character. Memory enrichment is a quality enhancement, not a functional requirement. Memory management (list, delete) is an explicit user action ("show me my memories") where returning stale or empty data would be confusing. A clear 503 tells the user to try again later.

### Why bounded retry queue with oldest-drop policy

Unbounded queues risk memory exhaustion during extended outages. Dropping the oldest entries is acceptable because newer conversations contain more recent context that is more valuable for memory formation. The 100-item limit is generous -- at 10 messages/minute (chat rate limit), it covers ~10 minutes of conversation.

### Why drain retry queue in background task, not synchronously

Draining the retry queue synchronously when the circuit closes would block the request that triggered the probe. Instead, `asyncio.create_task(breaker.drain_retry_queue())` runs the drain in the background, consistent with how `_persist_exchange` already works.

---

## 9. Notes for Developers

### For backend-dev

- The `Mem0CircuitBreaker` class is stateful (singleton). Use `time.monotonic()` for all internal timing, consistent with `core/rate_limit.py`. Use `datetime.now(tz=UTC)` only for the `last_success_at` and `last_failure_at` fields reported in `get_status()` (these are user-facing timestamps).
- The retry queue uses `collections.deque(maxlen=N)` for automatic oldest-entry eviction.
- The `call_with_breaker` method should accept a generic async callable. Use `asyncio.to_thread()` internally if the callable is synchronous (Mem0 SDK calls are sync, wrapped in `to_thread`).
- When modifying `ChatService._search_memories()`, the circuit breaker check and cache lookup should happen BEFORE creating the `MemoryClient`. Avoid instantiating the client when the circuit is open.
- The `drain_retry_queue` method should iterate over a copy of the queue (pop items one by one) to avoid issues if new items are enqueued during drain.
- For `MemoryService`, add a private method `_check_circuit()` that raises `HTTPException(503)` if the circuit is OPEN. Call it at the top of each public method.
- The health endpoint modification is minimal: import `get_mem0_circuit_breaker`, call `get_status()`, and include it in the response.
- Config fields go in the `Settings` class grouped under a `# Circuit Breaker` comment, after the existing `# Memory` section.

### For backend-tester

- Circuit breaker tests need time mocking. Use `unittest.mock.patch("app.core.circuit_breaker.time.monotonic")` to control failure/recovery timing.
- For integration tests that verify chat continues without memories, mock the `MemoryClient` to raise `Exception` 3 times, verify the circuit opens, then send a 4th message and verify the SSE stream completes successfully with a `done` event.
- The retry queue drain test should mock `MemoryClient.add` to verify it is called for each queued item.
- Test the singleton pattern: verify `get_mem0_circuit_breaker()` returns the same instance across calls within a test (and can be reset for test isolation).
