# Ember Common Standards

All agents and all platforms

This document defines rules that apply to every agent, every platform, and every code change
in the Ember project. Zero-memory sessions must read this file before reading any other document.

---

## Table of Contents

1. Critical Architectural Rules
2. Git Commit Format
3. Branch Naming
4. Secrets Policy
5. API Contract Rules
6. Cursor Pagination Rules
7. Error Response Format
8. Security Rules
9. Performance Targets
10. Code Review Checklist

---

## 1. Critical Architectural Rules

These rules are non-negotiable. Violating them will break the application.

### Single Conversation Per Character

Each user has exactly ONE conversation per character. There is no "new chat" feature.
The first message to a character auto-creates the conversation. All subsequent messages
append to the same conversation.

```
User A + Character Luna  →  one conversation, forever
User A + Character Aria  →  one separate conversation, forever
User B + Character Luna  →  one conversation, forever (isolated from User A)
```

**Technical consequence**: There is no endpoint to create a conversation.
A conversation is auto-created when a character is created (in `CharacterService.create_character()`).
The chat service has a defensive `_get_or_create_conversation` as fallback.

### Message Endpoint

```
CORRECT:   POST /characters/:id/messages
INCORRECT: POST /conversations/:id/messages
INCORRECT: POST /characters/:id/conversations/:cid/messages
```

The character ID is the primary routing key. Never route through a conversation ID.

### Mem0 agent_id Format

```
CORRECT format:   {template_id}_{user_id}
CORRECT example:  luna_550e8400-e29b-41d4-a716-446655440000
INCORRECT:        user_550e8400_luna
INCORRECT:        luna-550e8400-e29b-41d4-a716-446655440000  (dash not underscore)
```

The `template_id` is the character template identifier (e.g., `luna`, `aria`, `kai`).
The `user_id` is the UUID from the users table.
Both `user_id` and `agent_id` are passed to every Mem0 call.

### Context Window Slice

When building the LLM prompt, include the **last 30–50 messages** from the conversation,
not the full history. Full history is handled by Mem0 memory retrieval.

```
Context = system_prompt + mem0_memories + last_50_messages + new_user_message
```

### No user_id in Request Body

The `user_id` is always extracted from the JWT. Never accept `user_id` as a request body
field or query parameter. Accepting user_id from clients is a critical security vulnerability.

```python
# CORRECT — extract from token
user_id = current_user.id   # from Depends(get_current_user)

# INCORRECT — NEVER DO THIS
user_id = body.user_id      # ← SECURITY VULNERABILITY
user_id = request.query_params.get("user_id")  # ← SECURITY VULNERABILITY
```

---

## 2. Git Commit Format

```
<type>(<scope>): <description> [agent:<name>] [platform:<platforms>]
```

### Types

| Type       | Use When                                                    |
|------------|-------------------------------------------------------------|
| `feat`     | New feature visible to users or API consumers               |
| `fix`      | Bug fix                                                     |
| `refactor` | Code change with no functional effect                       |
| `test`     | Adding or updating tests                                    |
| `docs`     | Documentation only                                         |
| `chore`    | Build config, CI, dependencies, tooling                     |
| `style`    | Formatting, linting (no logic change)                       |
| `perf`     | Performance improvement                                     |

### Scopes

| Scope       | Meaning                                    |
|-------------|---------------------------------------------|
| `auth`      | Authentication / authorization              |
| `chat`      | Message sending, streaming, conversation    |
| `characters`| Character list, detail, templates          |
| `memory`    | Mem0 integration, memory display           |
| `voice`     | ElevenLabs TTS, STT                        |
| `navigation`| App navigation, routing                    |
| `ui`        | Shared UI components, theme                |
| `api`       | API client, network layer                  |
| `db`        | Database models, migrations                |
| `ci`        | GitHub Actions, build scripts              |

### Agent Names

`backend-dev`, `ios-dev`, `android-dev`, `backend-tester`, `ios-tester`, `android-tester`,
`architect`, `doc-writer`, `reviewer`

### Platform Tags

`backend`, `ios`, `android`, `mobile` (both mobile), `all`

### Examples

```bash
git commit -m "feat(chat): add SSE streaming support [agent:backend-dev] [platform:backend]"
git commit -m "fix(auth): handle Cognito token expiry on 401 [agent:ios-dev] [platform:ios]"
git commit -m "feat(memory): display Mem0 memories in settings [agent:android-dev] [platform:android]"
git commit -m "test(chat): add ChatViewModel unit tests [agent:ios-tester] [platform:ios]"
git commit -m "refactor(api): extract LLM provider abstraction [agent:backend-dev] [platform:backend]"
git commit -m "docs(standards): add cursor pagination rules [agent:architect] [platform:all]"
```

---

## 3. Branch Naming

```
feature/p{phase}/{feature-name}
fix/p{phase}/{issue-description}
chore/{description}
```

### Phase numbers

