# iOS Network Layer

> Provides the production-ready HTTP and SSE networking infrastructure that all Ember iOS features use to communicate with the backend.

**Status**: Released
**Added in**: Phase 3 (P03-02)
**Platforms**: iOS
**GitHub Issue**: #18

---

## Overview

The iOS network layer replaces the empty protocol stubs created in the P03-01 scaffold with a fully working implementation. It gives every subsequent iOS feature a single, consistent way to make API calls: pass an `APIEndpoint` enum case, get back a decoded Swift value. There is no HTTP boilerplate scattered across feature files.

The layer has three main pieces. `APIEndpoint` is a type-safe enum covering all 19 backend endpoints. `APIClient` is a generic `URLSession`-backed client with three methods — `request<T>`, `requestVoid`, and `streamSSE` — that together handle JSON requests, empty-body DELETE calls, and SSE streaming. `SSEClient.swift` holds the `SSEEvent` enum and `SSEDelegate` class that parse the backend's five SSE event types into Swift values delivered over `AsyncThrowingStream`.

The layer also implements automatic 401 token refresh. When a protected endpoint returns 401, the client calls `AuthServiceProtocol.refreshToken()` and retries the request once. If the retry also fails, or if `refreshToken()` throws, the error becomes `APIError.unauthorized` — a distinct case that signals ViewModels to navigate to the login screen. SSE streams do not retry on 401; they yield an error event and let the calling ViewModel decide how to proceed.

---

## Architecture

### How It Works (Data Flow)

**Standard JSON request:**

1. The caller invokes `apiClient.request(endpoint: .listCharacters, responseType: CharacterListResponse.self)`.
2. `APIClient.buildRequest(endpoint:body:)` constructs a `URLRequest` from `baseURL` + `endpoint.path`, appends `endpoint.queryItems` if present, sets `httpMethod`, and JSON-encodes the body if provided (with `Content-Type: application/json`).
3. Because `.listCharacters.requiresAuth` is `true`, `APIClient` calls `authService.getAccessToken()` and sets `Authorization: Bearer {token}`.
4. `URLSession.data(for:)` executes the request. Any transport error is wrapped in `APIError.networkError`.
5. `handleResponse(data:response:)` casts to `HTTPURLResponse`. For 2xx, it returns `(data, statusCode)`. For non-2xx (excluding 401), it parses `{"detail": "..."}` from the response body and throws `APIError.serverError(statusCode:detail:)`.
6. If `statusCode == 401` and `endpoint.requiresAuth`, the retry path starts: `authService.refreshToken()` is called, the request is rebuilt with the new token, and it executes once more. A second 401 (or a throw from `refreshToken()`) yields `APIError.unauthorized`.
7. The response data is decoded with `JSONDecoder.ember` (snake_case → camelCase) and returned.

**SSE stream:**

1. The caller invokes `apiClient.streamSSE(endpoint: .streamMessage(characterId: id), body: requestBody)`.
2. `APIClient.streamSSE` returns an `AsyncThrowingStream<SSEEvent, Error>` immediately.
3. Inside the stream's `Task`, `buildRequest` constructs the request, adds `Accept: text/event-stream`, and injects the auth token.
4. A dedicated `URLSession` is created with `SSEDelegate` as its delegate.
5. `SSEDelegate.urlSession(_:dataTask:didReceive:data:)` appends incoming UTF-8 text to a buffer and splits on `\n\n` to extract complete SSE event blocks.
6. Each `data: {json}` line is decoded into `SSEPayload`, then mapped to one of the five `SSEEvent` cases and yielded to the `AsyncThrowingStream` continuation.
7. When the stream is cancelled (e.g., user navigates away), `continuation.onTermination` cancels the data task and calls `invalidateAndCancel()` on the delegate session to prevent retain cycles.
8. A normal stream completion or `[DONE]` sentinel finishes the continuation cleanly.

### SSE Event Types

The backend sends JSON objects with a `type` discriminator field. `SSEDelegate` maps each type to a `SSEEvent` case:

