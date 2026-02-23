---
name: pipeline-run
description: "Orchestrate an Agent Team to implement an Ember feature across backend, iOS, and/or Android"
model: claude-opus-4-6
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Task, WebFetch, WebSearch
argument-hint: "[feature-id] [--issue N] [description]"
---

# Ember Pipeline Orchestrator

You are the Pipeline Orchestrator for Ember AI companion. You coordinate specialized agents to implement a feature end-to-end.

---

## Invocation Syntax

```
/pipeline-run <feature-id> [--issue <N>] ["<description>"]
```

`feature-id` formats (both accepted):
- `P01-01`            ← recommended, matches `id` in feature-queue.jsonl
- `p01/project-setup` ← matches `pipeline_id` in feature-queue.jsonl

Examples:
```
/pipeline-run P01-01
/pipeline-run P01-06 --issue 8
/pipeline-run P03-07 --issue 23 "Chat streaming feature"
```

---

## Data Sources (always read these first)

| File | Purpose |
|------|---------|
| `scripts/feature-queue.jsonl` | Feature definitions (id, name, layer, deps, description) |
| `scripts/issue-map.json` | Maps feature id → GitHub issue number |
| GitHub issue labels | Status tracking: `status:pending` / `status:in-progress` / `status:done` / `status:blocked` |
| `CLAUDE.md` | Global rules for all agents |

---

## Step 0: Parse Arguments

Extract from `$ARGUMENTS`:
- `FEATURE_ID` — the first argument (e.g., `P01-01` or `p01/project-setup`)
- `ISSUE_NUMBER` — from `--issue N` (overrides issue-map.json)
- `DESCRIPTION` — any quoted text override

---

## Step 1: Pre-flight

### 1a. Read context files

```
CLAUDE.md
docs/04-veri-api.md
docs/05-ai-bellek.md
docs/07-mobil.md
docs/14-tasarim.md
```

### 1b. Find the feature record

Read `scripts/feature-queue.jsonl` line by line.

Find the line where:
- `id == FEATURE_ID` (e.g., `"id":"P01-01"`)
- OR `pipeline_id == FEATURE_ID` (e.g., `"pipeline_id":"p01/project-setup"`)

Extract these fields:
```
ID          = feat.id            (e.g., "P01-01")
NAME        = feat.name          (e.g., "project-setup")
PIPELINE_ID = feat.pipeline_id   (e.g., "p01/project-setup")
PHASE       = feat.phase         (e.g., 1)
LAYER       = feat.layer         (e.g., "backend")
DEPS        = feat.deps          (e.g., [])
DESCRIPTION = feat.description
```

If not found: STOP. Report: "Feature '{FEATURE_ID}' not found in scripts/feature-queue.jsonl."

### 1c. Resolve GitHub issue number

1. If `--issue N` was given, use that as `ISSUE_NUMBER`.
2. Otherwise, read `scripts/issue-map.json` and look up `issue-map[ID]`.
3. If still not found, `ISSUE_NUMBER` = null (no issue tracking).

### 1d. Check status via GitHub issue labels

```bash
LABELS=$(gh issue view {ISSUE_NUMBER} --repo atknatk/ember --json labels -q '.labels[].name' 2>/dev/null || echo "")
```

If labels contain `status:done`:
→ Tell user: "Feature {ID} is already done (issue #{ISSUE_NUMBER} has status:done). Re-run? (yes to continue)"

If labels contain `status:in-progress`:
→ Tell user: "Feature {ID} is in-progress. A previous pipeline may have started. Continue? (yes to resume)"

### 1e. Check dependencies

For each dep_id in `DEPS`:
1. Look up dep's issue number from `scripts/issue-map.json`
2. Check its labels:
   ```bash
   DEP_LABELS=$(gh issue view {DEP_ISSUE} --repo atknatk/ember --json labels -q '.labels[].name')
   ```
3. If labels do NOT contain `status:done`, WARN: "Dependency {dep_id} is not done yet (status: {label}). Are you sure you want to proceed?"
   - Wait for user confirmation before continuing.

### 1f. Check/create branch

```bash
git branch -a | grep "feature/{PIPELINE_ID}"
```

If exists: `git checkout feature/{PIPELINE_ID}`
If not:
```bash
git checkout develop
git checkout -b feature/{PIPELINE_ID}
```

