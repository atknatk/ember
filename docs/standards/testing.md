# Ember Testing Standards

All platforms: Backend / iOS / Android

This document is the authoritative reference for testing across all Ember platforms.
Zero-memory sessions must follow every rule here without exception.

---

## Table of Contents

1. Coverage Requirements
2. What to Test vs What Not to Test
3. Backend Testing (pytest + httpx)
4. iOS Testing (Swift Testing + XCTest)
5. Android Testing (JUnit + MockK + Turbine)
6. Integration vs Unit Test Distinction
7. Test Naming Conventions
8. Test File Locations
9. CI Test Commands

---

## 1. Coverage Requirements

| Metric        | New Code | Existing Code |
|---------------|----------|---------------|
| Line coverage | 80%      | No regression |
| Branch coverage | 70%    | No regression |

These are minimum thresholds for pull request merges. CI blocks merges below these thresholds.

Coverage is measured per platform:
- **Backend**: `pytest --cov=app --cov-fail-under=80`
- **iOS**: Xcode scheme coverage report (checked in CI)
- **Android**: Jacoco (`jacocoTestReport`, `jacocoCoverageVerification`)

### What counts toward coverage

- All service classes
- All ViewModel logic
- All repository classes
- Utility functions
- Error paths and edge cases

### What does NOT count toward coverage

- Auto-generated code (Alembic migrations, generated Protobuf/Codable stubs)
- View/Composable/SwiftUI rendering code (presentation only, no logic)
- `main.py` / `App.swift` / `Application.kt` app entry points
- Configuration constants
- DTOs and plain data classes with no logic

---

## 2. What to Test vs What Not to Test

### Test This

- **Business logic**: service layer methods, ViewModel state transitions
- **Error paths**: what happens on 4xx, 5xx, network timeout, empty response
- **Pagination**: cursor encoding, decoding, boundary conditions (last page, empty page)
- **Authentication**: valid token passes, invalid token rejected, expired token rejected
- **Data transformation**: mapping DB model → response schema, API response → UI model
- **Edge cases**: empty strings, max-length strings, null fields, duplicate IDs
- **Integration contracts**: API endpoint returns expected schema shape

### Do Not Test This

- Framework internals (FastAPI routing dispatch, Compose recomposition)
- Third-party library behavior (Mem0, Amplify, Kingfisher internals)
- Pure getter/setter data classes with no logic
- View layout and styling (test visual appearance with manual QA + screenshot tests)
- `__init__` and `__str__` methods with no logic
- Trivial pass-through functions (1-line wrappers that do nothing but delegate)

---

## 3. Backend Testing (pytest + httpx)

### Dependencies

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.coverage.run]
source = ["app"]
omit = ["app/db/migrations/*", "app/main.py"]

[tool.coverage.report]
fail_under = 80
```

```
pytest                     # run all
pytest tests/routes/       # routes only
pytest tests/services/     # services only
pytest -k "test_send"      # name filter
pytest --cov=app --cov-report=html
```

### conftest.py Pattern

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.main import app
from app.dependencies import get_db, get_current_user
from app.models.base import Base
from app.models.user import User

TEST_DATABASE_URL = "postgresql+asyncpg://ember:ember@localhost/ember_test"

test_engine = create_async_engine(TEST_DATABASE_URL)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestSession() as session:
        yield session
        await session.rollback()  # isolate each test


@pytest_asyncio.fixture
def fake_user() -> User:
    return User(
        id="test-user-id",
        cognito_sub="test-sub-123",
        email="test@ember.ai",
    )


@pytest_asyncio.fixture
async def client(db: AsyncSession, fake_user: User) -> AsyncClient:
    async def override_db():
        yield db

    async def override_user():
        return fake_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
```

### Route Tests

