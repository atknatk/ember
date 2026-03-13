import Foundation
import Observation

@Observable
final class ProfileViewModel {
    // MARK: - Public State

    var profile: ProfileData?
    var characters: [Character] = []
    var isLoading: Bool = false
    var isSaving: Bool = false
    var errorMessage: String?
    var showPhotoPicker: Bool = false
    var showTimezonePicker: Bool = false
    var showDeleteConfirmation: Bool = false
    var deleteConfirmationText: String = ""
    var isEditingName: Bool = false
    var editedName: String = ""
    var notificationPreferences: [String: Bool] = [:]
    var shouldSignOut: Bool = false
    var accountDeleted: Bool = false
    var didSaveSuccessfully: Bool = false

    // MARK: - Dependencies

    private let apiClient: APIClientProtocol

    // MARK: - Init

    init(apiClient: APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    // MARK: - Actions

    func loadProfile() async {
        isLoading = true
        errorMessage = nil

        do {
            async let profileResponse = apiClient.request(
                endpoint: .getProfile,
                responseType: ProfileData.self
            )
            async let charactersResponse = apiClient.request(
                endpoint: .listCharacters,
                responseType: CharacterListResponse.self
            )

            let (fetchedProfile, fetchedCharacters) = try await (profileResponse, charactersResponse)
            profile = fetchedProfile
            characters = fetchedCharacters.characters

            loadNotificationPreferences()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    func updateName() async {
        let trimmed = editedName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else {
            errorMessage = "Name cannot be empty"
            return
        }

        isSaving = true

        do {
            let body = ProfileUpdateBody(name: trimmed)
            let updated: ProfileData = try await apiClient.request(
                endpoint: .updateProfile,
                body: body,
                responseType: ProfileData.self
            )
            profile = updated
            isEditingName = false
            HapticManager.notification(.success)
            flashSaveSuccess()
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.notification(.error)
        }

        isSaving = false
    }

    func updateTimezone(_ timezone: String) async {
        isSaving = true

        do {
            let body = ProfileUpdateBody(timezone: timezone)
            let updated: ProfileData = try await apiClient.request(
                endpoint: .updateProfile,
                body: body,
                responseType: ProfileData.self
            )
            profile = updated
            HapticManager.notification(.success)
            flashSaveSuccess()
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.notification(.error)
        }

        isSaving = false
    }

    func updateLanguage(_ language: String) async {
        isSaving = true

        do {
            let body = ProfileUpdateBody(preferredLanguage: language)
            let updated: ProfileData = try await apiClient.request(
                endpoint: .updateProfile,
                body: body,
                responseType: ProfileData.self
            )
            profile = updated
            HapticManager.notification(.success)
            flashSaveSuccess()
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.notification(.error)
        }

        isSaving = false
    }

    func uploadAvatar(imageData: Data) async {
        isSaving = true

        do {
            // Step 1: Get presigned upload URL
            let uploadBody = UploadURLRequest(
                filename: "avatar.jpg",
                contentType: "image/jpeg",
                type: "photo"
            )
            let uploadResponse: UploadURLResponse = try await apiClient.request(
                endpoint: .uploadURL,
                body: uploadBody,
                responseType: UploadURLResponse.self
            )

            // Step 2: Upload image data to S3 via presigned URL
            guard let uploadURL = URL(string: uploadResponse.uploadUrl) else {
                errorMessage = "Invalid upload URL"
                isSaving = false
                return
            }
            var uploadRequest = URLRequest(url: uploadURL)
            uploadRequest.httpMethod = "PUT"
            uploadRequest.setValue("image/jpeg", forHTTPHeaderField: "Content-Type")

            let (_, response) = try await URLSession.shared.upload(for: uploadRequest, from: imageData)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                errorMessage = "Failed to upload image"
                isSaving = false
                HapticManager.notification(.error)
                return
            }

            // Step 3: Update profile with new avatar URL
            let profileBody = ProfileUpdateBody(avatarUrl: uploadResponse.fileUrl)
            let updated: ProfileData = try await apiClient.request(
                endpoint: .updateProfile,
                body: profileBody,
                responseType: ProfileData.self
            )
            profile = updated
            HapticManager.notification(.success)
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.notification(.error)
        }

        isSaving = false
    }

    func deleteAccount() async {
        guard deleteConfirmationText == "DELETE MY ACCOUNT" else {
            errorMessage = "Please type DELETE MY ACCOUNT to confirm"
            return
        }

        isSaving = true

        do {
            let body = AccountDeleteBody(confirmation: "DELETE MY ACCOUNT")
            try await apiClient.requestVoid(
                endpoint: .deleteAccount,
                body: body
            )

            UserDefaults.standard.set(false, forKey: "hasCompletedOnboarding")
            accountDeleted = true
            HapticManager.notification(.error)
        } catch {
            errorMessage = error.localizedDescription
            HapticManager.notification(.error)
        }

        isSaving = false
        deleteConfirmationText = ""
    }

    func signOut() {
        shouldSignOut = true
        HapticManager.impact(.medium)
    }

    func updateNotificationPreference(key: String, value: Bool) {
        notificationPreferences[key] = value
        persistNotificationPreferences()
        HapticManager.selection()
    }

    func startEditingName() {
        editedName = profile?.name ?? ""
        isEditingName = true
    }

    func cancelEditingName() {
        isEditingName = false
        editedName = ""
    }

    // MARK: - Private

    private func loadNotificationPreferences() {
        if let stored = UserDefaults.standard.dictionary(forKey: "notification_preferences") as? [String: Bool] {
            notificationPreferences = stored
        } else {
            // Default all to true
            var defaults: [String: Bool] = [
                "morning_checkin": true,
                "evening_reflection": true,
                "sleep_reminder": true
            ]
            for character in characters {
                defaults["character_\(character.id)"] = true
            }
            notificationPreferences = defaults
            persistNotificationPreferences()
        }
    }

    private func persistNotificationPreferences() {
        UserDefaults.standard.set(notificationPreferences, forKey: "notification_preferences")
    }

    /// Briefly sets `didSaveSuccessfully` to true, then resets after 0.5s.
    private func flashSaveSuccess() {
        didSaveSuccessfully = true
        Task {
            try? await Task.sleep(nanoseconds: 500_000_000)
            didSaveSuccessfully = false
        }
    }
}