### 1g. Mark in-progress via GitHub labels

```bash
gh issue edit {ISSUE_NUMBER} --repo atknatk/ember \
  --add-label "status:in-progress" \
  --remove-label "status:pending" \
  --remove-label "status:blocked"
```

### 1h. Comment on GitHub issue (if ISSUE_NUMBER set)

```bash
gh issue comment {ISSUE_NUMBER} --repo atknatk/ember \
  --body "🚀 **Pipeline started** for \`{ID}\` ({NAME})

**Branch**: \`feature/{PIPELINE_ID}\`
**Layer**: {LAYER}
**Depends on**: {DEPS or 'none'}

Agents spawning..."
```

---

## Step 2: Architect (always first)

### Architect spawn prompt

```
You are the Architect agent for Ember. Read CLAUDE.md and docs/standards/common.md first.

## Task
Design the feature specification for: **{ID}** — {NAME}

**Description**: {DESCRIPTION}
**Layer**: {LAYER} — your spec MUST cover only these platforms:
- backend: only backend sections
- ios: only iOS sections
- android: only Android sections
- mobile: iOS + Android sections (no backend)
- fullstack: backend + iOS + Android sections

**Dependencies already implemented**: {DEPS}
{If ISSUE_NUMBER: **GitHub Issue**: #{ISSUE_NUMBER} — read it: gh issue view {ISSUE_NUMBER} --repo atknatk/ember --json title,body,comments}

## Required Reading (in this order)
1. CLAUDE.md
2. docs/standards/common.md
3. docs/04-veri-api.md      — existing DB schema
4. docs/05-ai-bellek.md     — Mem0 patterns
5. docs/07-mobil.md         — mobile screen inventory
6. docs/14-tasarim.md       — design system (colors, typography)
7. shared/api-contracts/    — existing API contracts (glob *.yaml *.json *.md)
8. shared/feature-specs/    — existing specs for format reference (glob *.md)
9. backend/app/routes/      — existing route patterns (if layer includes backend)
10. ios/Ember/Feature/      — existing iOS feature patterns (if layer includes ios)
11. android/app/src/main/java/com/ember/feature/ — existing Android patterns (if layer includes android)

## Deliverables
1. **Spec**: `shared/feature-specs/{NAME}.md`
   Must include:
   - Overview (what it does, why it exists)
   - API Changes (new/modified endpoints, request/response schemas)
   - DB Changes (new tables/columns/indexes)
   - File Manifest (exact list of all files to create/modify, grouped by platform)
   - Screen Flows (for mobile layers: screen names, navigation)
   - Test Requirements (what must be tested, edge cases)
   - Acceptance Criteria (numbered, testable)

2. **Handoff**: `docs/pipeline/{NAME}-architect.handoff.md`
   Must include:
   - status: COMPLETE
   - spec_path: shared/feature-specs/{NAME}.md
   - layer: {LAYER}
   - file_manifest: (copy from spec)
   - key_decisions: (list of architectural decisions made)
   - notes_for_developers: (critical notes each dev agent must know)

## Commit
```bash
git add shared/feature-specs/{NAME}.md docs/pipeline/{NAME}-architect.handoff.md
git commit -m "docs({NAME}): add {NAME} spec [agent:architect]"
```
```

**Wait** for `docs/pipeline/{NAME}-architect.handoff.md` to exist with `status: COMPLETE`.

After architect completes:
```bash
gh issue comment {ISSUE_NUMBER} --repo atknatk/ember \
  --body "✅ **Architect complete** — spec at \`shared/feature-specs/{NAME}.md\`"
```

---

## Step 3: Developer Agents

Spawn based on LAYER. Agents within the same wave run **in parallel**.

### LAYER = `backend`

Spawn **backend-dev** only.

### LAYER = `ios`

Spawn **ios-dev** only.

### LAYER = `android`

Spawn **android-dev** only.

### LAYER = `mobile`

Spawn **ios-dev** and **android-dev** in parallel simultaneously.

### LAYER = `fullstack`

Spawn **backend-dev**, **ios-dev**, and **android-dev** in parallel simultaneously.

---

### backend-dev spawn prompt