```python
# tests/routes/test_messages.py
import pytest
from httpx import AsyncClient


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_returns_201_with_valid_body(self, client: AsyncClient):
        response = await client.post(
            "/characters/char-1/messages",
            json={"content": "Hello Ember"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["role"] == "assistant"
        assert body["id"] is not None
        assert body["content"] != ""

    @pytest.mark.asyncio
    async def test_returns_422_with_empty_content(self, client: AsyncClient):
        response = await client.post(
            "/characters/char-1/messages",
            json={"content": ""},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_401_without_auth(self):
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/characters/char-1/messages",
                json={"content": "Hi"},
            )
        assert response.status_code == 401


class TestListMessages:
    @pytest.mark.asyncio
    async def test_returns_empty_page_for_new_character(self, client: AsyncClient):
        response = await client.get("/characters/new-char/messages")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_cursor_pagination_returns_correct_pages(self, client: AsyncClient):
        # Seed 5 messages
        for i in range(5):
            await client.post("/characters/char-p/messages", json={"content": f"msg {i}"})

        page1 = (await client.get("/characters/char-p/messages?limit=2")).json()
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True
        assert page1["next_cursor"] is not None

        page2 = (await client.get(
            f"/characters/char-p/messages?limit=2&cursor={page1['next_cursor']}"
        )).json()
        assert len(page2["items"]) == 2

        # No ID overlap between pages
        ids_p1 = {m["id"] for m in page1["items"]}
        ids_p2 = {m["id"] for m in page2["items"]}
        assert ids_p1.isdisjoint(ids_p2)
```

### Mocking External Services

```python
# tests/services/test_llm_service.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_claude_provider_returns_text():
    with patch("anthropic.AsyncAnthropic") as mock_anthropic:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello from Claude")]
        mock_anthropic.return_value.messages.create = AsyncMock(return_value=mock_response)

        from app.services.llm_service import ClaudeProvider
        provider = ClaudeProvider()
        result = await provider.complete(
            system="You are Ember.",
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert result == "Hello from Claude"


@pytest.mark.asyncio
async def test_memory_service_uses_correct_agent_id():
    with patch("app.services.memory_service.get_mem0_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.search = AsyncMock(return_value=[])
        mock_client_factory.return_value = mock_client

        from app.services.memory_service import MemoryService
        svc = MemoryService()
        await svc.search(query="test", user_id="user123", template_id="luna")

        mock_client.search.assert_called_once_with(
            query="test",
            user_id="user123",
            agent_id="luna_user123",
            limit=10,
        )


@pytest.mark.asyncio
async def test_elevenlabs_voice_synthesis():
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake-audio-bytes"
        mock_post.return_value = mock_response

        from app.services.voice_service import VoiceService
        svc = VoiceService()
        audio = await svc.synthesize(text="Hello", voice_id="voice-1")
        assert isinstance(audio, bytes)
        assert len(audio) > 0
```

---

## 4. iOS Testing (Swift Testing + XCTest)

### Preferred: Swift Testing (new tests)

```swift
// Tests/Unit/ChatViewModelTests.swift
import Testing
@testable import EmberApp

@Suite("ChatViewModel tests")
struct ChatViewModelTests {

    @Test("initial state: messages are empty after loadHistory with empty page")
    func initialStateEmpty() async throws {
        let mock = MockAPIClient()
        mock.messagePage = MessagePage(items: [], nextCursor: nil, hasMore: false)
        let vm = ChatViewModel(characterId: "c1", apiClient: mock)

        await vm.loadHistory()

        #expect(vm.messages.isEmpty)
        #expect(vm.errorMessage == nil)
        #expect(vm.isStreaming == false)
    }

    @Test("sendMessage: appends user then assistant message")
    func sendMessageAppendsMessages() async throws {
        let mock = MockAPIClient()
        mock.streamResponse = ["Hi", " there"]
        let vm = ChatViewModel(characterId: "c1", apiClient: mock)

        vm.inputText = "Hello"
        await vm.sendMessage()

        #expect(vm.messages.count == 2)
        #expect(vm.messages[0].role == .user)
        #expect(vm.messages[0].content == "Hello")
        #expect(vm.messages[1].role == .assistant)
        #expect(vm.messages[1].content == "Hi there")
        #expect(vm.inputText.isEmpty)
        #expect(vm.isStreaming == false)
    }

    @Test("sendMessage: sets errorMessage on network failure")
    func sendMessageSetsError() async throws {
        let mock = MockAPIClient()
        mock.shouldThrow = APIError.httpError(statusCode: 503)
        let vm = ChatViewModel(characterId: "c1", apiClient: mock)

        vm.inputText = "Test"
        await vm.sendMessage()

        #expect(vm.errorMessage != nil)
        #expect(vm.messages.isEmpty)  // no partial user message left
    }

    @Test("sendMessage: does nothing when inputText is empty")
    func sendMessageIgnoresEmptyInput() async throws {
        let mock = MockAPIClient()
        let vm = ChatViewModel(characterId: "c1", apiClient: mock)

        vm.inputText = "   "
        await vm.sendMessage()

        #expect(vm.messages.isEmpty)
        #expect(!mock.streamMessageCalled)
    }
}
```

