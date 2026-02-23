# 06 — Proaktif Bildirim Sistemi

## Çalışma Mantığı

Sunucu tarafında bir cron job her 30 dakikada bir çalışır.
Her aktif kullanıcı için koşullar kontrol edilir.
Koşul sağlanırsa Claude Haiku ile kişiselleştirilmiş mesaj üretilir ve FCM ile gönderilir.

```
[Cron: 30 dakikada bir]
        ↓
[Tüm kullanıcılar için döngü]
        ↓
[user_activity tablosunu oku]
        ↓
[Timezone'a göre yerel saat hesapla]
        ↓
[Tetikleyici koşulları kontrol et]
        ↓ koşul sağlandı
[Claude Haiku ile kişiselleştirilmiş metin üret]
        ↓
[Firebase FCM ile push gönder]
        ↓
[notifications_sent_today'e tipi ekle]
```

---

## Tetikleyici Koşullar

| ID | Zaman Aralığı | Koşul | Mesaj Tonu |
|----|--------------|-------|-----------|
| `morning_checkin` | 08:00 – 09:30 | Bugün henüz chat yok | Sıcak, enerjik |
| `afternoon_nudge` | 14:00 – 15:30 | Bugün hiç aktif değil | Meraklı, hafif |
| `evening_reflection` | 20:00 – 21:00 | Akşam check-in yok | Sakin, yansıtıcı |
| `sleep_reminder` | 23:00+ | Son 1 saatte aktif | Nazik, umursayıcı |
| `goal_followup` | 15:00 – 17:00 | Memory'de hedef var, ilgili aktivite yok | Destekleyici |

Aynı tip bildirim günde maksimum 1 kez gönderilir (`notifications_sent_today` kontrolü).
Her gece gece yarısı `notifications_sent_today` sıfırlanır.

---

## Kişiselleştirme

Her bildirim metni Claude Haiku ile üretilir:

1. Kullanıcının Mem0 memories'inden ilgili bilgiler çekilir
2. Bildirim tipi + memories ile prompt oluşturulur
3. Claude Haiku kısa (1-2 cümle) kişiselleştirilmiş metin üretir

Örnek — sabah bildirimi:
- Genel: "Günaydın! Bugün nasılsın?"
- Kişiselleştirilmiş: "Günaydın Atakan! Bugün omuz günün, hazır mısın?" (fitness memory'den)

Örnek — uyku bildirimi:
- Genel: "Uyu artık, gec oldu."
- Kişiselleştirilmiş: "Saat 23:50 oldu, yarın sabah 07:00'de kalkman lazım." (uyku memory'den)

---

## Bildirim Tıklama Davranışı

Kullanıcı bildirimi tıklar → native uygulama açılır → ilgili karakterin chat ekranı gelir.

Bildirim payload'ında `character_id` gönderilir — uygulama doğrudan o karakterin tek konuşmasını açar.
AI bağlamı zaten hazırdır (sistem prompt'u bildirim tipine göre önceden şekillendirilmiş).

---

## Bildirim Limitleri ve Kullanıcı Tercihleri

Kullanıcı profil ekranından hangi bildirim tiplerini almak istediğini ayarlayabilir:

- Sabah check-in: Açık / Kapalı
- Akşam yansıma: Açık / Kapalı
- Uyku hatırlatması: Açık / Kapalı
- Hedef takibi: Açık / Kapalı

Sessiz saatler: Kullanıcı "rahatsız etme" saatleri belirleyebilir (Faz 11+).

---

## `user_activity` Tablosu Kullanımı

Her bildirim kararı için şu alanlar okunur:

- `last_chat_at` → bugün mesaj gönderildi mi?
- `last_active_at` → son 1 saatte aktif miydi?
- `notifications_sent_today` → hangi tipler zaten gönderildi?

Her bildirim sonrası `notifications_sent_today` güncellenir.
Her mesaj gönderiminde `last_chat_at` ve `last_active_at` güncellenir (middleware).
