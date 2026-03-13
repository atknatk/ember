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
    extract_required_fields,
    get_fastapi_schema,
    get_path_params,
    get_query_params,
    get_request_body_schema,
    get_response_codes,
    load_yaml_specs,
    normalize_path,
    resolve_ref,
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

    def test_get_query_params_empty(self) -> None:
        """get_query_params returns empty dict when no parameters."""
        assert get_query_params({}) == {}
        assert get_query_params({"parameters": []}) == {}

    def test_get_query_params_no_schema_type(self) -> None:
        """get_query_params returns 'unknown' for params without explicit type."""
        operation = {
            "parameters": [
                {"name": "foo", "in": "query", "schema": {}},
            ]
        }
        result = get_query_params(operation)
        assert result == {"foo": "unknown"}

    def test_extract_required_fields_with_required_list(self) -> None:
        """extract_required_fields returns required field names from schema."""
        schema = {
            "type": "object",
            "required": ["email", "password"],
            "properties": {
                "email": {"type": "string"},
                "password": {"type": "string"},
                "name": {"type": "string"},
            },
        }
        assert extract_required_fields(schema) == {"email", "password"}

    def test_extract_required_fields_empty_schema(self) -> None:
        """extract_required_fields returns empty set for missing required list."""
        assert extract_required_fields({}) == set()
        assert extract_required_fields(None) == set()  # type: ignore[arg-type]

    def test_get_path_params(self) -> None:
        """get_path_params returns path parameter names only."""
        operation = {
            "parameters": [
                {"name": "character_id", "in": "path", "schema": {"type": "string"}},
                {"name": "limit", "in": "query", "schema": {"type": "integer"}},
            ]
        }
        result = get_path_params(operation)
        assert result == {"character_id"}

    def test_get_path_params_empty(self) -> None:
        """get_path_params returns empty set when no path params."""
        assert get_path_params({}) == set()
        assert get_path_params({"parameters": []}) == set()

    def test_resolve_ref_valid(self) -> None:
        """resolve_ref returns the nested dict at the given JSON pointer."""
        full_schema = {
            "components": {
                "schemas": {
                    "Foo": {"type": "object", "properties": {"bar": {"type": "string"}}}
                }
            }
        }
        result = resolve_ref("#/components/schemas/Foo", full_schema)
        assert result == {"type": "object", "properties": {"bar": {"type": "string"}}}

    def test_resolve_ref_missing_path_returns_empty(self) -> None:
        """resolve_ref returns empty dict when path does not exist."""
        result = resolve_ref("#/components/schemas/DoesNotExist", {"components": {}})
        assert result == {}

    def test_resolve_ref_non_internal_ref_returns_empty(self) -> None:
        """resolve_ref returns empty dict for non-internal refs (not starting with #/)."""
        result = resolve_ref("../schemas/auth.yaml#/RegisterRequest", {})
        assert result == {}

    def test_get_response_codes_empty(self) -> None:
        """get_response_codes returns empty set for operation with no responses."""
        assert get_response_codes({}) == set()
        assert get_response_codes({"responses": {}}) == set()

    def test_get_request_body_schema_empty_operation(self) -> None:
        """get_request_body_schema returns empty dict when operation has no requestBody."""
        result = get_request_body_schema({}, {})
        assert result == {}

    def test_get_request_body_schema_with_direct_schema(self) -> None:
        """get_request_body_schema returns the inline schema from application/json."""
        operation = {
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"properties": {"field": {"type": "string"}}}
                    }
                }
            }
        }
        result = get_request_body_schema(operation, {})
        assert result == {"properties": {"field": {"type": "string"}}}

    def test_get_request_body_schema_resolves_ref(self) -> None:
        """get_request_body_schema resolves $ref to the component schema."""
        full_schema = {
            "components": {
                "schemas": {
                    "MyRequest": {
                        "properties": {"name": {"type": "string"}}
                    }
                }
            }
        }
        operation = {
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/MyRequest"}
                    }
                }
            }
        }
        result = get_request_body_schema(operation, full_schema)
        assert result == {"properties": {"name": {"type": "string"}}}

    def test_extract_field_names_with_anyof_combiner(self) -> None:
        """extract_field_names unions fields from all anyOf branches."""
        schema = {
            "anyOf": [
                {"properties": {"foo": {"type": "string"}}},
                {"properties": {"bar": {"type": "integer"}}},
            ]
        }
        result = extract_field_names(schema)
        assert result == {"foo", "bar"}

    def test_extract_field_names_with_allof_combiner(self) -> None:
        """extract_field_names unions fields from all allOf branches."""
        schema = {
            "allOf": [
                {"properties": {"alpha": {"type": "string"}}},
                {"properties": {"beta": {"type": "integer"}}},
            ]
        }
        result = extract_field_names(schema)
        assert result == {"alpha", "beta"}

    def test_extract_field_names_with_oneof_combiner(self) -> None:
        """extract_field_names unions fields from all oneOf branches."""
        schema = {
            "oneOf": [
                {"properties": {"x": {"type": "string"}}},
                {"type": "null"},
            ]
        }
        result = extract_field_names(schema)
        assert result == {"x"}