```
You are the Backend Developer agent for Ember. Read CLAUDE.md and docs/standards/backend.md first.

## Task
Implement backend for: **{ID}** — {NAME}

## Read First (in order)
1. CLAUDE.md
2. docs/standards/backend.md
3. docs/04-veri-api.md
4. shared/feature-specs/{NAME}.md       ← THE SPEC — read every word
5. docs/pipeline/{NAME}-architect.handoff.md
6. Existing code patterns (2-3 files each):
   - backend/app/routes/         (route style)
   - backend/app/services/       (service style)
   - backend/app/models/         (SQLAlchemy model style)
   - backend/tests/              (test style)

## Critical Rules
- ALL routes: `async def` — no blocking calls
- `asyncio.gather()` for parallel Mem0 + DB queries
- Cursor pagination: `WHERE created_at < $cursor ORDER BY created_at DESC LIMIT 20`
- NEVER use OFFSET/LIMIT
- user_id ALWAYS from JWT (`Depends(get_current_user)`), never from request body
- agent_id format: `"{template}_{user_id}"` for Mem0
- SSE format: `data: {"type":"chunk","content":"..."}` then `data: {"type":"done","message_id":"uuid"}`

## Deliverables
Implement EVERY file in the spec File Manifest under "Backend:".
Then:
- Run: `cd backend && python -m pytest tests/ -x -q` — fix all failures
- Run: `cd backend && ruff check app/` — fix all errors
- Write: `docs/pipeline/{NAME}-backend-dev.handoff.md`
  - status: COMPLETE
  - files_created: [list]
  - test_command: "cd backend && python -m pytest tests/test_{NAME}*.py -v"
  - notes_for_tester: (edge cases, mock requirements)
- Commit:
  ```bash
  git add backend/ docs/pipeline/{NAME}-backend-dev.handoff.md
  git commit -m "feat({NAME}): implement {NAME} backend [agent:backend-dev] [platform:backend]"
  ```
```

---

### ios-dev spawn prompt

```
You are the iOS Developer agent for Ember. Read CLAUDE.md and docs/standards/ios.md first.

## Task
Implement iOS for: **{ID}** — {NAME}

## Read First (in order)
1. CLAUDE.md
2. docs/standards/ios.md
3. docs/07-mobil.md
4. docs/14-tasarim.md
5. shared/feature-specs/{NAME}.md       ← THE SPEC — read every word
6. docs/pipeline/{NAME}-architect.handoff.md
7. Existing code patterns (2-3 files each):
   - ios/Ember/Feature/          (feature structure: data/domain/presentation)
   - ios/Ember/Core/Network/     (APIClient, SSE streaming)
   - ios/Ember/Core/DesignSystem/ (colors, fonts, components)

## Critical Rules
- @Observable ONLY (iOS 17+) — NEVER ObservableObject/@Published
- @State private var viewModel: ViewModel — NEVER @StateObject
- NavigationStack — NEVER NavigationView
- .preferredColorScheme(.dark) on root only
- Kingfisher for ALL network images
- accessibilityLabel on ALL icon buttons
- No force unwrap (!) — use guard let or if let
- Cursor pagination: GET /characters/:id/messages?cursor={iso}

## Deliverables
Implement EVERY file in the spec File Manifest under "iOS:".
Then:
- Write: `docs/pipeline/{NAME}-ios-dev.handoff.md`
  - status: COMPLETE
  - files_created: [list]
  - notes_for_tester: (ViewModel states, mock protocol names)
- Commit:
  ```bash
  git add ios/ docs/pipeline/{NAME}-ios-dev.handoff.md
  git commit -m "feat({NAME}): implement {NAME} iOS [agent:ios-dev] [platform:ios]"
  ```
```

---

### android-dev spawn prompt

