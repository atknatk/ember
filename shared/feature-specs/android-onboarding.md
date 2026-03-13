# Feature Spec: P04-03 -- Android Onboarding

**Feature ID**: P04-03
**Phase**: 4
**Layer**: android
**GitHub Issue**: #30
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements the full onboarding flow for the Ember Android app. It consists of two production screens:

1. **WelcomeScreen** -- A 3-page HorizontalPager carousel with Lottie animations (fallback to Material Icons), page indicator dots, next/skip buttons, and a "Get Started" CTA on the final page.

2. **QuestionsScreen** -- 7 personalization question cards with animated transitions (AnimatedContent with slide), progress indicator ("1/7" through "7/7"), free-text input per card, skip/back/next navigation, and a final "Submit" action that posts all answers to `POST /api/v1/onboarding/complete`.

An `OnboardingViewModel` drives the entire flow, managing phase state (Welcome vs Questions), answer collection, validation, API submission, and error handling.

### Why It Exists

The onboarding flow is the user's first interaction with Ember after signing up. It collects 7 personalization answers that the backend converts into Mem0 memories via Claude Haiku. Without this flow, the AI companion has zero context about the user, making conversations generic and impersonal.

### Dependencies

- **P04-01** (android-scaffold) -- provides project structure, theme, navigation, Hilt setup
- **P04-02** (android-auth) -- provides AuthRepository, TokenManager, AuthViewModel with isAuthenticated
- **P01-09** (onboarding-endpoint, backend) -- provides POST /api/v1/onboarding/complete

### What This Feature Does NOT Do

- Does not change any backend code
- Does not add ProfileSetupView (name + photo) -- handled separately
- Does not bundle Lottie animation JSON files -- uses fallback Material Icons gracefully

---

## 2. Data Models

### Kotlin Models

- `OnboardingAnswer` -- request body component with `questionKey` and `answer`
- `OnboardingRequest` -- wraps `answers: List<OnboardingAnswer>`
- `OnboardingResponse` -- `onboardingCompleted: Boolean, memoriesSeeded: Int`
- `OnboardingQuestion` -- pure domain model for question card data

---

## 3. API Endpoints

Uses existing endpoint:

```
POST /api/v1/onboarding/complete
Auth: Bearer JWT required
Request: {"answers": [{"question_key": "...", "answer": "..."}]}
Response 200: {"onboarding_completed": true, "memories_seeded": 7}
Response 409: {"detail": "Onboarding already completed"} -- treated as success
Response 422: Validation error
Response 503: Service unavailable
```

---

## 4. Screens and Components

### OnboardingScreen (Container)
- Routes between WelcomeScreen and QuestionsScreen via AnimatedContent
- Handles completion callback to navigate to main app
- Uses `hiltViewModel()` to inject OnboardingViewModel

### WelcomeScreen (3-Page Carousel)
- HorizontalPager with 3 pages
- Each page: Lottie animation (fallback icon), title, description
- Custom page indicator dots with spring animation
- Next button (pages 0-1), Get Started button (page 2)
- Skip link (pages 0-1) jumps to last page

### QuestionsScreen (7 Question Cards)
- AnimatedContent with slide transitions between cards
- Progress bar with animated fill
- Question number badge, question text, free-text input
- Back/Next/Submit navigation buttons
- Skip link per question
- Error dialog on submission failure

### OnboardingViewModel
- Sealed UiState: Welcome, Questions, Completed, Error
- Welcome phase: page navigation, skip to last
- Questions phase: answer management, navigation, submission
- Submits "Not provided" for skipped questions
- 409 Conflict treated as success by repository

---

## 5. Navigation Integration

- New `Screen.Onboarding` route added
- EmberNavHost determines start destination:
  - Not authenticated -> Auth
  - Authenticated, not onboarded -> Onboarding
  - Authenticated and onboarded -> Home
- After auth success, routes to Onboarding if `hasCompletedOnboarding` is false
- After onboarding completion, sets flag via AuthRepository and navigates to Home

---

## 6. Question Keys

| Index | Key | Question |
|-------|-----|----------|
| 0 | `preferred_name` | What should I call you? |
| 1 | `occupation` | What do you do for work? |
| 2 | `daily_rhythm` | Are you a morning person or a night owl? |
| 3 | `health_goal` | What are your health or fitness goals? |
| 4 | `stress_management` | How do you manage stress? |
| 5 | `sleep_schedule` | What is your sleep schedule like? |
| 6 | `communication_style` | What kind of friendship do you expect from me? |

---

## 7. File Manifest

```
Android:
  CREATE  android/.../features/onboarding/OnboardingModels.kt
  CREATE  android/.../features/onboarding/OnboardingApi.kt
  CREATE  android/.../features/onboarding/OnboardingRepository.kt
  CREATE  android/.../features/onboarding/OnboardingUiState.kt
  CREATE  android/.../features/onboarding/OnboardingViewModel.kt
  CREATE  android/.../features/onboarding/OnboardingScreen.kt
  CREATE  android/.../features/onboarding/WelcomeScreen.kt
  CREATE  android/.../features/onboarding/QuestionsScreen.kt
  CREATE  android/.../features/onboarding/OnboardingModule.kt
  MODIFY  android/.../core/navigation/Screen.kt (add Onboarding route)
  MODIFY  android/.../core/navigation/EmberNavHost.kt (add onboarding routing)
  MODIFY  android/.../core/auth/TokenManager.kt (add onboarding flag)
  MODIFY  android/.../core/auth/AuthRepository.kt (expose onboarding status)
  MODIFY  android/.../features/auth/AuthViewModel.kt (expose onboarding status)
  MODIFY  android/app/src/main/res/values/strings.xml (add onboarding strings)

Tests:
  CREATE  android/.../test/.../onboarding/OnboardingViewModelTest.kt
  CREATE  android/.../test/.../onboarding/OnboardingRepositoryTest.kt
```