| Backend `type` | `SSEEvent` case | Key fields |
|----------------|-----------------|------------|
| `chunk` | `.chunk(content: String)` | `content` — text fragment to append |
| `action` | `.action(action: String, payloadJSON: Data)` | `action` — action name; `payloadJSON` — serialized payload dictionary |
| `done` | `.done(messageId: String)` | `message_id` — UUID of the saved message |
| `error` | `.error(message: String)` | `message` — human-readable error |
| `moderation` | `.moderation(message: String)` | `message` — moderation notice |

The `action` case stores its payload as `Data` rather than `[String: Any]` because `[String: Any]` is not `Sendable`. Call `sseEvent.actionPayload()` to decode the payload into a dictionary on demand.

### 401 Retry Logic

The retry applies only to standard HTTP requests (`request<T>` and `requestVoid`), not SSE streams, and only when `endpoint.requiresAuth` is `true`.

```
initial request → 401?
  ├─ endpoint.requiresAuth = false → throw .serverError(401, ...)
  └─ endpoint.requiresAuth = true →
       authService.refreshToken()
         ├─ throws → throw .unauthorized
         └─ succeeds → retry with new token → 401? → throw .unauthorized
                                             → 2xx → decode and return
```

### Key Files

```
ios/Ember/Core/Network/
  APIEndpoint.swift          # HTTPMethod enum + APIEndpoint enum (all 19 endpoint cases)
  APIClient.swift            # APIClientProtocol + APIClient + AnyEncodable helper
  SSEClient.swift            # SSEEvent enum + SSEDelegate + SSEPayload + AnyCodableValue
  APIError.swift             # APIError enum: unauthorized, serverError, decodingError, networkError
  JSONCoding.swift           # JSONEncoder.ember / JSONDecoder.ember (from P03-01, unmodified)

ios/Ember/Core/Auth/
  AuthService.swift          # AuthServiceProtocol (adds refreshToken()) + stub AuthService

ios/EmberTests/Core/Network/
  APIEndpointTests.swift     # 28 tests for path, method, requiresAuth, queryItems
  APIClientTests.swift       # 20 tests for request/requestVoid, 401 retry, headers, encoding
  SSEClientTests.swift       # 14 tests for SSE parsing, error events, action payload, APIError messages

ios/EmberTests/Mocks/
  MockURLProtocol.swift      # URLProtocol subclass for network interception in tests
  MockAuthService.swift      # AuthServiceProtocol mock with controllable token/refresh behavior
  MockAPIClient.swift        # APIClientProtocol mock for ViewModel unit tests
```

---

## API Reference

This feature adds no new backend endpoints. It creates the iOS client infrastructure for all endpoints documented in [`docs/04-veri-api.md`](../04-veri-api.md).

### Endpoint Coverage

All 19 backend endpoints have a corresponding `APIEndpoint` case:

| Group | Cases |
|-------|-------|
| Auth (public) | `.register`, `.login`, `.refreshToken` |
| Characters | `.listCharacters`, `.createCharacter`, `.updateCharacter(id:)`, `.deleteCharacter(id:)` |
| Chat | `.sendMessage(characterId:)`, `.streamMessage(characterId:)`, `.listMessages(characterId:cursor:limit:)` |
| Memories | `.listMemories(characterId:)`, `.deleteMemory(characterId:memoryId:)`, `.deleteAllMemories(characterId:)` |
| Media | `.uploadURL` |
| Profile | `.getProfile`, `.updateProfile`, `.deleteAccount` |
| Onboarding | `.completeOnboarding` |
| Notifications | `.updateFCMToken`, `.updateNotificationPreferences` |

---

## iOS Implementation

### APIEndpoint

`APIEndpoint` has four computed properties:

- `path: String` — the URL path component, always prefixed with `/api/v1/`. Character IDs and memory IDs are interpolated directly into the path string.
- `method: HTTPMethod` — `.get`, `.post`, `.put`, or `.delete`.
- `requiresAuth: Bool` — `false` only for `.register`, `.login`, `.refreshToken`; `true` for all other cases.
- `queryItems: [URLQueryItem]?` — returns items for `.listMessages(characterId:cursor:limit:)` (`limit` always included; `cursor` omitted when `nil`). Returns `nil` for all other cases.

