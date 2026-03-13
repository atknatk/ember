package ai.ember.app.core.error

import org.junit.Test
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class EmberErrorTest {

    // -- from(Throwable) mapping --

    @Test
    fun `from maps UnknownHostException to Offline`() {
        val error = EmberError.from(UnknownHostException("no host"))
        assertIs<EmberError.Offline>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `from maps SocketTimeoutException to Timeout`() {
        val error = EmberError.from(SocketTimeoutException("timed out"))
        assertIs<EmberError.Timeout>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `from maps SSLException to NetworkError`() {
        val error = EmberError.from(SSLException("SSL handshake failed"))
        assertIs<EmberError.NetworkError>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `from maps ConnectException to NetworkError`() {
        val error = EmberError.from(java.net.ConnectException("refused"))
        assertIs<EmberError.NetworkError>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `from maps IOException to NetworkError`() {
        val error = EmberError.from(java.io.IOException("stream closed"))
        assertIs<EmberError.NetworkError>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `from maps unknown exception to Unknown`() {
        val error = EmberError.from(IllegalStateException("wat"))
        assertIs<EmberError.Unknown>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `from unwraps EmberErrorException`() {
        val wrapped = EmberErrorException(EmberError.RateLimited)
        val error = EmberError.from(wrapped)
        assertIs<EmberError.RateLimited>(error)
    }

    // -- fromHttpStatus mapping --

    @Test
    fun `fromHttpStatus maps 401 to Unauthorized`() {
        val error = EmberError.fromHttpStatus(401)
        assertIs<EmberError.Unauthorized>(error)
        assertFalse(error.isRetryable)
        assertTrue(error.requiresReauth)
    }

    @Test
    fun `fromHttpStatus maps 404 to NotFound`() {
        val error = EmberError.fromHttpStatus(404, resource = "Character")
        assertIs<EmberError.NotFound>(error)
        assertFalse(error.isRetryable)
        assertTrue(error.userMessage.contains("Character"))
    }

    @Test
    fun `fromHttpStatus maps 429 to RateLimited`() {
        val error = EmberError.fromHttpStatus(429)
        assertIs<EmberError.RateLimited>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `fromHttpStatus maps 408 to Timeout`() {
        val error = EmberError.fromHttpStatus(408)
        assertIs<EmberError.Timeout>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `fromHttpStatus maps 500 to ServerError`() {
        val error = EmberError.fromHttpStatus(500)
        assertIs<EmberError.ServerError>(error)
        assertTrue(error.isRetryable)
        assertEquals(500, error.statusCode)
    }

    @Test
    fun `fromHttpStatus maps 503 to ServerError`() {
        val error = EmberError.fromHttpStatus(503)
        assertIs<EmberError.ServerError>(error)
        assertTrue(error.isRetryable)
    }

    @Test
    fun `fromHttpStatus maps unknown status to Unknown`() {
        val error = EmberError.fromHttpStatus(418)
        assertIs<EmberError.Unknown>(error)
    }

    // -- User messages --

    @Test
    fun `all error types have non-empty user messages`() {
        val errors = listOf(
            EmberError.Offline,
            EmberError.NetworkError(),
            EmberError.ServerError(),
            EmberError.Unauthorized,
            EmberError.NotFound(),
            EmberError.RateLimited,
            EmberError.Timeout,
            EmberError.Unknown(),
        )

        errors.forEach { error ->
            assertTrue(error.userMessage.isNotEmpty(), "Empty message for ${error::class.simpleName}")
        }
    }

    // -- Retry semantics --

    @Test
    fun `retryable errors are correctly flagged`() {
        assertTrue(EmberError.Offline.isRetryable)
        assertTrue(EmberError.NetworkError().isRetryable)
        assertTrue(EmberError.ServerError().isRetryable)
        assertTrue(EmberError.RateLimited.isRetryable)
        assertTrue(EmberError.Timeout.isRetryable)
        assertTrue(EmberError.Unknown().isRetryable)
    }

    @Test
    fun `non-retryable errors are correctly flagged`() {
        assertFalse(EmberError.Unauthorized.isRetryable)
        assertFalse(EmberError.NotFound().isRetryable)
    }

    // -- EmberErrorException --

    @Test
    fun `EmberErrorException wraps error and exposes message`() {
        val error = EmberError.ServerError(503)
        val exception = EmberErrorException(error)
        assertEquals(error.userMessage, exception.message)
        assertEquals(error, exception.emberError)
    }
}
