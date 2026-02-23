---
name: verify
description: "Run quality gates for the current feature branch (tests, lint, coverage)"
model: claude-sonnet-4-6
allowed-tools: Read, Bash, Glob, Grep
argument-hint: "[--backend] [--ios] [--android] [--all]"
---

# Ember Verify

Run all quality gates for the current feature branch and report results.

---

## Invocation

```
/verify              ← auto-detect platforms from changed files
/verify --backend    ← backend only
/verify --ios        ← iOS only
/verify --android    ← android only
/verify --all        ← all platforms
```

---

## Step 1: Detect Scope

If no flags given, detect which platforms have changes:

```bash
git diff develop...HEAD --name-only
```

- Any `backend/` file → run backend checks
- Any `ios/` file → run iOS checks
- Any `android/` file → run Android checks

---

## Step 2: Backend Checks

If backend in scope:

```bash
cd /path/to/repo

# 1. Lint
cd backend && ruff check app/ --output-format=concise
echo "RUFF_EXIT=$?"

# 2. Type check
cd backend && python -m mypy app/ --ignore-missing-imports --no-error-summary
echo "MYPY_EXIT=$?"

# 3. Tests with coverage
cd backend && python -m pytest tests/ -q \
  --cov=app \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  --tb=short 2>&1
echo "PYTEST_EXIT=$?"
```

**Pass criteria:**
- `ruff`: 0 errors (warnings OK)
- `mypy`: 0 errors
- `pytest`: all pass, coverage ≥ 80%

---

## Step 3: Android Checks

If android in scope:

```bash
cd android

# 1. Lint
./gradlew lint 2>&1 | grep -E "^(ERROR|WARNING|BUILD)" | tail -20
echo "LINT_EXIT=$?"

# 2. Tests
./gradlew testDebugUnitTest 2>&1 | tail -20
echo "TEST_EXIT=$?"
```

**Pass criteria:**
- `lint`: no ERROR level issues
- `testDebugUnitTest`: BUILD SUCCESSFUL

---

## Step 4: iOS Checks

If iOS in scope — note: full build requires Xcode on macOS. Report what can be verified:

```bash
# SwiftLint (if installed)
which swiftlint && cd ios && swiftlint lint --quiet 2>&1 | head -30 || echo "SwiftLint not installed — skip"

# Report: iOS tests require Xcode, run manually with:
# xcodebuild test -scheme Ember -destination 'platform=iOS Simulator,name=iPhone 16'
```

---

## Step 5: Security Scan

Run for all platforms in scope:

```bash
# Backend — no hardcoded secrets
grep -rn "api_key\s*=\s*['\"]" backend/app/ --include="*.py" | grep -v "os\.\|env\.\|settings\.\|test\|#" || echo "No hardcoded keys found"

# Backend — no OFFSET pagination
grep -rn "\bOFFSET\b" backend/app/ --include="*.py" | grep -v "test\|#" || echo "No OFFSET found"

# iOS — forbidden patterns
grep -rn "ObservableObject\|NavigationView\|AsyncImage" ios/Ember/ --include="*.swift" | grep -v "//\|test" || echo "No forbidden iOS patterns"

# Android — forbidden patterns
grep -rn "\b!!\b\|LiveData" android/app/src/main/ --include="*.kt" | grep -v "//\|test" || echo "No forbidden Android patterns"
```

---

## Step 6: Report

Output a clear summary table:

```
## Verify Report — feature/{branch}

| Check | Platform | Result | Detail |
|-------|----------|--------|--------|
| Ruff lint | Backend | ✅ Pass | 0 errors |
| MyPy types | Backend | ✅ Pass | 0 errors |
| Pytest | Backend | ✅ Pass | 47 passed, coverage 84% |
| Gradle lint | Android | ✅ Pass | 0 errors |
| Gradle test | Android | ✅ Pass | 23 passed |
| SwiftLint | iOS | ⚠️ Skip | Not installed |
| Security scan | All | ✅ Pass | No hardcoded secrets |

**Overall: ✅ PASS** (or **❌ FAIL**)

Failures:
- [list any ❌ items with file:line detail]
```

If any ❌ items: print exact error output so the developer can fix.