### Legacy XCTest (for existing tests and UI tests)

```swift
// Tests/Integration/MessagePaginationTests.swift
import XCTest
@testable import EmberApp

final class MessagePaginationTests: XCTestCase {

    var mockAPI: MockAPIClient!

    override func setUp() {
        super.setUp()
        mockAPI = MockAPIClient()
    }

    func testLoadHistoryLoadsFirstPage() async throws {
        mockAPI.messagePage = MessagePage(
            items: [
                Message(id: "1", role: .user, content: "Hello"),
                Message(id: "2", role: .assistant, content: "Hi"),
            ],
            nextCursor: "cursor-abc",
            hasMore: true
        )
        let vm = ChatViewModel(characterId: "c1", apiClient: mockAPI)

        await vm.loadHistory()

        XCTAssertEqual(vm.messages.count, 2)
        XCTAssertEqual(vm.messages[0].id, "2")  // reversed (latest first)
    }

    func testLoadMoreAppendsMessages() async throws {
        let vm = ChatViewModel(characterId: "c1", apiClient: mockAPI)
        // ... setup and assertions
    }
}
```

### Fake Objects Pattern

```swift
// Tests/Fakes/MockAPIClient.swift
import Foundation
@testable import EmberApp

final class MockAPIClient: APIClientProtocol {
    // Controllable state
    var messagePage = MessagePage(items: [], nextCursor: nil, hasMore: false)
    var streamResponse: [String] = []
    var shouldThrow: Error? = nil
    var characters: [Character] = []

    // Call tracking
    var sendMessageCalled = false
    var streamMessageCalled = false
    var listMessagesCursor: String? = nil

    func listMessages(characterId: String, cursor: String?, limit: Int) async throws -> MessagePage {
        listMessagesCursor = cursor
        if let error = shouldThrow { throw error }
        return messagePage
    }

    func sendMessage(characterId: String, content: String) async throws -> Message {
        sendMessageCalled = true
        if let error = shouldThrow { throw error }
        return Message(id: UUID().uuidString, role: .assistant, content: streamResponse.joined())
    }

    func streamMessage(characterId: String, content: String) -> AsyncThrowingStream<String, Error> {
        streamMessageCalled = true
        let chunks = streamResponse
        let error = shouldThrow
        return AsyncThrowingStream { continuation in
            Task {
                if let error {
                    continuation.finish(throwing: error)
                    return
                }
                for chunk in chunks {
                    continuation.yield(chunk)
                }
                continuation.finish()
            }
        }
    }

    func listCharacters() async throws -> [Character] {
        if let error = shouldThrow { throw error }
        return characters
    }
}
```

---

## 5. Android Testing (JUnit + MockK + Turbine)

### Test Dependencies

```kotlin
// app/build.gradle.kts
dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("io.mockk:mockk:1.13.10")
    testImplementation("app.cash.turbine:turbine:1.1.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    testImplementation("com.google.truth:truth:1.4.2")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("com.google.dagger:hilt-android-testing:2.51.1")
}
```

### ViewModel Tests with Turbine

