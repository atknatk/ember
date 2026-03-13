# Feature Spec: P03-02 -- iOS Network Layer

**Feature ID**: P03-02
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #18
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements the full iOS networking layer: a production-ready `APIClient` class backed by `URLSession`, generic request/response methods using `Codable`, an `SSEClient` for Server-Sent Events streaming via `AsyncThrowingStream`, an `APIEndpoint` enum for type-safe endpoint definitions, automatic `Authorization: Bearer` header injection, and automatic 401 retry logic (refresh the Cognito token via `AuthServiceProtocol`, then retry the request once).

### Why It Exists

Every subsequent iOS feature that communicates with the Ember backend (character list, chat, memories, profile, onboarding) depends on a working network layer. The P03-01 scaffold created empty stubs for `APIClientProtocol` and `APIClient`. This feature replaces those stubs with real implementations so that downstream features can call `apiClient.request(...)` and `apiClient.streamSSE(...)` without reimplementing HTTP boilerplate.

### Dependencies

- **P03-01** (ios-scaffold) -- provides `APIClient.swift` (stub), `APIError.swift`, `JSONCoding.swift`, `AuthService.swift` (stub), `AuthError.swift`, `AppContainer.swift`. All of these files are MODIFIED by this feature.

### What This Feature Does NOT Do

- It does not implement specific API calls (listCharacters, sendMessage, etc.). Those are added by each feature's PR.
- It does not implement the real Cognito `AuthService`. The token refresh retry logic calls `AuthServiceProtocol.getAccessToken()` and `AuthServiceProtocol.refreshToken()`, which remain stubs until the auth feature.
- It does not implement any UI changes.
- It does not add backend changes.

---

## 2. Data Models

No database changes. This is an iOS-only feature.

---

## 3. API Endpoints

No new API endpoints. This feature creates the iOS client infrastructure that calls existing backend endpoints documented in `docs/04-veri-api.md`.

The network layer must support all endpoint patterns from the backend:

| Method | Path Pattern | Content-Type (Response) | Used By |
|--------|-------------|-------------------------|---------|
| POST | `/api/v1/auth/register` | `application/json` | Auth |
| POST | `/api/v1/auth/login` | `application/json` | Auth |
| POST | `/api/v1/auth/refresh` | `application/json` | Token refresh |
| GET | `/api/v1/characters` | `application/json` | Character list |
| POST | `/api/v1/characters` | `application/json` | Character creation |
| PUT | `/api/v1/characters/:id` | `application/json` | Character update |
| DELETE | `/api/v1/characters/:id` | (no body) | Character delete |
| POST | `/api/v1/characters/:id/messages` | `text/event-stream` | Chat SSE |
| GET | `/api/v1/characters/:id/messages` | `application/json` | Message history |
| GET | `/api/v1/characters/:id/memories` | `application/json` | Memory list |
| DELETE | `/api/v1/characters/:id/memories/:memId` | (no body) | Memory delete |
| POST | `/api/v1/media/upload-url` | `application/json` | Media upload |
| GET | `/api/v1/profile` | `application/json` | Profile |
| PUT | `/api/v1/profile` | `application/json` | Profile update |
| DELETE | `/api/v1/profile/account` | (no body) | Account delete |

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature.

---

## 5. iOS Screens and Components

This feature has no screens. It modifies and creates Core/Network files only.

### 5.1 APIEndpoint Enum

**File**: `ios/Ember/Core/Network/APIEndpoint.swift` (CREATE)

A type-safe enum that encapsulates endpoint path, HTTP method, and query parameters. This avoids raw string paths scattered across the codebase.

```
enum APIEndpoint {
    // Auth (public, no token needed)
    case register
    case login
    case refreshToken

    // Characters
    case listCharacters
    case createCharacter
    case updateCharacter(id: String)
    case deleteCharacter(id: String)

    // Chat
    case sendMessage(characterId: String)
    case streamMessage(characterId: String)
    case listMessages(characterId: String, cursor: String?, limit: Int)

    // Memories
    case listMemories(characterId: String)
    case deleteMemory(characterId: String, memoryId: String)
    case deleteAllMemories(characterId: String)

    // Media
    case uploadURL

    // Profile
    case getProfile
    case updateProfile
    case deleteAccount

    // Onboarding
    case completeOnboarding

    // Notifications
    case updateFCMToken
    case updateNotificationPreferences
}
```

