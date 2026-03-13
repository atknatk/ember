# Android Dev Handoff: Android Onboarding

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files
- `android/.../features/onboarding/OnboardingModels.kt`
- `android/.../features/onboarding/OnboardingApi.kt`
- `android/.../features/onboarding/OnboardingRepository.kt`
- `android/.../features/onboarding/OnboardingUiState.kt`
- `android/.../features/onboarding/OnboardingViewModel.kt`
- `android/.../features/onboarding/OnboardingScreen.kt`
- `android/.../features/onboarding/WelcomeScreen.kt`
- `android/.../features/onboarding/QuestionsScreen.kt`
- `android/.../features/onboarding/OnboardingModule.kt`

## Modified Files
- `android/.../core/navigation/Screen.kt` -- added `Screen.Onboarding`
- `android/.../core/navigation/EmberNavHost.kt` -- added onboarding route and Auth->Onboarding->Home flow
- `android/.../core/auth/TokenManager.kt` -- added `hasCompletedOnboarding` and `setOnboardingCompleted`
- `android/.../core/auth/AuthRepository.kt` -- exposed onboarding status, saves flag from auth response
- `android/.../features/auth/AuthViewModel.kt` -- exposed `hasCompletedOnboarding` and `setOnboardingCompleted`
- `android/app/src/main/res/values/strings.xml` -- added 27 onboarding strings

## Screens Implemented
- **WelcomeScreen**: 3-page HorizontalPager carousel with Lottie/fallback icons, page indicators, next/skip/get started buttons
- **QuestionsScreen**: 7 personalization cards with animated transitions, progress bar, back/next/skip/submit navigation
- **OnboardingScreen**: Container routing between Welcome and Questions phases

## strings.xml Keys Added
- `onboarding_welcome_title_1`: "Meet Ember"
- `onboarding_welcome_desc_1`: "Your personal AI companion..."
- `onboarding_welcome_title_2`: "Built on Memory"
- `onboarding_welcome_desc_2`: "Every conversation builds..."
- `onboarding_welcome_title_3`: "Always Here for You"
- `onboarding_welcome_desc_3`: "Get personalized support..."
- `onboarding_get_started`: "Get Started"
- `onboarding_next`: "Next"
- `onboarding_skip`: "Skip"
- `onboarding_back`: "Back"
- `onboarding_submit`: "Submit"
- `onboarding_progress`: "%1$d/%2$d"
- `onboarding_question_1` through `onboarding_question_7`
- `onboarding_placeholder_1` through `onboarding_placeholder_7`
- `onboarding_error_title`: "Error"
- `onboarding_try_again`: "Try Again"
- `onboarding_dismiss`: "Dismiss"

## Deviations from Spec
- Lottie JSON files not bundled (fallback Material Icons used gracefully). The asset files (`onboarding-welcome.json`, `onboarding-memory.json`, `onboarding-companion.json`) should be placed in `android/app/src/main/assets/` when available.

## Notes for Android Tester
- ViewModel depends on `OnboardingRepository` -- use MockK `mockk<OnboardingRepository>()`
- Repository depends on `OnboardingApi` -- mock Retrofit `Response<OnboardingResponse>` objects
- Test 409 Conflict handling -- repository treats it as success
- Test "Not provided" fallback for skipped answers
- Turbine is configured -- use `.test { }` for StateFlow assertions
- Navigation flow: verify Auth -> Onboarding -> Home routing based on `hasCompletedOnboarding` flag
- The `TokenManager.setOnboardingCompleted()` persists the flag in EncryptedSharedPreferences
