# 15 — Fiyatlandırma

## Öneri: Freemium + Aylık Abonelik

### Neden Freemium?

- Giriş engeli sıfır → viral büyüme ve ağızdan ağıza yayılma
- Kullanıcı önce değeri görür, sonra öder (LTV artar)
- AI companion ürünleri premium öncesi "bağ" kurulması gerektirir
- ChatGPT ve Perplexity'nin kanıtladığı model

---

## Tier Yapısı

### Ücretsiz Plan

**Amaç:** Değeri hissettir, bağ kur.

| Özellik | Limit |
|---------|-------|
| Aylık mesaj | 100 mesaj |
| Bellek (Memory) | 50 memory |
| Fotoğraf analizi | 5 fotoğraf/ay |
| Karakter | Sadece General Friend (1 karakter) |
| Proaktif bildirimler | Yok |
| Sesli yanıt / mesaj | Yok |
| Cihaz entegrasyonu | Yok |
| Konuşma geçmişi | Sınırsız (süresiz saklanır) |

**Upgrade tetikleyicisi:** 100 mesaja ulaşınca "Bu ay limitine ulaştın" banner'ı görünür.
Kullanıcı aktif kullanmaya başladıktan sonra premium sunulur — ondan önce değil.

---

### Premium Plan — $9.99/ay

**Amaç:** Gerçek bir AI arkadaş deneyimi, tüm özellikler açık.

| Özellik | Premium |
|---------|---------|
| Mesaj | Sınırsız |
| Bellek | Sınırsız |
| Fotoğraf analizi | Sınırsız |
| **Karakterler** | **Sınırsız (şablonlar + custom)** |
| Proaktif bildirimler | ✓ |
| Sesli yanıt (TTS) | ✓ |
| Sesli mesaj (STT) | ✓ |
| Cihaz entegrasyonu | ✓ |
| Partner bağlantısı | ✓ |
| Memory export (JSON) | ✓ |
| Öncelikli destek | ✓ |
| Konuşma geçmişi | Sınırsız |

**Fiyat:** $9.99/ay veya $79.99/yıl (~33% indirim).

---

### Yıllık Plan — 79.99 USD / yıl

Aylık ücretin ~%33 altında.
App Store / Play Store "En İyi Değer" rozeti için önerilen oran.

---

## Maliyet Analizi (COGS) — Premium Kullanıcı Başına

### Senaryo: Orta Aktif Kullanıcı

- 20 mesaj/gün (chat)
- 3 fotoğraf/hafta
- 5 TTS yanıt/gün
- 3 STT mesaj/gün

### AI API Maliyeti

| Servis | Kullanım | Maliyet/ay |
|--------|---------|-----------|
| Claude Sonnet (chat + vision) | ~600 mesaj × avg 1.5k token | ~$4.50 |
| Claude Haiku (intent + bildirim) | ~300 işlem | ~$0.15 |
| ElevenLabs TTS | ~4.5k karakter/gün → 135k/ay | ~$0.29 (Creator plan payı) |
| OpenAI Whisper STT | ~90 dk/ay | ~$0.54 |
| **AI Toplam** | | **~$5.48/ay** |

### Altyapı Maliyeti (AWS payı)

100 kullanıcı senaryosunda AWS ~$46/ay → kullanıcı başına ~$0.46/ay

### Toplam COGS

| Maliyet Kalemi | USD/ay |
|---------------|--------|
| AI API | $5.48 |
| AWS altyapı payı | $0.46 |
| Mem0.ai (cloud) | ~$0.10 |
| Firebase FCM | $0.00 |
| **Toplam COGS** | **~$6.04** |

### Brüt Marj

| Gelir | COGS | Brüt Marj |
|-------|------|-----------|
| $9.99 | $6.04 | **$3.95 (%40)** |

%40 brüt marj başlangıç için makul. Kullanıcı sayısı arttıkça (AWS ölçeği, Mem0 hacim indirimi)
marj %55–65'e çıkabilir.

---

## Ölçek Senaryosu

| Kullanıcı | Aylık Gelir | Aylık AWS | AI API (toplam) | Net |
|-----------|------------|-----------|-----------------|-----|
| 100 | $999 | $46 | $548 | ~$395 |
| 500 | $4,995 | $120 | $2,740 | ~$2,115 |
| 1,000 | $9,990 | $200 | $5,480 | ~$4,210 |
| 5,000 | $49,950 | $600 | $27,400 | ~$21,850 |

*Tahminler %60 premium conversion ve orta aktif kullanım varsayar.*

---

## Freemium → Premium Dönüşüm Stratejisi

### Tetikleyiciler

1. **Limit barrier:** "100 mesajın doldu, bu ay daha fazlası için Premium'a geç"
2. **Feature gate:** Proaktif bildirim geldiğinde "Bu özellik Premium'da"
3. **Value moment:** 5. günde "AI seni tanımaya başladı — tüm özellikleri aç"
4. **Nudge:** 7. günde bir kez in-app "Premium dene: 7 gün ücretsiz"

### 7 Günlük Ücretsiz Deneme

Premium'a geçişte 7 gün trial (kredi kartı gerekli ama çekim yok).
Trial bitmeden 2 gün önce push notification: "Deneme süren bitiyor"

---

## Fiyat Lokalizasyonu

Uygulama worldwide. Türkiye özel lokalizasyon yok.

| Ülke | Aylık Fiyat |
|------|------------|
| ABD | $9.99 |
| Almanya / AB | €9.49 |
| UK | £8.49 |
| Japonya | ¥1,500 |
| Avustralya | A$15.99 |

App Store Connect ve Google Play Console otomatik kur dönüşümü yapar.
Büyük pazarlarda fiyat araştırması yapılarak güncellenir.

---

## Couple Plan

Partner bağlantısı açıldığında:

**Couple Plan — $14.99/ay**
- 2 kullanıcı aynı ödeme altında (2 × $9.99 yerine $14.99)
- Her kullanıcı tüm premium özelliklere sahip
- Partner sync özellikleri aktif
- ~%25 indirim çiftler için

Bu, çiftlerin ayrı ayrı ödeme yapması yerine birlikte ödeme yapmasını sağlar.

---

## Karakter Sistemi Maliyet Etkisi

Her ek karakter kullanıcı başına maliyet artışı yaratır:

| Senaryo | COGS Etkisi |
|---------|------------|
| 1 karakter (General Friend) | Baz maliyet ~$6.04/ay |
| +1 English Teacher (aktif) | +~$2.50/ay (chat + memory) |
| +1 Therapist (aktif) | +~$2.50/ay |
| 3 aktif karakter | ~$11/ay COGS |

Premium fiyatı ($9.99) tek aktif karakter için makul.
Çok karakterli yoğun kullanıcılar için marj düşer ama retention artar.
Dengeler: premium tier fiyatı ileride $12.99'a çıkarılabilir (değer net ise).

---

## App Store / Play Store Kısıtları

- **iOS:** App Store Commission %30 (küçük geliştiriciler için %15 indirilebilir)
- **Android:** Google Play Commission %15 (ilk $1M gelir için)

Komisyon sonrası gerçek gelir:

| Platform | Aylık $9.99 | Komisyon | Net |
|----------|------------|---------|-----|
| iOS | $9.99 | %15 | $8.49 |
| Android | $9.99 | %15 | $8.49 |

*Küçük geliştirici (yıllık <$1M) %15 komisyon programı varsayılıyor.*
