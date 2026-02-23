# Ember iOS Coding Standards

Swift 5.10 / SwiftUI / iOS 17+

This document is the authoritative reference for all iOS development on the Ember project.
Zero-memory sessions must follow every rule here without exception.

---

## Table of Contents

1. Project Structure
2. @Observable Pattern (iOS 17+)
3. Navigation: NavigationStack + NavigationPath
4. Network Layer: URLSession + Codable + async/await
5. SSE Streaming: URLSession + AsyncStream
6. AWS Amplify Cognito Integration
7. Kingfisher for Network Images
8. SF Symbols Usage
9. Dark Mode
10. Color and Typography System
11. Error Handling in SwiftUI
12. Haptic Feedback
13. Accessibility
14. Swift Testing and XCTest Patterns
15. Protocol-Based Dependency Injection

---

## 1. Project Structure

```
EmberApp/
  App/
    EmberApp.swift             # @main entry point
    AppContainer.swift         # Dependency container (root DI)
  Features/
    Auth/
      AuthViewModel.swift
      LoginView.swift
      SignUpView.swift
    Characters/
      CharacterListViewModel.swift
      CharacterListView.swift
      CharacterDetailView.swift
    Chat/
      ChatViewModel.swift
      ChatView.swift
      MessageBubbleView.swift
    Memory/
      MemoryListViewModel.swift
      MemoryListView.swift
    Settings/
      SettingsViewModel.swift
      SettingsView.swift
  Core/
    Network/
      APIClient.swift          # URLSession wrapper
      APIEndpoint.swift        # Endpoint definitions
      SSEClient.swift          # Server-Sent Events client
    Auth/
      AuthService.swift        # Amplify wrapper
      TokenStore.swift
    Models/
      Character.swift
      Message.swift
      Conversation.swift
      Memory.swift
    Utils/
      HapticManager.swift
      ImageCache.swift
    Extensions/
      Color+Ember.swift
      Font+Ember.swift
      View+Accessibility.swift
  Resources/
    Assets.xcassets
    Localizable.xcstrings
  Tests/
    Unit/
    Integration/
```

---

## 2. @Observable Pattern (iOS 17+)

Use `@Observable` (Observation framework) for all ViewModels. Do **not** use `ObservableObject` / `@Published` — those are pre-iOS 17 patterns.

```swift
// Features/Chat/ChatViewModel.swift
import Observation
import Foundation

@Observable
final class ChatViewModel {
    var messages: [Message] = []
    var inputText: String = ""
    var isStreaming: Bool = false
    var errorMessage: String? = nil

    private let apiClient: APIClientProtocol
    private let characterId: String

    init(characterId: String, apiClient: APIClientProtocol = APIClient.shared) {
        self.characterId = characterId
        self.apiClient = apiClient
    }

    func sendMessage() async {
        guard !inputText.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        let content = inputText
        inputText = ""
        isStreaming = true
        errorMessage = nil

        do {
            let userMessage = Message(role: .user, content: content)
            messages.append(userMessage)

            var assistantMessage = Message(role: .assistant, content: "")
            messages.append(assistantMessage)

            for try await chunk in apiClient.streamMessage(characterId: characterId, content: content) {
                assistantMessage.content += chunk
                messages[messages.count - 1] = assistantMessage
            }
        } catch {
            errorMessage = error.localizedDescription
            messages.removeLast()  // remove empty assistant bubble
        }
        isStreaming = false
    }

    func loadHistory() async {
        do {
            let page = try await apiClient.listMessages(characterId: characterId, cursor: nil, limit: 30)
            messages = page.items.reversed()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
```

