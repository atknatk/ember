import Testing
import Foundation
@testable import Ember

/// Extended tests for APIEndpoint — edge cases not covered by APIEndpointTests.swift.
/// Focuses on: remaining endpoint paths, special-character IDs, method coverage
/// for all endpoints, requiresAuth coverage for non-auth cases, and queryItems
/// boundary conditions.
@Suite("APIEndpoint Extended")
struct APIEndpointExtendedTests {

    // MARK: - Remaining Paths

    @Test("createCharacter path is /api/v1/characters")
    func createCharacterPath() {
        #expect(APIEndpoint.createCharacter.path == "/api/v1/characters")
    }

    @Test("updateCharacter path includes character ID")
    func updateCharacterPath() {
        #expect(APIEndpoint.updateCharacter(id: "char-001").path == "/api/v1/characters/char-001")
    }

    @Test("deleteCharacter path includes character ID")
    func deleteCharacterPath() {
        #expect(APIEndpoint.deleteCharacter(id: "xyz-789").path == "/api/v1/characters/xyz-789")
    }

    @Test("listMessages path includes character ID")
    func listMessagesPath() {
        #expect(
            APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 20).path
                == "/api/v1/characters/abc/messages"
        )
    }

    @Test("deleteAllMemories path includes character ID")
    func deleteAllMemoriesPath() {
        #expect(
            APIEndpoint.deleteAllMemories(characterId: "char-99").path
                == "/api/v1/characters/char-99/memories"
        )
    }

    @Test("completeOnboarding path is /api/v1/onboarding/complete")
    func completeOnboardingPath() {
        #expect(APIEndpoint.completeOnboarding.path == "/api/v1/onboarding/complete")
    }

    @Test("updateFCMToken path is /api/v1/notifications/fcm-token")
    func updateFCMTokenPath() {
        #expect(APIEndpoint.updateFCMToken.path == "/api/v1/notifications/fcm-token")
    }

    @Test("updateNotificationPreferences path is /api/v1/notifications/preferences")
    func updateNotificationPreferencesPath() {
        #expect(APIEndpoint.updateNotificationPreferences.path == "/api/v1/notifications/preferences")
    }

    @Test("updateProfile path is /api/v1/profile")
    func updateProfilePath() {
        #expect(APIEndpoint.updateProfile.path == "/api/v1/profile")
    }

    @Test("deleteMemory path includes both character and memory IDs")
    func deleteMemoryPathWithBothIDs() {
        #expect(
            APIEndpoint.deleteMemory(characterId: "c-001", memoryId: "m-999").path
                == "/api/v1/characters/c-001/memories/m-999"
        )
    }

    // MARK: - Path Consistency: sendMessage and streamMessage share path

    @Test("sendMessage and streamMessage share the same path for same characterId")
    func sendAndStreamMessageSharePath() {
        let characterId = "char-shared"
        #expect(
            APIEndpoint.sendMessage(characterId: characterId).path
                == APIEndpoint.streamMessage(characterId: characterId).path
        )
    }

    // MARK: - Path Consistency: listMessages and sendMessage share path

    @Test("listMessages and sendMessage share the same path for same characterId")
    func listMessagesAndSendMessageSharePath() {
        let characterId = "char-same"
        #expect(
            APIEndpoint.listMessages(characterId: characterId, cursor: nil, limit: 20).path
                == APIEndpoint.sendMessage(characterId: characterId).path
        )
    }

    // MARK: - Path Consistency: listMemories and deleteAllMemories share path

    @Test("listMemories and deleteAllMemories share the same path")
    func listAndDeleteAllMemoriesSharePath() {
        let characterId = "char-mem"
        #expect(
            APIEndpoint.listMemories(characterId: characterId).path
                == APIEndpoint.deleteAllMemories(characterId: characterId).path
        )
    }

    // MARK: - Method Coverage (remaining cases)

    @Test("listMessages method is GET")
    func listMessagesMethod() {
        #expect(APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 20).method == .get)
    }

    @Test("listMemories method is GET")
    func listMemoriesMethod() {
        #expect(APIEndpoint.listMemories(characterId: "abc").method == .get)
    }

    @Test("deleteMemory method is DELETE")
    func deleteMemoryMethod() {
        #expect(APIEndpoint.deleteMemory(characterId: "c", memoryId: "m").method == .delete)
    }

    @Test("deleteAllMemories method is DELETE")
    func deleteAllMemoriesMethod() {
        #expect(APIEndpoint.deleteAllMemories(characterId: "c").method == .delete)
    }

    @Test("updateCharacter method is PUT")
    func updateCharacterMethod() {
        #expect(APIEndpoint.updateCharacter(id: "abc").method == .put)
    }

    @Test("updateNotificationPreferences method is PUT")
    func updateNotificationPreferencesMethod() {
        #expect(APIEndpoint.updateNotificationPreferences.method == .put)
    }

    @Test("completeOnboarding method is POST")
    func completeOnboardingMethod() {
        #expect(APIEndpoint.completeOnboarding.method == .post)
    }

    @Test("updateFCMToken method is POST")
    func updateFCMTokenMethod() {
        #expect(APIEndpoint.updateFCMToken.method == .post)
    }

    @Test("uploadURL method is POST")
    func uploadURLMethod() {
        #expect(APIEndpoint.uploadURL.method == .post)
    }

    @Test("deleteAccount method is DELETE")
    func deleteAccountMethod() {
        #expect(APIEndpoint.deleteAccount.method == .delete)
    }

    @Test("login method is POST")
    func loginMethod() {
        #expect(APIEndpoint.login.method == .post)
    }

    @Test("refreshToken method is POST")
    func refreshTokenMethod() {
        #expect(APIEndpoint.refreshToken.method == .post)
    }

    // MARK: - requiresAuth Coverage (remaining cases)

    @Test("listMessages requires auth")
    func listMessagesRequiresAuth() {
        #expect(APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 20).requiresAuth == true)
    }

    @Test("streamMessage requires auth")
    func streamMessageRequiresAuth() {
        #expect(APIEndpoint.streamMessage(characterId: "abc").requiresAuth == true)
    }

    @Test("listMemories requires auth")
    func listMemoriesRequiresAuth() {
        #expect(APIEndpoint.listMemories(characterId: "abc").requiresAuth == true)
    }

    @Test("deleteMemory requires auth")
    func deleteMemoryRequiresAuth() {
        #expect(APIEndpoint.deleteMemory(characterId: "c", memoryId: "m").requiresAuth == true)
    }

    @Test("deleteAllMemories requires auth")
    func deleteAllMemoriesRequiresAuth() {
        #expect(APIEndpoint.deleteAllMemories(characterId: "abc").requiresAuth == true)
    }

    @Test("getProfile requires auth")
    func getProfileRequiresAuth() {
        #expect(APIEndpoint.getProfile.requiresAuth == true)
    }

    @Test("updateProfile requires auth")
    func updateProfileRequiresAuth() {
        #expect(APIEndpoint.updateProfile.requiresAuth == true)
    }

    @Test("updateCharacter requires auth")
    func updateCharacterRequiresAuth() {
        #expect(APIEndpoint.updateCharacter(id: "abc").requiresAuth == true)
    }

    @Test("deleteCharacter requires auth")
    func deleteCharacterRequiresAuth() {
        #expect(APIEndpoint.deleteCharacter(id: "abc").requiresAuth == true)
    }

    @Test("completeOnboarding requires auth")
    func completeOnboardingRequiresAuth() {
        #expect(APIEndpoint.completeOnboarding.requiresAuth == true)
    }

    @Test("updateFCMToken requires auth")
    func updateFCMTokenRequiresAuth() {
        #expect(APIEndpoint.updateFCMToken.requiresAuth == true)
    }

    @Test("updateNotificationPreferences requires auth")
    func updateNotificationPreferencesRequiresAuth() {
        #expect(APIEndpoint.updateNotificationPreferences.requiresAuth == true)
    }

    @Test("uploadURL requires auth")
    func uploadURLRequiresAuth() {
        #expect(APIEndpoint.uploadURL.requiresAuth == true)
    }

    // MARK: - queryItems Edge Cases

    @Test("listMessages with limit 1 encodes limit correctly")
    func listMessagesLimitOne() {
        let endpoint = APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 1)
        let items = endpoint.queryItems
        let itemDict = Dictionary(uniqueKeysWithValues: (items ?? []).map { ($0.name, $0.value) })
        #expect(itemDict["limit"] == "1")
    }

    @Test("listMessages with limit 100 encodes limit correctly")
    func listMessagesLimitHundred() {
        let endpoint = APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 100)
        let items = endpoint.queryItems
        let itemDict = Dictionary(uniqueKeysWithValues: (items ?? []).map { ($0.name, $0.value) })
        #expect(itemDict["limit"] == "100")
    }

    @Test("listMessages cursor value is preserved exactly")
    func listMessagesCursorPreserved() {
        let cursorValue = "2026-03-13T10:00:00Z"
        let endpoint = APIEndpoint.listMessages(characterId: "abc", cursor: cursorValue, limit: 20)
        let items = endpoint.queryItems
        let itemDict = Dictionary(uniqueKeysWithValues: (items ?? []).map { ($0.name, $0.value) })
        #expect(itemDict["cursor"] == cursorValue)
    }

    @Test("listMessages queryItems does not include cursor key when cursor is nil")
    func listMessagesNilCursorExcludesCursorKey() {
        let endpoint = APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 20)
        let items = endpoint.queryItems ?? []
        let cursorItem = items.first { $0.name == "cursor" }
        #expect(cursorItem == nil)
    }

    @Test("deleteMemory has nil queryItems")
    func deleteMemoryNoQueryItems() {
        #expect(APIEndpoint.deleteMemory(characterId: "c", memoryId: "m").queryItems == nil)
    }

    @Test("updateCharacter has nil queryItems")
    func updateCharacterNoQueryItems() {
        #expect(APIEndpoint.updateCharacter(id: "abc").queryItems == nil)
    }

    @Test("getProfile has nil queryItems")
    func getProfileNoQueryItems() {
        #expect(APIEndpoint.getProfile.queryItems == nil)
    }

    @Test("register has nil queryItems")
    func registerNoQueryItems() {
        #expect(APIEndpoint.register.queryItems == nil)
    }

    // MARK: - All paths start with /api/v1/

    @Test("all endpoint paths start with /api/v1/")
    func allPathsHaveCorrectPrefix() {
        let endpoints: [APIEndpoint] = [
            .register, .login, .refreshToken,
            .listCharacters, .createCharacter,
            .updateCharacter(id: "id"), .deleteCharacter(id: "id"),
            .sendMessage(characterId: "id"), .streamMessage(characterId: "id"),
            .listMessages(characterId: "id", cursor: nil, limit: 20),
            .listMemories(characterId: "id"),
            .deleteMemory(characterId: "id", memoryId: "mid"),
            .deleteAllMemories(characterId: "id"),
            .uploadURL, .getProfile, .updateProfile, .deleteAccount,
            .completeOnboarding, .updateFCMToken, .updateNotificationPreferences
        ]
        for endpoint in endpoints {
            #expect(endpoint.path.hasPrefix("/api/v1/"), "Path '\(endpoint.path)' does not start with /api/v1/")
        }
    }
}