```kotlin
// features/chat/ChatViewModelTest.kt
@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val chatRepository: ChatRepository = mockk()
    private val savedStateHandle = SavedStateHandle(mapOf("characterId" to "char-1"))
    private lateinit var viewModel: ChatViewModel

    @Before
    fun setUp() {
        coEvery {
            chatRepository.getMessages("char-1", null, 30)
        } returns Result.success(MessagePage(emptyList(), null, false))

        viewModel = ChatViewModel(chatRepository, savedStateHandle)
    }

    @Test
    fun `uiState starts as Loading then transitions to Success`() = runTest {
        viewModel.uiState.test {
            assertIs<ChatUiState.Success>(awaitItem())
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `sendMessage emits user and assistant messages`() = runTest {
        every { chatRepository.streamMessage("char-1", "Hi") } returns flowOf("Hello", "!")

        viewModel.uiState.test {
            skipItems(1)  // initial Success(empty)

            viewModel.onInputChanged("Hi")
            viewModel.sendMessage()

            val streamingState = awaitItem()
            assertIs<ChatUiState.Success>(streamingState)
            Truth.assertThat(streamingState.isStreaming).isTrue()

            val finalState = expectMostRecentItem()
            assertIs<ChatUiState.Success>(finalState)
            Truth.assertThat(finalState.messages).hasSize(2)
            Truth.assertThat(finalState.messages[0].content).isEqualTo("Hi")
            Truth.assertThat(finalState.messages[1].content).isEqualTo("Hello!")
            Truth.assertThat(finalState.isStreaming).isFalse()
        }
    }

    @Test
    fun `sendMessage transitions to Error on exception`() = runTest {
        every {
            chatRepository.streamMessage("char-1", "Hi")
        } throws RuntimeException("Connection failed")

        viewModel.uiState.test {
            skipItems(1)
            viewModel.onInputChanged("Hi")
            viewModel.sendMessage()

            val errorState = expectMostRecentItem()
            assertIs<ChatUiState.Error>(errorState)
            Truth.assertThat(errorState.message).isNotEmpty()
        }
    }

    @Test
    fun `inputText is cleared after sendMessage`() = runTest {
        every { chatRepository.streamMessage(any(), any()) } returns flowOf("Response")

        viewModel.onInputChanged("Hello world")
        Truth.assertThat(viewModel.inputText.value).isEqualTo("Hello world")

        viewModel.sendMessage()

        Truth.assertThat(viewModel.inputText.value).isEmpty()
    }
}

// Test utility
class MainDispatcherRule : TestWatcher() {
    private val dispatcher = UnconfinedTestDispatcher()
    override fun starting(description: Description) = Dispatchers.setMain(dispatcher)
    override fun finished(description: Description) = Dispatchers.resetMain()
}
```

### Compose UI Tests

```kotlin
// androidTest/features/chat/ChatScreenTest.kt
@HiltAndroidTest
class ChatScreenTest {

    @get:Rule(order = 0)
    val hiltRule = HiltAndroidRule(this)

    @get:Rule(order = 1)
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Inject
    lateinit var chatRepository: ChatRepository  // injected via test module

    @Before
    fun setUp() {
        hiltRule.inject()
    }

    @Test
    fun sendButton_isDisabled_whenInputEmpty() {
        composeRule.setContent {
            EmberTheme(darkTheme = true) {
                ChatScreen(characterId = "char-1")
            }
        }

        composeRule
            .onNodeWithContentDescription("Send message")
            .assertIsNotEnabled()
    }

    @Test
    fun messageList_displaysHistoricalMessages() {
        // Setup fake repository to return pre-seeded messages
        // ...
        composeRule.setContent {
            EmberTheme { ChatScreen(characterId = "char-1") }
        }

        composeRule
            .onNodeWithText("Hello from history")
            .assertIsDisplayed()
    }
}
```

---

## 6. Integration vs Unit Test Distinction

### Unit Tests

- Test a **single class** in isolation.
- All dependencies are **mocked or faked**.
- No network calls, no database, no file I/O.
- Fast: < 10ms per test.
- Located in `tests/` (backend), `Tests/Unit/` (iOS), `src/test/` (Android).

```
Unit test = class under test + all collaborators replaced with mocks/fakes
```

### Integration Tests

- Test **two or more real classes** working together.
- May use real database (test container or in-memory).
- No external network calls (mock HTTP at boundary).
- Medium speed: 100ms–2s per test.
- Located in `tests/integration/` (backend), `Tests/Integration/` (iOS), `src/androidTest/` (Android).

```
Integration test = real service + real DB + mocked external APIs
```

### End-to-End Tests (E2E)

- Not required in CI for every PR.
- Run weekly or before releases.
- Use a real staging environment.
- Backend: `pytest tests/e2e/` against staging API.
- Mobile: Detox (iOS) / Maestro (Android) against staging.

---

## 7. Test Naming Conventions

### Backend (Python)

```python
# Module: test_{module_name}.py
# Class: Test{FeatureName}
# Method: test_{what}_{condition}_{expected}

class TestSendMessage:
    async def test_returns_201_with_valid_content(self): ...
    async def test_returns_422_with_empty_content(self): ...
    async def test_returns_401_without_bearer_token(self): ...
    async def test_returns_404_for_unknown_character(self): ...
```

### iOS (Swift Testing)

```swift
// Suite: named after the class under test
@Suite("ChatViewModel")
struct ChatViewModelTests {
    // Test: describe the behavior in plain English
    @Test("sends message: appends user and assistant to messages list")
    func sendsMessageAppendsMessages() async throws { }

    @Test("sends message: clears input text after send")
    func sendsMessageClearsInput() async throws { }

    @Test("sends message: sets errorMessage on network failure")
    func sendsMessageSetsErrorOnFailure() async throws { }
}
```

