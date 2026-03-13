# iOS Auth Screens Polish

> Elevates the login and sign-up screens from functional to polished with animated transitions, micro-interaction feedback, inline email validation, password visibility toggles, and VoiceOver hints.

**Status**: Released
**Added in**: Phase 3 (P03-05)
**Platforms**: iOS
**GitHub Issue**: #21

---

## Overview

This feature is a UI/UX polish layer built on top of the auth screens delivered by P03-03 (ios-cognito-auth). P03-03 produced `LoginView`, `SignUpView`, and `AuthViewModel` with complete auth logic: form validation, loading states, keyboard avoidance, haptic feedback, and error alerts. P03-05 adds the finishing touches that make these screens feel like a production-quality product rather than a working prototype.

The enhancements fall into five categories: screen transition animations (the Login-to-SignUp swap now slides rather than snaps), micro-interaction animations (the submit button shakes horizontally when sign-in or sign-up fails), an initial fade-in that makes the first screen appearance feel deliberate, inline email validation that appears only after the user leaves the email field, and password visibility toggles on every password field. VoiceOver accessibility hints are added to all interactive elements that previously had only labels.

No auth logic, API calls, Keychain operations, or data models change. This feature is entirely confined to the View and ViewModel presentation layer. All five modified files already existed; no new files were created.

---

## Architecture

### How It Works (Data Flow)

The feature touches three layers but does not change any layer boundaries:

1. `EmberApp.swift` evaluates `authViewModel.isAuthenticated` and `authViewModel.isShowingSignUp` to decide which view to render.
2. When `isShowingSignUp` flips, the parent `Group` in `EmberApp` applies an asymmetric slide + opacity transition animated over 300ms.
3. `LoginView` or `SignUpView` appears. On `.onAppear`, a local `@State isAppeared` property transitions from `false` to `true` with a 300ms easeOut animation, causing the content to fade in.
4. The user types in the email field. When focus moves away (tracked via `@FocusState` and `.onChange(of: focusedField)`), the view sets `viewModel.emailHasBeenEdited = true`.
5. `viewModel.showEmailValidationError` (a computed property on `AuthViewModel`) evaluates to `true` if `emailHasBeenEdited && !email.isEmpty && !email.contains("@")`. A hint text animates in below the email field.
6. The user taps the eye icon on a password field. A local `@State isPasswordVisible` property toggles, swapping `SecureField` for `TextField` (or back) inside a `ZStack`.
7. The user submits. If the auth service call fails, `AuthViewModel.triggerErrorShake()` sets `showErrorShake = true` and schedules an async reset after 500ms.
8. The view observes `showErrorShake` via `.onChange`. When it becomes `true`, `performShakeAnimation()` fires a spring-based sequence of four `withAnimation` calls that oscillate `shakeOffset` between -8pt, +8pt, -8pt, and back to 0. The submit button's `.offset(x: shakeOffset)` binding drives the physical movement.
9. The existing error alert (from P03-03) still fires — the shake is an additional, parallel visual cue.

### Animation Inventory

| Animation | Trigger | Duration / Curve | What Moves |
|-----------|---------|-----------------|------------|
| Login ↔ SignUp slide | `isShowingSignUp` changes | 300ms easeInOut | Full screen view |
| Auth → App content fade | `isAuthenticated` changes | 350ms easeInOut | Full screen view |
| Screen fade-in on appear | `.onAppear` | 300ms easeOut | Entire VStack opacity |
| Email validation hint | `showEmailValidationError` changes | 200ms easeInOut | Hint text (opacity + move) |
| Error shake | `showErrorShake` becomes `true` | 4× spring (0.1s response, damping 0.2–0.5) | Submit button x-offset |

### ViewModel Properties Added by This Feature

`AuthViewModel` gains three new public properties, all of which live on the ViewModel because they are either triggered by business logic or need to be testable:

- `showErrorShake: Bool` — set to `true` by `triggerErrorShake()` when `signIn()` or `signUp()` catches an error. Auto-reset to `false` after 500ms via a detached `Task`.
- `emailHasBeenEdited: Bool` — set to `true` by the view when focus leaves the email field. Reset to `false` by `signOut()`.
- `showEmailValidationError: Bool` (computed) — `emailHasBeenEdited && !email.isEmpty && !email.contains("@")`. Drives the inline validation hint.

The `triggerErrorShake()` helper is `private`. It sets `showErrorShake = true`, then uses `Task.sleep(nanoseconds: 500_000_000)` to defer the reset without blocking the main thread.

### EmberApp.swift Transition Setup

The Login/SignUp asymmetric transitions use `.asymmetric(insertion:removal:)` so each view slides in from a consistent edge regardless of which direction the swap goes:

- `LoginView` uses `.move(edge: .leading)` for both insertion and removal — it always enters and exits on the left edge.
- `SignUpView` uses `.move(edge: .trailing)` for both — it always enters and exits on the right edge.

