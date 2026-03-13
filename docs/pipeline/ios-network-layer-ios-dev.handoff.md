# iOS Dev Handoff: iOS Network Layer

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### Created
- `ios/Ember/Core/Network/APIEndpoint.swift` -- Type-safe enum for all backend endpoints with path, method, requiresAuth, queryItems
- `ios/Ember/Core/Network/SSEClient.swift` -- SSEEvent enum, SSEDelegate (URLSessionDataDelegate), SSE JSON parsing
- `ios/EmberTests/Core/Network/APIEndpointTests.swift` -- 28 tests covering path, method, requiresAuth, queryItems
- `ios/EmberTests/Core/Network/APIClientTests.swift` -- 20 tests covering request/requestVoid/streamSSE, 401 retry, headers, encoding
- `ios/EmberTests/Core/Network/SSEClientTests.swift` -- 14 tests covering SSE parsing, error events, action payload, APIError messages
- `ios/EmberTests/Mocks/MockURLProtocol.swift` -- URLProtocol subclass for intercepting HTTP in tests
- `ios/EmberTests/Mocks/MockAuthService.swift` -- Mock AuthServiceProtocol with controllable token/refresh behavior
- `ios/EmberTests/Mocks/MockAPIClient.swift` -- Mock APIClientProtocol for future ViewModel tests

### Modified
- `ios/Ember/Core/Network/APIClient.swift` -- Full implementation: generic request<T>, requestVoid, streamSSE with 401 retry
- `ios/Ember/Core/Network/APIError.swift` -- Enhanced with unauthorized, serverError(statusCode:detail:), Equatable conformance, user-facing messages
- `ios/Ember/Core/Auth/AuthService.swift` -- Added refreshToken() to protocol and stub implementation
- `ios/EmberTests/Core/APIErrorTests.swift` -- Updated to use new serverError case (replaced httpError references)
- `ios/Ember.xcodeproj/project.pbxproj` -- Added all new files to project and targets

## Screens Implemented
- None (this is a Core/Network infrastructure feature)

## Deviations from Spec
- None

## Notes for iOS Tester

### Mock Patterns
- `MockURLProtocol`: Register with `URLSessionConfiguration.ephemeral`, set `protocolClasses = [MockURLProtocol.self]`. Set `MockURLProtocol.requestHandler` before each test, call `MockURLProtocol.reset()` in teardown.
- `MockAuthService`: Implements `AuthServiceProtocol`. Control token values via `accessToken`/`refreshedToken` properties. Set `shouldThrowOnRefresh = true` to simulate refresh failure. Check `refreshCallCount` to verify retry logic.
- `MockAPIClient`: Implements `APIClientProtocol`. Set `requestResult` for success, `requestError` for failure, `sseEvents` for stream tests.

### Key Test Scenarios
- **401 Retry**: `APIClient.request` with 401 response calls `authService.refreshToken()` once, retries with new token. If retry also 401 or refresh throws, throws `APIError.unauthorized`.
- **Public endpoint 401**: Register/login/refreshToken endpoints do NOT attempt token refresh on 401.
- **SSE parsing**: SSEDelegate buffers partial data, splits on `\n\n`, parses `data: {json}` lines into typed SSEEvent cases.
- **Sendable safety**: `SSEEvent.action` stores payload as `Data` (not `[String: Any]`). Use `actionPayload()` convenience to decode.
- **AnyEncodable**: The `body: (any Encodable)?` parameter is wrapped in an internal `AnyEncodable` struct for type erasure.

### What to Verify
1. All 62 tests pass (28 endpoint + 20 client + 14 SSE)
2. `APIClient.shared` singleton returns same instance
3. `baseURL` defaults to `https://api.ember.ai` when env var not set
4. Request bodies encoded with snake_case keys
5. Response bodies decoded from snake_case to camelCase
6. Authorization header set only for `requiresAuth` endpoints
7. Content-Type header set only for POST/PUT with body
8. SSE stream correctly yields chunk, action, done, error, moderation events
9. Network errors wrapped in `APIError.networkError`
10. `APIError.errorDescription` returns user-facing messages per spec
