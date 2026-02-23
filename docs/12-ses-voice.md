# 12 — Ses ve Sesli Yanıt

## Genel Bakış

İki ayrı ses özelliği vardır ve bağımsız geliştirilebilir:

| Özellik | Yön | Teknoloji | Faz |
|---------|-----|-----------|-----|
| **STT** — Sesli mesaj (async) | Kullanıcı → AI | Whisper (batch) | **Faz 5** |
| **TTS** — Sesli yanıt (async) | AI → Kullanıcı | ElevenLabs Flash / Polly | **Faz 5** |
| **Gerçek zamanlı sesli arama** | İki yönlü | LiveKit + Deepgram + ElevenLabs | **Faz 12** |

> **Önemli:** OpenAI Whisper **gerçek zamanlı streaming desteklemez** — batch-only modeldir.
> Async sesli mesajlar (WhatsApp tarzı) için uygundur. Gerçek zamanlı için Deepgram Nova-3
> kullanılır — bkz. [17-gercek-zamanli-ses.md](17-gercek-zamanli-ses.md).

---

## STT — Konuşmadan Metne (Sesli Mesaj)

### Akış

```
Kullanıcı mikrofona basar (basılı tut)
    ↓
iOS: AVAudioRecorder ile kayıt (M4A/AAC, max 2 dakika)
Android: AudioRecord / MediaRecorder ile kayıt
    ↓
Ses dosyası S3'e yüklenir (presigned URL)
    ↓
Backend → OpenAI Whisper API'ye gönderilir (auto-detect language)
    ↓
Dönen metin → ChatScreen'e metin olarak eklenir
    ↓
Normal mesaj akışı devam eder
```

### Provider Karşılaştırması

| Provider | Dil Desteği | Maliyet | Gecikme | Streaming |
|----------|-------------|---------|---------|-----------|
| **OpenAI Whisper** | 99+ dil, auto-detect | $0.006/dak | ~1-2 sn | Hayır (batch) |
| Deepgram Nova-3 | 36+ dil (`tr` dahil) | $0.0077/dak | < 300ms | **Evet** (gerçek zamanlı için) |
| AWS Transcribe | İyi | $0.024/dak | ~2-3 sn | Hayır |

**Tercih (async):** OpenAI Whisper — auto language detection, en ucuz.
**Tercih (real-time, Faz 12):** Deepgram Nova-3 — bkz. [17-gercek-zamanli-ses.md](17-gercek-zamanli-ses.md).

### Maliyet Hesabı

- Ortalama sesli mesaj: 30 saniye
- 10 sesli mesaj/gün → 5 dakika/gün
- Whisper: 5 dk × $0.006 = $0.030/kullanıcı/gün = $0.90/kullanıcı/ay

---

## TTS — Metinden Konuşmaya (Sesli Yanıt)

### Akış

```
AI metin yanıtını üretir (SSE stream tamamlanır)
    ↓
Kullanıcı mesaj balonundaki "sesli dinle" butonuna basar
    ↓
Backend → TTS provider'a metin gönderilir
    ↓
Ses dosyası S3'e kaydedilir (MP3)
    ↓
S3 URL uygulamaya döner
    ↓
iOS: AVPlayer ile oynatılır
Android: ExoPlayer (Media3) ile oynatılır
    ↓
Hız ayarı: 0.75x / 1x / 1.25x / 1.5x
```

Alternatif akış: Ses otomatik başlar (kullanıcı tercihi olarak ayarlanabilir).

---

## TTS Provider Karşılaştırması

### ElevenLabs Flash v2.5 — Önerilen

**Model:** Flash v2.5 (Multilingual) — 135ms time-to-first-audio, Türkçe dahil çok dil.

| Plan | Karakter/ay | Aylık Ücret | Karakter Ücreti |
|------|-------------|-------------|----------------|
| Free | 10.000 | $0 | — |
| Starter | 30.000 | $5 | $0.30/1k ekstra |
| Creator | 100.000 | $22 | $0.30/1k ekstra |
| Pro | 500.000 | $99 | $0.24/1k ekstra |

Flash v2.5 = 0.5 kredi/karakter (standart modelin yarısı fiyat).

| Kullanım | Karakter/ay | Plan | Maliyet |
|----------|------------|------|---------|
| 5 TTS/gün | 45.000/ay | Creator | $22/ay (sabit, ~100 kullanıcıya yeter) |
| 10 TTS/gün | 90.000/ay | Creator | $22/ay |
| 15 TTS/gün | 135.000/ay | Creator + ekstra | ~$31/ay |

