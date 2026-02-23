# Ember Android Coding Standards

Kotlin 2.0 / Jetpack Compose / Android API 26+

This document is the authoritative reference for all Android development on the Ember project.
Zero-memory sessions must follow every rule here without exception.

---

## Table of Contents

1. Project Structure
2. ViewModel + StateFlow + Sealed UiState Pattern
3. collectAsStateWithLifecycle
4. OkHttp + Retrofit + Kotlin Serialization
5. SSE: OkHttp EventSource
6. AWS Amplify Cognito Integration
7. Coil for Network Images
8. Material Icons
9. Dark Theme
10. Color and Typography System
11. Error Handling in Compose
12. Haptic Feedback
13. Accessibility
14. Testing: JUnit + MockK + Turbine
15. Hilt Dependency Injection

---

## 1. Project Structure

```
app/
  src/
    main/
      kotlin/ai/ember/app/
        EmberApplication.kt          # Hilt Application
        MainActivity.kt              # Single activity
        navigation/
          EmberNavHost.kt
          Screen.kt                  # Sealed route definitions
        features/
          auth/
            AuthViewModel.kt
            LoginScreen.kt
            SignUpScreen.kt
          characters/
            CharactersViewModel.kt
            CharactersScreen.kt
            CharacterCard.kt
          chat/
            ChatViewModel.kt
            ChatScreen.kt
            MessageBubble.kt
          memory/
            MemoryViewModel.kt
            MemoryScreen.kt
          settings/
            SettingsViewModel.kt
            SettingsScreen.kt
        core/
          network/
            ApiService.kt            # Retrofit interface
            ApiClient.kt             # OkHttp + Retrofit setup
            SseClient.kt             # OkHttp EventSource
            NetworkModule.kt         # Hilt module
          auth/
            AuthRepository.kt
            AuthModule.kt            # Hilt module
            TokenInterceptor.kt
          models/
            Character.kt
            Message.kt
            Conversation.kt
            Memory.kt
            Pagination.kt
          ui/
            theme/
              Color.kt
              Typography.kt
              Theme.kt
            components/
              EmberButton.kt
              AvatarImage.kt
              LoadingIndicator.kt
          utils/
            HapticUtils.kt
            CursorUtils.kt
    test/
    androidTest/
  build.gradle.kts
```

---

## 2. ViewModel + StateFlow + Sealed UiState Pattern

This is the mandatory pattern for all screens.

```kotlin
// features/chat/ChatViewModel.kt
package ai.ember.app.features.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

// Sealed UiState — one per screen
sealed interface ChatUiState {
    data object Loading : ChatUiState
    data class Success(
        val messages: List<Message>,
        val isStreaming: Boolean = false,
    ) : ChatUiState
    data class Error(val message: String) : ChatUiState
}

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val chatRepository: ChatRepository,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val characterId: String = checkNotNull(savedStateHandle["characterId"])

    private val _uiState = MutableStateFlow<ChatUiState>(ChatUiState.Loading)
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private val _inputText = MutableStateFlow("")
    val inputText: StateFlow<String> = _inputText.asStateFlow()

    init {
        loadHistory()
    }

    fun onInputChanged(text: String) {
        _inputText.value = text
    }

    fun sendMessage() {
        val content = _inputText.value.trim()
        if (content.isEmpty()) return
        _inputText.value = ""

        viewModelScope.launch {
            val currentMessages = (_uiState.value as? ChatUiState.Success)?.messages ?: emptyList()
            val userMsg = Message(role = Role.USER, content = content)

            _uiState.value = ChatUiState.Success(
                messages = currentMessages + userMsg,
                isStreaming = true,
            )

            chatRepository.streamMessage(characterId, content)
                .catch { e ->
                    _uiState.value = ChatUiState.Error(e.message ?: "Failed to send message")
                }
                .collect { chunk ->
                    val state = _uiState.value as? ChatUiState.Success ?: return@collect
                    val lastMsg = state.messages.lastOrNull()
                    if (lastMsg?.role == Role.ASSISTANT) {
                        val updated = state.messages.dropLast(1) +
                            lastMsg.copy(content = lastMsg.content + chunk)
                        _uiState.value = state.copy(messages = updated)
                    } else {
                        _uiState.value = state.copy(
                            messages = state.messages + Message(role = Role.ASSISTANT, content = chunk)
                        )
                    }
                }

            val finalState = _uiState.value as? ChatUiState.Success
            _uiState.value = finalState?.copy(isStreaming = false) ?: _uiState.value
        }
    }

    private fun loadHistory() {
        viewModelScope.launch {
            _uiState.value = ChatUiState.Loading
            chatRepository.getMessages(characterId, cursor = null, limit = 30)
                .onSuccess { page ->
                    _uiState.value = ChatUiState.Success(messages = page.items.reversed())
                }
                .onFailure { e ->
                    _uiState.value = ChatUiState.Error(e.message ?: "Failed to load messages")
                }
        }
    }
}
```

