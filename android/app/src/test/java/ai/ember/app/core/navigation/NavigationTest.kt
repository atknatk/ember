package ai.ember.app.core.navigation

import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * Unit tests for navigation routes and bottom tab definitions.
 */
class NavigationTest {

    // -- Screen routes --

    @Test
    fun `home screen route is home`() {
        assertEquals("home", Screen.Home.route)
    }

    @Test
    fun `memories screen route is memories`() {
        assertEquals("memories", Screen.Memories.route)
    }

    @Test
    fun `profile screen route is profile`() {
        assertEquals("profile", Screen.Profile.route)
    }

    @Test
    fun `all screen routes are unique`() {
        val routes = listOf(Screen.Home.route, Screen.Memories.route, Screen.Profile.route)
        assertEquals(routes.size, routes.toSet().size)
    }

    // -- Bottom tabs --

    @Test
    fun `bottom tab count is 3`() {
        assertEquals(3, BottomTab.entries.size)
    }

    @Test
    fun `bottom tab order is Home Memories Profile`() {
        val tabs = BottomTab.entries
        assertEquals(BottomTab.HOME, tabs[0])
        assertEquals(BottomTab.MEMORIES, tabs[1])
        assertEquals(BottomTab.PROFILE, tabs[2])
    }

    @Test
    fun `each tab maps to correct screen`() {
        assertEquals(Screen.Home, BottomTab.HOME.screen)
        assertEquals(Screen.Memories, BottomTab.MEMORIES.screen)
        assertEquals(Screen.Profile, BottomTab.PROFILE.screen)
    }

    @Test
    fun `each tab has distinct selected and unselected icons`() {
        BottomTab.entries.forEach { tab ->
            assertNotEquals(
                tab.selectedIcon,
                tab.unselectedIcon,
                "Tab ${tab.name} should have different selected and unselected icons",
            )
        }
    }

    @Test
    fun `each tab has valid label resource id`() {
        BottomTab.entries.forEach { tab ->
            assertTrue(
                tab.labelResId != 0,
                "Tab ${tab.name} should have a non-zero label resource id",
            )
        }
    }

    @Test
    fun `each tab has valid content description resource id`() {
        BottomTab.entries.forEach { tab ->
            assertTrue(
                tab.contentDescriptionResId != 0,
                "Tab ${tab.name} should have a non-zero content description resource id",
            )
        }
    }
}
