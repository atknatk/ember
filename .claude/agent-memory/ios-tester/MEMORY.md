# iOS Tester Agent Memory

## Project
- [iOS network layer test patterns](project_ios_network_layer.md) — MockURLProtocol setup, ExtendedTests file naming, pbxproj update process for new test files
- [iOS cognito auth test patterns](project_ios_cognito_auth.md) — AuthService URL interception, KeychainTokenStore edge cases, AuthViewModel extended coverage, pbxproj group IDs for auth tests
- [iOS onboarding test patterns](project_ios_onboarding.md) — MockAPIClient for onboarding, JSON model testing, pbxproj group IDs for onboarding tests
- [iOS home view test patterns](project_ios_home_view.md) — MockHomeAPIClient with per-endpoint routing, UserDefaults isolation, pbxproj group IDs for Home tests, xcodegen UUID regeneration behaviour
- [iOS chat view test patterns](project_ios_chat_test_patterns.md) — MockChatService, ChatMessageListResponse type, error rollback behavior, pbxproj group IDs for chat tests
- [iOS memory list test patterns](project_ios_memories_test_patterns.md) — MockMemoriesAPIClient with endpoint routing, MemorySegment equality, showDeleteConfirmation computed property, pbxproj already registered by ios-dev
- [iOS profile view test patterns](project_ios_profile_test_patterns.md) — MockProfileAPIClient with endpoint routing, UserDefaults cleanup for notification_preferences and hasCompletedOnboarding, uploadAvatar S3 step untestable without URLSession injection, pbxproj group IDs for profile tests
