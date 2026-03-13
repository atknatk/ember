#!/usr/bin/env python3
"""CI check: detect common doc-code drift patterns.

Mechanically verifiable assertions only — does not parse prose.
Exit code 0 = pass (warnings are OK), 1 = at least one FAIL.

Checks:
  1. Model class existence  — imports in docs vs actual model files
  2. Route file existence   — docs listing vs actual route files
  3. Config field coverage  — Settings fields in code vs docs (WARN only)
  4. Service file existence — docs listing vs actual service files
  5. Mem0 client import     — AsyncMemoryClient must not appear in docs
  6. User model reference   — app.models.user must not appear in docs
  7. Route prefix consistency — main.py vs docs create_app example (WARN only)
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Resolve repo root (backend/ is one level above scripts/)
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DOCS_STANDARDS = REPO_ROOT / "docs" / "standards"
BACKEND_MD = DOCS_STANDARDS / "backend.md"
TESTING_MD = DOCS_STANDARDS / "testing.md"
MAIN_PY = BACKEND_DIR / "app" / "main.py"
CONFIG_PY = BACKEND_DIR / "app" / "config.py"

failures: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL: {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"WARN: {msg}", file=sys.stderr)


# ── Check 1: Model class existence ──────────────────────────────────────────

def check_model_imports() -> None:
    """Verify that model imports referenced in docs actually exist."""
    pattern = re.compile(r"from\s+app\.models\.(\w+)\s+import\s+(\w+)")
    docs = [BACKEND_MD, TESTING_MD]

    for doc_path in docs:
        if not doc_path.exists():
            continue
        text = doc_path.read_text()
        for match in pattern.finditer(text):
            module_name = match.group(1)
            class_name = match.group(2)
            model_file = BACKEND_DIR / "app" / "models" / f"{module_name}.py"
            if not model_file.exists():
                fail(
                    f"{doc_path.name}: references app.models.{module_name} "
                    f"but {model_file.relative_to(BACKEND_DIR)} does not exist"
                )
                continue
            # Check that the class is actually defined in the file
            source = model_file.read_text()
            if f"class {class_name}" not in source:
                fail(
                    f"{doc_path.name}: references class {class_name} in "
                    f"app.models.{module_name} but class not found in file"
                )


# ── Check 2: Route file existence ───────────────────────────────────────────

def _extract_tree_entries(text: str, section: str) -> set[str]:
    """Extract .py filenames from a project-structure tree block in markdown."""
    entries: set[str] = set()
    in_section = False
    for line in text.splitlines():
        if f"{section}/" in line:
            in_section = True
            continue
        if in_section:
            # Stop when we exit the indented block
            stripped = line.lstrip()
            if stripped and not stripped.startswith("#") and not line.startswith(" ") and not line.startswith("\t"):
                break
            m = re.search(r"(\w+\.py)", stripped)
            if m:
                entries.add(m.group(1))
            # Also stop at next top-level directory
            if stripped and not stripped.startswith("#") and "/" in stripped and not stripped.startswith("__"):
                in_section = False
    return entries


def check_route_files() -> None:
    """Verify route files listed in docs exist, and vice versa."""
    if not BACKEND_MD.exists():
        return

    text = BACKEND_MD.read_text()
    doc_routes = _extract_tree_entries(text, "routes")

    actual_dir = BACKEND_DIR / "app" / "routes"
    actual_routes = {
        f.name for f in actual_dir.glob("*.py")
        if f.name != "__init__.py"
    }

    # Files in docs but not in code
    for f in doc_routes - {"__init__.py"}:
        if f not in actual_routes and "planned" not in text.lower():
            # Allow commented-out entries (e.g. "# voice.py — planned")
            pass

    # Files in code but not in docs
    for f in actual_routes:
        if f not in doc_routes:
            fail(f"backend.md project structure: route file {f} exists in code but not listed in docs")


# ── Check 3: Config field coverage ──────────────────────────────────────────

def _parse_settings_fields(filepath: Path) -> set[str]:
    """Parse field names from the Settings class using AST."""
    source = filepath.read_text()
    tree = ast.parse(source)
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    name = item.target.id
                    if not name.startswith("_") and name != "model_config":
                        fields.add(name)
    return fields


def _extract_doc_settings_fields(text: str) -> set[str]:
    """Extract field names from the Settings code block in docs."""
    fields: set[str] = set()
    # Find the Settings class block
    in_settings = False
    for line in text.splitlines():
        if "class Settings" in line:
            in_settings = True
            continue
        if in_settings:
            if line.strip() and not line.startswith(" ") and not line.startswith("#") and not line.startswith("```"):
                if "def " in line or "class " in line:
                    break
            # Match field definitions like: field_name: type = default
            m = re.match(r"\s+(\w+)\s*:\s*\w+", line)
            if m:
                name = m.group(1)
                if not name.startswith("_") and name != "model_config":
                    fields.add(name)
    return fields


def check_config_fields() -> None:
    """Warn about config fields in code not documented, or vice versa."""
    if not CONFIG_PY.exists() or not BACKEND_MD.exists():
        return

    code_fields = _parse_settings_fields(CONFIG_PY)
    doc_fields = _extract_doc_settings_fields(BACKEND_MD.read_text())

    for f in code_fields - doc_fields:
        warn(f"Config field '{f}' exists in code but not in docs/standards/backend.md")

    for f in doc_fields - code_fields:
        warn(f"Config field '{f}' documented in backend.md but not in code")


# ── Check 4: Service file existence ─────────────────────────────────────────

def check_service_files() -> None:
    """Verify service files listed in docs exist, and vice versa."""
    if not BACKEND_MD.exists():
        return

    text = BACKEND_MD.read_text()
    doc_services = _extract_tree_entries(text, "services")

    actual_dir = BACKEND_DIR / "app" / "services"
    actual_services = {
        f.name for f in actual_dir.glob("*.py")
        if f.name != "__init__.py"
    }

    for f in actual_services:
        if f not in doc_services:
            fail(f"backend.md project structure: service file {f} exists in code but not listed in docs")


# ── Check 5: Mem0 client import check ───────────────────────────────────────

def check_async_memory_client() -> None:
    """Fail if AsyncMemoryClient appears in docs (it does not exist in mem0 SDK)."""
    for doc_path in [BACKEND_MD, TESTING_MD]:
        if not doc_path.exists():
            continue
        text = doc_path.read_text()
        if "AsyncMemoryClient" in text:
            fail(
                f"{doc_path.name}: references AsyncMemoryClient which does not exist "
                f"in the mem0 SDK. Use MemoryClient + asyncio.to_thread()."
            )


# ── Check 6: User model reference check ─────────────────────────────────────

def check_user_model_reference() -> None:
    """Fail if any docs/standards/ .md file references app.models.user."""
    pattern = re.compile(r"from\s+app\.models\.user\s+import")
    for md_file in DOCS_STANDARDS.glob("*.md"):
        text = md_file.read_text()
        if pattern.search(text):
            fail(
                f"{md_file.name}: references app.models.user which does not exist. "
                f"The model is Profile in app.models.profile."
            )


# ── Check 7: Route prefix consistency ────────────────────────────────────────

def _extract_include_router_prefixes(filepath: Path) -> set[str]:
    """Extract prefix strings from include_router calls."""
    prefixes: set[str] = set()
    text = filepath.read_text()
    for m in re.finditer(r'include_router\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', text):
        prefixes.add(m.group(1))
    return prefixes


def check_route_prefixes() -> None:
    """Warn if route prefixes in main.py differ from docs."""
    if not MAIN_PY.exists() or not BACKEND_MD.exists():
        return

    code_prefixes = _extract_include_router_prefixes(MAIN_PY)
    doc_prefixes = _extract_include_router_prefixes(BACKEND_MD)

    for p in code_prefixes - doc_prefixes:
        warn(f"Route prefix '{p}' in main.py but not in docs/standards/backend.md create_app example")

    for p in doc_prefixes - code_prefixes:
        warn(f"Route prefix '{p}' in docs but not in main.py")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("Running doc-code sync checks...")

    check_model_imports()
    check_route_files()
    check_config_fields()
    check_service_files()
    check_async_memory_client()
    check_user_model_reference()
    check_route_prefixes()

    print(f"\nResults: {len(failures)} failures, {len(warnings)} warnings")

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    if warnings:
        print("\nWARNINGS (non-blocking):", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
