package ai.ember.app.core.error

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Test
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class RetryHelperTest {

    @Test
    fun `withRetry returns result on first success`() = runTest {
        var callCount = 0
        val result = RetryHelper.withRetry(maxAttempts = 3) {
            callCount++
            "success"
        }
        assertEquals("success", result)
        assertEquals(1, callCount)
    }

    @Test
    fun `withRetry retries on retryable error then succeeds`() = runTest {
        var callCount = 0
        val result = RetryHelper.withRetry(
            maxAttempts = 3,
            baseDelayMs = 1,
            jitter = false,
        ) {
            callCount++
            if (callCount < 3) {
                throw SocketTimeoutException("timeout")
            }
            "success"
        }
        assertEquals("success", result)
        assertEquals(3, callCount)
    }

    @Test
    fun `withRetry throws immediately on non-retryable error`() = runTest {
        var callCount = 0
        val exception = assertFailsWith<EmberErrorException> {
            RetryHelper.withRetry(maxAttempts = 3, baseDelayMs = 1) {
                callCount++
                throw EmberErrorException(EmberError.Unauthorized)
            }
        }
        assertIs<EmberError.Unauthorized>(exception.emberError)
        assertEquals(1, callCount)
    }

    @Test
    fun `withRetry throws after exhausting all attempts`() = runTest {
        var callCount = 0
        val exception = assertFailsWith<EmberErrorException> {
            RetryHelper.withRetry(
                maxAttempts = 3,
                baseDelayMs = 1,
                jitter = false,
            ) {
                callCount++
                throw UnknownHostException("no host")
            }
        }
        assertIs<EmberError.Offline>(exception.emberError)
        assertEquals(3, callCount)
    }

    @Test
    fun `withRetry wraps unknown exceptions as EmberError`() = runTest {
        val exception = assertFailsWith<EmberErrorException> {
            RetryHelper.withRetry(
                maxAttempts = 1,
                baseDelayMs = 1,
            ) {
                throw IllegalStateException("unexpected")
            }
        }
        assertIs<EmberError.Unknown>(exception.emberError)
    }

    // -- calculateDelay --

    @Test
    fun `calculateDelay uses exponential backoff`() {
        val delay0 = RetryHelper.calculateDelay(0, 1000, 10000, jitter = false)
        val delay1 = RetryHelper.calculateDelay(1, 1000, 10000, jitter = false)
        val delay2 = RetryHelper.calculateDelay(2, 1000, 10000, jitter = false)

        assertEquals(1000, delay0)
        assertEquals(2000, delay1)
        assertEquals(4000, delay2)
    }

    @Test
    fun `calculateDelay caps at maxDelay`() {
        val delay = RetryHelper.calculateDelay(10, 1000, 5000, jitter = false)
        assertEquals(5000, delay)
    }

    @Test
    fun `calculateDelay with jitter stays within range`() {
        repeat(100) {
            val delay = RetryHelper.calculateDelay(1, 1000, 10000, jitter = true)
            assertTrue(delay >= 1000, "Delay $delay should be >= 1000")
            assertTrue(delay <= 2000, "Delay $delay should be <= 2000")
        }
    }
}
