# CLAUDE.md — Ember AI Companion

## Project Identity

- **App Name**: Ember
- **Type**: Personal AI companion — memory-first, proactive, multi-character
- **Platforms**: Native iOS (Swift + SwiftUI) + Native Android (Kotlin + Jetpack Compose)
- **Backend**: Python 3.12 + FastAPI
- **Status**: Active development

## Architecture at a Glance

```
[iOS App]        [Android App]
    ↕ REST API + SSE          ↕
       [FastAPI Backend — ECS Fargate]
       ↕             ↕             ↕
  [RDS PostgreSQL]  [Mem0.ai]  [Anthropic Claude]
       ↕                            ↕
    [AWS S3]              [ElevenLabs / Whisper]
       ↕
  [Firebase FCM]
```

**Key insight**: Ember is NOT session-based like ChatGPT. Each character has ONE
continuous conversation forever. Mem0 provides long-term memory across time.
Context window: last 50 messages (configurable via `max_context_messages`) + Mem0 semantic search results (max 10 memories).

## Full Documentation

All architectural decisions, data models, API contracts, and feature specs live in `docs/`.
**Agents: read the relevant doc before implementing. Never guess the architecture.**

| Doc | What it covers |
|-----|----------------|
| `docs/01-vizyon.md` | Vision, problem, target audience, competitive analysis |
| `docs/02-ozellikler.md` | All features and user stories |
| `docs/03-mimari.md` | System architecture, LLM multi-provider strategy |
| `docs/04-veri-api.md` | Database schema, API endpoints, pagination rules |
| `docs/05-ai-bellek.md` | Mem0 integration, memory isolation per character, prompt architecture |
| `docs/06-bildirimler.md` | Proactive notification system, FCM flow, triggers |
| `docs/07-mobil.md` | Mobile screens, navigation, iOS/Android tech stack |
| `docs/08-guvenlik-performans.md` | Security (JWT, IAM, S3 isolation), performance targets |
| `docs/09-dagitim.md` | AWS deployment (ECS, RDS, S3, Cognito), CI/CD |
| `docs/10-yol-haritasi.md` | 12-phase roadmap with task checklists |
| `docs/11-acik-sorular.md` | All architectural decisions (all decided, reference here) |
| `docs/12-ses-voice.md` | TTS (ElevenLabs Flash v2.5), STT (Whisper), async voice |
| `docs/13-cihaz-entegrasyonu.md` | Device integration: alarm, calendar, call log |
| `docs/14-tasarim.md` | Design system: colors, typography, animations, dark mode |
| `docs/15-fiyatlandirma.md` | Freemium pricing, cost analysis, tier structure |
| `docs/16-karakterler.md` | Multi-character system, memory isolation, templates |
| `docs/17-gercek-zamanli-ses.md` | Real-time voice call: LiveKit + Deepgram + ElevenLabs |

**Architecture Decision Records** (why we chose what we chose):

| ADR | Decision |
|-----|---------|
| `docs/adr/ADR-001-native-over-flutter.md` | Native iOS + Android, not Flutter |
| `docs/adr/ADR-002-postgresql-pgvector.md` | PostgreSQL + pgvector, not alternatives |
| `docs/adr/ADR-003-single-conversation.md` | One conversation per character forever |
| `docs/adr/ADR-004-mem0-memory.md` | Mem0.ai for long-term memory layer |
| `docs/adr/ADR-005-monorepo.md` | Monorepo (backend + iOS + Android) |
| `docs/adr/ADR-006-multi-provider-llm.md` | Multi-provider LLM (Claude default) |

## Technology Stack

### Backend
- **Runtime**: Python 3.12 + FastAPI (async)
- **Database**: AWS RDS PostgreSQL 16 + pgvector 0.8.0
- **Memory**: Mem0.ai cloud (each character has isolated `agent_id`)
- **Auth**: AWS Cognito (JWT RS256, 1h access token, 30d refresh)
- **Storage**: AWS S3 (files at `{type}/{user_id}/{filename}`)
- **AI**: Anthropic Claude (Sonnet 4.6 default, Haiku 4.5 for fast ops)
- **TTS**: ElevenLabs Flash v2.5 (135ms TTFA, multilingual) + AWS Polly Burcu (fallback)
- **STT**: OpenAI Whisper (batch, async) — NOT real-time
- **Push**: Firebase Admin SDK (Python)
- **Hosting**: AWS ECS Fargate

