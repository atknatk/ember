# Feature Spec: P03-05 -- iOS Auth Screens

**Feature ID**: P03-05
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #21
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature applies visual polish and UX enhancements to the auth screens (LoginView, SignUpView, AuthViewModel) that were already implemented in P03-03 (ios-cognito-auth). P03-03 delivered fully functional login and sign-up screens with form validation, loading states, keyboard management, haptic feedback, and error handling. P03-05 adds the finishing touches that elevate the screens from "functional" to "polished": animated transitions between login and sign-up, an error shake animation on the sign-in button when submission fails, inline email validation feedback, a subtle fade-in on initial appearance, and improved VoiceOver field ordering with accessibility hints.

### Why It Exists

The P03-05 issue description ("LoginView with email + password fields, sign in button, sign up link, error state; RegisterView with name + email + password, validation; @Observable AuthViewModel; keyboard avoidance; loading states") overlaps almost entirely with what P03-03 already delivered. Rather than duplicating work, this feature focuses on the animation and UX polish items from `docs/14-tasarim.md` that P03-03 did not implement: screen transition animations, micro-interaction animations (error shake, success check), and inline validation feedback.

### What P03-03 Already Delivered

The following are fully implemented and require NO changes:

- **LoginView.swift**: Email field, password field, sign-in button with loading spinner, sign-up link, error alert, @FocusState keyboard management, `.scrollDismissesKeyboard(.interactively)`, design system colors/spacing/fonts, accessibility labels.
- **SignUpView.swift**: Name field, email field, password field, confirm password field with mismatch validation text, create account button with loading spinner, sign-in link, error alert, @FocusState keyboard management, accessibility labels.
- **AuthViewModel.swift**: @Observable with email, password, name, confirmPassword form state; isLoading, errorMessage, isShowingSignUp, isAuthenticated UI state; isSignInFormValid, isSignUpFormValid, passwordsDoNotMatch computed properties; signIn(), signUp(), signOut(), clearError() methods; HapticManager integration; AuthServiceProtocol dependency injection.
- **AuthTextFieldStyle**: Shared ViewModifier for consistent text field styling.
- **EmberApp.swift**: Auth state switching via authViewModel.isAuthenticated, environment injection of AuthViewModel.

### What This Feature Adds

1. **Animated transition between Login and SignUp** -- smooth cross-fade or slide animation when toggling `isShowingSignUp` instead of an abrupt view swap.
2. **Error shake animation** -- when sign-in or sign-up fails, the submit button shakes horizontally (3x, 8px amplitude) per `docs/14-tasarim.md` micro-animation spec.
3. **Initial appearance fade-in** -- the auth screen content fades in on first appearance (300ms, easeOut).
4. **Inline email validation** -- when the email field loses focus and does not contain `@`, a small error hint appears below the field: "Please enter a valid email" in `.emberCaption` / `.emberError`.
5. **Accessibility hints** -- add `.accessibilityHint` on the sign-in button ("Double tap to sign in with your email and password") and sign-up button ("Double tap to create your account").
6. **Password visibility toggle** -- a small eye icon button inside the password fields to toggle between `SecureField` and `TextField` for password visibility.

### Dependencies

- **P03-03** (ios-cognito-auth) -- provides the existing LoginView.swift, SignUpView.swift, AuthViewModel.swift, AuthTextFieldStyle, and all auth infrastructure (AuthService, KeychainTokenStore, AuthModels).

### What This Feature Does NOT Do

- It does not add "Forgot Password" functionality (Phase 4 per P03-03 spec).
- It does not add social sign-in (Apple, Google).
- It does not change any auth logic, API calls, or Keychain operations.
- It does not add new backend endpoints.

---

## 2. Data Models

No database changes. No new Swift models. This is a pure UI/UX polish feature on existing iOS views.

---

## 3. API Endpoints

No new API endpoints. No changes to existing endpoint calls. The auth flow (login, register, refresh) remains exactly as P03-03 implemented it.

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature.

---

## 5. iOS Screens and Components

