# Architect Handoff: Android Auth

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Scope
Android authentication flow: login/signup screens, JWT token management via EncryptedSharedPreferences, OkHttp auth interceptor with 401 auto-refresh.

## Key Decisions
- Direct REST API calls (no AWS Amplify SDK) — matches iOS AuthService pattern
- EncryptedSharedPreferences for token storage (Android equivalent of iOS Keychain)
- OkHttp Interceptor for Bearer token injection + 401 retry
- Single AuthViewModel shared between Login and SignUp screens
- Navigation determined by token existence at app start

## Spec Location
`shared/feature-specs/android-auth.md`
