import Testing
import Foundation
@testable import Ember

/// Tests for APIEndpoint enum: path, method, requiresAuth, queryItems.
@Suite("APIEndpoint")
struct APIEndpointTests {

    // MARK: - Paths

    @Test("listCharacters path is /api/v1/characters")
    func listCharactersPath() {
        #expect(APIEndpoint.listCharacters.path == "/api/v1/characters")
    }

    @Test("sendMessage path includes character ID")
    func sendMessagePath() {
        #expect(APIEndpoint.sendMessage(characterId: "abc").path == "/api/v1/characters/abc/messages")
    }

    @Test("streamMessage path includes character ID")
    func streamMessagePath() {
        #expect(APIEndpoint.streamMessage(characterId: "abc").path == "/api/v1/characters/abc/messages")
    }

    @Test("deleteAccount path is /api/v1/profile/account")
    func deleteAccountPath() {
        #expect(APIEndpoint.deleteAccount.path == "/api/v1/profile/account")
    }

    @Test("register path is /api/v1/auth/register")
    func registerPath() {
        #expect(APIEndpoint.register.path == "/api/v1/auth/register")
    }

    @Test("login path is /api/v1/auth/login")
    func loginPath() {
        #expect(APIEndpoint.login.path == "/api/v1/auth/login")
    }

    @Test("refreshToken path is /api/v1/auth/refresh")
    func refreshTokenPath() {
        #expect(APIEndpoint.refreshToken.path == "/api/v1/auth/refresh")
    }

    @Test("listMemories path includes character ID")
    func listMemoriesPath() {
        #expect(APIEndpoint.listMemories(characterId: "xyz").path == "/api/v1/characters/xyz/memories")
    }

    @Test("deleteMemory path includes character and memory IDs")
    func deleteMemoryPath() {
        #expect(APIEndpoint.deleteMemory(characterId: "c1", memoryId: "m1").path == "/api/v1/characters/c1/memories/m1")
    }

    @Test("getProfile path is /api/v1/profile")
    func getProfilePath() {
        #expect(APIEndpoint.getProfile.path == "/api/v1/profile")
    }

    @Test("uploadURL path is /api/v1/media/upload-url")
    func uploadURLPath() {
        #expect(APIEndpoint.uploadURL.path == "/api/v1/media/upload-url")
    }

    // MARK: - Methods

    @Test("sendMessage method is POST")
    func sendMessageMethod() {
        #expect(APIEndpoint.sendMessage(characterId: "abc").method == .post)
    }

    @Test("listCharacters method is GET")
    func listCharactersMethod() {
        #expect(APIEndpoint.listCharacters.method == .get)
    }

    @Test("deleteCharacter method is DELETE")
    func deleteCharacterMethod() {
        #expect(APIEndpoint.deleteCharacter(id: "abc").method == .delete)
    }

    @Test("updateCharacter method is PUT")
    func updateCharacterMethod() {
        #expect(APIEndpoint.updateCharacter(id: "abc").method == .put)
    }

    @Test("createCharacter method is POST")
    func createCharacterMethod() {
        #expect(APIEndpoint.createCharacter.method == .post)
    }

    @Test("register method is POST")
    func registerMethod() {
        #expect(APIEndpoint.register.method == .post)
    }

    @Test("getProfile method is GET")
    func getProfileMethod() {
        #expect(APIEndpoint.getProfile.method == .get)
    }

    @Test("updateProfile method is PUT")
    func updateProfileMethod() {
        #expect(APIEndpoint.updateProfile.method == .put)
    }

    // MARK: - requiresAuth

    @Test("register does not require auth")
    func registerNoAuth() {
        #expect(APIEndpoint.register.requiresAuth == false)
    }

    @Test("login does not require auth")
    func loginNoAuth() {
        #expect(APIEndpoint.login.requiresAuth == false)
    }

    @Test("refreshToken does not require auth")
    func refreshTokenNoAuth() {
        #expect(APIEndpoint.refreshToken.requiresAuth == false)
    }

    @Test("listCharacters requires auth")
    func listCharactersRequiresAuth() {
        #expect(APIEndpoint.listCharacters.requiresAuth == true)
    }

    @Test("sendMessage requires auth")
    func sendMessageRequiresAuth() {
        #expect(APIEndpoint.sendMessage(characterId: "abc").requiresAuth == true)
    }

    @Test("deleteAccount requires auth")
    func deleteAccountRequiresAuth() {
        #expect(APIEndpoint.deleteAccount.requiresAuth == true)
    }

    // MARK: - Query Items

    @Test("listMessages with cursor has cursor and limit query items")
    func listMessagesWithCursor() {
        let endpoint = APIEndpoint.listMessages(characterId: "abc", cursor: "xyz", limit: 30)
        let items = endpoint.queryItems
        #expect(items != nil)
        let itemDict = Dictionary(uniqueKeysWithValues: (items ?? []).map { ($0.name, $0.value) })
        #expect(itemDict["cursor"] == "xyz")
        #expect(itemDict["limit"] == "30")
    }

    @Test("listMessages without cursor has limit but no cursor")
    func listMessagesWithoutCursor() {
        let endpoint = APIEndpoint.listMessages(characterId: "abc", cursor: nil, limit: 20)
        let items = endpoint.queryItems
        #expect(items != nil)
        let itemDict = Dictionary(uniqueKeysWithValues: (items ?? []).map { ($0.name, $0.value) })
        #expect(itemDict["cursor"] == nil)
        #expect(itemDict["limit"] == "20")
    }

    @Test("listCharacters has nil queryItems")
    func listCharactersNoQueryItems() {
        #expect(APIEndpoint.listCharacters.queryItems == nil)
    }

    @Test("sendMessage has nil queryItems")
    func sendMessageNoQueryItems() {
        #expect(APIEndpoint.sendMessage(characterId: "abc").queryItems == nil)
    }
}
