package ai.ember.app.features.onboarding

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class OnboardingRepositoryTest {

    private lateinit var onboardingApi: OnboardingApi
    private lateinit var repository: OnboardingRepository
    private val json = Json { ignoreUnknownKeys = true }

    private val validAnswers = listOf(
        OnboardingAnswer("preferred_name", "Alex"),
        OnboardingAnswer("occupation", "Engineer"),
        OnboardingAnswer("daily_rhythm", "Morning person"),
        OnboardingAnswer("health_goal", "Run a marathon"),
        OnboardingAnswer("stress_management", "Walking"),
        OnboardingAnswer("sleep_schedule", "11pm to 7am"),
        OnboardingAnswer("communication_style", "Casual"),
    )

    @Before
    fun setUp() {
        onboardingApi = mockk()
        repository = OnboardingRepository(onboardingApi, json)
    }

    @Test
    fun `completeOnboarding returns success on 200`() = runTest {
        val response = OnboardingResponse(onboardingCompleted = true, memoriesSeeded = 7)
        coEvery { onboardingApi.completeOnboarding(any()) } returns Response.success(response)

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isSuccess)
        assertEquals(true, result.getOrNull()?.onboardingCompleted)
        assertEquals(7, result.getOrNull()?.memoriesSeeded)
    }

    @Test
    fun `completeOnboarding treats 409 as success`() = runTest {
        val errorBody = okhttp3.ResponseBody.create(
            okhttp3.MediaType.parse("application/json"),
            """{"detail": "Onboarding already completed"}""",
        )
        coEvery { onboardingApi.completeOnboarding(any()) } returns
            Response.error(409, errorBody)

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isSuccess)
        assertEquals(true, result.getOrNull()?.onboardingCompleted)
    }

    @Test
    fun `completeOnboarding returns failure on 503`() = runTest {
        val errorBody = okhttp3.ResponseBody.create(
            okhttp3.MediaType.parse("application/json"),
            """{"detail": "AI service temporarily unavailable"}""",
        )
        coEvery { onboardingApi.completeOnboarding(any()) } returns
            Response.error(503, errorBody)

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<OnboardingException>(exception)
        assertEquals("AI service temporarily unavailable", exception.message)
    }

    @Test
    fun `completeOnboarding returns failure on 422`() = runTest {
        val errorBody = okhttp3.ResponseBody.create(
            okhttp3.MediaType.parse("application/json"),
            """{"detail": "Missing question keys: occupation"}""",
        )
        coEvery { onboardingApi.completeOnboarding(any()) } returns
            Response.error(422, errorBody)

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<OnboardingException>(exception)
        assertEquals("Missing question keys: occupation", exception.message)
    }

    @Test
    fun `completeOnboarding returns failure on 401`() = runTest {
        val errorBody = okhttp3.ResponseBody.create(
            okhttp3.MediaType.parse("application/json"),
            """{"detail": "Invalid or expired token"}""",
        )
        coEvery { onboardingApi.completeOnboarding(any()) } returns
            Response.error(401, errorBody)

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<OnboardingException>(exception)
        assertEquals("Session expired. Please sign in again.", exception.message)
    }

    @Test
    fun `completeOnboarding returns failure on network error`() = runTest {
        coEvery { onboardingApi.completeOnboarding(any()) } throws
            java.io.IOException("Connection refused")

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<OnboardingException>(exception)
        assertEquals("Connection failed. Please check your internet.", exception.message)
    }

    @Test
    fun `completeOnboarding returns failure on null response body`() = runTest {
        coEvery { onboardingApi.completeOnboarding(any()) } returns
            Response.success(null)

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isFailure)
    }

    @Test
    fun `completeOnboarding returns generic error for unknown status codes`() = runTest {
        val errorBody = okhttp3.ResponseBody.create(
            okhttp3.MediaType.parse("application/json"),
            """{"detail": "Unknown error"}""",
        )
        coEvery { onboardingApi.completeOnboarding(any()) } returns
            Response.error(500, errorBody)

        val result = repository.completeOnboarding(validAnswers)
        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<OnboardingException>(exception)
        assertEquals("Something went wrong. Please try again.", exception.message)
    }
}
