# 07 — Mobil Uygulama

İki ayrı native uygulama. Ortak backend, ortak tasarım dili, ayrı kod tabanları.

- **iOS:** Swift + SwiftUI
- **Android:** Kotlin + Jetpack Compose

iOS önce geliştirilir (Faz 3), Android sonra (Faz 4).

---

## Navigasyon Yapısı

```
App Başlangıcı
│
├── Onboarding Flow (ilk kurulum, bir kez)
│   ├── WelcomeView          ← Ürün tanıtımı, 3 ekran
│   ├── ProfileSetupView     ← İsim + fotoğraf
│   └── QuestionsView        ← 7 kişiselleştirme sorusu → Mem0'a seed
│
├── Auth Flow (giriş yapılmamışsa)
│   ├── LoginView
│   └── RegisterView
│
└── Ana Uygulama (giriş yapılmışsa)
    ├── Tab 1: HomeView          ← Karakterler grid'i (karakter = sohbet)
    ├── Tab 2: MemoriesView      ← Karakter bazında memory listesi
    └── Tab 3: ProfileView       ← Tercihler + hesap
        └── ChatView             ← Karaktere tıklayınca açılır (push/modal)
```

---

## Ekran Detayları

### WelcomeView
- 3 ekranlık swipe animasyonu (TabView / ViewPager2)
- Her ekranda: başlık, kısa açıklama, görsel animasyon (Lottie)
- Son ekranda "Get Started" CTA

### QuestionsView
- Her soru tam ekran kart, swipe ile geçiş
- Serbest metin + "Skip" seçeneği
- İlerleme göstergesi (2/7, 3/7…)
- Tamamlanınca tüm yanıtlar backend'e → Mem0'a seed memory eklenir

### HomeView
- Üstte: Günlük özet kartı (varsayılan karakter sabah kısa mesaj üretir)
- Orta/Ana: Karakter grid'i (avatar + isim + son mesaj önizlemesi + zaman)
- Karaktere tıklamak = doğrudan o karakterin sohbetine girmek (devam eder)
- Yeni karakter ekleme: karakter grid'inin sonunda "+ Karakter ekle" butonu
- "Yeni konuşma başlat" butonu yok — her karakter zaten tek sürekli sohbet

### ChatView
- Bubble tabanlı mesaj görünümü (kullanıcı sağ, AI sol)
- SSE stream: kelime kelime akış, doğal hissettiriyor
- AI mesajlarında Markdown render
- "Yazıyor..." animasyonu (3 nokta bounce)
- Üst bar: aktif karakter adı + avatarı, tıklayınca karakter değiştir
- Alt input: metin girişi + [fotoğraf] [ses] butonları (Faz 5)
- Infinite scroll yukarı: eski mesajlar lazy load
- Uzun basınca: kopyala

### MemoriesView
- Karakter seçici (segment control)
- Her karakter için ayrı memory listesi
- Kategorilere göre gruplama (Fitness, Beslenme, Kişilik…)
- Swipe to delete + onay alert

### ProfileView
- Profil fotoğrafı + isim + düzenleme
- Bildirim tercihleri (karakter bazında toggle)
- Timezone seçimi
- Partner bağlantısı
- Hesap: şifre değiştir, tüm verileri export (JSON), hesap sil

---

## iOS — Teknoloji ve Kütüphaneler

### Core

| Teknoloji | Kullanım |
|-----------|---------|
| **SwiftUI** | Tüm UI |
| **@Observable** (iOS 17+) | State management |
| **Swift Concurrency** (async/await) | Tüm async operasyonlar |
| **Combine** | SSE stream (URLSession + AsyncStream) |
| **NavigationStack** | Ekran navigasyonu + deep link |

### Networking & API

| Kütüphane | Kullanım |
|-----------|---------|
| `URLSession` | HTTP requests + SSE streaming |
| `Codable` | JSON encode/decode |
| Custom SSE parser | `data:` event satırlarını parse eder |

### Platform APIs (native, SDK gerektirmez)

| API | Kullanım |
|-----|---------|
| `EventKit` | Takvim okuma/yazma |
| `UNUserNotificationCenter` | Local alarm notifications |
| `AVAudioRecorder` | Ses kaydı (Faz 5) |
| `AVPlayer` | Ses oynatma / TTS (Faz 5) |
| `PHPickerViewController` | Fotoğraf seçimi |
| `CoreLocation` | Timezone belirleme |

### Third-party

| Kütüphane | Kullanım |
|-----------|---------|
| Firebase iOS SDK | FCM push notifications |
| AWS Amplify iOS (Cognito) | Authentication |
| Kingfisher | Network image caching |
| Lottie iOS | Animasyonlar (onboarding, empty states) |
| swift-markdown | AI yanıtlarında Markdown render |
| Ready Player Me SDK (Faz 3) | 3D avatar — değerlendiriliyor |