```swift
// Features/Chat/ChatView.swift
import SwiftUI

struct ChatView: View {
    @State private var viewModel: ChatViewModel

    init(characterId: String) {
        _viewModel = State(initialValue: ChatViewModel(characterId: characterId))
    }

    var body: some View {
        VStack(spacing: 0) {
            MessageListView(messages: viewModel.messages, isStreaming: viewModel.isStreaming)
            ChatInputBar(
                text: $viewModel.inputText,
                isSending: viewModel.isStreaming,
                onSend: {
                    Task { await viewModel.sendMessage() }
                }
            )
        }
        .task { await viewModel.loadHistory() }
        .alert("Error", isPresented: .constant(viewModel.errorMessage != nil)) {
            Button("OK") { viewModel.errorMessage = nil }
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }
}
```

**Rules:**
- `@Observable` is the only ViewModel pattern. No `ObservableObject`.
- `@State private var viewModel: ChatViewModel` — not `@StateObject`.
- ViewModels are `final class`, never `struct`.
- All async calls wrapped in `Task { }` inside view event handlers.
- Business logic lives in ViewModel, never in View body.

---

## 3. Navigation: NavigationStack + NavigationPath

```swift
// App/EmberApp.swift
import SwiftUI

@main
struct EmberApp: App {
    @State private var router = AppRouter()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(router)
                .preferredColorScheme(.dark)
        }
    }
}
```

```swift
// Core/Navigation/AppRouter.swift
import Observation
import SwiftUI

@Observable
final class AppRouter {
    var path = NavigationPath()

    enum Route: Hashable {
        case characterDetail(characterId: String)
        case chat(characterId: String)
        case memoryList(characterId: String)
        case settings
    }

    func push(_ route: Route) {
        path.append(route)
    }

    func pop() {
        path.removeLast()
    }

    func popToRoot() {
        path.removeLast(path.count)
    }
}
```

```swift
// Features/Characters/CharacterListView.swift
struct CharacterListView: View {
    @Environment(AppRouter.self) private var router

    var body: some View {
        NavigationStack(path: Bindable(router).path) {
            CharacterGridContent()
                .navigationDestination(for: AppRouter.Route.self) { route in
                    switch route {
                    case .chat(let id):
                        ChatView(characterId: id)
                    case .characterDetail(let id):
                        CharacterDetailView(characterId: id)
                    case .memoryList(let id):
                        MemoryListView(characterId: id)
                    case .settings:
                        SettingsView()
                    }
                }
        }
    }
}
```

**Rules:**
- Single `NavigationStack` at the root — do not nest multiple stacks.
- All navigation routes defined in `AppRouter.Route` enum.
- `@Environment(AppRouter.self)` to access router from any view.
- No `NavigationLink(destination:)` — use `.navigationDestination(for:)` + `router.push`.

---

## 4. Network Layer: URLSession + Codable + async/await

```swift
// Core/Network/APIEndpoint.swift
import Foundation

enum APIEndpoint {
    case listMessages(characterId: String, cursor: String?, limit: Int)
    case sendMessage(characterId: String)
    case listCharacters
    case getMemories(characterId: String)

    var path: String {
        switch self {
        case .listMessages(let id, _, _): return "/characters/\(id)/messages"
        case .sendMessage(let id):        return "/characters/\(id)/messages"
        case .listCharacters:             return "/characters"
        case .getMemories(let id):        return "/characters/\(id)/messages"
        }
    }

    var method: String {
        switch self {
        case .sendMessage: return "POST"
        default:           return "GET"
        }
    }
}
```