### APIClientProtocol

```swift
protocol APIClientProtocol: AnyObject, Sendable {
    func request<T: Decodable>(
        endpoint: APIEndpoint,
        body: (any Encodable)?,
        responseType: T.Type
    ) async throws -> T

    func requestVoid(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) async throws

    func streamSSE(
        endpoint: APIEndpoint,
        body: (any Encodable)?
    ) -> AsyncThrowingStream<SSEEvent, Error>
}
```

A protocol extension provides convenience overloads that omit `body:` (defaulting to `nil`). New feature modules call the convenience overloads for `GET` and `DELETE` endpoints and pass a body explicitly for `POST`/`PUT`.

### APIClient

`APIClient` is a `final class` that is `@unchecked Sendable`. The `@unchecked` annotation is safe because `URLSession` is thread-safe and all mutable properties (`encoder`, `decoder`) are set once in `init` and never mutated afterward.

The constructor accepts three optional parameters for testability:

```swift
init(
    baseURL: URL? = nil,
    session: URLSession = .shared,
    authService: AuthServiceProtocol = AuthService.shared
)
```

When `baseURL` is `nil`, the client reads `ProcessInfo.processInfo.environment["API_BASE_URL"]` and falls back to `https://api.ember.ai` if the environment variable is absent. The `static let shared` singleton uses all defaults.

Body encoding uses an internal `AnyEncodable` wrapper to erase the `any Encodable` existential before passing it to `JSONEncoder`. This avoids the "cannot use protocol as generic constraint when it has Self or associated type requirements" compile error.

### SSEEvent

```swift
enum SSEEvent: Sendable {
    case chunk(content: String)
    case action(action: String, payloadJSON: Data)
    case done(messageId: String)
    case error(message: String)
    case moderation(message: String)
}
```

The `action` case stores its arbitrary JSON payload as `Data` for `Sendable` conformance. Decode it with `sseEvent.actionPayload() -> [String: Any]?`.

### SSEDelegate

`SSEDelegate` is a `final class NSObject` that conforms to `URLSessionDataDelegate`. It is not `Sendable` and is confined to the `URLSession` delegate queue. It holds a string `buffer` that accumulates incoming UTF-8 data and processes complete `\n\n`-terminated SSE event blocks as they arrive.

The delegate handles the `[DONE]` sentinel value (from some SSE implementations) as a stream terminator, in addition to processing standard JSON-typed events.

### APIError

```swift
enum APIError: LocalizedError, Equatable {
    case unauthorized
    case serverError(statusCode: Int, detail: String)
    case decodingError(Error)
    case networkError(Error)
}
```

`errorDescription` returns user-facing strings safe to display in the UI:

| Case | Message |
|------|---------|
| `.unauthorized` | "Your session has expired. Please sign in again." |
| `.serverError(429, _)` | "Too many requests. Please wait a moment and try again." |
| `.serverError(500+, _)` | "Something went wrong. Please try again." |
| `.serverError(other, detail)` | The `detail` string from the server response |
| `.decodingError` | "Something went wrong. Please try again." |
| `.networkError` | "Connection failed. Please check your internet and try again." |

`Equatable` conformance is implemented manually because `Error` is not `Equatable`. The `decodingError` and `networkError` cases compare by `localizedDescription`.

### AuthServiceProtocol (Addition)

This feature adds `refreshToken() async throws -> String` to `AuthServiceProtocol`. The stub implementation in `AuthService` throws `AuthError.notImplemented`. The real Cognito implementation is added in the auth feature. Until then, the 401 retry path always resolves to `APIError.unauthorized`.

### Navigation

This feature has no screens and requires no navigation changes.

---

## Testing

### Coverage Summary

| File | Tests | Focus |
|------|-------|-------|
| `APIEndpointTests.swift` | 28 | Path strings, HTTP methods, `requiresAuth` flags, query item generation |
| `APIClientTests.swift` | 20 | Request/response cycle, 401 retry logic, header injection, body encoding, error mapping |
| `SSEClientTests.swift` | 14 | SSE event parsing, partial data buffering, action payload, error events, APIError messages |
| **Total** | **62** | |

