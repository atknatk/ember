# Feature Spec: Android Auth

**Feature ID**: P04-02
**Phase**: 4
**Layer**: android
**Status**: IMPLEMENTED

## Overview

Android authentication flow with login, sign-up screens, REST-based JWT token management, secure token storage via EncryptedSharedPreferences, and automatic 401 retry via OkHttp interceptor.

## API Endpoints

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | /api/v1/auth/login | `{email, password}` | `{token, refresh_token, user}` |
| POST | /api/v1/auth/register | `{email, password, name}` | `{token, refresh_token, user}` |
| POST | /api/v1/auth/refresh | `{refresh_token}` | `{token}` |

## Architecture

### Token Management
- **Storage**: EncryptedSharedPreferences (AES-256-GCM via Android Keystore)
- **TokenManager**: Singleton, provides getAccessToken/getRefreshToken/saveTokens/clearTokens
- **No Amplify SDK**: Direct REST API calls (matches iOS AuthService pattern)

### Auth Interceptor (401 Retry)
- OkHttp Interceptor adds Bearer token to all non-auth requests
- On 401: refreshes token via /auth/refresh, retries once
- Auth endpoints (login/register/refresh) are excluded from token injection

### Navigation
- Start destination determined by `TokenManager.hasTokens`
- No tokens: Auth screen (login/signup)
- Has tokens: Home screen (main app)
- On auth success: navigate to Home, clear auth back stack

## Screens

### LoginScreen
- Email + password fields with validation
- Password visibility toggle
- Sign In button (disabled until form valid)
- "Don't have an account? Sign Up" link
- Error display via Snackbar
- Haptic feedback on success/error

### SignUpScreen
- Name + email + password + confirm password fields
- Real-time validation (email format, password length >= 8, password match)
- Create Account button (disabled until form valid)
- "Already have an account? Sign In" link
- AnimatedContent transition between login/signup

## Validation Rules
- Email: must contain "@", trimmed
- Password (login): non-empty
- Password (signup): >= 8 characters
- Confirm password: must match password
- Name: non-empty after trimming

## Error Mapping
| HTTP Code | Login Message | SignUp Message |
|-----------|--------------|----------------|
| 401 | Invalid email or password | - |
| 400 | detail or "Invalid email or password" | Context-specific (already exists, password requirements) |
| 429 | Too many attempts | Too many attempts |
| Network | Connection failed | Connection failed |
| Other | Something went wrong | Something went wrong |

## Dependencies
- Hilt for DI (TokenManager, AuthRepository, AuthApi, TokenInterceptor)
- Kotlin Serialization for JSON
- EncryptedSharedPreferences (androidx.security:security-crypto)
- OkHttp MockWebServer for interceptor tests