Both transitions are combined with `.opacity`. The `.animation(.easeInOut(duration: 0.3), value: authViewModel.isShowingSignUp)` modifier on the wrapping `Group` drives both.

The outer `Group` (which switches between unauthenticated and authenticated states) carries `.animation(.easeInOut(duration: 0.35), value: authViewModel.isAuthenticated)`. The authenticated content uses `.transition(.opacity)`.

---

## API Reference

This feature makes no API calls and adds no endpoints. All network communication is handled by the underlying P03-03 auth infrastructure. See [`docs/04-veri-api.md`](../04-veri-api.md) for the auth endpoint contracts and [`docs/features/ios-cognito-auth.md`](ios-cognito-auth.md) for how `AuthService` calls them.

---

## iOS Implementation

**Files** (all MODIFY — no new files created):
- `ios/Ember/Features/Auth/AuthViewModel.swift` — adds `showErrorShake`, `emailHasBeenEdited`, `showEmailValidationError`, `triggerErrorShake()`
- `ios/Ember/Features/Auth/LoginView.swift` — adds fade-in, inline validation, shake, password toggle, accessibility hints
- `ios/Ember/Features/Auth/SignUpView.swift` — same enhancements as LoginView, plus a second toggle for confirm password
- `ios/Ember/App/EmberApp.swift` — adds asymmetric slide transitions and authenticated-state fade
- `ios/EmberTests/Features/Auth/AuthViewModelTests.swift` — adds 8 new test cases covering the new ViewModel properties

**Key Patterns**:

- Both views use `@Observable` `AuthViewModel` accessed via `@Environment(AuthViewModel.self)`. A local `@Bindable var viewModel = viewModel` is declared inside `body` to enable two-way bindings.
- Shake animation is intentionally implemented with `DispatchQueue.main.asyncAfter` rather than a single chained animation to give precise control over each oscillation step.
- The password toggle uses a `ZStack(alignment: .trailing)` containing the field (`SecureField` or `TextField` inside a `Group`) and the eye icon `Button`. The outer `.modifier(AuthTextFieldStyle())` applies to the `Group`, keeping the toggle button outside the styled container.
- Each view has its own independent `@State private var shakeOffset: CGFloat = 0` and visibility toggle states. No state is shared across views for these properties.

**ViewModel State** (`AuthViewModel` — full property list after P03-05):

```swift
// Form state
var email: String = ""
var password: String = ""
var name: String = ""
var confirmPassword: String = ""

// UI state
var isLoading: Bool = false
var errorMessage: String? = nil
var isShowingSignUp: Bool = false
var isAuthenticated: Bool = false
var showErrorShake: Bool = false      // P03-05
var emailHasBeenEdited: Bool = false  // P03-05

// Computed
var isSignInFormValid: Bool { ... }
var isSignUpFormValid: Bool { ... }
var passwordsDoNotMatch: Bool { ... }
var showEmailValidationError: Bool { ... }  // P03-05
```

**Local View State** (`LoginView`):

```swift
@FocusState private var focusedField: Field?
@State private var isAppeared: Bool = false
@State private var isPasswordVisible: Bool = false
@State private var shakeOffset: CGFloat = 0
```

`SignUpView` has the same properties plus `@State private var isConfirmPasswordVisible: Bool = false`.

**Navigation**: These screens have no `NavigationStack` involvement. `EmberApp.swift` renders `LoginView` or `SignUpView` directly as the window root when `authViewModel.isAuthenticated == false`. The `isShowingSignUp` toggle on `AuthViewModel` drives which of the two screens is shown.

**Accessibility**:

| Element | Label | Hint |
|---------|-------|------|
| Sign In button | "Sign In" | "Double tap to sign in with your email and password" |
| Sign Up link (on LoginView) | "Sign Up" | "Double tap to navigate to sign up" |
| Create Account button | "Create Account" | "Double tap to create your account" |
| Sign In link (on SignUpView) | "Sign In" | "Double tap to navigate to sign in" |
| Password toggle button (LoginView) | "Toggle password visibility" | "Double tap to show/hide password" (dynamic) |
| Confirm password toggle button (SignUpView) | "Toggle confirm password visibility" | "Double tap to show/hide password" (dynamic) |

---

## Android Implementation

Not applicable. This is an iOS-only feature.

---

## Testing

### Coverage Summary

| Platform | File | Tests Added | Total Tests |
|----------|------|-------------|-------------|
| iOS | `ios/EmberTests/Features/Auth/AuthViewModelTests.swift` | 8 | ~31 |

All tests use Swift Testing (`import Testing`), not XCTest. The test file existed from P03-03; P03-05 appended a new `@Suite`-scoped section at the bottom.

### New Test Cases (P03-05)