---

### AWS Polly — Yedek / Kısa Metinler

**Ses:** Burcu Neural — AWS'nin Türkçe Neural sesi.
**Hibrit strateji:** < 150 karakter → Polly (hızlı, ucuz), ≥ 150 karakter → ElevenLabs.

| Kullanım | Karakter/ay | Maliyet |
|----------|------------|---------|
| Neural TTS | $16.00 / 1M karakter | — |
| Kısa mesajlar < 150 char, 10 gün, 100 kullanıcı | ~15M karakter/ay | ~$240/ay |

**Not:** Polly sadece kısa onay mesajları için kullanılır ("Tamam, kaydettim!").

---

## Kullanıcı Başına Aylık Tahmini Ses Maliyeti

| Senaryo | TTS Maliyet | STT Maliyet | Toplam |
|---------|-------------|-------------|--------|
| Hafif kullanım (3 TTS + 2 STT/gün) | $0.13 | $0.36 | **$0.49** |
| Orta kullanım (5 TTS + 5 STT/gün) | $0.22 | $0.90 | **$1.12** |
| Yoğun kullanım (10 TTS + 10 STT/gün) | $0.44 | $1.80 | **$2.24** |

---

## Native Implementasyon

### iOS

**Ses kaydı (STT için):**

```swift
import AVFoundation

class AudioRecorder: NSObject, AVAudioRecorderDelegate {
    private var recorder: AVAudioRecorder?

    func startRecording() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .default)
        try session.setActive(true)

        let url = FileManager.default.temporaryDirectory.appendingPathComponent("voice.m4a")
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: 44100,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        recorder = try AVAudioRecorder(url: url, settings: settings)
        recorder?.record()
    }

    func stopRecording() -> URL? {
        recorder?.stop()
        return recorder?.url
    }
}
```

**Ses oynatma (TTS için):**

```swift
import AVFoundation

class AudioPlayer {
    private var player: AVPlayer?

    func play(url: URL, rate: Float = 1.0) {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default)
        try? session.setActive(true)

        player = AVPlayer(url: url)
        player?.rate = rate
        player?.play()
    }
}
```

**Gerekli izinler:**
```xml
<!-- Info.plist -->
<key>NSMicrophoneUsageDescription</key>
<string>Record voice messages for your AI companion</string>
```

### Android

**Ses kaydı (STT için):**

```kotlin
class AudioRecorder {
    private var mediaRecorder: MediaRecorder? = null
    private val outputFile = File(context.cacheDir, "voice.m4a")

    fun startRecording() {
        mediaRecorder = MediaRecorder(context).apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setOutputFile(outputFile.absolutePath)
            prepare()
            start()
        }
    }

    fun stopRecording(): File {
        mediaRecorder?.stop()
        mediaRecorder?.release()
        mediaRecorder = null
        return outputFile
    }
}
```

**Ses oynatma (TTS için):**

```kotlin
// build.gradle.kts: implementation("androidx.media3:media3-exoplayer:1.x.x")
class AudioPlayer(context: Context) {
    private val player = ExoPlayer.Builder(context).build()

    fun play(url: String, rate: Float = 1.0f) {
        player.setMediaItem(MediaItem.fromUri(url))
        player.playbackParameters = PlaybackParameters(rate)
        player.prepare()
        player.play()
    }

    fun release() = player.release()
}
```

**Gerekli izinler:**
```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
```

---

## UI Bileşenleri

**Mesaj balonu — TTS oynatıcı:**

```
┌──────────────────────────────────────┐
│ AI: "Bugün harika bir antrenman      │
│  yaptın! Squat PR'ını kırdın."       │
│                                      │
│  ▶ 0:08  ─────────●────────  0:23   │
│  0.75x  1x  1.25x  1.5x             │
└──────────────────────────────────────┘
```

**Ses gönderme butonu (chat input):**

```
[ Mesaj yaz...  ] [🎤] [📷] [➤]
                   ↑
             Basılı tut → kayıt başlar
             Bırak → gönderilir
             Yukarı sürükle → iptal
```

---

## Platform Kısıtları

**iOS:**
- Mikrofon izni: `NSMicrophoneUsageDescription` Info.plist
- Arka planda kayıt: `audio` background mode (`UIBackgroundModes`)
- Audio session: `.record` (kayıt) / `.playback` (oynatma) kategorisi

**Android:**
- İzinler: `RECORD_AUDIO` (runtime, API 23+)
- `AndroidManifest.xml`'e izin eklenmeli
