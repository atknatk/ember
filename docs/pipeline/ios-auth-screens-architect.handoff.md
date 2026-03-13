# Architect Handoff: iOS Auth Screens

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

P03-05 is a UI/UX polish layer on top of the auth screens already implemented by P03-03 (ios-cognito-auth). P03-03 delivered fully functional LoginView, SignUpView, and AuthViewModel with form validation, loading states, keyboard management, haptic feedback, error alerts, and accessibility labels. P03-05 adds animated transitions between login/sign-up, an error shake micro-animation, inline email validation on blur, password visibility toggles, and accessibility hints.

## Key Decisions

- **MODIFY-only feature**: All three auth files (LoginView.swift, SignUpView.swift, AuthViewModel.swift) already exist from P03-03. This spec adds animation and polish enhancements without recreating any files or changing auth logic.
- **Error shake on ViewModel**: The `showErrorShake` property lives on AuthViewModel (not local view state) because it is triggered by business logic (sign-in/sign-up failure) and should be testable.
- **Inline email validation on focus loss**: Validation hints appear only after the user moves focus away from the email field, avoiding disruptive mid-typing validation.
- **Password visibility toggle**: Standard UX pattern using `eye.fill` / `eye.slash.fill` SF Symbols with 44pt tap targets.
- **Transition animations**: Asymmetric slide transitions between Login and SignUp views, opacity transition for auth-to-main-content switch. All driven by `.animation(value:)` on the parent Group in EmberApp.swift.

## Spec Location

`shared/feature-specs/ios-auth-screens.md`

## Assumptions Made

- P03-03 is fully merged and all auth files exist as read during spec creation.
- The existing AuthTextFieldStyle ViewModifier does not need changes; password toggle is implemented inline.
- No new dependencies or packages are required.

## Dependencies

- Requires: P03-03 (ios-cognito-auth) -- already complete.
- Blocks: ios-dev (implements the polish enhancements).

## Next Steps

ios-dev should read the spec and implement the MODIFY changes to the five files listed in the file manifest.
