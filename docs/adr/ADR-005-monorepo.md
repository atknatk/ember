# ADR-005: Monorepo for Backend, iOS, and Android

| Field    | Value                    |
|----------|--------------------------|
| Date     | 2026-02-23               |
| Status   | Accepted                 |
| Deciders | Architecture Team        |
| Replaces | —                        |

---

## Context

Ember has three codebases:

1. **Backend** — Python/FastAPI, in `backend/`
2. **iOS** — Swift/SwiftUI, in `ios/`
3. **Android** — Kotlin/Compose, in `android/`

The team must decide whether to maintain these in:

- **One repository** (monorepo): all three platforms in `github.com/ember-ai/ember`
- **Three separate repositories**: `ember-backend`, `ember-ios`, `ember-android`

---

## Decision

**Use a single monorepo containing all three platforms.**

```
ember/                   # root
  backend/               # Python/FastAPI
  ios/                   # Swift/SwiftUI
  android/               # Kotlin/Compose
  docs/                  # shared documentation
    04-veri-api.md       # API contract (single source of truth)
    standards/           # platform coding standards
    adr/                 # architecture decisions
  .pipeline/             # pipeline config and handoffs
  CLAUDE.md              # instructions for AI agents
  README.md
```

---

## Reasons

### 1. AI Development Context

The primary reason for choosing a monorepo is the AI-assisted development workflow.

Claude Code agents (backend-agent, ios-agent, android-agent) read the repository to understand
context before implementing features. In a monorepo:

- `backend-agent` can read the iOS and Android schemas to understand what the mobile clients
  expect from the API response.
- `ios-agent` can read the backend route implementation to verify endpoint availability.
- `android-agent` can read the iOS implementation to maintain parity.
- All agents read `docs/04-veri-api.md` — the API contract — which is in the same repo.
- All agents read `docs/standards/` — the coding standards — in the same repo.

In a poly-repo setup, an agent working on iOS would need to read from the backend repository
separately. This requires additional configuration, cross-repo access tokens, and the risk
that the agent operates on a stale version of the contract.

With a monorepo, every agent has full, current context in a single `git clone`.

### 2. Atomic Pull Requests for Fullstack Features

Many Ember features span all three platforms:

- Feature: "SSE Streaming Chat" requires backend SSE endpoint + iOS SSE client + Android SSE client.
- Feature: "Memory Display" requires a backend memory endpoint + iOS settings screen + Android settings screen.

In a poly-repo setup, implementing this requires:

- PR #12 in `ember-backend`
- PR #8 in `ember-ios`
- PR #7 in `ember-android`

These PRs are independent and can merge in any order. A backend PR may merge before the
mobile PRs are ready, breaking mobile clients on staging. Mobile PRs may merge before the
backend PR, causing crashes.

In a monorepo:

- One PR with changes in `backend/`, `ios/`, and `android/`.
- CI runs all three test suites in the same check.
- The entire feature is reviewed atomically.
- The feature ships when all three are ready — not before.

### 3. Single CLAUDE.md

`CLAUDE.md` at the repository root is the primary instruction file for AI agents.
It contains project context, agent roles, pipeline instructions, and references to
the standards documents.

With one repo, one `CLAUDE.md` covers all three platforms. AI agents always read this
file first when entering a new session. The context is complete and current.

With three repos, there would be three `CLAUDE.md` files. Keeping them in sync requires
a coordination mechanism. They will inevitably drift. An iOS agent might read stale context
about the backend API contract.

### 4. Shared API Contract in docs/04-veri-api.md

The API contract is the most critical shared artifact. It defines:

- All endpoints, HTTP methods, request bodies, and response schemas.
- Pagination format.
- Error response format.
- Authentication requirements.

In a monorepo, this document lives in `docs/04-veri-api.md`. All agents read it from the same
location. A backend-agent updating the API must update this file in the same commit/PR as the
implementation. An ios-agent implementing a new feature reads the contract in the same workspace.

In a poly-repo, the API contract would live in a fourth repository (`ember-docs`) or be
duplicated. The risk of the contract being out of sync with the implementation is high.

### 5. Shared Standards Documents

