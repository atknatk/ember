# Ember Pipeline Guide

The 9-agent development pipeline for the Ember project.

This document explains how to trigger the pipeline, how it works, what each agent does,
and how to handle failures. Zero-memory sessions must read this before triggering any pipeline run.

---

## Table of Contents

1. Overview
2. How to Trigger the Pipeline
3. Agent Roster
4. Layer Types
5. Feature Queue Format
6. Issue Map Format
7. Pipeline Phases and Flow
8. Handoff File Format
9. Quality Gates
10. Resuming a Failed Pipeline
11. Branch Naming and PR Creation
12. GitHub Issue Lifecycle

---

## 1. Overview

The Ember pipeline is a sequential 9-agent workflow. Each agent reads a handoff file from
the previous agent, does its work, writes a new handoff file, and triggers the next agent.

```
PM → Architect → Backend → iOS → Android → QA → DevOps → Review → Merge
```

- Each agent works independently and in sequence.
- Agents communicate through handoff files in `.pipeline/handoffs/`.
- The pipeline is triggered manually via the `/pipeline-run` command.
- Failures stop the pipeline; humans review and resume from the failed agent.

---

## 2. How to Trigger the Pipeline

```
/pipeline-run <feature-id> <feature-name> [--issue <github-issue-number>]
```

### Examples

```bash
# Start new pipeline run for a feature
/pipeline-run P01-01 user-auth --issue 5

# Start without a pre-existing GitHub issue (PM agent creates one)
/pipeline-run P01-02 character-list

# Resume from a specific agent after a failure
/pipeline-run P01-01 user-auth --resume-from backend-agent --issue 5
```

### Feature ID Format

```
P{phase:02d}-{sequence:02d}

P01-01  = Phase 1, Feature 1
P01-02  = Phase 1, Feature 2
P02-01  = Phase 2, Feature 1
```

Feature IDs come from `feature-queue.jsonl`.

### Parameters

| Parameter          | Required | Description                                      |
|--------------------|----------|--------------------------------------------------|
| `feature-id`       | Yes      | ID from `feature-queue.jsonl`                    |
| `feature-name`     | Yes      | Short kebab-case name used for branch naming     |
| `--issue`          | No       | GitHub issue number to link                      |
| `--resume-from`    | No       | Agent name to restart from (skips earlier agents)|
| `--layer`          | No       | Override layer (backend/ios/android/mobile/fullstack) |

---

## 3. Agent Roster

| Agent Name         | Role                                                        | Produces                     |
|--------------------|-------------------------------------------------------------|------------------------------|
| `pm-agent`         | Accepts feature request, writes spec, creates GitHub issue  | `spec.md`, GitHub issue      |
| `architect-agent`  | Reviews spec, writes technical design, identifies risks     | `technical-design.md`        |
| `backend-agent`    | Implements FastAPI endpoints, services, DB migrations       | Backend code, tests          |
| `ios-agent`        | Implements SwiftUI screens and networking                   | iOS code, tests              |
| `android-agent`    | Implements Compose screens and networking                   | Android code, tests          |
| `qa-agent`         | Writes integration tests, validates coverage, files bugs    | Test files, bug reports      |
| `devops-agent`     | Updates CI/CD, infra configs, Docker if needed              | CI config, infra changes     |
| `review-agent`     | Code review against standards, security check              | Review comments, approval    |
| `merge-agent`      | Merges approved PRs, closes issues, updates changelog       | Merged PRs, closed issues    |

---

## 4. Layer Types

Specify the layer when the feature affects only a subset of agents.

| Layer        | Agents That Run                               | Use When                               |
|--------------|-----------------------------------------------|----------------------------------------|
| `fullstack`  | All 9 agents                                  | Feature spans backend + both mobile    |
| `backend`    | pm, architect, backend, qa, devops, review, merge | API-only change, no mobile UI        |
| `mobile`     | pm, architect, ios, android, qa, review, merge | Mobile-only UI change (no new API)    |
| `ios`        | pm, architect, ios, qa, review, merge         | iOS-only change                        |
| `android`    | pm, architect, android, qa, review, merge     | Android-only change                    |

