# 03 — Sistem Mimarisi ve Teknoloji

## Genel Mimari

```
┌──────────────────────────────────────────────────────────────────┐
│                     KULLANICI CİHAZI                             │
│     iOS App (Swift + SwiftUI)  /  Android App (Kotlin + Compose) │
│   Chat │ Ses Kayıt │ Fotoğraf │ Alarm │ Takvim │ Telefon Takibi  │
└─────────────────────────┬────────────────────────────────────────┘
                          │  HTTPS + SSE (streaming)
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                   BACKEND — AWS ECS Fargate                      │
│                   Python + FastAPI                               │
│                                                                  │
│  Auth  │  Chat/SSE  │  Memories  │  Ses  │  Proactive Cron      │
└───┬────────────┬─────────────┬─────────┬──────────────┬─────────┘
    │            │             │         │              │
    ▼            ▼             ▼         ▼              ▼
 AWS          Claude        Mem0.ai   ElevenLabs    Firebase
 Cognito      Sonnet+Haiku  Memory    / AWS Polly   FCM Push
    │                          │
    ▼                          ▼
 AWS RDS                   pgvector
 PostgreSQL                (vector search)
    │
    ▼
 AWS S3
 (fotoğraf, ses)
```

---

## Veri Akışı — Mesaj Gönderme

1. iOS/Android uygulaması mesajı backend'e POST eder
2. Backend, Mem0'da semantic search yapar (ilgili memories çekilir)
3. Backend, RDS PostgreSQL'den son 20 mesajı çeker (konuşma bağlamı)
4. Sistem prompt oluşturulur: karakter + memories + cihaz bağlamı + tarih/saat
5. Claude'a istek gönderilir, yanıt SSE ile native uygulamaya stream edilir
6. Sesli yanıt istenirse: metin → ElevenLabs/Polly → ses dosyası → S3 URL → native uygulama
7. Konuşma tamamlandığında (arka planda, kullanıcı beklemez):
   - Mem0'a ekle (yeni gerçekler öğrenilir)
   - RDS'e kaydet

---

## Veri Akışı — Proaktif Bildirim

1. Cron job her 30 dakikada bir çalışır
2. Aktif tüm kullanıcılar için koşullar kontrol edilir
3. Koşul sağlanırsa: Claude Haiku ile kişiselleştirilmiş metin üretilir
4. Firebase FCM ile push notification gönderilir
5. `user_activity` tablosunda bildirim tipi işaretlenir (günde 1 kez)

---

## Teknoloji Kararları

### Native iOS + Android — Neden?

İki ayrı native uygulama: **Swift + SwiftUI** (iOS) ve **Kotlin + Jetpack Compose** (Android).

- En küçük app bundle boyutu (~20-30MB vs Flutter ~40-50MB)
- Platform-native scroll performansı (özellikle chat listesi için kritik)
- Doğrudan platform API erişimi: EventKit, CallKit, UNUserNotificationCenter, AVFoundation
- 3D avatar için SceneKit/RealityKit (iOS) ve SceneView (Android) — plugin katmanı yok
- Gerçek zamanlı sesli arama (WebRTC) ileride eklendiğinde native en temiz çözüm
- SwiftUI / Compose Multiplatform: kod paylaşımı ihtiyacı olursa seçenek

Değerlendirilen alternatifler:
- Flutter: Tek codebase ama ~15MB ek boyut, plugin katmanı, 3D avatar kısıtlı
- React Native: Bridging overhead, native API erişimi daha kısıtlı

---

### Python + FastAPI — Neden?

- Mem0.ai'ın Python SDK'sı Node.js'ten çok daha olgun ve özellik açısından zengin
- FastAPI: async/await, SSE streaming, tip güvenliği (Pydantic), otomatik API dokümantasyonu
- AWS boto3 kütüphanesi (S3, Cognito, Polly, Transcribe) Python için en iyi
- AI ekosistemi Python'da: Anthropic, OpenAI, LangChain, LlamaIndex hepsi Python-first
- Gelecekte ML/vektör işlemleri eklenirse Python en hazır dil

Değerlendirilen alternatifler:
- Node.js/TypeScript: Frontend ile aynı dil ama AI ekosistemi daha kısıtlı
- Go: Üstün performans ama AI kütüphaneleri zayıf, Mem0 Go SDK yok
- Python kazandı çünkü tüm servis SDK'ları birinci sınıf Python'da

---

### AI Model Stratejisi — Provider Bağımsız

