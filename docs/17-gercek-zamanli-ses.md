# 17 — Gerçek Zamanlı Sesli Arama

Telefonu kaldırıp konuşmak gibi hissettiren AI sesli arama özelliği.
Sen konuşuyorsun → STT anında yazıya çeviriyor → AI işliyor → TTS sesle konuşuyor.
Hedef round-trip: **< 1 saniye**

**Faz:** Yol haritasının Post-Launch bölümünde (Faz 12). Değerlendirme süreci başlatıldı.

---

## Async Sesli Mesaj vs Gerçek Zamanlı Arama Farkı

| Özellik | Async Sesli Mesaj (Faz 5) | Gerçek Zamanlı Arama (Faz 12) |
|---------|--------------------------|-------------------------------|
| Hissiyat | WhatsApp sesli not gibi | Gerçek telefon görüşmesi gibi |
| Akış | Kes → işle → yanıt gel | Sürekli iki yönlü akış |
| Gecikme | 3-10 saniye kabul edilir | < 1 saniye hedef |
| Teknoloji | Whisper (batch) + ElevenLabs | WebRTC + Deepgram streaming + ElevenLabs Flash |
| Maliyet/dak | ~$0.01 | ~$0.044-0.076 |
| Karmaşıklık | Basit (HTTP upload/download) | Yüksek (WebRTC, VAD, echo cancellation) |

---

## Mimari Seçenekler

### Seçenek A — OpenAI Realtime API (`gpt-4o-realtime`)

Tek model; STT + LLM + TTS hepsini tek geçişte hallediyor.

```
Mobil ─── WebRTC ──▶ OpenAI Realtime API ──▶ Mobil
         PCM audio      STT+LLM+TTS         Streamed audio
```

| Ölçüt | Değer |
|-------|-------|
| Gecikme | ~350-600ms end-to-end |
| Türkçe kalite | Belgelenmemiş (risk var) |
| Maliyet/dak | ~$0.30 (gpt-4o) / ~$0.09 (mini) |
| Karmaşıklık | Düşük — tek API |
| Kontrol | Yok — tüm pipeline OpenAI'da |

### Seçenek B — Özel Pipeline (Deepgram → Claude → ElevenLabs)

Her bileşen en iyi seçenek, tüm pipeline kontrolümüzde.

```
Mobil ─── LiveKit ──▶ Deepgram Nova-3 ──▶ Claude Haiku ──▶ ElevenLabs Flash ──▶ Mobil
         WebRTC       STT (~250ms)         LLM (~300ms)     TTS (~135ms TTFA)    audio
```

| Ölçüt | Değer |
|-------|-------|
| Gecikme | ~700-900ms end-to-end |
| Türkçe kalite | Mükemmel (Deepgram Nova-3 TR + ElevenLabs TR) |
| Maliyet/dak | ~$0.044-0.076 (LLM seçimine göre) |
| Karmaşıklık | Yüksek — 4 servis orkestrasyonu |
| Kontrol | Tam — her bileşen değiştirilebilir |

### Seçenek C — LiveKit Agents (Seçenek B üzerinde orkestrasyon katmanı)

Seçenek B'nin tüm avantajları + VAD, kesme algılama, tur yönetimi otomatik.

> **Karar: Seçenek C** — LiveKit Agents + Deepgram + Claude + ElevenLabs

---

## Karar: Mimari

```
┌─────────────┐  WebRTC (LiveKit Swift/Android SDK)  ┌─────────────────────────────────┐
│  iOS/Android │◄─────────────────────────────────────►│     LiveKit Cloud Room          │
│  (kullanıcı) │                                       │                                 │
└─────────────┘                                       │  ┌───────────────────────────┐  │
                                                      │  │  LiveKit Agents (Python)  │  │
                                                      │  │                           │  │
                                                      │  │  VoicePipelineAgent:      │  │
                                                      │  │  ┌─────────────────────┐  │  │
                                                      │  │  │ VAD: Silero on-srv  │  │  │
                                                      │  │  │ STT: Deepgram Nova-3│  │  │
                                                      │  │  │ LLM: Claude Haiku   │  │  │
                                                      │  │  │ TTS: ElevenLabs Fls │  │  │
                                                      │  │  └─────────────────────┘  │  │
                                                      │  └───────────────────────────┘  │
                                                      └─────────────────────────────────┘
```

