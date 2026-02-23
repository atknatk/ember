---
name: queue-run
description: "Process features sequentially in dependency order — by phase or all at once"
model: claude-opus-4-6
allowed-tools: Read, Bash, Grep, Glob, Write, Edit, Task, WebFetch
argument-hint: "[all|1|2|3..12|--from <feature-id>] [--dry-run]"
---

# Ember Queue Runner

You are the **Queue Runner**. You process Ember features one by one in dependency order,
calling `/pipeline-run` for each feature. Each feature is fully implemented, tested,
reviewed, and merged to `develop` before the next one starts.

---

## Invocation

```
/queue-run            ← run all pending features in dependency order
/queue-run 1          ← run all features in Phase 1 only
/queue-run 2          ← run all features in Phase 2 only
/queue-run 1 2 3      ← run phases 1, 2, and 3 in order
/queue-run --from P01-03   ← resume from a specific feature (skip earlier ones)
/queue-run 1 --dry-run     ← show what would run without doing anything
```

---

## Step 0: Parse Arguments

From `$ARGUMENTS`:
- If number(s) (e.g. `1`, `1 2 3`) → `PHASES = [1, 2, 3]`
- If `all` or empty → `PHASES = [1..12]`
- `--from P01-03` → skip all features before P01-03 in the queue
- `--dry-run` → print plan only, do nothing

---

## Step 1: Pre-flight

```bash
# 1. Ensure on develop and up-to-date
git checkout develop && git pull origin develop

# 2. Verify gh CLI authenticated
gh auth status

# 3. Verify we're in the repo root
ls CLAUDE.md scripts/feature-queue.jsonl scripts/feature-status.json
```

If any fail → STOP and report.

---

## Step 2: Build the Ordered Feature List

Read `scripts/feature-queue.jsonl` and build an ordered list.
**Status is tracked via GitHub issue labels** — read from GitHub, not from a local file.

```python
import json, subprocess

queue = [json.loads(line) for line in open("scripts/feature-queue.jsonl") if line.strip()]
issue_map = json.load(open("scripts/issue-map.json"))

# Filter to requested phases
if PHASES != "all":
    queue = [f for f in queue if f["phase"] in PHASES]

# Get status for each feature from GitHub issue labels
def get_issue_labels(issue_num):
    r = subprocess.run(
        ["gh", "issue", "view", str(issue_num), "--repo", "atknatk/ember",
         "--json", "labels", "-q", ".labels[].name"],
        capture_output=True, text=True
    )
    return r.stdout.strip().split("\n") if r.returncode == 0 else []

def get_status(feature_id):
    issue_num = issue_map.get(feature_id)
    if not issue_num:
        return "unknown"
    labels = get_issue_labels(issue_num)
    for s in ["status:done", "status:in-progress", "status:blocked", "status:pending"]:
        if s in labels:
            return s.replace("status:", "")
    return "pending"

# Build status dict (batch to avoid N+1 gh calls — read once per feature)
status = {f["id"]: get_status(f["id"]) for f in queue}

# Filter out already done
pending = [f for f in queue if status.get(f["id"]) != "done"]

# If --from given, skip features before that ID
if FROM_ID:
    ids = [f["id"] for f in pending]
    if FROM_ID in ids:
        start_idx = ids.index(FROM_ID)
        pending = pending[start_idx:]

# Topological sort by deps (features whose deps are all done come first)
ordered = topological_sort(pending, status)
```

**Topological sort logic:**
1. Start with features whose all deps have `status:done` (GitHub label)
2. After each feature merges, re-check which features are now unblocked
3. Process in phase+seq order when multiple features are unblocked

---

## Dry Run Output (if --dry-run)

```
=== Queue Run Plan ===

Phase 1 (10 features):
  1. P01-01 [backend] project-setup            deps: none
  2. P01-02 [backend] user-auth                deps: P01-01 ✅
  3. P01-03 [backend] database-schema          deps: P01-01 ✅
  4. P01-04 [backend] chat-stream              deps: P01-02, P01-03 (waiting)
  ...

Phase 2 (4 features):
  11. P02-01 [backend] activity-tracking       deps: P01-02 (waiting)
  ...

Total: 69 features
Already done: 0
To process: 69

Run without --dry-run to start.
```

