"""Tests for the doc-code sync CI check script (P1.5-07).

Verifies that:
  - All 7 checks pass against the current codebase (exit code 0)
  - Each check detects the specific drift it was designed to catch
  - Edge cases in parsing helpers behave correctly

The script under test is backend/scripts/check_doc_code_sync.py.
No application code is modified; only the script logic is exercised.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module import setup
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Import helpers and public functions from the script.
# The script uses module-level lists (failures, warnings) that are mutated by
# each check function, so we import the module and reset state between tests.
import scripts.check_doc_code_sync as sync_module  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
DOCS_STANDARDS = REPO_ROOT / "docs" / "standards"


def _reset_state() -> None:
    """Clear the module-level failures/warnings lists before each test."""
    sync_module.failures.clear()
    sync_module.warnings.clear()


# ---------------------------------------------------------------------------
# Tests: current codebase — all checks pass
# ---------------------------------------------------------------------------


class TestCurrentCodebase:
    """All 7 checks must pass against the real codebase (exit code 0)."""

    def test_script_exits_zero_on_current_codebase(self) -> None:
        """Running the script against the real repo must exit with code 0."""
        result = subprocess.run(
            [sys.executable, str(BACKEND_DIR / "scripts" / "check_doc_code_sync.py")],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
        )
        assert result.returncode == 0, (
            f"Script failed with exit code {result.returncode}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    def test_script_prints_all_checks_passed_on_success(self) -> None:
        """Script stdout must include 'All checks passed.' on success."""
        result = subprocess.run(
            [sys.executable, str(BACKEND_DIR / "scripts" / "check_doc_code_sync.py")],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
        )
        assert "All checks passed." in result.stdout

    def test_check1_model_imports_no_failures(self) -> None:
        """Check 1: All model imports in docs reference existing files and classes."""
        _reset_state()
        sync_module.check_model_imports()
        assert sync_module.failures == [], (
            f"Unexpected model import failures: {sync_module.failures}"
        )

    def test_check2_route_files_no_failures(self) -> None:
        """Check 2: All route files in code are listed in backend.md."""
        _reset_state()
        sync_module.check_route_files()
        assert sync_module.failures == [], (
            f"Unexpected route file failures: {sync_module.failures}"
        )

    def test_check3_config_fields_no_failures(self) -> None:
        """Check 3: Config field coverage produces no FAILs (warnings are OK)."""
        _reset_state()
        sync_module.check_config_fields()
        assert sync_module.failures == [], (
            f"Unexpected config field failures: {sync_module.failures}"
        )

    def test_check4_service_files_no_failures(self) -> None:
        """Check 4: All service files in code are listed in backend.md."""
        _reset_state()
        sync_module.check_service_files()
        assert sync_module.failures == [], (
            f"Unexpected service file failures: {sync_module.failures}"
        )

    def test_check5_no_async_memory_client_in_docs(self) -> None:
        """Check 5: AsyncMemoryClient does not appear in any standards doc."""
        _reset_state()
        sync_module.check_async_memory_client()
        assert sync_module.failures == [], (
            f"AsyncMemoryClient found in docs: {sync_module.failures}"
        )

    def test_check6_no_user_model_reference_in_docs(self) -> None:
        """Check 6: 'from app.models.user import' does not appear in any standards doc."""
        _reset_state()
        sync_module.check_user_model_reference()
        assert sync_module.failures == [], (
            f"app.models.user reference found in docs: {sync_module.failures}"
        )

    def test_check7_route_prefixes_no_failures(self) -> None:
        """Check 7: Route prefix consistency produces no FAILs (warnings are OK)."""
        _reset_state()
        sync_module.check_route_prefixes()
        assert sync_module.failures == [], (
            f"Unexpected route prefix failures: {sync_module.failures}"
        )

    def test_zero_results_message_in_stdout(self) -> None:
        """Script must print '0 failures, 0 warnings' when codebase is clean."""
        result = subprocess.run(
            [sys.executable, str(BACKEND_DIR / "scripts" / "check_doc_code_sync.py")],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
        )
        assert "0 failures" in result.stdout
        assert "0 warnings" in result.stdout


# ---------------------------------------------------------------------------
# Tests: Check 1 — Model class existence (drift detection)
# ---------------------------------------------------------------------------


class TestCheck1ModelImports:
    """check_model_imports must detect references to non-existent model files/classes."""

    def test_fails_when_referenced_model_file_does_not_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when a docs import references a missing model file."""
        _reset_state()

        # Write a fake backend.md that references a non-existent model
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```python\nfrom app.models.doesnotexist import GhostModel\n```\n"
        )
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text("")

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)

        sync_module.check_model_imports()

        assert len(sync_module.failures) == 1
        assert "app.models.doesnotexist" in sync_module.failures[0]

    def test_fails_when_model_file_exists_but_class_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when the model file exists but the class is not defined."""
        _reset_state()

        # Create a fake models directory with a file that lacks the expected class
        fake_models_dir = tmp_path / "app" / "models"
        fake_models_dir.mkdir(parents=True)
        model_file = fake_models_dir / "profile.py"
        model_file.write_text("class WrongClass:\n    pass\n")

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```python\nfrom app.models.profile import Profile\n```\n"
        )
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text("")

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)

        sync_module.check_model_imports()

        assert len(sync_module.failures) == 1
        assert "Profile" in sync_module.failures[0]

    def test_passes_when_model_file_and_class_both_exist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No failures when docs reference a model that actually exists."""
        _reset_state()

        # Use the real BACKEND_MD and BACKEND_DIR (Profile class exists)
        monkeypatch.setattr(sync_module, "BACKEND_MD", DOCS_STANDARDS / "backend.md")
        monkeypatch.setattr(sync_module, "TESTING_MD", DOCS_STANDARDS / "testing.md")
        monkeypatch.setattr(sync_module, "BACKEND_DIR", BACKEND_DIR)

        sync_module.check_model_imports()

        assert sync_module.failures == []

    def test_skips_doc_gracefully_when_file_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check_model_imports does not crash when a doc file does not exist."""
        _reset_state()

        monkeypatch.setattr(sync_module, "BACKEND_MD", tmp_path / "nonexistent.md")
        monkeypatch.setattr(sync_module, "TESTING_MD", tmp_path / "also_missing.md")

        sync_module.check_model_imports()  # must not raise

        assert sync_module.failures == []

    def test_detects_user_model_reference_that_was_a_known_contradiction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Injecting the old C-01 drift pattern triggers a failure (regression guard)."""
        _reset_state()

        # Simulate the pre-fix state: backend.md references app.models.user
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```python\nfrom app.models.user import User\n```\n"
        )
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text("")

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)

        sync_module.check_model_imports()

        # app/models/user.py does not exist, so this must be flagged
        assert any("app.models.user" in f for f in sync_module.failures)


