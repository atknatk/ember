---
name: ios-network-layer test patterns
description: Patterns established during P03-02 iOS network layer testing — MockURLProtocol usage, test file naming, project file update process
type: project
---

The network layer (P03-02) uses `MockURLProtocol` registered on `URLSessionConfiguration.ephemeral` to intercept HTTP in tests. Set `MockURLProtocol.requestHandler` before each test and call `MockURLProtocol.reset()` after. The `MockAuthService` has `shouldThrowOnGetToken` and `shouldThrowOnRefresh` flags plus `getAccessTokenCallCount` and `refreshCallCount` for verification.

**Why:** Established baseline for all future iOS feature tests that use `APIClient`.

**How to apply:** When writing tests for any iOS feature that calls `APIClient`, use this same `makeClient()` pattern with `URLSessionConfiguration.ephemeral` + `MockURLProtocol`. Extended tests go in `*ExtendedTests.swift` files alongside the original test files, not mixed into them. All new test files must be added to `Ember.xcodeproj/project.pbxproj` with a `PBXFileReference`, a `PBXBuildFile`, a group entry under `449A9DA6A1EEE797DF0335ED` (the Network test group), and a Sources build phase entry under `91FC9734A1965EA61C9B43FF`.

The project has 165 total tests for the network layer after P03-02.