```swift
// Core/Network/APIClient.swift
import Foundation

protocol APIClientProtocol {
    func listMessages(characterId: String, cursor: String?, limit: Int) async throws -> MessagePage
    func sendMessage(characterId: String, content: String) async throws -> Message
    func streamMessage(characterId: String, content: String) -> AsyncThrowingStream<String, Error>
}

final class APIClient: APIClientProtocol {
    static let shared = APIClient()

    private let baseURL: URL
    private let session: URLSession
    private let tokenStore: TokenStore

    init(
        baseURL: URL = URL(string: ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://api.ember.ai")!,
        session: URLSession = .shared,
        tokenStore: TokenStore = .shared
    ) {
        self.baseURL = baseURL
        self.session = session
        self.tokenStore = tokenStore
    }

    private func makeRequest(path: String, method: String = "GET", body: Encodable? = nil) async throws -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let token = try await tokenStore.getAccessToken()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        if let body {
            request.httpBody = try JSONEncoder.ember.encode(body)
        }
        return request
    }

    func listMessages(characterId: String, cursor: String?, limit: Int) async throws -> MessagePage {
        var path = "/characters/\(characterId)/messages?limit=\(limit)"
        if let cursor { path += "&cursor=\(cursor)" }
        let request = try await makeRequest(path: path)
        let (data, response) = try await session.data(for: request)
        try validate(response)
        return try JSONDecoder.ember.decode(MessagePage.self, from: data)
    }

    func sendMessage(characterId: String, content: String) async throws -> Message {
        struct Body: Encodable { let content: String }
        let request = try await makeRequest(
            path: "/characters/\(characterId)/messages",
            method: "POST",
            body: Body(content: content)
        )
        let (data, response) = try await session.data(for: request)
        try validate(response)
        return try JSONDecoder.ember.decode(Message.self, from: data)
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200...299).contains(http.statusCode) else {
            throw APIError.httpError(statusCode: http.statusCode)
        }
    }
}

extension JSONEncoder {
    static let ember: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        e.dateEncodingStrategy = .iso8601
        return e
    }()
}

extension JSONDecoder {
    static let ember: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }()
}

enum APIError: LocalizedError {
    case httpError(statusCode: Int)
    case decodingError(Error)

    var errorDescription: String? {
        switch self {
        case .httpError(let code): return "Server error: \(code)"
        case .decodingError(let e): return "Data error: \(e.localizedDescription)"
        }
    }
}
```

---

## 5. SSE Streaming: URLSession + AsyncStream

```swift
// Core/Network/SSEClient.swift
import Foundation

final class SSEClient {
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func stream(request: URLRequest) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = session.dataTask(with: request) { _, _, error in
                if let error {
                    continuation.finish(throwing: error)
                }
            }

            // Use URLSessionDataDelegate for streaming
            let delegate = SSEDelegate(continuation: continuation)
            let streamSession = URLSession(configuration: .default, delegate: delegate, delegateQueue: nil)
            let streamTask = streamSession.dataTask(with: request)
            streamTask.resume()

            continuation.onTermination = { _ in
                streamTask.cancel()
            }
        }
    }
}

private final class SSEDelegate: NSObject, URLSessionDataDelegate {
    private let continuation: AsyncThrowingStream<String, Error>.Continuation
    private var buffer = ""

    init(continuation: AsyncThrowingStream<String, Error>.Continuation) {
        self.continuation = continuation
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard let text = String(data: data, encoding: .utf8) else { return }
        buffer += text

        while let range = buffer.range(of: "\n\n") {
            let event = String(buffer[buffer.startIndex..<range.lowerBound])
            buffer.removeSubrange(buffer.startIndex..<range.upperBound)

            if event.hasPrefix("data: ") {
                let payload = String(event.dropFirst(6))
                if payload == "[DONE]" {
                    continuation.finish()
                    return
                }
                continuation.yield(payload)
            }
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error {
            continuation.finish(throwing: error)
        } else {
            continuation.finish()
        }
    }
}
```

```swift
// Usage in APIClient
func streamMessage(characterId: String, content: String) -> AsyncThrowingStream<String, Error> {
    AsyncThrowingStream { continuation in
        Task {
            do {
                struct Body: Encodable { let content: String }
                var request = try await makeRequest(
                    path: "/characters/\(characterId)/messages/stream",
                    method: "POST",
                    body: Body(content: content)
                )
                request.setValue("text/event-stream", forHTTPHeaderField: "Accept")

                let sseClient = SSEClient()
                for try await event in sseClient.stream(request: request) {
                    if let data = event.data(using: .utf8),
                       let json = try? JSONDecoder.ember.decode(SSEDelta.self, from: data) {
                        continuation.yield(json.delta)
                    }
                }
                continuation.finish()
            } catch {
                continuation.finish(throwing: error)
            }
        }
    }
}

struct SSEDelta: Decodable { let delta: String }
```

