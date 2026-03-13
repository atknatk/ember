"""Tests for the OpenAPI validation script (drift detection).

Verifies that the validation script correctly identifies when the
hand-written YAML specs match the FastAPI auto-generated schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from scripts.validate_openapi import (  # noqa: E402
    compare_schemas,
    extract_field_names,
    get_fastapi_schema,
    get_query_params,
    get_response_codes,
    load_yaml_specs,
    normalize_path,
)

# ---------------------------------------------------------------------------
# Tests: validation against current codebase
# ---------------------------------------------------------------------------


class TestCurrentCodebase:
    """Run validation against the actual current codebase."""

    def test_validation_passes(self) -> None:
        """The validation script must find zero differences."""
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)
        fastapi_schema = get_fastapi_schema()
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert errors == [], (
            f"Validation found {len(errors)} difference(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    def test_all_fastapi_paths_in_yaml(self) -> None:
        """Every FastAPI path must be documented in the YAML specs."""
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)
        fastapi_schema = get_fastapi_schema()
        fastapi_paths = fastapi_schema.get("paths", {})

        missing: list[str] = []
        for fpath in fastapi_paths:
            if fpath.startswith("/api/v1"):
                yaml_path = fpath[len("/api/v1"):]
                # Skip test-only routes injected by the test suite
                if "/_test" in yaml_path:
                    continue
                if yaml_path not in yaml_paths:
                    missing.append(fpath)

        assert not missing, (
            "Undocumented endpoints:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_all_yaml_paths_in_fastapi(self) -> None:
        """Every YAML spec path must exist in the FastAPI schema."""
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)
        fastapi_schema = get_fastapi_schema()
        fastapi_paths = fastapi_schema.get("paths", {})

        missing: list[str] = []
        for yaml_path in yaml_paths:
            fastapi_path = f"/api/v1{yaml_path}"
            if fastapi_path not in fastapi_paths:
                missing.append(yaml_path)

        assert not missing, (
            "YAML paths not in FastAPI:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_request_body_fields_match(self) -> None:
        """Request body field names must match between YAML and FastAPI for all endpoints."""
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)
        fastapi_schema = get_fastapi_schema()
        errors = compare_schemas(yaml_paths, fastapi_schema)

        body_errors = [e for e in errors if "request body" in e.lower()]
        assert not body_errors, (
            "Request body mismatches:\n"
            + "\n".join(f"  - {e}" for e in body_errors)
        )

    def test_response_codes_match(self) -> None:
        """Response status codes must match between YAML and FastAPI."""
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)
        fastapi_schema = get_fastapi_schema()
        errors = compare_schemas(yaml_paths, fastapi_schema)

        code_errors = [e for e in errors if "response code" in e.lower()]
        assert not code_errors, (
            "Response code mismatches:\n"
            + "\n".join(f"  - {e}" for e in code_errors)
        )

    def test_query_params_match(self) -> None:
        """Query parameter names must match between YAML and FastAPI."""
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)
        fastapi_schema = get_fastapi_schema()
        errors = compare_schemas(yaml_paths, fastapi_schema)

        param_errors = [e for e in errors if "query param" in e.lower()]
        assert not param_errors, (
            "Query parameter mismatches:\n"
            + "\n".join(f"  - {e}" for e in param_errors)
        )


# ---------------------------------------------------------------------------
# Tests: helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Unit tests for validation helper functions."""

    def test_normalize_path(self) -> None:
        """normalize_path adds /api/v1 prefix."""
        assert normalize_path("/health") == "/api/v1/health"
        assert normalize_path("/auth/login") == "/api/v1/auth/login"

    def test_extract_field_names_simple(self) -> None:
        """extract_field_names gets property names from a schema."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        assert extract_field_names(schema) == {"name", "age"}

    def test_extract_field_names_empty(self) -> None:
        """extract_field_names returns empty set for empty schema."""
        assert extract_field_names({}) == set()
        assert extract_field_names(None) == set()  # type: ignore[arg-type]

    def test_get_response_codes(self) -> None:
        """get_response_codes extracts status codes."""
        operation = {
            "responses": {
                "200": {"description": "OK"},
                "404": {"description": "Not Found"},
            }
        }
        assert get_response_codes(operation) == {"200", "404"}

    def test_get_query_params(self) -> None:
        """get_query_params extracts query parameter names and types."""
        operation = {
            "parameters": [
                {"name": "cursor", "in": "query", "schema": {"type": "string"}},
                {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                {"name": "id", "in": "path", "schema": {"type": "string"}},
            ]
        }
        result = get_query_params(operation)
        assert result == {"cursor": "string", "limit": "integer"}