- `p1` — Phase 1: Foundation (auth, character list, basic chat)
- `p2` — Phase 2: Core Experience (streaming, memory display)
- `p3` — Phase 3: Voice
- `p4` — Phase 4: Advanced Features

### Examples

```
feature/p1/user-auth-cognito
feature/p1/character-list-screen
feature/p2/sse-streaming-chat
feature/p2/memory-display
fix/p1/token-refresh-loop
chore/setup-ci-pipeline
```

### Rules

- Branch names: lowercase, hyphens only (no underscores, no slashes except prefix).
- Never commit directly to `main`.
- Each feature branch corresponds to exactly one GitHub issue.
- Delete branch after PR merge.

---

## 4. Secrets Policy

### Never hardcode secrets

```python
# INCORRECT — NEVER DO THIS
API_KEY = "sk-ant-api03-..."
DATABASE_URL = "postgresql://user:password@host/db"
```

```swift
// INCORRECT — NEVER DO THIS
let apiKey = "sk-ant-api03-..."
```

### What counts as a secret

- API keys (Anthropic, OpenAI, Mem0, ElevenLabs)
- Database URLs with credentials
- JWT signing secrets
- AWS access keys and secret keys
- Cognito client secrets

### Where secrets live

| Environment | Backend | Mobile |
|-------------|---------|--------|
| Local dev   | `.env` file (gitignored) | `Config.xcconfig` (gitignored) / `local.properties` |
| CI          | GitHub Actions secrets | GitHub Actions secrets |
| Production  | AWS Secrets Manager | Fetched from backend at app start |

### Files that must be gitignored

```
.env
.env.*
!.env.example
Config.xcconfig
local.properties
google-services.json    # if contains private keys
*.p12
*.key
```

### .env.example (committed — empty values)

```bash
# .env.example
DEBUG=true
LOG_LEVEL=INFO
DATABASE_URL=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
MEM0_API_KEY=
ELEVENLABS_API_KEY=
COGNITO_USER_POOL_ID=
COGNITO_APP_CLIENT_ID=
AWS_REGION=us-east-1
LLM_PROVIDER=claude
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_HAIKU_MODEL=claude-haiku-4-5
OPENAI_MODEL=gpt-4o
OPENAI_FAST_MODEL=gpt-4o-mini
S3_BUCKET_NAME=
FIREBASE_CREDENTIALS_JSON=
RATE_LIMIT_CHAT=10
RATE_LIMIT_WRITE=20
RATE_LIMIT_READ=60
CORS_ORIGINS=*
SENTRY_DSN=
SENTRY_ENVIRONMENT=development
MAX_CONTEXT_MESSAGES=50
MEM0_CIRCUIT_FAILURE_THRESHOLD=3
MEM0_CIRCUIT_RECOVERY_TIMEOUT=60.0
MEM0_CACHE_TTL=300.0
MEM0_RETRY_QUEUE_MAX_SIZE=100
```

---

## 5. API Contract Rules

### Primary Reference

The API contract is defined in `docs/04-veri-api.md`. Before implementing any endpoint
(backend) or any API call (mobile), check that file.

If `docs/04-veri-api.md` and actual code differ, raise the discrepancy — do not silently
deviate from the spec.

### Contract Rules

1. Request and response fields follow `snake_case` naming.
2. All timestamps are ISO 8601 UTC strings: `"2026-02-23T14:30:00Z"`.
3. All IDs are UUIDs represented as strings.
4. Nullable fields are included with `null` value, not omitted from the response.
5. List endpoints always return `{"items": [...], "next_cursor": "...", "has_more": true}`.
6. The `Authorization` header is `Bearer <token>` on all authenticated endpoints.

### Adding a New Endpoint

1. Update `docs/04-veri-api.md` first.
2. Implement backend.
3. Update mobile API client.
4. All three steps in the same PR when possible (fullstack agent) or three coordinated PRs.

---

## 6. Cursor Pagination Rules

These rules apply on all platforms.

### Rules (Backend)

- Every list endpoint MUST use cursor pagination.
- OFFSET/LIMIT is forbidden in all new code.
- Cursor encodes `(created_at, id)` as base64 URL-safe JSON.
- Index required: `(user_id, character_id, created_at DESC, id DESC)`.
- Default `limit`: 20. Maximum `limit`: 100.
- Response always includes `next_cursor` (string or null) and `has_more` (boolean).

### Rules (Mobile)

- Store `nextCursor` from the last page response.
- Send `cursor` query param on subsequent fetches.
- When `hasMore` is false, stop fetching.
- Never send `page=2` or `offset=30` — these are forbidden.
- Append new results to existing list; do not replace.

### Pagination Response Shape

```json
{
  "items": [...],
  "next_cursor": "eyJ0cyI6ICIyMDI2LTAyLTIzVDE0OjMwOjAwWiIsICJpZCI6ICJ...",
  "has_more": true
}
```

When there are no more pages:

```json
{
  "items": [...],
  "next_cursor": null,
  "has_more": false
}
```

---

## 7. Error Response Format

