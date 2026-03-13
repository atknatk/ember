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
        """The spec must document all endpoint+method combinations."""
        root = _load_root_spec()
        paths = _load_all_paths(root)

        count = 0
        for operations in paths.values():
            for method, op in operations.items():
                if isinstance(op, dict):
                    count += 1

        assert count == 24, f"Expected 24 endpoints, found {count}"


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
            "memories", "media", "notifications", "onboarding", "profile", "tts", "stt",
        }
        assert tag_names == expected, f"Missing tags: {expected - tag_names}"

    def test_servers_defined(self) -> None:
        """Root spec must define production and local development servers."""
        root = _load_root_spec()
        servers = root.get("servers", [])
        urls = {s["url"] for s in servers}
        assert "https://api.ember.com/api/v1" in urls, "Production server URL missing"
        assert "http://localhost:8000/api/v1" in urls, "Local dev server URL missing"

    def test_global_security_references_bearer_auth(self) -> None:
        """Global security must reference bearerAuth."""
        root = _load_root_spec()
        global_security = root.get("security", [])
        assert global_security, "Global security is not defined"
        scheme_names = set()
        for entry in global_security:
            scheme_names.update(entry.keys())
        assert "bearerAuth" in scheme_names, "Global security must reference bearerAuth"

    def test_bearer_auth_format_is_jwt(self) -> None:
        """bearerAuth security scheme must specify bearerFormat: JWT."""
        root = _load_root_spec()
        bearer = root.get("components", {}).get("securitySchemes", {}).get("bearerAuth", {})
        assert bearer.get("bearerFormat") == "JWT", (
            f"bearerAuth.bearerFormat expected 'JWT', got {bearer.get('bearerFormat')}"
        )


# ---------------------------------------------------------------------------
# Tests: operation IDs
# ---------------------------------------------------------------------------


