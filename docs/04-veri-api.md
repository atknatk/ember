# 04 — Veri Modeli ve API

## Veri Modeli

### `profiles` — Kullanıcı Profilleri

| Alan | Tip | Açıklama |
|------|-----|---------|
| `id` | UUID (PK) | AWS Cognito sub (user identifier) |
| `email` | TEXT UNIQUE | Giriş e-postası |
| `name` | TEXT | Görünen ad |
| `mem0_user_id` | TEXT UNIQUE | Mem0.ai'daki kullanıcı tanımlayıcısı |
| `fcm_token` | TEXT / NULL | Firebase push notification token |
| `timezone` | TEXT | IANA timezone (örn. "America/New_York") |
| `avatar_url` | TEXT / NULL | AWS S3 URL |
| `preferred_language` | TEXT DEFAULT 'en' | Uygulama dili |
| `onboarding_completed` | BOOLEAN DEFAULT FALSE | Onboarding tamamlandı mı? |
| `subscription_tier` | TEXT DEFAULT 'free' | `free` veya `premium` |
| `subscription_expires_at` | TIMESTAMPTZ / NULL | Premium bitiş tarihi |
| `created_at` | TIMESTAMPTZ | Kayıt tarihi |

---

### `characters` — AI Karakterleri

| Alan | Tip | Açıklama |
|------|-----|---------|
| `id` | UUID (PK) | |
| `user_id` | UUID → profiles | |
| `name` | TEXT | Kullanıcının bu karaktere verdiği isim |
| `template` | TEXT | `companion`, `english_teacher`, `therapist`, `fitness_coach`, `career_coach`, `custom` |
| `description` | TEXT / NULL | Custom karakterler için kullanıcı açıklaması |
| `system_prompt` | TEXT | Dinamik oluşturulmuş sistem promptu (düzenlenebilir) |
| `mem0_agent_id` | TEXT UNIQUE | Mem0'da izole memory alanı: `{template}_{user_id}` |
| `avatar_style` | TEXT DEFAULT 'default' | UI renk/şekil ayırt edici |
| `is_default` | BOOLEAN DEFAULT FALSE | General Friend için `true` |
| `is_active` | BOOLEAN DEFAULT TRUE | |
| `created_at` | TIMESTAMPTZ | |

---

### `conversations` — Konuşma Oturumu (Otomatik, Tek)

Her karakter için **tek bir konuşma** bulunur — kullanıcıya görünmez.
Karakter oluşturulduğunda otomatik açılır, asla yeni oturum başlatılmaz.
Bu tablo sadece DB organizasyonu içindir; uygulama "yeni konuşma" konseptini göstermez.

| Alan | Tip | Açıklama |
|------|-----|---------|
| `id` | UUID (PK) | |
| `user_id` | UUID → profiles | |
| `character_id` | UUID → characters UNIQUE | Her karakter için yalnızca 1 satır |
| `last_message_at` | TIMESTAMPTZ | Son mesaj zamanı — karakter grid sıralaması için |
| `created_at` | TIMESTAMPTZ | |

---

### `messages` — Konuşma Mesajları

| Alan | Tip | Açıklama |
|------|-----|---------|
| `id` | UUID (PK) | |
| `conversation_id` | UUID → conversations | |
| `user_id` | UUID → profiles | |
| `role` | TEXT | `user` veya `assistant` |
| `content` | TEXT | Mesaj içeriği |
| `media_url` | TEXT / NULL | AWS S3 URL (fotoğraf veya ses) |
| `tts_url` | TEXT / NULL | AWS S3 URL (sesli yanıt MP3) |
| `metadata` | JSONB / NULL | Ek veri (kalori tahmini, intent action vb.) |
| `created_at` | TIMESTAMPTZ | |

---

### `user_activity` — Proaktif Bildirim Takibi

| Alan | Tip | Açıklama |
|------|-----|---------|
| `user_id` | UUID (PK) → profiles | |
| `last_active_at` | TIMESTAMPTZ / NULL | Son uygulama açılışı |
| `last_chat_at` | TIMESTAMPTZ / NULL | Son mesaj zamanı |
| `notifications_sent_today` | JSONB (string[]) | Bugün gönderilen bildirim tipleri |
| `updated_at` | TIMESTAMPTZ | |

---

### `partners` — Partner Bağlantıları