**Rules:**
- Every screen has exactly one `ViewModel`.
- Every `ViewModel` has exactly one `StateFlow<XxxUiState>`.
- `UiState` is a sealed interface with `Loading`, `Success`, and `Error` variants.
- Never expose `MutableStateFlow` — always use `asStateFlow()`.
- Use `viewModelScope.launch` for coroutines.
- `SavedStateHandle` for route arguments — no constructor parameters.

---

## 3. collectAsStateWithLifecycle

Always use `collectAsStateWithLifecycle` instead of `collectAsState`.

```kotlin
// features/chat/ChatScreen.kt
package ai.ember.app.features.chat

import androidx.compose.runtime.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun ChatScreen(
    characterId: String,
    onNavigateBack: () -> Unit,
    viewModel: ChatViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val inputText by viewModel.inputText.collectAsStateWithLifecycle()

    when (val state = uiState) {
        is ChatUiState.Loading -> LoadingIndicator()

        is ChatUiState.Success -> ChatContent(
            messages = state.messages,
            isStreaming = state.isStreaming,
            inputText = inputText,
            onInputChanged = viewModel::onInputChanged,
            onSend = viewModel::sendMessage,
        )

        is ChatUiState.Error -> ErrorMessage(
            message = state.message,
            onRetry = viewModel::loadHistory,
        )
    }
}
```

**Rules:**
- `collectAsStateWithLifecycle` stops collection when the Composable is not in the foreground — saves battery.
- Import: `androidx.lifecycle.compose.collectAsStateWithLifecycle`.
- Never use `LaunchedEffect` to collect `StateFlow` — use `collectAsStateWithLifecycle`.

---

## 4. OkHttp + Retrofit + Kotlin Serialization

```kotlin
// core/network/NetworkModule.kt
package ai.ember.app.core.network

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideJson(): Json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
        isLenient = true
    }

    @Provides
    @Singleton
    fun provideOkHttpClient(tokenInterceptor: TokenInterceptor): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(tokenInterceptor)
            .addInterceptor(
                HttpLoggingInterceptor().apply {
                    level = if (BuildConfig.DEBUG)
                        HttpLoggingInterceptor.Level.BODY
                    else
                        HttpLoggingInterceptor.Level.NONE
                }
            )
            .build()

    @Provides
    @Singleton
    fun provideRetrofit(okHttpClient: OkHttpClient, json: Json): Retrofit =
        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()

    @Provides
    @Singleton
    fun provideApiService(retrofit: Retrofit): ApiService =
        retrofit.create(ApiService::class.java)
}
```