```bash
/pipeline-run P01-01 user-auth --layer fullstack
/pipeline-run P02-03 fix-android-crash --layer android
/pipeline-run P01-05 api-rate-limiting --layer backend
```

---

## 5. Feature Queue Format

Location: `.pipeline/feature-queue.jsonl`

One JSON object per line. Each line is one feature.

```jsonl
{"id": "P01-01", "name": "user-auth", "title": "User Authentication via Cognito", "phase": 1, "layer": "fullstack", "priority": 1, "status": "pending", "issue": null}
{"id": "P01-02", "name": "character-list", "title": "Character List & Detail Screens", "phase": 1, "layer": "fullstack", "priority": 2, "status": "pending", "issue": null}
{"id": "P01-03", "name": "basic-chat", "title": "Basic Text Chat (non-streaming)", "phase": 1, "layer": "fullstack", "priority": 3, "status": "pending", "issue": null}
{"id": "P01-04", "name": "conversation-history", "title": "Load Conversation History with Cursor Pagination", "phase": 1, "layer": "fullstack", "priority": 4, "status": "pending", "issue": null}
{"id": "P02-01", "name": "sse-streaming", "title": "SSE Streaming Chat Responses", "phase": 2, "layer": "fullstack", "priority": 1, "status": "pending", "issue": null}
{"id": "P02-02", "name": "mem0-memory", "title": "Mem0 Memory Integration", "phase": 2, "layer": "backend", "priority": 2, "status": "pending", "issue": null}
{"id": "P02-03", "name": "memory-display", "title": "Memory Display in Settings", "phase": 2, "layer": "mobile", "priority": 3, "status": "pending", "issue": null}
```

### Feature Status Values

| Status       | Meaning                                      |
|--------------|----------------------------------------------|
| `pending`    | Not yet started                              |
| `in-progress`| Pipeline is running for this feature         |
| `blocked`    | Pipeline stopped, waiting for human action   |
| `done`       | All PRs merged, issue closed                 |

### Updating the Queue

After the pipeline completes a feature:

```jsonl
{"id": "P01-01", "name": "user-auth", ..., "status": "done", "issue": 5, "pr": 12}
```

---

## 6. Issue Map Format

Location: `.pipeline/issue-map.json`

Maps feature IDs to GitHub issue numbers and PR numbers.

```json
{
  "P01-01": {
    "issue": 5,
    "prs": {
      "backend": 12,
      "ios": 13,
      "android": 14
    },
    "branch": "feature/p1/user-auth",
    "status": "merged",
    "completed_at": "2026-02-23T14:30:00Z"
  },
  "P01-02": {
    "issue": 6,
    "prs": {},
    "branch": "feature/p1/character-list",
    "status": "in-progress",
    "completed_at": null
  }
}
```

---

## 7. Pipeline Phases and Flow

```
┌─────────────┐
│   TRIGGER   │  /pipeline-run P01-01 user-auth --issue 5
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  pm-agent   │  Reads feature-queue.jsonl
│             │  Writes spec + acceptance criteria
│             │  Creates/links GitHub issue
└──────┬──────┘
       │ handoff: pm-to-architect.json
       ▼
┌──────────────────┐
│ architect-agent  │  Reviews spec
│                  │  Writes technical design
│                  │  Identifies DB schema, API contract changes
└──────┬───────────┘
       │ handoff: architect-to-backend.json
       ▼
┌───────────────┐
│ backend-agent │  Creates branch feature/p1/user-auth
│               │  Implements routes, services, models
│               │  Writes unit tests
│               │  Opens backend PR
└──────┬────────┘
       │ handoff: backend-to-ios.json
       ▼
┌───────────┐
│ ios-agent │  Implements SwiftUI screens
│           │  Wires API client
│           │  Writes unit tests
│           │  Opens iOS PR
└──────┬────┘
       │ handoff: ios-to-android.json
       ▼
┌──────────────┐
│ android-agent│  Implements Compose screens
│              │  Wires Retrofit/OkHttp
│              │  Writes unit tests
│              │  Opens Android PR
└──────┬───────┘
       │ handoff: android-to-qa.json
       ▼
┌──────────┐
│ qa-agent │  Runs all tests
│          │  Validates coverage >= thresholds
│          │  Files bug issues if failures found
│          │  Writes integration tests
└──────┬───┘
       │ handoff: qa-to-devops.json
       ▼
┌─────────────┐
│ devops-agent│  Updates CI if needed
│             │  Validates Docker/infra configs
│             │  Ensures deployment config correct
└──────┬──────┘
       │ handoff: devops-to-review.json
       ▼
┌──────────────┐
│ review-agent │  Reviews code vs docs/standards/
│              │  Security check
│              │  Leaves PR review comments
│              │  Approves or requests changes
└──────┬───────┘
       │ handoff: review-to-merge.json
       ▼
┌─────────────┐
│ merge-agent │  Squash-merges approved PRs
│             │  Closes GitHub issue
│             │  Updates feature-queue.jsonl status to "done"
│             │  Updates issue-map.json
│             │  Updates CHANGELOG
└─────────────┘
```

