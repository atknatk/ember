package ai.ember.app.features.profile

import ai.ember.app.core.models.Character
import ai.ember.app.core.models.CharacterListResponse
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class ProfileRepositoryTest {

    private lateinit var profileApi: ProfileApi
    private lateinit var okHttpClient: OkHttpClient
    private lateinit var json: Json
    private lateinit var repository: ProfileRepository

    @Before
    fun setUp() {
        profileApi = mockk()
        okHttpClient = OkHttpClient()
        json = Json { ignoreUnknownKeys = true }
        repository = ProfileRepository(profileApi, okHttpClient, json)
    }

    // -- getProfile --

    @Test
    fun `getProfile returns success on 200`() = runTest {
        val profile = createProfile()
        coEvery { profileApi.getProfile() } returns Response.success(profile)

        val result = repository.getProfile()

        assertTrue(result.isSuccess)
        assertEquals("Alex", result.getOrNull()?.name)
        assertEquals("user@example.com", result.getOrNull()?.email)
    }

    @Test
    fun `getProfile returns failure on null body`() = runTest {
        coEvery { profileApi.getProfile() } returns Response.success(null)

        val result = repository.getProfile()

        assertTrue(result.isFailure)
        assertIs<ProfileException>(result.exceptionOrNull())
    }

    @Test
    fun `getProfile returns failure on 401`() = runTest {
        coEvery { profileApi.getProfile() } returns Response.error(
            401,
            """{"detail":"Invalid or expired token"}""".toResponseBody(),
        )

        val result = repository.getProfile()

        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<ProfileException>(exception)
        assertEquals("Session expired. Please sign in again.", exception.message)
    }

    @Test
    fun `getProfile returns failure on network exception`() = runTest {
        coEvery { profileApi.getProfile() } throws RuntimeException("Network error")

        val result = repository.getProfile()

        assertTrue(result.isFailure)
        assertIs<ProfileException>(result.exceptionOrNull())
    }

    // -- updateProfile --

    @Test
    fun `updateProfile returns success on 200`() = runTest {
        val updatedProfile = createProfile(name = "Alex Updated")
        val request = ProfileUpdateRequest(name = "Alex Updated")
        coEvery { profileApi.updateProfile(request) } returns Response.success(updatedProfile)

        val result = repository.updateProfile(request)

        assertTrue(result.isSuccess)
        assertEquals("Alex Updated", result.getOrNull()?.name)
    }

    @Test
    fun `updateProfile returns failure on 422`() = runTest {
        val request = ProfileUpdateRequest(timezone = "Invalid/Zone")
        coEvery { profileApi.updateProfile(request) } returns Response.error(
            422,
            """{"detail":"Invalid IANA timezone"}""".toResponseBody(),
        )

        val result = repository.updateProfile(request)

        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<ProfileException>(exception)
        assertEquals("Invalid IANA timezone", exception.message)
    }

    // -- deleteAccount --

    @Test
    fun `deleteAccount returns success on 204`() = runTest {
        coEvery { profileApi.deleteAccount(any()) } returns Response.success(204, Unit)

        val result = repository.deleteAccount("DELETE MY ACCOUNT")

        assertTrue(result.isSuccess)
    }

    @Test
    fun `deleteAccount returns failure on 400`() = runTest {
        coEvery { profileApi.deleteAccount(any()) } returns Response.error(
            400,
            """{"detail":"Confirmation text must be exactly 'DELETE MY ACCOUNT'"}""".toResponseBody(),
        )

        val result = repository.deleteAccount("wrong")

        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<ProfileException>(exception)
        assertTrue(exception.message?.contains("Confirmation") == true)
    }

    // -- getUploadUrl --

    @Test
    fun `getUploadUrl returns success on 200`() = runTest {
        val uploadResponse = UploadUrlResponse(
            uploadUrl = "https://s3.amazonaws.com/upload",
            fileUrl = "https://s3.amazonaws.com/file.jpg",
        )
        coEvery { profileApi.getUploadUrl(any()) } returns Response.success(uploadResponse)

        val result = repository.getUploadUrl("avatar.jpg", "image/jpeg")

        assertTrue(result.isSuccess)
        assertEquals("https://s3.amazonaws.com/upload", result.getOrNull()?.uploadUrl)
        assertEquals("https://s3.amazonaws.com/file.jpg", result.getOrNull()?.fileUrl)
    }

    // -- getCharacters --

    @Test
    fun `getCharacters returns success on 200`() = runTest {
        val characters = listOf(
            createCharacter("1", "Luna", "companion"),
            createCharacter("2", "Sarah", "english_teacher"),
        )
        coEvery { profileApi.listCharacters() } returns
            Response.success(CharacterListResponse(characters))

        val result = repository.getCharacters()

        assertTrue(result.isSuccess)
        assertEquals(2, result.getOrNull()?.size)
    }

    @Test
    fun `getCharacters returns failure on network error`() = runTest {
        coEvery { profileApi.listCharacters() } throws RuntimeException("Network error")

        val result = repository.getCharacters()

        assertTrue(result.isFailure)
        assertIs<ProfileException>(result.exceptionOrNull())
    }

    // -- Helpers --

    private fun createProfile(
        name: String = "Alex",
        email: String = "user@example.com",
    ) = ProfileData(
        id = "uuid-1",
        email = email,
        name = name,
        timezone = "America/New_York",
        preferredLanguage = "en",
        subscriptionTier = "free",
        createdAt = "2026-02-23T10:00:00Z",
    )

    private fun createCharacter(
        id: String,
        name: String,
        template: String,
    ) = Character(
        id = id,
        name = name,
        template = template,
    )
}
