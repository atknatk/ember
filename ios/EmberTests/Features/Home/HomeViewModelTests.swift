import Testing
import Foundation
@testable import Ember

@Suite("HomeViewModel")
struct HomeViewModelTests {

    // MARK: - Mock API Client

    /// A mock that returns different results based on the endpoint.
    /// Supports `listCharacters` returning `CharacterListResponse` and
    /// `listMessages` returning `MessageListResponse`.
    private final class MockHomeAPIClient: APIClientProtocol, @unchecked Sendable {
        var characterListResponse: CharacterListResponse = CharacterListResponse(characters: [])
        var messageListResponses: [String: MessageListResponse] = [:]
        var requestError: Error?
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
                let response = messageListResponses[characterId] ?? MessageListResponse(items: [], nextCursor: nil, hasMore: false)
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

    // MARK: - Test Data

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

    // MARK: - Helpers

    private func makeViewModel() -> (HomeViewModel, MockHomeAPIClient) {
        let mock = MockHomeAPIClient()
        let vm = HomeViewModel(apiClient: mock)
        return (vm, mock)
    }

    // MARK: - loadCharacters Tests

    @Test("loadCharacters sets characters on success")
    func loadCharactersSuccess() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna", isDefault: true)
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])

        await vm.loadCharacters()

        #expect(vm.characters.count == 2)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    @Test("loadCharacters sets errorMessage on network failure")
    func loadCharactersNetworkError() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.networkError(
            NSError(domain: "Test", code: -1, userInfo: [NSLocalizedDescriptionKey: "No connection"])
        )

        await vm.loadCharacters()

        #expect(vm.characters.isEmpty)
        #expect(vm.errorMessage != nil)
        #expect(vm.isLoading == false)
    }

    @Test("loadCharacters sets errorMessage on server error")
    func loadCharactersServerError() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.serverError(statusCode: 500, detail: "Internal error")

        await vm.loadCharacters()

        #expect(vm.errorMessage != nil)
        #expect(vm.isLoading == false)
    }

    @Test("loadCharacters fetches last messages for each character")
    func loadCharactersFetchesLastMessages() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])

        let msg1 = Self.makeMessagePreview(id: "m1", content: "Hello from Luna")
        let msg2 = Self.makeMessagePreview(id: "m2", content: "Workout time!")
        mock.messageListResponses = [
            "c1": MessageListResponse(items: [msg1], nextCursor: nil, hasMore: false),
            "c2": MessageListResponse(items: [msg2], nextCursor: nil, hasMore: false)
        ]

        await vm.loadCharacters()

        #expect(vm.lastMessages.count == 2)
        #expect(vm.lastMessages["c1"]?.content == "Hello from Luna")
        #expect(vm.lastMessages["c2"]?.content == "Workout time!")
    }

    @Test("pull-to-refresh preserves existing data during refresh")
    func pullToRefreshPreservesData() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        mock.characterListResponse = CharacterListResponse(characters: [c1])

        // Initial load
        await vm.loadCharacters()
        #expect(vm.characters.count == 1)

        // Second load (refresh) -- should set isRefreshing, not isLoading
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])

        await vm.loadCharacters()

        #expect(vm.characters.count == 2)
        #expect(vm.isLoading == false)
        #expect(vm.isRefreshing == false)
    }

    // MARK: - defaultCharacter Tests

    @Test("defaultCharacter returns the is_default character")
    func defaultCharacterReturnsDefault() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna", isDefault: true)
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])

        await vm.loadCharacters()

        #expect(vm.defaultCharacter?.isDefault == true)
        #expect(vm.defaultCharacter?.id == "c1")
    }

    @Test("defaultCharacter returns nil when no characters")
    func defaultCharacterNilWhenEmpty() {
        let (vm, _) = makeViewModel()
        #expect(vm.defaultCharacter == nil)
    }

    // MARK: - greeting Tests

    @Test("greeting returns correct string for morning")
    func greetingMorning() {
        let calendar = Calendar.current
        guard let date = calendar.date(bySettingHour: 8, minute: 0, second: 0, of: Date()) else { return }
        let result = HomeViewModel.greeting(for: date)
        #expect(result == "Good morning")
    }

    @Test("greeting returns correct string for afternoon")
    func greetingAfternoon() {
        let calendar = Calendar.current
        guard let date = calendar.date(bySettingHour: 14, minute: 0, second: 0, of: Date()) else { return }
        let result = HomeViewModel.greeting(for: date)
        #expect(result == "Good afternoon")
    }

    @Test("greeting returns correct string for evening")
    func greetingEvening() {
        let calendar = Calendar.current
        guard let date = calendar.date(bySettingHour: 20, minute: 0, second: 0, of: Date()) else { return }
        let result = HomeViewModel.greeting(for: date)
        #expect(result == "Good evening")
    }

    // MARK: - templateIcon Tests

    @Test("templateIcon returns correct SF Symbol for each template")
    func templateIconMapping() {
        #expect(HomeViewModel.templateIcon(for: "companion") == "person.fill")
        #expect(HomeViewModel.templateIcon(for: "english_teacher") == "book.fill")
        #expect(HomeViewModel.templateIcon(for: "therapist") == "heart.text.square.fill")
        #expect(HomeViewModel.templateIcon(for: "fitness_coach") == "figure.run")
        #expect(HomeViewModel.templateIcon(for: "career_coach") == "briefcase.fill")
        #expect(HomeViewModel.templateIcon(for: "custom") == "sparkles")
        #expect(HomeViewModel.templateIcon(for: "unknown") == "person.fill")
    }
}