Properties on `APIEndpoint`:

- `var path: String` -- returns the URL path component (e.g., `/api/v1/characters`). All paths are prefixed with `/api/v1/`.
- `var method: HTTPMethod` -- returns `.get`, `.post`, `.put`, or `.delete`.
- `var requiresAuth: Bool` -- returns `false` for `register`, `login`, `refreshToken`; `true` for all others.
- `var queryItems: [URLQueryItem]?` -- returns query parameters for endpoints that need them (e.g., `listMessages` returns `cursor` and `limit` items). Returns `nil` when no query params.

`HTTPMethod` is a simple string enum: `enum HTTPMethod: String { case get = "GET", post = "POST", put = "PUT", delete = "DELETE" }`. Defined in the same file.

### 5.2 APIClient (Full Implementation)

**File**: `ios/Ember/Core/Network/APIClient.swift` (MODIFY -- replace stub)

The existing stub has `APIClientProtocol` with no methods and `APIClient` with only `baseURL`. This feature replaces it entirely.

#### APIClientProtocol

```
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

Default parameter values: `body` defaults to `nil` in both `request` and `requestVoid`. These defaults are provided via protocol extension methods that call the main methods.

#### APIClient Class

```
final class APIClient: APIClientProtocol, @unchecked Sendable {
    static let shared = APIClient()

