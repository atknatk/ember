# Content Moderation

> Protects users and the platform by screening chat messages for harmful content, prompt injection, and abuse before they reach the LLM.

**Status**: Released
**Added in**: 2026-03-13
**Platforms**: Backend only

---

## Overview

Content moderation adds a multi-layer safety pipeline to the Ember chat flow. Every user message passes through the moderation service before it reaches Mem0 or the main LLM, meaning blocked messages never incur the cost of a Claude Sonnet streaming call.

The system operates at three levels. First, individual messages are checked for length violations, prompt injection patterns, and harmful content (via Claude Haiku classification). Second, the therapist character receives per-message system prompt augmentation when the classifier detects a crisis indicator such as suicidal ideation or self-harm language. Third, repeated violations within a 24-hour rolling window trigger escalating temporary send-blocks, deterring persistent abuse without permanently banning users.

The design philosophy is deliberately fail-open: if the Haiku classifier is unreachable or returns unparseable output, messages are allowed through. Ember is a personal companion app, not a public forum — over-blocking harms user trust more than occasional missed moderation. Anthropic's built-in Claude safety layer provides a second line of defense even when Ember's classifier is down.

---

## Architecture

### How It Works (Data Flow)

1. The mobile app calls `POST /api/v1/characters/{character_id}/messages` or the SSE streaming variant with the user's message content.
2. `ChatService.validate_send_message()` first looks up the character to confirm ownership and retrieve the character template.
3. `ContentModerationService.check_message()` is called with the message content, `user_id`, `character_id`, and `character_template`.
4. Inside `check_message`, two checks run in parallel via `asyncio.gather()`: the abuse block state DB query and the Claude Haiku content classification call.
5. If the abuse block check finds a `blocked_until` timestamp in the future, a `ModerationResult(allowed=False, blocked_until=...)` is returned immediately and no LLM call is made.
6. Separately (step 3 of the pipeline, but placed after the parallel gather in code), the heuristic prompt injection regex scanner runs synchronously against the content.
7. If injection patterns are detected, the service logs a `moderation_event` as a background task and sets the injection preamble as `augment_system_prompt`. The message is not blocked.
8. If the Haiku classification returns `safe=False` with `severity` of `medium` or `high`, the message is blocked with HTTP 400 and a violation is recorded as a background task.
9. If the character template is `therapist` and the classification returns `crisis=True`, the crisis resource text is appended to `augment_system_prompt`.
10. Back in `ChatService`, if `moderation_result.augment_system_prompt` is set, it is appended to the system prompt before the Mem0 + recent messages fetch proceeds.
11. For therapist characters where crisis augmentation was applied, a `{"type": "moderation", "message": "..."}` SSE event is emitted at the start of the response stream.
12. Normal chat streaming proceeds; the moderation result does not affect subsequent steps.

### Parallel Execution Detail

The abuse state check (PostgreSQL read) and the Haiku classification call (LLM network round-trip) are the two most latency-sensitive steps. They run concurrently:

```python
abuse_result, classification = await asyncio.gather(
    moderation_service._check_abuse_state(user_id, db),
    moderation_service._classify_content(content),
    return_exceptions=True,
)
```

Both results are inspected for exceptions before use. A failure in either falls back to the safe default (fail-open).

### Violation Recording as Background Task

Recording a `moderation_event` and updating `user_moderation_state` happens via `asyncio.create_task()` (fire-and-forget). The background function opens its own `AsyncSessionLocal` session so it does not interfere with the main request session. If the background write fails, only the audit log is lost — the response to the user is not affected.

### Abuse Escalation Policy

The rolling window is 24 hours (configurable). Violations are counted against `user_moderation_state.violation_count`. When the current timestamp exceeds `window_start + 24h`, the count resets to 1 for the new window.

| Violation in window | Action |
|---------------------|--------|
| 1–2 | Logged only, message allowed |
| 3 | Current message blocked (HTTP 400), no future block |
| 4–5 | Current message blocked, `blocked_until = now + 15 min` |
| 6+ | Current message blocked, `blocked_until = now + 60 min` |

Note: the `total_lifetime_violations` counter never resets and is intended for future manual review tooling.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `moderation_events` | INSERT | Append-only audit log; `user_content` truncated to 200 chars |
| `user_moderation_state` | SELECT, INSERT, UPDATE | One row per user; upsert pattern via `_update_abuse_state` |
| `characters` | SELECT | Needed before moderation to get `template` value |
| `profiles` | (FK ref) | Cascading delete keeps both moderation tables clean |

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract. Content moderation modifies the behavior of the existing chat endpoint.