### 5.1 AuthViewModel Additions

**File**: `ios/Ember/Features/Auth/AuthViewModel.swift` (MODIFY)

Add the following properties to support UI animations:

**New Properties**:
- `var showErrorShake: Bool = false` -- set to `true` briefly when sign-in or sign-up fails, triggers shake animation on the submit button. Reset to `false` after the animation completes (via a 0.5s delay).
- `var emailHasBeenEdited: Bool = false` -- tracks whether the user has interacted with the email field. Used to suppress inline validation on initial display.

**New Computed Property**:
- `var showEmailValidationError: Bool` -- returns `true` when `emailHasBeenEdited` is `true`, email is not empty, and email does not contain `@`. This drives the inline validation hint below the email field.

**Changes to `signIn()`**:
- After the `catch` block sets `errorMessage`, also set `showErrorShake = true`. After a short delay (dispatched via `Task`), set `showErrorShake = false`.

**Changes to `signUp()`**:
- Same `showErrorShake` trigger as `signIn()`.

### 5.2 LoginView Enhancements

**File**: `ios/Ember/Features/Auth/LoginView.swift` (MODIFY)

#### 5.2.1 Animated Appearance

Wrap the main `VStack` content with an `.opacity` modifier driven by a local `@State private var isAppeared: Bool = false` property. On `.onAppear`, set `isAppeared = true` with a 300ms easeOut animation. The VStack opacity is bound to `isAppeared ? 1 : 0`.

#### 5.2.2 Inline Email Validation

Below the email `TextField`, add a conditional `Text` view:
- Shown when `viewModel.showEmailValidationError` is `true`.
- Text: "Please enter a valid email"
- Font: `.emberCaption`
- Color: `.emberError`
- Left padding: `.emberSpacing4`
- Animated appearance with `.transition(.opacity.combined(with: .move(edge: .top)))`.

To track when the email field loses focus, observe `focusedField` changes. When `focusedField` changes away from `.email`, set `viewModel.emailHasBeenEdited = true`.

#### 5.2.3 Error Shake Animation

Apply a `.offset(x:)` modifier to the sign-in button, driven by `viewModel.showErrorShake`. When `showErrorShake` is `true`, apply a horizontal shake animation. Implementation approach: use a local `@State private var shakeOffset: CGFloat = 0` property. When `showErrorShake` changes to `true`, trigger a withAnimation sequence that oscillates `shakeOffset` between -8, 8, -8, 0 using a spring animation. This matches the `docs/14-tasarim.md` specification: "Shake (3x, 8px)" for form submit errors.

#### 5.2.4 Password Visibility Toggle

Replace the `SecureField` with a `ZStack` containing:
- A `SecureField` shown when `isPasswordVisible` is `false`.
- A `TextField` shown when `isPasswordVisible` is `true`.
- A `Button` with an eye icon (`EmberSymbol` -- `"eye"` when hidden, `"eye.slash"` when visible) aligned to the trailing edge inside the field.

Add `@State private var isPasswordVisible: Bool = false` to `LoginView`.

The toggle button:
- SF Symbol: `"eye.fill"` (show) / `"eye.slash.fill"` (hide)
- Color: `.emberTextSecondary`
- Size: 17pt
- Tap target: 44x44pt minimum
- `.accessibilityLabel("Toggle password visibility")`

#### 5.2.5 Accessibility Hints

Add `.accessibilityHint("Double tap to sign in with your email and password")` to the sign-in button.
Add `.accessibilityHint("Double tap to navigate to sign up")` to the sign-up link.

### 5.3 SignUpView Enhancements

**File**: `ios/Ember/Features/Auth/SignUpView.swift` (MODIFY)

#### 5.3.1 Animated Appearance

Same fade-in pattern as LoginView (`.opacity` + `.onAppear` + 300ms easeOut animation).

#### 5.3.2 Inline Email Validation

Same inline email validation as LoginView. The `viewModel.showEmailValidationError` computed property is shared because the ViewModel is shared.