    private let baseURL: URL
    private let session: URLSession
    private let authService: AuthServiceProtocol
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
}
```

**Constructor**:
- `init(baseURL: URL, session: URLSession, authService: AuthServiceProtocol)`
- `baseURL` defaults to the value from `ProcessInfo.processInfo.environment["API_BASE_URL"]` or `"https://api.ember.ai/"`
- `session` defaults to `URLSession.shared`
- `authService` defaults to `AuthService.shared`
- `encoder` is set to `JSONEncoder.ember`
- `decoder` is set to `JSONDecoder.ember`
- Private `init()` (for `shared` singleton) calls the full init with defaults

**`request<T>` method implementation**:

1. Build a `URLRequest` via the private `buildRequest(endpoint:body:)` method.
2. If `endpoint.requiresAuth`, call `authService.getAccessToken()` and set the `Authorization: Bearer {token}` header.
3. Execute the request with `session.data(for: request)`.
4. Call the private `handleResponse(data:response:)` method.
5. If the response is 401 and the endpoint requires auth, enter the **retry path**:
   a. Call `authService.refreshToken()` to get a new access token.
   b. Rebuild the request with the new token.
   c. Execute the request again.
   d. If this second request also fails with 401, throw `APIError.unauthorized`.
   e. If `refreshToken()` itself throws, throw `APIError.unauthorized`.
6. Decode the response body as `T` using `JSONDecoder.ember`. If decoding fails, throw `APIError.decodingError(underlyingError)`.
7. Return the decoded value.

**`requestVoid` method implementation**:

Same as `request<T>` but does not decode the response body. Used for DELETE endpoints that return 204 No Content. Still validates the HTTP status code.

**`streamSSE` method implementation**:

1. Build a `URLRequest` via `buildRequest(endpoint:body:)`.
2. Set `Accept: text/event-stream` header.
3. If `endpoint.requiresAuth`, set the `Authorization` header.
4. Return an `AsyncThrowingStream<SSEEvent, Error>`.
5. Inside the stream's closure, create a `URLSession` with a custom `SSEDelegate` (Section 5.3) as its delegate.
6. Start a `dataTask` with the request.
7. The `SSEDelegate` parses incoming data and yields `SSEEvent` values to the continuation.
8. On `continuation.onTermination`, cancel the data task and invalidate the delegate session.
9. No automatic 401 retry for SSE streams. If the initial SSE response is 401, the delegate yields an `SSEEvent.error` and finishes the stream. The caller (ViewModel) handles re-authentication.

**Private helper methods**:

- `buildRequest(endpoint:body:) -> URLRequest`:
  - Constructs `URL` from `baseURL` + `endpoint.path`.
  - Appends `endpoint.queryItems` if present.
  - Sets `httpMethod` from `endpoint.method.rawValue`.
  - Sets `Content-Type: application/json` for POST/PUT methods.
  - Encodes `body` if provided using `JSONEncoder.ember`.

- `handleResponse(data:response:) throws -> (Data, Int)`:
  - Casts `URLResponse` to `HTTPURLResponse`.
  - Returns `(data, statusCode)`.
  - Throws `APIError.httpError(statusCode:detail:)` for non-2xx status codes (except 401, which is handled by the retry logic in `request`).
  - Attempts to decode the error body as `{"detail": "..."}` to extract the server error message. Falls back to a generic message.

### 5.3 SSEClient and SSEDelegate

**File**: `ios/Ember/Core/Network/SSEClient.swift` (CREATE)

#### SSEEvent Enum

```
enum SSEEvent: Sendable {
    case chunk(content: String)
    case action(action: String, payload: [String: Any])
    case done(messageId: String)
    case error(message: String)
    case moderation(message: String)
}
```

Note: `payload` in `action` is `[String: Any]` (not `Codable`) because the backend sends arbitrary JSON dictionaries. For `Sendable` conformance, the `action` case stores the raw JSON `Data` instead, and provides a computed property to decode it.

Revised approach for Sendable safety:

```
enum SSEEvent: Sendable {
    case chunk(content: String)
    case action(action: String, payloadJSON: Data)
    case done(messageId: String)
    case error(message: String)
    case moderation(message: String)
}
```

A convenience method `SSEEvent.actionPayload() -> [String: Any]?` decodes `payloadJSON` via `JSONSerialization`.

#### SSEDelegate

`SSEDelegate` is a `private final class` conforming to `URLSessionDataDelegate`. It is NOT `Sendable` (it is confined to the URLSession delegate queue).

Properties:
- `private let continuation: AsyncThrowingStream<SSEEvent, Error>.Continuation`
- `private var buffer: String = ""`

Methods:

- `urlSession(_:dataTask:didReceive response:completionHandler:)`:
  - Checks the HTTP status code. If non-2xx, yields an `SSEEvent.error` with the status code and finishes the stream.
  - Calls `completionHandler(.allow)`.

- `urlSession(_:dataTask:didReceive data:)`:
  - Appends incoming `Data` (UTF-8 decoded) to `buffer`.
  - Splits on `\n\n` to extract complete SSE events.
  - For each complete event line starting with `data: `:
    - Strips the `data: ` prefix.
    - Decodes the JSON to determine `type`.
    - Maps to the appropriate `SSEEvent` case:
      - `"chunk"` -> `SSEEvent.chunk(content:)` -- extracts `content` field.
      - `"action"` -> `SSEEvent.action(action:payloadJSON:)` -- extracts `action` string and re-serializes `payload` to Data.
      - `"done"` -> `SSEEvent.done(messageId:)` -- extracts `message_id` field.
      - `"error"` -> `SSEEvent.error(message:)` -- extracts `message` field.
      - `"moderation"` -> `SSEEvent.moderation(message:)` -- extracts `message` field.
    - Yields the event to the continuation.

- `urlSession(_:task:didCompleteWithError:)`:
  - If error is non-nil and is not a cancellation, finish the stream with the error wrapped in `APIError.networkError`.
  - If error is nil (normal completion), finish the stream normally.

#### JSON Parsing for SSE

A private `struct SSEPayload: Decodable` with fields `type: String`, `content: String?`, `action: String?`, `payload: [String: AnyCodable]?`, `messageId: String?`, `message: String?` is used for initial type discrimination. The `messageId` field uses `CodingKeys` to map from `message_id` (snake_case from the backend). Alternatively, since `JSONDecoder.ember` uses `.convertFromSnakeCase`, the property can be named `messageId` directly.

### 5.4 APIError (Enhanced)

**File**: `ios/Ember/Core/Network/APIError.swift` (MODIFY)

The existing enum has three cases. This feature extends it with additional cases needed for the full network layer.

Current cases (keep as-is):
- `.httpError(statusCode: Int)`
- `.decodingError(Error)`
- `.networkError(Error)`

New cases to add:
- `.unauthorized` -- 401 after token refresh retry failed. Distinct from `.httpError(statusCode: 401)` to signal that the caller should navigate to login.
- `.serverError(statusCode: Int, detail: String)` -- non-2xx with a parsed error body. The existing `.httpError` is replaced by this richer variant. Keeping `.httpError` for backwards compatibility is acceptable but the new network layer should prefer `.serverError`.

Revised enum:

```
enum APIError: LocalizedError, Equatable {
    case unauthorized
    case serverError(statusCode: Int, detail: String)
    case decodingError(Error)
    case networkError(Error)