| Alan | Tip | Açıklama |
|------|-----|---------|
| `id` | UUID (PK) | |
| `user_id_1` | UUID → profiles | Davet eden |
| `user_id_2` | UUID → profiles / NULL | Daveti kabul eden |
| `invite_token` | TEXT UNIQUE | Davet linki token'ı |
| `status` | TEXT | `pending`, `active`, `disconnected` |
| `created_at` | TIMESTAMPTZ | |

---

### `body_measurements` — Vücut Ölçümleri

| Alan | Tip | Açıklama |
|------|-----|---------|
| `id` | UUID (PK) | |
| `user_id` | UUID → profiles | |
| `date` | DATE | |
| `weight_kg` | DECIMAL / NULL | |
| `body_fat_pct` | DECIMAL / NULL | |
| `notes` | TEXT / NULL | |
| `created_at` | TIMESTAMPTZ | |

---

### Performans — Kritik İndeksler

`messages` tablosu için cursor-based (keyset) pagination zorunlu — OFFSET/LIMIT kullanma.
OFFSET derin sayfalarda O(n) tablo taramasına döner; keyset her zaman O(log n).

```sql
-- messages tablosu için kritik composite index
CREATE INDEX idx_messages_conv_time
    ON messages (conversation_id, created_at DESC);

-- Cursor-based pagination örneği (son 20 mesaj)
SELECT id, role, content, created_at
FROM messages
WHERE conversation_id = $1
  AND created_at < $cursor_timestamp   -- cursor: son yüklenen mesajın created_at'i
ORDER BY created_at DESC
LIMIT 20;

-- karakter grid sıralaması için (son aktif karakter üstte)
CREATE INDEX idx_conversations_user_time
    ON conversations (user_id, last_message_at DESC);

-- activity_log TTL cleanup için
CREATE INDEX idx_activity_log_expires
    ON activity_log (expires_at)
    WHERE expires_at < NOW();
```

İlk mesaj isteğinde `cursor` yoktur → en son 20 mesaj gelir. Scroll up'ta son mesajın `created_at` değeri `cursor` olarak gönderilir.

### Güvenlik

Backend, AWS Cognito JWT ile token doğrular. Her endpoint'te `user_id` JWT'den çıkarılır.
Kullanıcı yalnızca kendi verisine erişir — uygulama katmanında zorunlu.

Hassas tablolar (therapist character messages) → sütun düzeyinde şifreleme (AWS RDS TDE veya uygulama katmanı AES-256).

---

## API Sözleşmesi

**Base URL:** `https://api.{app-domain}.com/api/v1`

**Auth:** Tüm korumalı endpoint'lerde `Authorization: Bearer <cognito_jwt>` header'ı gerekli.

**Format:** JSON (request + response)

---

### Kimlik Doğrulama

**POST /auth/register**

```json
{
  "email": "user@example.com",
  "password": "secret123",
  "name": "Alex"
}
```

Yanıt (201):
```json
{
  "token": "eyJ...",
  "refresh_token": "...",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "name": "Alex",
    "onboarding_completed": false
  }
}
```

---

**POST /auth/login**

```json
{ "email": "user@example.com", "password": "secret123" }
```

Yanıt (200): Token + kullanıcı bilgisi

---

**POST /auth/refresh**

```json
{ "refresh_token": "..." }
```

Yanıt (200): Yeni access token

---

### Karakterler

**GET /characters**

```json
{
  "characters": [
    {
      "id": "uuid",
      "name": "Luna",
      "template": "companion",
      "is_default": true,
      "avatar_style": "purple",
      "last_conversation_at": "2026-02-23T14:30:00Z"
    }
  ]
}
```

---

**POST /characters**

```json
{
  "name": "Sarah",
  "template": "english_teacher",
  "description": null
}
```

Custom template için:
```json
{
  "name": "Marco",
  "template": "custom",
  "description": "İtalyanca öğretmeni. Sadece İtalyanca konuşur, başlangıç seviyesine uygun."
}
```

Yanıt (201): Karakter + üretilmiş `system_prompt` döner (kullanıcı onaylayabilir/düzenleyebilir)

---

**PUT /characters/:id**

```json
{
  "name": "Sarah",
  "system_prompt": "...(kullanıcı düzenledi)...",
  "avatar_style": "blue"
}
```

---

**DELETE /characters/:id**

General Friend (`is_default: true`) silinemez → 403.
Konuşma geçmişi olan karakter deaktive edilir, fiziksel silinmez.