Note: The focus field enum in SignUpView already has `.email` case. Use the same `.onChange(of: focusedField)` pattern to set `viewModel.emailHasBeenEdited = true` when focus leaves the email field.

#### 5.3.3 Error Shake Animation

Same shake animation on the "Create Account" button as described for LoginView.

#### 5.3.4 Password Visibility Toggles

Add password visibility toggles to both the password field and the confirm password field. Each has its own independent `@State private var isPasswordVisible: Bool` and `@State private var isConfirmPasswordVisible: Bool`.

#### 5.3.5 Accessibility Hints

Add `.accessibilityHint("Double tap to create your account")` to the create account button.
Add `.accessibilityHint("Double tap to navigate to sign in")` to the sign-in link.

### 5.4 EmberApp.swift -- Animated Auth Transition

**File**: `ios/Ember/App/EmberApp.swift` (MODIFY)

Add a `.transition` modifier to the login/sign-up views and the main content to animate the switch between `isShowingSignUp` states and between unauthenticated/authenticated states.

For the `isShowingSignUp` toggle:
- Wrap the conditional in an explicit animation: use `.animation(.easeInOut(duration: 0.3), value: authViewModel.isShowingSignUp)` on the parent `Group`.
- Add `.transition(.asymmetric(insertion: .move(edge: .trailing).combined(with: .opacity), removal: .move(edge: .leading).combined(with: .opacity)))` on SignUpView.
- Add `.transition(.asymmetric(insertion: .move(edge: .leading).combined(with: .opacity), removal: .move(edge: .trailing).combined(with: .opacity)))` on LoginView.

For the authenticated transition (login to main content):
- Add `.transition(.opacity)` on the main content group.
- Add `.animation(.easeInOut(duration: 0.35), value: authViewModel.isAuthenticated)` on the outer Group.

### 5.5 AuthTextFieldStyle Enhancement

**File**: `ios/Ember/Features/Auth/LoginView.swift` (MODIFY -- AuthTextFieldStyle is defined at the bottom of this file)

The existing `AuthTextFieldStyle` is adequate but does not account for the password visibility toggle layout. Create a new `AuthPasswordFieldStyle` ViewModifier or update `AuthTextFieldStyle` to accept an optional trailing button parameter. However, to keep changes minimal, the password visibility toggle is implemented inline in each view rather than modifying the shared style.

No changes to `AuthTextFieldStyle` are needed.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature.

---

## 7. Test Plan

### iOS Unit Tests

#### AuthViewModel Tests (Additional)

**File**: `ios/EmberTests/Features/Auth/AuthViewModelTests.swift` (MODIFY -- add new test cases)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `signIn` failure sets `showErrorShake` to true | `showErrorShake` is `true` immediately after failure |
| 2 | `signUp` failure sets `showErrorShake` to true | `showErrorShake` is `true` immediately after failure |
| 3 | `showEmailValidationError` with edited email missing `@` | Returns `true` |
| 4 | `showEmailValidationError` with valid email | Returns `false` |
| 5 | `showEmailValidationError` with unedited email | Returns `false` (even if email is invalid) |
| 6 | `showEmailValidationError` with empty email after editing | Returns `false` (suppressed when empty to avoid noise) |
| 7 | `signIn` success does not set `showErrorShake` | `showErrorShake` remains `false` |

#### UI Tests (Guidance)

No automated UI tests are specified for this feature. The visual polish (animations, transitions) should be verified through manual QA on a simulator or device. The tester should verify:

- Login-to-SignUp transition has a smooth slide animation (not abrupt).
- Error shake animation plays on the submit button after a failed attempt.
- Fade-in animation plays when the auth screen first appears.
- Inline email validation hint appears after the email field loses focus with an invalid value.
- Password visibility toggle works for all password fields.
- VoiceOver announces accessibility hints on buttons.

---

## 8. Acceptance Criteria

1. Given the app launches for the first time, when the login screen appears, then the content fades in smoothly over approximately 300ms.

2. Given the login screen is showing, when the user taps "Sign Up", then the view transitions with a smooth horizontal slide animation to the sign-up screen (not an abrupt swap).

