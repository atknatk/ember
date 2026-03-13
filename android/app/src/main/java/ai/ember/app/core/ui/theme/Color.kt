package ai.ember.app.core.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color

// Brand
val EmberPrimary = Color(0xFF5B4FE8)
val EmberPrimaryPressed = Color(0xFF4B3FD8)
val EmberPrimaryHover = Color(0xFF6B5FF8)
val EmberAccent = Color(0xFFFF6B6B)

// Backgrounds
val EmberBackground = Color(0xFF0F0F14)
val EmberSurface = Color(0xFF1A1A24)
val EmberSurface2 = Color(0xFF22223A)
val EmberSurface3 = Color(0xFF2C2C4A)

// Text
val EmberTextPrimary = Color(0xFFF0F0F8)
val EmberTextSecondary = Color(0xFF9090B0)
val EmberTextDisabled = Color(0xFF5A5A7A)

// Status
val EmberSuccess = Color(0xFF4CAF87)
val EmberWarning = Color(0xFFF5A623)
val EmberError = Color(0xFFE85B5B)

// Gradients
val EmberGradientStart = Color(0xFF5B4FE8)
val EmberGradientEnd = Color(0xFFFF6B6B)
val EmberAIBubbleStart = Color(0xFF1E1E35)
val EmberAIBubbleEnd = Color(0xFF252545)

val EmberDarkColorScheme = darkColorScheme(
    primary = EmberPrimary,
    onPrimary = Color.White,
    primaryContainer = EmberPrimaryPressed,
    secondary = EmberAccent,
    onSecondary = Color.White,
    background = EmberBackground,
    onBackground = EmberTextPrimary,
    surface = EmberSurface,
    onSurface = EmberTextPrimary,
    surfaceVariant = EmberSurface2,
    onSurfaceVariant = EmberTextSecondary,
    error = EmberError,
    onError = Color.White,
    outline = EmberTextDisabled,
)
