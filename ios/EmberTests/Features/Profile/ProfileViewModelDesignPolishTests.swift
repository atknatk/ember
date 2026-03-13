import Testing
import Foundation
@testable import Ember

/// Tests for `ProfileViewModel` behaviour added in P03-10 (iOS Design Polish):
/// - `didSaveSuccessfully` flag and `flashSaveSuccess()` private method
/// - `didSaveSuccessfully` starts as `false`
/// - `didSaveSuccessfully` becomes `true` after each successful update
///   (updateName, updateTimezone, updateLanguage)
/// - `didSaveSuccessfully` stays `false` after a failed update
///
/// Note: `flashSaveSuccess()` resets `didSaveSuccessfully` to `false` after
/// a 0.5-second Task.sleep. In synchronous unit tests the reset cannot be
/// observed reliably, so we only assert that the flag is `true` immediately
/// after the async update returns (before the delayed reset fires).
@Suite("ProfileViewModel Design Polish (didSaveSuccessfully)")
struct ProfileViewModelDesignPolishTests {

    // MARK: - Endpoint-aware Mock

    private final class MockProfileAPIClient: APIClientProtocol, @unchecked Sendable {
        var profileResponse: ProfileData?
        var characterListResponse = CharacterListResponse(characters: [])
        var updateProfileResponse: ProfileData?
        var requestError: Error?
        var deleteError: Error?