Anthropic dahil hiçbir provider'a kilitli değiliz. Her iş için en uygun model kullanılır,
servis katmanı izole tutulur — provider değişince yalnızca servis güncellenir.

**Mevcut tercihler (değiştirilebilir):**

| İşlem | Varsayılan Model | Provider | Alternatifler |
|-------|-----------------|----------|---------------|
| Ana konuşma | claude-sonnet-4-6 | Anthropic | GPT-4o, Gemini 2.0 Flash |
| Fotoğraf analizi | claude-sonnet-4-6 | Anthropic | GPT-4o Vision, Gemini 2.0 |
| Intent sınıflandırma | claude-haiku-4-5 | Anthropic | GPT-4o mini, Gemini Flash |
| Proaktif bildirim | claude-haiku-4-5 | Anthropic | GPT-4o mini, Llama 3 (self-hosted) |
| Sistem prompt üretimi | claude-haiku-4-5 | Anthropic | GPT-4o mini |
| Real-time sesli arama | Deepgram + Claude + ElevenLabs | Multi | OpenAI Realtime API (tek provider) |
| TTS (sesli yanıt) | ElevenLabs Flash v2.5 | ElevenLabs | AWS Polly Burcu (yedek) |
| STT (sesli mesaj) | Whisper | OpenAI | Deepgram Nova-3 |
| STT (real-time) | Deepgram Nova-3 (`tr`) | Deepgram | — |

**Servis soyutlama prensibi:**

```python
# services/llm.py — provider swap: sadece bu dosya değişir
class LLMService:
    async def chat(self, messages, system_prompt) -> AsyncIterator[str]:
        # Bugün: Anthropic
        # Yarın: OpenAI, Gemini, ya da self-hosted Llama
        ...
```

Karar değiştiriciler: fiyat, kalite farkı, Türkçe performans, rate limit sorunları.
Kullanıcı fark etmez — arayüz aynı kalır.

---

### AWS Stack — Neden?

Zaten AWS altyapısı mevcut; yeni servis eklemek entegrasyon maliyeti düşürür:

| AWS Servisi | Görev | Alternatif |
|-------------|-------|-----------|
| ECS Fargate | Container hosting | EC2 (daha fazla yönetim) |
| RDS PostgreSQL + pgvector | Ana DB + vektör arama | Supabase (dış servis) |
| S3 | Dosya depolama (fotoğraf, ses) | Supabase Storage |
| Cognito | Auth (kullanıcı yönetimi) | Self-managed JWT |
| ECR | Container image registry | Docker Hub |
| CloudFront | CDN + API ön kapısı | — |
| Polly | TTS (yedek/ekonomik seçenek) | ElevenLabs |
| Transcribe | STT (yedek) | OpenAI Whisper |

---

### Mem0 — Cloud → Self-Hosted Geçiş

Detaylı bilgi için bkz. [05-ai-bellek.md](05-ai-bellek.md#self-hosted-geçiş).

Özet: Mem0 open-source, pgvector tabanlı, Docker ile self-host edilebilir.
Cloud'dan geçiş API export + re-import ile mümkün (araçlar gelişiyor).

---

## Klasör Yapısı

```
ai-companion/
├── README.md
├── docs/                         ← Proje dokümantasyonu
├── backend/
│   ├── app/
│   │   ├── routes/               ← API endpoint'leri (FastAPI routers)
│   │   ├── services/             ← Claude, Mem0, S3, FCM, ElevenLabs
│   │   ├── middleware/           ← Auth, rate limit, hata yönetimi
│   │   └── jobs/                 ← APScheduler: proaktif bildirimler
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── Dockerfile
├── ios/                          ← iOS uygulaması (Swift + SwiftUI)
│   ├── Ember/
│   │   ├── Views/                ← SwiftUI ekranlar
│   │   ├── ViewModels/           ← @Observable view models
│   │   ├── Services/             ← API, SSE, Cognito, FCM
│   │   ├── Models/               ← Codable veri modelleri
│   │   └── Resources/            ← Assets, localization
│   └── Ember.xcodeproj
├── android/                      ← Android uygulaması (Kotlin + Compose)
│   ├── app/src/main/
│   │   ├── ui/                   ← Compose ekranlar
│   │   ├── viewmodel/            ← ViewModel + StateFlow
│   │   ├── data/                 ← Repository, API service
│   │   ├── model/                ← Data classes
│   │   └── util/                 ← SSE parser, helpers
│   └── build.gradle.kts
└── infra/
    └── migrations/               ← SQL migration dosyaları (Alembic)
```
