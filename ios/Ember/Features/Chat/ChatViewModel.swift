import Foundation
import Observation

/// Represents a single chat message displayed in the UI.
/// Distinct from `MessagePreview` (which is for home screen previews).
struct ChatMessage: Identifiable, Equatable {
    /// Mutable because the `done` SSE event replaces the local UUID with the server-assigned ID.
    var id: String
    let role: MessageRole
    var content: String
    let createdAt: Date
    /// True while this message is being streamed from the AI.
    var isStreaming: Bool

    enum MessageRole: String, Equatable {
        case user
        case assistant
    }

    /// Creates a user message with a local UUID and the current timestamp.
    static func userMessage(content: String) -> ChatMessage {
        ChatMessage(
            id: UUID().uuidString,
            role: .user,
            content: content,
            createdAt: Date(),
            isStreaming: false
        )
    }

    /// Creates an empty assistant message placeholder for streaming.
    static func streamingPlaceholder() -> ChatMessage {
        ChatMessage(
            id: UUID().uuidString,
            role: .assistant,
            content: "",
            createdAt: Date(),
            isStreaming: true
        )
    }
}

/// A date separator item displayed between message groups on different days.
struct DateSeparator: Identifiable, Equatable {
    let id: String
    let date: Date
}

/// Unified item type for the chat list, supporting both messages and date separators.
enum ChatListItem: Identifiable, Equatable {
    case message(ChatMessage)
    case dateSeparator(DateSeparator)

    var id: String {
        switch self {
        case .message(let msg): return msg.id
        case .dateSeparator(let sep): return sep.id
        }
    }
}

@Observable
final class ChatViewModel {
    // MARK: - Public State

    var messages: [ChatMessage] = []
    var inputText: String = ""
    var isStreaming: Bool = false
    var isLoadingHistory: Bool = false
    var isLoadingMore: Bool = false
    var errorMessage: String? = nil
    var currentError: EmberError? = nil
    var characterName: String

    // MARK: - Pagination State

    private(set) var hasMore: Bool = true
    private var nextCursor: String? = nil
    private var isLoadMoreInProgress: Bool = false

    // MARK: - Dependencies

    private let characterId: String
    private let service: ChatServiceProtocol
    private let pageSize: Int = 20

    // MARK: - Init

    init(
        characterId: String,
        characterName: String = "",
        service: ChatServiceProtocol = ChatService()
    ) {
        self.characterId = characterId
        self.characterName = characterName
        self.service = service
    }

    // MARK: - Computed Properties

    /// Builds a list of chat items with date separators inserted between day boundaries.
    var chatListItems: [ChatListItem] {
        guard !messages.isEmpty else { return [] }

        var items: [ChatListItem] = []
        let calendar = Calendar.current
        var lastDay: DateComponents?

        for message in messages {
            let messageDay = calendar.dateComponents([.year, .month, .day], from: message.createdAt)
            if messageDay != lastDay {
                let separator = DateSeparator(
                    id: "sep-\(messageDay.year ?? 0)-\(messageDay.month ?? 0)-\(messageDay.day ?? 0)",
                    date: message.createdAt
                )
                items.append(.dateSeparator(separator))
                lastDay = messageDay
            }
            items.append(.message(message))
        }

        return items
    }

    // MARK: - Load History

    /// Loads the initial page of message history.
    func loadHistory() async {
        guard !isLoadingHistory else { return }
        isLoadingHistory = true
        errorMessage = nil

        do {
            let response = try await service.loadMessages(
                characterId: characterId,
                cursor: nil,
                limit: pageSize
            )

            messages = mapResponseToMessages(response).reversed()
            nextCursor = response.nextCursor
            hasMore = response.hasMore
        } catch {
            let emberError = EmberError.from(error)
            currentError = emberError
            errorMessage = emberError.errorDescription
        }

        isLoadingHistory = false
    }

    /// Loads the next page of older messages (infinite scroll upward).
    func loadMoreIfNeeded() async {
        guard hasMore,
              !isLoadMoreInProgress,
              !isLoadingHistory,
              !isStreaming,
              let cursor = nextCursor else {
            return
        }

        isLoadMoreInProgress = true
        isLoadingMore = true

        do {
            let response = try await service.loadMessages(
                characterId: characterId,
                cursor: cursor,
                limit: pageSize
            )

            let olderMessages = mapResponseToMessages(response).reversed()
            messages.insert(contentsOf: olderMessages, at: 0)
            nextCursor = response.nextCursor
            hasMore = response.hasMore
        } catch {
            // Silently fail on load-more; user can scroll up again to retry
        }

        isLoadingMore = false
        isLoadMoreInProgress = false
    }

    // MARK: - Send Message

    /// Sends the current input text and streams the AI response.
    func sendMessage() async {
        let trimmed = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isStreaming else { return }

        let content = trimmed
        inputText = ""
        isStreaming = true
        errorMessage = nil

        // Append user message immediately
        let userMessage = ChatMessage.userMessage(content: content)
        messages.append(userMessage)

        // Haptic feedback for message send
        HapticManager.impact(.light)

        // Append streaming placeholder for assistant
        var assistantMessage = ChatMessage.streamingPlaceholder()
        messages.append(assistantMessage)

        do {
            for try await event in service.streamMessage(characterId: characterId, content: content) {
                switch event {
                case .chunk(let chunk):
                    assistantMessage.content += chunk
                    updateLastMessage(assistantMessage)

                case .done(let messageId):
                    assistantMessage.id = messageId
                    assistantMessage.isStreaming = false
                    updateLastMessage(assistantMessage)

                case .action:
                    // Device action intents are logged but not handled in Phase 3.
                    // Future: trigger alarm/calendar from action payload.
                    break

                case .error(let message):
                    removeLastAssistantIfEmpty()
                    let emberError = EmberError.unknown(message)
                    currentError = emberError
                    errorMessage = message
                    HapticManager.notification(.error)

                case .moderation(let message):
                    removeLastAssistantIfEmpty()
                    let emberError = EmberError.unknown(message)
                    currentError = emberError
                    errorMessage = message
                }
            }
        } catch {
            removeLastAssistantIfEmpty()
            let emberError = EmberError.from(error)
            currentError = emberError
            errorMessage = emberError.errorDescription
            HapticManager.notification(.error)
        }

        isStreaming = false
    }

    /// Dismisses the current error banner.
    func dismissError() {
        errorMessage = nil
        currentError = nil
    }

    // MARK: - Private Helpers

    /// Maps an API response page into `ChatMessage` values.
    /// API returns newest-first; this returns the same order (caller reverses if needed).
    private func mapResponseToMessages(_ response: ChatMessageListResponse) -> [ChatMessage] {
        response.items.map { message in
            ChatMessage(
                id: message.id,
                role: message.role == "user" ? .user : .assistant,
                content: message.content,
                createdAt: message.createdAt,
                isStreaming: false
            )
        }
    }

    /// Replaces the last message in the array with the updated version.
    private func updateLastMessage(_ message: ChatMessage) {
        guard !messages.isEmpty else { return }
        messages[messages.count - 1] = message
    }

    /// Removes the last message if it is an empty assistant placeholder (stream failed).
    private func removeLastAssistantIfEmpty() {
        guard let last = messages.last,
              last.role == .assistant,
              last.content.isEmpty else {
            return
        }
        messages.removeLast()
    }
}
