import SwiftUI
import PhotosUI
import Kingfisher

struct ProfileView: View {
    @Environment(AuthViewModel.self) private var authViewModel
    @State private var viewModel: ProfileViewModel
    @State private var selectedPhotoItem: PhotosPickerItem?

    init(apiClient: APIClientProtocol = APIClient.shared) {
        _viewModel = State(initialValue: ProfileViewModel(apiClient: apiClient))
    }

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.profile == nil {
                loadingView
            } else if let profile = viewModel.profile {
                profileContent(profile)
            } else if viewModel.errorMessage != nil {
                errorStateView
            }
        }
        .background(Color.emberBackground.ignoresSafeArea())
        .navigationTitle("Profile")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadProfile()
        }
        .alert("Error", isPresented: Binding(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) {}
            Button("Retry") {
                Task { await viewModel.loadProfile() }
            }
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
        .alert("Delete Account", isPresented: $viewModel.showDeleteConfirmation) {
            TextField("Type DELETE MY ACCOUNT", text: $viewModel.deleteConfirmationText)
            Button("Delete", role: .destructive) {
                Task { await viewModel.deleteAccount() }
            }
            .disabled(viewModel.deleteConfirmationText != "DELETE MY ACCOUNT")
            Button("Cancel", role: .cancel) {
                viewModel.deleteConfirmationText = ""
            }
        } message: {
            Text("This action is permanent and cannot be undone. All your data, conversations, and memories will be deleted. Type DELETE MY ACCOUNT to confirm.")
        }
        .sheet(isPresented: $viewModel.showTimezonePicker) {
            TimezonePickerSheet(
                selectedTimezone: viewModel.profile?.timezone ?? TimeZone.current.identifier,
                onSelect: { timezone in
                    viewModel.showTimezonePicker = false
                    Task { await viewModel.updateTimezone(timezone) }
                }
            )
        }
        .photosPicker(
            isPresented: $viewModel.showPhotoPicker,
            selection: $selectedPhotoItem,
            matching: .images
        )
        .onChange(of: selectedPhotoItem) { _, newItem in
            guard let newItem else { return }
            Task {
                if let data = try? await newItem.loadTransferable(type: Data.self) {
                    await viewModel.uploadAvatar(imageData: compressImage(data))
                }
                selectedPhotoItem = nil
            }
        }
        .onChange(of: viewModel.shouldSignOut) { _, shouldSignOut in
            if shouldSignOut {
                Task { await authViewModel.signOut() }
            }
        }
        .onChange(of: viewModel.accountDeleted) { _, deleted in
            if deleted {
                Task { await authViewModel.signOut() }
            }
        }
    }

    // MARK: - Subviews

    @ViewBuilder
    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .tint(Color.emberPrimary)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var errorStateView: some View {
        VStack(spacing: .emberSpacing16) {
            Spacer()
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48, weight: .medium))
                .foregroundStyle(Color.emberError)
                .accessibilityHidden(true)

            Text("Failed to load profile")
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)

            Button {
                Task { await viewModel.loadProfile() }
            } label: {
                Text("Retry")
                    .font(.emberHeadline)
                    .foregroundStyle(.white)
                    .padding(.horizontal, .emberSpacing24)
                    .padding(.vertical, .emberSpacing12)
                    .background(Color.emberPrimary)
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius28))
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private func profileContent(_ profile: ProfileData) -> some View {
        ScrollView {
            VStack(spacing: .emberSpacing24) {
                profileHeaderSection(profile)
                preferencesSection(profile)
                accountSection
            }
            .padding(.horizontal, .emberSpacing20)
            .padding(.top, .emberSpacing24)
            .padding(.bottom, .emberSpacing32)
        }
    }

    // MARK: - Profile Header

    @ViewBuilder
    private func profileHeaderSection(_ profile: ProfileData) -> some View {
        VStack(spacing: .emberSpacing12) {
            // Avatar
            Button {
                viewModel.showPhotoPicker = true
            } label: {
                ZStack(alignment: .bottomTrailing) {
                    avatarImage(profile)
                        .frame(width: 80, height: 80)
                        .clipShape(Circle())

                    // Camera overlay
                    Image(systemName: "camera.fill")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Color.emberTextSecondary)
                        .padding(6)
                        .background(Color.emberSurface2)
                        .clipShape(Circle())
                }
            }
            .accessibilityLabel("Profile photo. Tap to change")

            // Name
            if viewModel.isEditingName {
                nameEditField
            } else {
                Button {
                    viewModel.startEditingName()
                } label: {
                    Text(profile.name)
                        .font(.emberTitle)
                        .foregroundStyle(Color.emberTextPrimary)
                }
                .accessibilityLabel("Display name: \(profile.name). Tap to edit")
            }

            // Email
            Text(profile.email)
                .font(.emberSecondary)
                .foregroundStyle(Color.emberTextSecondary)

            // Subscription badge
            subscriptionBadge(tier: profile.subscriptionTier)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func avatarImage(_ profile: ProfileData) -> some View {
        if let avatarUrl = profile.avatarUrl, let url = URL(string: avatarUrl) {
            KFImage(url)
                .placeholder {
                    avatarPlaceholder(name: profile.name)
                }
                .fade(duration: 0.25)
                .resizable()
                .aspectRatio(contentMode: .fill)
        } else {
            avatarPlaceholder(name: profile.name)
        }
    }

    @ViewBuilder
    private func avatarPlaceholder(name: String) -> some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [Color.emberGradientStart, Color.emberGradientEnd],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .overlay(
                Text(String(name.prefix(1)).uppercased())
                    .font(.emberLargeTitle)
                    .foregroundStyle(.white)
            )
    }

    @ViewBuilder
    private var nameEditField: some View {
        HStack(spacing: .emberSpacing8) {
            TextField("Name", text: $viewModel.editedName)
                .font(.emberTitle)
                .foregroundStyle(Color.emberTextPrimary)
                .padding(.horizontal, .emberSpacing12)
                .padding(.vertical, .emberSpacing8)
                .background(Color.emberSurface2)
                .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
                .accessibilityLabel("Edit display name")

            Button {
                Task { await viewModel.updateName() }
            } label: {
                Text("Save")
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberPrimary)
            }
            .disabled(viewModel.isSaving)
            .accessibilityLabel("Save name")

            Button {
                viewModel.cancelEditingName()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(Color.emberTextSecondary)
            }
            .accessibilityLabel("Cancel editing name")
        }
    }

    @ViewBuilder
    private func subscriptionBadge(tier: String) -> some View {
        let isPremium = tier == "premium"
        Text(isPremium ? "Premium" : "Free")
            .font(.emberCaption)
            .foregroundStyle(isPremium ? .white : Color.emberTextSecondary)
            .padding(.horizontal, .emberSpacing8)
            .padding(.vertical, .emberSpacing4)
            .background(isPremium ? Color.emberPrimary : Color.emberSurface3)
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius4))
    }

    // MARK: - Preferences Section

    @ViewBuilder
    private func preferencesSection(_ profile: ProfileData) -> some View {
        VStack(alignment: .leading, spacing: .emberSpacing16) {
            Text("Preferences")
                .font(.emberHeadline)
                .foregroundStyle(Color.emberTextPrimary)

            // Timezone row
            Button {
                viewModel.showTimezonePicker = true
            } label: {
                settingsRow(
                    title: "Timezone",
                    value: profile.timezone,
                    showChevron: true
                )
            }
            .accessibilityLabel("Timezone: \(profile.timezone)")
            .accessibilityHint("Opens timezone picker")

            // Language row
            VStack(alignment: .leading, spacing: .emberSpacing8) {
                Text("Language")
                    .font(.emberBody)
                    .foregroundStyle(Color.emberTextPrimary)

                Picker("Language", selection: Binding(
                    get: { profile.preferredLanguage },
                    set: { newValue in
                        HapticManager.impact(.light)
                        Task { await viewModel.updateLanguage(newValue) }
                    }
                )) {
                    Text("English").tag("en")
                    Text("Turkish").tag("tr")
                }
                .pickerStyle(.segmented)
            }
            .padding(.emberSpacing16)
            .background(Color.emberSurface2)
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))

            // Notifications
            notificationsSection
        }
    }

    @ViewBuilder
    private var notificationsSection: some View {
        VStack(alignment: .leading, spacing: .emberSpacing12) {
            Text("Notifications")
                .font(.emberHeadline)
                .foregroundStyle(Color.emberTextPrimary)

            VStack(spacing: 0) {
                notificationToggle(
                    title: "Morning Check-in",
                    key: "morning_checkin"
                )
                Divider().background(Color.emberSurface3)
                notificationToggle(
                    title: "Evening Reflection",
                    key: "evening_reflection"
                )
                Divider().background(Color.emberSurface3)
                notificationToggle(
                    title: "Sleep Reminder",
                    key: "sleep_reminder"
                )

                ForEach(viewModel.characters) { character in
                    Divider().background(Color.emberSurface3)
                    notificationToggle(
                        title: character.name,
                        key: "character_\(character.id)"
                    )
                }
            }
            .background(Color.emberSurface2)
            .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
        }
    }

    @ViewBuilder
    private func notificationToggle(title: String, key: String) -> some View {
        Toggle(isOn: Binding(
            get: { viewModel.notificationPreferences[key] ?? true },
            set: { viewModel.updateNotificationPreference(key: key, value: $0) }
        )) {
            Text(title)
                .font(.emberBody)
                .foregroundStyle(Color.emberTextPrimary)
        }
        .tint(Color.emberPrimary)
        .padding(.horizontal, .emberSpacing16)
        .padding(.vertical, .emberSpacing12)
    }

    @ViewBuilder
    private func settingsRow(title: String, value: String, showChevron: Bool) -> some View {
        HStack {
            Text(title)
                .font(.emberBody)
                .foregroundStyle(Color.emberTextPrimary)
            Spacer()
            Text(value)
                .font(.emberSecondary)
                .foregroundStyle(Color.emberTextSecondary)
                .lineLimit(1)
            if showChevron {
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color.emberTextDisabled)
            }
        }
        .padding(.emberSpacing16)
        .background(Color.emberSurface2)
        .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
    }

    // MARK: - Account Section

    @ViewBuilder
    private var accountSection: some View {
        VStack(alignment: .leading, spacing: .emberSpacing16) {
            Text("Account")
                .font(.emberHeadline)
                .foregroundStyle(Color.emberTextPrimary)

            // Sign Out
            Button {
                viewModel.signOut()
            } label: {
                Text("Sign Out")
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberTextPrimary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, .emberSpacing12)
                    .background(Color.emberSurface2)
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
            }
            .accessibilityLabel("Sign out of your account")

            // Delete Account
            Button {
                HapticManager.notification(.warning)
                viewModel.showDeleteConfirmation = true
            } label: {
                Text("Delete Account")
                    .font(.emberHeadline)
                    .foregroundStyle(Color.emberError)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, .emberSpacing12)
                    .background(Color.emberSurface2)
                    .clipShape(RoundedRectangle(cornerRadius: .emberRadius12))
            }
            .accessibilityLabel("Delete your account permanently")
        }
    }

    // MARK: - Helpers

    private func compressImage(_ data: Data) -> Data {
        guard let uiImage = UIImage(data: data),
              let compressed = uiImage.jpegData(compressionQuality: 0.8) else {
            return data
        }
        return compressed
    }
}