Stop here if `--dry-run`.

---

## Main Loop

For each feature `F` in the ordered list:

### Step A: Check Dependencies

```python
unmet = [d for d in F["deps"] if status.get(d) != "done"]
if unmet:
    print(f"⏸️  Skipping {F['id']} — unmet deps: {unmet}")
    continue
```

→ Skip (don't stop the queue) — it will be picked up once deps are done.

---

### Step B: Announce + Claim Issue

Mark the issue as `status:in-progress` (claim it) and comment:

```bash
ISSUE_NUM=$(python3 -c "import json; m=json.load(open('scripts/issue-map.json')); print(m.get('{F["id"]}', ''))")
if [ -n "$ISSUE_NUM" ]; then
  # Claim: pending/blocked → in-progress
  gh issue edit $ISSUE_NUM --repo atknatk/ember \
    --add-label "status:in-progress" \
    --remove-label "status:pending" \
    --remove-label "status:blocked"

  gh issue comment $ISSUE_NUM --repo atknatk/ember \
    --body "⏳ **Queue Runner**: Starting [{F["id"]}] — {F["name"]}
Queue position: {n}/{total} | Layer: {F["layer"]}
Starting full pipeline now..."
fi
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[{n}/{total}] Starting: {F["id"]} — {F["name"]}
  Phase: {F["phase"]} | Layer: {F["layer"]}
  Deps:  {F["deps"] or "none"}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step C: Ensure on develop and pull

```bash
git checkout develop
git pull origin develop
```

---

### Step D: Run Pipeline

```
/pipeline-run {F["id"]}
```

**Wait for pipeline to complete.** The pipeline:
1. Creates `feature/{F["pipeline_id"]}` branch
2. Runs all 9 agents
3. Creates PR with `agent:pipeline` label
4. Enables auto-merge

Capture the PR URL from pipeline output.

---

### Step E: Wait for PR to Merge

```bash
PR_URL=$(gh pr list --head "feature/{F["pipeline_id"]}" --repo atknatk/ember --json url -q '.[0].url')
PR_NUMBER=$(gh pr list --head "feature/{F["pipeline_id"]}" --repo atknatk/ember --json number -q '.[0].number')

echo "⏳ Waiting for PR #$PR_NUMBER to merge (auto-merge enabled)..."

# Poll every 30s, max 20 minutes
for i in $(seq 1 40); do
  STATE=$(gh pr view $PR_NUMBER --repo atknatk/ember --json state -q '.state' 2>/dev/null)
  MERGEABLE=$(gh pr view $PR_NUMBER --repo atknatk/ember --json mergeable -q '.mergeable' 2>/dev/null)

  if [ "$STATE" = "MERGED" ]; then
    echo "✅ PR #$PR_NUMBER merged."
    break
  fi

  if [ "$STATE" = "CLOSED" ]; then
    echo "❌ PR #$PR_NUMBER was closed without merging."
    QUEUE_ERROR=true
    break
  fi

  echo "  [$i/40] State: $STATE, Mergeable: $MERGEABLE — waiting 30s..."
  sleep 30
done

if [ "$i" = "40" ] && [ "$STATE" != "MERGED" ]; then
  echo "⚠️  PR did not merge within 20 minutes. Check CI status."
  QUEUE_ERROR=true
fi
```

**If CI fails (PR not merging):**
- Check CI status: `gh pr checks $PR_NUMBER --repo atknatk/ember`
- Attempt to fix (run `/verify` → identify failure → spawn fix agent)
- Max 2 fix attempts. If still failing → **STOP the queue** and report.

---

### Step F: Post-merge Cleanup

```bash
# Pull latest develop
git checkout develop
git pull origin develop

# Delete local feature branch
git branch -d "feature/{F["pipeline_id"]}" 2>/dev/null || true

# Mark done on GitHub (pipeline-run Step 8a should have done this already,
# but ensure it's correct)
ISSUE_NUM=$(python3 -c "import json; m=json.load(open('scripts/issue-map.json')); print(m.get('{F["id"]}', ''))")
if [ -n "$ISSUE_NUM" ]; then
  gh issue edit $ISSUE_NUM --repo atknatk/ember \
    --add-label "status:done" \
    --remove-label "status:in-progress"
fi
```

Update local `status` dict: `status[F["id"]] = "done"`

---

### Step G: Unblock Dependents

After each feature merges, find features that were blocked on it
and update their GitHub labels:

```python
newly_unblocked = [
    f for f in all_pending
    if F["id"] in f["deps"]
    and all(status.get(d) == "done" for d in f["deps"])
]

if newly_unblocked:
    print(f"🔓 Newly unblocked: {[f['id'] for f in newly_unblocked]}")
    for f in newly_unblocked:
        dep_issue = issue_map.get(f["id"])
        if dep_issue:
            subprocess.run([
                "gh", "issue", "edit", str(dep_issue),
                "--repo", "atknatk/ember",
                "--add-label", "status:pending",
                "--remove-label", "status:blocked"
            ])
            subprocess.run([
                "gh", "issue", "comment", str(dep_issue),
                "--repo", "atknatk/ember",
                "--body", f"🔓 **Unblocked** — All dependencies resolved ({F['id']} merged). Ready for pipeline."
            ])
        # Add to processing queue if in scope
        if f not in ordered:
            ordered.append(f)
```

---

### Step H: Log Progress

```
✅ [{n}/{total}] DONE: {F["id"]} — {F["name"]} ({elapsed}s)
```

---

## Error Handling

### Pipeline Failure

If `/pipeline-run` returns an error or fails to complete:

```bash
# Comment on issue
gh issue comment $ISSUE_NUM --repo atknatk/ember \
  --body "❌ **Queue Runner: Pipeline Failed**

Feature: {F['id']} — {F['name']}
Stage: {failed_stage}
Error: {error_details}

**Queue is paused.** Resume with:
\`\`\`
/queue-run --from {F['id']}
\`\`\`"
```

→ **STOP the queue.** Report exact failure to user.

---

### CI Failure (PR not merging)

```bash
gh pr checks $PR_NUMBER --repo atknatk/ember
```

If backend CI fails → spawn backend-dev fix agent with specific error.
If android CI fails → spawn android-dev fix agent with specific error.
If iOS CI fails → report to user (requires local Xcode).

Max 2 fix attempts per feature. If still failing → STOP queue, report.

---

### Skip Feature

If a feature must be skipped (user asks, or dependency loop detected):

```bash
SKIP_ISSUE=$(python3 -c "import json; m=json.load(open('scripts/issue-map.json')); print(m.get('{F["id"]}', ''))")
if [ -n "$SKIP_ISSUE" ]; then
  gh issue edit $SKIP_ISSUE --repo atknatk/ember --add-label "status:blocked"
  gh issue comment $SKIP_ISSUE --repo atknatk/ember --body "⏭️ **Skipped** by queue runner."
fi
```

Log as skipped and continue to next.

---

## Completion Summary

After all features are processed:

```
╔══════════════════════════════════════════════╗
║         Queue Run Complete                   ║
╚══════════════════════════════════════════════╝

Phases processed: {PHASES}
Total features:   {total}
✅ Succeeded:     {done}
⏭️  Skipped:      {skipped}
❌ Failed:        {failed}
⏸️  Blocked:      {blocked} (deps not met)

Completed:
  ✅ P01-01 — project-setup
  ✅ P01-02 — user-auth
  ...

{If any failed:}
Failed:
  ❌ P01-05 — mem0-integration — reason: ...

{If any blocked:}
Still blocked (deps not met):
  ⏸️ P01-04 — chat-stream — waiting for: P01-02, P01-03

{Next steps:}
Next phase: /queue-run {next_phase}
Resume from failure: /queue-run --from {failed_id}
```

---

## Rules

1. **One feature at a time** — never run multiple pipelines in parallel
2. **Always start from develop** — `git checkout develop && git pull` before each feature
3. **Dependency order respected** — never process a feature with unmet deps
4. **Wait for PR merge** — don't start next feature until PR merges to develop
5. **On failure: STOP** — don't skip to next feature when current one fails
6. **Resume is safe** — `--from P01-03` skips already-done features
7. **GitHub issue labels are truth** — `status:done` = merged to develop
8. **Auto-merge only** — never force-merge or skip CI checks