---

## 6. AWS Amplify Cognito Integration

```swift
// Core/Auth/AuthService.swift
import Amplify
import AWSCognitoAuthPlugin
import Foundation

protocol AuthServiceProtocol {
    func signIn(username: String, password: String) async throws
    func signOut() async
    func getCurrentUser() async throws -> AuthUser
    func getAccessToken() async throws -> String
}

final class AuthService: AuthServiceProtocol {
    static let shared = AuthService()

    private init() {}

    func configure() {
        do {
            try Amplify.add(plugin: AWSCognitoAuthPlugin())
            try Amplify.configure()
        } catch {
            fatalError("Failed to configure Amplify: \(error)")
        }
    }

    func signIn(username: String, password: String) async throws {
        let result = try await Amplify.Auth.signIn(username: username, password: password)
        guard result.isSignedIn else {
            throw AuthError.signInFailed("Sign-in incomplete")
        }
    }

    func signOut() async {
        _ = await Amplify.Auth.signOut()
    }

    func getCurrentUser() async throws -> AuthUser {
        try await Amplify.Auth.getCurrentUser()
    }

    func getAccessToken() async throws -> String {
        let session = try await Amplify.Auth.fetchAuthSession()
        if let cognitoSession = session as? AuthCognitoTokensProvider {
            let tokens = try cognitoSession.getCognitoTokens().get()
            return tokens.accessToken
        }
        throw AuthError.tokenUnavailable
    }
}

enum AuthError: LocalizedError {
    case signInFailed(String)
    case tokenUnavailable

    var errorDescription: String? {
        switch self {
        case .signInFailed(let msg): return msg
        case .tokenUnavailable: return "Authentication token unavailable"
        }
    }
}
```

```swift
// App/EmberApp.swift — configure at launch
@main
struct EmberApp: App {
    init() {
        AuthService.shared.configure()
    }
    // ...
}
```

---

## 7. Kingfisher for Network Images

```swift
import Kingfisher
import SwiftUI

// Basic usage
KFImage(URL(string: character.avatarURL))
    .placeholder {
        Circle()
            .fill(Color.emberSurface)
            .overlay(Image(systemName: "person.fill").foregroundStyle(.secondary))
    }
    .resizable()
    .aspectRatio(contentMode: .fill)
    .frame(width: 80, height: 80)
    .clipShape(Circle())

// With fade transition
KFImage(URL(string: character.avatarURL))
    .fade(duration: 0.25)
    .resizable()
    .scaledToFill()
```

**Rules:**
- Always provide a placeholder view.
- Use `.fade(duration: 0.25)` for smooth loading.
- Never use `AsyncImage` — Kingfisher has better caching and disk storage.
- Avatar sizes: thumbnail 40pt, list 80pt, detail 160pt.

---

## 8. SF Symbols Usage

```swift
// Always use .weight and .scale for consistency
Image(systemName: "message.fill")
    .symbolRenderingMode(.hierarchical)
    .font(.system(size: 20, weight: .medium))

// In toolbar / navigation
ToolbarItem(placement: .navigationBarTrailing) {
    Button {
        router.push(.settings)
    } label: {
        Image(systemName: "gearshape.fill")
            .symbolRenderingMode(.hierarchical)
    }
}

// Symbol constants — define in one place
enum EmberSymbol {
    static let send      = "arrow.up.circle.fill"
    static let microphone = "mic.fill"
    static let memory    = "brain.head.profile"
    static let character = "person.crop.circle"
    static let settings  = "gearshape.fill"
    static let back      = "chevron.left"
}
```

