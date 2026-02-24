# 14 — Tasarım Sistemi

## Felsefe

Uygulama bir arkadaşla konuşma hissi vermeli — soğuk, steril bir araç değil.
Tasarım sıcak ama minimalist. Animasyonlar var ama gösteriş için değil, anlam için.

**3 temel prensip:**
1. **Samimi** — UI, AI'ın arkadaşça tonunu destekler. Sert köşeler yok, sert renkler yok.
2. **Odaklanmış** — Her ekranda tek bir ana aksiyon. Karmaşık menü yok.
3. **Canlı** — Mesaj gelirken hayat var. Beklerken animasyon var. Duygusal tepki var.

---

## Renk Sistemi

### Ana Palet

```
Ana renk (Primary):        #5B4FE8  — Derin mor-indigo
                           Türev: 4B3FD8 (pressed), 6B5FF8 (hover)

Vurgu (Accent):            #FF6B6B  — Sıcak mercan
                           Proaktif bildirimler, özel günler için

Nötr (Background):         #0F0F14  — Neredeyse siyah, tam siyah değil
Yüzey (Surface):           #1A1A24  — Koyu gece mavisi-siyahı
Yüzey 2 (Surface2):        #22223A  — Kartlar, input alanları
Yüzey 3 (Surface3):        #2C2C4A  — Hover, aktif state

Metin — Birincil:          #F0F0F8  — Beyaza yakın, göz yormayan
Metin — İkincil:           #9090B0  — Soluk mor-gri
Metin — Devre dışı:        #5A5A7A  — Düğmeler, placeholder

Başarı:                    #4CAF87  — Yeşil (onay, tamamlandı)
Uyarı:                     #F5A623  — Amber
Hata:                      #E85B5B  — Kırmızı
```

**Neden koyu tema?** Arkadaşla gece geç saatlerde konuşulur.
Göz yormayan koyu arka plan konuşma deneyimini uzatır.
Ayrıca ChatGPT / iMessage dark mode referansıyla aşinalık yaratır.

---

### Gradient Kullanımı

```
Onboarding splash:  #5B4FE8 → #FF6B6B  (mor → mercan, 135°)
AI mesaj balonu:    #1E1E35 → #252545  (hafif gradient, cansız değil)
CTA buton:          #5B4FE8 → #7B6FF8  (soldan sağa)
```

---

## Tipografi

**Font:** Inter (Google Fonts — ücretsiz, Türkçe tam destek)

| Kullanım | Font | Ağırlık | Boyut | Satır Aralığı |
|----------|------|---------|-------|---------------|
| Büyük başlık | Inter | 700 Bold | 28px | 1.2 |
| Ekran başlığı | Inter | 600 SemiBold | 22px | 1.3 |
| Bölüm başlığı | Inter | 600 SemiBold | 16px | 1.4 |
| Mesaj metni | Inter | 400 Regular | 15px | 1.6 |
| İkincil metin | Inter | 400 Regular | 13px | 1.5 |
| Etiket / chip | Inter | 500 Medium | 12px | 1.4 |
| Mikro metin | Inter | 400 Regular | 11px | 1.4 |

**Türkçe özellik:** ğ, ü, ş, ı, ö, ç harfleri Inter'da tam desteklenir.

---

## Boşluk Sistemi (8px Grid)

```
4px   — İkon ile metin arası, küçük padding
8px   — Chip iç padding, küçük boşluk
12px  — Liste item padding (dikey)
16px  — Kart iç padding, standart padding
20px  — Ekran kenar boşluğu (horizontal)
24px  — Bölümler arası boşluk
32px  — Büyük bölüm ayırıcı
48px  — Ekran üst padding (safe area sonrası)
```

---

## Köşe Yarıçapı

```
4px   — Küçük chip, badge
12px  — Input alanları, küçük kartlar
16px  — Mesaj balonları
20px  — Ana kartlar, modal'lar
28px  — Büyük CTA butonları (pill şekli)
999px — Tam yuvarlak (avatar, ikon buton)
```

---

## Chat Ekranı Tasarımı

### Mesaj Balonları

