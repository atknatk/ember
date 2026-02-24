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
| Claude Sonnet (chat + vision) | ~600 mesaj × avg 3k token (system prompt + context + memories) | ~$7.20 |
| Claude Haiku (intent + bildirim) | ~300 işlem | ~$0.15 |
| ElevenLabs TTS | ~4.5k karakter/gün → 135k/ay | ~$0.29 (Creator plan payı) |
| OpenAI Whisper STT | ~90 dk/ay | ~$0.54 |
| **AI Toplam** | | **~$8.18/ay** |

### Altyapı Maliyeti (AWS payı)

100 kullanıcı senaryosunda AWS ~$46/ay → kullanıcı başına ~$0.46/ay

### Toplam COGS

| Maliyet Kalemi | USD/ay |
|---------------|--------|
| AI API | $8.18 |
| AWS altyapı payı | $0.46 |
| Mem0.ai (cloud) | ~$0.10 |
| Firebase FCM | $0.00 |
| **Toplam COGS** | **~$8.74** |

### Brüt Marj

| Gelir | COGS | Brüt Marj |
|-------|------|-----------|
| $9.99 | $8.74 | **$1.25 (%13)** |

> **Uyarı:** %13 brüt marj sürdürülebilir değil. Aşağıdaki risk analizi ve fiyatlandırma önerilerine bakınız.

---

## Ölçek Senaryosu

| Kullanıcı | Premium (%12 conversion) | Aylık Gelir | Aylık AWS | AI API | Net |
|-----------|------------------------|------------|-----------|--------|-----|
| 100 | 12 | $102 | $46 | $105 | **-$49** |
| 500 | 60 | $510 | $120 | $524 | **-$134** |
| 1,000 | 120 | $1,019 | $200 | $1,049 | **-$230** |
| 5,000 | 600 | $5,094 | $600 | $5,244 | **-$750** |

*Düzeltme: Önceki tahminler %60 conversion varsayıyordu. Sektör ortalaması %5-15. Tabloda %12 kullanıldı.*

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
| 1 karakter (General Friend) | Baz maliyet ~$8.74/ay |
| +1 English Teacher (aktif) | +~$3.50/ay (chat + memory) |
| +1 Therapist (aktif) | +~$3.50/ay |
| 3 aktif karakter | **~$15.74/ay COGS** |

> **Kritik:** 3 aktif karakter kullanan premium kullanıcı $15.74 COGS üretir, $8.49 net gelire karşı. Bu kullanıcılar zararda.

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

---

## Risk Analizi ve Fiyatlandırma Önerileri

### Tespit Edilen Riskler

1. **COGS > Gelir riski:** Mevcut $9.99 fiyatla, tek karakter bile %13 marj bırakır. Çoklu karakter kullanan kullanıcılar net zararda.
2. **Conversion rate:** Sektör ortalaması %5-15 (Replika ~%8, Character.AI <%5, ChatGPT Plus ~%6). %60 varsayımı 4-12x yüksek.
3. **Sınırsız karakter:** Unlimited karakter $9.99'da finansal olarak sürdürülemez.

### Önerilen Aksiyonlar

| Aksiyon | Açıklama |
|---------|----------|
| **Fiyat artışı** | Premium: $9.99 → $14.99/ay ($11.99 yıllık planla) |
| **Karakter limiti** | Premium'da 3 aktif karakter, Premium+ ($19.99) unlimited |
| **Prompt caching agresif kullan** | Anthropic prompt caching ile %30-50 token tasarrufu → COGS $5-6'ya düşer |
| **Claude Haiku for non-critical** | Fitness Coach, Career Coach → Haiku ile çalıştır (Sonnet'in 1/10 maliyeti) |
| **Usage-based pricing** | Ağır kullanıcılar için mesaj paketi: 1000 mesaj/ay base + $0.01/extra mesaj |
| **Mem0 self-host** | Phase 12'de Mem0 Cloud → self-hosted geçiş, $0.10/user/ay tasarruf |

### Revize Break-Even Analizi

**Senaryo A — $14.99 fiyat, prompt caching:**
- COGS: ~$5.50/user/ay (prompt caching ile)
- Net gelir: $12.74 (iOS/Android %15 komisyon sonrası)
- Brüt marj: **$7.24 (%57)** — sürdürülebilir

**Senaryo B — $9.99 fiyat, Haiku for secondary characters:**
- COGS: ~$4.80/user/ay (secondary chars Haiku)
- Net gelir: $8.49
- Brüt marj: **$3.69 (%43)** — marjinal ama kabul edilebilir

**Önerilen strateji:** Senaryo A (fiyat artışı + prompt caching). Değer kanıtlandıktan sonra kullanıcılar $14.99'u ödemeye hazır.