    var errorDescription: String? { ... }

    // Equatable conformance: decodingError and networkError compare by localizedDescription
    static func == (lhs: APIError, rhs: APIError) -> Bool { ... }
}
```

The `errorDescription` should return user-facing messages per `docs/standards/common.md` Section 7:
- `.unauthorized` -> "Your session has expired. Please sign in again."
- `.serverError(429, _)` -> "Too many requests. Please wait a moment and try again."
- `.serverError(500..., _)` -> "Something went wrong. Please try again."
- `.serverError(_, detail)` -> the `detail` string from the server.
- `.decodingError` -> "Something went wrong. Please try again."
- `.networkError` -> "Connection failed. Please check your internet and try again."

### 5.5 AuthServiceProtocol (Enhanced)

**File**: `ios/Ember/Core/Auth/AuthService.swift` (MODIFY)

The existing protocol has `configure()`, `signIn(username:password:)`, `signOut()`, `getAccessToken()`. The network layer's 401 retry logic needs a `refreshToken()` method.

Add to `AuthServiceProtocol`:
```
func refreshToken() async throws -> String
```

This method should:
1. Call the backend's `POST /api/v1/auth/refresh` endpoint (or, when Amplify is integrated, `Amplify.Auth.fetchAuthSession()`).
2. Return the new access token string.
3. Throw `AuthError.tokenUnavailable` if refresh fails.

Add to `AuthService` (stub implementation):
```
func refreshToken() async throws -> String {
    throw AuthError.notImplemented
}
```

The real implementation will be added in the Cognito auth feature.

### 5.6 AppContainer (No Change)

**File**: `ios/Ember/App/AppContainer.swift`

No changes required. `AppContainer` already holds `apiClient: APIClientProtocol` and `authService: AuthServiceProtocol`. The updated `APIClient.shared` singleton automatically picks up `AuthService.shared` for token injection.

However, `APIClient`'s constructor should accept `authService` as a parameter for testability. The `shared` singleton uses `AuthService.shared`. When constructing `APIClient` for tests, a `MockAuthService` is injected.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature.

---

## 7. Test Plan

### Unit Tests

All tests use Swift Testing (`import Testing`) as the primary framework, per `docs/standards/ios.md` Section 14.

#### APIEndpoint Tests

**File**: `ios/EmberTests/Core/Network/APIEndpointTests.swift`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `APIEndpoint.listCharacters.path` | `"/api/v1/characters"` |
| 2 | `APIEndpoint.sendMessage(characterId: "abc").path` | `"/api/v1/characters/abc/messages"` |
| 3 | `APIEndpoint.streamMessage(characterId: "abc").path` | `"/api/v1/characters/abc/messages"` |
| 4 | `APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 20).queryItems` | Contains `limit=20`, no `cursor` |
| 5 | `APIEndpoint.listMessages(characterId: "abc", cursor: "xyz", limit: 30).queryItems` | Contains `cursor=xyz` and `limit=30` |
| 6 | `APIEndpoint.register.requiresAuth` | `false` |
| 7 | `APIEndpoint.listCharacters.requiresAuth` | `true` |
| 8 | `APIEndpoint.sendMessage(characterId: "abc").method` | `.post` |
| 9 | `APIEndpoint.listCharacters.method` | `.get` |
| 10 | `APIEndpoint.deleteCharacter(id: "abc").method` | `.delete` |
| 11 | `APIEndpoint.deleteAccount.path` | `"/api/v1/profile/account"` |

#### APIClient Tests

**File**: `ios/EmberTests/Core/Network/APIClientTests.swift`

Uses `MockURLProtocol` (a custom `URLProtocol` subclass) to intercept HTTP requests without hitting the network, and `MockAuthService` for token injection.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `request` with 200 response and valid JSON | Returns decoded object |
| 2 | `request` with 200 response and invalid JSON | Throws `APIError.decodingError` |
| 3 | `request` with 404 response and `{"detail": "Not found"}` | Throws `APIError.serverError(statusCode: 404, detail: "Not found")` |
| 4 | `request` with 500 response | Throws `APIError.serverError(statusCode: 500, ...)` |
| 5 | `request` with 401 response, then refresh succeeds, retry returns 200 | Returns decoded object; `refreshToken()` was called once |
| 6 | `request` with 401 response, refresh succeeds, retry returns 401 again | Throws `APIError.unauthorized` |
| 7 | `request` with 401 response, `refreshToken()` throws | Throws `APIError.unauthorized` |
| 8 | `request` on a `requiresAuth: false` endpoint with 401 | Throws `APIError.serverError(statusCode: 401, ...)` -- does NOT attempt refresh |
| 9 | `requestVoid` with 204 response | Completes without error |
| 10 | `requestVoid` with 403 response | Throws `APIError.serverError(statusCode: 403, ...)` |
| 11 | `request` sets `Authorization: Bearer {token}` header for auth endpoints | Verify via `MockURLProtocol` that the header was sent |
| 12 | `request` sets `Content-Type: application/json` for POST body | Verify via `MockURLProtocol` |
| 13 | `request` does NOT set `Authorization` header for public endpoints | Verify via `MockURLProtocol` |
| 14 | `request` encodes body with snake_case keys | Request body JSON has `snake_case` keys |
| 15 | `request` decodes response with snake_case keys to camelCase properties | Decoded object has correct values |
| 16 | Network error (no connection) | Throws `APIError.networkError` |

#### SSE Tests

**File**: `ios/EmberTests/Core/Network/SSEClientTests.swift`

Tests SSE event parsing by feeding raw SSE text data through a `MockURLProtocol` that simulates chunked delivery.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Stream with three chunk events + done | Yields 3 `.chunk` events then `.done`, stream finishes |
| 2 | Stream with an error event | Yields `.error(message:)` |
| 3 | Stream with an action event | Yields `.action(action:payloadJSON:)` with correct action string |
| 4 | Stream with a moderation event then chunks then done | Yields `.moderation`, chunks, then `.done` in order |
| 5 | Partial data delivery (event split across two data callbacks) | Buffer correctly reassembles and yields complete event |
| 6 | Stream receives HTTP 401 | Yields `.error` with status info and finishes |
| 7 | Stream cancelled via `continuation.onTermination` | Data task is cancelled, no crash |
| 8 | Empty `data:` line (keep-alive) | Ignored, no event yielded |

#### Mock Types

**File**: `ios/EmberTests/Mocks/MockURLProtocol.swift` (CREATE)

A `URLProtocol` subclass for testing:
- Class-level `requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data?))?`
- In `startLoading()`, calls the handler and sends the response via `client`.
- For SSE tests, supports a `streamHandler` variant that delivers data in chunks with controlled timing.

**File**: `ios/EmberTests/Mocks/MockAuthService.swift` (CREATE)

Implements `AuthServiceProtocol`:
- `var accessToken: String = "mock-access-token"`
- `var refreshedToken: String = "mock-refreshed-token"`
- `var shouldThrowOnRefresh: Bool = false`
- `var refreshCallCount: Int = 0`
- `getAccessToken()` returns `accessToken`
- `refreshToken()` increments `refreshCallCount`, returns `refreshedToken` or throws based on `shouldThrowOnRefresh`
- Other methods are no-ops or throw `.notImplemented`

**File**: `ios/EmberTests/Mocks/MockAPIClient.swift` (CREATE)

Implements `APIClientProtocol` for use by future ViewModel tests:
- `var requestResult: Any?`
- `var requestError: Error?`
- `var sseEvents: [SSEEvent] = []`
- `request<T>` returns `requestResult as! T` or throws `requestError`
- `requestVoid` throws `requestError` if set
- `streamSSE` yields events from `sseEvents` array

---

## 8. Acceptance Criteria

1. Given the `APIClient` is initialized, when inspecting `baseURL`, then it equals the value from `ProcessInfo.processInfo.environment["API_BASE_URL"]` or falls back to `"https://api.ember.ai/"`.

2. Given a call to `apiClient.request(endpoint: .listCharacters, responseType: SomeDecodable.self)`, when the backend returns 200 with valid JSON, then the method returns the decoded object with `snake_case` keys mapped to `camelCase` Swift properties.

3. Given a call to `apiClient.request(endpoint: .listCharacters, ...)`, when the backend returns 404 with `{"detail": "Not found"}`, then the method throws `APIError.serverError(statusCode: 404, detail: "Not found")`.

4. Given a call to `apiClient.request(endpoint: .listCharacters, ...)`, when the backend returns 401, then the client calls `authService.refreshToken()` once, rebuilds the request with the new token, and retries.

5. Given the 401 retry path, when the retry also returns 401, then the method throws `APIError.unauthorized` (does not loop).

6. Given the 401 retry path, when `refreshToken()` throws, then the method throws `APIError.unauthorized`.

7. Given a call to `apiClient.request(endpoint: .register, ...)` (a public endpoint), when the backend returns 401, then the client does NOT attempt token refresh and instead throws `APIError.serverError(statusCode: 401, ...)`.

8. Given a call to `apiClient.requestVoid(endpoint: .deleteCharacter(id: "abc"))`, when the backend returns 204, then the method completes without error.

9. Given a call to `apiClient.streamSSE(endpoint: .streamMessage(characterId: "abc"), body: someBody)`, when the backend streams `data: {"type":"chunk","content":"Hello"}`, then the `AsyncThrowingStream` yields `SSEEvent.chunk(content: "Hello")`.

10. Given an SSE stream, when the backend sends `data: {"type":"done","message_id":"uuid-123"}`, then the stream yields `SSEEvent.done(messageId: "uuid-123")` and finishes.

11. Given an SSE stream, when the backend sends `data: {"type":"error","message":"AI service temporarily unavailable"}`, then the stream yields `SSEEvent.error(message: "AI service temporarily unavailable")`.

12. Given an SSE stream, when the backend sends `data: {"type":"action","action":"SET_ALARM","payload":{"time":"07:00"}}`, then the stream yields `SSEEvent.action(action: "SET_ALARM", payloadJSON: ...)` where the payload data can be decoded to `{"time":"07:00"}`.

13. Given an authenticated endpoint request, when the request is sent, then the `Authorization: Bearer {token}` header is present in the HTTP request.

14. Given a POST or PUT request with a body, when the request is sent, then the body is JSON-encoded with `snake_case` keys and `Content-Type: application/json` is set.

15. Given the `APIEndpoint.listMessages(characterId: "abc", cursor: "xyz", limit: 30)`, when its `queryItems` are inspected, then they contain `cursor=xyz` and `limit=30`.

16. Given all unit tests, when they are run, then all tests pass with zero failures and line coverage is at least 80%.

---

## 9. File Manifest

```
iOS:
  CREATE  ios/Ember/Core/Network/APIEndpoint.swift
  CREATE  ios/Ember/Core/Network/SSEClient.swift
  MODIFY  ios/Ember/Core/Network/APIClient.swift
  MODIFY  ios/Ember/Core/Network/APIError.swift
  MODIFY  ios/Ember/Core/Auth/AuthService.swift