### State Management Pattern

```swift
// @Observable ile basit, modern state
@Observable class ChatViewModel {
    var messages: [Message] = []
    var isStreaming = false

    func sendMessage(_ text: String) async {
        // SSE stream ile AI yanıtı al
        for await chunk in apiService.streamMessage(text) {
            messages[messages.endIndex - 1].content += chunk
        }
    }
}
```

---

## Android — Teknoloji ve Kütüphaneler

### Core

| Teknoloji | Kullanım |
|-----------|---------|
| **Jetpack Compose** | Tüm UI |
| **ViewModel + StateFlow** | State management |
| **Kotlin Coroutines** | Async operasyonlar |
| **Navigation Compose** | Ekran navigasyonu + deep link |

### Networking & API

| Kütüphane | Kullanım |
|-----------|---------|
| OkHttp | HTTP requests |
| Retrofit | API client (type-safe) |
| Custom SSE EventListener | OkHttp üzerinde SSE |

### Platform APIs

| API | Kullanım |
|-----|---------|
| `CalendarContract` | Takvim okuma/yazma |
| `AlarmManager` | Exact alarms (Android 12+) |
| `AudioRecord` / `MediaRecorder` | Ses kaydı (Faz 5) |
| `ExoPlayer` (Media3) | Ses oynatma / TTS (Faz 5) |
| `ActivityResultContracts.PickVisualMedia` | Fotoğraf seçimi |
| `CallLog.Calls` ContentProvider | Telefon araması takibi |

### Third-party

| Kütüphane | Kullanım |
|-----------|---------|
| Firebase Android SDK | FCM push notifications |
| AWS Amplify Android (Cognito) | Authentication |
| Coil | Network image caching |
| Lottie Android | Animasyonlar |
| Markwon | AI yanıtlarında Markdown render |
| Ready Player Me SDK (Faz 3) | 3D avatar — değerlendiriliyor |

### State Management Pattern

```kotlin
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val repository: ChatRepository
) : ViewModel() {

    val messages = MutableStateFlow<List<Message>>(emptyList())
    val isStreaming = MutableStateFlow(false)

    fun sendMessage(text: String) = viewModelScope.launch {
        repository.streamMessage(text).collect { chunk ->
            // SSE chunk'larını mesaja ekle
        }
    }
}
```

---

## SSE Streaming Implementasyonu

### iOS (URLSession + AsyncStream)

```swift
func streamMessage(_ text: String) -> AsyncStream<String> {
    AsyncStream { continuation in
        let task = URLSession.shared.dataTask(with: request) { data, _, _ in
            // data: {"type":"chunk","content":"..."} parse et
            continuation.yield(chunk)
        }
        task.resume()
    }
}
```

### Android (OkHttp EventSource)

```kotlin
val eventSource = OkHttpClient().newEventSource(request, object : EventSourceListener() {
    override fun onEvent(source: EventSource, id: String?, type: String?, data: String) {
        // JSON parse et, StateFlow'a emit et
    }
})
```

---

## 3D Avatar

**Öneri: Ready Player Me SDK** (iOS + Android native SDK mevcut, ücretsiz tier var)

Kullanıcı onboarding sırasında kendi avatarını özelleştirir: saç, yüz, kıyafet.
Chat ekranında küçük animasyonlu avatar gösterilir: idle, talking, happy, thinking.

**Durum:** Faz 3'e alındı.
- Ready Player Me SDK entegrasyonu değerlendirilecek
- Alternatif: SceneKit/Reality Composer ile custom model (daha küçük app boyutu)
- Minimum viable: 2D Lottie animasyon (basit, çalışır, 3D sonraya)

---

## Push Notification Davranışı

**iOS:**
- Push izni ilk chat oturumu bittikten sonra context'li sorulur
- Bildirim gelince: banner → tıkla → deep link ile chat açılır
- FCM token her açılışta backend'e güncellenir

**Android:**
- API 33+ (Android 13+): runtime permission gerekli
- API 32 ve altı: otomatik
- FCM aynı şekilde çalışır

---

## Shared Conventions

İki uygulama aynı API sözleşmesini (04-veri-api.md) ve tasarım sistemini (14-tasarim.md) kullanır.

**Renk sabitleri, spacing, tipografi** iOS'ta `Assets.xcassets` + `Constants.swift`,
Android'de `colors.xml` + `Theme.kt` + `Dimens.kt` olarak tutulur.

Her iki uygulama için string lokalizasyonu:
- iOS: `Localizable.strings`
- Android: `strings.xml`
- Diller: `en` (varsayılan), `tr` (Faz 10)