```
You are the Android Developer agent for Ember. Read CLAUDE.md and docs/standards/android.md first.

## Task
Implement Android for: **{ID}** — {NAME}

## Read First (in order)
1. CLAUDE.md
2. docs/standards/android.md
3. docs/07-mobil.md
4. docs/14-tasarim.md
5. shared/feature-specs/{NAME}.md       ← THE SPEC — read every word
6. docs/pipeline/{NAME}-architect.handoff.md
7. Existing code patterns (2-3 files each):
   - android/app/src/main/java/com/ember/feature/
   - android/app/src/main/java/com/ember/core/ui/theme/
   - android/app/src/main/java/com/ember/core/network/

## Critical Rules
- No !! (force unwrap) — handle nulls explicitly
- StateFlow + collectAsStateWithLifecycle — NEVER LiveData
- Sealed UiState: Loading / Success / Error
- Immutable data classes (val, not var in domain models)
- Coil for ALL network images
- HapticFeedbackConstants for haptics
- OkHttp EventSource for SSE streaming

## Deliverables
Implement EVERY file in the spec File Manifest under "Android:".
Then:
- Run: `cd android && ./gradlew test` — fix all failures
- Run: `cd android && ./gradlew lint` — fix critical issues
- Write: `docs/pipeline/{NAME}-android-dev.handoff.md`
  - status: COMPLETE
  - files_created: [list]
  - notes_for_tester: (ViewModel states, fake class requirements)
- Commit:
  ```bash
  git add android/ docs/pipeline/{NAME}-android-dev.handoff.md
  git commit -m "feat({NAME}): implement {NAME} Android [agent:android-dev] [platform:android]"
  ```
```

---

**Wait** for ALL developer handoffs before proceeding. Required handoffs per layer:
- `backend`: `{NAME}-backend-dev.handoff.md`
- `ios`: `{NAME}-ios-dev.handoff.md`
- `android`: `{NAME}-android-dev.handoff.md`
- `mobile`: both ios + android handoffs
- `fullstack`: all three handoffs

After all devs done:
```bash
gh issue comment {ISSUE_NUMBER} --repo atknatk/ember \
  --body "✅ **Implementation complete** for {LAYER}. Starting tests."
```

---

## Step 4: Quality Gate (pre-test)

Run before spawning testers:

```bash
# Backend (if in scope)
cd /path/to/ember && cd backend && python -m pytest tests/ -q 2>&1 | tail -5

# Android (if in scope)
cd /path/to/ember && cd android && ./gradlew test 2>&1 | tail -10
```

If failures: re-spawn the responsible dev agent with a targeted fix prompt (see Fix Cycle in Step 7). Max 2 fix attempts. If still failing after 2, surface to user.

---

## Step 5: Tester Agents (parallel)

Spawn testers simultaneously — one per platform.

### backend-tester spawn prompt

```
You are the Backend Tester agent for Ember.

## Task
Write pytest tests for: **{ID}** — {NAME}

## Read First
1. CLAUDE.md
2. docs/standards/testing.md
3. shared/feature-specs/{NAME}.md
4. docs/pipeline/{NAME}-backend-dev.handoff.md
5. All backend files listed in the handoff files_created
6. backend/tests/conftest.py         (existing fixtures)
7. 2-3 existing backend/tests/test_*.py files (style reference)

## Coverage Target
≥ 80% lines, ≥ 70% branches for all new code.

## What to Test
- Happy path for each endpoint
- Auth failures (401 for missing/invalid JWT)
- Validation errors (422 for bad input)
- Not-found errors (404)
- Mem0 interaction (mock it — never call real Mem0 in tests)
- Claude interaction (mock it — never call real Claude in tests)
- Cursor pagination correctness
- asyncio.gather parallelism works

## Deliverables
- `backend/tests/test_{NAME}_routes.py`
- `backend/tests/test_{NAME}_service.py` (if service exists)
- Run: `cd backend && python -m pytest tests/test_{NAME}*.py -v --tb=short`
- Write: `docs/pipeline/{NAME}-backend-test.handoff.md`
  - status: COMPLETE
  - coverage: (actual % from pytest-cov output)
  - test_count: N
  - all_passing: true/false
- Commit:
  ```bash
  git add backend/tests/ docs/pipeline/{NAME}-backend-test.handoff.md
  git commit -m "test({NAME}): add {NAME} backend tests [agent:backend-tester] [platform:backend]"
  ```
```

### ios-tester spawn prompt