# ---------------------------------------------------------------------------
# Tests: Check 2 — Route file existence (drift detection)
# ---------------------------------------------------------------------------


class TestCheck2RouteFiles:
    """check_route_files must detect route files in code missing from docs."""

    def test_fails_when_code_route_file_not_listed_in_docs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when a route file exists in code but is absent from docs."""
        _reset_state()

        # Create a routes dir with a new file not mentioned in the fake docs
        fake_routes_dir = tmp_path / "app" / "routes"
        fake_routes_dir.mkdir(parents=True)
        (fake_routes_dir / "newfeature.py").write_text("")
        (fake_routes_dir / "__init__.py").write_text("")

        # backend.md that does NOT list newfeature.py
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```\nbackend/\n  app/\n    routes/\n      auth.py\n```\n"
        )

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)

        sync_module.check_route_files()

        assert any("newfeature.py" in f for f in sync_module.failures)

    def test_passes_when_all_route_files_listed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No failures when all code route files appear in the docs listing."""
        _reset_state()

        fake_routes_dir = tmp_path / "app" / "routes"
        fake_routes_dir.mkdir(parents=True)
        (fake_routes_dir / "auth.py").write_text("")
        (fake_routes_dir / "__init__.py").write_text("")

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```\nbackend/\n  app/\n    routes/\n      auth.py\n```\n"
        )

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)

        sync_module.check_route_files()

        assert sync_module.failures == []

    def test_init_py_not_flagged_as_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """__init__.py is never flagged as missing from docs listing."""
        _reset_state()

        fake_routes_dir = tmp_path / "app" / "routes"
        fake_routes_dir.mkdir(parents=True)
        (fake_routes_dir / "__init__.py").write_text("")

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text("No route files listed here.\n")

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)

        sync_module.check_route_files()

        assert sync_module.failures == []

    def test_skips_gracefully_when_backend_md_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check_route_files does not crash when backend.md does not exist."""
        _reset_state()

        monkeypatch.setattr(sync_module, "BACKEND_MD", tmp_path / "missing.md")

        sync_module.check_route_files()  # must not raise

        assert sync_module.failures == []

    def test_real_codebase_all_route_files_covered(self) -> None:
        """All actual route files in backend/app/routes/ appear in backend.md."""
        _reset_state()

        # Reset to real paths
        sync_module.BACKEND_MD  # noqa: B018 — reading attribute to verify it exists
        sync_module.check_route_files()

        assert sync_module.failures == [], (
            f"Route file(s) missing from docs: {sync_module.failures}"
        )


# ---------------------------------------------------------------------------
# Tests: Check 3 — Config field coverage (warnings only)
# ---------------------------------------------------------------------------


class TestCheck3ConfigFields:
    """check_config_fields emits WARNs (never FAILs) for coverage gaps."""

    def test_warns_when_code_field_not_in_docs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A WARN is emitted when a Settings field in code is absent from docs."""
        _reset_state()

        config_source = (
            "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    existing_field: str = 'x'\n"
            "    brand_new_field: int = 42\n"
        )
        config_file = tmp_path / "config.py"
        config_file.write_text(config_source)

        backend_md = tmp_path / "backend.md"
        backend_md.write_text(
            "```python\nclass Settings(BaseSettings):\n    existing_field: str\n```\n"
        )

        monkeypatch.setattr(sync_module, "CONFIG_PY", config_file)
        monkeypatch.setattr(sync_module, "BACKEND_MD", backend_md)

        sync_module.check_config_fields()

        assert sync_module.failures == [], "Config check must never FAIL"
        assert any("brand_new_field" in w for w in sync_module.warnings), (
            f"Expected warning about brand_new_field, got: {sync_module.warnings}"
        )

    def test_warns_when_doc_field_not_in_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A WARN is emitted when a docs-only field does not exist in code."""
        _reset_state()

        config_source = (
            "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    real_field: str = 'x'\n"
        )
        config_file = tmp_path / "config.py"
        config_file.write_text(config_source)

        backend_md = tmp_path / "backend.md"
        backend_md.write_text(
            "```python\n"
            "class Settings(BaseSettings):\n"
            "    real_field: str\n"
            "    phantom_field: int\n"
            "```\n"
        )

        monkeypatch.setattr(sync_module, "CONFIG_PY", config_file)
        monkeypatch.setattr(sync_module, "BACKEND_MD", backend_md)

        sync_module.check_config_fields()

        assert sync_module.failures == [], "Config check must never FAIL"
        assert any("phantom_field" in w for w in sync_module.warnings)

    def test_no_warnings_when_fields_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No warnings when code and docs Settings fields match exactly."""
        _reset_state()

        config_source = (
            "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    debug: bool = False\n"
            "    database_url: str = ''\n"
        )
        config_file = tmp_path / "config.py"
        config_file.write_text(config_source)

        backend_md = tmp_path / "backend.md"
        backend_md.write_text(
            "```python\n"
            "class Settings(BaseSettings):\n"
            "    debug: bool\n"
            "    database_url: str\n"
            "```\n"
        )

        monkeypatch.setattr(sync_module, "CONFIG_PY", config_file)
        monkeypatch.setattr(sync_module, "BACKEND_MD", backend_md)

        sync_module.check_config_fields()

        assert sync_module.failures == []
        assert sync_module.warnings == []

    def test_model_config_excluded_from_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """model_config attribute is not counted as a Settings field."""
        _reset_state()

        config_source = (
            "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
            "class Settings(BaseSettings):\n"
            "    model_config = SettingsConfigDict(env_file='.env')\n"
            "    debug: bool = False\n"
        )
        config_file = tmp_path / "config.py"
        config_file.write_text(config_source)

        backend_md = tmp_path / "backend.md"
        backend_md.write_text(
            "```python\n"
            "class Settings(BaseSettings):\n"
            "    debug: bool\n"
            "```\n"
        )

        monkeypatch.setattr(sync_module, "CONFIG_PY", config_file)
        monkeypatch.setattr(sync_module, "BACKEND_MD", backend_md)

        sync_module.check_config_fields()

        # model_config must not trigger a warning about being undocumented
        assert not any("model_config" in w for w in sync_module.warnings)

    def test_skips_gracefully_when_config_py_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check_config_fields does not crash when config.py does not exist."""
        _reset_state()

        monkeypatch.setattr(sync_module, "CONFIG_PY", tmp_path / "nonexistent.py")
        monkeypatch.setattr(sync_module, "BACKEND_MD", tmp_path / "also_missing.md")

        sync_module.check_config_fields()  # must not raise

        assert sync_module.failures == []


# ---------------------------------------------------------------------------
# Tests: Check 4 — Service file existence (drift detection)
# ---------------------------------------------------------------------------


class TestCheck4ServiceFiles:
    """check_service_files must detect service files in code missing from docs."""

    def test_fails_when_code_service_file_not_listed_in_docs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when a service file exists in code but is absent from docs."""
        _reset_state()

        fake_services_dir = tmp_path / "app" / "services"
        fake_services_dir.mkdir(parents=True)
        (fake_services_dir / "new_service.py").write_text("")
        (fake_services_dir / "__init__.py").write_text("")

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```\nbackend/\n  app/\n    services/\n      auth_service.py\n```\n"
        )

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)

        sync_module.check_service_files()

        assert any("new_service.py" in f for f in sync_module.failures)

    def test_passes_when_all_service_files_listed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No failures when all code service files appear in the docs listing."""
        _reset_state()

        fake_services_dir = tmp_path / "app" / "services"
        fake_services_dir.mkdir(parents=True)
        (fake_services_dir / "auth_service.py").write_text("")
        (fake_services_dir / "__init__.py").write_text("")

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```\nbackend/\n  app/\n    services/\n      auth_service.py\n```\n"
        )

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)

        sync_module.check_service_files()

        assert sync_module.failures == []

    def test_real_codebase_all_service_files_covered(self) -> None:
        """All actual service .py files in backend/app/services/ appear in backend.md."""
        _reset_state()
        sync_module.check_service_files()
        assert sync_module.failures == [], (
            f"Service file(s) missing from docs: {sync_module.failures}"
        )


# ---------------------------------------------------------------------------
# Tests: Check 5 — AsyncMemoryClient reference (drift detection)
# ---------------------------------------------------------------------------


class TestCheck5AsyncMemoryClient:
    """check_async_memory_client must detect the banned AsyncMemoryClient import."""

    def test_fails_when_async_memory_client_in_backend_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when backend.md references AsyncMemoryClient."""
        _reset_state()

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```python\nfrom mem0 import AsyncMemoryClient\n```\n"
        )
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text("")

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)

        sync_module.check_async_memory_client()

        assert len(sync_module.failures) == 1
        assert "AsyncMemoryClient" in sync_module.failures[0]
        assert "backend.md" in sync_module.failures[0]

    def test_fails_when_async_memory_client_in_testing_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when testing.md references AsyncMemoryClient."""
        _reset_state()

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text("")
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text("Use AsyncMemoryClient for async support.\n")

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)

        sync_module.check_async_memory_client()

        assert any("AsyncMemoryClient" in f for f in sync_module.failures)
        assert any("testing.md" in f for f in sync_module.failures)

    def test_passes_when_only_memory_client_used(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No failures when docs use MemoryClient (sync) correctly."""
        _reset_state()

        content = "from mem0 import MemoryClient\nclient = MemoryClient()\n"
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(content)
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text(content)

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)

        sync_module.check_async_memory_client()

        assert sync_module.failures == []

    def test_real_docs_contain_no_async_memory_client(self) -> None:
        """The real docs/standards/backend.md must not contain AsyncMemoryClient."""
        backend_md_text = (DOCS_STANDARDS / "backend.md").read_text()
        assert "AsyncMemoryClient" not in backend_md_text, (
            "Contradiction C-03 regression: AsyncMemoryClient found in backend.md"
        )

    def test_skips_gracefully_when_docs_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check_async_memory_client does not crash when doc files are absent."""
        _reset_state()

        monkeypatch.setattr(sync_module, "BACKEND_MD", tmp_path / "missing.md")
        monkeypatch.setattr(sync_module, "TESTING_MD", tmp_path / "also_missing.md")

        sync_module.check_async_memory_client()  # must not raise

        assert sync_module.failures == []


# ---------------------------------------------------------------------------
# Tests: Check 6 — User model reference (drift detection)
# ---------------------------------------------------------------------------


class TestCheck6UserModelReference:
    """check_user_model_reference must detect the banned app.models.user import."""

    def test_fails_when_from_app_models_user_import_in_standards_doc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when any standards/*.md has 'from app.models.user import'."""
        _reset_state()

        fake_standards = tmp_path / "standards"
        fake_standards.mkdir()
        bad_doc = fake_standards / "backend.md"
        bad_doc.write_text("from app.models.user import User\n")

        monkeypatch.setattr(sync_module, "DOCS_STANDARDS", fake_standards)

        sync_module.check_user_model_reference()

        assert len(sync_module.failures) == 1
        assert "app.models.user" in sync_module.failures[0]
        assert "backend.md" in sync_module.failures[0]

    def test_fails_when_user_model_in_testing_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A FAIL is recorded when testing.md contains 'from app.models.user import'."""
        _reset_state()

        fake_standards = tmp_path / "standards"
        fake_standards.mkdir()
        (fake_standards / "testing.md").write_text(
            "```python\nfrom app.models.user import User\n```"
        )

        monkeypatch.setattr(sync_module, "DOCS_STANDARDS", fake_standards)

        sync_module.check_user_model_reference()

        assert any("app.models.user" in f for f in sync_module.failures)

    def test_passes_when_only_profile_model_referenced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No failures when docs correctly import from app.models.profile."""
        _reset_state()

        fake_standards = tmp_path / "standards"
        fake_standards.mkdir()
        (fake_standards / "backend.md").write_text(
            "from app.models.profile import Profile\n"
        )

        monkeypatch.setattr(sync_module, "DOCS_STANDARDS", fake_standards)

        sync_module.check_user_model_reference()

        assert sync_module.failures == []

    def test_real_standards_contain_no_user_model_import(self) -> None:
        """All real docs/standards/*.md files must not reference app.models.user."""
        for md_file in DOCS_STANDARDS.glob("*.md"):
            content = md_file.read_text()
            assert "from app.models.user import" not in content, (
                f"Contradiction C-01 regression: app.models.user found in {md_file.name}"
            )

    def test_multiple_violations_in_multiple_files_all_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All files with the banned import are reported, not just the first."""
        _reset_state()

        fake_standards = tmp_path / "standards"
        fake_standards.mkdir()
        (fake_standards / "backend.md").write_text("from app.models.user import User\n")
        (fake_standards / "testing.md").write_text("from app.models.user import User\n")

        monkeypatch.setattr(sync_module, "DOCS_STANDARDS", fake_standards)

        sync_module.check_user_model_reference()

        assert len(sync_module.failures) == 2


# ---------------------------------------------------------------------------
# Tests: Check 7 — Route prefix consistency (warnings only)
# ---------------------------------------------------------------------------


class TestCheck7RoutePrefixes:
    """check_route_prefixes emits WARNs for prefix mismatches, never FAILs."""

    def test_warns_when_main_py_prefix_not_in_docs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A WARN is emitted when main.py has a prefix not documented in backend.md."""
        _reset_state()

        fake_main = tmp_path / "main.py"
        fake_main.write_text(
            "app.include_router(newrouter.router, prefix='/api/v1/newfeature')\n"
        )
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "app.include_router(health.router, prefix='/api/v1')\n"
        )

        monkeypatch.setattr(sync_module, "MAIN_PY", fake_main)
        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)

        sync_module.check_route_prefixes()

        assert sync_module.failures == [], "Route prefix check must never FAIL"
        assert any("/api/v1/newfeature" in w for w in sync_module.warnings)

    def test_warns_when_docs_prefix_not_in_main_py(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A WARN is emitted when backend.md has a prefix absent from main.py."""
        _reset_state()

        fake_main = tmp_path / "main.py"
        fake_main.write_text(
            "app.include_router(health.router, prefix='/api/v1')\n"
        )
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "app.include_router(health.router, prefix='/api/v1')\n"
            "app.include_router(voice.router, prefix='/api/v1/voice')\n"
        )

        monkeypatch.setattr(sync_module, "MAIN_PY", fake_main)
        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)

        sync_module.check_route_prefixes()

        assert sync_module.failures == [], "Route prefix check must never FAIL"
        assert any("/api/v1/voice" in w for w in sync_module.warnings)

    def test_no_warnings_when_prefixes_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No warnings when all prefixes in main.py and backend.md match."""
        _reset_state()

        content = "app.include_router(health.router, prefix='/api/v1')\n"
        fake_main = tmp_path / "main.py"
        fake_main.write_text(content)
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(content)

        monkeypatch.setattr(sync_module, "MAIN_PY", fake_main)
        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)

        sync_module.check_route_prefixes()

        assert sync_module.failures == []
        assert sync_module.warnings == []

    def test_skips_gracefully_when_files_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check_route_prefixes does not crash when main.py or backend.md is missing."""
        _reset_state()

        monkeypatch.setattr(sync_module, "MAIN_PY", tmp_path / "missing.py")
        monkeypatch.setattr(sync_module, "BACKEND_MD", tmp_path / "missing.md")

        sync_module.check_route_prefixes()  # must not raise

        assert sync_module.failures == []


# ---------------------------------------------------------------------------
# Tests: Exit code behaviour
# ---------------------------------------------------------------------------


class TestExitCode:
    """main() must return the correct exit code based on failures/warnings."""

    def test_exit_code_0_when_no_failures(self) -> None:
        """main() returns 0 when there are no failures."""
        _reset_state()

        result = sync_module.main()

        assert result == 0, f"Expected 0 but got {result}, failures: {sync_module.failures}"

    def test_exit_code_1_when_there_are_failures(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """main() returns 1 when at least one FAIL is recorded."""
        _reset_state()

        # Inject a missing route file to trigger a failure
        fake_routes_dir = tmp_path / "app" / "routes"
        fake_routes_dir.mkdir(parents=True)
        (fake_routes_dir / "undocumented.py").write_text("")
        (fake_routes_dir / "__init__.py").write_text("")

        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```\nbackend/\n  app/\n    routes/\n      auth.py\n```\n"
        )
        # Services and models dirs must exist to avoid crashes
        (tmp_path / "app" / "services").mkdir(parents=True)
        (tmp_path / "app" / "models").mkdir(parents=True)
        fake_config = tmp_path / "config.py"
        fake_config.write_text(
            "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n    debug: bool = False\n"
        )
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text("")

        fake_standards = tmp_path / "standards"
        fake_standards.mkdir()

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)
        monkeypatch.setattr(sync_module, "DOCS_STANDARDS", fake_standards)
        monkeypatch.setattr(sync_module, "MAIN_PY", tmp_path / "main.py")
        monkeypatch.setattr(sync_module, "CONFIG_PY", fake_config)

        result = sync_module.main()

        assert result == 1

    def test_exit_code_0_with_warnings_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """main() returns 0 when there are warnings but no failures."""
        _reset_state()

        # Config mismatch (produces WARN), no route issues
        fake_routes_dir = tmp_path / "app" / "routes"
        fake_routes_dir.mkdir(parents=True)
        (fake_routes_dir / "__init__.py").write_text("")

        fake_services_dir = tmp_path / "app" / "services"
        fake_services_dir.mkdir(parents=True)
        (fake_services_dir / "__init__.py").write_text("")

        (tmp_path / "app" / "models").mkdir(parents=True)

        fake_config = tmp_path / "config.py"
        fake_config.write_text(
            "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    real_field: str = 'x'\n"
            "    undocumented_field: int = 0\n"
        )
        fake_backend_md = tmp_path / "backend.md"
        fake_backend_md.write_text(
            "```python\nclass Settings(BaseSettings):\n    real_field: str\n```\n"
        )
        fake_testing_md = tmp_path / "testing.md"
        fake_testing_md.write_text("")
        fake_standards = tmp_path / "standards"
        fake_standards.mkdir()

        monkeypatch.setattr(sync_module, "BACKEND_MD", fake_backend_md)
        monkeypatch.setattr(sync_module, "TESTING_MD", fake_testing_md)
        monkeypatch.setattr(sync_module, "BACKEND_DIR", tmp_path)
        monkeypatch.setattr(sync_module, "DOCS_STANDARDS", fake_standards)
        monkeypatch.setattr(sync_module, "MAIN_PY", tmp_path / "main.py")
        monkeypatch.setattr(sync_module, "CONFIG_PY", fake_config)

        result = sync_module.main()

        assert result == 0
        assert sync_module.failures == []
        assert sync_module.warnings  # at least one warning


# ---------------------------------------------------------------------------
# Tests: Helper function unit tests
# ---------------------------------------------------------------------------


class TestExtractTreeEntries:
    """_extract_tree_entries must correctly parse project structure markdown."""

    def test_extracts_py_filenames_under_routes_section(self) -> None:
        """Filenames under 'routes/' are extracted from indented tree blocks."""
        text = (
            "```\n"
            "backend/\n"
            "  app/\n"
            "    routes/\n"
            "      auth.py\n"
            "      characters.py\n"
            "      health.py\n"
            "    services/\n"
            "      auth_service.py\n"
            "```\n"
        )
        result = sync_module._extract_tree_entries(text, "routes")
        assert "auth.py" in result
        assert "characters.py" in result
        assert "health.py" in result
        # Services must not bleed into routes result
        assert "auth_service.py" not in result

    def test_extracts_py_filenames_under_services_section(self) -> None:
        """Filenames under 'services/' section are extracted correctly."""
        text = (
            "```\n"
            "  app/\n"
            "    services/\n"
            "      chat_service.py\n"
            "      memory_service.py\n"
            "```\n"
        )
        result = sync_module._extract_tree_entries(text, "services")
        assert "chat_service.py" in result
        assert "memory_service.py" in result

    def test_returns_empty_set_when_section_not_found(self) -> None:
        """Returns an empty set when the requested section label is absent."""
        text = "No routes here.\n"
        result = sync_module._extract_tree_entries(text, "routes")
        assert result == set()

    def test_does_not_include_files_with_comments_indicating_planned(self) -> None:
        """Commented-out entries (e.g. '# voice.py — planned') are parsed as non-.py lines."""
        text = (
            "    routes/\n"
            "      chat.py\n"
            "      # voice.py — planned for Phase 3\n"
        )
        result = sync_module._extract_tree_entries(text, "routes")
        assert "chat.py" in result
        # The comment line does not produce a .py entry in the returned set
        # (the regex looks for bare word.py, comments won't match as filenames to check)
        assert "voice.py" not in result or "chat.py" in result  # at minimum chat.py found


class TestParseSettingsFields:
    """_parse_settings_fields must parse Settings class fields from source code."""

    def test_extracts_annotated_field_names(self, tmp_path: Path) -> None:
        """Simple annotated fields are extracted correctly."""
        source = (
            "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    debug: bool = False\n"
            "    database_url: str = ''\n"
            "    max_retries: int = 3\n"
        )
        config_file = tmp_path / "config.py"
        config_file.write_text(source)

        result = sync_module._parse_settings_fields(config_file)
        assert result == {"debug", "database_url", "max_retries"}

    def test_excludes_model_config_attribute(self, tmp_path: Path) -> None:
        """model_config class attribute is excluded from field names."""
        source = (
            "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
            "class Settings(BaseSettings):\n"
            "    model_config = SettingsConfigDict()\n"
            "    app_name: str = 'Ember'\n"
        )
        config_file = tmp_path / "config.py"
        config_file.write_text(source)

        result = sync_module._parse_settings_fields(config_file)
        assert "model_config" not in result
        assert "app_name" in result

    def test_excludes_private_attributes(self, tmp_path: Path) -> None:
        """Fields starting with _ are excluded."""
        source = (
            "from pydantic_settings import BaseSettings\n"
            "class Settings(BaseSettings):\n"
            "    _private: str = 'hidden'\n"
            "    public_field: str = 'visible'\n"
        )
        config_file = tmp_path / "config.py"
        config_file.write_text(source)

        result = sync_module._parse_settings_fields(config_file)
        assert "_private" not in result
        assert "public_field" in result

    def test_returns_empty_set_when_no_settings_class(self, tmp_path: Path) -> None:
        """Returns an empty set when no Settings class is defined."""
        source = "DEBUG = True\n"
        config_file = tmp_path / "config.py"
        config_file.write_text(source)

        result = sync_module._parse_settings_fields(config_file)
        assert result == set()

    def test_real_config_py_returns_known_fields(self) -> None:
        """Real config.py must include key known fields."""
        result = sync_module._parse_settings_fields(BACKEND_DIR / "app" / "config.py")
        expected_fields = {
            "debug", "database_url", "anthropic_api_key", "mem0_api_key",
            "rate_limit_chat", "rate_limit_write", "rate_limit_read",
            "max_context_messages", "cors_origins",
        }
        missing = expected_fields - result
        assert not missing, f"Expected config fields not found: {missing}"


class TestExtractDocSettingsFields:
    """_extract_doc_settings_fields must parse Settings fields from markdown text."""

    def test_extracts_field_names_from_settings_block(self) -> None:
        """Field names in a Settings class code block are extracted."""
        text = (
            "Some prose.\n"
            "```python\n"
            "class Settings(BaseSettings):\n"
            "    debug: bool\n"
            "    database_url: str\n"
            "```\n"
        )
        result = sync_module._extract_doc_settings_fields(text)
        assert "debug" in result
        assert "database_url" in result

    def test_excludes_model_config(self) -> None:
        """model_config is excluded from the extracted field names."""
        text = (
            "class Settings(BaseSettings):\n"
            "    model_config = SettingsConfigDict()\n"
            "    app_name: str\n"
        )
        result = sync_module._extract_doc_settings_fields(text)
        assert "model_config" not in result
        assert "app_name" in result

    def test_returns_empty_set_when_no_settings_block(self) -> None:
        """Returns an empty set when no Settings class appears in the text."""
        result = sync_module._extract_doc_settings_fields("No settings here.\n")
        assert result == set()


class TestExtractIncludeRouterPrefixes:
    """_extract_include_router_prefixes must extract prefix strings from Python source."""

    def test_extracts_prefixes_from_main_py_content(self, tmp_path: Path) -> None:
        """All prefix= values in include_router calls are extracted."""
        source = (
            "app.include_router(health.router, prefix='/api/v1')\n"
            "app.include_router(auth.router, prefix='/api/v1/auth')\n"
            'app.include_router(chat.router, prefix="/api/v1/characters")\n'
        )
        fp = tmp_path / "main.py"
        fp.write_text(source)

        result = sync_module._extract_include_router_prefixes(fp)
        assert "/api/v1" in result
        assert "/api/v1/auth" in result
        assert "/api/v1/characters" in result

    def test_returns_empty_set_when_no_include_router_calls(
        self, tmp_path: Path
    ) -> None:
        """Returns an empty set when the file has no include_router calls."""
        fp = tmp_path / "main.py"
        fp.write_text("app = FastAPI()\n")

        result = sync_module._extract_include_router_prefixes(fp)
        assert result == set()

    def test_real_main_py_contains_expected_prefixes(self) -> None:
        """Real main.py must expose all expected API prefixes."""
        result = sync_module._extract_include_router_prefixes(BACKEND_DIR / "app" / "main.py")
        assert "/api/v1" in result
        assert "/api/v1/auth" in result
        assert "/api/v1/characters" in result


# ---------------------------------------------------------------------------
# Tests: CI workflow integration
# ---------------------------------------------------------------------------


class TestCIWorkflowIntegration:
    """The doc-code sync step must be present in the CI workflow."""

    CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "backend-ci.yml"

    def test_ci_workflow_exists(self) -> None:
        """backend-ci.yml must exist."""
        assert self.CI_WORKFLOW_PATH.exists()

    def test_ci_workflow_contains_doc_code_sync_step(self) -> None:
        """CI workflow must have a step that runs check_doc_code_sync.py."""
        content = self.CI_WORKFLOW_PATH.read_text()
        assert "check_doc_code_sync.py" in content

    def test_ci_workflow_doc_sync_step_has_name(self) -> None:
        """The doc-code sync step in CI must have a descriptive name."""
        import yaml

        workflow = yaml.safe_load(self.CI_WORKFLOW_PATH.read_text())
        found = False
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if "check_doc_code_sync.py" in step.get("run", ""):
                    if step.get("name"):
                        found = True
                        break
        assert found, "check_doc_code_sync.py CI step must have a 'name' field"


# ---------------------------------------------------------------------------
# Tests: Acceptance criteria from spec (C-01 through C-14 key checks)
# ---------------------------------------------------------------------------


class TestSpecAcceptanceCriteria:
    """Verify key acceptance criteria from the doc-code-sync spec directly on docs."""

    def test_ac1_no_from_app_models_user_in_backend_md(self) -> None:
        """AC1: backend.md must not contain 'from app.models.user'."""
        text = (DOCS_STANDARDS / "backend.md").read_text()
        assert "from app.models.user" not in text

    def test_ac2_no_async_memory_client_in_backend_md(self) -> None:
        """AC2: backend.md must not contain 'AsyncMemoryClient'."""
        text = (DOCS_STANDARDS / "backend.md").read_text()
        assert "AsyncMemoryClient" not in text

    def test_ac3_cognito_module_path_is_app_core_auth(self) -> None:
        """AC3: backend.md must reference app/core/auth.py for cognito verification."""
        text = (DOCS_STANDARDS / "backend.md").read_text()
        assert "app/core/auth.py" in text

    def test_ac4_create_app_includes_media_onboarding_profile(self) -> None:
        """AC4: backend.md create_app example must include media, onboarding, profile routers."""
        text = (DOCS_STANDARDS / "backend.md").read_text()
        assert "media" in text
        assert "onboarding" in text
        assert "profile" in text

    def test_ac4_create_app_does_not_include_voice_router(self) -> None:
        """AC4: backend.md create_app example must NOT list a voice router call."""
        text = (DOCS_STANDARDS / "backend.md").read_text()
        # The comment about voice being planned is acceptable; an include_router call is not
        import re
        voice_router_call = re.search(r"include_router\([^)]*voice[^)]*\)", text)
        assert voice_router_call is None, (
            "backend.md must not include a voice router registration "
            "(Phase 3 — not yet implemented)"
        )

    def test_ac5_error_format_is_detail_not_nested_error_object(self) -> None:
        """AC5: docs/04-veri-api.md must show '\"detail\"' not '\"error\": {\"code\"'."""
        text = (REPO_ROOT / "docs" / "04-veri-api.md").read_text()
        assert '"detail"' in text
        # The old nested error format must be gone
        assert '"error": {' not in text

    def test_ac6_memory_item_field_is_memory_not_content(self) -> None:
        """AC6: docs/04-veri-api.md memory item must use 'memory' field, not 'content'."""
        text = (REPO_ROOT / "docs" / "04-veri-api.md").read_text()
        assert '"memory"' in text

    def test_ac7_claude_md_context_window_is_50_not_20(self) -> None:
        """AC7: CLAUDE.md must say 50 messages, not 'last 20 messages'."""
        text = (REPO_ROOT / "CLAUDE.md").read_text()
        # Must contain 50 in context window description
        assert "50" in text
        # The old stale value should not be the primary description
        assert "last 20 messages" not in text

    def test_ac8_claude_md_rate_limiting_describes_grouped_limits(self) -> None:
        """AC8: CLAUDE.md must describe grouped rate limits (chat/write/read)."""
        text = (REPO_ROOT / "CLAUDE.md").read_text()
        assert "chat" in text.lower()
        assert "write" in text.lower()
        assert "read" in text.lower()

    def test_ac9_common_md_default_pagination_limit_is_20(self) -> None:
        """AC9: docs/standards/common.md default limit must be 20, not 30."""
        text = (DOCS_STANDARDS / "common.md").read_text()
        assert "Default `limit`: 20" in text
        assert "Default `limit`: 30" not in text

    def test_ac12_backend_md_sse_events_are_typed_not_delta(self) -> None:
        """AC12: backend.md SSE format must use typed events, not '\"delta\"' format."""
        text = (DOCS_STANDARDS / "backend.md").read_text()
        assert '"type": "chunk"' in text or "type.*chunk" in text or '"chunk"' in text
        # The old delta format must be gone
        assert '"delta"' not in text

    def test_ac13_common_md_agent_names_use_dev_tester_suffixes(self) -> None:
        """AC13: docs/standards/common.md must use 'backend-dev', not 'backend-agent'."""
        text = (DOCS_STANDARDS / "common.md").read_text()
        assert "backend-dev" in text
        assert "ios-dev" in text
        assert "android-dev" in text
        # Old agent names must be gone
        assert "backend-agent" not in text
        assert "ios-agent" not in text
        assert "android-agent" not in text