# ---------------------------------------------------------------------------
# Tests: drift detection (compare_schemas)
# ---------------------------------------------------------------------------


class TestDriftDetection:
    """compare_schemas must detect spec drift between YAML and FastAPI schemas."""

    def _make_fastapi_schema(self, paths: dict) -> dict:
        """Build a minimal FastAPI schema dict around the given paths."""
        return {"paths": paths}

    def test_yaml_path_not_in_fastapi_returns_error(self) -> None:
        """An error is returned when a YAML path has no matching FastAPI path."""
        yaml_paths = {"/nonexistent": {"get": {"responses": {"200": {}}}}}
        fastapi_schema = self._make_fastapi_schema({})
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("nonexistent" in e for e in errors)

    def test_yaml_method_not_in_fastapi_returns_error(self) -> None:
        """An error is returned when a YAML method has no matching FastAPI method."""
        yaml_paths = {"/health": {"delete": {"responses": {"204": {}}}}}
        fastapi_schema = self._make_fastapi_schema(
            {"/api/v1/health": {"get": {"responses": {"200": {}}}}}
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("DELETE /health" in e for e in errors)

    def test_fastapi_path_not_in_yaml_returns_error(self) -> None:
        """An error is returned when a FastAPI path is not in the YAML specs."""
        yaml_paths = {}
        fastapi_schema = self._make_fastapi_schema(
            {"/api/v1/undocumented": {"get": {"responses": {"200": {}}}}}
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("undocumented" in e for e in errors)

    def test_fastapi_method_not_in_yaml_returns_error(self) -> None:
        """An error is returned when a FastAPI method is missing from YAML."""
        yaml_paths = {"/health": {"get": {"responses": {"200": {}}}}}
        fastapi_schema = self._make_fastapi_schema(
            {"/api/v1/health": {"get": {}, "post": {}}}
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("POST" in e and "health" in e for e in errors)

    def test_request_body_field_missing_in_yaml_returns_error(self) -> None:
        """An error is returned when a FastAPI request body field is missing from YAML."""
        yaml_paths = {
            "/test": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {"email": {"type": "string"}},
                                }
                            }
                        }
                    },
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {
                                            "email": {"type": "string"},
                                            "password": {"type": "string"},
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {"200": {}},
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("request body" in e.lower() and "password" in e for e in errors)

    def test_extra_yaml_request_body_field_returns_error(self) -> None:
        """An error is returned when YAML documents a field not in FastAPI."""
        yaml_paths = {
            "/test": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "email": {"type": "string"},
                                        "ghost_field": {"type": "string"},
                                    }
                                }
                            }
                        }
                    },
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {"email": {"type": "string"}}
                                    }
                                }
                            }
                        },
                        "responses": {"200": {}},
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("ghost_field" in e for e in errors)

    def test_missing_response_code_in_yaml_returns_error(self) -> None:
        """An error is returned when FastAPI returns a code not in YAML (not 422)."""
        yaml_paths = {
            "/test": {
                "get": {
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "get": {
                        "responses": {
                            "200": {},
                            "400": {"description": "Bad request"},
                        }
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("response code" in e.lower() and "400" in e for e in errors)

    def test_extra_422_in_fastapi_is_tolerated_when_yaml_omits_it(self) -> None:
        """Auto-generated 422 in FastAPI is not flagged when YAML omits it."""
        yaml_paths = {
            "/test": {
                "post": {
                    "requestBody": {},
                    "responses": {"201": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "post": {
                        "requestBody": {},
                        "responses": {
                            "201": {},
                            "422": {"description": "Validation Error"},
                        },
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        response_code_errors = [e for e in errors if "response code" in e.lower()]
        assert not response_code_errors, (
            "422 should be tolerated but got errors: "
            + ", ".join(response_code_errors)
        )

    def test_test_only_routes_skipped_in_fastapi_check(self) -> None:
        """FastAPI routes containing /_test are skipped during comparison."""
        yaml_paths = {}
        fastapi_schema = self._make_fastapi_schema(
            {"/api/v1/_test_protected": {"get": {}}}
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        # Should not flag the _test route
        assert not any("_test" in e for e in errors)

    def test_query_param_missing_in_yaml_returns_error(self) -> None:
        """An error is returned when FastAPI has a query param not in YAML."""
        yaml_paths = {
            "/test": {
                "get": {
                    "parameters": [],
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "get": {
                        "parameters": [
                            {"name": "limit", "in": "query", "schema": {"type": "integer"}}
                        ],
                        "responses": {"200": {}},
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("query param" in e.lower() and "limit" in e for e in errors)

    def test_extra_yaml_query_param_returns_error(self) -> None:
        """An error is returned when YAML has a query param not in FastAPI."""
        yaml_paths = {
            "/test": {
                "get": {
                    "parameters": [
                        {"name": "ghost_param", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {"/api/v1/test": {"get": {"parameters": [], "responses": {"200": {}}}}}
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("query param" in e.lower() and "ghost_param" in e for e in errors)

    def test_path_param_mismatch_returns_error(self) -> None:
        """An error is returned when path parameter names differ."""
        yaml_paths = {
            "/items/{item_id}": {
                "get": {
                    "parameters": [
                        {"name": "item_id", "in": "path", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/items/{item_id}": {
                    "get": {
                        "parameters": [
                            {"name": "wrong_id", "in": "path", "schema": {"type": "string"}}
                        ],
                        "responses": {"200": {}},
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("path param" in e.lower() for e in errors)

    def test_no_errors_when_schemas_match(self) -> None:
        """compare_schemas returns no errors when YAML and FastAPI are in sync."""
        yaml_paths = {
            "/health": {
                "get": {
                    "parameters": [
                        {
                            "name": "check_dependencies",
                            "in": "query",
                            "schema": {"type": "boolean"},
                        }
                    ],
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/health": {
                    "get": {
                        "parameters": [
                            {
                                "name": "check_dependencies",
                                "in": "query",
                                "schema": {"type": "boolean"},
                            }
                        ],
                        "responses": {"200": {}},
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert errors == []

    def test_yaml_has_body_but_fastapi_does_not_returns_error(self) -> None:
        """An error is returned when YAML has a request body but FastAPI does not."""
        yaml_paths = {
            "/test": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"properties": {"field": {"type": "string"}}}
                            }
                        }
                    },
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {"/api/v1/test": {"post": {"responses": {"200": {}}}}}
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("request body" in e.lower() for e in errors)

    def test_fastapi_has_body_but_yaml_does_not_returns_error(self) -> None:
        """An error is returned when FastAPI has a request body but YAML does not."""
        yaml_paths = {
            "/test": {
                "post": {
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {"field": {"type": "string"}}
                                    }
                                }
                            }
                        },
                        "responses": {"200": {}},
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any("request body" in e.lower() for e in errors)

    def test_response_body_field_missing_in_yaml_returns_error(self) -> None:
        """An error is returned when a FastAPI 200 response field is missing from YAML."""
        yaml_paths = {
            "/test": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {"name": {"type": "string"}}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "properties": {
                                                "name": {"type": "string"},
                                                "secret_field": {"type": "string"},
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any(
            "response fields" in e.lower() and "secret_field" in e for e in errors
        )

    def test_extra_yaml_response_body_field_returns_error(self) -> None:
        """An error is returned when YAML documents a response field not in FastAPI."""
        yaml_paths = {
            "/test": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {
                                            "name": {"type": "string"},
                                            "phantom_field": {"type": "string"},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "properties": {"name": {"type": "string"}}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        assert any(
            "response fields" in e.lower() and "phantom_field" in e for e in errors
        )

    def test_fastapi_paths_without_api_prefix_are_skipped(self) -> None:
        """FastAPI paths not under /api/v1 are silently ignored."""
        yaml_paths = {}
        fastapi_schema = self._make_fastapi_schema(
            {"/openapi.json": {"get": {}}, "/docs": {"get": {}}}
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        # No errors about /openapi.json or /docs
        assert not any("/openapi.json" in e or "/docs" in e for e in errors)

    def test_sse_endpoint_request_body_skipped(self) -> None:
        """Response body comparison is skipped for SSE endpoints."""
        # The SSE endpoint at POST /characters/{character_id}/messages should not
        # flag response body mismatches since FastAPI returns StreamingResponse.
        yaml_paths = {
            "/characters/{character_id}/messages": {
                "post": {
                    "parameters": [
                        {
                            "name": "character_id",
                            "in": "path",
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {"content": {"type": "string"}}
                                }
                            }
                        }
                    },
                    "responses": {"200": {}},
                }
            }
        }
        fastapi_schema = self._make_fastapi_schema(
            {
                "/api/v1/characters/{character_id}/messages": {
                    "post": {
                        "parameters": [
                            {
                                "name": "character_id",
                                "in": "path",
                                "schema": {"type": "string"},
                            }
                        ],
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {"content": {"type": "string"}}
                                    }
                                }
                            }
                        },
                        # No response schema (StreamingResponse)
                        "responses": {"200": {}},
                    }
                }
            }
        )
        errors = compare_schemas(yaml_paths, fastapi_schema)
        # Response body mismatch errors should not appear for the SSE endpoint
        response_body_errors = [e for e in errors if "response fields" in e.lower()]
        assert not response_body_errors


# ---------------------------------------------------------------------------
# Tests: load_yaml_specs error handling
# ---------------------------------------------------------------------------


class TestLoadYamlSpecs:
    """load_yaml_specs must handle missing files gracefully."""

    def test_missing_root_spec_exits(self, tmp_path: Path) -> None:
        """load_yaml_specs calls sys.exit when root spec is not found."""
        import pytest

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(SystemExit) as exc_info:
            load_yaml_specs(empty_dir)
        assert exc_info.value.code == 1

    def test_valid_contracts_dir_loads_paths(self) -> None:
        """load_yaml_specs loads all path keys from the real contracts directory.

        Note: 18 path keys cover endpoint+method combinations
        (some paths like /characters have both GET and POST operations).
        """
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)
        assert len(yaml_paths) == 18, (
            f"Expected 18 path keys from YAML specs, got {len(yaml_paths)}"
        )

    def test_unresolvable_pointer_prints_warning_and_skips(
        self, tmp_path: Path, capsys
    ) -> None:
        """load_yaml_specs prints a WARNING and skips refs with unresolvable pointers."""
        import yaml

        # Build a minimal contracts dir with a root spec referencing a bad pointer
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        paths_dir = contracts_dir / "paths"
        paths_dir.mkdir()

        # Write a paths file that exists but lacks the referenced pointer
        path_data = {"/existing": {"get": {"responses": {"200": {}}}}}
        with open(paths_dir / "fake.yaml", "w") as f:
            yaml.dump(path_data, f)

        # Root spec references a pointer that does NOT exist in the file
        root_data = {
            "openapi": "3.1.0",
            "paths": {
                "/broken": {"$ref": "paths/fake.yaml#/~1does~1not~1exist"}
            },
        }
        with open(contracts_dir / "ember-api.yaml", "w") as f:
            yaml.dump(root_data, f)

        yaml_paths = load_yaml_specs(contracts_dir)
        captured = capsys.readouterr()

        # The broken path is skipped (not included in returned dict)
        assert "/broken" not in yaml_paths
        # A warning is printed
        assert "WARNING" in captured.out

    def test_inline_path_without_ref_is_loaded(self, tmp_path: Path) -> None:
        """load_yaml_specs handles paths defined inline (no $ref) in the root spec."""
        import yaml

        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()

        # Root spec with a path defined inline (not using $ref)
        inline_op = {
            "get": {
                "description": "Inline endpoint",
                "responses": {"200": {"description": "OK"}},
            }
        }
        root_data = {
            "openapi": "3.1.0",
            "paths": {"/inline": inline_op},
        }
        with open(contracts_dir / "ember-api.yaml", "w") as f:
            yaml.dump(root_data, f)

        yaml_paths = load_yaml_specs(contracts_dir)
        assert "/inline" in yaml_paths
        assert "get" in yaml_paths["/inline"]

    def test_loaded_paths_include_all_endpoint_groups(self) -> None:
        """load_yaml_specs returns paths from all endpoint groups."""
        contracts_dir = backend_dir.parent / "shared" / "api-contracts"
        yaml_paths = load_yaml_specs(contracts_dir)

        # Spot-check one path from each group
        expected_paths = [
            "/health",
            "/auth/register",
            "/characters",
            "/characters/{character_id}/messages",
            "/memories",
            "/media/upload-url",
            "/onboarding/complete",
            "/profile",
            "/profile/account",
        ]
        missing = [p for p in expected_paths if p not in yaml_paths]
        assert not missing, f"Paths not loaded: {missing}"