```kotlin
// core/network/ApiService.kt
package ai.ember.app.core.network

import kotlinx.serialization.Serializable
import retrofit2.Response
import retrofit2.http.*

interface ApiService {
    @GET("characters/{characterId}/messages")
    suspend fun listMessages(
        @Path("characterId") characterId: String,
        @Query("cursor") cursor: String?,
        @Query("limit") limit: Int = 30,
    ): Response<MessagePage>

    @POST("characters/{characterId}/messages")
    suspend fun sendMessage(
        @Path("characterId") characterId: String,
        @Body body: SendMessageRequest,
    ): Response<Message>

    @GET("characters")
    suspend fun listCharacters(): Response<List<Character>>
}

@Serializable
data class SendMessageRequest(val content: String)

@Serializable
data class MessagePage(
    val items: List<Message>,
    val nextCursor: String?,
    val hasMore: Boolean,
)
```

```kotlin
// core/network/TokenInterceptor.kt
package ai.ember.app.core.network

import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

class TokenInterceptor @Inject constructor(
    private val authRepository: AuthRepository,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = runBlocking { authRepository.getAccessToken() }
        val request = chain.request().newBuilder()
            .addHeader("Authorization", "Bearer $token")
            .build()
        return chain.proceed(request)
    }
}
```

**Rules:**
- All network calls return `Response<T>` from Retrofit — check `isSuccessful` in repository layer.
- `ignoreUnknownKeys = true` prevents crashes on API additions.
- Never use `GsonConverterFactory` — Kotlin Serialization only.
- `runBlocking` in `TokenInterceptor` is intentional — OkHttp interceptors are synchronous.

---

## 5. SSE: OkHttp EventSource

```kotlin
// core/network/SseClient.kt
package ai.ember.app.core.network

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import javax.inject.Inject

class SseClient @Inject constructor(
    private val okHttpClient: OkHttpClient,
    private val tokenRepository: AuthRepository,
) {
    fun streamMessage(characterId: String, content: String): Flow<String> = callbackFlow {
        val token = runBlocking { tokenRepository.getAccessToken() }

        val requestBody = """{"content":"${content.replace("\"", "\\\"")}"}"""
            .toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("${BuildConfig.API_BASE_URL}characters/$characterId/messages/stream")
            .post(requestBody)
            .addHeader("Authorization", "Bearer $token")
            .addHeader("Accept", "text/event-stream")
            .build()

        val listener = object : EventSourceListener() {
            override fun onEvent(
                eventSource: EventSource,
                id: String?,
                type: String?,
                data: String,
            ) {
                if (data == "[DONE]") {
                    close()
                    return
                }
                try {
                    val json = Json.parseToJsonElement(data).jsonObject
                    val delta = json["delta"]?.jsonPrimitive?.content ?: return
                    trySend(delta)
                } catch (_: Exception) {}
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                close(t ?: Exception("SSE connection failed: ${response?.code}"))
            }
        }

        val factory = EventSources.createFactory(okHttpClient)
        val eventSource = factory.newEventSource(request, listener)

        awaitClose { eventSource.cancel() }
    }
}
```

**Rules:**
- SSE uses `callbackFlow` to bridge the callback-based `EventSourceListener` to a `Flow`.
- Parse `[DONE]` to close the flow cleanly.
- `awaitClose` cancels the EventSource when the collector cancels.
- Dependency: `com.squareup.okhttp3:okhttp-sse`.

---

## 6. AWS Amplify Cognito Integration

```kotlin
// core/auth/AuthModule.kt
package ai.ember.app.core.auth

import android.content.Context
import com.amplifyframework.auth.cognito.AWSCognitoAuthPlugin
import com.amplifyframework.core.Amplify
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AuthModule {

    @Provides
    @Singleton
    fun provideAuthRepository(@ApplicationContext context: Context): AuthRepository {
        return AmplifyAuthRepository(context)
    }
}
```