---

## 8. Handoff File Format

Location: `.pipeline/handoffs/{feature-id}/{from-agent}-to-{to-agent}.json`

Example: `.pipeline/handoffs/P01-01/pm-to-architect.json`

```json
{
  "feature_id": "P01-01",
  "feature_name": "user-auth",
  "from_agent": "pm-agent",
  "to_agent": "architect-agent",
  "timestamp": "2026-02-23T10:00:00Z",
  "status": "success",
  "github_issue": 5,
  "outputs": {
    "spec_file": "docs/specs/P01-01-user-auth.md",
    "acceptance_criteria": [
      "User can sign up with email and password",
      "User can sign in and receive JWT",
      "Invalid credentials return 401",
      "Expired token returns 401 with WWW-Authenticate header"
    ]
  },
  "notes": "Cognito user pool already provisioned in staging. See docs/08-guvenlik-performans.md for auth architecture."
}
```

```json
{
  "feature_id": "P01-01",
  "feature_name": "user-auth",
  "from_agent": "backend-agent",
  "to_agent": "ios-agent",
  "timestamp": "2026-02-23T11:30:00Z",
  "status": "success",
  "github_issue": 5,
  "branch": "feature/p1/user-auth",
  "pr_number": 12,
  "outputs": {
    "endpoints_implemented": [
      "POST /auth/register",
      "POST /auth/login",
      "GET /auth/me"
    ],
    "new_env_vars": [
      "COGNITO_USER_POOL_ID",
      "COGNITO_APP_CLIENT_ID"
    ],
    "migration": "db/migrations/versions/20260223_add_users_table.py"
  },
  "notes": "Token is returned as access_token field in login response. Use Bearer scheme."
}
```

### Handoff Status Values

| Status      | Meaning                                             |
|-------------|-----------------------------------------------------|
| `success`   | Agent completed successfully, next agent may proceed|
| `failed`    | Agent failed, pipeline stopped                      |
| `skipped`   | Agent not needed for this layer type                |
| `blocked`   | Agent waiting on external dependency                |

---

## 9. Quality Gates

The pipeline will not advance past these gates if the criteria are not met.

### After backend-agent

- [ ] All backend unit tests pass: `pytest tests/ -v`
- [ ] Type check passes: `mypy app --strict`
- [ ] Lint passes: `ruff check app && black --check app`
- [ ] Backend PR opened and CI passes

### After ios-agent

- [ ] All iOS unit tests pass: `xcodebuild test -scheme EmberApp ...`
- [ ] No SwiftLint warnings
- [ ] iOS PR opened and CI passes

### After android-agent

- [ ] All Android unit tests pass: `./gradlew testDebugUnitTest`
- [ ] Lint passes: `./gradlew lintDebug ktlintCheck`
- [ ] Android PR opened and CI passes

### After qa-agent

- [ ] Line coverage >= 80% on all platforms
- [ ] Branch coverage >= 70% on all platforms
- [ ] No open P0/P1 bugs from this feature (P2+ are acceptable with issue filed)
- [ ] Integration tests pass

### After review-agent

- [ ] All review comments addressed or acknowledged
- [ ] No CRITICAL or HIGH security findings
- [ ] All checklist items in `docs/standards/common.md` checked