**Rules:**
- Always use SF Symbols; never ship custom icons when SF Symbols suffice.
- Use `.symbolRenderingMode(.hierarchical)` for depth.
- Define symbol names as constants in `EmberSymbol` — never use raw strings in view code.
- Minimum symbol size: 17pt for tap targets.

---

## 9. Dark Mode

```swift
// App/EmberApp.swift
.preferredColorScheme(.dark)
```

Ember is a dark-first app. Force dark mode globally. Do not support system-adaptive appearance.

```swift
// This line goes on the root WindowGroup content view — never on individual views.
WindowGroup {
    RootView()
        .preferredColorScheme(.dark)
}
```

---

## 10. Color and Typography System

All colors and fonts are defined as extensions to avoid magic values in view code.

```swift
// Core/Extensions/Color+Ember.swift
import SwiftUI

extension Color {
    // Backgrounds
    static let emberBackground   = Color("EmberBackground")    // #0A0A0F
    static let emberSurface      = Color("EmberSurface")       // #141420
    static let emberCard         = Color("EmberCard")          // #1E1E30

    // Brand
    static let emberPrimary      = Color("EmberPrimary")       // #7C6AF7  (violet)
    static let emberAccent       = Color("EmberAccent")        // #E85D9A  (rose)

    // Text
    static let emberTextPrimary  = Color("EmberTextPrimary")   // #F0F0F8
    static let emberTextSecondary = Color("EmberTextSecondary") // #8888AA

    // Status
    static let emberSuccess      = Color("EmberSuccess")       // #4CAF50
    static let emberError        = Color("EmberError")         // #F44336
    static let emberWarning      = Color("EmberWarning")       // #FF9800
}
```

```swift
// Core/Extensions/Font+Ember.swift
import SwiftUI

extension Font {
    // Display — character names, onboarding headers
    static let emberDisplay     = Font.custom("SF Pro Display", size: 34, relativeTo: .largeTitle)
    // Title
    static let emberTitle       = Font.custom("SF Pro Display", size: 22, relativeTo: .title2)
    // Body — chat messages
    static let emberBody        = Font.system(.body, design: .default)
    // Caption — timestamps, metadata
    static let emberCaption     = Font.system(.caption, design: .default)
    // Monospace — debug/memory content
    static let emberMono        = Font.system(.caption, design: .monospaced)
}
```

**Rules:**
- All color literals in `Color+Ember.swift` only.
- Declare colors in `Assets.xcassets` as named color sets with dark-only variants.
- Never use `Color(.systemBackground)` or adaptive colors — Ember is dark-only.
- Use `relativeTo:` in `Font.custom` to respect Dynamic Type scaling.

---

## 11. Error Handling in SwiftUI

```swift
// Pattern: errorMessage string on ViewModel, .alert on View

@Observable
final class ExampleViewModel {
    var errorMessage: String? = nil

    func performAction() async {
        do {
            try await someAPICall()
        } catch let error as APIError {
            errorMessage = error.localizedDescription
        } catch {
            errorMessage = "Something went wrong. Please try again."
        }
    }
}

struct ExampleView: View {
    @State private var viewModel = ExampleViewModel()

    var body: some View {
        Content()
            .alert("Error", isPresented: Binding(
                get: { viewModel.errorMessage != nil },
                set: { if !$0 { viewModel.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(viewModel.errorMessage ?? "")
            }
    }
}
```

**Rules:**
- Never use `try!` or `try?` in production code (except trivial string operations).
- Catch specific error types before catching `Error`.
- User-facing messages must be human-readable — never show raw error dumps.
- Network errors: "Connection failed. Please check your internet and try again."
- Auth errors: redirect to login, do not show raw JWT errors.

---

## 12. Haptic Feedback

