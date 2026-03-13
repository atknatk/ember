import Foundation
import Observation

@Observable
final class HomeViewModel {
    // MARK: - Public State

    var characters: [Character] = []
    var lastMessages: [String: MessagePreview] = [:]
    var isLoading: Bool = false
    var isRefreshing: Bool = false
    var errorMessage: String? = nil
    var userName: String

    // MARK: - Dependencies

    private let apiClient: APIClientProtocol

    // MARK: - Init

    init(apiClient: APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
        self.userName = UserDefaults.standard.string(forKey: "user_name") ?? ""
    }

    // MARK: - Computed Properties

    /// The user's default character (where `isDefault == true`).
    var defaultCharacter: Character? {
        characters.first(where: { $0.isDefault })
    }

    /// The last message from the default character, for the daily summary card.
    var defaultCharacterLastMessage: MessagePreview? {
        guard let defaultChar = defaultCharacter else { return nil }
        return lastMessages[defaultChar.id]
    }

    // MARK: - Actions

    func loadCharacters() async {
        if characters.isEmpty {
            isLoading = true
        } else {
            isRefreshing = true
        }
        errorMessage = nil

        do {
            let response: CharacterListResponse = try await apiClient.request(
                endpoint: .listCharacters,
                responseType: CharacterListResponse.self
            )
            characters = response.characters

            await loadLastMessages(for: response.characters)
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
        isRefreshing = false
    }

    // MARK: - Private

    private func loadLastMessages(for characters: [Character]) async {
        await withTaskGroup(of: (String, MessagePreview?).self) { group in
            for character in characters {
                group.addTask { [apiClient] in
                    do {
                        let response: MessageListResponse = try await apiClient.request(
                            endpoint: .listMessages(characterId: character.id, cursor: nil, limit: 1),
                            responseType: MessageListResponse.self
                        )
                        return (character.id, response.items.first)
                    } catch {
                        return (character.id, nil)
                    }
                }
            }

            for await (characterId, preview) in group {
                if let preview {
                    lastMessages[characterId] = preview
                }
            }
        }
    }

    // MARK: - Static Helpers

    /// Returns the SF Symbol name for a given character template.
    static func templateIcon(for template: String) -> String {
        switch template {
        case "companion":
            return EmberSymbol.templateCompanion
        case "english_teacher":
            return EmberSymbol.templateEnglishTeacher
        case "therapist":
            return EmberSymbol.templateTherapist
        case "fitness_coach":
            return EmberSymbol.templateFitnessCoach
        case "career_coach":
            return EmberSymbol.templateCareerCoach
        case "custom":
            return EmberSymbol.templateCustom
        default:
            return EmberSymbol.templateCompanion
        }
    }

    /// Returns a time-of-day greeting string.
    static func greeting(for date: Date = Date()) -> String {
        let hour = Calendar.current.component(.hour, from: date)
        switch hour {
        case 5...11:
            return "Good morning"
        case 12...16:
            return "Good afternoon"
        default:
            return "Good evening"
        }
    }

    // MARK: - Local Unread Tracking

    /// Returns the date the user last opened a character's chat, or nil if never opened.
    static func lastOpenedDate(for characterId: String) -> Date? {
        guard let dict = UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double] else {
            return nil
        }
        guard let timestamp = dict[characterId] else { return nil }
        return Date(timeIntervalSince1970: timestamp)
    }

    /// Stores the current date as the last time the user opened a character's chat.
    static func markCharacterAsOpened(_ characterId: String) {
        var dict = (UserDefaults.standard.dictionary(forKey: "character_last_opened") as? [String: Double]) ?? [:]
        dict[characterId] = Date().timeIntervalSince1970
        UserDefaults.standard.set(dict, forKey: "character_last_opened")
    }

    /// Returns whether a character has unread messages.
    static func hasUnreadMessages(for character: Character) -> Bool {
        guard let lastMessageAt = character.lastMessageAt else { return false }
        guard let lastOpened = lastOpenedDate(for: character.id) else {
            // Never opened this character -- any message is "unread"
            return true
        }
        return lastMessageAt > lastOpened
    }
}
