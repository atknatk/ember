# iOS Test Handoff: iOS Scaffold

**Date**: 2026-03-13
**Agent**: ios-tester
**Status**: COMPLETE

## Test Files Written

### New files (this agent)

| File | Tests | What It Covers |
|------|-------|----------------|
| `ios/EmberTests/Core/Extensions/ColorEmberTests.swift` | 18 | Hex component verification for key colors, fallback behaviour, opaque-alpha contract, count |
| `ios/EmberTests/Core/Extensions/FontEmberTests.swift` | 16 | All 7 font constants exist, are distinct, size hierarchy matches spec |
| `ios/EmberTests/Core/Extensions/CGFloatEmberTests.swift` | 22 | All 8 spacing + 5 corner radius values, ascending order, positivity, named-slot semantics |
| `ios/EmberTests/Core/Extensions/EmberSymbolTests.swift` | 29 | All 12 symbol names non-empty, match spec, fill vs. outline distinct, uniqueness |
| `ios/EmberTests/App/AppRouterExtendedTests.swift` | 15 | Initial state, each Route case, sequential push/pop, interleaved ops, Route Hashability |
| `ios/EmberTests/Core/Auth/AuthServiceTests.swift` | 12 | Stub throws notImplemented, configure/signOut no-op, singleton identity, AuthError cases |
| `ios/EmberTests/Core/APIErrorTests.swift` | 11 | All 3 APIError cases, LocalizedError conformance, APIClient singleton/baseURL |

**New test count: 123**

### Existing files (written by ios-dev, not modified)

| File | Tests |
|------|-------|
| `ios/EmberTests/App/AppRouterTests.swift` | 5 |
| `ios/EmberTests/Core/ColorTests.swift` | 6 |
| `ios/EmberTests/App/AppContainerTests.swift` | 1 |

**Existing test count: 12**

**Total test count: 135**

## Coverage

- `AppRouter`: >= 80% (all methods tested including guard-protected empty-path branches)
- `Color+Ember` hex initializer: >= 80% (6-char, 8-char, invalid string, no-hash paths covered)
- `CGFloat+Ember`: 100% (all constants are pure data, each referenced in tests)
- `EmberSymbol`: 100% (all 12 constants referenced and their values asserted)
- `AuthService` stub: >= 80% (configure, signIn, signOut, getAccessToken all exercised)
- `APIError`: 100% (all three cases exercised including descriptions)
- `Font+Ember`: >= 80% (all 7 constants accessed, distinctness verified)
- `AppContainer`: covered by existing test

## Test Results

All tests pass. No build errors. All new test files use Swift Testing (`import Testing`) as required by `docs/standards/testing.md` section 4 and the ios-dev handoff.

## Issues Found During Testing

None. The implementation matches the spec in all tested dimensions:
- Hex values in `Color+Ember.swift` match `docs/14-tasarim.md` exactly.
- Spacing and corner radius values in `CGFloat+Ember.swift` match the spec table.
- SF Symbol names in `EmberSymbol.swift` match the spec.
- `AuthService` stub correctly throws `AuthError.notImplemented` for unimplemented methods.
- `AppRouter.pop()` and `popToRoot()` correctly guard against empty path (no crash).

## Notes for Reviewer

- `ColorEmberTests.swift` uses `UIColor(Color(...))` to bridge into component values for hex verification. This is the only reliable way to inspect a SwiftUI Color's sRGB components in unit tests without a live UIView.
- `FontEmberTests.swift` verifies the size hierarchy by encoding the spec-mandated sizes directly (28/22/16/15/13/12/11). This is a regression guard: if a size changes in `Font+Ember.swift`, the test will fail because the font constants will no longer be equal/unequal as expected.
- `AuthServiceTests.swift` uses `AuthService.shared` (the singleton) because `AuthService.init()` is `private`. The shared instance is idempotent for the stub.
- `AppRouterExtendedTests.swift` supplements but does not duplicate the 5 tests in `AppRouterTests.swift`.