```swift
// Core/Utils/HapticManager.swift
import UIKit

enum HapticManager {
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        let generator = UIImpactFeedbackGenerator(style: style)
        generator.prepare()
        generator.impactOccurred()
    }

    static func notification(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        let generator = UINotificationFeedbackGenerator()
        generator.prepare()
        generator.notificationOccurred(type)
    }

    static func selection() {
        let generator = UISelectionFeedbackGenerator()
        generator.prepare()
        generator.selectionChanged()
    }
}

// Usage:
// Message sent:
HapticManager.impact(.medium)

// Error:
HapticManager.notification(.error)

// Character selected:
HapticManager.selection()

// Voice recording start:
HapticManager.impact(.rigid)
```

**Rules:**
- Call `prepare()` before `impactOccurred()` to reduce latency.
- Message send: `.medium` impact.
- Error feedback: `.notification(.error)`.
- Tap selection: `.selection()`.
- Never use haptics in background tasks.

---

## 13. Accessibility

```swift
// Accessibility labels on all interactive and image elements
Button {
    viewModel.sendMessage()
} label: {
    Image(systemName: EmberSymbol.send)
}
.accessibilityLabel("Send message")
.accessibilityHint("Sends your typed message to \(characterName)")

// Images
KFImage(URL(string: character.avatarURL))
    .accessibilityLabel("\(character.name) profile photo")
    .accessibilityHidden(false)

// Decorative images
Image(systemName: "sparkles")
    .accessibilityHidden(true)

// Dynamic Type — always use relative fonts
Text(message.content)
    .font(.emberBody)                    // uses .body text style
    .lineLimit(nil)                      // allow wrapping

// Custom accessibility actions
MessageBubbleView(message: message)
    .accessibilityAction(named: "Copy message") {
        UIPasteboard.general.string = message.content
    }
```

**Rules:**
- Every `Button` with an icon-only label must have `.accessibilityLabel`.
- Every `KFImage` / `AsyncImage` must have `.accessibilityLabel`.
- Pure decorative images: `.accessibilityHidden(true)`.
- All fonts must use text styles (`relativeTo:`) to support Dynamic Type.
- VoiceOver order must match visual order — use `.accessibilitySortPriority` if needed.
- Minimum tap target: 44x44pt (use `.frame(minWidth: 44, minHeight: 44)`).

---

## 14. Swift Testing and XCTest Patterns

### Unit Tests with Swift Testing (preferred for new tests)

```swift
// Tests/Unit/ChatViewModelTests.swift
import Testing
@testable import EmberApp

@Suite("ChatViewModel")
struct ChatViewModelTests {

    @Test("sends message and appends to list")
    func sendMessageAppendsToList() async throws {
        let mockAPI = MockAPIClient()
        mockAPI.streamResponse = ["Hello", " there", "!"]
        let vm = ChatViewModel(characterId: "c1", apiClient: mockAPI)

        vm.inputText = "Hi Ember"
        await vm.sendMessage()

        #expect(vm.messages.count == 2)
        #expect(vm.messages[0].role == .user)
        #expect(vm.messages[1].content == "Hello there!")
        #expect(vm.isStreaming == false)
    }

    @Test("clears input after send")
    func clearsInputAfterSend() async throws {
        let mockAPI = MockAPIClient()
        let vm = ChatViewModel(characterId: "c1", apiClient: mockAPI)
        vm.inputText = "Test"

        await vm.sendMessage()

        #expect(vm.inputText.isEmpty)
    }

    @Test("sets errorMessage on network failure")
    func setsErrorOnFailure() async throws {
        let mockAPI = MockAPIClient()
        mockAPI.shouldThrow = APIError.httpError(statusCode: 503)
        let vm = ChatViewModel(characterId: "c1", apiClient: mockAPI)
        vm.inputText = "Hi"

        await vm.sendMessage()

        #expect(vm.errorMessage != nil)
        #expect(vm.messages.isEmpty)
    }
}
```