### Android (JUnit)

```kotlin
// Method: backtick format describing behavior
class ChatViewModelTest {
    @Test
    fun `sendMessage emits user and assistant messages`() { }

    @Test
    fun `sendMessage clears input text`() { }

    @Test
    fun `sendMessage transitions to Error on network failure`() { }
}
```

---

## 8. Test File Locations

### Backend

```
backend/
  tests/
    conftest.py                   # shared fixtures
    routes/
      test_messages.py
      test_characters.py
      test_auth.py
    services/
      test_message_service.py
      test_memory_service.py
      test_llm_service.py
      test_voice_service.py
    utils/
      test_cursor.py
      test_cognito.py
    integration/
      test_send_message_flow.py   # service + DB, no mocks
```

### iOS

```
EmberApp/
  Tests/
    Unit/
      ChatViewModelTests.swift
      CharactersViewModelTests.swift
      MemoryViewModelTests.swift
      CursorTests.swift
    Integration/
      MessagePaginationTests.swift
      AuthServiceTests.swift
    Fakes/
      MockAPIClient.swift
      MockAuthService.swift
    UITests/                       # XCUITest
      ChatFlowTests.swift
```

### Android

```
app/
  src/
    test/kotlin/ai/ember/app/      # unit tests
      features/
        chat/ChatViewModelTest.kt
        characters/CharactersViewModelTest.kt
      core/
        network/ChatRepositoryTest.kt
        utils/CursorUtilsTest.kt
    androidTest/kotlin/ai/ember/app/  # instrumented + Compose tests
      features/chat/ChatScreenTest.kt
      di/FakeNetworkModule.kt
```

---

## 9. CI Test Commands

### Backend

```bash
# Install test dependencies
pip install -e ".[test]"

# Run unit tests
pytest tests/routes/ tests/services/ tests/utils/ -v

# Run with coverage
pytest --cov=app --cov-report=xml --cov-fail-under=80

# Run integration tests (requires test DB)
pytest tests/integration/ -v

# Type check
mypy app --strict

# Lint
ruff check app tests
black --check app tests
```

### iOS

```bash
# Run unit tests (simulator)
xcodebuild test \
  -scheme EmberApp \
  -destination "platform=iOS Simulator,name=iPhone 16,OS=18.0" \
  -enableCodeCoverage YES \
  -resultBundlePath TestResults/unit.xcresult \
  -only-testing:EmberAppTests

# Run UI tests
xcodebuild test \
  -scheme EmberApp \
  -destination "platform=iOS Simulator,name=iPhone 16,OS=18.0" \
  -only-testing:EmberAppUITests

# Check coverage threshold (xcresult → codecov or custom script)
xcrun xcresulttool get --path TestResults/unit.xcresult --format json | \
  python3 scripts/check_coverage.py --min-line 80
```

### Android

```bash
# Run unit tests
./gradlew :app:testDebugUnitTest

# Run unit tests with coverage
./gradlew :app:testDebugUnitTest :app:jacocoTestReport

# Check coverage thresholds
./gradlew :app:jacocoCoverageVerification

# Run instrumented tests (requires emulator or device)
./gradlew :app:connectedDebugAndroidTest

# Lint
./gradlew :app:lintDebug :app:ktlintCheck

# Full CI gate
./gradlew :app:testDebugUnitTest :app:jacocoCoverageVerification :app:lintDebug
```

### All Platforms (from repo root)

```bash
# Backend
cd backend && pytest --cov=app --cov-fail-under=80

# iOS (from CI machine with Xcode)
xcodebuild test -scheme EmberApp -destination "..." -enableCodeCoverage YES

# Android
./gradlew :app:testDebugUnitTest :app:jacocoCoverageVerification

# Type checking (backend)
mypy backend/app --strict
```

---

## Appendix: Common Testing Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|---|---|---|
| Mocking the class under test | You test nothing meaningful | Mock collaborators, not the SUT |
| `time.sleep` / `Thread.sleep` in tests | Flaky, slow | Use fake clocks or mock timers |
| Tests sharing mutable state | Order-dependent failures | Each test gets a fresh fixture |
| Testing only the happy path | Bugs live in error paths | Always test at least one error case |
| Asserting on log output | Fragile, couples to implementation | Assert on state/return values |
| Real network calls in unit tests | Flaky, slow, non-deterministic | Always mock at the HTTP boundary |
| OFFSET pagination in test seeds | Misses real pagination bugs | Test with cursor from actual response |