All tests use Swift Testing (`import Testing`), not XCTest.

### Test Infrastructure

**`MockURLProtocol`** intercepts HTTP requests at the `URLSession` level without network access. Set `MockURLProtocol.requestHandler` before each test and call `MockURLProtocol.reset()` in teardown. For SSE tests, a `streamHandler` variant delivers data in controllable chunks to exercise the buffer reassembly logic.

Usage:
```swift
let config = URLSessionConfiguration.ephemeral
config.protocolClasses = [MockURLProtocol.self]
let session = URLSession(configuration: config)
let client = APIClient(session: session, authService: MockAuthService())
```

**`MockAuthService`** implements `AuthServiceProtocol`. Key properties:
- `accessToken: String` — returned by `getAccessToken()`
- `refreshedToken: String` — returned by `refreshToken()` on success
- `shouldThrowOnRefresh: Bool` — set to `true` to simulate refresh failure
- `refreshCallCount: Int` — verify the retry called refresh exactly once

**`MockAPIClient`** implements `APIClientProtocol` for use in ViewModel unit tests written in future feature PRs. Set `requestResult`, `requestError`, or `sseEvents` to control behavior.

### Running Tests

```bash
cd ios
xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 16"
```

---

## Known Limitations

- **`refreshToken()` is a stub**: Until the Cognito auth feature is implemented, `AuthService.refreshToken()` throws `AuthError.notImplemented`. Any 401 response on a protected endpoint immediately yields `APIError.unauthorized`, even if the token could theoretically be refreshed.
- **No SSE 401 retry**: SSE streams do not attempt token refresh. A 401 on an SSE connection yields `SSEEvent.error(message: "HTTP 401")` and terminates the stream. The calling ViewModel must handle re-authentication and re-send the message.
- **No request timeout configuration**: `URLSession.shared` is used for standard requests and uses the system default timeouts. Timeout tuning is deferred to a later infrastructure improvement.
- **No request cancellation for standard requests**: `request<T>` and `requestVoid` do not return a cancellation token. Callers can cancel via Swift structured concurrency task cancellation, but there is no explicit cancel handle. SSE streams cancel cleanly via `continuation.onTermination`.

---

## Extending This Feature

### Adding a new endpoint

1. Add a case to `APIEndpoint` in `ios/Ember/Core/Network/APIEndpoint.swift`.
2. Add a `path` case to the `var path: String` switch.
3. Add a `method` case to the `var method: HTTPMethod` switch.
4. Set `requiresAuth` via the `default: return true` rule or add an explicit case.
5. Add `queryItems` logic if the endpoint uses query parameters.
6. Add test cases to `APIEndpointTests.swift` covering the path, method, and any query items.

No changes to `APIClientProtocol` or `APIClient` are required.

### Adding a new SSE event type

1. Add a case to `SSEEvent` in `ios/Ember/Core/Network/SSEClient.swift`.
2. Add a corresponding `case "type_string":` branch to `SSEDelegate.mapPayloadToEvent(_:rawJSON:)`.
3. Add fields to `SSEPayload` if the new event carries new JSON properties.
4. Add test cases to `SSEClientTests.swift`.
5. Update the ViewModel that consumes the stream to handle the new case.

### Injecting a custom base URL (e.g., staging)

Pass `baseURL` to the `APIClient` initializer, or set the `API_BASE_URL` environment variable in the scheme's run configuration. The environment variable is the standard approach for CI and staging environments.

### Writing a ViewModel that uses the network layer

1. Receive `AppContainer` via `@Environment(AppContainer.self)` in the view.
2. Pass `container.apiClient` to the ViewModel initializer (or store it via the container).
3. Use `MockAPIClient` in unit tests by injecting it instead of `APIClient.shared`.

---

## Related Documentation

- [Database Schema and API Contracts](../04-veri-api.md)
- [Mobile Screens and Navigation](../07-mobil.md)
- [iOS Standards](../standards/ios.md)
- [iOS Scaffold](ios-scaffold.md)
- [System Architecture](../03-mimari.md)