```kotlin
// core/auth/AmplifyAuthRepository.kt
package ai.ember.app.core.auth

import android.content.Context
import com.amplifyframework.auth.AuthException
import com.amplifyframework.auth.cognito.AWSCognitoAuthPlugin
import com.amplifyframework.auth.options.AuthSignInOptions
import com.amplifyframework.core.Amplify
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

interface AuthRepository {
    suspend fun signIn(username: String, password: String): Result<Unit>
    suspend fun signOut()
    suspend fun getAccessToken(): String
    suspend fun isSignedIn(): Boolean
}

class AmplifyAuthRepository(context: Context) : AuthRepository {

    init {
        try {
            Amplify.addPlugin(AWSCognitoAuthPlugin())
            Amplify.configure(context)
        } catch (_: Exception) {
            // Already configured
        }
    }

    override suspend fun signIn(username: String, password: String): Result<Unit> =
        suspendCoroutine { cont ->
            Amplify.Auth.signIn(
                username,
                password,
                { result ->
                    if (result.isSignedIn) cont.resume(Result.success(Unit))
                    else cont.resumeWithException(AuthException("Sign-in incomplete", ""))
                },
                { cont.resumeWithException(it) }
            )
        }

    override suspend fun signOut(): Unit = suspendCoroutine { cont ->
        Amplify.Auth.signOut { cont.resume(Unit) }
    }

    override suspend fun getAccessToken(): String = suspendCoroutine { cont ->
        Amplify.Auth.fetchAuthSession(
            { session ->
                val token = (session as? com.amplifyframework.auth.cognito.AWSCognitoAuthSession)
                    ?.accessToken?.value
                if (token != null) cont.resume(token)
                else cont.resumeWithException(AuthException("Token unavailable", ""))
            },
            { cont.resumeWithException(it) }
        )
    }

    override suspend fun isSignedIn(): Boolean = suspendCoroutine { cont ->
        Amplify.Auth.fetchAuthSession(
            { cont.resume(it.isSignedIn) },
            { cont.resume(false) }
        )
    }
}
```

---

## 7. Coil for Network Images

```kotlin
// In Composable
import coil.compose.AsyncImage
import coil.request.ImageRequest

@Composable
fun CharacterAvatar(
    imageUrl: String,
    contentDescription: String,
    size: Dp = 80.dp,
    modifier: Modifier = Modifier,
) {
    AsyncImage(
        model = ImageRequest.Builder(LocalContext.current)
            .data(imageUrl)
            .crossfade(true)
            .placeholder(R.drawable.avatar_placeholder)
            .error(R.drawable.avatar_placeholder)
            .build(),
        contentDescription = contentDescription,
        contentScale = ContentScale.Crop,
        modifier = modifier
            .size(size)
            .clip(CircleShape),
    )
}
```

**Rules:**
- Always provide `placeholder` and `error` drawables.
- Always pass `contentDescription` — never null for meaningful images.
- Use `crossfade(true)` for smooth loading transitions.
- Add Coil to Hilt if custom configuration is needed (auth headers for private images).

---

## 8. Material Icons

```kotlin
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Icon

// Outlined (default — lighter visual weight)
Icon(
    imageVector = Icons.Outlined.Settings,
    contentDescription = "Settings",
    tint = MaterialTheme.colorScheme.onSurface,
)

// Filled (active/selected state)
Icon(
    imageVector = Icons.Filled.Favorite,
    contentDescription = "Liked",
    tint = MaterialTheme.colorScheme.primary,
)

// Icon button
IconButton(onClick = { router.navigateTo(Screen.Settings) }) {
    Icon(
        imageVector = Icons.Outlined.Settings,
        contentDescription = "Open settings",
    )
}
```

**Rules:**
- Use `Outlined` by default; use `Filled` only for active/selected states.
- Always set `contentDescription` — never null except for purely decorative icons.
- Tint with `MaterialTheme.colorScheme` — never hardcoded colors.
- Define icon constants in a central `EmberIcons` object to avoid string-free accidental duplication.

---

## 9. Dark Theme

Ember is dark-first. Force dark theme at the application level.

```kotlin
// MainActivity.kt
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            EmberTheme(darkTheme = true) {
                EmberNavHost()
            }
        }
    }
}
```

