# Feature Spec: Android Scaffold (P04-01)

**Feature ID**: P04-01
**Phase**: 4
**Layer**: android
**Status**: COMPLETE

---

## Overview

Android project scaffold with Jetpack Compose, Material 3, dark-only theme, bottom navigation, and design system tokens matching the iOS implementation exactly.

## Design System Tokens

### Colors (matching ios/Ember/Core/Extensions/Color+Ember.swift)

| Token | Hex | Usage |
|-------|-----|-------|
| EmberPrimary | #5B4FE8 | Buttons, user message bubbles |
| EmberPrimaryPressed | #4B3FD8 | Pressed state |
| EmberPrimaryHover | #6B5FF8 | Hover/highlight state |
| EmberAccent | #FF6B6B | Notifications, special events |
| EmberBackground | #0F0F14 | Main background |
| EmberSurface | #1A1A24 | Surface containers, tab bar |
| EmberSurface2 | #22223A | Cards, input fields, AI bubbles |
| EmberSurface3 | #2C2C4A | Hover, active states |
| EmberTextPrimary | #F0F0F8 | Primary text |
| EmberTextSecondary | #9090B0 | Secondary text, timestamps |
| EmberTextDisabled | #5A5A7A | Disabled, placeholders |
| EmberSuccess | #4CAF87 | Success states |
| EmberWarning | #F5A623 | Warning states |
| EmberError | #E85B5B | Error states |
| EmberGradientStart | #5B4FE8 | Onboarding gradient start |
| EmberGradientEnd | #FF6B6B | Onboarding gradient end |
| EmberAIBubbleStart | #1E1E35 | AI bubble gradient start |
| EmberAIBubbleEnd | #252545 | AI bubble gradient end |

### Typography (matching ios/Ember/Core/Extensions/Font+Ember.swift)

| Material 3 Slot | iOS Equivalent | Size | Weight |
|----------------|----------------|------|--------|
| headlineLarge | emberLargeTitle | 28sp | Bold |
| headlineMedium | emberTitle | 22sp | SemiBold |
| titleMedium | emberHeadline | 16sp | SemiBold |
| bodyLarge | emberBody | 15sp | Normal |
| bodyMedium | emberSecondary | 13sp | Normal |
| labelMedium | emberCaption | 12sp | Medium |
| labelSmall | emberMicro | 11sp | Normal |

### Spacing (matching ios/Ember/Core/Extensions/CGFloat+Ember.swift)

| Token | Value | Usage |
|-------|-------|-------|
| xxs | 4dp | Icon-text gap |
| xs | 8dp | Chip padding |
| sm | 12dp | List item padding |
| md | 16dp | Card padding |
| lg | 20dp | Screen margin |
| xl | 24dp | Section gap |
| xxl | 32dp | Large divider |
| xxxl | 48dp | Screen top padding |

### Corner Radii (matching iOS CGFloat+Ember.swift)

| Token | Value | Usage |
|-------|-------|-------|
| chip | 4dp | Small chip, badge |
| input | 12dp | Input fields, small cards |
| messageBubble | 16dp | Message bubbles |
| card | 20dp | Main cards, modals |
| pill | 28dp | CTA buttons |

## Navigation

Three bottom tabs matching iOS MainTabView:

1. **Home** — `Icons.Outlined.Home` / `Icons.Filled.Home`
2. **Memories** — `Icons.Outlined.Psychology` / `Icons.Filled.Psychology`
3. **Profile** — `Icons.Outlined.AccountCircle` / `Icons.Filled.AccountCircle`

## Architecture

- Single Activity (`MainActivity`) with `@AndroidEntryPoint`
- `EmberApplication` with `@HiltAndroidApp`
- `EmberTheme` wrapping `MaterialTheme` with dark-only color scheme
- `EmberNavHost` with `NavHost` + `Scaffold` + `EmberBottomBar`
- Placeholder screens for each tab

## Dependencies (version catalog)

- Compose BOM 2024.12.01
- Material 3 1.3.1
- Navigation Compose 2.8.5
- Hilt 2.53.1
- OkHttp 4.12.0
- Retrofit 2.11.0
- Kotlin Serialization 1.7.3
- Coil 2.7.0
- Lottie 6.6.2
- Coroutines 1.9.0

## File Structure

```
android/
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
├── gradle/libs.versions.toml
└── app/
    ├── build.gradle.kts
    ├── proguard-rules.pro
    └── src/
        ├── main/
        │   ├── AndroidManifest.xml
        │   ├── res/values/{strings,colors,themes}.xml
        │   └── java/ai/ember/app/
        │       ├── EmberApplication.kt
        │       ├── MainActivity.kt
        │       ├── core/
        │       │   ├── ui/theme/{Color,Type,Theme,Spacing,Shape}.kt
        │       │   ├── ui/components/EmberBottomBar.kt
        │       │   ├── navigation/{Screen,EmberNavHost}.kt
        │       │   └── network/ (placeholder)
        │       └── features/{home,memories,profile}/*Screen.kt
        └── test/java/ai/ember/app/core/
            ├── ui/theme/ThemeTest.kt
            └── navigation/NavigationTest.kt
```
