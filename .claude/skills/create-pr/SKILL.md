---
name: create-pr
description: "Push current feature branch and create a PR to develop with pipeline labels"
model: claude-sonnet-4-6
allowed-tools: Read, Bash, Grep
argument-hint: "[feature-id] [--draft]"
---

# Ember Create PR

Push the current feature branch to GitHub and open a Pull Request targeting `develop`.

Called automatically by `pipeline-run` at Step 8, but can also be run standalone if you
implemented a feature manually and want to create the PR.

---

## Invocation

```
/create-pr              ← infer everything from current branch + feature-status
/create-pr P01-03       ← specify feature ID explicitly
/create-pr P01-03 --draft  ← open as draft PR
```

---

## Step 1: Resolve Feature Info

### 1a. Get current branch

```bash
git branch --show-current
```

Example result: `feature/p01/project-setup`

### 1b. Parse pipeline_id from branch

Strip `feature/` prefix → `pipeline_id = p01/project-setup`

### 1c. Find feature in queue

If `$ARGUMENTS` contains a feature ID (e.g. `P01-03`), use that.
Otherwise, read `scripts/feature-queue.jsonl` and find the line where
`pipeline_id == parsed_pipeline_id`.

Extract:
```
ID          = feat.id            (e.g. "P01-01")
NAME        = feat.name          (e.g. "project-setup")
PIPELINE_ID = feat.pipeline_id   (e.g. "p01/project-setup")
PHASE       = feat.phase
LAYER       = feat.layer
DESCRIPTION = feat.description
DEPS        = feat.deps
```

If not found and no explicit ID given: STOP. Ask user to provide feature ID.

### 1d. Resolve issue number

Read `scripts/issue-map.json` → `ISSUE_NUMBER = issue-map[ID]`
(null if not found — PR will be created without issue link)

---

## Step 2: Pre-flight Checks

```bash
# Verify we're not on develop or main
BRANCH=$(git branch --show-current)
if [[ "$BRANCH" == "develop" || "$BRANCH" == "main" ]]; then
  echo "ERROR: Cannot create PR from $BRANCH. Checkout a feature branch first."
  exit 1
fi

# Verify branch has commits ahead of develop
AHEAD=$(git rev-list develop..HEAD --count)
if [[ "$AHEAD" == "0" ]]; then
  echo "ERROR: No commits ahead of develop. Nothing to PR."
  exit 1
fi

echo "Branch: $BRANCH ($AHEAD commits ahead of develop)"
```

---

## Step 3: Check Handoff Files

Look for handoff files to build the PR description:

```bash
ls docs/pipeline/{NAME}-*.handoff.md 2>/dev/null
```

Read each handoff file to extract:
- Architect: `key_decisions`, `notes_for_developers`
- Dev handoffs: `files_created` per platform
- Test handoffs: `coverage`, `test_count`, `all_passing`
- Review handoff: `status` (APPROVED / CHANGES_REQUESTED), `warnings`

If review handoff exists with `status: CHANGES_REQUESTED` → WARN user and ask to confirm.
If no handoff files found → build a minimal PR description from git log.

---

## Step 4: Run Verify (optional)

If there are staged/uncommitted changes:
```bash
git status --short
```
If any unstaged changes exist, warn: "There are uncommitted changes. Commit them first."

---

## Step 5: Push Branch

```bash
git push origin feature/{PIPELINE_ID}
```

If push fails due to diverged history:
```
ERROR: Push failed. The remote branch may have diverged.
Run: git pull --rebase origin feature/{PIPELINE_ID}
Then retry: /create-pr
```

---

## Step 6: Build PR Body

Collect info from handoff files and build the PR body:

```
## {NAME}

{DESCRIPTION}

{If ISSUE_NUMBER: Closes #{ISSUE_NUMBER}}

---

## Pipeline Summary

| Stage | Agent | Status |
|-------|-------|--------|
| Architecture | architect | {✅ if handoff exists, else ⏭️ skipped} |
{backend row: ✅ / ⏭️}
{ios row: ✅ / ⏭️}
{android row: ✅ / ⏭️}
{backend-tester row: ✅ / ⏭️}
{ios-tester row: ✅ / ⏭️}
{android-tester row: ✅ / ⏭️}
| Documentation | doc-writer | {✅ / ⏭️} |
| Code Review | reviewer | {✅ APPROVED / ⚠️ manual} |

## Files Changed

{Group git diff --stat output by platform}

## Test Coverage

{Coverage numbers from tester handoffs, or "No automated test data"}

## Spec

{If exists: shared/feature-specs/{NAME}.md}

🤖 Generated via `/pipeline-run {ID}` or `/create-pr {ID}`
```

---

## Step 7: Create PR

```bash
IS_DRAFT=""
# If --draft flag was passed:
IS_DRAFT="--draft"

gh pr create \
  --repo atknatk/ember \
  --title "feat({NAME}): {NAME} [{ID}]" \
  --base develop \
  --head feature/{PIPELINE_ID} \
  --label "agent:pipeline" \
  $IS_DRAFT \
  --body "{PR_BODY}"
```

Capture the PR URL from output.

---

## Step 8: Enable Auto-merge (if not draft)

If `--draft` was NOT given:

```bash
gh pr merge --auto --squash --repo atknatk/ember feature/{PIPELINE_ID}
```

This enables auto-merge: when all CI checks pass, the PR is automatically squash-merged
into `develop`.

---

## Step 9: Update Issue (if ISSUE_NUMBER exists)

```bash
gh issue comment {ISSUE_NUMBER} --repo atknatk/ember \
  --body "🎉 **PR created**: {PR_URL}

**Branch**: \`feature/{PIPELINE_ID}\`
**Layer**: {LAYER}
**Auto-merge**: enabled (squash → develop)

All CI checks must pass before merge."
```

---

## Step 10: Report

```
## ✅ PR Created: {ID} — {NAME}

**PR**: {PR_URL}
**Branch**: feature/{PIPELINE_ID} → develop
**Issue**: #{ISSUE_NUMBER}
**Auto-merge**: {enabled / disabled (draft)}
**Label**: agent:pipeline

CI will run automatically. Once all checks pass, the PR will be squash-merged into develop.

To watch CI status:
  gh pr checks {PR_URL} --watch

To merge manually (if auto-merge not set):
  gh pr merge --squash {PR_URL}
```

---

## CI Checks That Must Pass

Auto-merge triggers only when all required checks pass:

| Check | Workflow |
|-------|---------|
| Backend tests | `.github/workflows/backend-ci.yml` |
| iOS lint | `.github/workflows/ios-ci.yml` |
| Android tests | `.github/workflows/android-ci.yml` |

Only the checks relevant to the changed files will run (path filters in each workflow).