---

## Bileşen Kararları

### Transport: LiveKit Cloud

- **Neden LiveKit:** Open source (self-host mümkün), Python Agents framework, native Swift+Kotlin SDK
- **Neden LiveKit Cloud (başlangıçta):** TURN/STUN/ICE altyapısını kendin kurma zorunluluğu yok
- **Plan:** Ship ($50/ay) — 150K bağlantı dakikası/ay
- **Self-host:** Ölçeklenince LiveKit server'ı kendi ECS Fargate'e alırız → sıfır transport maliyeti

| Plan | Fiyat | Bağlantı dak/ay | Eş zamanlı |
|------|-------|-----------------|-----------|
| Build | Ücretsiz | 5,000 | 100 |
| Ship | $50/ay | 150,000 | 1,000 |
| Scale | $500/ay | 1.5M | Sınırsız |
| Fazla kullanım | ~$0.005/dak | — | — |

### STT: Deepgram Nova-3 (`tr`)

- **Neden Deepgram:** Türkçe'ye resmi destek (Eylül 2025), gerçek streaming (Whisper batch-only)
- **Neden Nova-3:** %6.84 WER streaming, < 300ms gecikme
- **Dil kodu:** `tr` (Turkish)
- **Fiyat:** $0.0077/dak (Pay-As-You-Go) / $0.0065/dak (Growth)

> **Not:** OpenAI Whisper gerçek zamanlı streaming DESTEKLEMİYOR.
> Whisper batch modeldir — chunk'lara bölmek gerekir → 500ms+ gecikme + dikiş artifaktları.
> Realtime için Deepgram kullan. Whisper yalnızca async sesli mesajlar (Faz 5) için geçerli.

| STT Seçeneği | Türkçe | Gecikme | Fiyat/dak | Gerçek Streaming |
|---|---|---|---|---|
| Deepgram Nova-3 | Evet | < 300ms | $0.0077 | Evet |
| AssemblyAI Universal | **Hayır** | 300ms | $0.0025 | Evet |
| OpenAI Whisper | Evet | 500ms+ | $0.006 | **Hayır** (batch) |
| OpenAI Realtime API | Dolaylı | ~300ms | $0.06 | Evet |

### LLM: Claude 3.5 Haiku (streaming)

- Mevcut AI altyapımızla tutarlı
- Sesli konuşmada kısa yanıtlar yeterli → Haiku ideal
- Mem0 memory'den bağlam sistemi promptuna eklenir (normal chat gibi)
- **Streaming:** İlk token gelmesiyle TTS başlar (latency azaltır)

### TTS: ElevenLabs Flash v2.5

- **Neden Flash v2.5:** 135ms time-to-first-audio (TTFA), Türkçe sesler mevcut, WebSocket API
- **Neden ElevenLabs (Cartesia değil):** Cartesia Türkçe desteklemiyor (2026 başı itibarıyla)
- **Latency optimization level:** 3 (production için önerilen)
- **Fiyat:** ~$0.05/1K karakter (Flash v2.5 = 0.5 kredi/karakter)

| TTS Seçeneği | Türkçe | TTFA | Fiyat/1K char | WebSocket |
|---|---|---|---|---|
| ElevenLabs Flash v2.5 | Evet | ~135ms | ~$0.05 | Evet |
| Cartesia Sonic 3 | **Hayır** | ~40-95ms | ~$0.038 | Evet |
| AWS Polly Neural | Evet | ~300-500ms | ~$0.004 | Evet |

### VAD: Silero VAD (On-Device)

Kullanıcının konuşup konuşmadığını tespit etmek için ses aktivitesi algılama.

- **Neden Silero:** %87.7 TPR (WebRTC VAD'ın %50'sine karşı), on-device ONNX Runtime
- **Avantaj:** Boş ses iletimini önler → Deepgram maliyeti azalır
- iOS: `ios-vad` kütüphanesi (Silero + WebRTC VAD + YAMNet destekli)
- Android: `android-vad` kütüphanesi