### XCTest (for UI and integration tests)

```swift
// Tests/Integration/ChatIntegrationTests.swift
import XCTest
@testable import EmberApp

final class ChatIntegrationTests: XCTestCase {
    var mockAPI: MockAPIClient!
    var viewModel: ChatViewModel!

    override func setUp() {
        super.setUp()
        mockAPI = MockAPIClient()
        viewModel = ChatViewModel(characterId: "c1", apiClient: mockAPI)
    }

    func testLoadHistoryPopulatesMessages() async throws {
        mockAPI.messagePage = MessagePage(
            items: [Message(role: .user, content: "Old message")],
            nextCursor: nil,
            hasMore: false
        )

        await viewModel.loadHistory()

        XCTAssertEqual(viewModel.messages.count, 1)
        XCTAssertEqual(viewModel.messages[0].content, "Old message")
    }
}
```

---

## 15. Protocol-Based Dependency Injection (Fake Pattern)

```swift
// Core/Network/APIClientProtocol.swift
protocol APIClientProtocol {
    func listMessages(characterId: String, cursor: String?, limit: Int) async throws -> MessagePage
    func sendMessage(characterId: String, content: String) async throws -> Message
    func streamMessage(characterId: String, content: String) -> AsyncThrowingStream<String, Error>
    func listCharacters() async throws -> [Character]
}

// Tests/Fakes/MockAPIClient.swift
import Foundation
@testable import EmberApp

final class MockAPIClient: APIClientProtocol {
    var messagePage: MessagePage = MessagePage(items: [], nextCursor: nil, hasMore: false)
    var streamResponse: [String] = []
    var shouldThrow: Error? = nil
    var characters: [Character] = []

    func listMessages(characterId: String, cursor: String?, limit: Int) async throws -> MessagePage {
        if let error = shouldThrow { throw error }
        return messagePage
    }

    func sendMessage(characterId: String, content: String) async throws -> Message {
        if let error = shouldThrow { throw error }
        return Message(role: .assistant, content: streamResponse.joined())
    }

    func streamMessage(characterId: String, content: String) -> AsyncThrowingStream<String, Error> {
        let response = streamResponse
        let error = shouldThrow
        return AsyncThrowingStream { continuation in
            Task {
                if let error {
                    continuation.finish(throwing: error)
                    return
                }
                for chunk in response {
                    continuation.yield(chunk)
                    try? await Task.sleep(nanoseconds: 1_000_000)
                }
                continuation.finish()
            }
        }
    }

    func listCharacters() async throws -> [Character] {
        if let error = shouldThrow { throw error }
        return characters
    }
}
```

**Rules:**
- Every service used by a ViewModel must be behind a protocol.
- Test targets inject `MockXxx` implementations, never real network clients.
- Production code injects real implementations at the composition root (`AppContainer`).
- No `@EnvironmentObject` hacks for test injection — always constructor injection.

---

## Dependency Container (Composition Root)

```swift
// App/AppContainer.swift
import Foundation

@Observable
final class AppContainer {
    let apiClient: APIClientProtocol
    let authService: AuthServiceProtocol

    init(
        apiClient: APIClientProtocol = APIClient.shared,
        authService: AuthServiceProtocol = AuthService.shared
    ) {
        self.apiClient = apiClient
        self.authService = authService
    }
}

// App/EmberApp.swift
@main
struct EmberApp: App {
    @State private var container = AppContainer()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(container)
                .preferredColorScheme(.dark)
        }
    }
}

// Usage in a feature view:
struct ChatView: View {
    @Environment(AppContainer.self) private var container
    @State private var viewModel: ChatViewModel?

    var body: some View {
        Group {
            if let vm = viewModel {
                ChatContent(viewModel: vm)
            }
        }
        .onAppear {
            viewModel = ChatViewModel(characterId: characterId, apiClient: container.apiClient)
        }
    }
}
```
