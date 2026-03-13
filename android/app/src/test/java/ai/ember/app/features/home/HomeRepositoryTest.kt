package ai.ember.app.features.home

import ai.ember.app.core.models.Character
import ai.ember.app.core.models.CharacterListResponse
import ai.ember.app.core.models.MessageListResponse
import ai.ember.app.core.models.MessagePreview
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

class HomeRepositoryTest {

    private lateinit var characterApi: CharacterApi
    private lateinit var repository: HomeRepository
    private val json = Json { ignoreUnknownKeys = true }

    @Before
    fun setUp() {
        characterApi = mockk()
        repository = HomeRepository(characterApi, json)
    }

    // -- getCharacters --

    @Test
    fun `getCharacters returns success with characters`() = runTest {
        val characters = listOf(
            Character(id = "1", name = "Luna", template = "companion", isDefault = true),
            Character(id = "2", name = "Sarah", template = "english_teacher"),
        )
        coEvery { characterApi.listCharacters() } returns
            Response.success(CharacterListResponse(characters))

        val result = repository.getCharacters()

        assertTrue(result.isSuccess)
        assertEquals(2, result.getOrNull()?.size)
    }

    @Test
    fun `getCharacters returns success with empty list`() = runTest {
        coEvery { characterApi.listCharacters() } returns
            Response.success(CharacterListResponse(emptyList()))

        val result = repository.getCharacters()

        assertTrue(result.isSuccess)
        assertEquals(0, result.getOrNull()?.size)
    }

    @Test
    fun `getCharacters returns failure on 401`() = runTest {
        coEvery { characterApi.listCharacters() } returns
            Response.error(
                401,
                """{"detail":"Unauthorized"}""".toResponseBody(),
            )

        val result = repository.getCharacters()

        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<HomeException>(exception)
        assertEquals("Session expired. Please sign in again.", exception.message)
    }

    @Test
    fun `getCharacters returns failure on network exception`() = runTest {
        coEvery { characterApi.listCharacters() } throws
            java.io.IOException("No network")

        val result = repository.getCharacters()

        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<HomeException>(exception)
        assertEquals("Connection failed. Please check your internet.", exception.message)
    }

    @Test
    fun `getCharacters returns failure on 500`() = runTest {
        coEvery { characterApi.listCharacters() } returns
            Response.error(
                500,
                """{"detail":"Internal server error"}""".toResponseBody(),
            )

        val result = repository.getCharacters()

        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<HomeException>(exception)
        assertEquals("Internal server error", exception.message)
    }

    // -- getLastMessages --

    @Test
    fun `getLastMessages returns map of character id to preview`() = runTest {
        val preview1 = MessagePreview(id = "m1", role = "assistant", content = "Hello!")
        val preview2 = MessagePreview(id = "m2", role = "assistant", content = "Hi!")

        coEvery { characterApi.listMessages("1", null, 1) } returns
            Response.success(MessageListResponse(items = listOf(preview1)))
        coEvery { characterApi.listMessages("2", null, 1) } returns
            Response.success(MessageListResponse(items = listOf(preview2)))

        val result = repository.getLastMessages(listOf("1", "2"))

        assertEquals(2, result.size)
        assertEquals("Hello!", result["1"]?.content)
        assertEquals("Hi!", result["2"]?.content)
    }

    @Test
    fun `getLastMessages skips characters with no messages`() = runTest {
        coEvery { characterApi.listMessages("1", null, 1) } returns
            Response.success(MessageListResponse(items = emptyList()))

        val result = repository.getLastMessages(listOf("1"))

        assertTrue(result.isEmpty())
    }

    @Test
    fun `getLastMessages skips failed requests silently`() = runTest {
        val preview = MessagePreview(id = "m1", role = "assistant", content = "Hello!")

        coEvery { characterApi.listMessages("1", null, 1) } returns
            Response.success(MessageListResponse(items = listOf(preview)))
        coEvery { characterApi.listMessages("2", null, 1) } throws
            java.io.IOException("Network error")

        val result = repository.getLastMessages(listOf("1", "2"))

        assertEquals(1, result.size)
        assertEquals("Hello!", result["1"]?.content)
    }
}
