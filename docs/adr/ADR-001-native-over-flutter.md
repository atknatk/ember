# ADR-001: Native iOS and Android Instead of Flutter

| Field    | Value                    |
|----------|--------------------------|
| Date     | 2026-02-23               |
| Status   | Accepted                 |
| Deciders | Architecture Team        |
| Replaces | —                        |

---

## Context

Ember is a personal AI companion app. The mobile experience is central to the product — users
interact with animated 3D avatars, receive push notifications for reminders, access device
calendar for context-aware conversations, and use the microphone for voice interaction.

The team evaluated three mobile development approaches:

1. **Flutter** — cross-platform with a single Dart codebase, compiled to native.
2. **React Native** — cross-platform with JavaScript/TypeScript, bridges to native.
3. **Native (Swift/SwiftUI + Kotlin/Compose)** — platform-native codebases.

The primary decision axis was: which approach best supports Ember's product requirements
without compromising quality, performance, or long-term maintainability?

---

## Decision

**Use Native iOS (Swift/SwiftUI) and Native Android (Kotlin/Jetpack Compose).**

Two separate codebases: one in `ios/` and one in `android/`.

---

## Reasons

### 1. 3D Avatar Rendering

Ember's core feature is an animated 3D avatar companion. The implementation requires:

- **iOS**: SceneKit / RealityKit / ModelIO for 3D model loading and facial animation.
- **Android**: Sceneform / OpenGL ES 3.0 / ARCore for equivalent rendering.

Flutter's 3D support relies on the `flutter_scene` package or embedding a native view via
`PlatformView`. PlatformViews incur a significant rendering performance penalty because
the Flutter engine and the native view cannot share a GPU context. The result is frame drops
during avatar animation — unacceptable for a product where the avatar is always visible.

With native code, SceneKit and OpenGL ES run on the main render thread with zero overhead.

### 2. Native Device API Access

Ember requires deep integration with device APIs that are either unavailable or awkward
in Flutter:

| API                  | iOS                   | Android               | Flutter Status       |
|----------------------|-----------------------|-----------------------|----------------------|
| Calendar access      | EventKit              | CalendarProvider      | Plugin (limited)     |
| Call history         | Not available (iOS)   | CallLog ContentProvider | Plugin (limited)  |
| Contacts             | CNContactStore        | ContactsContract      | Plugin, outdated     |
| Live Activities      | ActivityKit (iOS 16+) | —                     | Not supported        |
| Dynamic Island       | ActivityKit (iOS 16+) | —                     | Not supported        |
| Widgets              | WidgetKit             | Glance (Compose)      | flutter_widget (alpha)|
| Shortcuts            | SiriKit               | App Shortcuts         | Not supported        |

For Android, reading the CallLog to provide context ("you had a long call earlier — want to
talk about it?") requires ContentProvider access that no Flutter plugin reliably provides.

### 3. Performance and Frame Rate

Ember's design involves smooth animations, message bubble physics, and avatar expressions
that respond to conversation sentiment. Target: 60fps stable, 120fps on ProMotion devices.

Flutter's rendering pipeline runs on its own Dart UI thread and composites onto a GPU
texture. For most apps this is sufficient. For Ember's combination of background blur effects,
particle systems on the avatar, and simultaneous SSE text streaming, Flutter's single-threaded
UI model creates contention.

SwiftUI leverages Metal directly. Jetpack Compose uses the hardware-accelerated Canvas API.
Both have zero-overhead access to the device GPU without an intermediate framework.

### 4. Binary Size

App size affects conversion rates, especially in markets with limited storage.

| Approach    | Minimum Install Size |
|-------------|----------------------|
| Flutter     | ~40–50 MB            |
| React Native| ~30–40 MB            |
| Native      | ~20–30 MB            |

Flutter bundles the Dart runtime and Flutter engine (~10 MB each). Native apps have no
runtime overhead beyond the OS frameworks already present on the device.

### 5. iOS 17+ @Observable

iOS 17 introduced the `@Observable` macro, which replaces the `ObservableObject` / `@Published`
pattern with a zero-boilerplate, compile-time-verified observation model. This is the
idiomatic SwiftUI pattern for iOS 17+.

Flutter's state management options (Riverpod, BLoC, Provider) are third-party libraries
that must be maintained separately. The native observation model is built into the language
and enforced by the compiler.

### 6. No Plugin Layer

Flutter plugins are Dart wrappers around platform channels that call native code. Every
plugin introduces:

- A maintenance dependency (plugin owner must keep up with iOS/Android SDK changes).
- A potential breaking change on major OS upgrades.
- A debugging surface where Dart, platform channel, and native code can all be at fault.

Native development eliminates this layer entirely. When Apple or Google change an API,
the fix is in one place.

### 7. AI Development Tooling

Claude Code (the AI agent writing this code) produces higher-quality output for Swift and
Kotlin than for Flutter/Dart. The Swift and Kotlin ecosystems have far more training data,
more idiomatic examples, and better static analysis tooling. This directly affects code
quality in an AI-assisted development workflow.

---

## Consequences

### Positive

- Full access to every native API on both platforms.
- Best possible performance for 3D avatar and animation.
- Smaller binary size.
- No dependency on Flutter plugin ecosystem.
- Swift @Observable and Kotlin StateFlow are the industry-standard patterns.
- iOS and Android can ship on independent schedules.

### Negative

- Two codebases to maintain (approximately 2x the mobile implementation work).
- Features must be implemented twice.
- No shared UI code between iOS and Android.
- Developers need Swift expertise (iOS) and Kotlin expertise (Android) — these are
  different skill sets.

### Mitigations

- Shared API contract in `docs/04-veri-api.md` ensures both platforms agree on the
  backend interface.
- The AI pipeline (ios-agent, android-agent) implements both platforms in parallel,
  which eliminates most of the human cost of maintaining two codebases.
- Shared design tokens in `docs/standards/ios.md` and `docs/standards/android.md`
  keep visual consistency without shared code.
- The `docs/standards/common.md` file defines rules that apply to both platforms.

### Trade-offs Accepted

- If a developer without AI tooling needs to add a feature, they must implement it twice.
- Bugs that exist on both platforms must be fixed twice.

---

## Alternatives Considered

### Flutter

Rejected because:
- 3D avatar rendering performance is inadequate (PlatformView overhead).
- CallLog access on Android not reliably supported.
- Live Activities / Dynamic Island not supported.
- ~15–20 MB larger binary.

### React Native

Rejected because:
- JavaScript bridge adds latency for frequent updates (animation frames, streaming text).
- Worse 3D support than Flutter.
- Weaker typing than Swift or Kotlin.
- Larger binary than Flutter for this use case.

### Flutter + Native Modules for Specific Features

Rejected because:
- If 3D avatar and device APIs require native modules, the Flutter layer adds complexity
  without adding value.
- Debugging cross-language stack traces (Dart → platform channel → Swift/Kotlin) is
  significantly harder than debugging pure native code.