3. Given the sign-up screen is showing, when the user taps "Sign In", then the view transitions with a smooth horizontal slide animation back to the login screen.

4. Given the login screen is showing, when the user enters an email without `@` and taps the password field (moving focus away from email), then a hint "Please enter a valid email" appears below the email field in red.

5. Given the login screen is showing, when the user corrects the email to include `@`, then the inline validation hint disappears.

6. Given the login screen is showing, when sign-in fails, then the sign-in button shakes horizontally (3 oscillations, approximately 8px amplitude).

7. Given the sign-up screen is showing, when sign-up fails, then the create account button shakes horizontally.

8. Given any password field on the login or sign-up screens, when the user taps the eye icon, then the password text becomes visible (switches from masked to plain text).

9. Given a visible password, when the user taps the eye icon again, then the password text becomes masked again.

10. Given VoiceOver is enabled, when the user focuses the sign-in button, then VoiceOver announces "Sign In. Button. Double tap to sign in with your email and password."

11. Given VoiceOver is enabled, when the user focuses the sign-up link on the login screen, then VoiceOver announces "Sign Up. Button. Double tap to navigate to sign up."

12. Given all existing P03-03 auth functionality (form validation, loading states, error alerts, keyboard avoidance, haptic feedback), when the P03-05 changes are applied, then all existing behavior continues to work correctly with no regressions.

13. Given the AuthViewModel unit tests (both existing from P03-03 and new from P03-05), when they are run, then all tests pass.

---

## 9. File Manifest

```
iOS:
  MODIFY  ios/Ember/Features/Auth/AuthViewModel.swift
  MODIFY  ios/Ember/Features/Auth/LoginView.swift
  MODIFY  ios/Ember/Features/Auth/SignUpView.swift
  MODIFY  ios/Ember/App/EmberApp.swift

Tests:
  MODIFY  ios/EmberTests/Features/Auth/AuthViewModelTests.swift

Shared:
  CREATE  shared/feature-specs/ios-auth-screens.md         (this file)
  CREATE  docs/pipeline/ios-auth-screens-architect.handoff.md
```

| Action | Count |
|--------|-------|
| CREATE | 2 (spec + handoff) |
| MODIFY | 5 |

---

## 10. Design Decisions and Rationale

### Why this feature is mostly MODIFY, not CREATE

P03-03 already created all three auth files (LoginView.swift, SignUpView.swift, AuthViewModel.swift) with full functionality. The P03-05 issue description is effectively a subset of what P03-03 delivered. Rather than recreating files, this spec adds the animation and polish layer that makes the screens feel "finished" per `docs/14-tasarim.md`.

### Why error shake instead of just the alert

The existing error handling shows a `.alert` dialog. This is correct and remains. The shake animation is an additional visual cue that provides immediate feedback before the user reads the alert. It follows `docs/14-tasarim.md` micro-animation spec: "Hata mesaji: Shake (3x, 8px) -- Form submit hatasi".

### Why inline email validation only on focus loss

Showing validation errors while the user is still typing is distracting. The standard pattern is to validate on blur (when focus leaves the field). The `@FocusState` already exists in both views; observing its changes is straightforward.

### Why password visibility toggle

Password fields use `SecureField` which masks input. Users frequently mistype passwords, especially on mobile keyboards. A visibility toggle is a standard UX pattern that reduces failed sign-in attempts due to typos. The toggle uses SF Symbols (`eye.fill` / `eye.slash.fill`) which are universally understood.

### Why showErrorShake is on the ViewModel (not local view state)

The shake is triggered by business logic (sign-in/sign-up failure), not by a UI gesture. Placing it on the ViewModel allows the view to react to it and allows the property to be tested.

### Transition animation approach

Using `.animation()` with `value:` parameters on the parent Group in EmberApp.swift provides smooth transitions between Login and SignUp without requiring custom transition infrastructure. The asymmetric transitions (slide left for forward, slide right for backward) provide directional context to the user.
