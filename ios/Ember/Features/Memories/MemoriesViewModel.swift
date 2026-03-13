import Foundation
import Observation
import SwiftUI

/// Represents which segment of memories the user is viewing.
enum MemorySegment: Hashable {
    case global
    case character(id: String, name: String)
}

@Observable
final class MemoriesViewModel {
    // MARK: - Public State

    var characters: [Character] = []
    var selectedSegment: MemorySegment = .global
    var memories: [MemoryItem] = []
    var isLoading: Bool = false
    var isLoadingCharacters: Bool = false
    var errorMessage: String? = nil
    var currentError: EmberError? = nil
    var showError: Bool = false
    var memoryToDelete: MemoryItem? = nil

    /// Controls the delete confirmation alert.
    /// Setting to `false` clears `memoryToDelete`.
    var showDeleteConfirmation: Bool {
        get { memoryToDelete != nil }
        set { if !newValue { memoryToDelete = nil } }
    }

    func dismissError() {
        errorMessage = nil
        currentError = nil
        showError = false
    }

    // MARK: - Dependencies

    private let apiClient: APIClientProtocol

    // MARK: - Init

    init(apiClient: APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    // MARK: - Actions

    /// Fetches the character list and then loads global memories.
    func loadInitialData() async {
        isLoadingCharacters = true

        do {
            let response: CharacterListResponse = try await apiClient.request(
                endpoint: .listCharacters,
                responseType: CharacterListResponse.self
            )
            characters = response.characters
        } catch {
            let emberError = EmberError.from(error)
            currentError = emberError
            errorMessage = emberError.errorDescription
            showError = true
            isLoadingCharacters = false
            return
        }

        isLoadingCharacters = false
        selectedSegment = .global
        await loadMemories()
    }

    /// Switches the selected segment and loads memories for it.
    func selectSegment(_ segment: MemorySegment) async {
        guard segment != selectedSegment else { return }
        selectedSegment = segment
        await loadMemories()
    }

    /// Fetches memories for the currently selected segment.
    func loadMemories() async {
        isLoading = true
        errorMessage = nil

        do {
            let response: MemoryListResponse
            switch selectedSegment {
            case .global:
                response = try await apiClient.request(
                    endpoint: .listGlobalMemories,
                    responseType: MemoryListResponse.self
                )
            case .character(let id, _):
                response = try await apiClient.request(
                    endpoint: .listMemories(characterId: id),
                    responseType: MemoryListResponse.self
                )
            }
            memories = response.memories
        } catch {
            let emberError = EmberError.from(error)
            currentError = emberError
            errorMessage = emberError.errorDescription
            showError = true
            HapticManager.notification(.error)
        }

        isLoading = false
    }

    /// Deletes the memory stored in `memoryToDelete` via the appropriate endpoint.
    func confirmDelete() async {
        guard let memory = memoryToDelete else { return }

        do {
            switch selectedSegment {
            case .global:
                try await apiClient.requestVoid(
                    endpoint: .deleteGlobalMemory(memoryId: memory.id)
                )
            case .character(let id, _):
                try await apiClient.requestVoid(
                    endpoint: .deleteMemory(characterId: id, memoryId: memory.id)
                )
            }

            withAnimation {
                memories.removeAll { $0.id == memory.id }
            }
            HapticManager.notification(.success)
        } catch {
            let emberError = EmberError.from(error)
            currentError = emberError
            errorMessage = emberError.errorDescription
            showError = true
            HapticManager.notification(.error)
        }

        memoryToDelete = nil
    }
}
