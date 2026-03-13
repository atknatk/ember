package ai.ember.app.features.chat

import ai.ember.app.core.auth.AuthRepository
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class ChatRepositoryTest {

    private lateinit var chatApi: ChatApi
    private lateinit var okHttpClient: OkHttpClient
    private lateinit var authRepository: AuthRepository
    private lateinit var json: Json
    private lateinit var repository: ChatRepository

    @Before
    fun setUp() {
        chatApi = mockk()
        okHttpClient = OkHttpClient()
        authRepository = mockk()
        json = Json {
            ignoreUnknownKeys = true
            coerceInputValues = true
            isLenient = true
        }
        repository = ChatRepository(chatApi, okHttpClient, authRepository, json)
    }

    @Test
    fun `getMessages returns success on 200`() = runTest {
        val page = ChatMessageListResponse(
            items = listOf(
                ChatMessage(id = "1", role = MessageRole.ASSISTANT, content = "Hello!"),
            ),
            nextCursor = "cursor1",
            hasMore = true,
        )
        coEvery { chatApi.listMessages("char-1", null, 20) } returns Response.success(page)

        val result = repository.getMessages("char-1", null, 20)
        assertTrue(result.isSuccess)
        assertEquals(1, result.getOrNull()?.items?.size)
        assertEquals("cursor1", result.getOrNull()?.nextCursor)
        assertTrue(result.getOrNull()?.hasMore == true)
    }

    @Test
    fun `getMessages returns success with empty list`() = runTest {
        val page = ChatMessageListResponse(items = emptyList(), hasMore = false)
        coEvery { chatApi.listMessages("char-1", null, 20) } returns Response.success(page)

        val result = repository.getMessages("char-1", null, 20)
        assertTrue(result.isSuccess)
        assertTrue(result.getOrNull()?.items?.isEmpty() == true)
        assertFalse(result.getOrNull()?.hasMore == true)
    }

    @Test
    fun `getMessages returns failure on network error`() = runTest {
        coEvery { chatApi.listMessages("char-1", null, 20) } throws Exception("timeout")

        val result = repository.getMessages("char-1", null, 20)
        assertTrue(result.isFailure)
        assertIs<ChatException>(result.exceptionOrNull())
    }

    @Test
    fun `getMessages with cursor passes cursor to API`() = runTest {
        val page = ChatMessageListResponse(
            items = listOf(
                ChatMessage(id = "1", role = MessageRole.USER, content = "Hi"),
            ),
            nextCursor = null,
            hasMore = false,
        )
        coEvery { chatApi.listMessages("char-1", "cursor1", 20) } returns Response.success(page)

        val result = repository.getMessages("char-1", "cursor1", 20)
        assertTrue(result.isSuccess)
        assertEquals(1, result.getOrNull()?.items?.size)
    }
}