`docs/standards/backend.md`, `docs/standards/ios.md`, `docs/standards/android.md`,
`docs/standards/common.md` — these are the coding standards that govern all three platforms.

A monorepo ensures that:
- Platform standards reference each other (e.g., common.md is referenced by backend.md).
- Security rules in common.md are visible to all agents regardless of platform.
- Changes to standards are versioned alongside code.

### 6. Cross-Platform Visibility for Code Review

The review-agent checks all code against `docs/standards/`. In a monorepo, reviewing a
fullstack feature means one review pass across `backend/`, `ios/`, and `android/` together.

The reviewer can verify:
- Backend response schema matches what iOS/Android expects.
- Error codes on the backend are handled on mobile.
- Cursor pagination is consistently implemented on all three.

In separate repos, this cross-cutting review would require reading three separate PRs
in three separate repositories and correlating them manually.

---

## Repository Structure

```
ember/
  .github/
    workflows/
      backend-ci.yml
      ios-ci.yml
      android-ci.yml
      pipeline.yml
  .pipeline/
    feature-queue.jsonl
    issue-map.json
    handoffs/
  backend/
    app/
    tests/
    pyproject.toml
    Dockerfile
  ios/
    EmberApp/
    EmberApp.xcodeproj/
    EmberAppTests/
  android/
    app/
    build.gradle.kts
    settings.gradle.kts
  docs/
    01-proje-ozeti.md
    04-veri-api.md
    08-guvenlik-performans.md
    14-tasarim.md
    standards/
      common.md
      backend.md
      ios.md
      android.md
      testing.md
    adr/
      ADR-001-native-over-flutter.md
      ADR-002-postgresql-pgvector.md
      ...
  CLAUDE.md
  README.md
```

---

## CI Configuration

Each platform has its own CI workflow, but they all run on PRs that touch their directory:

```yaml
# .github/workflows/backend-ci.yml
on:
  push:
    paths: ["backend/**"]
  pull_request:
    paths: ["backend/**"]

# .github/workflows/ios-ci.yml
on:
  push:
    paths: ["ios/**"]
  pull_request:
    paths: ["ios/**"]
```

A fullstack PR touching all three directories triggers all three CI workflows in parallel.

---

## Consequences

### Positive

- Complete cross-cutting context for every AI agent in a single `git clone`.
- Atomic PRs for fullstack features.
- Single API contract, single `CLAUDE.md`, single `docs/`.
- Cross-platform code review in one PR.
- Consistent CI that validates all platforms before merge.

### Negative

- Repository size grows faster (iOS binaries, Android build artifacts must be gitignored carefully).
- CI for a pure-backend change still runs backend CI only — but the repo checkout is larger.
- Developers unfamiliar with a platform may accidentally modify files in the wrong directory.
- `git clone` is slower for a large monorepo (mitigated with sparse checkout for platform-specific work).

### Accepted Trade-offs

- Repository size: iOS and Android build artifacts are in `.gitignore`. Only source code
  is committed. Expected repo size: < 500 MB.
- Sparse checkout is available for developers who only work on one platform.
- The CI path filter (`paths: ["backend/**"]`) ensures backend changes don't trigger
  iOS CI and vice versa, keeping CI fast.

---

## Alternatives Considered

### Three Separate Repositories

Rejected because:
- AI agent context is fragmented across repos.
- API contract synchronization is error-prone.
- Fullstack features require coordinating three separate PRs.
- Review across platforms requires reading three separate codebases.

### Two Repositories (backend + mobile)

Considered: `ember-backend` and `ember-mobile` (with iOS and Android subfolders).

Partially addresses the mobile parity issue but still:
- Splits the API contract from the backend implementation.
- AI backend-agent cannot see mobile client code.
- Two CLAUDE.md files to maintain.

Rejected for the same AI context fragmentation reason as three separate repos.

### Nx or Turborepo Monorepo Tool

Considered for managing build caching across platforms.

Deferred: the current three-platform setup does not need a monorepo build tool.
If the repo grows to include additional services (e.g., a separate notification service,
an admin dashboard), a monorepo tool may be added in Phase 4.
