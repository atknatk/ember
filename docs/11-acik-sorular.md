# 11 — Açık Sorular

Tüm kararlar verildi. Referans için çözülmüş sorular aşağıda.

---

## Çözülmüş Sorular

| Soru | Karar |
|------|-------|
| Uygulama adı? | **Ember** |
| Backend dili? | Python + FastAPI |
| Deployment altyapısı? | AWS (ECS Fargate, RDS, S3, Cognito) |
| Web versiyonu? | Yok |
| AI model provider? | Multi-provider (Anthropic varsayılan, GPT-4o / Gemini alternatifleri mevcut) |
| Türkçe TTS? | ElevenLabs Flash v2.5 + AWS Polly Burcu (yedek) |
| Mem0 self-hosted mümkün mü? | Evet — bkz. 05-ai-bellek.md |
| Uygulama dili? | Multilingual EN öncelikli, worldwide |
| Flutter vs Native? | **Native** — iOS (Swift + SwiftUI), Android (Kotlin + Jetpack Compose) |
| Karanlık mod? | Varsayılan |
| Fazlar / MVP? | Yok — tüm fazlar sırayla tam yapılır, **12 faz** |
| Partner bağlantısı? | **Faz 8** |
| Push notification opt-in? | İlk chat oturumu bittikten sonra, context'li |
| Ücretsiz tier mesaj limiti? | 100 mesaj/ay |
| Konuşma geçmişi saklama? | Süresiz |
| Karakter sistemi? | Evet — bkz. 16-karakterler.md |
| Ücretsiz tier karakter hakkı? | Sadece General Friend (1 karakter) |
| Premium karakter hakkı? | Sınırsız |
| Karakter ismi? | Kullanıcı kendisi belirler (onboarding'de sorar) |
| Romantic companion? | Opsiyonel karakter add-on, ana ürün değil |
| Konumlandırma? | Personal AI assistant — romantic companion değil |
| Telefon araması takibi (iOS)? | Kullanıcı söylerse AI kaydeder (Apple kısıtı) |
| Telefon araması takibi (Android)? | `CallLog.Calls` ContentProvider (native Android) |
| Sesli yanıt (async)? | **Faz 5** — ElevenLabs Flash v2.5 + Polly hibrit |
| Sesli mesaj STT (async)? | **Faz 5** — OpenAI Whisper (batch, auto-detect language) |
| Gerçek zamanlı sesli arama? | **Faz 12** — LiveKit + Deepgram Nova-3 + ElevenLabs Flash |
| Whisper real-time kullanılabilir mi? | Hayır — batch-only. Real-time için Deepgram Nova-3 |
| Veritabanı? | AWS RDS PostgreSQL + pgvector (değiştirme gerekmez) |
| Fitness modülü? | Sadeleştirildi — body_measurements + ExerciseDB API (workout tracker yok) |
| Egzersiz görselleri? | ExerciseDB API — link/GIF, veri saklanmaz |
| Worldwide pazar mı? | Evet |
| Fiyat? | Freemium + $9.99/ay premium |

---

*Açık kalan karar yok.*