        func request<T: Decodable>(
            endpoint: APIEndpoint,
            body: (any Encodable)?,
            responseType: T.Type
        ) async throws -> T {
            if let error = requestError { throw error }

            switch endpoint {
            case .getProfile:
                guard let result = profileResponse as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1,
                                userInfo: [NSLocalizedDescriptionKey: "No profile mock set"])
                    )
                }
                return result
            case .listCharacters:
                guard let result = characterListResponse as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1,
                                userInfo: [NSLocalizedDescriptionKey: "Type mismatch"])
                    )
                }
                return result
            case .updateProfile:
                guard let result = (updateProfileResponse ?? profileResponse) as? T else {
                    throw APIError.decodingError(
                        NSError(domain: "Mock", code: -1,
                                userInfo: [NSLocalizedDescriptionKey: "No update mock set"])
                    )
                }
                return result
            default:
                throw APIError.decodingError(
                    NSError(domain: "Mock", code: -1,
                            userInfo: [NSLocalizedDescriptionKey: "Unexpected endpoint"])
                )
            }
        }

        func requestVoid(endpoint: APIEndpoint, body: (any Encodable)?) async throws {
            if let error = deleteError { throw error }
        }

        func streamSSE(endpoint: APIEndpoint, body: (any Encodable)?) -> AsyncThrowingStream<SSEEvent, Error> {
            AsyncThrowingStream { $0.finish() }
        }
    }

    // MARK: - Test Data Factories

    private static func makeProfile(
        name: String = "Alex",
        timezone: String = "America/New_York",
        preferredLanguage: String = "en"
    ) -> ProfileData {
        ProfileData(
            id: "user-1",
            email: "test@example.com",
            name: name,
            timezone: timezone,
            avatarUrl: nil,
            preferredLanguage: preferredLanguage,
            onboardingCompleted: true,
            subscriptionTier: "free",
            subscriptionExpiresAt: nil,
            createdAt: Date()
        )
    }

    private func makeViewModel() -> (ProfileViewModel, MockProfileAPIClient) {
        let mock = MockProfileAPIClient()
        let vm = ProfileViewModel(apiClient: mock)
        return (vm, mock)
    }

    // MARK: - Initial State

    @Test("didSaveSuccessfully is false on initial state")
    func didSaveSuccessfullyIsFalseInitially() {
        let (vm, _) = makeViewModel()
        #expect(vm.didSaveSuccessfully == false)
    }

    // MARK: - updateName: didSaveSuccessfully transitions

    @Test("updateName sets didSaveSuccessfully to true on success")
    func updateNameSetsDidSaveSuccessfullyOnSuccess() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = Self.makeProfile(name: "Jordan")
        await vm.loadProfile()

        vm.editedName = "Jordan"
        await vm.updateName()

        // Immediately after return, the flag must be true (the 0.5s reset fires asynchronously)
        #expect(vm.didSaveSuccessfully == true)
    }

    @Test("updateName leaves didSaveSuccessfully false on API failure")
    func updateNameLeavesDidSaveSuccessfullyFalseOnFailure() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.requestError = APIError.serverError(statusCode: 500, detail: "error")
        vm.editedName = "Jordan"
        await vm.updateName()

        #expect(vm.didSaveSuccessfully == false)
    }

    @Test("updateName with empty trimmed name leaves didSaveSuccessfully false (guard hit)")
    func updateNameEmptyLeavesDidSaveSuccessfullyFalse() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        vm.editedName = "   "
        await vm.updateName()

        #expect(vm.didSaveSuccessfully == false)
    }

    // MARK: - updateTimezone: didSaveSuccessfully transitions

    @Test("updateTimezone sets didSaveSuccessfully to true on success")
    func updateTimezoneSetsDidSaveSuccessfullyOnSuccess() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = Self.makeProfile(timezone: "Europe/Istanbul")
        await vm.loadProfile()

        await vm.updateTimezone("Europe/Istanbul")

        #expect(vm.didSaveSuccessfully == true)
    }

    @Test("updateTimezone leaves didSaveSuccessfully false on API failure")
    func updateTimezoneLeavesDidSaveSuccessfullyFalseOnFailure() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.requestError = APIError.networkError(NSError(domain: "test", code: -1))
        await vm.updateTimezone("Europe/Istanbul")

        #expect(vm.didSaveSuccessfully == false)
    }

    // MARK: - updateLanguage: didSaveSuccessfully transitions

    @Test("updateLanguage sets didSaveSuccessfully to true on success")
    func updateLanguageSetsDidSaveSuccessfullyOnSuccess() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = Self.makeProfile(preferredLanguage: "tr")
        await vm.loadProfile()

        await vm.updateLanguage("tr")

        #expect(vm.didSaveSuccessfully == true)
    }

    @Test("updateLanguage leaves didSaveSuccessfully false on API failure")
    func updateLanguageLeavesDidSaveSuccessfullyFalseOnFailure() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.requestError = APIError.serverError(statusCode: 503, detail: "Service unavailable")
        await vm.updateLanguage("tr")

        #expect(vm.didSaveSuccessfully == false)
    }

    // MARK: - Multiple sequential saves

    @Test("didSaveSuccessfully is true after each of updateName, updateTimezone, updateLanguage in sequence")
    func didSaveSuccessfullyForEachUpdateInSequence() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = Self.makeProfile()
        await vm.loadProfile()

        vm.editedName = "Jordan"
        await vm.updateName()
        #expect(vm.didSaveSuccessfully == true, "Expected true after updateName")

        // Set flag back to false to test next save independently
        vm.didSaveSuccessfully = false

        await vm.updateTimezone("Asia/Tokyo")
        #expect(vm.didSaveSuccessfully == true, "Expected true after updateTimezone")

        vm.didSaveSuccessfully = false

        await vm.updateLanguage("tr")
        #expect(vm.didSaveSuccessfully == true, "Expected true after updateLanguage")
    }

    @Test("didSaveSuccessfully can be manually reset to false between saves")
    func didSaveSuccessfullyCanBeManuallyReset() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = Self.makeProfile(name: "Sam")
        await vm.loadProfile()

        vm.editedName = "Sam"
        await vm.updateName()
        #expect(vm.didSaveSuccessfully == true)

        vm.didSaveSuccessfully = false
        #expect(vm.didSaveSuccessfully == false)
    }

    // MARK: - Interaction with error state

    @Test("didSaveSuccessfully is false and errorMessage is non-nil after failed updateName")
    func failedUpdateNameSetsErrorNotSaveSuccess() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        await vm.loadProfile()

        mock.requestError = APIError.serverError(statusCode: 422, detail: "Validation error")
        vm.editedName = "BadName"
        await vm.updateName()

        #expect(vm.didSaveSuccessfully == false)
        #expect(vm.errorMessage != nil)
    }

    @Test("didSaveSuccessfully is true and errorMessage is nil after successful updateName")
    func successfulUpdateNameSetsSaveSuccessNotError() async {
        let (vm, mock) = makeViewModel()
        mock.profileResponse = Self.makeProfile()
        mock.updateProfileResponse = Self.makeProfile(name: "Alex")
        await vm.loadProfile()

        vm.editedName = "Alex"
        await vm.updateName()

        #expect(vm.didSaveSuccessfully == true)
        #expect(vm.errorMessage == nil)
    }
}
