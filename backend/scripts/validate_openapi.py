"""Validate hand-written OpenAPI YAML specs against FastAPI auto-generated schema.

Drift detection: ensures the YAML specs in shared/api-contracts/ match the
actual FastAPI endpoint definitions. Exits with code 0 if specs match,
code 1 if any differences are found.

Usage:
    python scripts/validate_openapi.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

# Add backend to path so we can import the FastAPI app
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# The /api/v1 prefix used in FastAPI route registration
API_PREFIX = "/api/v1"

# Paths to skip comparison for specific methods (SSE streaming cannot be modelled)
SSE_ENDPOINTS: set[tuple[str, str]] = {
    ("/api/v1/characters/{character_id}/messages", "post"),
}


def load_yaml_specs(contracts_dir: Path) -> dict[str, Any]:
    """Load and merge all YAML spec files, resolving $ref pointers manually."""
    root_path = contracts_dir / "ember-api.yaml"
    if not root_path.exists():
        print(f"ERROR: Root spec file not found: {root_path}")
        sys.exit(1)

    with open(root_path) as f:
        root = yaml.safe_load(f)

    # Load all path files and schema files
    paths: dict[str, Any] = {}
    for path_key, ref_obj in root.get("paths", {}).items():
        if "$ref" in ref_obj:
            ref_str = ref_obj["$ref"]
            file_part, fragment = ref_str.split("#", 1)
            file_path = contracts_dir / file_part
            with open(file_path) as f:
                path_data = yaml.safe_load(f)

            # Resolve the JSON pointer fragment (e.g., /~1health -> /health)
            pointer = fragment.lstrip("/")
            pointer = pointer.replace("~1", "/").replace("~0", "~")
            if pointer in path_data:
                paths[path_key] = path_data[pointer]
            else:
                print(f"WARNING: Could not resolve {ref_str} in {file_path}")
        else:
            paths[path_key] = ref_obj

    return paths


def get_fastapi_schema() -> dict[str, Any]:
    """Get the auto-generated OpenAPI schema from FastAPI."""
    from app.main import app  # noqa: E402

    return app.openapi()


def normalize_path(yaml_path: str) -> str:
    """Convert a YAML spec path to the FastAPI equivalent by adding the /api/v1 prefix."""
    return f"{API_PREFIX}{yaml_path}"


def extract_field_names(schema: dict[str, Any]) -> set[str]:
    """Extract property names from a JSON schema object."""
    if not schema:
        return set()
    if "properties" in schema:
        return set(schema["properties"].keys())
    # Handle allOf, anyOf, oneOf
    for combiner in ("allOf", "anyOf", "oneOf"):
        if combiner in schema:
            names: set[str] = set()
            for sub in schema[combiner]:
                names |= extract_field_names(sub)
            return names
    return set()


def extract_required_fields(schema: dict[str, Any]) -> set[str]:
    """Extract required field names from a JSON schema object."""
    if not schema:
        return set()
    return set(schema.get("required", []))


def resolve_ref(ref: str, full_schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve a $ref pointer within the FastAPI schema."""
    if not ref.startswith("#/"):
        return {}
    parts = ref[2:].split("/")
    current = full_schema
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return {}
    return current if isinstance(current, dict) else {}


def get_request_body_schema(
    operation: dict[str, Any], full_schema: dict[str, Any]
) -> dict[str, Any]:
    """Extract the request body schema from an operation, resolving $ref."""
    rb = operation.get("requestBody", {})
    if not rb:
        return {}
    content = rb.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    if "$ref" in schema:
        return resolve_ref(schema["$ref"], full_schema)
    return schema


def get_response_codes(operation: dict[str, Any]) -> set[str]:
    """Get the set of response status codes from an operation."""
    return set(operation.get("responses", {}).keys())


def get_query_params(operation: dict[str, Any]) -> dict[str, str]:
    """Get query parameter names and their types."""
    params = {}
    for param in operation.get("parameters", []):
        if param.get("in") == "query":
            schema = param.get("schema", {})
            param_type = schema.get("type", "unknown")
            params[param["name"]] = param_type
    return params


