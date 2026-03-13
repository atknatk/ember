package ai.ember.app.features.memories

import ai.ember.app.core.models.Character
import ai.ember.app.core.models.CharacterListResponse
import ai.ember.app.core.models.MemoryItem
import ai.ember.app.core.models.MemoryListResponse
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

class MemoriesRepositoryTest {

    private lateinit var memoryApi: MemoryApi
    private lateinit var repository: MemoriesRepository
    private val json = Json { ignoreUnknownKeys = true }

    @Before
    fun setUp() {
        memoryApi = mockk()
        repository = MemoriesRepository(memoryApi, json)
    }

    // -- getCharacters --

    @Test
    fun `getCharacters returns success with characters`() = runTest {
        val characters = listOf(
            Character(id = "1", name = "Luna", template = "companion", isDefault = true),
        )
        coEvery { memoryApi.listCharacters() } returns
            Response.success(CharacterListResponse(characters))

        val result = repository.getCharacters()

        assertTrue(result.isSuccess)
        assertEquals(1, result.getOrNull()?.size)
    }

    @Test
    fun `getCharacters returns failure on network exception`() = runTest {
        coEvery { memoryApi.listCharacters() } throws
            java.io.IOException("No network")

        val result = repository.getCharacters()

        assertTrue(result.isFailure)
        assertIs<MemoriesException>(result.exceptionOrNull())
    }

    // -- getGlobalMemories --

    @Test
    fun `getGlobalMemories returns success with memories`() = runTest {
        val memories = listOf(
            MemoryItem(id = "m1", memory = "Likes coffee", createdAt = "2026-02-20T10:00:00Z"),
            MemoryItem(id = "m2", memory = "Works remotely"),
        )
        coEvery { memoryApi.listGlobalMemories() } returns
            Response.success(MemoryListResponse(memories))

        val result = repository.getGlobalMemories()

        assertTrue(result.isSuccess)
        assertEquals(2, result.getOrNull()?.size)
        assertEquals("Likes coffee", result.getOrNull()?.get(0)?.memory)
    }

    @Test
    fun `getGlobalMemories returns success with empty list`() = runTest {
        coEvery { memoryApi.listGlobalMemories() } returns
            Response.success(MemoryListResponse(emptyList()))

        val result = repository.getGlobalMemories()

        assertTrue(result.isSuccess)
        assertEquals(0, result.getOrNull()?.size)
    }

    @Test
    fun `getGlobalMemories returns failure on 503`() = runTest {
        coEvery { memoryApi.listGlobalMemories() } returns
            Response.error(
                503,
                """{"detail":"Memory service unavailable"}""".toResponseBody(),
            )

        val result = repository.getGlobalMemories()

        assertTrue(result.isFailure)
        val exception = result.exceptionOrNull()
        assertIs<MemoriesException>(exception)
        assertEquals("Memory service unavailable. Please try again.", exception.message)
    }

    @Test
    fun `getGlobalMemories returns failure on network exception`() = runTest {
        coEvery { memoryApi.listGlobalMemories() } throws
            java.io.IOException("Network error")

        val result = repository.getGlobalMemories()

        assertTrue(result.isFailure)
        assertIs<MemoriesException>(result.exceptionOrNull())
        assertEquals(
            "Connection failed. Please check your internet.",
            result.exceptionOrNull()?.message,
        )
    }

    // -- getCharacterMemories --

    @Test
    fun `getCharacterMemories returns success with memories`() = runTest {
        val memories = listOf(
            MemoryItem(id = "m1", memory = "Confuses affect vs effect"),
        )
        coEvery { memoryApi.listCharacterMemories("char-1") } returns
            Response.success(MemoryListResponse(memories))

        val result = repository.getCharacterMemories("char-1")

        assertTrue(result.isSuccess)
        assertEquals(1, result.getOrNull()?.size)
    }

    @Test
    fun `getCharacterMemories returns failure on 401`() = runTest {
        coEvery { memoryApi.listCharacterMemories("char-1") } returns
            Response.error(
                401,
                """{"detail":"Unauthorized"}""".toResponseBody(),
            )

        val result = repository.getCharacterMemories("char-1")

        assertTrue(result.isFailure)
        assertIs<MemoriesException>(result.exceptionOrNull())
        assertEquals("Session expired. Please sign in again.", result.exceptionOrNull()?.message)
    }

    // -- deleteGlobalMemory --

    @Test
    fun `deleteGlobalMemory returns success on 204`() = runTest {
        coEvery { memoryApi.deleteGlobalMemory("m1") } returns
            Response.success(204, Unit)

        val result = repository.deleteGlobalMemory("m1")

        assertTrue(result.isSuccess)
    }

    @Test
    fun `deleteGlobalMemory returns failure on error`() = runTest {
        coEvery { memoryApi.deleteGlobalMemory("m1") } returns
            Response.error(
                503,
                """{"detail":"Memory service unavailable"}""".toResponseBody(),
            )

        val result = repository.deleteGlobalMemory("m1")

        assertTrue(result.isFailure)
    }

    @Test
    fun `deleteGlobalMemory returns failure on network exception`() = runTest {
        coEvery { memoryApi.deleteGlobalMemory("m1") } throws
            java.io.IOException("Network error")

        val result = repository.deleteGlobalMemory("m1")

        assertTrue(result.isFailure)
        assertIs<MemoriesException>(result.exceptionOrNull())
    }

    // -- deleteCharacterMemory --

    @Test
    fun `deleteCharacterMemory returns success on 204`() = runTest {
        coEvery { memoryApi.deleteCharacterMemory("char-1", "m1") } returns
            Response.success(204, Unit)

        val result = repository.deleteCharacterMemory("char-1", "m1")

        assertTrue(result.isSuccess)
    }

    @Test
    fun `deleteCharacterMemory returns failure on error`() = runTest {
        coEvery { memoryApi.deleteCharacterMemory("char-1", "m1") } returns
            Response.error(
                503,
                """{"detail":"Memory service unavailable"}""".toResponseBody(),
            )

        val result = repository.deleteCharacterMemory("char-1", "m1")

        assertTrue(result.isFailure)
    }
}