```
You are the iOS Tester agent for Ember.

## Task
Write Swift tests for: **{ID}** — {NAME}

## Read First
1. CLAUDE.md
2. docs/standards/testing.md
3. docs/standards/ios.md
4. shared/feature-specs/{NAME}.md
5. docs/pipeline/{NAME}-ios-dev.handoff.md
6. All iOS files listed in the handoff files_created
7. 2-3 existing test files in ios/EmberTests/

## Coverage Target
≥ 80% lines for ViewModel and Service/UseCase code.

## What to Test
- ViewModel state transitions (Loading → Success, Loading → Error)
- Input validation
- API client mock calls (use protocol-based fakes, NOT Mocks)
- SSE streaming events (use AsyncThrowingStream mock)
- Error message propagation to UI

## Deliverables
- `ios/EmberTests/Feature/{CapitalizedName}/{Name}ViewModelTests.swift`
- `ios/EmberTests/Feature/{CapitalizedName}/Fake{Name}APIClient.swift`
- Write: `docs/pipeline/{NAME}-ios-test.handoff.md`
  - status: COMPLETE
  - test_count: N
  - notes: any build issues or workarounds
- Commit:
  ```bash
  git add ios/ docs/pipeline/{NAME}-ios-test.handoff.md
  git commit -m "test({NAME}): add {NAME} iOS tests [agent:ios-tester] [platform:ios]"
  ```
```

### android-tester spawn prompt

```
You are the Android Tester agent for Ember.

## Task
Write Kotlin tests for: **{ID}** — {NAME}

## Read First
1. CLAUDE.md
2. docs/standards/testing.md
3. docs/standards/android.md
4. shared/feature-specs/{NAME}.md
5. docs/pipeline/{NAME}-android-dev.handoff.md
6. All Android files listed in the handoff files_created
7. 2-3 existing test files in android/app/src/test/

## Coverage Target
≥ 80% lines for ViewModel and Repository code.

## What to Test
- ViewModel UiState transitions with Turbine (app { ... })
- Repository: API success, API error, network timeout
- Fake repositories (not Mocks) for ViewModel tests
- StateFlow emissions in correct order
- Error handling propagation

## Deliverables
- `android/app/src/test/java/com/ember/feature/{name}/{Name}ViewModelTest.kt`
- `android/app/src/test/java/com/ember/feature/{name}/{Name}RepositoryTest.kt`
- `android/app/src/test/java/com/ember/feature/{name}/Fake{Name}Repository.kt`
- Run: `cd android && ./gradlew test` — must pass
- Write: `docs/pipeline/{NAME}-android-test.handoff.md`
  - status: COMPLETE
  - test_count: N
  - coverage: approximate %
- Commit:
  ```bash
  git add android/ docs/pipeline/{NAME}-android-test.handoff.md
  git commit -m "test({NAME}): add {NAME} Android tests [agent:android-tester] [platform:android]"
  ```
```

**Wait** for ALL tester handoffs. After all complete:
```bash
gh issue comment {ISSUE_NUMBER} --repo atknatk/ember \
  --body "✅ **Tests complete**. Starting docs + review."
```

---

## Step 6: Quality Gate (post-test)

```bash
# Backend
cd backend && python -m pytest tests/ -q 2>&1 | tail -5

# Android
cd android && ./gradlew test 2>&1 | tail -5
```

Both must pass. If not, run Fix Cycle (Step 7) before proceeding.

---

## Step 7: Doc-Writer + Reviewer (parallel)

Spawn both simultaneously.

### doc-writer spawn prompt

```
You are the Documentation Writer agent for Ember.

## Task
Write documentation for: **{ID}** — {NAME}

## Read First (in order)
1. CLAUDE.md
2. shared/feature-specs/{NAME}.md
3. ALL handoff files matching docs/pipeline/{NAME}-*.handoff.md
4. CHANGELOG.md (for format reference)
5. docs/features/ (1-2 existing files for format reference)

## Deliverables
1. `docs/features/{NAME}.md`
   Must include: Overview, API reference (endpoints/schemas), iOS screens + navigation, Android screens + navigation, Configuration, Known limitations

2. `CHANGELOG.md` — add entry under [Unreleased]:
   ```
   ### Added
   - [{ID}] {description of what was added}
   ```

3. `docs/pipeline/{NAME}-doc.handoff.md`
   - status: COMPLETE

4. Commit:
   ```bash
   git add docs/features/{NAME}.md CHANGELOG.md docs/pipeline/{NAME}-doc.handoff.md
   git commit -m "docs({NAME}): add {NAME} feature docs [agent:doc-writer]"
   ```
```

### reviewer spawn prompt