### Modified Endpoint: `POST /api/v1/characters/{character_id}/messages`

**Auth**: Bearer JWT required

**New error responses introduced by moderation**:

| Status | When | Response body |
|--------|------|---------------|
| 400 | Message exceeds 4000 characters | `{"detail": "Message content exceeds maximum length of 4000 characters"}` |
| 400 | Harmful content (medium/high severity) | `{"detail": "Your message could not be sent. Please rephrase and try again."}` |
| 403 | User temporarily blocked | `{"detail": {"detail": "Message sending is temporarily disabled. Please try again later.", "blocked_until": "2026-03-13T15:30:00Z"}}` |

All pre-existing responses (200, 401, 403 ownership, 404, 429, 500, 503) are unchanged.

### New SSE Event: `moderation`

Emitted only for therapist characters when crisis augmentation is applied. Mobile clients that do not recognize this event type should ignore it (SSE spec requires ignoring unknown event types).

```
data: {"type": "moderation", "message": "I need to be careful here. If you're in crisis, please contact..."}
```

This event carries no classification data. It is an informational signal that the response was augmented with crisis resources.

---

## Backend Implementation

**Files**:
- `backend/app/services/content_moderation.py` — all moderation logic (classifier, injection detector, abuse tracker)
- `backend/app/models/moderation_event.py` — SQLAlchemy model for `moderation_events` table
- `backend/app/models/user_moderation_state.py` — SQLAlchemy model for `user_moderation_state` table
- `backend/app/services/chat_service.py` — integration point: calls `check_message()` in `validate_send_message()`
- `backend/app/config.py` — five new `Settings` fields (see Configuration section below)

### Key Data Classes

`ContentClassification` (frozen dataclass) — result of the Haiku classification call:

```python
@dataclass(frozen=True)
class ContentClassification:
    safe: bool
    category: str   # "none" | "violence" | "self_harm" | "sexual" | "hate" | "illegal"
    severity: str   # "none" | "low" | "medium" | "high"
    crisis: bool
```

`ModerationResult` (frozen dataclass) — returned by `check_message()` to the caller:

```python
@dataclass(frozen=True)
class ModerationResult:
    allowed: bool
    reason: str | None
    category: str | None
    severity: str
    augment_system_prompt: str | None
    blocked_until: datetime | None
```

### Prompt Injection Detection

`_check_prompt_injection(content)` uses nine compiled regex patterns covering common injection phrases ("ignore previous instructions", "you are now", "forget everything", etc.), repeated special character delimiters (`###`, `===`, `---`, `<<<`, `>>>`), and base64-encoded strings longer than 100 characters. All patterns are compiled at import time for performance.

When injection is detected, the message is not blocked. Instead, `augment_system_prompt` is set to `_INJECTION_PREAMBLE`, which instructs the LLM to ignore override attempts and stay in character.

### Content Classification Prompt

The Haiku classifier receives a structured prompt with strict rules distinguishing harmful content from normal emotional expression. Key rules: expressing sadness, frustration, or anger is explicitly classified as safe; only direct threats and incitement are classified as `severity: high`. This avoids over-blocking users who are discussing difficult topics — core functionality for a companion app.

Blocking threshold: `safe == False AND severity in ("medium", "high")`. Low-severity unsafe content is logged but allowed through.

### Configuration

All settings live in `app/config.py` under the `Settings` class:

| Setting | Default | Description |
|---------|---------|-------------|
| `moderation_enabled` | `True` | Master toggle — set to `False` to bypass all moderation |
| `moderation_fail_open` | `True` | Allow messages through when classifier fails |
| `moderation_abuse_window_hours` | `24` | Rolling window duration for abuse rate detection |
| `moderation_block_duration_short_minutes` | `15` | Block duration for violations 4–5 |
| `moderation_block_duration_long_minutes` | `60` | Block duration for violations 6+ |

All five are surfaced in `.env.example`.

---

## iOS Implementation

This is a backend-only feature. No new iOS screens, ViewModels, or services were added.

**Mobile client impact**: The existing error handling in the chat ViewModel already handles 400 and 403 responses. The `detail` field from the error body should be displayed to the user. For 403 responses with `blocked_until`, the client can optionally display "You can send messages again at {time}" — this is not currently implemented on iOS but the data is present in the response body.

