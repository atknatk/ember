# 08 — Güvenlik ve Performans

## Güvenlik

### API Güvenliği

- Tüm endpoint'ler HTTPS zorunlu
- AWS Cognito JWT token'ları (RS256) — sunucu tarafında doğrulanır
- Access token süresi: 1 saat
- Refresh token süresi: 30 gün
- Rate limiting: Gruplu limitler — chat: 10/dk, write: 20/dk, read: 60/dk (kullanici basina, `config.py` ayarlanabilir)

### İçerik Moderasyonu

- Kullanıcı mesajları Anthropic content filtering ile kontrol edilir
- Prompt injection koruması: system prompt manipülasyonu engellenir
- Therapist karakter için özel hassasiyet: kriz durumunda acil kaynak yönlendirmesi
- Mesaj uzunluk limiti: max 4000 karakter per message
- Memory sanitization: Mem0'ya yazılan memory'ler zararlı içerikten temizlenir
- Detaylı implementasyon: P02-05 (content-moderation) issue'da

### API Key Güvenliği

API key'ler (Anthropic, Mem0, ElevenLabs, Firebase) **hiçbir zaman** mobil uygulamada saklanmaz.
Tüm AI çağrıları backend üzerinden yapılır.

Native iOS/Android uygulamalarında yalnızca şunlar tutulur:
- AWS Cognito JWT token (session yönetimi için)
- Backend API URL

AWS Secrets Manager ve Parameter Store — tüm secret'lar environment variable olarak ECS task'lara inject edilir. Kod içinde hardcoded secret yok.

### Kullanıcı Veri İzolasyonu

Her endpoint'te `user_id` JWT'den çıkarılır — kullanıcı yalnızca kendi verisine erişir.
Backend servis rolü tüm verilere erişebilir (cron job'lar, Mem0 güncelleme için).
Fotoğraflar S3'te kullanıcı ID'sine göre izole klasörlerde saklanır: `photos/{user_id}/{filename}`
S3 bucket policy: kullanıcı yalnızca kendi klasörüne erişebilir (IAM policy).

### GDPR Uyumu

- Hesap silme özelliği zorunlu (App Store gerekliliği)
- Hesap silinince:
  - RDS'deki tüm satırlar silinir (profiles, conversations, messages, user_activity)
  - Mem0'daki tüm memories silinir
  - S3'teki tüm dosyalar silinir (photos, audio)
- Veri export (Faz 11): Tüm kişisel verinin JSON olarak indirilmesi

---

## Performans Hedefleri

| Metrik | Hedef |
|--------|-------|
| İlk streaming token | < 1 saniye |
| Konuşma geçmişi yükleme | < 500ms |
| Fotoğraf analizi (ilk token) | < 5 saniye |
| Bildirim iletim süresi | < 10 saniye (cron tetiklemesinden) |
| Mobil uygulama soğuk başlatma | < 3 saniye |
| API yanıt süresi (streaming hariç) | < 300ms |

---

## Performans Stratejileri

### Backend

- Mem0 search ve RDS mesaj çekimi paralel yapılır (`asyncio.gather`)
- Memory güncelleme (Mem0'a ekle) async — yanıt dönükten sonra arka planda çalışır
- Veritabanı sorguları index'li: `messages(conversation_id, created_at DESC)` — cursor pagination
- Prompt caching (Anthropic): Karakter system prompt Block 1'de cache'lenir, %30-50 token tasarrufu
- Rate limiting ile tek kullanıcının sistemi yorması engellenir
- ECS Fargate auto scaling: CPU %70 → yeni task başlatılır

### iOS

- Mesaj listesi lazy loading (infinite scroll, cursor-based pagination)
- Kingfisher ile network image cache (avatar, fotoğraflar)
- `@Observable` ile gereksiz view rebuild'leri önlenir
- Büyük fotoğraflar gönderilmeden önce sıkıştırılır (max 1MB, HEIF → JPEG)

### Android

- Mesaj listesi lazy loading (LazyColumn, cursor-based pagination)
- Coil ile network image cache
- `StateFlow` + `collectAsStateWithLifecycle` ile gereksiz recomposition önlenir
- Büyük fotoğraflar sıkıştırılır (max 1MB, WEBP tercih edilir)