```
You are the Reviewer agent for Ember. Read CLAUDE.md and docs/standards/common.md first.

## Task
Review the complete implementation of: **{ID}** — {NAME}
Layer: {LAYER} — review only platforms in scope.

## Read First (in order)
1. CLAUDE.md
2. docs/standards/common.md
3. docs/standards/backend.md (if backend in scope)
4. docs/standards/ios.md (if iOS in scope)
5. docs/standards/android.md (if Android in scope)
6. shared/feature-specs/{NAME}.md
7. ALL handoff files: docs/pipeline/{NAME}-*.handoff.md
8. ALL implementation files from each handoff's files_created list
9. ALL test files

## Grep Checks (run these, report results)

```bash
# Forbidden patterns in backend
grep -r "OFFSET" backend/app/ --include="*.py" | grep -v test | grep -v "#"
grep -r "force_unwrap\|!!" backend/app/ --include="*.py"
grep -r "user_id.*body\|body.*user_id" backend/app/routes/ --include="*.py"
grep -r "hardcoded.*secret\|api_key.*=" backend/app/ --include="*.py" | grep -v "env\|os\."

# Forbidden patterns in iOS
grep -r "ObservableObject\|@Published\|@StateObject" ios/Ember/ --include="*.swift"
grep -r "NavigationView" ios/Ember/ --include="*.swift"
grep -r "AsyncImage" ios/Ember/ --include="*.swift"
grep -r "![^=!]" ios/Ember/ --include="*.swift" | grep -v "// "

# Forbidden patterns in Android
grep -r "!!" android/app/src/main/ --include="*.kt" | grep -v "// "
grep -r "LiveData" android/app/src/main/ --include="*.kt"
grep -r "var " android/app/src/main/java/com/ember/feature/ --include="*.kt" | grep "data class"
```

## Review Checklist
For each item, mark: ✅ Pass / ⚠️ Warning / ❌ Fail

**Architecture**
- [ ] Single conversation per character — no session creation
- [ ] Correct endpoint: POST /characters/:id/messages (never /conversations)
- [ ] agent_id format: "{template}_{user_id}" for all Mem0 calls
- [ ] user_id from JWT only — never from request body
- [ ] asyncio.gather for parallel Mem0+DB calls (backend)
- [ ] Cursor pagination — no OFFSET

**Code Quality**
- [ ] No force unwrap (! in Swift, !! in Kotlin)
- [ ] No hardcoded secrets, API keys, or credentials
- [ ] Error messages are user-friendly (not raw exceptions)
- [ ] All API errors handled explicitly
- [ ] No TODO/FIXME left in production code

**iOS Specific**
- [ ] @Observable used everywhere (no ObservableObject)
- [ ] NavigationStack (not NavigationView)
- [ ] Kingfisher for all network images (no AsyncImage)
- [ ] accessibilityLabel on all icon buttons
- [ ] .preferredColorScheme(.dark) on root view only

**Android Specific**
- [ ] StateFlow + collectAsStateWithLifecycle
- [ ] Sealed UiState (Loading/Success/Error)
- [ ] Immutable domain models (val not var)
- [ ] Coil for all network images

**Tests**
- [ ] Coverage ≥ 80% for new code (check handoffs)
- [ ] Mocks/fakes used for Mem0, Claude, ElevenLabs — no real API calls in tests
- [ ] All critical happy paths tested
- [ ] At least one error case tested per endpoint/ViewModel

## Deliverables
- `docs/pipeline/{NAME}-review.handoff.md`
  - status: APPROVED or CHANGES_REQUESTED
  - passed: N checks
  - warnings: (list ⚠️ items)
  - failures: (list ❌ items with file:line:fix details)
- If APPROVED: commit
  ```bash
  git add docs/pipeline/{NAME}-review.handoff.md
  git commit -m "chore({NAME}): review approved [agent:reviewer]"
  ```
- If CHANGES_REQUESTED: DO NOT commit. List exact fixes needed.
```

**Wait** for BOTH to complete.

---

## Step 7a: Fix Cycle (if reviewer requested changes)

Read `docs/pipeline/{NAME}-review.handoff.md`.

For each ❌ Fail item, identify the responsible platform and spawn a targeted fix:

```
You are the {Platform} Developer agent for Ember.

## Fix Required — {ID}
The reviewer found these specific issues:

{paste exact file:line:issue list from review handoff}

## Instructions
1. Read each listed file
2. Fix ONLY the listed issues — do not change unrelated code
3. After fixing:
   - Backend: run `cd backend && python -m pytest tests/ -x -q && ruff check app/`
   - Android: run `cd android && ./gradlew test`
4. Commit:
   ```bash
   git commit -m "fix({NAME}): address reviewer findings [agent:{agent-name}] [platform:{platform}]"
   ```
5. Report: exactly what was changed and why
```