Tests:
  CREATE  ios/EmberTests/Core/Network/APIEndpointTests.swift
  CREATE  ios/EmberTests/Core/Network/APIClientTests.swift
  CREATE  ios/EmberTests/Core/Network/SSEClientTests.swift
  CREATE  ios/EmberTests/Mocks/MockURLProtocol.swift
  CREATE  ios/EmberTests/Mocks/MockAuthService.swift
  CREATE  ios/EmberTests/Mocks/MockAPIClient.swift

Shared:
  CREATE  shared/feature-specs/ios-network-layer.md         (this file)
  CREATE  docs/pipeline/ios-network-layer-architect.handoff.md
```

| Action | Count |
|--------|-------|
| CREATE | 8 |
| MODIFY | 3 |

---

## 10. Design Decisions and Rationale

### Why generic `request<T>` instead of per-endpoint methods on APIClientProtocol

The P03-01 scaffold and `docs/standards/ios.md` show a protocol with specific methods like `listMessages(characterId:cursor:limit:)`. This approach requires modifying `APIClientProtocol` every time a new endpoint is added. Instead, this spec defines three generic methods (`request<T>`, `requestVoid`, `streamSSE`) that accept an `APIEndpoint` enum value. Each downstream feature adds new cases to `APIEndpoint` without touching the protocol. Feature-specific convenience methods can be added as protocol extensions or on feature-level service classes.

### Why `APIEndpoint` enum instead of raw string paths

Type safety. Misspelled paths are caught at compile time. Query parameter construction is centralized. The `requiresAuth` property eliminates manual tracking of which endpoints need tokens. Future features add cases to the enum, which is a clean extension point.

### Why `SSEEvent` enum instead of raw strings

The backend sends structured JSON events with a `type` discriminator (see `backend/app/schemas/chat.py`). Parsing these into a typed enum at the network layer means ViewModels do not need to parse JSON themselves. The five event types (`chunk`, `action`, `done`, `error`, `moderation`) map 1:1 to the backend's SSE event models.

### Why `payloadJSON: Data` instead of `[String: Any]` for action events

`[String: Any]` is not `Sendable`. Since `SSEEvent` must be `Sendable` (it is yielded from an `AsyncThrowingStream` across actor boundaries), the payload is stored as raw `Data`. A convenience method decodes it on demand.

### Why no automatic 401 retry for SSE streams

SSE streams are long-lived connections. Retrying mid-stream after a 401 would lose context (the user's message would need to be re-sent). Instead, the stream yields an error event. The calling ViewModel can prompt re-authentication and then re-send the message. This keeps the retry logic simple and predictable.

### Why `MockURLProtocol` instead of mocking URLSession

`URLSession` cannot be subclassed effectively for testing. The standard iOS testing pattern is a custom `URLProtocol` registered with a test-specific `URLSessionConfiguration`. This intercepts requests at the system level and allows full control over responses, status codes, and data delivery timing (important for SSE chunk tests).

### Why `refreshToken()` added to AuthServiceProtocol

The 401 retry logic needs to refresh the Cognito token. `getAccessToken()` returns the cached token, but after a 401, the client needs to force a refresh. Separating the two methods keeps the contract clear: `getAccessToken()` returns what is available; `refreshToken()` explicitly forces a refresh and returns the new token.

### Relationship to docs/standards/ios.md Section 4-5

The iOS standards doc provides example implementations for `APIClient` and `SSEClient`. This spec follows the same patterns but with several differences:
- Generic methods instead of per-endpoint methods.
- `APIEndpoint` enum instead of raw paths.
- `SSEEvent` typed enum instead of raw string yields.
- Automatic 401 retry (not shown in the standards doc).
- `@unchecked Sendable` on `APIClient` (same as existing scaffold).

The standards doc is a guide, not a rigid template. This spec is the authoritative reference for this feature.

---

## 11. Notes for Developers

### For ios-dev

- The existing `APIClient.swift` has a `private init()` with no parameters. You need to change this to a parameterized `init` (with defaults) so tests can inject `MockAuthService` and a test `URLSession`. Keep the `static let shared` singleton that calls the default init.
- `JSONCoding.swift` is not modified. The existing `JSONEncoder.ember` and `JSONDecoder.ember` are used by `APIClient`.
- The `sendMessage` and `streamMessage` endpoints share the same path (`/characters/:id/messages`) but differ in HTTP method behavior (both POST). The difference is in the `Accept` header: `streamMessage` sets `Accept: text/event-stream`. The backend uses the same route for both -- it always returns SSE. The non-streaming `sendMessage` variant is not used in practice (the app always streams), but `APIEndpoint` should still have both cases for completeness. In implementation, they can map to the same path.
- For `MockURLProtocol`, register it with `URLSessionConfiguration.ephemeral` and set `protocolClasses = [MockURLProtocol.self]`. Create the test `URLSession` with this configuration. Pass it to `APIClient(session:)`.
- The `SSEDelegate` should NOT retain a strong reference to the `URLSession` it is a delegate of, to avoid retain cycles. The `URLSession` is created inside the `streamSSE` method and invalidated on termination.
- All `@unchecked Sendable` usages must be documented with a comment explaining why they are safe (e.g., "URLSession is thread-safe; mutable state is only accessed from the delegate queue").
