# Architect Handoff: iOS Cognito Auth

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Complete iOS authentication flow using backend REST endpoints (not Amplify SDK). AuthService calls POST /api/v1/auth/register, /login, and /refresh via URLSession, stores JWT tokens in iOS Keychain via KeychainTokenStore, and provides an @Observable AuthViewModel that drives LoginView and SignUpView. Replaces the @AppStorage-based placeholder auth with production Keychain-backed token management. The APIClient 401 retry (from P03-02) is wired end-to-end via AuthService.refreshToken().

## Key Decisions

- **Backend endpoints over Amplify SDK**: The backend already handles Cognito sign-up/login/refresh and creates DB rows (Profile, Character, Conversation). Using Amplify on the client would skip DB row creation and require distributing amplifyconfiguration.json. All auth goes through the backend REST API.
- **AuthService makes its own HTTP calls**: To avoid circular dependency with APIClient (which calls AuthService for tokens), AuthService uses URLSession directly for the three public auth endpoints.
- **Keychain over @AppStorage**: @AppStorage uses unencrypted UserDefaults. docs/standards/common.md mandates Keychain for token storage.
- **AuthViewModel as reactive bridge**: AuthService is @unchecked Sendable (not @Observable). AuthViewModel provides the SwiftUI reactivity layer, exposing isAuthenticated for EmberApp to observe.
- **No Amplify SDK dependency added**: Since auth goes through backend, the Amplify package is not needed. This avoids the amplifyconfiguration.json requirement.
- **LoginPlaceholderView deleted**: Replaced entirely by LoginView with real form fields.

## Spec Location

`shared/feature-specs/ios-cognito-auth.md`

## Assumptions Made

- The backend auth endpoints (P01-04) are deployed and accessible.
- The backend auto-confirms users during sign-up (MVP mode, no email verification UI needed).
- Forgot password / password reset is Phase 4 (not included).
- The onboarding flow remains a placeholder; auth transitions to OnboardingPlaceholderView after first sign-up.
- Social sign-in (Apple, Google) is out of scope.

## Dependencies

- Requires: P03-01 (ios-scaffold), P03-02 (ios-network-layer), P01-04 (auth-endpoints backend)
- Blocks: all subsequent iOS features that make authenticated API calls

## Next Steps

ios-dev should read the spec and implement. ios-tester follows after implementation.