```
Kullanıcı mesajı (sağ):
   ┌────────────────────────┐
   │ Bugün antrenman yaptım │  ← #5B4FE8 arka plan
   │ ama çok yoruldum.      │  ← Beyaz metin
   └────────────────────────┘ ← Alt sağ köşe kesik (karakteristik)
                          14:32 ✓✓

AI mesajı (sol):
┌────────────────────────────────┐
│ Süper! Peki ne kadar dinlendin │  ← Surface2 arka plan
│ sonra? Uyku önemli...          │  ← Birincil metin
└────────────────────────────────┘
14:33
```

### Streaming Animasyonu

AI yanıt üretirken 3 nokta ile "yazıyor" animasyonu:

```
●  ●  ●   (sol → sağ hafif yukarı/aşağı, 400ms döngü)
```

Metin stream edilirken karakter karakter değil, kelime kelime gösterilir
(daha doğal ve az "robotik" hissettiren).

### Fotoğraf Mesajı

```
┌──────────────────────┐
│  [Fotoğraf önizleme] │
│  📷 Yükleniyor...   │  ← Progress bar
└──────────────────────┘
→ Yüklendi → Analiz geliyor...
```

---

## Ana Ekranlar

### Home Ekranı

```
┌─────────────────────────────┐
│  Günaydın, Atakan ☀️        │  ← Günün saatine göre selamlama
│  Pazartesi, 23 Şubat        │
│                             │
│  ┌─────────────────────┐    │  ← Günlük özet kartı (AI üretir)
│  │ Bugün: 3 hedef var  │    │
│  │ Son antrenman: 2 gün│    │
│  └─────────────────────┘    │
│                             │
│  Son konuşmalar             │
│  ┌─────────────────────┐    │
│  │ 💬 Dün · 3 mesaj    │    │
│  └─────────────────────┘    │
│  ┌─────────────────────┐    │
│  │ 💬 Pzt · Antrenman  │    │
│  └─────────────────────┘    │
│                             │
│  [+ Yeni Karakter Ekle]      │  ← Karakter oluşturma (FAB)
└─────────────────────────────┘
```

### Memories Ekranı

```
┌─────────────────────────────┐
│  ← Hakkımda ne biliyor?     │
│                             │
│  Fitness                    │
│  ┌─────────────────────┐    │
│  │ Squat PR: 100 kg   ×│    │  ← × ile silinebilir
│  │ Sol dizi hassas    ×│    │
│  └─────────────────────┘    │
│                             │
│  Beslenme                   │
│  ┌─────────────────────┐    │
│  │ Kahvaltıda yulaf   ×│    │
│  │ Brokoli sevmez     ×│    │
│  └─────────────────────┘    │
└─────────────────────────────┘
```

---

## Animasyon Sistemi

### İlkeler

1. **Amaçlı:** Her animasyon kullanıcıya bir bilgi verir (yükleniyor, tamamlandı, hata)
2. **Hızlı:** Ana geçişler 250–350ms. 400ms üzeri sadece onboarding/splash
3. **Yumuşak:** Easing: `easeInOutCubic` standart, spring animasyon kritik aksiyonlar için
4. **Doğal:** Fizik tabanlı — elementler "yapışır" veya "fırlar", sert durmuyor

---

### Geçiş Animasyonları

| Ekran Geçişi | Animasyon | Süre |
|-------------|-----------|------|
| Home → Chat | Slide up + fade | 300ms |
| Chat → Back | Slide down + fade | 250ms |
| Onboarding slide | Horizontal slide + scale | 400ms |
| Modal açılış | Bottom sheet spring | 350ms |
| Modal kapanış | Bottom sheet dismiss | 250ms |

---

### Mikro Animasyonlar

| Element | Animasyon | Tetikleyici |
|---------|-----------|-------------|
| Send butonu | Scale 1.0 → 0.85 → 1.0 | Tap |
| AI "yazıyor" | 3 nokta bounce | Stream başlangıcı |
| Memory silme | Slide out + fade | Swipe left / × tap |
| Mesaj geldi | Slide up + fade in | Yeni mesaj |
| Hata mesajı | Shake (3x, 8px) | Form submit hatası |
| Başarı | Check mark çiz animasyonu | İşlem tamamlandı |
| Bildirim badge | Scale pop (spring) | Yeni bildirim |

