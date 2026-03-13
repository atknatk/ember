# Android Dev Handoff: Android Auth

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files
- `android/app/src/main/java/ai/ember/app/core/models/AuthModels.kt`
- `android/app/src/main/java/ai/ember/app/core/auth/TokenManager.kt`
- `android/app/src/main/java/ai/ember/app/core/auth/AuthRepository.kt`
- `android/app/src/main/java/ai/ember/app/core/auth/AuthModule.kt`
- `android/app/src/main/java/ai/ember/app/core/network/AuthApi.kt`
- `android/app/src/main/java/ai/ember/app/core/network/TokenInterceptor.kt`
- `android/app/src/main/java/ai/ember/app/core/network/NetworkModule.kt`
- `android/app/src/main/java/ai/ember/app/features/auth/AuthUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/auth/AuthViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/auth/AuthScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/auth/LoginScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/auth/SignUpScreen.kt`

## Modified Files
- `android/app/src/main/java/ai/ember/app/core/navigation/Screen.kt` — added `Auth` route
- `android/app/src/main/java/ai/ember/app/core/navigation/EmberNavHost.kt` — auth flow + conditional start destination
- `android/app/src/main/res/values/strings.xml` — added 18 auth string keys
- `android/app/build.gradle.kts` — added security-crypto + mockwebserver deps
- `android/gradle/libs.versions.toml` — added security-crypto + mockwebserver versions

## Test Files
- `android/app/src/test/java/ai/ember/app/features/auth/AuthViewModelTest.kt` (22 tests)
- `android/app/src/test/java/ai/ember/app/core/auth/AuthRepositoryTest.kt` (12 tests)
- `android/app/src/test/java/ai/ember/app/core/network/TokenInterceptorTest.kt` (7 tests)

## Screens Implemented
- **LoginScreen**: Email + password, validation, password visibility toggle, sign-up link
- **SignUpScreen**: Name + email + password + confirm password, real-time validation
- **AuthScreen**: Container with AnimatedContent transition between login/signup

## strings.xml Keys Added
- `auth_welcome_back`: "Welcome Back"
- `auth_sign_in_subtitle`: "Sign in to continue"
- `auth_create_account`: "Create Account"
- `auth_sign_up_subtitle`: "Join Ember to get started"
- `auth_email_label`: "Email"
- `auth_password_label`: "Password"
- `auth_password_hint`: "Password (8+ characters)"
- `auth_name_label`: "Full Name"
- `auth_confirm_password_label`: "Confirm Password"
- `auth_sign_in_button`: "Sign In"
- `auth_create_account_button`: "Create Account"
- `auth_no_account`: "Don't have an account?"
- `auth_sign_up_link`: "Sign Up"
- `auth_have_account`: "Already have an account?"
- `auth_sign_in_link`: "Sign In"
- `auth_toggle_password_visibility`: "Toggle password visibility"
- `auth_email_invalid`: "Please enter a valid email"
- `auth_passwords_mismatch`: "Passwords do not match"

## Deviations from Spec
- Used direct REST API calls via Retrofit instead of AWS Amplify Cognito SDK (matches iOS pattern and avoids heavy SDK dependency)
- AuthModule.kt is minimal (empty object) since TokenManager and AuthRepository use constructor injection — kept for future @Binds declarations

## Notes for Android Tester
- ViewModel depends on `AuthRepository` — use MockK `mockk<AuthRepository>(relaxed = true)`
- TokenManager requires Android context (EncryptedSharedPreferences) — cannot be unit tested directly, mock it
- TokenInterceptor tests use MockWebServer — verify auth header injection and 401 retry
- Turbine is configured — use `.test { }` for StateFlow assertions in AuthViewModelTest
- Navigation test updated to include new Auth route
