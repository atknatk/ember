# Architect Handoff: Auth Endpoints

**Date**: 2026-02-23
**Agent**: architect
**Status**: COMPLETE
**Feature ID**: P01-04
**GitHub Issue**: #6
**Layer**: backend

---

## What Was Designed

Three public authentication endpoints for the Ember backend: POST /api/v1/auth/register (Cognito signup + profiles row + Mem0 user identifier assignment + default "General Friend" character creation + auto-conversation), POST /api/v1/auth/login (Cognito USER_PASSWORD_AUTH authentication, profile lookup, return tokens + user), and POST /api/v1/auth/refresh (Cognito REFRESH_TOKEN_AUTH, return new ID token). All endpoints use Pydantic v2 request/response schemas. The register flow bootstraps the user's entire environment in a single database transaction.

## Spec Location

`shared/feature-specs/auth-endpoints.md`

## Key Decisions

- **Auto-confirm users via `admin_confirm_sign_up`**: During MVP/early development, email verification adds friction without critical value. Auto-confirming allows immediate login after registration. In production, this can be replaced by a Cognito pre-sign-up Lambda trigger or a proper email verification flow in Phase 2.
- **`USER_PASSWORD_AUTH` flow (not `ALLOW_USER_SRP_AUTH`)**: The backend communicates with Cognito over HTTPS on AWS-internal network. SRP is for client-side SDKs where the password must never leave the device. `USER_PASSWORD_AUTH` is sufficient and simpler.
- **`asyncio.to_thread()` for all boto3 calls**: boto3 is synchronous. Wrapping with `asyncio.to_thread()` prevents blocking the FastAPI event loop. This is a standard-library solution preferred over `aioboto3` (third-party, limited maintenance).
- **Default character named "Ember"**: The default "General Friend" character uses template `companion` and is named after the app itself. Users can rename it later.
- **`mem0_user_id` format is `"user_{sub}"`**: The `"user_"` prefix distinguishes Mem0 user identifiers from agent IDs and memory IDs. No explicit Mem0 API call is made during registration -- Mem0 creates user records lazily on first `add()` or `search()` call.
- **Single database transaction for Profile + Character + Conversation**: Ensures atomicity. Either the entire user setup succeeds or nothing is committed. Without this, a user could end up with a profile but no character to talk to.
- **Generic "Invalid email or password" on login failure**: Both wrong-email and wrong-password cases return the same message to prevent email enumeration attacks.
- **Refresh does not return a new refresh_token**: This is Cognito's behavior with `REFRESH_TOKEN_AUTH` -- it returns a new ID token but reuses the existing refresh token (valid for 30 days).
- **Idempotent registration for Cognito-DB split-brain**: If Cognito signup succeeds but DB insertion fails, the next registration attempt with the same email catches `UsernameExistsException`, attempts authentication, and if successful (same password), creates the missing DB rows.
- **ID token decoded without JWKS verification after `initiate_auth`**: The token was just obtained directly from Cognito over TLS. Using `jose.jwt.get_unverified_claims()` avoids a dependency on the JWKS cache for registration and login flows.
- **`email-validator` added to requirements.txt**: Required by Pydantic's `EmailStr` type used in request schemas. Without it, Pydantic raises an import error at runtime.

## Assumptions Made

- P01-01 is complete: `config.py` has `cognito_user_pool_id`, `cognito_app_client_id`, `aws_region`; `main.py` has `create_app()` with `include_router` pattern; `core/` directory exists.
- P01-02 is complete: `Profile`, `Character`, and `Conversation` SQLAlchemy models exist with the exact column names and types documented in `docs/04-veri-api.md`.
- P01-03 is complete: `core/auth.py` has `verify_cognito_token()` and `CognitoJWKSProvider`; `dependencies.py` has real `get_current_user` (not the 501 stub).
- `boto3` is in `requirements.txt` (verified -- it is).
- `python-jose[cryptography]` is in `requirements.txt` (verified -- it is).
- The Cognito User Pool App Client has `USER_PASSWORD_AUTH` enabled (infrastructure concern, not code).
- The ECS task role has `cognito-idp:AdminConfirmSignUp` IAM permission (infrastructure concern, not code).

## Dependencies

- **Requires**: P01-01 (project-setup), P01-02 (database-schema), P01-03 (cognito-auth-middleware)
- **Blocks**: All subsequent features that require an authenticated user (character CRUD, messaging, memory, profile, etc.)

## File Manifest

```
Backend:
  CREATE  backend/app/routes/auth.py
  CREATE  backend/app/services/auth_service.py
  CREATE  backend/app/schemas/auth.py
  MODIFY  backend/app/main.py
  MODIFY  backend/requirements.txt
  CREATE  backend/tests/test_auth_routes.py
  CREATE  backend/tests/test_auth_service.py
  CREATE  backend/tests/test_auth_schemas.py

Shared:
  CREATE  shared/feature-specs/auth-endpoints.md
  CREATE  docs/pipeline/auth-endpoints-architect.handoff.md
```

## Notes for Developers

- **Read the full spec first**: `shared/feature-specs/auth-endpoints.md` -- it contains the complete registration/login/refresh flows, all error scenarios, Pydantic schema definitions, 30 test scenarios, and 20 acceptance criteria.
- **Build order**: Start with schemas (`app/schemas/auth.py`), then the service (`app/services/auth_service.py`), then the route (`app/routes/auth.py`), then wire up in `main.py`. This order lets you test each layer incrementally.
- **Add `email-validator>=2.0.0,<3.0.0` to `requirements.txt`**: Without it, Pydantic's `EmailStr` fails at import time.
- **All three auth routes are public**: None use `Depends(get_current_user)`. The router must NOT have a global auth dependency.
- **Router prefix**: Register with `prefix="/api/v1/auth"` in `main.py`. Route functions use relative paths: `@router.post("/register")`, `@router.post("/login")`, `@router.post("/refresh")`.
- **Wrap boto3 calls with `asyncio.to_thread()`**: Every `self.cognito.sign_up(...)`, `self.cognito.admin_confirm_sign_up(...)`, and `self.cognito.initiate_auth(...)` must be wrapped.
- **Decode ID token with `jose.jwt.get_unverified_claims()`**: Do NOT use `verify_cognito_token()` from `core/auth.py`. The token was just obtained from Cognito and does not need JWKS verification.
- **Import `Profile` from `app.models.profile`**: The model file is `profile.py`, not `user.py`.
- **System prompt placeholder**: `DEFAULT_COMPANION_PROMPT` uses `{user_name}`. Use `str.format(user_name=name)` to substitute.
- **Cognito exception handling**: Catch `botocore.exceptions.ClientError` and dispatch on `e.response["Error"]["Code"]`. See the error mapping table in the spec (Section 4).
- **Transaction management**: Call `db.add()` for each new object (Profile, Character, Conversation), then a single `db.commit()`. If commit fails, SQLAlchemy automatically rolls back.

## Next Steps

backend-dev should read the spec at `shared/feature-specs/auth-endpoints.md` and implement all 8 files (3 new modules, 2 modifications, 3 test files). backend-tester should then verify all 20 acceptance criteria.