The new `moderation` SSE event type can be handled by the SSE parser to optionally display a subtle crisis resource banner. If the client does not handle it, the SSE spec requires that unknown event types be silently ignored.

---

## Android Implementation

This is a backend-only feature. No new Android screens, ViewModels, repositories, or Retrofit interfaces were added.

Mobile client impact is identical to iOS (see above).

---

## Testing

### Coverage Summary

| Platform | File | Coverage |
|----------|------|----------|
| Backend | `backend/tests/services/test_content_moderation.py` | Service layer: injection detection, classification, abuse state, full pipeline |

**Note — implementation deviation from spec**: The spec called for a separate `backend/tests/routes/test_chat_moderation.py` for route-level moderation tests. This file was not created. Route-level moderation tests are not present in `backend/tests/routes/test_chat.py` either. If route-level coverage is needed, `test_chat_moderation.py` should be created following the 10-scenario test plan in `shared/feature-specs/content-moderation.md` Section 7.

### Running Tests

**Backend service tests**:
```bash
cd backend && python -m pytest tests/services/test_content_moderation.py -v
```

### Test Scenarios Covered

- Normal message passes all moderation and is allowed through
- Message exceeding 4000 characters is blocked
- Harmful content with high severity is blocked; low severity is logged and allowed
- Prompt injection detected: message allowed but injection preamble set in `augment_system_prompt`
- User with active `blocked_until` receives a block result regardless of message content
- Expired `blocked_until` is treated as unblocked
- Therapist character + `crisis=True` classification adds crisis resource text to `augment_system_prompt`
- Non-therapist character + `crisis=True` receives no augmentation
- Classifier failure (exception and malformed JSON) both fail open
- `moderation_enabled=False` bypasses all checks
- Violation escalation: counts 4–5 apply 15-minute block, counts 6+ apply 60-minute block
- Rolling window resets violation count after 24 hours

---

## Known Limitations

- Route-level integration tests (`test_chat_moderation.py`) were not implemented; only service-level tests exist. The 10 acceptance criteria in the spec remain untested at the HTTP layer.
- The `moderation` SSE event response body contains only a generic message string, not the actual crisis resources. The full crisis resource text is injected into the LLM system prompt, not the SSE event payload.
- Response length enforcement relies on `max_tokens=2048` in the Anthropic call (approximately 8000 characters). If a future model change produces significantly longer tokens per character, explicit character counting in `stream_response()` should be added.
- The `blocked_until` timestamp in the 403 response body is nested under a `detail` key (`{"detail": {"detail": "...", "blocked_until": "..."}}`) rather than at the top level. Mobile clients must unpack this nested structure.
- Prompt injection preamble and crisis augmentation text are appended to the system prompt using a simple `\n\n` separator. If both are triggered simultaneously (injection detected on a crisis message to a therapist), they are concatenated in that order: injection preamble first, then crisis text.
- The admin moderation stats endpoint (`GET /api/v1/admin/moderation/stats`) is reserved but not implemented.

---

## Extending This Feature

**Adding a new injection pattern**: Add a compiled `re.compile(...)` entry to `_INJECTION_PATTERNS` in `content_moderation.py`. The list is iterated in order; no other changes are required.

**Adding a new harm category**: Add the value to the `category` constraint in `_CLASSIFICATION_PROMPT` and to `ModerationEvent.category` documentation. The database column is a plain `TEXT` field with no enum constraint, so no migration is needed.

**Changing escalation thresholds**: Update the `if count >= 6` / `elif count >= 4` logic in `_update_abuse_state()` and the corresponding `Settings` fields in `config.py`. The thresholds are not currently driven by the config values — if you want fully config-driven escalation, the count thresholds must also be moved to `Settings`.

**Adding a therapist-only pre-message check**: The `character_template` parameter is already passed to `check_message()`. Add a new branch alongside the existing `if classification.crisis and character_template == "therapist"` block.

**Enabling strict mode (fail-closed)**: Set `moderation_fail_open=False` in the environment. When `False`, classifier exceptions and malformed JSON responses are re-raised, causing the request to fail with HTTP 500 rather than allowing the message through. Only use this in environments where over-blocking is acceptable.

---

## Related Documentation

- [Database Schema](../04-veri-api.md)
- [AI Memory System](../05-ai-bellek.md)
- [Character System](../16-karakterler.md)
- [LLM Provider Abstraction](llm-provider-abstraction.md)
- [Chat Streaming](chat-streaming.md)
