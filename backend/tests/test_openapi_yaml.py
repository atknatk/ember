"""Tests for OpenAPI YAML spec syntax and completeness.

Validates that all YAML files parse correctly, $ref pointers resolve,
the merged spec is valid OpenAPI 3.1, and every endpoint has proper
documentation and security configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "shared" / "api-contracts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    """Load a YAML file and return its contents."""
    with open(path) as f:
        return yaml.safe_load(f)


def _get_all_yaml_files() -> list[Path]:
    """Get all .yaml files in the api-contracts directory."""
    return sorted(CONTRACTS_DIR.rglob("*.yaml"))


def _load_root_spec() -> dict:
    """Load the root ember-api.yaml."""
    return _load_yaml(CONTRACTS_DIR / "ember-api.yaml")


def _resolve_path_ref(ref_str: str) -> tuple[Path, str]:
    """Parse a $ref string into a file path and a JSON pointer."""
    file_part, fragment = ref_str.split("#", 1)
    file_path = CONTRACTS_DIR / file_part
    pointer = fragment.lstrip("/")
    pointer = pointer.replace("~1", "/").replace("~0", "~")
    return file_path, pointer


def _load_all_paths(root: dict) -> dict:
    """Load and resolve all path references from the root spec."""
    paths = {}
    for path_key, ref_obj in root.get("paths", {}).items():
        if "$ref" in ref_obj:
            file_path, pointer = _resolve_path_ref(ref_obj["$ref"])
            data = _load_yaml(file_path)
            if pointer in data:
                paths[path_key] = data[pointer]
        else:
            paths[path_key] = ref_obj
    return paths


# ---------------------------------------------------------------------------
# Tests: YAML syntax
# ---------------------------------------------------------------------------


class TestYamlSyntax:
    """All YAML files must parse without syntax errors."""

    @pytest.mark.parametrize("yaml_file", _get_all_yaml_files(), ids=lambda p: p.name)
    def test_yaml_parses(self, yaml_file: Path) -> None:
        """Each YAML file must parse without errors."""
        data = _load_yaml(yaml_file)
        assert data is not None, f"{yaml_file.name} parsed as empty"


# ---------------------------------------------------------------------------
# Tests: $ref resolution
# ---------------------------------------------------------------------------


class TestRefResolution:
    """All $ref pointers in the root spec must resolve."""

    def test_all_path_refs_resolve(self) -> None:
        """Every $ref in the root paths section resolves to an existing key."""
        root = _load_root_spec()
        for path_key, ref_obj in root.get("paths", {}).items():
            if "$ref" in ref_obj:
                file_path, pointer = _resolve_path_ref(ref_obj["$ref"])
                assert file_path.exists(), (
                    f"Referenced file does not exist: {file_path} "
                    f"(from path {path_key})"
                )
                data = _load_yaml(file_path)
                assert pointer in data, (
                    f"Pointer '{pointer}' not found in {file_path.name} "
                    f"(from path {path_key})"
                )

    def test_schema_refs_in_paths_resolve(self) -> None:
        """All $ref pointers in path operation schemas resolve to existing files."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        broken_refs: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                refs = _collect_refs(operation)
                for ref in refs:
                    if ref.startswith("#/"):
                        continue  # internal ref within same file — skip
                    if "#" in ref:
                        file_part, fragment = ref.split("#", 1)
                        # Refs in path files are relative to paths/ dir
                        ref_path = CONTRACTS_DIR / "paths" / file_part
                        if not ref_path.exists():
                            broken_refs.append(
                                f"{method.upper()} {path_key}: {ref} -> "
                                f"file not found: {ref_path}"
                            )
                            continue
                        data = _load_yaml(ref_path)
                        pointer = fragment.lstrip("/")
                        if pointer not in data:
                            broken_refs.append(
                                f"{method.upper()} {path_key}: {ref} -> "
                                f"pointer '{pointer}' not found in {ref_path.name}"
                            )

        assert not broken_refs, (
            "Broken $ref pointers:\n" + "\n".join(f"  - {r}" for r in broken_refs)
        )


