package ai.ember.app.core.auth

import ai.ember.app.core.models.AuthResponse
import ai.ember.app.core.models.LoginRequest
import ai.ember.app.core.models.RefreshResponse
import ai.ember.app.core.models.RefreshTokenRequest
import ai.ember.app.core.models.RegisterRequest
import ai.ember.app.core.models.UserResponse
import ai.ember.app.core.network.AuthApi
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AuthRepositoryTest {

    private lateinit var authApi: AuthApi
    private lateinit var tokenManager: TokenManager
    private lateinit var repository: AuthRepository

    private val json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
        isLenient = true
    }

    private val fakeUser = UserResponse(
        id = "user-1",
        email = "test@example.com",
        name = "Test User",
    )

    private val fakeAuthResponse = AuthResponse(
        token = "access-token-123",
        refreshToken = "refresh-token-456",
        user = fakeUser,
    )

    @Before
    fun setUp() {
        authApi = mockk()
        tokenManager = mockk(relaxed = true)
        repository = AuthRepository(authApi, tokenManager, json)
    }

    // -- signIn --

    @Test
    fun `signIn success saves tokens and returns Result success`() = runTest {
        coEvery { authApi.login(any()) } returns Response.success(fakeAuthResponse)

        val result = repository.signIn("test@example.com", "password")

        assertTrue(result.isSuccess)
        assertEquals("access-token-123", result.getOrNull()?.token)
        verify { tokenManager.saveTokens("access-token-123", "refresh-token-456") }
    }

    @Test
    fun `signIn 401 returns failure with invalid credentials message`() = runTest {
        coEvery { authApi.login(any()) } returns Response.error(
            401,
            """{"detail":"Invalid credentials"}""".toResponseBody(),
        )

        val result = repository.signIn("test@example.com", "wrong")

        assertTrue(result.isFailure)
        assertEquals("Invalid email or password", result.exceptionOrNull()?.message)
    }

    @Test
    fun `signIn 429 returns failure with rate limit message`() = runTest {
        coEvery { authApi.login(any()) } returns Response.error(
            429,
            """{"detail":"Rate limit exceeded"}""".toResponseBody(),
        )

        val result = repository.signIn("test@example.com", "password")

        assertTrue(result.isFailure)
        assertEquals("Too many attempts. Please try again later.", result.exceptionOrNull()?.message)
    }

    @Test
    fun `signIn network error returns failure with connection message`() = runTest {
        coEvery { authApi.login(any()) } throws RuntimeException("Network unreachable")

        val result = repository.signIn("test@example.com", "password")

        assertTrue(result.isFailure)
        assertEquals("Connection failed. Please check your internet.", result.exceptionOrNull()?.message)
    }

    // -- signUp --

    @Test
    fun `signUp success saves tokens and returns Result success`() = runTest {
        coEvery { authApi.register(any()) } returns Response.success(201, fakeAuthResponse)

        val result = repository.signUp("test@example.com", "password", "Test User")

        assertTrue(result.isSuccess)
        verify { tokenManager.saveTokens("access-token-123", "refresh-token-456") }
    }

    @Test
    fun `signUp 400 with already exists returns appropriate message`() = runTest {
        coEvery { authApi.register(any()) } returns Response.error(
            400,
            """{"detail":"User already exists"}""".toResponseBody(),
        )

        val result = repository.signUp("test@example.com", "password", "Test User")

        assertTrue(result.isFailure)
        assertEquals("An account with this email already exists", result.exceptionOrNull()?.message)
    }

    @Test
    fun `signUp 400 with password issue returns password message`() = runTest {
        coEvery { authApi.register(any()) } returns Response.error(
            400,
            """{"detail":"Password does not meet requirements"}""".toResponseBody(),
        )

        val result = repository.signUp("test@example.com", "weak", "Test User")

        assertTrue(result.isFailure)
        assertEquals("Password does not meet requirements", result.exceptionOrNull()?.message)
    }

    // -- signOut --

    @Test
    fun `signOut clears tokens`() {
        repository.signOut()
        verify { tokenManager.clearTokens() }
    }

    // -- isAuthenticated --

    @Test
    fun `isAuthenticated returns tokenManager hasTokens`() {
        every { tokenManager.hasTokens } returns true
        assertTrue(repository.isAuthenticated)

        every { tokenManager.hasTokens } returns false
        assertFalse(repository.isAuthenticated)
    }

    // -- getAccessToken --

    @Test
    fun `getAccessToken delegates to tokenManager`() {
        every { tokenManager.getAccessToken() } returns "token-xyz"
        assertEquals("token-xyz", repository.getAccessToken())
    }

    // -- refreshAccessToken --

    @Test
    fun `refreshAccessToken success updates access token`() = runTest {
        every { tokenManager.getRefreshToken() } returns "refresh-token"
        coEvery { authApi.refresh(any()) } returns Response.success(
            RefreshResponse(token = "new-access-token"),
        )

        val newToken = repository.refreshAccessToken()

        assertEquals("new-access-token", newToken)
        verify { tokenManager.updateAccessToken("new-access-token") }
    }

    @Test
    fun `refreshAccessToken returns null when no refresh token stored`() = runTest {
        every { tokenManager.getRefreshToken() } returns null

        val result = repository.refreshAccessToken()

        assertNull(result)
    }

    @Test
    fun `refreshAccessToken returns null on API error`() = runTest {
        every { tokenManager.getRefreshToken() } returns "refresh-token"
        coEvery { authApi.refresh(any()) } returns Response.error(
            401,
            """{"detail":"Token expired"}""".toResponseBody(),
        )

        val result = repository.refreshAccessToken()

        assertNull(result)
    }

    @Test
    fun `refreshAccessToken returns null on network error`() = runTest {
        every { tokenManager.getRefreshToken() } returns "refresh-token"
        coEvery { authApi.refresh(any()) } throws RuntimeException("Network error")

        val result = repository.refreshAccessToken()

        assertNull(result)
    }
}
