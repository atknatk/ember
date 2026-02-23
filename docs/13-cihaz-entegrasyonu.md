# 13 — Cihaz Entegrasyonu

## Genel Bakış

Üç cihaz entegrasyonu **Faz 6**'da eklenir. Hepsi AI'ın doğal konuşma sırasında
tetiklenebilir — kullanıcı ayrı bir menüye gitmez.

| Özellik | iOS | Android | Faz |
|---------|-----|---------|-----|
| Telefon araması takibi | Kısıtlı (manuel not) | Tam (`CallLog.Calls`) | Faz 6 |
| Alarm kurma | `UNUserNotificationCenter` | `AlarmManager` | Faz 6 |
| Takvim entegrasyonu | `EventKit` | `CalendarContract` | Faz 6 |

---

## 1. Telefon Araması Takibi

### Amaç

Kullanıcı AI'a sorar: "Bugün kim aradı beni?"
AI cevaplar: "Ahmet saat 14:30'da aradı, geri dönmek ister misin?"

Veya AI proaktif sorar: "Az önce bir çağrı kaçırdın — Tuvik aramış, döner misin?"

---

### Android — Tam Destek

Native API: `CallLog.Calls` ContentProvider

İzin: `READ_CALL_LOG` (runtime'da istenir, sadece özellik kullanılınca)

Kullanım akışı:

```
Kullanıcı "kim aradı?" diye sorar
    ↓
Backend intent sınıflandırır: CALL_LOG_QUERY
    ↓
App (Android) → CallLog.Calls ContentProvider sorgusu
    ↓
Son 24 saatin aramaları çekilir (missed/incoming/outgoing)
    ↓
App → backend'e gönderir (context olarak)
    ↓
AI aramaları yorumlar, cevap üretir
```

Örnek veri:

```json
{
  "call_logs": [
    { "name": "Ahmet Yılmaz", "number": "+90...", "type": "missed", "time": "14:32", "duration": 0 },
    { "name": "Tuvik", "number": "+90...", "type": "incoming", "time": "11:15", "duration": 180 }
  ]
}
```

---

### iOS — Kısıtlı

iOS, üçüncü taraf uygulamaların call log'a erişimine izin vermez.
CallKit'e okuma erişimi yok. Apple politikası engelliyor.

**Alternatif yaklaşım:**

1. Kullanıcı aramaları manuel notlayabilir: "Az önce Ahmet aradı"
   → AI bu bilgiyi Mem0'ya kaydeder
   → Sonraki konuşmalarda hatırlar

2. Proaktif bildirim yerine reaktif: Kullanıcı söylemeden AI bilemez.

3. Future: iOS'ta Siri Shortcut entegrasyonu — kullanıcı Siri ile tetikler,
   bu uygulama tetiklenecek şekilde yapılandırılabilir (karmaşık, değerlendiriliyor).

---

## 2. Alarm Kurma

### Amaç

Kullanıcı: "Yarın sabah 7'ye alarm kur"
AI: "Tamam, 7:00 alarmı kurdum"

Kullanıcı: "Pazartesi saat 9'da toplantım var, hatırlat"
AI: "Pazartesi 09:00'da 'Toplantı' bildirimi ayarladım"

---

### Uygulama

Alarm akışı:

```
Kullanıcı "alarm kur" içeren mesaj yazar
    ↓
Backend → Claude Haiku ile intent extraction:
  { "intent": "SET_ALARM", "time": "07:00", "label": "Sabah alarmı", "date": "tomorrow" }
    ↓
Backend → uygulamaya action mesajı döner:
  { "action": "SET_ALARM", "time": "2026-02-24T07:00:00", "label": "Sabah alarmı" }
    ↓
iOS: UNUserNotificationCenter ile scheduled notification
Android: AlarmManager.setExactAndAllowWhileIdle() ile alarm
    ↓
Kullanıcıya onay gösterilir: "7:00 alarmı kuruldu"
```

---

### Platform Kısıtları

**iOS:**
- `UNUserNotificationCenter` kullanılır
- `requestAuthorization(options: [.alert, .sound, .badge])` ile izin alınır
- Uygulama kapalıyken de çalışır (iOS local notifications)
- Tam ekran alarm (müzik çalma) için `AVAudioSession` gerekir — değerlendiriliyor

**Android:**
- `AlarmManager.setExactAndAllowWhileIdle()` kullanılır
- `SCHEDULE_EXACT_ALARM` izni Android 12+ için gerekli
- Uygulama kapalıyken çalışır
- Özel alarm sesi: assets'e MP3 eklenebilir

---

### Kod Örnekleri (Konsept)

**iOS (Swift):**

```swift
func scheduleAlarm(at date: Date, label: String) {
    let content = UNMutableNotificationContent()
    content.title = "⏰ Alarm"
    content.body = label
    content.sound = .default

    let trigger = UNCalendarNotificationTrigger(
        dateMatching: Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date),
        repeats: false
    )

    let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: trigger)
    UNUserNotificationCenter.current().add(request)
}
```

**Android (Kotlin):**

```kotlin
fun scheduleAlarm(context: Context, triggerAt: Long, label: String) {
    val intent = Intent(context, AlarmReceiver::class.java).apply {
        putExtra("label", label)
    }
    val pendingIntent = PendingIntent.getBroadcast(context, alarmId, intent, PendingIntent.FLAG_IMMUTABLE)
    val alarmManager = context.getSystemService(AlarmManager::class.java)
    alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent)
}
```

---

## 3. Takvim Entegrasyonu

### Amaç

Kullanıcı: "Salı günü saat 15:00'te diş doktoru randevusu var"
AI: "Takvime ekleyeyim mi?" → Kullanıcı onaylar → Takvime eklenir

Veya:
Kullanıcı: "Bu hafta ne var takvimdeki?"
AI: "Salı diş doktoru, Cuma proje teslimi var."

---

### Uygulama

Platform:
- **iOS:** `EventKit` framework (`EKEventStore`)
- **Android:** `CalendarContract` ContentProvider

İzinler:
- `READ_CALENDAR` — takvim okuma
- `WRITE_CALENDAR` — takvime yazma
- iOS: `NSCalendarsUsageDescription` + `NSCalendarsWriteOnlyAccessUsageDescription`

---

### Takvim Okuma Akışı

```
Kullanıcı "bu hafta ne var?" diye sorar
    ↓
Backend intent: CALENDAR_READ
    ↓
iOS: EKEventStore.events(matching: predicate)
Android: CalendarContract.Events content resolver query
    ↓
Etkinlikler backend'e gönderilir
    ↓
AI etkinlikleri yorumlar, öneride bulunur
```

---

### Takvim Yazma Akışı

```
Kullanıcı etkinlik eklemek ister
    ↓
Backend intent: CALENDAR_WRITE + parsing:
  { "title": "Diş doktoru", "date": "2026-02-24", "time": "15:00", "duration": 60 }
    ↓
Uygulama kullanıcıya ONAY gösterir:
  "Salı 15:00 — Diş doktoru (1 saat) takvime eklensin mi?"
    ↓
Kullanıcı onaylarsa:
  iOS: EKEvent oluştur → EKEventStore.save()
  Android: CalendarContract.Events insert
    ↓
AI: "Eklendi! Salı 15:00'i boş tut."
```

**Onay zorunludur.** AI asla kullanıcı onayı olmadan takvime yazmaz.

---

### Intent Parsing (Claude Haiku)

Kullanıcı mesajından zaman/tarih/etkinlik bilgisi çıkarmak için Haiku kullanılır:

```
Giriş: "yarın öğleden sonra 3'te diş doktoru randevum var"

Çıkış:
{
  "intent": "CALENDAR_WRITE",
  "title": "Diş Doktoru Randevusu",
  "date": "2026-02-24",
  "time": "15:00",
  "duration_minutes": 60,
  "confidence": 0.95
}
```

Confidence < 0.7 ise AI kullanıcıya sorar: "Tam tarihi doğrulayabilir misin?"

---

## Genel İzin Yönetimi

Tüm cihaz izinleri kullanıcı ilk kez o özelliği kullanmak istediğinde istenir.
Onboarding sırasında toplu izin istenmez — bu iOS App Store kurallarına da uygundur.

| İzin | Android | iOS | Ne Zaman İstenir |
|------|---------|-----|-----------------|
| `READ_CALL_LOG` | Var | Yok | Kullanıcı ilk "kim aradı" dediğinde |
| `READ_CALENDAR` | Var | EventKit | "Bu hafta ne var?" ilk kez |
| `WRITE_CALENDAR` | Var | EventKit | İlk takvim yazma onayında |
| `SCHEDULE_EXACT_ALARM` | Android 12+ | — | İlk alarm kurulumunda |
| Bildirim izni | Var | APNs | Onboarding sonu |

---

## Mem0 Entegrasyonu

Cihaz verisi sadece anlık bağlam için değil, Mem0'a da yazılabilir:

- "Diş doktoru randevusu var" → Mem0: "Salı 15:00 diş doktoru var, hatırlatılabilir"
- Tekrarlayan arama: "Her Cuma Ahmet arıyor" → Mem0: "Ahmet her Cuma arar"
- Takvim deseni: "Pazartesi toplantısı düzenli" → Mem0: "Pazartesileri toplantı günü"

AI zamanla kullanıcının rutinini öğrenir.
