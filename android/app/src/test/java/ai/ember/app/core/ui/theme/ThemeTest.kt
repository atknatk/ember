package ai.ember.app.core.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals

/**
 * Unit tests for the Ember design system tokens.
 *
 * Verifies that all color, typography, spacing, and shape tokens
 * match the iOS design system values from Color+Ember.swift,
 * Font+Ember.swift, and CGFloat+Ember.swift.
 */
class ThemeTest {

    // -- Colors: match iOS hex values exactly --

    @Test
    fun `primary color matches iOS emberPrimary`() {
        assertEquals(Color(0xFF5B4FE8), EmberPrimary)
    }

    @Test
    fun `primary pressed color matches iOS emberPrimaryPressed`() {
        assertEquals(Color(0xFF4B3FD8), EmberPrimaryPressed)
    }

    @Test
    fun `primary hover color matches iOS emberPrimaryHover`() {
        assertEquals(Color(0xFF6B5FF8), EmberPrimaryHover)
    }

    @Test
    fun `accent color matches iOS emberAccent`() {
        assertEquals(Color(0xFFFF6B6B), EmberAccent)
    }

    @Test
    fun `background color matches iOS emberBackground`() {
        assertEquals(Color(0xFF0F0F14), EmberBackground)
    }

    @Test
    fun `surface color matches iOS emberSurface`() {
        assertEquals(Color(0xFF1A1A24), EmberSurface)
    }

    @Test
    fun `surface2 color matches iOS emberSurface2`() {
        assertEquals(Color(0xFF22223A), EmberSurface2)
    }

    @Test
    fun `surface3 color matches iOS emberSurface3`() {
        assertEquals(Color(0xFF2C2C4A), EmberSurface3)
    }

    @Test
    fun `text primary color matches iOS emberTextPrimary`() {
        assertEquals(Color(0xFFF0F0F8), EmberTextPrimary)
    }

    @Test
    fun `text secondary color matches iOS emberTextSecondary`() {
        assertEquals(Color(0xFF9090B0), EmberTextSecondary)
    }

    @Test
    fun `text disabled color matches iOS emberTextDisabled`() {
        assertEquals(Color(0xFF5A5A7A), EmberTextDisabled)
    }

    @Test
    fun `success color matches iOS emberSuccess`() {
        assertEquals(Color(0xFF4CAF87), EmberSuccess)
    }

    @Test
    fun `warning color matches iOS emberWarning`() {
        assertEquals(Color(0xFFF5A623), EmberWarning)
    }

    @Test
    fun `error color matches iOS emberError`() {
        assertEquals(Color(0xFFE85B5B), EmberError)
    }

    @Test
    fun `gradient start matches iOS emberGradientStart`() {
        assertEquals(Color(0xFF5B4FE8), EmberGradientStart)
    }

    @Test
    fun `gradient end matches iOS emberGradientEnd`() {
        assertEquals(Color(0xFFFF6B6B), EmberGradientEnd)
    }

    @Test
    fun `AI bubble start matches iOS emberAIBubbleStart`() {
        assertEquals(Color(0xFF1E1E35), EmberAIBubbleStart)
    }

    @Test
    fun `AI bubble end matches iOS emberAIBubbleEnd`() {
        assertEquals(Color(0xFF252545), EmberAIBubbleEnd)
    }

    // -- Dark Color Scheme --

    @Test
    fun `dark color scheme uses correct primary`() {
        assertEquals(EmberPrimary, EmberDarkColorScheme.primary)
    }

    @Test
    fun `dark color scheme uses correct background`() {
        assertEquals(EmberBackground, EmberDarkColorScheme.background)
    }

    @Test
    fun `dark color scheme uses correct surface`() {
        assertEquals(EmberSurface, EmberDarkColorScheme.surface)
    }

    @Test
    fun `dark color scheme uses correct error`() {
        assertEquals(EmberError, EmberDarkColorScheme.error)
    }

    @Test
    fun `dark color scheme uses correct onBackground`() {
        assertEquals(EmberTextPrimary, EmberDarkColorScheme.onBackground)
    }