class TestOperationIds:
    """All operationIds must be unique across the entire spec."""

    def test_operation_ids_are_unique(self) -> None:
        """No two operations may share the same operationId."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        seen: dict[str, str] = {}
        duplicates: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                op_id = operation.get("operationId")
                if not op_id:
                    continue
                label = f"{method.upper()} {path_key}"
                if op_id in seen:
                    duplicates.append(
                        f"'{op_id}' used by both {seen[op_id]} and {label}"
                    )
                else:
                    seen[op_id] = label

        assert not duplicates, (
            "Duplicate operationIds:\n"
            + "\n".join(f"  - {d}" for d in duplicates)
        )

    def test_all_operations_have_operation_id(self) -> None:
        """Every operation should have an operationId."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        missing: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                if not operation.get("operationId"):
                    missing.append(f"{method.upper()} {path_key}")

        assert not missing, (
            "Endpoints without operationId:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )


# ---------------------------------------------------------------------------
# Tests: endpoint tags
# ---------------------------------------------------------------------------


EXPECTED_ENDPOINT_TAGS: dict[tuple[str, str], str] = {
    ("get", "/health"): "health",
    ("post", "/auth/register"): "auth",
    ("post", "/auth/login"): "auth",
    ("post", "/auth/refresh"): "auth",
    ("get", "/characters"): "characters",
    ("post", "/characters"): "characters",
    ("put", "/characters/{character_id}"): "characters",
    ("delete", "/characters/{character_id}"): "characters",
    ("post", "/characters/{character_id}/messages"): "chat",
    ("get", "/characters/{character_id}/messages"): "chat",
    ("get", "/memories"): "memories",
    ("get", "/characters/{character_id}/memories"): "memories",
    ("delete", "/characters/{character_id}/memories"): "memories",
    ("delete", "/characters/{character_id}/memories/{memory_id}"): "memories",
    ("post", "/media/upload-url"): "media",
    ("post", "/onboarding/complete"): "onboarding",
    ("get", "/profile"): "profile",
    ("put", "/profile"): "profile",
    ("delete", "/profile/account"): "profile",
}


class TestEndpointTags:
    """Each endpoint must be tagged with the correct group."""

    def test_each_endpoint_has_correct_tag(self) -> None:
        """Every endpoint must carry its expected tag."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        errors: list[str] = []

        for (method, path_key), expected_tag in EXPECTED_ENDPOINT_TAGS.items():
            operations = paths.get(path_key, {})
            operation = operations.get(method)
            if not isinstance(operation, dict):
                errors.append(f"{method.upper()} {path_key}: operation not found")
                continue
            tags = operation.get("tags", [])
            if expected_tag not in tags:
                errors.append(
                    f"{method.upper()} {path_key}: expected tag '{expected_tag}', "
                    f"got {tags}"
                )

        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# Tests: 401 coverage for authenticated endpoints
# ---------------------------------------------------------------------------


class TestUnauthorizedCoverage:
    """All authenticated endpoints must document a 401 response."""

    PUBLIC_ENDPOINTS = {
        ("get", "/health"),
        ("post", "/auth/register"),
        ("post", "/auth/login"),
        ("post", "/auth/refresh"),
    }

    def test_authenticated_endpoints_document_401(self) -> None:
        """Every non-public endpoint must have a 401 response defined."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        missing: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                if (method, path_key) in self.PUBLIC_ENDPOINTS:
                    continue
                responses = operation.get("responses", {})
                if "401" not in responses:
                    missing.append(f"{method.upper()} {path_key}")

        assert not missing, (
            "Authenticated endpoints missing 401 response:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )


# ---------------------------------------------------------------------------
# Tests: 429 rate-limit coverage
# ---------------------------------------------------------------------------


class TestRateLimitCoverage:
    """All authenticated endpoints must document a 429 response with Retry-After header."""

    PUBLIC_ENDPOINTS = {
        ("get", "/health"),
        ("post", "/auth/register"),
        ("post", "/auth/login"),
        ("post", "/auth/refresh"),
    }

    def test_authenticated_endpoints_document_429(self) -> None:
        """Every non-public endpoint must have a 429 response defined."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        missing: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                if (method, path_key) in self.PUBLIC_ENDPOINTS:
                    continue
                responses = operation.get("responses", {})
                if "429" not in responses:
                    missing.append(f"{method.upper()} {path_key}")

        assert not missing, (
            "Authenticated endpoints missing 429 response:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_429_responses_include_retry_after_header(self) -> None:
        """All 429 responses must define a Retry-After response header."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        missing: list[str] = []

        for path_key, operations in paths.items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                if (method, path_key) in self.PUBLIC_ENDPOINTS:
                    continue
                responses = operation.get("responses", {})
                resp_429 = responses.get("429", {})
                if not resp_429:
                    continue
                headers = resp_429.get("headers", {})
                if "Retry-After" not in headers:
                    missing.append(f"{method.upper()} {path_key}")

        assert not missing, (
            "429 responses missing Retry-After header:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )


# ---------------------------------------------------------------------------
# Tests: path parameter format
# ---------------------------------------------------------------------------


class TestPathParameters:
    """Path parameters representing UUIDs must declare format: uuid."""

    # Endpoints that have character_id in path (should be uuid format)
    UUID_PATH_PARAMS = {
        "/characters/{character_id}",
        "/characters/{character_id}/messages",
        "/characters/{character_id}/memories",
        "/characters/{character_id}/memories/{memory_id}",
    }

    def test_character_id_path_params_have_uuid_format(self) -> None:
        """character_id path parameters must have format: uuid."""
        root = _load_root_spec()
        paths = _load_all_paths(root)
        errors: list[str] = []

        for path_key in self.UUID_PATH_PARAMS:
            operations = paths.get(path_key, {})
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                for param in operation.get("parameters", []):
                    if (
                        param.get("in") == "path"
                        and param.get("name") == "character_id"
                    ):
                        schema = param.get("schema", {})
                        if schema.get("format") != "uuid":
                            errors.append(
                                f"{method.upper()} {path_key}: character_id path "
                                f"param missing format: uuid (got {schema.get('format')})"
                            )

        assert not errors, "\n".join(errors)


# ---------------------------------------------------------------------------
# Tests: schema field completeness
# ---------------------------------------------------------------------------


SCHEMAS_DIR = CONTRACTS_DIR / "schemas"


def _load_schema(schema_file: str) -> dict:
    """Load a schema YAML file from the schemas directory."""
    return _load_yaml(SCHEMAS_DIR / schema_file)


class TestSchemaFieldCompleteness:
    """Verify that each schema contains all fields required by the spec."""

    def test_register_request_fields(self) -> None:
        """RegisterRequest must have email, password, and name fields."""
        schema = _load_schema("auth.yaml")["RegisterRequest"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"email", "password", "name"} <= props
        assert {"email", "password", "name"} == required

    def test_login_request_fields(self) -> None:
        """LoginRequest must have email and password fields."""
        schema = _load_schema("auth.yaml")["LoginRequest"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"email", "password"} <= props
        assert {"email", "password"} == required

    def test_auth_response_fields(self) -> None:
        """AuthResponse must have token, refresh_token, and user fields."""
        schema = _load_schema("auth.yaml")["AuthResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"token", "refresh_token", "user"} <= props
        assert {"token", "refresh_token", "user"} == required

    def test_user_response_fields(self) -> None:
        """UserResponse must have all required user fields."""
        schema = _load_schema("auth.yaml")["UserResponse"]
        required = set(schema.get("required", []))
        expected_required = {
            "id", "email", "name", "onboarding_completed",
            "subscription_tier", "preferred_language", "timezone", "created_at",
        }
        assert expected_required == required

    def test_refresh_response_fields(self) -> None:
        """RefreshResponse must have token field."""
        schema = _load_schema("auth.yaml")["RefreshResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert "token" in props
        assert "token" in required

    def test_send_message_request_fields(self) -> None:
        """SendMessageRequest must have content (required) and media_url (optional)."""
        schema = _load_schema("chat.yaml")["SendMessageRequest"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"content", "media_url"} <= props
        assert required == {"content"}

    def test_message_item_fields(self) -> None:
        """MessageItem must have id, role, content, media_url, metadata, created_at."""
        schema = _load_schema("chat.yaml")["MessageItem"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"id", "role", "content", "media_url", "metadata", "created_at"} <= props
        assert {"id", "role", "content", "created_at"} == required

    def test_message_list_response_fields(self) -> None:
        """MessageListResponse must have items, next_cursor, has_more."""
        schema = _load_schema("chat.yaml")["MessageListResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"items", "next_cursor", "has_more"} <= props
        assert {"items", "next_cursor", "has_more"} == required

    def test_memory_item_fields(self) -> None:
        """MemoryItem must have id and memory fields."""
        schema = _load_schema("memory.yaml")["MemoryItem"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"id", "memory", "created_at"} <= props
        assert {"id", "memory"} == required

    def test_memory_list_response_fields(self) -> None:
        """MemoryListResponse must have memories field (required)."""
        schema = _load_schema("memory.yaml")["MemoryListResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert "memories" in props
        assert "memories" in required

    def test_upload_url_request_fields(self) -> None:
        """UploadUrlRequest must have filename, content_type, type fields."""
        schema = _load_schema("media.yaml")["UploadUrlRequest"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"filename", "content_type", "type"} <= props
        assert {"filename", "content_type", "type"} == required

    def test_upload_url_response_fields(self) -> None:
        """UploadUrlResponse must have upload_url and file_url."""
        schema = _load_schema("media.yaml")["UploadUrlResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"upload_url", "file_url"} == props
        assert {"upload_url", "file_url"} == required

    def test_onboarding_answer_fields(self) -> None:
        """OnboardingAnswer must have question_key and answer fields."""
        schema = _load_schema("onboarding.yaml")["OnboardingAnswer"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"question_key", "answer"} == props
        assert {"question_key", "answer"} == required

    def test_onboarding_request_fields(self) -> None:
        """OnboardingRequest must have answers field (required, exactly 7 items)."""
        schema = _load_schema("onboarding.yaml")["OnboardingRequest"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert "answers" in props
        assert "answers" in required
        answers_schema = schema["properties"]["answers"]
        assert answers_schema.get("minItems") == 7
        assert answers_schema.get("maxItems") == 7

    def test_onboarding_response_fields(self) -> None:
        """OnboardingResponse must have onboarding_completed and memories_seeded."""
        schema = _load_schema("onboarding.yaml")["OnboardingResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"onboarding_completed", "memories_seeded"} == props
        assert {"onboarding_completed", "memories_seeded"} == required

    def test_profile_response_fields(self) -> None:
        """ProfileResponse must include all profile fields per spec."""
        schema = _load_schema("profile.yaml")["ProfileResponse"]
        props = set(schema.get("properties", {}).keys())
        expected_props = {
            "id", "email", "name", "timezone", "avatar_url",
            "preferred_language", "onboarding_completed", "subscription_tier",
            "subscription_expires_at", "created_at",
        }
        assert expected_props <= props

    def test_profile_update_request_fields(self) -> None:
        """ProfileUpdateRequest must have name, timezone, avatar_url, preferred_language."""
        schema = _load_schema("profile.yaml")["ProfileUpdateRequest"]
        props = set(schema.get("properties", {}).keys())
        assert {"name", "timezone", "avatar_url", "preferred_language"} <= props

    def test_account_delete_request_fields(self) -> None:
        """AccountDeleteRequest must have confirmation field (required)."""
        schema = _load_schema("profile.yaml")["AccountDeleteRequest"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert "confirmation" in props
        assert "confirmation" in required

    def test_character_list_item_fields(self) -> None:
        """CharacterListItem must have all required fields per spec."""
        schema = _load_schema("character.yaml")["CharacterListItem"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"id", "name", "template", "avatar_style", "is_default", "created_at"} <= required
        assert {"description", "last_message_at"} <= props

    def test_character_detail_fields(self) -> None:
        """CharacterDetail must include system_prompt."""
        schema = _load_schema("character.yaml")["CharacterDetail"]
        required = set(schema.get("required", []))
        assert "system_prompt" in required

    def test_health_response_fields(self) -> None:
        """HealthResponse must have status and version (required), plus optional deps."""
        schema = _load_schema("health.yaml")["HealthResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"status", "version"} == required
        assert {"dependencies", "circuit_breaker"} <= props

    def test_error_response_has_detail_field(self) -> None:
        """ErrorResponse must have a required detail field."""
        schema = _load_schema("common.yaml")["ErrorResponse"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert "detail" in props
        assert "detail" in required

    def test_error_response_detail_is_oneof_string_or_array(self) -> None:
        """ErrorResponse.detail must be oneOf string | array (for 422 vs HTTPException)."""
        schema = _load_schema("common.yaml")["ErrorResponse"]
        detail_schema = schema["properties"]["detail"]
        one_of = detail_schema.get("oneOf", [])
        assert len(one_of) == 2, f"Expected 2 variants in oneOf, got {len(one_of)}"
        types = {v.get("type") for v in one_of}
        assert "string" in types
        assert "array" in types

    def test_rate_limit_error_has_detail_field(self) -> None:
        """RateLimitError must have a required detail field."""
        schema = _load_schema("common.yaml")["RateLimitError"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert "detail" in props
        assert "detail" in required


# ---------------------------------------------------------------------------
# Tests: SSE event schema completeness
# ---------------------------------------------------------------------------


class TestSSEEventSchemas:
    """SSE event schemas must define all fields per spec."""

    def test_chunk_event_fields(self) -> None:
        """ChunkEvent must have type (const: chunk) and content fields."""
        schema = _load_schema("chat.yaml")["ChunkEvent"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"type", "content"} == props
        assert {"type", "content"} == required
        assert schema["properties"]["type"].get("const") == "chunk"

    def test_action_event_fields(self) -> None:
        """ActionEvent must have type (const: action), action, and payload fields."""
        schema = _load_schema("chat.yaml")["ActionEvent"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"type", "action", "payload"} == props
        assert {"type", "action", "payload"} == required
        assert schema["properties"]["type"].get("const") == "action"

    def test_done_event_fields(self) -> None:
        """DoneEvent must have type (const: done) and message_id fields."""
        schema = _load_schema("chat.yaml")["DoneEvent"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"type", "message_id"} == props
        assert {"type", "message_id"} == required
        assert schema["properties"]["type"].get("const") == "done"

    def test_error_event_fields(self) -> None:
        """ErrorEvent must have type (const: error) and message fields."""
        schema = _load_schema("chat.yaml")["ErrorEvent"]
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        assert {"type", "message"} == props
        assert {"type", "message"} == required
        assert schema["properties"]["type"].get("const") == "error"


# ---------------------------------------------------------------------------
# Tests: key schema constraints match spec
# ---------------------------------------------------------------------------


class TestSchemaConstraints:
    """Field constraints (minLength, maxLength, enum) must match spec."""

    def test_register_request_password_min_length(self) -> None:
        """RegisterRequest.password must have minLength: 8."""
        schema = _load_schema("auth.yaml")["RegisterRequest"]
        pw = schema["properties"]["password"]
        assert pw.get("minLength") == 8

    def test_register_request_name_max_length(self) -> None:
        """RegisterRequest.name must have maxLength: 100."""
        schema = _load_schema("auth.yaml")["RegisterRequest"]
        name = schema["properties"]["name"]
        assert name.get("maxLength") == 100

    def test_register_request_email_format(self) -> None:
        """RegisterRequest.email must have format: email."""
        schema = _load_schema("auth.yaml")["RegisterRequest"]
        email = schema["properties"]["email"]
        assert email.get("format") == "email"

    def test_send_message_content_max_length(self) -> None:
        """SendMessageRequest.content must have maxLength: 4000."""
        schema = _load_schema("chat.yaml")["SendMessageRequest"]
        content = schema["properties"]["content"]
        assert content.get("maxLength") == 4000
        assert content.get("minLength") == 1

    def test_onboarding_answer_enum_values(self) -> None:
        """OnboardingAnswer.question_key must enumerate exactly the 7 expected keys."""
        schema = _load_schema("onboarding.yaml")["OnboardingAnswer"]
        enum_values = set(schema["properties"]["question_key"]["enum"])
        expected = {
            "preferred_name", "occupation", "daily_rhythm", "health_goal",
            "stress_management", "sleep_schedule", "communication_style",
        }
        assert enum_values == expected

    def test_onboarding_answer_max_length(self) -> None:
        """OnboardingAnswer.answer must have maxLength: 500."""
        schema = _load_schema("onboarding.yaml")["OnboardingAnswer"]
        answer = schema["properties"]["answer"]
        assert answer.get("maxLength") == 500
        assert answer.get("minLength") == 1

    def test_upload_url_request_type_enum(self) -> None:
        """UploadUrlRequest.type must enumerate photo, audio, tts."""
        schema = _load_schema("media.yaml")["UploadUrlRequest"]
        enum_values = set(schema["properties"]["type"]["enum"])
        assert enum_values == {"photo", "audio", "tts"}

    def test_upload_url_request_filename_constraints(self) -> None:
        """UploadUrlRequest.filename must have minLength: 1, maxLength: 255."""
        schema = _load_schema("media.yaml")["UploadUrlRequest"]
        filename = schema["properties"]["filename"]
        assert filename.get("minLength") == 1
        assert filename.get("maxLength") == 255

    def test_message_item_role_enum(self) -> None:
        """MessageItem.role must enumerate user and assistant."""
        schema = _load_schema("chat.yaml")["MessageItem"]
        role = schema["properties"]["role"]
        assert set(role.get("enum", [])) == {"user", "assistant"}

    def test_character_system_prompt_max_length(self) -> None:
        """UpdateCharacterRequest.system_prompt must have maxLength: 10000."""
        schema = _load_schema("character.yaml")["UpdateCharacterRequest"]
        system_prompt_schema = schema["properties"]["system_prompt"]
        # system_prompt is oneOf: [{type: string, ...}, {type: null}]
        one_of = system_prompt_schema.get("oneOf", [])
        string_variant = next((v for v in one_of if v.get("type") == "string"), None)
        assert string_variant is not None, "system_prompt must have a string variant"
        assert string_variant.get("maxLength") == 10000


# ---------------------------------------------------------------------------
# Tests: CI workflow
# ---------------------------------------------------------------------------


class TestCIWorkflow:
    """The backend CI workflow must include the OpenAPI validation step."""

    CI_WORKFLOW_PATH = (
        Path(__file__).resolve().parent.parent.parent
        / ".github" / "workflows" / "backend-ci.yml"
    )

    def test_ci_workflow_exists(self) -> None:
        """The backend-ci.yml file must exist."""
        assert self.CI_WORKFLOW_PATH.exists(), (
            f"CI workflow not found at {self.CI_WORKFLOW_PATH}"
        )

    def test_ci_workflow_has_validate_openapi_step(self) -> None:
        """The CI workflow must contain a step that runs validate_openapi.py."""
        content = self.CI_WORKFLOW_PATH.read_text()
        assert "validate_openapi.py" in content, (
            "CI workflow does not include validate_openapi.py step"
        )

    def test_ci_workflow_validate_step_has_name(self) -> None:
        """The validate step must have a descriptive name."""
        workflow = _load_yaml(self.CI_WORKFLOW_PATH)
        jobs = workflow.get("jobs", {})
        found = False
        for job in jobs.values():
            for step in job.get("steps", []):
                name = step.get("name", "")
                run = step.get("run", "")
                if "validate_openapi.py" in run and name:
                    found = True
                    break
        assert found, "validate_openapi.py step must have a 'name' field"
