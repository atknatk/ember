package ai.ember.app.core.network

import ai.ember.app.core.auth.AuthRepository
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class TokenInterceptorTest {

    private lateinit var mockWebServer: MockWebServer
    private lateinit var authRepository: AuthRepository
    private lateinit var client: OkHttpClient

    @Before
    fun setUp() {
        mockWebServer = MockWebServer()
        mockWebServer.start()

        authRepository = mockk(relaxed = true)
        val lazyAuth = dagger.Lazy { authRepository }
        val interceptor = TokenInterceptor(lazyAuth)
        client = OkHttpClient.Builder()
            .addInterceptor(interceptor)
            .build()
    }

    @After
    fun tearDown() {
        mockWebServer.shutdown()
    }

    @Test
    fun `adds Authorization header for non-auth endpoints`() {
        every { authRepository.getAccessToken() } returns "test-token"
        mockWebServer.enqueue(MockResponse().setResponseCode(200).setBody("{}"))

        val request = okhttp3.Request.Builder()
            .url(mockWebServer.url("/api/v1/characters"))
            .build()
        client.newCall(request).execute()

        val recorded = mockWebServer.takeRequest()
        assertEquals("Bearer test-token", recorded.getHeader("Authorization"))
    }

    @Test
    fun `skips Authorization header for auth login endpoint`() {
        every { authRepository.getAccessToken() } returns "test-token"
        mockWebServer.enqueue(MockResponse().setResponseCode(200).setBody("{}"))

        val request = okhttp3.Request.Builder()
            .url(mockWebServer.url("/api/v1/auth/login"))
            .build()
        client.newCall(request).execute()

        val recorded = mockWebServer.takeRequest()
        assertNull(recorded.getHeader("Authorization"))
    }

    @Test
    fun `skips Authorization header for auth register endpoint`() {
        every { authRepository.getAccessToken() } returns "test-token"
        mockWebServer.enqueue(MockResponse().setResponseCode(200).setBody("{}"))

        val request = okhttp3.Request.Builder()
            .url(mockWebServer.url("/api/v1/auth/register"))
            .build()
        client.newCall(request).execute()

        val recorded = mockWebServer.takeRequest()
        assertNull(recorded.getHeader("Authorization"))
    }

    @Test
    fun `skips Authorization header for auth refresh endpoint`() {
        every { authRepository.getAccessToken() } returns "test-token"
        mockWebServer.enqueue(MockResponse().setResponseCode(200).setBody("{}"))

        val request = okhttp3.Request.Builder()
            .url(mockWebServer.url("/api/v1/auth/refresh"))
            .build()
        client.newCall(request).execute()

        val recorded = mockWebServer.takeRequest()
        assertNull(recorded.getHeader("Authorization"))
    }

    @Test
    fun `retries with new token on 401`() {
        every { authRepository.getAccessToken() } returns "old-token"
        coEvery { authRepository.refreshAccessToken() } returns "new-token"

        // First request returns 401
        mockWebServer.enqueue(MockResponse().setResponseCode(401).setBody("{}"))
        // Retry returns 200
        mockWebServer.enqueue(MockResponse().setResponseCode(200).setBody("{\"ok\":true}"))

        val request = okhttp3.Request.Builder()
            .url(mockWebServer.url("/api/v1/characters"))
            .build()
        val response = client.newCall(request).execute()

        assertEquals(200, response.code)

        // First request had old token
        val firstRequest = mockWebServer.takeRequest()
        assertEquals("Bearer old-token", firstRequest.getHeader("Authorization"))

        // Retry had new token
        val retryRequest = mockWebServer.takeRequest()
        assertEquals("Bearer new-token", retryRequest.getHeader("Authorization"))
    }

    @Test
    fun `returns 401 when token refresh fails`() {
        every { authRepository.getAccessToken() } returns "old-token"
        coEvery { authRepository.refreshAccessToken() } returns null

        mockWebServer.enqueue(MockResponse().setResponseCode(401).setBody("{}"))

        val request = okhttp3.Request.Builder()
            .url(mockWebServer.url("/api/v1/characters"))
            .build()
        val response = client.newCall(request).execute()

        assertEquals(401, response.code)
        assertEquals(1, mockWebServer.requestCount)
    }

    @Test
    fun `sends request without token when no access token stored`() {
        every { authRepository.getAccessToken() } returns null
        mockWebServer.enqueue(MockResponse().setResponseCode(200).setBody("{}"))

        val request = okhttp3.Request.Builder()
            .url(mockWebServer.url("/api/v1/characters"))
            .build()
        client.newCall(request).execute()

        val recorded = mockWebServer.takeRequest()
        assertNull(recorded.getHeader("Authorization"))
    }
}