---

### Karakter Memory

**GET /characters/:id/memories**

```json
{
  "memories": [
    {
      "id": "mem0-uuid",
      "content": "Confuses 'affect' vs 'effect'",
      "created_at": "2026-02-20T10:00:00Z"
    }
  ]
}
```

**DELETE /characters/:id/memories/:memId** → 204

**DELETE /characters/:id/memories** → Tüm karakter memory'lerini sil → 204

---

### Mesajlaşma (Karakter Bazlı)

Konuşma kavramı kullanıcıya **hiç gösterilmez.** Tüm mesaj operasyonları `character_id` üzerinden yapılır.
Backend, ilgili `conversation_id`'yi otomatik bulur (her karakterin tek bir konuşması var).

---

**POST /characters/:id/messages**

```json
{
  "content": "I want to practice English today!",
  "media_url": "https://s3.amazonaws.com/..."
}
```

Yanıt: **Server-Sent Events (SSE)**

```
data: {"type": "chunk", "content": "Great"}
data: {"type": "chunk", "content": "! Let's start"}
...
data: {"type": "action", "action": "SET_ALARM", "payload": {"time": "07:00", "label": "Wake up"}}
data: {"type": "done", "message_id": "uuid"}
```

`action` event'i cihaz entegrasyon komutları için kullanılır (alarm, takvim).

---

**GET /characters/:id/messages?cursor={created_at_iso}**

Cursor-based sayfalı mesaj listesi, en yeniden en eskiye sıralı (20 mesaj/sayfa).
`cursor` belirtilmezse en son 20 mesaj döner. Scroll up'ta son yüklenen mesajın `created_at` değeri cursor olarak gönderilir.

---

### Bellek

**GET /memories** → General Friend (global) memory'leri

**GET /characters/:id/memories** → Karaktere özel memory'ler

**DELETE /memories/:memId** → 204

---

### Medya

**POST /media/upload-url**

```json
{
  "filename": "meal.jpg",
  "content_type": "image/jpeg",
  "type": "photo"
}
```

Yanıt (200):
```json
{
  "upload_url": "https://s3.amazonaws.com/...?X-Amz-Signature=...",
  "file_url": "https://s3.amazonaws.com/ai-companion-media/photos/user_id/timestamp_meal.jpg"
}
```

Uygulama bu URL'ye doğrudan dosyayı yükler (PUT), sonra `file_url`'yi mesajda kullanır.

---

### TTS (Faz 5)

**POST /tts**

```json
{
  "text": "That's great progress! Your vocabulary is improving.",
  "character_id": "uuid"
}
```

Yanıt (200):
```json
{
  "audio_url": "https://s3.amazonaws.com/.../tts/uuid.mp3",
  "duration_seconds": 4.2
}
```

---

### STT (Faz 5)

**POST /stt**

```json
{
  "audio_url": "https://s3.amazonaws.com/.../audio/uuid.mp3"
}
```

Yanıt (200):
```json
{
  "transcript": "I want to practice speaking today",
  "language": "en",
  "confidence": 0.97
}
```

---

### Partner (Faz 7)

```
POST   /partners/invite            → Davet linki oluştur
POST   /partners/accept            → Token ile kabul et
GET    /partners/progress          → Anonim haftalık özet
DELETE /partners                   → Bağlantıyı kes
```

---

### Profil

**GET /profile** → Profil bilgisi

**PUT /profile**

```json
{
  "name": "Alex",
  "avatar_url": "https://...",
  "timezone": "America/New_York",
  "preferred_language": "en"
}
```

**DELETE /profile/account** → GDPR hesap silme (30 gün içinde temizlenir)

---

### Bildirimler

**PUT /notifications/token**

```json
{ "fcm_token": "fcm-device-token-here" }
```

**PUT /notifications/preferences**

```json
{
  "morning_checkin": true,
  "evening_reflection": true,
  "sleep_reminder": false,
  "character_notifications": {
    "english_teacher_uuid": true,
    "therapist_uuid": false
  }
}
```

---

### Hata Formatı

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or expired token."
  }
}
```

| Kod | Anlam |
|-----|-------|
| 400 | Invalid request |
| 401 | Authentication failed |
| 403 | Forbidden (e.g., deleting default character) |
| 404 | Resource not found |
| 429 | Rate limit exceeded |
| 500 | Server error |