All API errors return this exact shape:

```json
{
  "detail": "Human-readable error message"
}
```

### HTTP Status Code Guide

| Code | Meaning                          | When to Use                                              |
|------|----------------------------------|----------------------------------------------------------|
| 400  | Bad Request                      | Validation failed, malformed input                       |
| 401  | Unauthorized                     | Missing or invalid JWT                                   |
| 403  | Forbidden                        | Valid JWT but insufficient permission                    |
| 404  | Not Found                        | Resource does not exist                                  |
| 409  | Conflict                         | Duplicate creation attempt                               |
| 422  | Unprocessable Entity             | Pydantic validation failure (FastAPI auto)               |
| 429  | Too Many Requests                | Rate limit exceeded                                      |
| 500  | Internal Server Error            | Unexpected server error (never expose stack traces)      |
| 503  | Service Unavailable              | Upstream dependency (LLM, Mem0) is down                  |

### Mobile Error Handling

Mobile clients must handle these status codes:

- `401`: Clear stored token, redirect to login screen.
- `403`: Show "Access denied" message, do not retry.
- `404`: Show "Not found" message specific to the resource.
- `429`: Show "Too many requests, please wait" and back off.
- `500` / `503`: Show "Something went wrong, please try again" with retry button.

---

## 8. Security Rules

### JWT Only

- Authentication is JWT-only via AWS Cognito.
- No session cookies.
- No API keys for mobile clients.
- Token storage: iOS Keychain, Android EncryptedSharedPreferences.
- Never store tokens in UserDefaults, SharedPreferences (unencrypted), or local storage.

### HTTPS Only

- All API calls must use HTTPS.
- No HTTP in production, staging, or review environments.
- Mobile: certificate pinning is a Phase 3 item (tracked separately).

### No PII in Logs

- Never log email addresses, names, phone numbers, or message content.
- Log user ID (UUID) is acceptable for tracing.
- In production: structured logging (JSON) to CloudWatch.

### Input Validation

- Backend: Pydantic validators on all request fields.
- Mobile: Trim whitespace, reject empty strings before sending.
- Max message content length: 4000 characters (enforced backend + mobile).

### SQL Injection

- All queries use SQLAlchemy parameterized statements.
- Raw SQL is forbidden unless there is no ORM alternative (document why).

---

## 9. Performance Targets

These targets apply in production with real load.

| Metric                                | Target     |
|---------------------------------------|------------|
| POST /characters/:id/messages (TTFB)  | < 2000ms   |
| SSE first token (TTFT)                | < 1500ms   |
| GET /characters (list)                | < 500ms    |
| GET /characters/:id/messages          | < 300ms    |
| iOS app cold start                    | < 3s       |
| Android app cold start                | < 3s       |
| Memory search (Mem0)                  | < 800ms    |
| Voice synthesis (ElevenLabs TTFB)     | < 1200ms   |
| API p99 latency                       | < 5000ms   |
| API error rate                        | < 0.1%     |

Performance regressions introduced by a PR must be justified in the PR description.

---

## 10. Code Review Checklist

Every PR must pass this checklist before merge.

### Security

- [ ] No secrets hardcoded or logged
- [ ] `user_id` extracted from JWT, never from request body
- [ ] Input validation present on all new endpoints
- [ ] Authorization checks: user can only access their own data

### Architecture

- [ ] Single conversation per character rule preserved
- [ ] Message endpoint is `POST /characters/:id/messages`
- [ ] Mem0 `agent_id` uses format `{template_id}_{user_id}`
- [ ] Cursor pagination used (no OFFSET/LIMIT)
- [ ] API contract in `docs/04-veri-api.md` matches implementation

### Code Quality

- [ ] All new functions have type annotations (backend)
- [ ] No business logic in route handlers (backend)
- [ ] No business logic in SwiftUI View body (iOS)
- [ ] No business logic in Composable functions (Android)
- [ ] No `print()` / `println()` in production code — use logging
- [ ] Error paths are handled (not just happy path)

### Testing

- [ ] New code has unit tests (80% line coverage minimum)
- [ ] Error paths are tested
- [ ] No real network calls in unit tests
- [ ] Mocks/fakes use protocols (mobile) or `unittest.mock` (backend)

### Performance

- [ ] No N+1 queries (use `asyncio.gather` or SQL joins)
- [ ] No synchronous blocking calls in async functions
- [ ] Images use lazy loading (Kingfisher / Coil)

### Mobile Specific

- [ ] Dark mode verified (Ember forces dark mode)
- [ ] Accessibility labels on interactive elements
- [ ] Haptic feedback on primary actions
- [ ] `collectAsStateWithLifecycle` used (Android, not `collectAsState`)
- [ ] `@Observable` used (iOS, not `ObservableObject`)

### Documentation

- [ ] New endpoints documented in `docs/04-veri-api.md`
- [ ] ADR written for significant architecture decisions
- [ ] Commit message follows `<type>(<scope>): <desc> [agent:x] [platform:y]` format