```kotlin
// core/ui/theme/Theme.kt
@Composable
fun EmberTheme(
    darkTheme: Boolean = true,   // always true in production
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = EmberDarkColorScheme,
        typography = EmberTypography,
        content = content,
    )
}
```

---

## 10. Color and Typography System

```kotlin
// core/ui/theme/Color.kt
package ai.ember.app.core.ui.theme

import androidx.compose.ui.graphics.Color

// Backgrounds
val EmberBackground   = Color(0xFF0A0A0F)
val EmberSurface      = Color(0xFF141420)
val EmberCard         = Color(0xFF1E1E30)

// Brand
val EmberPrimary      = Color(0xFF7C6AF7)   // violet
val EmberAccent       = Color(0xFFE85D9A)   // rose
val EmberPrimaryContainer = Color(0xFF2D2560)

// Text
val EmberOnBackground = Color(0xFFF0F0F8)
val EmberOnSurface    = Color(0xFFF0F0F8)
val EmberTextSecondary = Color(0xFF8888AA)

// Status
val EmberSuccess      = Color(0xFF4CAF50)
val EmberError        = Color(0xFFF44336)
val EmberWarning      = Color(0xFFFF9800)
```

```kotlin
// core/ui/theme/Color.kt — dark color scheme
import androidx.compose.material3.darkColorScheme

val EmberDarkColorScheme = darkColorScheme(
    primary          = EmberPrimary,
    onPrimary        = Color.White,
    primaryContainer = EmberPrimaryContainer,
    secondary        = EmberAccent,
    background       = EmberBackground,
    surface          = EmberSurface,
    onBackground     = EmberOnBackground,
    onSurface        = EmberOnSurface,
    error            = EmberError,
)
```

```kotlin
// core/ui/theme/Typography.kt
package ai.ember.app.core.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val EmberTypography = Typography(
    displayLarge = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Bold,
        fontSize = 57.sp,
        lineHeight = 64.sp,
    ),
    headlineMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 28.sp,
        lineHeight = 36.sp,
    ),
    bodyLarge = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp,
        letterSpacing = 0.5.sp,
    ),
    bodyMedium = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    labelSmall = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 16.sp,
        letterSpacing = 0.5.sp,
    ),
)
```

**Rules:**
- All colors from `EmberDarkColorScheme` via `MaterialTheme.colorScheme`.
- All text from `EmberTypography` via `MaterialTheme.typography`.
- Never hardcode color hex values in Composables.
- Never hardcode `sp` or `dp` values outside the theme files.

---

## 11. Error Handling in Compose

```kotlin
// Pattern: show error state from UiState, or use Snackbar for transient errors

@Composable
fun ChatScreen(viewModel: ChatViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    // Transient errors via Snackbar
    LaunchedEffect(uiState) {
        if (uiState is ChatUiState.Error) {
            snackbarHostState.showSnackbar(
                message = (uiState as ChatUiState.Error).message,
                actionLabel = "Retry",
                duration = SnackbarDuration.Long,
            )
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        when (val state = uiState) {
            is ChatUiState.Loading -> Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }

            is ChatUiState.Success -> ChatContent(
                state = state,
                modifier = Modifier.padding(padding),
            )

            is ChatUiState.Error -> ErrorScreen(
                message = state.message,
                onRetry = viewModel::loadHistory,
                modifier = Modifier.padding(padding),
            )
        }
    }
}

@Composable
fun ErrorScreen(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.Outlined.ErrorOutline,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.error,
            modifier = Modifier.size(48.dp),
        )
        Spacer(Modifier.height(16.dp))
        Text(text = message, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(24.dp))
        Button(onClick = onRetry) { Text("Retry") }
    }
}
```

---

## 12. Haptic Feedback