| VAD | TPR (%5 FPR) | Ağırlık | Tür |
|-----|-------------|---------|-----|
| WebRTC VAD | %50 | Çok küçük | Sinyal işleme |
| **Silero VAD** | **%87.7** | Küçük | DNN (ONNX) |
| Cobra (Picovoice) | %98.9 | Orta | DNN (ücretli) |

### Echo Cancellation & Noise Suppression

- **iOS:** `AVAudioSession` + `.voiceChat` modu → donanım seviyesi AEC
- **Android:** `AcousticEchoCanceler.create()` + `NoiseSuppressor`
- **LiveKit SDK:** Her iki platformda WebRTC AEC3'ü otomatik devreye alıyor

---

## Gecikme Analizi

```
Kullanıcı konuşmayı bitirir
        │
        ▼  ~50ms
Silero VAD konuşma bitişini algılar
        │
        ▼  ~40-70ms (WebRTC transport)
Deepgram Nova-3 son transcript'ı üretir  ~250ms
        │
        ▼
Claude Haiku ilk token'ı yayınlar        ~200-400ms
        │
        ▼  (pipeline: LLM token'ları TTS'e akar)
ElevenLabs Flash ilk audio chunk         ~135ms
        │
        ▼  ~40-70ms (WebRTC transport geri)
Kullanıcı AI'ı duyar
```

**Toplam tahmini gecikme: 715-975ms** (genellikle ~800ms)

Endüstri eşiği: 800ms kabul edilebilir. 1.5 saniye üstü deneyimi bozar.

---

## Maliyet Analizi

### Bileşen başına maliyet (10 dakikalık görüşme)

| Bileşen | Birim fiyat | 10 dak maliyet |
|---------|-------------|----------------|
| LiveKit transport | $0.005/dak × 2 katılımcı | $0.10 |
| Deepgram Nova-3 (10 dak) | $0.0077/dak | $0.077 |
| Claude Haiku (~2K input + 800 output token/dak) | ~$0.008/dak | $0.08 |
| ElevenLabs Flash v2.5 (AI 5 dak konuşur, ~150 char/sn) | ~$0.023/dak | $0.23 |
| **Toplam** | | **~$0.487 / 10 dak = ~$0.049/dak** |

### Claude Sonnet ile (daha kaliteli LLM):

| Bileşen | 10 dak maliyet |
|---------|----------------|
| LiveKit + Deepgram + ElevenLabs (aynı) | $0.41 |
| Claude Sonnet (~$0.04/dak) | $0.40 |
| **Toplam** | **~$0.81 / 10 dak = ~$0.081/dak** |

### OpenAI Realtime API ile karşılaştırma:

| Mimari | Gecikme | Türkçe Kalite | Maliyet/dak |
|--------|---------|---------------|-------------|
| LiveKit + Deepgram + Claude Haiku + ElevenLabs | ~800ms | Mükemmel | ~$0.049 |
| LiveKit + Deepgram + Claude Sonnet + ElevenLabs | ~850ms | Mükemmel | ~$0.081 |
| OpenAI gpt-4o-realtime | ~400ms | Belirsiz | ~$0.30 |
| OpenAI gpt-4o-mini-realtime | ~400ms | Belirsiz | ~$0.09 |

→ Özel pipeline: OpenAI Realtime'ın **6x daha ucuzu**, Türkçe garantili.

---

## Mobil Implementasyon

### iOS — LiveKit Swift SDK

```swift
// Package: https://github.com/livekit/client-sdk-swift
import LiveKit

class VoiceCallViewModel: ObservableObject {
    private var room = Room()

    func startCall(token: String) async throws {
        try await room.connect("wss://your-livekit.livekit.cloud", token: token)
        // LiveKit Agents server-side agent otomatik odaya katılır
        // AVAudioSession .voiceChat modu SDK tarafından ayarlanır
    }

    func endCall() async {
        await room.disconnect()
    }
}
```

**Gerekli izinler:**
```xml
<!-- Info.plist -->
<key>NSMicrophoneUsageDescription</key>
<string>Voice calls with your AI companion</string>
```

**Minimum iOS sürümü:** iOS 15+ (LiveKit Swift SDK gereksinimi)

### Android — LiveKit Android SDK