def get_path_params(operation: dict[str, Any]) -> set[str]:
    """Get path parameter names."""
    params = set()
    for param in operation.get("parameters", []):
        if param.get("in") == "path":
            params.add(param["name"])
    return params


def compare_schemas(
    yaml_paths: dict[str, Any],
    fastapi_schema: dict[str, Any],
) -> list[str]:
    """Compare YAML specs against FastAPI schema and return list of errors."""
    errors: list[str] = []
    fastapi_paths = fastapi_schema.get("paths", {})

    # Check every YAML path exists in FastAPI
    for yaml_path, yaml_ops in yaml_paths.items():
        fastapi_path = normalize_path(yaml_path)
        if fastapi_path not in fastapi_paths:
            errors.append(
                f"YAML spec references path {yaml_path} "
                f"(-> {fastapi_path}) not found in FastAPI"
            )
            continue

        fastapi_ops = fastapi_paths[fastapi_path]

        for method, yaml_op in yaml_ops.items():
            if method not in fastapi_ops:
                errors.append(
                    f"YAML spec references {method.upper()} {yaml_path} "
                    f"not found in FastAPI"
                )
                continue

            fastapi_op = fastapi_ops[method]
            endpoint_label = f"{method.upper()} {yaml_path}"

            # Skip response body comparison for SSE endpoints
            is_sse = (fastapi_path, method) in SSE_ENDPOINTS

            # Compare request body field names
            if not is_sse:
                yaml_rb = yaml_op.get("requestBody", {})
                fastapi_rb = fastapi_op.get("requestBody", {})

                yaml_has_body = bool(yaml_rb)
                fastapi_has_body = bool(fastapi_rb)

                if yaml_has_body != fastapi_has_body:
                    errors.append(
                        f"{endpoint_label}: request body mismatch -- "
                        f"YAML={'present' if yaml_has_body else 'absent'}, "
                        f"FastAPI={'present' if fastapi_has_body else 'absent'}"
                    )
                elif yaml_has_body and fastapi_has_body:
                    yaml_rb_schema = _extract_json_schema(yaml_rb)
                    fastapi_rb_schema = get_request_body_schema(
                        fastapi_op, fastapi_schema
                    )
                    yaml_fields = extract_field_names(yaml_rb_schema)
                    fastapi_fields = extract_field_names(fastapi_rb_schema)

                    if yaml_fields and fastapi_fields:
                        missing_in_yaml = fastapi_fields - yaml_fields
                        extra_in_yaml = yaml_fields - fastapi_fields
                        if missing_in_yaml:
                            errors.append(
                                f"{endpoint_label}: request body fields in FastAPI "
                                f"but missing from YAML: {sorted(missing_in_yaml)}"
                            )
                        if extra_in_yaml:
                            errors.append(
                                f"{endpoint_label}: request body fields in YAML "
                                f"but missing from FastAPI: {sorted(extra_in_yaml)}"
                            )

            # Compare response status codes
            yaml_codes = get_response_codes(yaml_op)
            fastapi_codes = get_response_codes(fastapi_op)

            # Tolerate extra 422 in FastAPI (auto-generated)
            fastapi_codes_for_compare = fastapi_codes.copy()
            if "422" in yaml_codes:
                pass  # both have it, fine
            else:
                fastapi_codes_for_compare.discard("422")

            missing_codes = fastapi_codes_for_compare - yaml_codes
            if missing_codes:
                errors.append(
                    f"{endpoint_label}: response codes in FastAPI but missing "
                    f"from YAML: {sorted(missing_codes)}"
                )

            # We don't flag codes in YAML but not in FastAPI for 401/429
            # since FastAPI doesn't auto-generate those but we document them.

            # Compare query parameters
            yaml_query = get_query_params(yaml_op)
            fastapi_query = get_query_params(fastapi_op)

            yaml_query_names = set(yaml_query.keys())
            fastapi_query_names = set(fastapi_query.keys())

            missing_query = fastapi_query_names - yaml_query_names
            extra_query = yaml_query_names - fastapi_query_names
            if missing_query:
                errors.append(
                    f"{endpoint_label}: query params in FastAPI but missing "
                    f"from YAML: {sorted(missing_query)}"
                )
            if extra_query:
                errors.append(
                    f"{endpoint_label}: query params in YAML but missing "
                    f"from FastAPI: {sorted(extra_query)}"
                )

            # Compare path parameters
            yaml_path_params = get_path_params(yaml_op)
            fastapi_path_params = get_path_params(fastapi_op)

            if yaml_path_params != fastapi_path_params:
                errors.append(
                    f"{endpoint_label}: path params mismatch -- "
                    f"YAML={sorted(yaml_path_params)}, "
                    f"FastAPI={sorted(fastapi_path_params)}"
                )

            # Compare response body field names (200/201 only, skip SSE)
            if not is_sse:
                for code in ("200", "201"):
                    if code in yaml_codes and code in fastapi_codes:
                        yaml_resp = yaml_op["responses"][code]
                        fastapi_resp = fastapi_op["responses"][code]

                        yaml_resp_schema = _extract_json_schema_from_response(yaml_resp)
                        fastapi_resp_schema = _extract_json_schema_from_response(
                            fastapi_resp
                        )

                        if "$ref" in fastapi_resp_schema:
                            fastapi_resp_schema = resolve_ref(
                                fastapi_resp_schema["$ref"], fastapi_schema
                            )

                        yaml_resp_fields = extract_field_names(yaml_resp_schema)
                        fastapi_resp_fields = extract_field_names(fastapi_resp_schema)

                        if yaml_resp_fields and fastapi_resp_fields:
                            missing = fastapi_resp_fields - yaml_resp_fields
                            extra = yaml_resp_fields - fastapi_resp_fields
                            if missing:
                                errors.append(
                                    f"{endpoint_label} [{code}]: response fields "
                                    f"in FastAPI but missing from YAML: {sorted(missing)}"
                                )
                            if extra:
                                errors.append(
                                    f"{endpoint_label} [{code}]: response fields "
                                    f"in YAML but missing from FastAPI: {sorted(extra)}"
                                )

    # Check every FastAPI path exists in YAML
    for fastapi_path, fastapi_ops in fastapi_paths.items():
        # Strip /api/v1 prefix to get the YAML path
        if not fastapi_path.startswith(API_PREFIX):
            continue
        yaml_path = fastapi_path[len(API_PREFIX):]

        # Skip test-only routes injected by the test suite
        if "/_test" in yaml_path:
            continue

        if yaml_path not in yaml_paths:
            errors.append(
                f"FastAPI endpoint {fastapi_path} not documented in YAML specs"
            )
            continue

        for method in fastapi_ops:
            if method not in yaml_paths[yaml_path]:
                errors.append(
                    f"FastAPI endpoint {method.upper()} {fastapi_path} "
                    f"not documented in YAML specs"
                )

    return errors


def _extract_json_schema(request_body: dict[str, Any]) -> dict[str, Any]:
    """Extract JSON schema from a request body object."""
    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    return json_content.get("schema", {})


def _extract_json_schema_from_response(response: dict[str, Any]) -> dict[str, Any]:
    """Extract JSON schema from a response object."""
    content = response.get("content", {})
    json_content = content.get("application/json", {})
    return json_content.get("schema", {})


def main() -> int:
    """Run the validation and return exit code."""
    contracts_dir = backend_dir.parent / "shared" / "api-contracts"

    print(f"Loading YAML specs from {contracts_dir}")
    yaml_paths = load_yaml_specs(contracts_dir)
    print(f"Found {len(yaml_paths)} paths in YAML specs")

    print("Loading FastAPI auto-generated schema")
    fastapi_schema = get_fastapi_schema()
    fastapi_paths = fastapi_schema.get("paths", {})
    print(f"Found {len(fastapi_paths)} paths in FastAPI schema")

    print("\nComparing specs...\n")
    errors = compare_schemas(yaml_paths, fastapi_schema)

    if errors:
        print(f"FAILED: {len(errors)} difference(s) found:\n")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        print()
        return 1

    print("OK: All YAML specs match the FastAPI schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
