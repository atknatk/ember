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
        var lastDeleteEndpoint: APIEndpoint?

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
            lastDeleteEndpoint = endpoint
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

    // MARK: - Initial State

    @Test("initial state: memories empty, not loading, no error")
    func initialState() {
        let (vm, _) = makeViewModel()
        #expect(vm.memories.isEmpty)
        #expect(vm.characters.isEmpty)
        #expect(vm.isLoading == false)
        #expect(vm.isLoadingCharacters == false)
        #expect(vm.errorMessage == nil)
        #expect(vm.showError == false)
        #expect(vm.memoryToDelete == nil)
        #expect(vm.selectedSegment == .global)
        #expect(vm.showDeleteConfirmation == false)
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

    @Test("loadInitialData stops and does not load memories when character fetch fails")
    func loadInitialDataCharacterErrorPreventsMemoryLoad() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.serverError(statusCode: 503, detail: "Service unavailable")

        await vm.loadInitialData()

        // Only 1 API call (characters), memories never fetched
        #expect(mock.requestCallCount == 1)
        #expect(vm.memories.isEmpty)
    }

    @Test("loadInitialData resets selectedSegment to global even when previously set to character")
    func loadInitialDataSetsGlobalSegment() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .character(id: "c99", name: "Old")
        mock.characterListResponse = CharacterListResponse(characters: [])
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadInitialData()

        #expect(vm.selectedSegment == .global)
    }

    @Test("loadInitialData populates characters with correct names and ids")
    func loadInitialDataCorrectCharacterNames() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        let c2 = Self.makeCharacter(id: "c2", name: "Max", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadInitialData()

        #expect(vm.characters.first?.name == "Luna")
        #expect(vm.characters.last?.name == "Max")
        #expect(vm.characters.first?.id == "c1")
        #expect(vm.characters.last?.id == "c2")
    }

    @Test("loadInitialData succeeds with empty character list and shows no memories")
    func loadInitialDataEmptyCharacters() async {
        let (vm, mock) = makeViewModel()
        mock.characterListResponse = CharacterListResponse(characters: [])
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadInitialData()

        #expect(vm.characters.isEmpty)
        #expect(vm.selectedSegment == .global)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
        #expect(vm.showError == false)
    }

    @Test("loadInitialData clears isLoadingCharacters after completion")
    func loadInitialDataClearsLoadingCharacters() async {
        let (vm, mock) = makeViewModel()
        mock.characterListResponse = CharacterListResponse(characters: [])
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadInitialData()

        #expect(vm.isLoadingCharacters == false)
    }

    @Test("loadInitialData clears isLoading after memory fetch completes")
    func loadInitialDataClearsIsLoading() async {
        let (vm, mock) = makeViewModel()
        mock.characterListResponse = CharacterListResponse(characters: [])
        mock.memoryListResponse = MemoryListResponse(memories: [Self.makeMemory()])

        await vm.loadInitialData()

        #expect(vm.isLoading == false)
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

    @Test("selectSegment from character back to global loads global memories")
    func selectSegmentCharacterToGlobal() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        mock.characterListResponse = CharacterListResponse(characters: [c1])
        mock.memoryListResponse = MemoryListResponse(memories: [])
        await vm.loadInitialData()

        mock.characterMemoryResponses["c1"] = MemoryListResponse(memories: [
            Self.makeMemory(id: "cm1", memory: "Character memory")
        ])
        await vm.selectSegment(.character(id: "c1", name: "Luna"))
        #expect(vm.memories.count == 1)

        let globalMemory = Self.makeMemory(id: "gm1", memory: "Global memory")
        mock.memoryListResponse = MemoryListResponse(memories: [globalMemory])
        await vm.selectSegment(.global)

        #expect(vm.selectedSegment == .global)
        #expect(vm.memories.count == 1)
        #expect(vm.memories.first?.memory == "Global memory")
    }

    @Test("selectSegment between different characters loads each character's memories correctly")
    func selectSegmentDifferentCharacters() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", template: "fitness_coach", isDefault: false)
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])
        mock.memoryListResponse = MemoryListResponse(memories: [])
        await vm.loadInitialData()

        mock.characterMemoryResponses["c1"] = MemoryListResponse(memories: [
            Self.makeMemory(id: "m1", memory: "Luna memory")
        ])
        mock.characterMemoryResponses["c2"] = MemoryListResponse(memories: [
            Self.makeMemory(id: "m2", memory: "Coach memory A"),
            Self.makeMemory(id: "m3", memory: "Coach memory B"),
        ])

        await vm.selectSegment(.character(id: "c1", name: "Luna"))
        #expect(vm.memories.count == 1)
        #expect(vm.memories.first?.memory == "Luna memory")

        await vm.selectSegment(.character(id: "c2", name: "Coach"))
        #expect(vm.memories.count == 2)
        #expect(vm.memories.contains(where: { $0.memory == "Coach memory A" }) == true)
    }

    @Test("selectSegment same character segment twice is a no-op")
    func selectSegmentSameCharacterIsNoop() async {
        let (vm, mock) = makeViewModel()
        mock.characterListResponse = CharacterListResponse(characters: [])
        mock.memoryListResponse = MemoryListResponse(memories: [])
        await vm.loadInitialData()

        mock.characterMemoryResponses["c1"] = MemoryListResponse(memories: [])
        await vm.selectSegment(.character(id: "c1", name: "Luna"))
        let callCountAfterFirst = mock.requestCallCount

        await vm.selectSegment(.character(id: "c1", name: "Luna"))
        #expect(mock.requestCallCount == callCountAfterFirst)
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

    @Test("loadMemories clears errorMessage at start of each call")
    func loadMemoriesClearsErrorMessage() async {
        let (vm, mock) = makeViewModel()
        vm.errorMessage = "Old error"
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadMemories()

        // loadMemories sets errorMessage = nil at the start
        #expect(vm.errorMessage == nil)
    }

    @Test("loadMemories sets isLoading false after success")
    func loadMemoriesIsLoadingFalseAfterSuccess() async {
        let (vm, mock) = makeViewModel()
        mock.memoryListResponse = MemoryListResponse(memories: [Self.makeMemory()])

        await vm.loadMemories()

        #expect(vm.isLoading == false)
    }

    @Test("loadMemories sets isLoading false after failure")
    func loadMemoriesIsLoadingFalseAfterFailure() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.networkError(NSError(domain: "t", code: -1))

        await vm.loadMemories()

        #expect(vm.isLoading == false)
    }

    @Test("loadMemories for global segment uses listGlobalMemories endpoint")
    func loadMemoriesGlobalUsesCorrectEndpoint() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .global
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadMemories()

        if case .listGlobalMemories = mock.lastEndpoint {
            // correct endpoint was used
        } else {
            Issue.record("Expected .listGlobalMemories endpoint, got \(String(describing: mock.lastEndpoint))")
        }
    }

    @Test("loadMemories for character segment uses listMemories endpoint with correct characterId")
    func loadMemoriesCharacterUsesCorrectEndpoint() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .character(id: "char-42", name: "Emma")
        mock.characterMemoryResponses["char-42"] = MemoryListResponse(memories: [])

        await vm.loadMemories()

        if case .listMemories(let id) = mock.lastEndpoint {
            #expect(id == "char-42")
        } else {
            Issue.record("Expected .listMemories endpoint, got \(String(describing: mock.lastEndpoint))")
        }
    }

    @Test("loadMemories populates memories with correct content and ids")
    func loadMemoriesPopulatesContent() async {
        let (vm, mock) = makeViewModel()
        let m1 = Self.makeMemory(id: "m1", memory: "Name is Alex")
        let m2 = Self.makeMemory(id: "m2", memory: "Prefers short responses")
        mock.memoryListResponse = MemoryListResponse(memories: [m1, m2])

        await vm.loadMemories()

        #expect(vm.memories.count == 2)
        #expect(vm.memories[0].memory == "Name is Alex")
        #expect(vm.memories[1].memory == "Prefers short responses")
        #expect(vm.memories[0].id == "m1")
        #expect(vm.memories[1].id == "m2")
    }

    @Test("loadMemories with 401 unauthorized sets error")
    func loadMemoriesUnauthorized() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.unauthorized

        await vm.loadMemories()

        #expect(vm.showError == true)
        #expect(vm.errorMessage != nil)
        #expect(vm.isLoading == false)
    }

    @Test("loadMemories with empty response replaces previous memories with empty list")
    func loadMemoriesEmptyResponseClearsPrevious() async {
        let (vm, mock) = makeViewModel()
        vm.memories = [Self.makeMemory(id: "old")]
        mock.memoryListResponse = MemoryListResponse(memories: [])

        await vm.loadMemories()

        #expect(vm.memories.isEmpty)
        #expect(vm.errorMessage == nil)
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

    @Test("confirmDelete clears memoryToDelete on success")
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

    @Test("confirmDelete clears memoryToDelete even on failure")
    func confirmDeleteClearsMemoryToDeleteOnFailure() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "Test")
        vm.memories = [m1]
        vm.memoryToDelete = m1
        mock.deleteError = APIError.serverError(statusCode: 500, detail: "error")

        await vm.confirmDelete()

        #expect(vm.memoryToDelete == nil)
    }

    @Test("confirmDelete for character memory routes to deleteMemory with correct characterId and memoryId")
    func confirmDeleteCharacterRoutesCorrectEndpoint() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .character(id: "char-99", name: "Luna")
        let m1 = Self.makeMemory(id: "mem-abc", memory: "Test")
        vm.memories = [m1]
        vm.memoryToDelete = m1

        await vm.confirmDelete()

        if case .deleteMemory(let characterId, let memoryId) = mock.lastDeleteEndpoint {
            #expect(characterId == "char-99")
            #expect(memoryId == "mem-abc")
        } else {
            Issue.record("Expected .deleteMemory endpoint, got \(String(describing: mock.lastDeleteEndpoint))")
        }
    }

    @Test("confirmDelete for global memory routes to deleteGlobalMemory with correct memoryId")
    func confirmDeleteGlobalRoutesCorrectEndpoint() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "mem-xyz", memory: "Test")
        vm.memories = [m1]
        vm.memoryToDelete = m1

        await vm.confirmDelete()

        if case .deleteGlobalMemory(let memoryId) = mock.lastDeleteEndpoint {
            #expect(memoryId == "mem-xyz")
        } else {
            Issue.record("Expected .deleteGlobalMemory endpoint, got \(String(describing: mock.lastDeleteEndpoint))")
        }
    }

    @Test("confirmDelete preserves order of remaining memories after deletion")
    func confirmDeletePreservesOrder() async {
        let (vm, _) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "Alpha")
        let m2 = Self.makeMemory(id: "m2", memory: "Beta")
        let m3 = Self.makeMemory(id: "m3", memory: "Gamma")
        vm.memories = [m1, m2, m3]
        vm.memoryToDelete = m2

        await vm.confirmDelete()

        #expect(vm.memories.count == 2)
        #expect(vm.memories[0].id == "m1")
        #expect(vm.memories[1].id == "m3")
    }

    @Test("confirmDelete failure sets errorMessage and showError")
    func confirmDeleteFailureSetsErrorMessage() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "Test")
        vm.memories = [m1]
        vm.memoryToDelete = m1
        mock.deleteError = APIError.networkError(
            NSError(domain: "test", code: -1009, userInfo: [NSLocalizedDescriptionKey: "offline"])
        )

        await vm.confirmDelete()

        #expect(vm.errorMessage != nil)
        #expect(vm.showError == true)
    }

    @Test("confirmDelete failure does not remove memory from list")
    func confirmDeleteFailureKeepsMemory() async {
        let (vm, mock) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "Stay")
        let m2 = Self.makeMemory(id: "m2", memory: "Also stay")
        vm.memories = [m1, m2]
        vm.memoryToDelete = m1
        mock.deleteError = APIError.serverError(statusCode: 503, detail: "Service down")

        await vm.confirmDelete()

        #expect(vm.memories.count == 2)
        #expect(vm.memories.contains(where: { $0.id == "m1" }) == true)
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

    @Test("showDeleteConfirmation setter to false clears memoryToDelete")
    func showDeleteConfirmationSetterClearsMemoryToDelete() {
        let (vm, _) = makeViewModel()
        vm.memoryToDelete = Self.makeMemory(id: "m1", memory: "Should be cleared")

        vm.showDeleteConfirmation = false

        #expect(vm.memoryToDelete == nil)
    }

    @Test("showDeleteConfirmation setter to true when memoryToDelete is nil has no effect")
    func showDeleteConfirmationSetterTrueNoEffect() {
        let (vm, _) = makeViewModel()
        vm.showDeleteConfirmation = true
        #expect(vm.memoryToDelete == nil)
        #expect(vm.showDeleteConfirmation == false)
    }

    // MARK: - MemorySegment Equality Tests

    @Test("MemorySegment global equals global")
    func memorySegmentGlobalEquality() {
        let s1 = MemorySegment.global
        let s2 = MemorySegment.global
        #expect(s1 == s2)
    }

    @Test("MemorySegment character with same id and name are equal")
    func memorySegmentCharacterEquality() {
        let s1 = MemorySegment.character(id: "c1", name: "Luna")
        let s2 = MemorySegment.character(id: "c1", name: "Luna")
        #expect(s1 == s2)
    }

    @Test("MemorySegment global does not equal character segment")
    func memorySegmentGlobalNotEqualCharacter() {
        let global = MemorySegment.global
        let character = MemorySegment.character(id: "c1", name: "Luna")
        #expect(global != character)
    }

    @Test("MemorySegment different character ids are not equal")
    func memorySegmentDifferentCharacterIds() {
        let s1 = MemorySegment.character(id: "c1", name: "Luna")
        let s2 = MemorySegment.character(id: "c2", name: "Luna")
        #expect(s1 != s2)
    }

    // MARK: - MemoryItem Model Tests

    @Test("MemoryItem with nil createdAt is valid and accessible")
    func memoryItemNilCreatedAt() {
        let m = MemoryItem(id: "m1", memory: "No timestamp", createdAt: nil)
        #expect(m.createdAt == nil)
        #expect(m.memory == "No timestamp")
        #expect(m.id == "m1")
    }

    @Test("MemoryItem equality requires all fields to match")
    func memoryItemEqualityRequiresAllFields() {
        let date = Date(timeIntervalSince1970: 1700000000)
        let m1 = MemoryItem(id: "same-id", memory: "Content A", createdAt: date)
        let m2 = MemoryItem(id: "same-id", memory: "Content B", createdAt: date)
        #expect(m1 != m2)
    }

    // MARK: - Error Recovery Tests

    @Test("showError can be manually cleared after an error occurs")
    func showErrorCanBeCleared() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.networkError(NSError(domain: "t", code: -1))

        await vm.loadMemories()
        #expect(vm.showError == true)

        vm.showError = false
        #expect(vm.showError == false)
    }

    @Test("retry after error: successful loadMemories clears errorMessage and populates memories")
    func retryAfterErrorClearsError() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.networkError(NSError(domain: "t", code: -1))
        await vm.loadMemories()
        #expect(vm.showError == true)

        // Retry with success
        mock.requestError = nil
        mock.memoryListResponse = MemoryListResponse(memories: [Self.makeMemory()])
        await vm.loadMemories()

        // loadMemories clears errorMessage at start regardless of outcome
        #expect(vm.errorMessage == nil)
        // Successfully loads memories on retry
        #expect(vm.memories.count == 1)
        #expect(vm.isLoading == false)
    }

    // MARK: - Sequence Tests

    @Test("multiple segment switches correctly update memories each time")
    func multipleSegmentSwitches() async {
        let (vm, mock) = makeViewModel()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        mock.characterListResponse = CharacterListResponse(characters: [c1])
        mock.memoryListResponse = MemoryListResponse(memories: [Self.makeMemory(id: "g1")])
        await vm.loadInitialData()
        #expect(vm.memories.count == 1)

        mock.characterMemoryResponses["c1"] = MemoryListResponse(memories: [
            Self.makeMemory(id: "cm1"),
            Self.makeMemory(id: "cm2"),
        ])
        await vm.selectSegment(.character(id: "c1", name: "Luna"))
        #expect(vm.memories.count == 2)

        mock.memoryListResponse = MemoryListResponse(memories: [
            Self.makeMemory(id: "g2"),
            Self.makeMemory(id: "g3"),
            Self.makeMemory(id: "g4"),
        ])
        await vm.selectSegment(.global)
        #expect(vm.memories.count == 3)
    }

    @Test("deleting multiple memories in sequence reduces list correctly")
    func deleteMultipleMemoriesInSequence() async {
        let (vm, _) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "First")
        let m2 = Self.makeMemory(id: "m2", memory: "Second")
        let m3 = Self.makeMemory(id: "m3", memory: "Third")
        vm.memories = [m1, m2, m3]

        vm.memoryToDelete = m1
        await vm.confirmDelete()
        #expect(vm.memories.count == 2)

        vm.memoryToDelete = m3
        await vm.confirmDelete()
        #expect(vm.memories.count == 1)
        #expect(vm.memories.first?.id == "m2")
    }

    @Test("deleting last memory in list results in empty memories array")
    func deletingLastMemoryResultsInEmptyList() async {
        let (vm, _) = makeViewModel()
        vm.selectedSegment = .global
        let m1 = Self.makeMemory(id: "m1", memory: "Only one")
        vm.memories = [m1]
        vm.memoryToDelete = m1

        await vm.confirmDelete()

        #expect(vm.memories.isEmpty)
        #expect(vm.memoryToDelete == nil)
    }
}