---

### Onboarding Animasyonları

- **Splash:** Logo merkeze doğru büyür (scale 0.3 → 1.0), 600ms, spring
- **Welcome cards:** Kartlar 3D perspektifle eğilir, swipe sırasında paralaks
- **Soru geçişi:** Yukarıdan gelir, cevapla birlikte yukarı gider
- **Tamamlandı:** Konfeti efekti (riveanimation veya Lottie)

---

### Lottie Animasyonları (Seçili Ekranlar)

| Ekran | Animasyon | Kaynak |
|-------|-----------|--------|
| Onboarding tamamlandı | Konfeti/kutlama | LottieFiles.com |
| Boş chat ekranı | Hafif dalga/parıltı | Özel |
| Yükleniyor | Nabız atışı | Özel |
| Hata | Hafif sarsılma | LottieFiles.com |

---

## İkon Stili

**iOS:** SF Symbols — sistem ikon seti, otomatik dark/light uyumu.
**Android:** Material Icons — outlined (normal) / filled (aktif state).

Stil: Line/outlined icons, 24px standart. Filled varyant: aktif tab, seçili state.

| Kavramsal İkon | iOS (SF Symbols) | Android (Material) |
|----------------|------------------|-------------------|
| Chat / Konuşmalar | `bubble.left.and.bubble.right` | `chat_bubble_outline` |
| Memories | `brain` | `psychology` |
| Profil | `person.circle` | `account_circle` |
| Bildirimler | `bell` | `notifications_none` |
| Fotoğraf gönder | `camera` | `camera_alt` |
| Ses kaydı | `mic` | `mic_none` |
| TTS oynat | `speaker.wave.2` | `volume_up` |
| Sil | `trash` | `delete_outline` |
| Liste navigasyon | `chevron.right` | `chevron_right` |

---

## Haptic Feedback

| Aksiyon | iOS | Android |
|---------|-----|---------|
| Mesaj gönder | `UIImpactFeedbackGenerator(style: .light)` | `HapticFeedbackConstants.KEYBOARD_TAP` |
| Memory silindi | `UIImpactFeedbackGenerator(style: .medium)` | `HapticFeedbackConstants.LONG_PRESS` |
| Hata | `UIImpactFeedbackGenerator(style: .heavy)` | `HapticFeedbackConstants.REJECT` |
| Onay / başarı | `UISelectionFeedbackGenerator` | `HapticFeedbackConstants.CONFIRM` |
| Bildirim geldi | `UINotificationFeedbackGenerator(type: .success)` | System notification haptic |

---

## Dark Mode

Dark mode varsayılandır. Açık tema Faz 2'de eklenebilir.

**iOS:** `@AppStorage("colorScheme")` ile kalıcı tercih, `.preferredColorScheme(.dark)` ile uygulama başlangıcında sabit dark mode.
**Android:** `AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)` ile uygulama genelinde dark mode.

Faz 2'de: sistem temasına bağlama veya manuel toggle eklenebilir.

---

## Erişilebilirlik

- Minimum dokunma hedefi: 44×44px (iOS HIG + Android standard)
- Kontrast oranı: AA seviyesi (4.5:1 metin, 3:1 büyük metin)
- Semantic labels: iOS `accessibilityLabel`, Android `contentDescription` — tüm ikonlara eklenir
- Font scaling: iOS Dynamic Type, Android Font Scale — layout max 1.5x ile test edilmeli

---

## Uygulama İkonu

**Konsept:** Derin mor zemin üzerinde soyut bir "bağlantı" veya "nabız" sembolü.
Sade, akılda kalıcı, uygulamanın sıcak + teknolojik kimliğini yansıtır.

**Boyutlar:**
- iOS: 1024×1024px (App Store), 180×180px (iPhone), 167×167px (iPad)
- Android: 512×512px (Play Store), Adaptive icon (foreground + background layer)

**Splash screen:** Uygulama açılışında logo merkeze oturur, arka plan #0F0F14'e dönüşür.
iOS: `LaunchScreen.storyboard` ile native splash — beyaz flash olmadan.
Android: SplashScreen API (Android 12+) + `windowSplashScreenBackground` teması ile.