def _collect_refs(obj: object) -> list[str]:
    """Recursively collect all $ref values from a nested structure."""
    refs: list[str] = []
    if isinstance(obj, dict):
        if "$ref" in obj:
            refs.append(obj["$ref"])
        for value in obj.values():
            refs.extend(_collect_refs(value))
    elif isinstance(obj, list):
        for item in obj:
            refs.extend(_collect_refs(item))
    return refs


# ---------------------------------------------------------------------------
# Tests: content completeness
# ---------------------------------------------------------------------------


class TestContentCompleteness:
    """Every endpoint must have required documentation fields."""

    def test_every_path_has_responses(self) -> None:
        """Every path operation must have at least one response defined."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        missing: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses", {})
                if not responses:
                    missing.append(f"{method.upper()} {path_key}")

        assert not missing, (
            "Endpoints without responses:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_every_endpoint_has_description(self) -> None:
        """Every path operation must have a description."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        missing: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                if not operation.get("description"):
                    missing.append(f"{method.upper()} {path_key}")

        assert not missing, (
            "Endpoints without description:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_endpoint_count(self) -> None:
        """The spec must document all 19 endpoint+method combinations."""
        root = _load_root_spec()
        paths = _load_all_paths(root)

        count = 0
        for operations in paths.values():
            for method, op in operations.items():
                if isinstance(op, dict):
                    count += 1

        assert count == 19, f"Expected 19 endpoints, found {count}"


# ---------------------------------------------------------------------------
# Tests: security
# ---------------------------------------------------------------------------


class TestSecurity:
    """Auth endpoints must have correct security configuration."""

    # These endpoints must have security: [] (no auth)
    PUBLIC_ENDPOINTS = {
        ("get", "/health"),
        ("post", "/auth/register"),
        ("post", "/auth/login"),
        ("post", "/auth/refresh"),
    }

    def test_public_endpoints_have_empty_security(self) -> None:
        """Health, register, login, refresh must have security: []."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        errors: list[str] = []

        for method, path_key in self.PUBLIC_ENDPOINTS:
            if path_key not in paths:
                errors.append(f"Missing path: {path_key}")
                continue
            operation = paths[path_key].get(method, {})
            security = operation.get("security")
            if security != []:
                errors.append(
                    f"{method.upper()} {path_key}: expected security: [], "
                    f"got {security}"
                )

        assert not errors, "\n".join(errors)

    def test_protected_endpoints_inherit_global_security(self) -> None:
        """All non-public endpoints must not have security: [] override."""
        root = _load_root_spec()

        # Verify global security is set
        global_security = root.get("security")
        assert global_security, "Root spec must have global security defined"

        paths = _load_all_paths(root)
        errors: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                if (method, path_key) in self.PUBLIC_ENDPOINTS:
                    continue  # skip public endpoints
                security = operation.get("security")
                if security == []:
                    errors.append(
                        f"{method.upper()} {path_key}: has security: [] "
                        f"but should inherit global auth"
                    )

        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# Tests: root spec structure
# ---------------------------------------------------------------------------


class TestRootSpec:
    """The root ember-api.yaml must have correct structure."""

    def test_openapi_version(self) -> None:
        """Root spec must declare OpenAPI 3.1.0."""
        root = _load_root_spec()
        assert root.get("openapi") == "3.1.0"

    def test_info_section(self) -> None:
        """Root spec must have info with title and version."""
        root = _load_root_spec()
        info = root.get("info", {})
        assert info.get("title") == "Ember API"
        assert info.get("version") == "1.0.0"

    def test_security_schemes(self) -> None:
        """Root spec must define bearerAuth security scheme."""
        root = _load_root_spec()
        schemes = root.get("components", {}).get("securitySchemes", {})
        assert "bearerAuth" in schemes
        assert schemes["bearerAuth"]["type"] == "http"
        assert schemes["bearerAuth"]["scheme"] == "bearer"

    def test_tags_defined(self) -> None:
        """Root spec must define all expected tags."""
        root = _load_root_spec()
        tag_names = {t["name"] for t in root.get("tags", [])}
        expected = {
            "health", "auth", "characters", "chat",
            "memories", "media", "onboarding", "profile",
        }
        assert tag_names == expected, f"Missing tags: {expected - tag_names}"
