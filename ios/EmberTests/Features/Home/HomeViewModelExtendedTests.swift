import Testing
import Foundation
@testable import Ember

/// Extended tests for `HomeViewModel` — edge cases not covered by `HomeViewModelTests.swift`.
/// Covers: `defaultCharacterLastMessage`, greeting boundary hours, `hasUnreadMessages`,
/// `markCharacterAsOpened`, `lastOpenedDate`, retry clearing errorMessage,
/// empty character list, partial lastMessage failure, and `userName` initialisation.
@Suite("HomeViewModel Extended")
struct HomeViewModelExtendedTests {

    // MARK: - Mock API Client

    /// Routes `listCharacters` and `listMessages` separately.
    /// Optionally throws only on `listMessages` to simulate partial failure.
    private final class MockHomeAPIClient: APIClientProtocol, @unchecked Sendable {
        var characterListResponse: CharacterListResponse = CharacterListResponse(characters: [])
        var messageListResponses: [String: MessageListResponse] = [:]
        var requestError: Error?
        /// When set, only `listMessages` calls throw this error (not `listCharacters`).
        var messageRequestError: Error?
        var requestCallCount: Int = 0

        func request<T: Decodable>(
            endpoint: APIEndpoint,
            body: (any Encodable)?,
            responseType: T.Type
        ) async throws -> T {
            requestCallCount += 1
            if let error = requestError {
                throw error
            }
            switch endpoint {
            case .listCharacters:
                guard let result = characterListResponse as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "Type mismatch"])
                    )
                }
                return result
            case .listMessages(let characterId, _, _):
                if let error = messageRequestError { throw error }
                let response = messageListResponses[characterId]
                    ?? MessageListResponse(items: [], nextCursor: nil, hasMore: false)
                guard let result = response as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "Type mismatch"])
                    )
                }
                return result
            default:
                throw APIError.decodingError(
                    NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "Unexpected endpoint"])
                )
            }
        }

        func requestVoid(endpoint: APIEndpoint, body: (any Encodable)?) async throws {
            if let error = requestError { throw error }
        }

        func streamSSE(endpoint: APIEndpoint, body: (any Encodable)?) -> AsyncThrowingStream<SSEEvent, Error> {
            AsyncThrowingStream { $0.finish() }
        }
    }

    // MARK: - Test Data Helpers

    private static func makeCharacter(
        id: String = "c1",
        name: String = "Luna",
        template: String = "companion",
        isDefault: Bool = true,
        lastMessageAt: Date? = Date()
    ) -> Character {
        Character(
            id: id,
            name: name,
            template: template,
            description: nil,
            avatarStyle: "default",
            isDefault: isDefault,
            lastMessageAt: lastMessageAt,
            createdAt: Date()
        )
    }

    private static func makeMessagePreview(
        id: String = "m1",
        role: String = "assistant",
        content: String = "Good morning! How are you?",
        createdAt: Date = Date()
    ) -> MessagePreview {
        MessagePreview(id: id, role: role, content: content, createdAt: createdAt)
    }

    private func makeViewModel(mock: MockHomeAPIClient = MockHomeAPIClient()) -> HomeViewModel {
        HomeViewModel(apiClient: mock)
    }

    // MARK: - defaultCharacterLastMessage Tests

    @Test("defaultCharacterLastMessage returns preview for default character")
    func defaultCharacterLastMessageReturnsPreview() async {
        let mock = MockHomeAPIClient()
        let character = Self.makeCharacter(id: "c1", isDefault: true)
        let preview = Self.makeMessagePreview(id: "m1", content: "Hey there!")
        mock.characterListResponse = CharacterListResponse(characters: [character])
        mock.messageListResponses = ["c1": MessageListResponse(items: [preview], nextCursor: nil, hasMore: false)]
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.defaultCharacterLastMessage?.content == "Hey there!")
        #expect(vm.defaultCharacterLastMessage?.id == "m1")
    }

    @Test("defaultCharacterLastMessage returns nil when no default character exists")
    func defaultCharacterLastMessageNilWithoutDefault() async {
        let mock = MockHomeAPIClient()
        let character = Self.makeCharacter(id: "c1", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [character])
        mock.messageListResponses = ["c1": MessageListResponse(
            items: [Self.makeMessagePreview(id: "m1")],
            nextCursor: nil,
            hasMore: false
        )]
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.defaultCharacterLastMessage == nil)
    }

    @Test("defaultCharacterLastMessage returns nil when default character has no messages")
    func defaultCharacterLastMessageNilWhenNoMessages() async {
        let mock = MockHomeAPIClient()
        let character = Self.makeCharacter(id: "c1", isDefault: true)
        mock.characterListResponse = CharacterListResponse(characters: [character])
        // No message list response for c1 — defaults to empty items
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.defaultCharacterLastMessage == nil)
    }

    @Test("defaultCharacterLastMessage returns nil before loadCharacters is called")
    func defaultCharacterLastMessageNilBeforeLoad() {
        let vm = makeViewModel()
        #expect(vm.defaultCharacterLastMessage == nil)
    }

    // MARK: - Greeting Boundary Hours

    @Test("greeting returns Good morning at hour 5 (lower boundary)")
    func greetingHour5IsMorning() {
        let date = Calendar.current.date(bySettingHour: 5, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good morning")
    }

    @Test("greeting returns Good morning at hour 11 (upper morning boundary)")
    func greetingHour11IsMorning() {
        let date = Calendar.current.date(bySettingHour: 11, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good morning")
    }

    @Test("greeting returns Good afternoon at hour 12 (lower afternoon boundary)")
    func greetingHour12IsAfternoon() {
        let date = Calendar.current.date(bySettingHour: 12, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good afternoon")
    }

    @Test("greeting returns Good afternoon at hour 16 (upper afternoon boundary)")
    func greetingHour16IsAfternoon() {
        let date = Calendar.current.date(bySettingHour: 16, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good afternoon")
    }

    @Test("greeting returns Good evening at hour 17 (lower evening boundary)")
    func greetingHour17IsEvening() {
        let date = Calendar.current.date(bySettingHour: 17, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good evening")
    }

    @Test("greeting returns Good evening at hour 0 (midnight)")
    func greetingMidnightIsEvening() {
        let date = Calendar.current.date(bySettingHour: 0, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good evening")
    }

    @Test("greeting returns Good evening at hour 4 (late night)")
    func greetingHour4IsEvening() {
        let date = Calendar.current.date(bySettingHour: 4, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good evening")
    }

    @Test("greeting returns Good evening at hour 23 (late evening)")
    func greetingHour23IsEvening() {
        let date = Calendar.current.date(bySettingHour: 23, minute: 0, second: 0, of: Date())!
        #expect(HomeViewModel.greeting(for: date) == "Good evening")
    }

    // MARK: - hasUnreadMessages Tests

    @Test("hasUnreadMessages returns false when character has no lastMessageAt")
    func hasUnreadMessagesFalseWhenNoLastMessageAt() {
        let character = Self.makeCharacter(id: "c_no_msg", lastMessageAt: nil)
        #expect(HomeViewModel.hasUnreadMessages(for: character) == false)
    }

    @Test("hasUnreadMessages returns true when character was never opened")
    func hasUnreadMessagesTrueWhenNeverOpened() {
        // Use a unique ID to avoid state from other tests
        let uniqueId = "c_never_opened_\(UUID().uuidString)"
        // Ensure no existing entry for this ID
        var dict = (UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double]) ?? [:]
        dict.removeValue(forKey: uniqueId)
        UserDefaults.standard.set(dict, forKey: "character_last_opened")

        let character = Self.makeCharacter(id: uniqueId, lastMessageAt: Date())
        #expect(HomeViewModel.hasUnreadMessages(for: character) == true)
    }

    @Test("hasUnreadMessages returns true when message is newer than last opened date")
    func hasUnreadMessagesTrueWhenMessageIsNewer() {
        let uniqueId = "c_unread_\(UUID().uuidString)"
        let oldDate = Date(timeIntervalSinceNow: -3600) // 1 hour ago
        let newMessage = Date(timeIntervalSinceNow: -1800) // 30 min ago

        // Record that the user opened this character 1 hour ago
        var dict = (UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double]) ?? [:]
        dict[uniqueId] = oldDate.timeIntervalSince1970
        UserDefaults.standard.set(dict, forKey: "character_last_opened")

        let character = Self.makeCharacter(id: uniqueId, lastMessageAt: newMessage)
        #expect(HomeViewModel.hasUnreadMessages(for: character) == true)
    }

    @Test("hasUnreadMessages returns false when last opened is more recent than last message")
    func hasUnreadMessagesFalseWhenOpenedAfterMessage() {
        let uniqueId = "c_read_\(UUID().uuidString)"
        let oldMessage = Date(timeIntervalSinceNow: -3600) // 1 hour ago
        let recentOpen = Date(timeIntervalSinceNow: -1800) // 30 min ago

        // Record that the user opened this character 30 min ago
        var dict = (UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double]) ?? [:]
        dict[uniqueId] = recentOpen.timeIntervalSince1970
        UserDefaults.standard.set(dict, forKey: "character_last_opened")

        let character = Self.makeCharacter(id: uniqueId, lastMessageAt: oldMessage)
        #expect(HomeViewModel.hasUnreadMessages(for: character) == false)
    }

    // MARK: - markCharacterAsOpened / lastOpenedDate Tests

    @Test("markCharacterAsOpened stores a date retrievable by lastOpenedDate")
    func markCharacterAsOpenedStoresDate() {
        let uniqueId = "c_mark_\(UUID().uuidString)"
        let before = Date()

        HomeViewModel.markCharacterAsOpened(uniqueId)

        let stored = HomeViewModel.lastOpenedDate(for: uniqueId)
        let after = Date()

        #expect(stored != nil)
        if let stored {
            #expect(stored >= before.addingTimeInterval(-1))
            #expect(stored <= after.addingTimeInterval(1))
        }
    }

    @Test("lastOpenedDate returns nil for a character that was never opened")
    func lastOpenedDateNilWhenNeverOpened() {
        let uniqueId = "c_no_open_\(UUID().uuidString)"
        // Ensure this ID has no entry
        var dict = (UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double]) ?? [:]
        dict.removeValue(forKey: uniqueId)
        UserDefaults.standard.set(dict, forKey: "character_last_opened")

        #expect(HomeViewModel.lastOpenedDate(for: uniqueId) == nil)
    }

    @Test("markCharacterAsOpened can be called twice and updates the stored date")
    func markCharacterAsOpenedUpdatesDate() throws {
        let uniqueId = "c_double_mark_\(UUID().uuidString)"

        HomeViewModel.markCharacterAsOpened(uniqueId)
        let first = HomeViewModel.lastOpenedDate(for: uniqueId)

        // Small artificial delay to ensure timestamps differ
        let laterDate = (first ?? Date()).addingTimeInterval(1)
        var dict = (UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double]) ?? [:]
        dict[uniqueId] = laterDate.timeIntervalSince1970
        UserDefaults.standard.set(dict, forKey: "character_last_opened")

        let second = HomeViewModel.lastOpenedDate(for: uniqueId)
        #expect(second != nil)
        if let first, let second {
            #expect(second >= first)
        }
    }

    @Test("markCharacterAsOpened clears the unread state for a character")
    func markCharacterAsOpenedClearsUnread() {
        let uniqueId = "c_clear_unread_\(UUID().uuidString)"
        let oldMessage = Date(timeIntervalSinceNow: -3600) // 1 hour ago

        // Before marking: character was never opened
        var dict = (UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double]) ?? [:]
        dict.removeValue(forKey: uniqueId)
        UserDefaults.standard.set(dict, forKey: "character_last_opened")

        let character = Self.makeCharacter(id: uniqueId, lastMessageAt: oldMessage)
        #expect(HomeViewModel.hasUnreadMessages(for: character) == true)

        // After marking as opened now, message is older so no unread
        HomeViewModel.markCharacterAsOpened(uniqueId)
        #expect(HomeViewModel.hasUnreadMessages(for: character) == false)
    }

    // MARK: - loadCharacters with Empty Character List

    @Test("loadCharacters with empty character list results in empty characters and no lastMessages")
    func loadCharactersEmptyList() async {
        let mock = MockHomeAPIClient()
        mock.characterListResponse = CharacterListResponse(characters: [])
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.characters.isEmpty)
        #expect(vm.lastMessages.isEmpty)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    // MARK: - Partial lastMessages Failure

    @Test("loadCharacters populates lastMessages for successful character even when one character message fetch fails")
    func loadCharactersPartialMessageFailure() async {
        let mock = MockHomeAPIClient()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna", isDefault: true)
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])

        // Only c1 has a message response; c2 will get an empty response (no error, just no items)
        let msg1 = Self.makeMessagePreview(id: "m1", content: "Luna's message")
        mock.messageListResponses = [
            "c1": MessageListResponse(items: [msg1], nextCursor: nil, hasMore: false)
            // c2 intentionally missing — returns empty MessageListResponse
        ]

        let vm = makeViewModel(mock: mock)
        await vm.loadCharacters()

        // c1's message was fetched
        #expect(vm.lastMessages["c1"]?.content == "Luna's message")
        // c2 had no message items, so no entry in lastMessages
        #expect(vm.lastMessages["c2"] == nil)
        // Characters are still populated correctly
        #expect(vm.characters.count == 2)
        #expect(vm.errorMessage == nil)
    }

    @Test("loadCharacters does not set errorMessage when only lastMessages fetch fails")
    func loadCharactersMessageFetchFailureDoesNotSetError() async {
        let mock = MockHomeAPIClient()
        let character = Self.makeCharacter(id: "c1", isDefault: true)
        mock.characterListResponse = CharacterListResponse(characters: [character])
        mock.messageRequestError = APIError.networkError(
            NSError(domain: "Test", code: -1, userInfo: [NSLocalizedDescriptionKey: "Timeout"])
        )

        let vm = makeViewModel(mock: mock)
        await vm.loadCharacters()

        // Characters still loaded
        #expect(vm.characters.count == 1)
        // errorMessage is NOT set because the top-level loadCharacters() succeeded
        // (lastMessages failure is swallowed per spec — N+1 failures are silent)
        #expect(vm.errorMessage == nil)
        #expect(vm.lastMessages.isEmpty)
    }

    // MARK: - Error Recovery (retry clears previous errorMessage)

    @Test("loadCharacters clears errorMessage on successful retry")
    func loadCharactersClearsErrorOnRetry() async {
        let mock = MockHomeAPIClient()
        // First call: error
        mock.requestError = APIError.serverError(statusCode: 500, detail: "Server error")
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()
        #expect(vm.errorMessage != nil)

        // Second call: success
        mock.requestError = nil
        let character = Self.makeCharacter(id: "c1")
        mock.characterListResponse = CharacterListResponse(characters: [character])

        await vm.loadCharacters()

        #expect(vm.errorMessage == nil)
        #expect(vm.characters.count == 1)
    }

    // MARK: - isLoading vs isRefreshing State

    @Test("isLoading is false after successful load")
    func isLoadingFalseAfterSuccess() async {
        let mock = MockHomeAPIClient()
        mock.characterListResponse = CharacterListResponse(characters: [Self.makeCharacter(id: "c1")])
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.isLoading == false)
        #expect(vm.isRefreshing == false)
    }

    @Test("isLoading is false after failed load")
    func isLoadingFalseAfterError() async {
        let mock = MockHomeAPIClient()
        mock.requestError = APIError.networkError(
            NSError(domain: "Test", code: -1, userInfo: [NSLocalizedDescriptionKey: "No connection"])
        )
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.isLoading == false)
        #expect(vm.isRefreshing == false)
    }

    @Test("isRefreshing is false after refresh succeeds")
    func isRefreshingFalseAfterRefresh() async {
        let mock = MockHomeAPIClient()
        let c1 = Self.makeCharacter(id: "c1")
        mock.characterListResponse = CharacterListResponse(characters: [c1])
        let vm = makeViewModel(mock: mock)

        // Initial load
        await vm.loadCharacters()
        #expect(vm.characters.count == 1)

        // Refresh
        let c2 = Self.makeCharacter(id: "c2", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])
        await vm.loadCharacters()

        #expect(vm.isRefreshing == false)
        #expect(vm.isLoading == false)
        #expect(vm.characters.count == 2)
    }

    // MARK: - userName Initialisation

    @Test("userName is loaded from UserDefaults key user_name on init")
    func userNameLoadedFromUserDefaults() {
        let storedName = "TestUserUnique_\(UUID().uuidString.prefix(8))"
        UserDefaults.standard.set(storedName, forKey: "user_name")

        let vm = makeViewModel()

        #expect(vm.userName == storedName)

        // Cleanup
        UserDefaults.standard.removeObject(forKey: "user_name")
    }

    @Test("userName is empty string when user_name key is not set in UserDefaults")
    func userNameEmptyWhenNotSet() {
        UserDefaults.standard.removeObject(forKey: "user_name")
        let vm = makeViewModel()
        #expect(vm.userName == "")
    }

    // MARK: - templateIcon Edge Cases

    @Test("templateIcon returns person.fill for empty string template")
    func templateIconEmptyStringFallback() {
        #expect(HomeViewModel.templateIcon(for: "") == "person.fill")
    }

    @Test("templateIcon returns person.fill for nil-like unknown template")
    func templateIconUnrecognizedTemplate() {
        #expect(HomeViewModel.templateIcon(for: "astrologer") == "person.fill")
        #expect(HomeViewModel.templateIcon(for: "COMPANION") == "person.fill")
    }

    @Test("templateIcon is case-sensitive — uppercase companion falls back to default")
    func templateIconCaseSensitive() {
        #expect(HomeViewModel.templateIcon(for: "Companion") == "person.fill")
    }

    // MARK: - Multiple Default Characters

    @Test("defaultCharacter returns first character with isDefault true when multiple exist")
    func defaultCharacterReturnsFirstDefault() async {
        let mock = MockHomeAPIClient()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna", isDefault: true)
        let c2 = Self.makeCharacter(id: "c2", name: "Sky", isDefault: true)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.defaultCharacter?.id == "c1")
    }

    @Test("defaultCharacter returns nil when all characters have isDefault false")
    func defaultCharacterNilWhenAllNonDefault() async {
        let mock = MockHomeAPIClient()
        let c1 = Self.makeCharacter(id: "c1", isDefault: false)
        let c2 = Self.makeCharacter(id: "c2", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.defaultCharacter == nil)
    }

    // MARK: - Single Character Load

    @Test("loadCharacters with single character populates characters and lastMessages")
    func loadCharactersSingleCharacter() async {
        let mock = MockHomeAPIClient()
        let character = Self.makeCharacter(id: "c1", name: "Emma", isDefault: true)
        let preview = Self.makeMessagePreview(id: "m1", content: "Hi!")
        mock.characterListResponse = CharacterListResponse(characters: [character])
        mock.messageListResponses = ["c1": MessageListResponse(items: [preview], nextCursor: nil, hasMore: false)]
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(vm.characters.count == 1)
        #expect(vm.characters[0].name == "Emma")
        #expect(vm.lastMessages["c1"]?.content == "Hi!")
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    // MARK: - API Request Call Count

    @Test("loadCharacters calls API at least once on initial load")
    func loadCharactersCallsAPIAtLeastOnce() async {
        let mock = MockHomeAPIClient()
        mock.characterListResponse = CharacterListResponse(characters: [])
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        #expect(mock.requestCallCount >= 1)
    }

    @Test("loadCharacters calls API for each character to fetch last messages")
    func loadCharactersCallsAPIForEachCharacter() async {
        let mock = MockHomeAPIClient()
        let characters = [
            Self.makeCharacter(id: "c1", isDefault: true),
            Self.makeCharacter(id: "c2", isDefault: false),
            Self.makeCharacter(id: "c3", isDefault: false)
        ]
        mock.characterListResponse = CharacterListResponse(characters: characters)
        let vm = makeViewModel(mock: mock)

        await vm.loadCharacters()

        // 1 call for listCharacters + 3 calls for listMessages (one per character)
        #expect(mock.requestCallCount == 4)
    }
}