| Test | Scenario | Expected |
|------|----------|----------|
| `signInFailureSetsShake` | `signIn()` fails | `showErrorShake == true` immediately after failure |
| `signUpFailureSetsShake` | `signUp()` fails | `showErrorShake == true` immediately after failure |
| `signInSuccessNoShake` | `signIn()` succeeds | `showErrorShake == false` (never set) |
| `emailValidationErrorMissingAt` | `emailHasBeenEdited = true`, email has no `@` | `showEmailValidationError == true` |
| `emailValidationErrorValidEmail` | `emailHasBeenEdited = true`, email has `@` | `showEmailValidationError == false` |
| `emailValidationErrorUnedited` | `emailHasBeenEdited = false`, invalid email | `showEmailValidationError == false` |
| `emailValidationErrorEmptyAfterEdit` | `emailHasBeenEdited = true`, email is `""` | `showEmailValidationError == false` |
| `signOutResetsEmailEdited` | `signOut()` called while `emailHasBeenEdited = true` | `emailHasBeenEdited == false` after sign-out |

Note on the shake reset: `showErrorShake` is set back to `false` asynchronously after 500ms via a `Task`. In unit tests, the property will still be `true` immediately after `await signIn()` or `await signUp()` returns, because the reset `Task` runs after the test assertion. This is intentional and is why the tests assert the `true` value rather than waiting for the reset.

### Visual QA Checklist (manual, simulator or device)

The following behaviors cannot be verified through unit tests and require manual verification:

- Login ↔ SignUp transition is a smooth horizontal slide (not an abrupt swap)
- Error shake animation plays 3 oscillations at approximately 8px amplitude on the submit button
- Content fades in smoothly when the auth screen first appears (approximately 300ms)
- Inline email validation hint appears with an animated slide after the email field loses focus with an invalid value
- Password visibility toggle works on all password fields; tapping the eye icon reveals/hides the typed characters
- VoiceOver announces all accessibility hints correctly on all interactive elements

### Running Tests

```bash
cd ios
xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 16"
```

---

## Known Limitations

- **Shake reset is fire-and-forget**: `triggerErrorShake()` launches an unstructured `Task` that sets `showErrorShake = false` after 500ms. If the view is dismissed before the 500ms elapses, the `Task` will complete against a deallocated context. In practice this is harmless (the ViewModel is an `@Observable` value held by `EmberApp`), but it is worth noting for any future structured-concurrency refactor.
- **Shake uses `DispatchQueue.main.asyncAfter`**: The `performShakeAnimation()` function in both views uses four chained `DispatchQueue.main.asyncAfter` calls instead of a single declarative SwiftUI keyframe animation. This is intentional (for precise timing control) but means the animation is harder to disable in tests or accessibility contexts (e.g., Reduce Motion). Currently there is no `UIAccessibility.isReduceMotionEnabled` check on the shake.
- **No Reduce Motion guard on transitions**: The EmberApp slide transitions and the per-screen fade-in also do not check `UIAccessibility.isReduceMotionEnabled`. The design system doc (`docs/14-tasarim.md`) notes this as a future improvement for the animation layer.
- **Email validation is `@`-presence only**: `showEmailValidationError` checks only for the presence of `@`, matching the same rule used by `isSignInFormValid` and `isSignUpFormValid`. It does not validate full RFC 5322 email syntax. This is consistent with the rest of the validation in the app.

---

## Extending This Feature

### Adding Reduce Motion support

Wrap any animation that should be suppressed with a check on `UIAccessibility.isReduceMotionEnabled`. For the shake animation in `LoginView` and `SignUpView`, guard `performShakeAnimation()`:

```swift
guard !UIAccessibility.isReduceMotionEnabled else { return }
performShakeAnimation()
```

For SwiftUI-driven animations in `EmberApp.swift`, use the `@Environment(\.accessibilityReduceMotion)` environment value to conditionally apply or omit animation modifiers.

### Adding a new inline validation rule

Add a new computed property to `AuthViewModel` following the same pattern as `showEmailValidationError`:

```swift
var showPasswordStrengthWarning: Bool {
    passwordHasBeenEdited && !password.isEmpty && password.count < 8
}
```

Add a corresponding `passwordHasBeenEdited: Bool` property and set it in the relevant view using `.onChange(of: focusedField)`, matching the email field pattern exactly.

### Replacing the shake animation with a SwiftUI keyframe animation

If you upgrade the project to iOS 17's `KeyframeAnimator`, you can replace the `DispatchQueue.main.asyncAfter` chain in `performShakeAnimation()` with a declarative keyframe block. The ViewModel side (`showErrorShake` property) does not need to change — only the view's `.onChange(of: viewModel.showErrorShake)` handler needs to be replaced.

---

## Related Documentation

- [iOS Cognito Auth](ios-cognito-auth.md) — P03-03 foundation this feature builds on
- [iOS Scaffold](ios-scaffold.md) — design system tokens used throughout (`.emberSpacing`, `.emberRadius`, `Color.emberPrimary`, etc.)
- [iOS Onboarding](ios-onboarding.md) — the screen that follows successful sign-in for new users
- [Mobile Screens and Navigation](../07-mobil.md)
- [Design System](../14-tasarim.md) — micro-animation spec: "Shake (3x, 8px) — Form submit hatasi"
- [iOS Standards](../standards/ios.md)