```kotlin
// core/utils/HapticUtils.kt
package ai.ember.app.core.utils

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.HapticFeedbackConstants
import android.view.View

object HapticUtils {

    fun performClick(view: View) {
        view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
    }

    fun performLongClick(view: View) {
        view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
    }

    fun performTextHandleMove(view: View) {
        view.performHapticFeedback(HapticFeedbackConstants.TEXT_HANDLE_MOVE)
    }

    fun vibrate(context: Context, durationMs: Long = 50L) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vibratorManager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
            vibratorManager.defaultVibrator.vibrate(
                VibrationEffect.createOneShot(durationMs, VibrationEffect.DEFAULT_AMPLITUDE)
            )
        } else {
            @Suppress("DEPRECATION")
            val vibrator = context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            @Suppress("DEPRECATION")
            vibrator.vibrate(durationMs)
        }
    }
}

// Usage in Compose with LocalView
@Composable
fun SendButton(onClick: () -> Unit) {
    val view = LocalView.current
    IconButton(
        onClick = {
            view.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            onClick()
        }
    ) {
        Icon(Icons.Filled.Send, contentDescription = "Send message")
    }
}
```

---

## 13. Accessibility

```kotlin
// contentDescription on all icon-only elements
Icon(
    imageVector = Icons.Outlined.Mic,
    contentDescription = "Start voice recording",
)

// Merge semantics for compound components
Row(
    modifier = Modifier.semantics(mergeDescendants = true) {}
) {
    AsyncImage(/* ... */, contentDescription = null)  // described by Row semantics
    Column {
        Text(character.name)
        Text(character.tagline)
    }
}

// Custom semantic action
Box(
    modifier = Modifier.semantics {
        contentDescription = "Message from ${message.role}: ${message.content}"
        customActions = listOf(
            CustomAccessibilityAction("Copy message") {
                clipboardManager.setText(AnnotatedString(message.content))
                true
            }
        )
    }
)

// Font Scale — never hardcode sp values in custom components
// Always use MaterialTheme.typography.*
Text(
    text = message.content,
    style = MaterialTheme.typography.bodyLarge,
    // Do NOT do: fontSize = 16.sp
)

// Minimum touch target
IconButton(
    onClick = { /* ... */ },
    modifier = Modifier.size(48.dp),   // minimum 48dp
) {
    Icon(Icons.Outlined.Delete, contentDescription = "Delete message")
}
```

**Rules:**
- Every icon-only `Icon` or `Image` must have a non-null `contentDescription`.
- Pure decorative elements: `contentDescription = null`.
- Use `semantics(mergeDescendants = true)` for compound clickable items.
- Minimum touch target: 48dp x 48dp.
- All text must use `MaterialTheme.typography.*` — never hardcode `sp` in Composables.
- Test with TalkBack on physical device before shipping.

---

## 14. Testing: JUnit + MockK + Turbine

```kotlin
// Dependency: app/build.gradle.kts
testImplementation("io.mockk:mockk:1.13.10")
testImplementation("app.cash.turbine:turbine:1.1.0")
testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
testImplementation("junit:junit:4.13.2")
```

### ViewModel Unit Tests

