import Testing
import Foundation
@testable import Ember

@Suite("MemoriesViewModel")
struct MemoriesViewModelTests {

    // MARK: - Mock API Client

    /// Endpoint-aware mock that returns different results for characters, memories, and delete operations.
    private final class MockMemoriesAPIClient: APIClientProtocol, @unchecked Sendable {
        var characterListResponse = CharacterListResponse(characters: [])
        var memoryListResponse = MemoryListResponse(memories: [])
        var characterMemoryResponses: [String: MemoryListResponse] = [:]
        var requestError: Error?
        var deleteError: Error?
        var requestCallCount: Int = 0
        var requestVoidCallCount: Int = 0
        var lastEndpoint: APIEndpoint?

        func request<T: Decodable>(
            endpoint: APIEndpoint,
            body: (any Encodable)?,
            responseType: T.Type
        ) async throws -> T {
            requestCallCount += 1
            lastEndpoint = endpoint
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
            case .listGlobalMemories:
                guard let result = memoryListResponse as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "Type mismatch"])
                    )
                }
                return result
            case .listMemories(let characterId):
                let response = characterMemoryResponses[characterId] ?? MemoryListResponse(memories: [])
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
            requestVoidCallCount += 1
            lastEndpoint = endpoint
            if let error = deleteError {
                throw error
            }
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
        isDefault: Bool = true
    ) -> Character {
        Character(
            id: id,
            name: name,
            template: template,
            description: nil,
            avatarStyle: "default",
            isDefault: isDefault,
            lastMessageAt: nil,
            createdAt: Date()
        )
    }

    private static func makeMemory(
        id: String = "mem-1",
        memory: String = "Prefers morning workouts",
        createdAt: Date? = Date()
    ) -> MemoryItem {
        MemoryItem(id: id, memory: memory, createdAt: createdAt)
    }

    // MARK: - Helpers

    private func makeViewModel() -> (MemoriesViewModel, MockMemoriesAPIClient) {
        let mock = MockMemoriesAPIClient()
        let vm = MemoriesViewModel(apiClient: mock)
        return (vm, mock)
    }

    // MARK: - loadInitialData Tests

    @Test("loadInitialData fetches characters and then global memories")
    func loadInitialDataSuccess() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])

        let m1 = Self.makeMemory(id: "m1", memory: "Loves coffee")
        let m2 = Self.makeMemory(id: "m2", memory: "Works at Acme")
        let m3 = Self.makeMemory(id: "m3", memory: "Has a cat")
        mock.memoryListResponse = MemoryListResponse(memories: [m1, m2, m3])

        await vm.loadInitialData()

        #expect(vm.characters.count == 2)
        #expect(vm.selectedSegment == .global)
        #expect(vm.memories.count == 3)
        #expect(vm.isLoading == false)
        #expect(vm.isLoadingCharacters == false)
    }

    @Test("loadInitialData sets error when character fetch fails")
    func loadInitialDataCharacterError() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.networkError(
            NSError(domain: "Test", code: -1, userInfo: [NSLocalizedDescriptionKey: "No connection"])
        )

        await vm.loadInitialData()

        #expect(vm.characters.isEmpty)
        #expect(vm.showError == true)
        #expect(vm.errorMessage != nil)
        #expect(vm.isLoadingCharacters == false)
    }

    // MARK: - selectSegment Tests

    @Test("selectSegment changes segment and loads character memories")
    func selectSegmentChanges() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "char-1", name: "Luna")
        mock.characterListResponse = CharacterListResponse(characters: [c1])
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadInitialData()

        let m1 = Self.makeMemory(id: "cm1", memory: "Likes yoga")
        let m2 = Self.makeMemory(id: "cm2", memory: "Runs 5k daily")
        mock.characterMemoryResponses["char-1"] = MemoryListResponse(memories: [m1, m2])

        await vm.selectSegment(.character(id: "char-1", name: "Luna"))

        #expect(vm.selectedSegment == .character(id: "char-1", name: "Luna"))
        #expect(vm.memories.count == 2)
    }

    @Test("selectSegment with same segment is a no-op")
    func selectSegmentSameIsNoop() async {
        let (vm, mock) = makeViewModel()
        mock.characterListResponse = CharacterListResponse(characters: [])
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadInitialData()

        let callCountBefore = mock.requestCallCount

        await vm.selectSegment(.global)

        #expect(mock.requestCallCount == callCountBefore)
    }

    // MARK: - loadMemories Tests

    @Test("loadMemories sets error on failure")
    func loadMemoriesError() async {
        let (vm, mock) = makeViewModel()
        mock.characterListResponse = CharacterListResponse(characters: [])
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadInitialData()

        mock.requestError = APIError.serverError(statusCode: 503, detail: "Memory service unavailable")

        await vm.loadMemories()

        #expect(vm.showError == true)
        #expect(vm.errorMessage?.contains("unavailable") == true)
        #expect(vm.isLoading == false)
    }

    // MARK: - confirmDelete Tests

    @Test("confirmDelete removes memory from list on success (character memory)")
    func confirmDeleteCharacterMemory() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .character(id: "c1", name: "Luna")
        let m1 = Self.makeMemory(id: "m1", memory: "First")
        let m2 = Self.makeMemory(id: "m2", memory: "Second")
        let m3 = Self.makeMemory(id: "m3", memory: "Third")
        vm.memories = [m1, m2, m3]
        vm.memoryToDelete = m2

        await vm.confirmDelete()

        #expect(vm.memories.count == 2)
        #expect(vm.memories.contains(where: { $0.id == "m2" }) == false)
        #expect(mock.requestVoidCallCount == 1)
    }

    @Test("confirmDelete removes memory from list on success (global memory)")
    func confirmDeleteGlobalMemory() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "gm1", memory: "Global first")
        let m2 = Self.makeMemory(id: "gm2", memory: "Global second")
        vm.memories = [m1, m2]
        vm.memoryToDelete = m1

        await vm.confirmDelete()

        #expect(vm.memories.count == 1)
        #expect(vm.memories.first?.id == "gm2")
        #expect(mock.requestVoidCallCount == 1)
    }

    @Test("confirmDelete sets error on failure")
    func confirmDeleteError() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "Test")
        vm.memories = [m1]
        vm.memoryToDelete = m1
        mock.deleteError = APIError.serverError(statusCode: 500, detail: "Delete failed")

        await vm.confirmDelete()

        #expect(vm.showError == true)
        #expect(vm.memories.count == 1)
    }

    @Test("confirmDelete clears memoryToDelete")
    func confirmDeleteClearsMemory() async {
        let (vm, _) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "Test")
        vm.memories = [m1]
        vm.memoryToDelete = m1

        await vm.confirmDelete()

        #expect(vm.memoryToDelete == nil)
    }

    @Test("confirmDelete does nothing when memoryToDelete is nil")
    func confirmDeleteNilIsNoop() async {
        let (vm, mock) = makeViewModel()
        vm.memoryToDelete = nil

        await vm.confirmDelete()

        #expect(mock.requestVoidCallCount == 0)
    }

    // MARK: - showDeleteConfirmation Tests

    @Test("showDeleteConfirmation is true when memoryToDelete is set")
    func showDeleteConfirmationComputed() {
        let (vm, _) = makeViewModel()

        #expect(vm.showDeleteConfirmation == false)

        vm.memoryToDelete = Self.makeMemory(id: "m1")
        #expect(vm.showDeleteConfirmation == true)

        vm.showDeleteConfirmation = false
        #expect(vm.memoryToDelete == nil)
        #expect(vm.showDeleteConfirmation == false)
    }
}