    @Test
    fun `dark color scheme uses correct onSurfaceVariant`() {
        assertEquals(EmberTextSecondary, EmberDarkColorScheme.onSurfaceVariant)
    }

    // -- Typography: match iOS Font+Ember.swift sizes --

    @Test
    fun `headlineLarge matches iOS emberLargeTitle 28sp bold`() {
        assertEquals(28.sp, EmberTypography.headlineLarge.fontSize)
        assertEquals(androidx.compose.ui.text.font.FontWeight.Bold, EmberTypography.headlineLarge.fontWeight)
    }

    @Test
    fun `headlineMedium matches iOS emberTitle 22sp semibold`() {
        assertEquals(22.sp, EmberTypography.headlineMedium.fontSize)
        assertEquals(androidx.compose.ui.text.font.FontWeight.SemiBold, EmberTypography.headlineMedium.fontWeight)
    }

    @Test
    fun `titleMedium matches iOS emberHeadline 16sp semibold`() {
        assertEquals(16.sp, EmberTypography.titleMedium.fontSize)
        assertEquals(androidx.compose.ui.text.font.FontWeight.SemiBold, EmberTypography.titleMedium.fontWeight)
    }

    @Test
    fun `bodyLarge matches iOS emberBody 15sp regular`() {
        assertEquals(15.sp, EmberTypography.bodyLarge.fontSize)
        assertEquals(androidx.compose.ui.text.font.FontWeight.Normal, EmberTypography.bodyLarge.fontWeight)
    }

    @Test
    fun `bodyMedium matches iOS emberSecondary 13sp regular`() {
        assertEquals(13.sp, EmberTypography.bodyMedium.fontSize)
        assertEquals(androidx.compose.ui.text.font.FontWeight.Normal, EmberTypography.bodyMedium.fontWeight)
    }

    @Test
    fun `labelMedium matches iOS emberCaption 12sp medium`() {
        assertEquals(12.sp, EmberTypography.labelMedium.fontSize)
        assertEquals(androidx.compose.ui.text.font.FontWeight.Medium, EmberTypography.labelMedium.fontWeight)
    }

    @Test
    fun `labelSmall matches iOS emberMicro 11sp regular`() {
        assertEquals(11.sp, EmberTypography.labelSmall.fontSize)
        assertEquals(androidx.compose.ui.text.font.FontWeight.Normal, EmberTypography.labelSmall.fontWeight)
    }

    // -- Spacing: match iOS CGFloat+Ember.swift values --

    @Test
    fun `spacing xxs is 4dp`() {
        assertEquals(4.dp, EmberSpacing.xxs)
    }

    @Test
    fun `spacing xs is 8dp`() {
        assertEquals(8.dp, EmberSpacing.xs)
    }

    @Test
    fun `spacing sm is 12dp`() {
        assertEquals(12.dp, EmberSpacing.sm)
    }

    @Test
    fun `spacing md is 16dp`() {
        assertEquals(16.dp, EmberSpacing.md)
    }

    @Test
    fun `spacing lg is 20dp`() {
        assertEquals(20.dp, EmberSpacing.lg)
    }

    @Test
    fun `spacing xl is 24dp`() {
        assertEquals(24.dp, EmberSpacing.xl)
    }

    @Test
    fun `spacing xxl is 32dp`() {
        assertEquals(32.dp, EmberSpacing.xxl)
    }

    @Test
    fun `spacing xxxl is 48dp`() {
        assertEquals(48.dp, EmberSpacing.xxxl)
    }

    // -- Shapes: match iOS corner radius values --

    @Test
    fun `all shape tokens are distinct instances`() {
        assertNotEquals(EmberShapes.chip, EmberShapes.input)
        assertNotEquals(EmberShapes.input, EmberShapes.messageBubble)
        assertNotEquals(EmberShapes.messageBubble, EmberShapes.card)
        assertNotEquals(EmberShapes.card, EmberShapes.pill)
    }
}