```kotlin
// features/chat/ChatViewModelTest.kt
package ai.ember.app.features.chat

import app.cash.turbine.test
import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var chatRepository: ChatRepository
    private lateinit var savedStateHandle: SavedStateHandle
    private lateinit var viewModel: ChatViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        chatRepository = mockk()
        savedStateHandle = SavedStateHandle(mapOf("characterId" to "char-1"))
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `initial state is Loading`() = runTest {
        coEvery { chatRepository.getMessages(any(), any(), any()) } returns
            Result.success(MessagePage(emptyList(), null, false))

        viewModel = ChatViewModel(chatRepository, savedStateHandle)

        viewModel.uiState.test {
            val state = awaitItem()
            assertIs<ChatUiState.Success>(state)
            cancelAndIgnoreRemainingEvents()
        }
    }

    @Test
    fun `sendMessage appends user and assistant messages`() = runTest {
        coEvery { chatRepository.getMessages(any(), any(), any()) } returns
            Result.success(MessagePage(emptyList(), null, false))
        every { chatRepository.streamMessage(any(), any()) } returns
            flowOf("Hello", " there", "!")

        viewModel = ChatViewModel(chatRepository, savedStateHandle)
        viewModel.onInputChanged("Hi Ember")

        viewModel.uiState.test {
            skipItems(1)  // initial success state
            viewModel.sendMessage()
            val finalState = expectMostRecentItem()
            assertIs<ChatUiState.Success>(finalState)
            assertEquals(2, finalState.messages.size)
            assertEquals("Hi Ember", finalState.messages[0].content)
            assertEquals("Hello there!", finalState.messages[1].content)
        }
    }

    @Test
    fun `sendMessage sets error on failure`() = runTest {
        coEvery { chatRepository.getMessages(any(), any(), any()) } returns
            Result.success(MessagePage(emptyList(), null, false))
        every { chatRepository.streamMessage(any(), any()) } throws RuntimeException("Network error")

        viewModel = ChatViewModel(chatRepository, savedStateHandle)
        viewModel.onInputChanged("Hi")

        viewModel.uiState.test {
            skipItems(1)
            viewModel.sendMessage()
            val errorState = expectMostRecentItem()
            assertIs<ChatUiState.Error>(errorState)
            assertTrue(errorState.message.isNotEmpty())
        }
    }
}
```

### Repository Tests

```kotlin
// core/network/ChatRepositoryTest.kt
package ai.ember.app.core.network

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Test
import retrofit2.Response
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ChatRepositoryTest {

    private val apiService: ApiService = mockk()
    private val sseClient: SseClient = mockk()
    private val repository = ChatRepositoryImpl(apiService, sseClient)

    @Test
    fun `getMessages returns success on 200`() = runTest {
        val page = MessagePage(
            items = listOf(Message(role = Role.USER, content = "Hi")),
            nextCursor = null,
            hasMore = false,
        )
        coEvery { apiService.listMessages("char-1", null, 30) } returns Response.success(page)

        val result = repository.getMessages("char-1", null, 30)
        assertTrue(result.isSuccess)
        assertEquals(1, result.getOrNull()?.items?.size)
    }
}
```

---

## 15. Hilt Dependency Injection

```kotlin
// EmberApplication.kt
@HiltAndroidApp
class EmberApplication : Application()

// MainActivity.kt
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            EmberTheme(darkTheme = true) {
                EmberNavHost()
            }
        }
    }
}

// ViewModel
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val chatRepository: ChatRepository,
    private val savedStateHandle: SavedStateHandle,
) : ViewModel()

// Hilt Module
@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideChatRepository(
        apiService: ApiService,
        sseClient: SseClient,
    ): ChatRepository = ChatRepositoryImpl(apiService, sseClient)
}

// Composable — inject ViewModel
@Composable
fun ChatScreen(
    characterId: String,
    viewModel: ChatViewModel = hiltViewModel(),
) { /* ... */ }
```

**Rules:**
- `@HiltViewModel` + `@Inject constructor` for all ViewModels.
- `@AndroidEntryPoint` on all Activities and Fragments.
- `@HiltAndroidApp` on Application class.
- Singleton-scoped: `@InstallIn(SingletonComponent::class)`.
- ViewModel-scoped: `@InstallIn(ViewModelComponent::class)`.
- Interface bindings: use `@Binds` in abstract `@Module` classes.
- Testing: use `@UninstallModules` + `@TestInstallIn` to replace production modules.

### Test Module Pattern

```kotlin
// src/test/.../FakeNetworkModule.kt
@Module
@TestInstallIn(components = [SingletonComponent::class], replaces = [NetworkModule::class])
object FakeNetworkModule {

    @Provides
    @Singleton
    fun provideApiService(): ApiService = FakeApiService()

    @Provides
    @Singleton
    fun provideSseClient(): SseClient = FakeSseClient()
}
```