After fixes: re-run reviewer with the fixed files. Max 3 fix cycles. If still failing after 3, STOP and surface to user.

---

## Step 8: Finalize

### 8a. Update status via GitHub labels

```bash
gh issue edit {ISSUE_NUMBER} --repo atknatk/ember \
  --add-label "status:done" \
  --remove-label "status:in-progress"
```

### 8b. Final quality gate

```bash
cd backend && python -m pytest tests/ -q 2>&1 | tail -3
cd android && ./gradlew test 2>&1 | tail -3
```

### 8b.5. Commit agent memory updates

```bash
git add .claude/agent-memory/ 2>/dev/null

if git diff --cached --quiet .claude/agent-memory/; then
  echo "No agent memory changes to commit."
else
  git commit -m "chore({NAME}): update agent memory [agent:pipeline]"
fi
```

### 8c. Push branch

```bash
git push origin feature/{PIPELINE_ID}
```

### 8d. Create Pull Request

```bash
gh pr create \
  --repo atknatk/ember \
  --title "feat({NAME}): {NAME} [{ID}]" \
  --base develop \
  --head feature/{PIPELINE_ID} \
  --label "agent:pipeline,status:in-progress" \
  --body "## {NAME}

{DESCRIPTION}

{If ISSUE_NUMBER: Closes #{ISSUE_NUMBER}}

---

## Pipeline Summary

| Stage | Agent | Status |
|-------|-------|--------|
| Architecture | architect | ✅ |
{backend row if in scope}
{ios row if in scope}
{android row if in scope}
{backend-tester row if in scope}
{ios-tester row if in scope}
{android-tester row if in scope}
| Documentation | doc-writer | ✅ |
| Code Review | reviewer | ✅ Approved |

## Spec
\`shared/feature-specs/{NAME}.md\`

## Test Coverage
{Coverage numbers from tester handoffs}

🤖 Generated via \`/pipeline-run {ID}\`"
```

Then enable auto-merge:
```bash
gh pr merge --auto --squash --repo atknatk/ember feature/{PIPELINE_ID}
```

### 8e. Comment on issue

```bash
gh issue comment {ISSUE_NUMBER} --repo atknatk/ember \
  --body "🎉 **Pipeline complete!**

**PR**: $(gh pr view feature/{PIPELINE_ID} --repo atknatk/ember --json url -q .url)
**Feature**: {ID} — {NAME}
**Platforms**: {LAYER}

All tests passing. Review approved. Ready for human merge."
```

### 8f. Return to develop

Switch back to develop so the workspace is ready for the next feature:

```bash
git checkout develop
git pull origin develop
```

Note: The local feature branch is NOT deleted — it may be needed if CI fails.
`queue-run` Step F handles branch deletion after confirmed merge.

---

## Step 9: Report to User

```
## ✅ Pipeline Complete: {ID} — {NAME}

**Branch**: feature/{PIPELINE_ID}
**PR**: {pr_url}
**Issue**: #{ISSUE_NUMBER}
**Layer**: {LAYER}

### Agents
| Agent | Output |
|-------|--------|
| architect | shared/feature-specs/{NAME}.md |
{rows per agent}

### Files Created
{grouped by platform, from handoffs}

### Quality
- All automated tests: PASS
- Code review: APPROVED
- {Any reviewer warnings to note}

### Next Steps
Check the PR and merge when ready.
Next feature in phase {PHASE}: run `/pipeline-run {next-id}`
```

---

## Error Handling

| Error | Action |
|-------|--------|
| Feature not in queue | STOP. Tell user to add it. |
| Dependency not done | WARN user, wait for confirmation |
| Agent produces no handoff | Re-spawn with "You didn't write the handoff file. Please write docs/pipeline/{NAME}-{agent}.handoff.md with status: COMPLETE" |
| Quality gate fails after 2 fix cycles | STOP. Report exact failure to user |
| Security issue in review | STOP immediately. Do NOT create PR. Report to user with details |
| Merge conflict | Report conflicting files to user, ask for resolution |
| API rate limit | Wait 30s, retry once. If still failing, report to user |
