# iOS Dev Handoff: iOS Auth Screens

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Modified Files
- `ios/Ember/Features/Auth/AuthViewModel.swift`
- `ios/Ember/Features/Auth/LoginView.swift`
- `ios/Ember/Features/Auth/SignUpView.swift`
- `ios/Ember/App/EmberApp.swift`
- `ios/EmberTests/Features/Auth/AuthViewModelTests.swift`

## Enhancements Implemented

### 1. Animated Transition Between Login and SignUp (EmberApp.swift)
- Asymmetric slide + opacity transitions on Login/SignUp toggle
- LoginView slides from leading edge, SignUpView slides from trailing edge
- 300ms easeInOut animation driven by `isShowingSignUp` value
- Opacity transition for authenticated state change (350ms)

### 2. Error Shake Animation (LoginView, SignUpView)
- Submit button shakes horizontally on auth failure (3 oscillations, 8px amplitude)
- Spring-based animation for natural feel
- `showErrorShake` property on ViewModel triggers the animation
- Auto-resets after 500ms via async Task

### 3. Initial Fade-In Animation (LoginView, SignUpView)
- Content fades in on first appearance with 300ms easeOut animation
- Driven by local `@State isAppeared` property

### 4. Inline Email Validation (LoginView, SignUpView)
- "Please enter a valid email" hint shown below email field
- Appears only after field loses focus (`emailHasBeenEdited`) and email lacks `@`
- Suppressed when email is empty to avoid noise
- Animated appearance with opacity + move transition

### 5. Password Visibility Toggle (LoginView, SignUpView)
- Eye icon button (`eye.fill` / `eye.slash.fill`) toggles between SecureField and TextField
- 44x44pt minimum tap target
- Independent toggles for password and confirm password fields on SignUpView
- Full accessibility labels and hints

### 6. Accessibility Hints
- Sign In button: "Double tap to sign in with your email and password"
- Sign Up link: "Double tap to navigate to sign up"
- Create Account button: "Double tap to create your account"
- Sign In link: "Double tap to navigate to sign in"
- Password toggle: "Double tap to show/hide password"

## Deviations from Spec
- None

## Notes for iOS Tester
- ViewModel uses `AuthServiceProtocol` -- existing `MockAuthService` can be reused for tests
- New properties to test: `showErrorShake`, `emailHasBeenEdited`, `showEmailValidationError`
- 8 new test cases added to `AuthViewModelTests.swift` covering all new ViewModel logic
- Shake animation resets `showErrorShake` to false after 500ms -- in tests, the value may still be `true` immediately after `signIn()`/`signUp()` returns since the reset is async
- Visual animations (fade-in, transitions, shake) should be verified manually on simulator/device
- Test password toggle by tapping eye icon and verifying text visibility changes
- Test email validation by entering invalid email, then tapping another field
- VoiceOver: verify all hints are announced correctly on interactive elements