---

## 10. Resuming a Failed Pipeline

When a pipeline run fails, the handoff file from the failed agent contains `"status": "failed"`.

### Resume Command

```bash
/pipeline-run P01-01 user-auth --resume-from <failed-agent> --issue 5
```

### Steps to Resume

1. Check the failed handoff file:
   ```
   .pipeline/handoffs/P01-01/{previous-agent}-to-{failed-agent}.json
   ```

2. Read the `notes` and `error` fields to understand the failure.

3. Fix the issue (may require human intervention).

4. Run the resume command to restart from the failed agent.

The resume command skips all agents before `--resume-from` and re-reads the last
successful handoff file.

### Common Failure Scenarios

| Failure                          | Fix                                                         |
|----------------------------------|-------------------------------------------------------------|
| Test coverage below threshold    | qa-agent files coverage report; dev agent adds tests        |
| Compilation error in mobile code | Mobile agent re-runs with fix                               |
| API contract mismatch            | Both agents align on `docs/04-veri-api.md`                  |
| CI timeout                       | devops-agent investigates; resume from devops-agent         |
| Review blocked on security issue | Fix the security issue; resume from review-agent            |

---

## 11. Branch Naming and PR Creation

### Branch

All pipeline features use a single branch per feature (all platforms):

```
feature/p{phase}/{feature-name}

feature/p1/user-auth
feature/p1/character-list
feature/p2/sse-streaming
```

For platform-specific changes within a feature, use sub-branches if needed:

```
feature/p1/user-auth-backend
feature/p1/user-auth-ios
feature/p1/user-auth-android
```

### PR Title Format

```
feat(scope): description [P{phase}-{seq}]

feat(auth): user authentication via Cognito [P01-01]
feat(chat): SSE streaming responses [P02-01]
fix(memory): correct agent_id format in Mem0 calls [P02-02]
```

### PR Description Template

```markdown
## Summary

Implements [feature title]. Closes #[issue].

## Changes

- `backend/`: [description of backend changes]
- `ios/`: [description of iOS changes]
- `android/`: [description of Android changes]

## Acceptance Criteria

- [ ] [criterion 1]
- [ ] [criterion 2]
- [ ] [criterion 3]

## Testing

- Unit tests: [describe what is tested]
- Coverage: backend X%, iOS X%, Android X%

## Notes

[Any implementation notes, deviations from spec, known issues]
```

---

## 12. GitHub Issue Lifecycle

### Issue States

```
open → in-progress → in-review → merged → closed
```

### Labels Used

| Label            | Meaning                                     |
|------------------|---------------------------------------------|
| `phase/p1`       | Phase 1 feature                             |
| `phase/p2`       | Phase 2 feature                             |
| `layer/backend`  | Backend work                                |
| `layer/ios`      | iOS work                                    |
| `layer/android`  | Android work                                |
| `layer/fullstack`| All platforms                               |
| `status/in-progress` | Pipeline is running                    |
| `status/blocked` | Pipeline stopped, needs human               |
| `priority/p0`    | Critical bug                                |
| `priority/p1`    | High priority                               |
| `priority/p2`    | Normal priority                             |
| `bug`            | Defect filed by qa-agent                    |
| `enhancement`    | Feature request                             |

### Issue Creation (pm-agent)

```markdown
## Feature: [Title]

**Feature ID**: P01-01
**Phase**: 1
**Layer**: fullstack

### Description

[What this feature does and why it matters]

### Acceptance Criteria

- [ ] [specific, testable criterion]
- [ ] [specific, testable criterion]

### Technical Notes

[Any pointers to relevant docs, constraints]

### Definition of Done

- [ ] Backend tests pass (coverage >= 80%)
- [ ] iOS tests pass (coverage >= 80%)
- [ ] Android tests pass (coverage >= 80%)
- [ ] Code review approved
- [ ] PRs merged to main
```

### Issue Closure (merge-agent)

merge-agent closes the issue with a comment:

```
Implemented in #12 (backend), #13 (iOS), #14 (Android).
All tests passing. Coverage: backend 84%, iOS 81%, Android 82%.
```
