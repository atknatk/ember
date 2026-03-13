import Testing
import Foundation
@testable import Ember

@Suite("ProfileViewModel")
struct ProfileViewModelTests {

    // MARK: - Mock API Client

    /// Endpoint-aware mock that returns different results for profile, characters, and update operations.
    private final class MockProfileAPIClient: APIClientProtocol, @unchecked Sendable {
        var profileResponse: ProfileData?
        var characterListResponse = CharacterListResponse(characters: [])
        var updateProfileResponse: ProfileData?
        var uploadURLResponse: UploadURLResponse?
        var requestError: Error?
        var deleteError: Error?
        var requestCallCount: Int = 0
        var requestVoidCallCount: Int = 0
        var lastEndpoint: APIEndpoint?
        var calledEndpoints: [String] = []

        func request<T: Decodable>(
            endpoint: APIEndpoint,
            body: (any Encodable)?,
            responseType: T.Type
        ) async throws -> T {
            requestCallCount += 1
            lastEndpoint = endpoint
            calledEndpoints.append(endpointName(endpoint))

            if let error = requestError {
                throw error
            }

            switch endpoint {
            case .getProfile:
                guard let result = profileResponse as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "No profile mock set"])
                    )
                }
                return result
            case .listCharacters:
                guard let result = characterListResponse as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "Type mismatch"])
                    )
                }
                return result
            case .updateProfile:
                guard let result = (updateProfileResponse ?? profileResponse) as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "No update mock set"])
                    )
                }
                return result
            case .uploadURL:
                guard let result = uploadURLResponse as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1, userInfo: [NSLocalizedDescriptionKey: "No upload URL mock set"])
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
            calledEndpoints.append(endpointName(endpoint))
            if let error = deleteError {
                throw error
            }
        }

        func streamSSE(endpoint: APIEndpoint, body: (any Encodable)?) -> AsyncThrowingStream<SSEEvent, Error> {
            AsyncThrowingStream { $0.finish() }
        }

        private func endpointName(_ endpoint: APIEndpoint) -> String {
            switch endpoint {
            case .getProfile: return "getProfile"
            case .listCharacters: return "listCharacters"
            case .updateProfile: return "updateProfile"
            case .deleteAccount: return "deleteAccount"
            case .uploadURL: return "uploadURL"
            default: return "other"
            }
        }
    }

    // MARK: - Test Data

    private static func makeProfile(
        id: String = "user-1",
        email: String = "test@example.com",
        name: String = "Alex",
        timezone: String = "America/New_York",
        avatarUrl: String? = nil,
        preferredLanguage: String = "en",
        subscriptionTier: String = "free"
    ) -> ProfileData {
        ProfileData(
            id: id,
            email: email,
            name: name,
            timezone: timezone,
            avatarUrl: avatarUrl,
            preferredLanguage: preferredLanguage,
            onboardingCompleted: true,
            subscriptionTier: subscriptionTier,
            subscriptionExpiresAt: nil,
            createdAt: Date()
        )
    }

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

    // MARK: - Helpers

    private func makeViewModel() -> (ProfileViewModel, MockProfileAPIClient) {
        let mock = MockProfileAPIClient()
        let vm = ProfileViewModel(apiClient: mock)
        return (vm, mock)
    }

    // MARK: - loadProfile Tests

    @Test("loadProfile sets profile on success")
    func loadProfileSuccess() async {
        let (vm, mock) = makeViewModel()
        let profile = Self.makeProfile()
        let c1 = Self.makeCharacter(id: "c1", name: "Luna")
        let c2 = Self.makeCharacter(id: "c2", name: "Coach", isDefault: false)
        mock.profileResponse = profile
        mock.characterListResponse = CharacterListResponse(characters: [c1, c2])

        await vm.loadProfile()

        #expect(vm.profile != nil)
        #expect(vm.profile?.name == "Alex")
        #expect(vm.characters.count == 2)
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    @Test("loadProfile sets errorMessage on network failure")
    func loadProfileNetworkError() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.networkError(
            NSError(domain: "Test", code: -1, userInfo: [NSLocalizedDescriptionKey: "No connection"])
        )

        await vm.loadProfile()

        #expect(vm.profile == nil)
        #expect(vm.errorMessage != nil)
        #expect(vm.isLoading == false)
    }

    @Test("loadProfile sets errorMessage on 401")
    func loadProfileUnauthorized() async {
        let (vm, mock) = makeViewModel()
        mock.requestError = APIError.unauthorized

        await vm.loadProfile()

        #expect(vm.errorMessage != nil)
        #expect(vm.isLoading == false)
    }

    @Test("loadProfile fetches profile and characters in parallel")
    func loadProfileFetchesBothEndpoints() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        mock.characterListResponse = CharacterListResponse(characters: [])

        await vm.loadProfile()

        #expect(mock.calledEndpoints.contains("getProfile"))
        #expect(mock.calledEndpoints.contains("listCharacters"))
    }

    // MARK: - updateName Tests

    @Test("updateName trims whitespace and sends PUT")
    func updateNameTrimsWhitespace() async {
        let (vm, mock) = makeViewModel()
        let updatedProfile = Self.makeProfile(name: "Alex")
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = updatedProfile

        await vm.loadProfile()

        vm.editedName = "  Alex  "
        await vm.updateName()

        #expect(vm.profile?.name == "Alex")
        #expect(vm.isEditingName == false)
        #expect(vm.isSaving == false)
    }

    @Test("updateName rejects empty string")
    func updateNameRejectsEmpty() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        let callCountBefore = mock.requestCallCount
        vm.editedName = "   "
        await vm.updateName()

        #expect(vm.errorMessage != nil)
        #expect(vm.errorMessage == "Name cannot be empty")
        // Should NOT have made any additional API call
        #expect(mock.requestCallCount == callCountBefore)
    }

    @Test("updateName sets error on API failure")
    func updateNameError() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.requestError = APIError.serverError(statusCode: 500, detail: "Internal error")
        vm.editedName = "NewName"
        await vm.updateName()

        #expect(vm.errorMessage != nil)
        #expect(vm.isSaving == false)
    }

    // MARK: - updateTimezone Tests

    @Test("updateTimezone sends PUT")
    func updateTimezoneSendsPUT() async {
        let (vm, mock) = makeViewModel()
        let updatedProfile = Self.makeProfile(timezone: "Europe/Istanbul")
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = updatedProfile

        await vm.loadProfile()
        await vm.updateTimezone("Europe/Istanbul")

        #expect(vm.profile?.timezone == "Europe/Istanbul")
        #expect(vm.isSaving == false)
    }

    @Test("updateTimezone sets error on failure")
    func updateTimezoneError() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.requestError = APIError.networkError(NSError(domain: "t", code: -1))
        await vm.updateTimezone("Europe/London")

        #expect(vm.errorMessage != nil)
        #expect(vm.isSaving == false)
    }

    // MARK: - updateLanguage Tests

    @Test("updateLanguage sends PUT")
    func updateLanguageSendsPUT() async {
        let (vm, mock) = makeViewModel()
        let updatedProfile = Self.makeProfile(preferredLanguage: "tr")
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = updatedProfile

        await vm.loadProfile()
        await vm.updateLanguage("tr")

        #expect(vm.profile?.preferredLanguage == "tr")
        #expect(vm.isSaving == false)
    }

    @Test("updateLanguage sets error on failure")
    func updateLanguageError() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.requestError = APIError.serverError(statusCode: 503, detail: "Service unavailable")
        await vm.updateLanguage("tr")

        #expect(vm.errorMessage != nil)
        #expect(vm.isSaving == false)
    }

    // MARK: - deleteAccount Tests

    @Test("deleteAccount with correct confirmation succeeds")
    func deleteAccountSuccess() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        vm.deleteConfirmationText = "DELETE MY ACCOUNT"
        await vm.deleteAccount()

        #expect(vm.accountDeleted == true)
        #expect(mock.requestVoidCallCount == 1)
        #expect(vm.isSaving == false)
    }

    @Test("deleteAccount with wrong confirmation does not call API")
    func deleteAccountWrongConfirmation() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        vm.deleteConfirmationText = "delete"
        await vm.deleteAccount()

        #expect(mock.requestVoidCallCount == 0)
        #expect(vm.errorMessage != nil)
        #expect(vm.accountDeleted == false)
    }

    @Test("deleteAccount on server error sets errorMessage")
    func deleteAccountServerError() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.deleteError = APIError.serverError(statusCode: 503, detail: "Service down")
        vm.deleteConfirmationText = "DELETE MY ACCOUNT"
        await vm.deleteAccount()

        #expect(vm.errorMessage != nil)
        #expect(vm.accountDeleted == false)
        #expect(vm.isSaving == false)
    }

    @Test("deleteAccount clears confirmation text after completion")
    func deleteAccountClearsConfirmationText() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        vm.deleteConfirmationText = "DELETE MY ACCOUNT"
        await vm.deleteAccount()

        #expect(vm.deleteConfirmationText == "")
    }

    // MARK: - signOut Tests

    @Test("signOut sets shouldSignOut flag")
    func signOutSetFlag() {
        let (vm, _) = makeViewModel()

        vm.signOut()

        #expect(vm.shouldSignOut == true)
    }

    // MARK: - updateNotificationPreference Tests

    @Test("updateNotificationPreference updates local state")
    func updateNotificationPreference() {
        let (vm, _) = makeViewModel()

        vm.updateNotificationPreference(key: "morning_checkin", value: false)

        #expect(vm.notificationPreferences["morning_checkin"] == false)
    }

    @Test("updateNotificationPreference persists to UserDefaults")
    func updateNotificationPreferencePersists() {
        let (vm, _) = makeViewModel()

        vm.updateNotificationPreference(key: "morning_checkin", value: false)

        let stored = UserDefaults.standard.dictionary(forKey: "notification_preferences") as? [String: Bool]
        #expect(stored?["morning_checkin"] == false)

        // Cleanup
        UserDefaults.standard.removeObject(forKey: "notification_preferences")
    }

    // MARK: - Name Editing Tests

    @Test("startEditingName sets editedName to current profile name")
    func startEditingName() {
        let (vm, _) = makeViewModel()
        vm.profile = Self.makeProfile(name: "Alex")

        vm.startEditingName()

        #expect(vm.isEditingName == true)
        #expect(vm.editedName == "Alex")
    }

    @Test("cancelEditingName resets editing state")
    func cancelEditingName() {
        let (vm, _) = makeViewModel()
        vm.isEditingName = true
        vm.editedName = "Something"

        vm.cancelEditingName()

        #expect(vm.isEditingName == false)
        #expect(vm.editedName == "")
    }
}