```kotlin
// build.gradle.kts
implementation("io.livekit:livekit-android:2.x.x")

class VoiceCallViewModel : ViewModel() {
    private lateinit var room: Room

    fun startCall(url: String, token: String) {
        room = LiveKit.create(context)
        viewModelScope.launch {
            room.connect(url, token)
            room.localParticipant.setMicrophoneEnabled(true)
        }
    }
}
```

**Gerekli izinler:**
```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />
```

**AudioManager otomatik konfigürasyonu:** LiveKit SDK `AudioManager.MODE_IN_COMMUNICATION` modunu otomatik ayarlar (echo cancellation aktif).

---

## Backend — LiveKit Agents (Python)

```python
# backend/app/services/voice_agent.py
from livekit.agents import VoicePipelineAgent, AgentSession, JobContext
from livekit.plugins import deepgram, elevenlabs, anthropic, silero

async def entrypoint(ctx: JobContext):
    await ctx.connect()

    # Mem0'dan kullanıcı bağlamını çek
    user_id = ctx.room.metadata  # mobil taraftan gönderilir
    memories = await mem0_service.search(query="voice call context", user_id=user_id)
    system_prompt = build_system_prompt(character, memories)

    agent = VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=deepgram.STT(language="tr", model="nova-3"),
        llm=anthropic.LLM(
            model="claude-haiku-4-5-20251001",
            system=system_prompt,
        ),
        tts=elevenlabs.TTS(
            model="eleven_flash_v2_5",
            voice_id="turkish_voice_id",
            latency_optimization=3,
        ),
    )

    session = AgentSession()
    await session.start(agent, room=ctx.room)
    await session.wait()
```

**LiveKit Agents kurulumu:**
```bash
pip install livekit-agents livekit-plugins-deepgram livekit-plugins-elevenlabs livekit-plugins-anthropic livekit-plugins-silero
```

**Environment variables:**
```
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...
```

---

## Token Üretimi (Backend API)

Mobil uygulama, sesli arama başlatmadan önce backend'den LiveKit token alır:

```python
# POST /voice/token
from livekit import api

async def create_voice_token(user_id: str, character_id: str) -> str:
    token = api.AccessToken(
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ).with_grants(
        api.VideoGrants(
            room_join=True,
            room=f"voice_{user_id}_{character_id}",
            can_publish=True,
            can_subscribe=True,
        )
    ).with_metadata(user_id)  # Agent bu metadata'yı alır
    return token.to_jwt()
```

---

## Kesme Algılama (Interruption Handling)

LiveKit Agents `VoicePipelineAgent` kesme algılamayı otomatik yönetir:
- Kullanıcı AI konuşurken söz alırsa → AI durur
- TTS akışı iptal edilir (yarım kalan audio buffer temizlenir)
- Yeni STT akışı başlar

Bu özellik Replika/Kindroid'in en çok beğenilen davranışıdır — elle yazmak yerine SDK'yı kullanmak bu yüzden kritik.

---

## Premium Tier Kısıtlaması

| Tier | Sesli Arama |
|------|------------|
| Free | Yok |
| Premium ($9.99/ay) | Aylık 60 dakika |
| Premium+ (ileride) | Sınırsız |

Maliyet gerekçesi: ~$0.05/dak × 60 dak = $3/ay ek maliyet → $9.99 premium fiyatı içinde sürdürülebilir.

---

## Uygulama Süreci

**Faz 12 öncesi araştırma:**
- [ ] Deepgram Nova-3 Türkçe demo testi yap (gerçek konuşma ile WER doğrula)
- [ ] ElevenLabs Flash v2.5 Türkçe ses kalitesi değerlendirmesi
- [ ] LiveKit Cloud Build plan ile PoC yap

**Faz 12 implementasyon:**
- [ ] LiveKit Cloud hesap + proje kur
- [ ] Backend: LiveKit Agents servisi (ayrı process veya ECS task)
- [ ] `POST /voice/token` endpoint'i
- [ ] iOS: LiveKit Swift SDK + VoiceCallView
- [ ] Android: LiveKit Android SDK + VoiceCallScreen
- [ ] VAD: Silero on-device entegrasyonu (iOS + Android)
- [ ] Premium gate: aylık kullanım sayacı
- [ ] Kullanım loglaması: ses görüşmesi dakikaları `user_activity` tablosuna
- [ ] LiveKit self-host değerlendirmesi (maliyet optimizasyonu için)
