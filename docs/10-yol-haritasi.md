# 10 — Geliştirme Yol Haritası

Acelemiz yok. Her faz tam bitmeden bir sonrakine geçilmez.
"MVP" kavramı yok — her özellik doğru yapılır, sonra devam edilir.

---

## Faz 1 — Backend Temeli

**Hedef:** Çalışan bir API ile basit chat, memory öğreniyor.

**Başarı kriteri:** Postman/curl ile chat çalışıyor, memory öğreniyor, AWS deployment ayakta.

### Yapılacaklar

- [ ] AWS RDS PostgreSQL instance oluştur + Alembic migration çalıştır
- [ ] FastAPI proje yapısını kur (app/, routes/, services/, middleware/)
- [ ] AWS Cognito User Pool kur + JWT doğrulama middleware
- [ ] Profil oluşturma — Mem0'da kullanıcı kaydı (`mem0_user_id` ata)
- [ ] Claude streaming chat endpoint (SSE)
- [ ] Mem0 search + add entegrasyonu (konuşma öncesi ara, sonra ekle)
- [ ] Konuşma listesi endpoint'i
- [ ] Mesaj geçmişi endpoint'i (sayfalı)
- [ ] Memories listele / sil endpoint'leri
- [ ] AWS S3 presigned URL endpoint'i (fotoğraf yükleme)
- [ ] `user_activity` güncelleme middleware'i
- [ ] Dockerfile yazımı
- [ ] ECR'e push + ECS Fargate deploy
- [ ] CloudFront + ALB konfigürasyonu
- [ ] GitHub Actions CI/CD pipeline

---

## Faz 2 — Proaktif Bildirim Sistemi

**Hedef:** Sunucu kullanıcılara otomatik ulaşıyor.

**Başarı kriteri:** Test kullanıcısına sabah bildirimi geliyor, içerik kişiselleştirilmiş.

### Yapılacaklar

- [ ] Firebase Admin SDK kurulumu (Python) + service account config
- [ ] FCM token kaydetme endpoint'i (`PUT /notifications/token`)
- [ ] APScheduler cron job altyapısı (her 30 dakika)
- [ ] Tetikleyici koşul fonksiyonları (5 adet: sabah, öğle, akşam, gece, hedef)
- [ ] Timezone'a göre yerel saat hesaplama (pytz)
- [ ] Claude Haiku ile kişiselleştirilmiş bildirim metni üretimi
- [ ] FCM push notification gönderme
- [ ] `notifications_sent_today` güncelleme ve gece sıfırlama
- [ ] Bildirim tercihleri (`profile` tablosuna alan ekle)

---

## Faz 3 — iOS Native Uygulama

**Hedef:** Çalışan iOS uygulaması, TestFlight'ta test edilebilir.

**Başarı kriteri:** iPhone'da konuşma çalışıyor, bildirim geliyor, memory görünüyor.

### Yapılacaklar