### iOS
- **Language**: Swift 5.9+, iOS 17+ minimum
- **UI**: SwiftUI + NavigationStack
- **State**: `@Observable` (iOS 17+)
- **Async**: Swift Concurrency (async/await)
- **SSE**: URLSession + AsyncStream
- **Auth**: AWS Amplify Cognito iOS SDK
- **Images**: Kingfisher
- **Animations**: Lottie iOS

### Android
- **Language**: Kotlin 2.1+
- **UI**: Jetpack Compose + Material 3
- **State**: ViewModel + StateFlow + collectAsStateWithLifecycle
- **Async**: Kotlin Coroutines
- **Network**: OkHttp + Retrofit
- **SSE**: OkHttp EventSource
- **Auth**: AWS Amplify Cognito Android SDK
- **Images**: Coil
- **Animations**: Lottie Android

## Critical Rules (All Agents)

### Backend
1. **All routes async** — `async def` everywhere, no blocking calls
2. **asyncio.gather()** for parallel operations (Mem0 search + DB query)
3. **Cursor-based pagination only** — NEVER use OFFSET/LIMIT on messages table
   ```sql
   -- CORRECT: cursor pagination
   WHERE conversation_id = $1 AND created_at < $cursor ORDER BY created_at DESC LIMIT 20
   -- WRONG: OFFSET pagination
   LIMIT 20 OFFSET 200  -- O(n) scan, forbidden
   ```
4. **No hardcoded secrets** — use AWS Secrets Manager / Parameter Store
5. **JWT extraction** — always get `user_id` from JWT, never from request body
6. **Rate limiting** — grouped: 10/min chat, 20/min write, 60/min read (see `config.py`)
7. **Memory isolation** — `agent_id = f"{template}_{user_id}"` per character

### iOS
1. **@Observable only** (iOS 17+) — no ObservableObject/Published
2. **No force unwrap** (`!`) — use `guard let` or `if let`
3. **NavigationStack** — not NavigationView
4. **Dark mode default** — `.preferredColorScheme(.dark)`
5. **Kingfisher** for all network images
6. **Accessibility** — `accessibilityLabel` on all icon buttons

### Android
1. **No `!!` (force unwrap)** — handle nulls explicitly
2. **StateFlow + collectAsStateWithLifecycle** — not LiveData
3. **Immutable data classes** — val not var in domain models
4. **No hardcoded strings** — `strings.xml` only
5. **Coil** for all network images
6. **HapticFeedbackConstants** for haptics

### All Agents
- Read `docs/04-veri-api.md` before touching any API endpoint
- Message endpoint: `POST /characters/:id/messages` (NOT `/conversations`)
- Conversations are auto-created per character — users never see "new conversation"
- Mem0 `agent_id` format: `"{template}_{user_id}"` — NEVER mix characters

## Detailed Standards

| Document | Who reads it |
|----------|-------------|
| `docs/standards/backend.md` | backend-dev, backend-tester |
| `docs/standards/ios.md` | ios-dev, ios-tester |
| `docs/standards/android.md` | android-dev, android-tester |
| `docs/standards/testing.md` | All testers, reviewer |
| `docs/standards/common.md` | All agents |

## Pipeline

9 specialized agents work in sequence with parallel phases:

```
Architect → [Backend Dev ‖ iOS Dev ‖ Android Dev]
          → [Backend Tester ‖ iOS Tester ‖ Android Tester]
          → Doc Writer → Reviewer → Quality Gate
```

Layer-specific pipelines for non-fullstack features:
- `backend` layer: Architect → Backend Dev → Backend Tester → Doc → Review
- `ios` layer: Architect → iOS Dev → iOS Tester → Doc → Review
- `android` layer: Architect → Android Dev → Android Tester → Doc → Review
- `mobile` layer: Architect → [iOS Dev ‖ Android Dev] → [iOS Tester ‖ Android Tester] → Doc → Review
- `fullstack` layer: Full 9-agent pipeline above

