package ai.ember.app.core.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import io.mockk.every
import io.mockk.mockk
import org.junit.Before
import org.junit.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Unit tests for [NetworkMonitor].
 *
 * Tests the synchronous connectivity check logic. The callback-based
 * flow is better tested via instrumentation tests with real ConnectivityManager.
 */
class NetworkMonitorTest {

    private lateinit var context: Context
    private lateinit var connectivityManager: ConnectivityManager

    @Before
    fun setUp() {
        connectivityManager = mockk(relaxed = true)
        context = mockk {
            every { getSystemService(Context.CONNECTIVITY_SERVICE) } returns connectivityManager
        }
    }

    @Test
    fun `isOnline is false when no active network`() {
        every { connectivityManager.activeNetwork } returns null

        val monitor = NetworkMonitor(context)
        assertFalse(monitor.isOnline.value)
    }

    @Test
    fun `isOnline is false when no capabilities`() {
        val network = mockk<Network>()
        every { connectivityManager.activeNetwork } returns network
        every { connectivityManager.getNetworkCapabilities(network) } returns null

        val monitor = NetworkMonitor(context)
        assertFalse(monitor.isOnline.value)
    }

    @Test
    fun `isOnline is true when network has internet and is validated`() {
        val network = mockk<Network>()
        val capabilities = mockk<NetworkCapabilities> {
            every { hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) } returns true
            every { hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) } returns true
        }
        every { connectivityManager.activeNetwork } returns network
        every { connectivityManager.getNetworkCapabilities(network) } returns capabilities

        val monitor = NetworkMonitor(context)
        assertTrue(monitor.isOnline.value)
    }

    @Test
    fun `isOnline is false when network has internet but is not validated`() {
        val network = mockk<Network>()
        val capabilities = mockk<NetworkCapabilities> {
            every { hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) } returns true
            every { hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) } returns false
        }
        every { connectivityManager.activeNetwork } returns network
        every { connectivityManager.getNetworkCapabilities(network) } returns capabilities

        val monitor = NetworkMonitor(context)
        assertFalse(monitor.isOnline.value)
    }
}