- [ ] Xcode projesi init (iOS 17+, Swift 5.9+, SwiftUI)
- [ ] AWS Amplify iOS (Cognito) entegrasyonu — login / register / session persistence
- [ ] `NavigationStack` ile navigasyon yapısı + deep link desteği
- [ ] `LoginView` + `RegisterView`
- [ ] `WelcomeView` (3 kart, TabView swipe animasyonu, Lottie)
- [ ] `ProfileSetupView` (isim + PHPickerViewController fotoğraf)
- [ ] `QuestionsView` (7 soru, Mem0'a seed)
- [ ] `HomeView` (konuşma listesi + günlük özet kartı)
- [ ] `ChatView` (SSE streaming, bubble UI, Markdown render via swift-markdown)
- [ ] SSE implementasyonu: `URLSession` + `AsyncStream` (bkz. [07-mobil.md](07-mobil.md))
- [ ] `MemoriesView` (kategorili liste + sil, segment control)
- [ ] `ProfileView` (tercihler + hesap + bildirim toggle)
- [ ] Firebase iOS SDK — FCM entegrasyonu
- [ ] Push notification opt-in: ilk chat oturumu bitince context'li sor
- [ ] Bildirim tıklama → deep link ile doğru ekrana yönlendirme
- [ ] Kingfisher — network image caching
- [ ] Lottie animasyonları (onboarding, empty state)
- [ ] TestFlight yükleme

> **3D Avatar:** Ready Player Me SDK (iOS native) desteği var, ücretsiz tier mevcut.
> Faz 3'te minimum viable: 2D Lottie animasyon (idle, talking, happy).
> Ready Player Me entegrasyonu değerlendiriliyor — bkz. [07-mobil.md](07-mobil.md#3d-avatar).

---

## Faz 4 — Android Native Uygulama

**Hedef:** Çalışan Android uygulaması, Internal Testing'de test edilebilir.

**Başarı kriteri:** Android'de konuşma çalışıyor, bildirim geliyor, iOS ile feature parity.

### Yapılacaklar

- [ ] Android Studio projesi init (minSdk 26, Kotlin, Jetpack Compose)
- [ ] AWS Amplify Android (Cognito) entegrasyonu — login / register / session persistence
- [ ] Navigation Compose ile navigasyon yapısı + deep link desteği
- [ ] `LoginScreen` + `RegisterScreen`
- [ ] `WelcomeScreen` (3 kart, HorizontalPager, Lottie)
- [ ] `ProfileSetupScreen` (isim + ActivityResultContracts.PickVisualMedia fotoğraf)
- [ ] `QuestionsScreen` (7 soru, Mem0'a seed)
- [ ] `HomeScreen` (konuşma listesi + günlük özet kartı)
- [ ] `ChatScreen` (SSE streaming, bubble UI, Markwon render)
- [ ] SSE implementasyonu: OkHttp `EventSourceListener` (bkz. [07-mobil.md](07-mobil.md))
- [ ] `MemoriesScreen` (kategorili liste + sil, tab row)
- [ ] `ProfileScreen` (tercihler + hesap + bildirim toggle)
- [ ] Firebase Android SDK — FCM entegrasyonu
- [ ] Push notification opt-in (Android 13+ runtime permission)
- [ ] Bildirim tıklama → deep link ile doğru ekrana
- [ ] Coil — network image caching
- [ ] Lottie Android animasyonları
- [ ] Google Play Internal Testing yükleme

> **3D Avatar:** Ready Player Me SDK (Android native) desteği var.
> iOS'ta uygulanan karar burada da geçerli.

---

## Faz 5 — Sesli Deneyim

**Hedef:** Kullanıcı konuşabilir, AI sesli yanıt verebilir.

**Başarı kriteri:** Sesli mesaj gönderilince metne çevriliyor, AI yanıtı sesli dinlenebiliyor.

### Backend

- [ ] TTS servis soyutlama katmanı oluştur (provider değişince sadece servis güncellenir)
- [ ] ElevenLabs TTS entegrasyonu (`POST /tts`)
- [ ] AWS Polly Burcu Neural — yedek provider
- [ ] Hibrit seçim mantığı: < 150 karakter → Polly, uzun → ElevenLabs
- [ ] Üretilen ses S3'e kaydedilir, URL döner
- [ ] OpenAI Whisper STT entegrasyonu (`POST /stt`)
- [ ] STT: dil parametresi (`language` field — user tercihi)

### iOS

- [ ] `AVAudioRecorder` — ses kaydı
- [ ] `AVPlayer` — ses oynatma
- [ ] `AVAudioSession` — ses oturumu konfigürasyonu
- [ ] Chat input'a mikrofon butonu: basılı tut = kayıt, bırak = gönder, yukarı sürükle = iptal
- [ ] Kayıt sırasında dalga animasyonu (ses seviyesi görsel)
- [ ] AI mesaj balonuna TTS play butonu ekle
- [ ] Audio player: progress bar + hız ayarı (0.75x / 1x / 1.5x)
- [ ] `NSMicrophoneUsageDescription` info.plist
- [ ] Kullanıcı tercihi: yanıtlar otomatik sesli gelsin mi? (ayarlar)

### Android

- [ ] `AudioRecord` / `MediaRecorder` — ses kaydı
- [ ] `ExoPlayer` (Media3) — ses oynatma
- [ ] `AudioManager` — ses oturumu
- [ ] Chat input'a mikrofon butonu (aynı UX — iOS ile tutarlı)
- [ ] Kayıt dalga animasyonu
- [ ] AI mesaj balonuna TTS play butonu
- [ ] Audio player: progress bar + hız ayarı
- [ ] `RECORD_AUDIO` izni (runtime)
- [ ] Kullanıcı tercihi: otomatik sesli yanıt (ayarlar)

---

## Faz 6 — Cihaz Entegrasyonu

**Hedef:** AI telefon aramalarını takip eder, alarm kurar, takvime yazar.

**Başarı kriteri:** "Yarın 8'e alarm kur" deyince alarm kurulmuş oluyor.

### Backend — Intent Parsing

- [ ] Claude Haiku ile intent extraction servisi
- [ ] Intent tipleri: `SET_ALARM`, `CALENDAR_READ`, `CALENDAR_WRITE`, `CALL_LOG_QUERY`
- [ ] Tarih/saat parsing: "yarın", "salı", "saat 15" → ISO 8601
- [ ] Confidence < 0.7 → AI kullanıcıya soruyor
- [ ] Backend → mobil action message protokolü:
  ```json
  { "action": "SET_ALARM", "payload": { "time": "...", "label": "..." } }
  ```

### iOS — Alarm

- [ ] `UNUserNotificationCenter` ile scheduled notification
- [ ] `TimeZone` ile kullanıcı timezone'ı
- [ ] iOS izin akışı: `requestAuthorization`
- [ ] Alarm onay UI: "7:00 alarmı kurulsun mu?" → Evet / Hayır
- [ ] Alarm iptal: "Alarmı kaldır" komutu

### Android — Alarm

- [ ] `AlarmManager` ile exact alarm
- [ ] Android 12+: `SCHEDULE_EXACT_ALARM` izni
- [ ] `TimeZone` kullanıcı timezone'ı
- [ ] Alarm onay UI (iOS ile tutarlı)
- [ ] Alarm iptal

### iOS — Takvim

- [ ] `EventKit` framework — `EKEventStore`
- [ ] `NSCalendarsUsageDescription` + `NSCalendarsWriteOnlyAccessUsageDescription`
- [ ] Takvim seçimi: birden fazla takvim varsa kullanıcı seçer (1 kez ayarlanır)
- [ ] Takvim okuma: bu hafta / bu ay etkinlikleri çek
- [ ] Takvim yazma: her zaman onay göster, AI direkt yazmaz
- [ ] Etkinlik oluşturma: başlık, tarih, saat, süre (varsayılan 1 saat)

### Android — Takvim

- [ ] `CalendarContract` ContentProvider
- [ ] `READ_CALENDAR` + `WRITE_CALENDAR` izinleri (runtime)
- [ ] Takvim seçimi, okuma, yazma (iOS ile aynı UX)

### Android — Telefon Araması

- [ ] `CallLog.Calls` ContentProvider
- [ ] `READ_CALL_LOG` izni (runtime, sadece istenince)
- [ ] Son 24 saat aramaları çek: missed / incoming / outgoing
- [ ] Arama verisi backend'e gönderilir (context olarak)
- [ ] Mem0'a arama paterni yazılabilir: "Her Cuma Ahmet arar"

### iOS — Telefon Araması (Kısıtlı)

- [ ] Call log okuma yok (Apple kısıtı)
- [ ] Kullanıcı manuel söylerse AI kaydeder: "Ahmet beni aradı" → Mem0
- [ ] UX: Chat'te "Bugün kim aradı?" sorusuna iOS kullanıcıları için açıklama

---

## Faz 7 — Fotoğraf ve Medya

> **Not:** Kullanıcı talebiyle Faz 3'ten buraya alındı. Backend altyapısı Faz 1'de kısmen kurulmuş olacak (S3 presigned URL endpoint'i).

**Hedef:** Fotoğraf gönderilebilir, AI yorumluyor.

**Başarı kriteri:** Yemek fotoğrafı gönderince kalori tahmini geliyor.

### Backend

- [ ] S3 bucket yapılandırması (IAM policy: user kendi `{user_id}/` klasörüne)
- [ ] Presigned URL endpoint'i (`POST /media/upload-url`) — Faz 1'de yapıldıysa atla
- [ ] Claude vision ile fotoğraf analizi (yemek için özel prompt)
- [ ] Fotoğraflı mesaj akışı: `media_url`'yi mesaja ekle, AI'ya fotoğrafı gönder
- [ ] Kalori/makro tahmini sonucunu mesaj `metadata`'sına kaydet
- [ ] S3 Lifecycle Policy: ses dosyaları 90 gün Glacier'a

### iOS

- [ ] `PHPickerViewController` — fotoğraf seçimi
- [ ] S3 presigned URL ile doğrudan yükleme
- [ ] Chat input'a fotoğraf butonu
- [ ] Yükleme progress göstergesi
- [ ] AI yanıtına kalori kartı UI (metadata render)

### Android

- [ ] `ActivityResultContracts.PickVisualMedia` — fotoğraf seçimi
- [ ] S3 presigned URL ile doğrudan yükleme
- [ ] Chat input'a fotoğraf butonu
- [ ] Yükleme progress göstergesi
- [ ] AI yanıtına kalori kartı UI

---

## Faz 8 — Partner Bağlantısı

**Hedef:** İki kullanıcı birbirini bağlayabilir, AI ortak motivasyon sağlar.

**Başarı kriteri:** Bağlı partner'ın anonim haftalık özeti AI konuşmasına giriyor.

### Backend

- [ ] `partners` tablosu: `user_id_1`, `user_id_2`, `status` (pending/active), `created_at`
- [ ] `POST /partners/invite` → benzersiz davet linki üret (JWT veya UUID token)
- [ ] `POST /partners/accept` → token doğrula, bağlantıyı aktifleştir
- [ ] `GET /partners/progress` → anonim haftalık özet (hangi aktivite, kaç kez — isim yok)
- [ ] `DELETE /partners` → bağlantıyı kes
- [ ] Claude sistem prompt güncellemesi: partner bağlıysa haftalık özeti 3. bloka ekle
- [ ] Partner bağlantısı kesilince sistem prompttan çıkar

### iOS + Android

- [ ] Partner kurulum ekranı (link oluştur / linki paylaş)
- [ ] Davet linki deep link ile açılır → onay akışı
- [ ] Partner bağlandı bildirimi (FCM)
- [ ] Home ekranında partner özet kartı (isteğe bağlı, kapatılabilir)
- [ ] Profil ekranında partner yönetimi (bağlı / bağla / bağlantıyı kes)

---

## Faz 9 — Karakter Sistemi

**Hedef:** Kullanıcı birden fazla AI karakteri oluşturabiliyor, her biri izole belleğe sahip.

**Başarı kriteri:** English Teacher karakteri oluşturulabiliyor, sadece dil memory'si birikiyor.

### Backend

- [ ] `characters` tablosu migrasyonu
- [ ] `conversations` tablosuna `character_id` eklenmesi
- [ ] Default General Friend karakteri otomatik oluşturma (register sırasında)
- [ ] Karakter CRUD endpoint'leri: GET/POST/PUT/DELETE `/characters`
- [ ] `POST /characters` → şablona göre system_prompt otomatik üretimi
- [ ] Custom şablon → Claude Haiku ile system_prompt üretimi
- [ ] Mem0 `agent_id` bazlı memory izolasyonu (bkz. [05-ai-bellek.md](05-ai-bellek.md))
- [ ] Çift Mem0 araması: global + karakter-özel (async paralel)
- [ ] Karakter memory endpoint'leri: GET/DELETE `/characters/:id/memories`
- [ ] Proaktif bildirim sistemi karakter bazında güncelleme
- [ ] Karakter bazında bildirim tercihleri

### iOS + Android

- [ ] Karakter listesi ekranı (grid view, avatar rengi, son konuşma zamanı)
- [ ] Karakter oluşturma akışı: şablon seç → isim ver → prompt önizle → avatar seç
- [ ] Custom şablon akışı: açıklama yaz → Haiku prompt üretir → onayla/düzenle
- [ ] Chat ekranı üst bar: aktif karakter göster + tıkla = değiştir
- [ ] Konuşma listesi karakter filtreleme
- [ ] Her karakter için ayrı Memory ekranı
- [ ] Karakter düzenleme (isim, sistem promptu, avatar)
- [ ] Premium gate: 2. karakter oluşturulunca upgrade prompt

---

## Faz 10 — Fitness Entegrasyonu (Sadeleştirilmiş)

> **Karar:** Ember bir fitness tracker değil — fitness **coach**. Workout logging ve grafiklerin büyük
> kısmı Fitness Coach karakteri + Mem0 ile karşılanıyor. Sadece kilo trendi için minimal DB tutulur,
> egzersiz görselleri için ExerciseDB API kullanılır (veri saklanmaz, sadece link).

**Hedef:** AI fitness anamnezini biliyor, egzersiz görsellerini gösterebiliyor, kilo trendini takip edebiliyor.

**Başarı kriteri:** "Bugün ne yapacağım?" sorusuna Mem0'dan kişiselleştirilmiş cevap geliyor, egzersiz GIF'i görüntülenebiliyor.

### Backend

- [ ] `body_measurements` tablosu: user_id, date, weight_kg, body_fat_pct, notes
- [ ] CRUD endpoint'leri: body_measurements (POST / GET)
- [ ] ExerciseDB API proxy endpoint'i: `GET /exercises/search?q=bench+press` → egzersiz adı + GIF URL döner
- [ ] Fitness verisi Mem0'ya yazılır (Fitness Coach karakteri üzerinden):
  - Antrenman notu: "2026-02-23: Göğüs, bench 5×5×85kg, incline 3×10×60kg"
  - PR kaydı: "Squat PR: 100kg (2026-01-15)"
  - Alışkanlık: "Haftada 4 gün antrenman yapıyor"

### iOS + Android

- [ ] Vücut ölçüm giriş ekranı (kilo + vücut yağ yüzdesi — basit form)
- [ ] Kilo trend grafiği (tek grafik, `body_measurements` tablosundan)
- [ ] Chat'te egzersiz kartı render: AI bir egzersiz adı içeren plan dönünce app ExerciseDB'den GIF + link çeker
- [ ] Egzersiz kartı UI:
  ```
  ┌─────────────────────────────────┐
  │  [GIF animasyon — ExerciseDB]   │
  │  Bench Press                    │
  │  5 × 5 × 85kg                   │
  │  ▶ Nasıl yapılır?               │
  └─────────────────────────────────┘
  ```
- [ ] Chat'te "antrenman bitti" mesajı → AI Mem0'a kaydeder (yapılandırılmış log gerekmez)

> **ExerciseDB:** 1300+ egzersiz, GIF + video linki, ücretsiz.
> Veriler bizde saklanmaz — sadece görsel lookup için kullanılır.

---

## Faz 11 — Cila ve Yayın

**Hedef:** App Store + Play Store'da yayın.

**Başarı kriteri:** Mağazalarda uygulama aktif, review geçildi.

### Yapılacaklar

- [ ] Loading state'ler ve skeleton ekranlar (tüm liste ekranları)
- [ ] Boş durum ekranları + Lottie animasyonları
- [ ] Hata mesajları (kullanıcı dostu, teknik değil)
- [ ] Offline durum yönetimi (bağlantı yoksa bilgi ver)
- [ ] Haptic feedback tüm aksiyonlarda (iOS: `UIImpactFeedbackGenerator`, Android: `HapticFeedback`)
- [ ] Dark mode final polish (kontrast kontrolü)
- [ ] App ikonu + splash screen animasyonu
- [ ] iOS: `LaunchScreen.storyboard` native splash
- [ ] Android: `SplashScreen` API (API 31+)
- [ ] App Store görselleri (screenshot) + açıklama metni (EN)
- [ ] Play Store görselleri + açıklama metni (EN)
- [ ] Gizlilik politikası sayfası (URL gerekli)
- [ ] Veri export özelliği (tüm memories + mesajlar JSON)
- [ ] App Store Connect → Submit for Review
- [ ] Google Play Console → Production track yayını

---

## Faz 12 — Post-Launch

İlk yayından sonra:

- [ ] Kullanıcı feedback toplama (in-app feedback butonu)
- [ ] Crash analytics (Firebase Crashlytics — iOS + Android)
- [ ] Performance monitoring (Firebase Performance)
- [ ] A/B test: onboarding soru sırası
- [ ] Mem0 self-hosted'a geçiş değerlendirmesi (bkz. [05-ai-bellek.md](05-ai-bellek.md#self-hosted-geçiş))
- [ ] Çoklu dil desteği UI'da (TR/EN toggle)
- [ ] Sessiz saatler ayarı (bildirim alma / almama saat aralığı)
- [ ] Widget (iOS: WidgetKit, Android: Glance) — home screen günlük özet
- [ ] Gerçek zamanlı sesli arama (WebRTC + streaming STT + TTS, < 1.5s latency) — değerlendiriliyor