| Agent | Model | Reads |
|-------|-------|-------|
| `architect` | Opus | `CLAUDE.md` + relevant `docs/` sections |
| `backend-dev` | Opus | `CLAUDE.md` + `docs/standards/backend.md` + `docs/04-veri-api.md` |
| `ios-dev` | Opus | `CLAUDE.md` + `docs/standards/ios.md` + `docs/07-mobil.md` |
| `android-dev` | Opus | `CLAUDE.md` + `docs/standards/android.md` + `docs/07-mobil.md` |
| `backend-tester` | Sonnet | `CLAUDE.md` + `docs/standards/testing.md` |
| `ios-tester` | Sonnet | `CLAUDE.md` + `docs/standards/testing.md` |
| `android-tester` | Sonnet | `CLAUDE.md` + `docs/standards/testing.md` |
| `doc-writer` | Sonnet | `CLAUDE.md` |
| `reviewer` | Opus | `CLAUDE.md` + `docs/standards/common.md` + all platform standards |

Commands: `/pipeline-run`, `/create-pr`, `/verify`

Full pipeline documentation: `docs/PIPELINE-GUIDE.md`

## Git Workflow

### Branch Naming
- `feature/p{phase}/{feature-name}` — e.g., `feature/p01/user-auth`
- `fix/p{phase}/{description}` — e.g., `fix/p01/jwt-expiry`

### Commit Convention
```
<type>(<scope>): <description> [agent:<name>] [platform:<backend|ios|android|all>]
```
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `infra`, `chore`

Example:
```
feat(auth): implement JWT middleware [agent:backend-dev] [platform:backend]
feat(chat): implement ChatView SSE streaming [agent:ios-dev] [platform:ios]
test(auth): add auth endpoint tests [agent:backend-tester] [platform:backend]
```

### Merge Strategy
- Feature → develop: Squash merge (auto-merge via CI for `agent:pipeline` label)
- develop → main: Merge commit

PR body MUST include `Closes #N` to auto-close the linked GitHub issue.

## GitHub Workflow

Issues tracked with **Milestones** (one per phase) and **Labels**.

Issue map: `scripts/issue-map.json` (feature ID → GitHub issue number)

### Labels
- `phase:1` through `phase:12` + `phase:1.5` (purple shades)
- `layer:backend`, `layer:ios`, `layer:android`, `layer:mobile`, `layer:fullstack`
- `type:model`, `type:api`, `type:ui`, `type:service`, `type:infra`, `type:integration`

## Key File Locations

### Backend
- `backend/app/main.py` — FastAPI app entry
- `backend/app/routes/` — API route handlers
- `backend/app/services/` — Business logic
- `backend/app/models/` — SQLAlchemy models
- `backend/app/utils/` — Helpers (auth, pagination, etc.)
- `backend/tests/` — pytest test suite
- `backend/requirements.txt` — Dependencies
- `backend/Dockerfile` — Container config

### iOS
- `ios/Ember/` — Source root
- `ios/Ember/Core/` — Shared (networking, auth, design system)
- `ios/Ember/Feature/` — Feature modules

### Android
- `android/app/src/main/java/com/ember/` — Source root
- `android/app/src/main/java/com/ember/core/` — Shared
- `android/app/src/main/java/com/ember/feature/` — Feature modules

### Shared
- `shared/api-contracts/` — OpenAPI YAML specs (source of truth for all API)
- `shared/feature-specs/` — Architect output (platform-agnostic specs)
- `scripts/feature-queue.jsonl` — Feature queue (all phases)
- `scripts/issue-map.json` — feature-id → GitHub issue number

## CI/CD

GitHub Actions in `.github/workflows/`:
- `backend-ci.yml` — pytest + ruff + mypy (path: `backend/**`)
- `ios-ci.yml` — SwiftLint + xcodebuild test (path: `ios/**`)
- `android-ci.yml` — ktlint + detekt + gradle test (path: `android/**`)
- `auto-merge.yml` — Squash merge for `agent:pipeline` PRs

---

**Last Updated**: 2026-02-24
**App Name**: Ember
**Stack**: Python/FastAPI + iOS Swift/SwiftUI + Android Kotlin/Compose
