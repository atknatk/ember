# 01 — Vizyon ve Hedefler

## Problem

Mevcut AI araçları (ChatGPT, Gemini vb.) her konuşmayı sıfırdan başlatır.
Sizi tanımaz, hatırlamaz, sizi aramaz. Pasif araçlardır — siz onlara gidiyorsunuz.

**Sonuç:** Kişiselleşme yok, süreklilik yok, proaktiflik yok.

---

## Vizyon

> "Herkesin kendine özel, kendini tanıyan, büyüyen bir AI asistanı olsun."

- **Öğrenir:** Her konuşmadan yeni şeyler öğrenir ve saklar
- **Hatırlar:** "Geçen hafta iş seyahatinden bahsetmiştin, nasıl geçti?" diyebilir
- **Proaktiftir:** Sen aramasan da ulaşır — sabah günaydın, gece "uyu artık"
- **Bütünseldir:** Fitness, stres, iş, ilişkiler, uyku — tek yerden
- **Uzmanlaşır:** Farklı rollerde karakterler oluşturulabilir (İngilizce öğretmeni, koç, terapist...)

---

## Konumlandırma

**Ember bir kişisel asistan — romantik companion değil.**

Piyasadaki büyük oyuncular (Replika, Nomi, Character.AI) romantic companion veya
entertainment odaklı. Ember'ın hedefi farklı:

- Seni tanıyan, öğrenen, büyüyen bir **yaşam asistanı**
- Sabah kahvaltını hatırlayan, akşam nasıl geçtiğini soran bir **kişisel yardımcı**
- Fitness koçu, dil öğretmeni, kariyer danışmanı — tek uygulamada **uzman karakterler**

Romantik companion isteyen kullanıcılar bunu bir karakter olarak ekleyebilir;
bu, ana ürünün bir add-on'u, tanımı değil.

---

## Hedef Kitle

**Birincil kullanıcı:**
25–40 yaş, kendini geliştirmek isteyen, AI teknolojisine açık, mobil öncelikli bireyler.

**Değil:** Yalnızlık için AI partner arayan kullanıcılar (bu segment kasıtlı hedeflenmiyor).

---

## Kullanım Senaryoları

### Senaryo 1 — Sabah Brifingi
Kullanıcı sabah uyandığında Ember proaktif mesaj atmış:
"Günaydın! Bugün salı toplantın var, önceki haftaki notlarına bakayım mı?
Ayrıca dün akşam 3 bardak su içmiştin, bugün daha fazla içmeyi dene."

### Senaryo 2 — Fitness Takipçisi
Atakan spor salonundan çıkar, fotoğraf çekip gönderir: "Bugün omuz günüydü."
AI önceki haftalarda öğrendiklerini hatırlayarak yorum yapar, squat PR'ından bahseder.

### Senaryo 3 — Uzman Karakter
Kullanıcı "Sarah" adını verdiği İngilizce öğretmeni karakteriyle konuşur.
Sarah sadece onun dil öğrenim geçmişini bilir: hangi kelimeleri karıştırdığını,
B2 seviyesinde olduğunu, konuşma pratiğini sevdiğini.
Günlük asistan bu konuşmaları görmez.

### Senaryo 4 — Günlük Organizasyon
"Yarın 9'a toplantı ekle ve sabah 7:30'a alarm kur."
Ember takvime yazar, alarmu kurar, onayı gösterir.

### Senaryo 5 — Çift Kullanımı
Atakan ve Tuvik birbirini partner olarak bağlar.
AI her ikisini ayrı öğrenir, opsiyonel olarak birbirlerinin anonim progress bilgisini paylaşır.
"Tuvik bu hafta 3 antrenman yaptı, sen ne yapıyorsun?"

### Senaryo 6 — Gece Uyku Kaçkını
Saat 23:45. Kullanıcı hala mesaj atıyor.
Ember kullanıcının uyku düzenini hatırlar ("07:00'de kalkmayı hedefliyor"), proaktif yazar:
"Uyu artık, sabah erken kalkman lazım."

---

## Rekabet Analizi

| Özellik | ChatGPT | Replika | Pi | Anima | **Ember** |
|---------|---------|---------|-----|-------|-----------|
| Deep long-term memory | Sınırlı | Var | Zayıf (~100 turn) | Yok | **Mem0 — en derin** |
| Proaktif bildirim | Hayır | Hayır | Hayır | Var (shallow) | **Var (Mem0-driven)** |
| Multi-character + izole memory | Yok | Yok | Yok | Yok | **Var — benzersiz** |
| Device integration (takvim/alarm) | Yok | Yok | Yok | Yok | **Var — benzersiz** |
| Fotoğraf analizi | Evet | Hayır | Hayır | Hayır | **Var** |
| Personal assistant odak | Kısmen | Hayır | Kısmen | Hayır | **Ana ürün** |
| Romantic companion | Hayır | Ana ürün | Hayır | Kısmen | Opsiyonel karakter |
| App Store yaş sınırı | 4+ | 17+ | 4+ | 17+ | **4+ (12+)** |

**Ember'ın boşluğu:** Piyasada gerçek long-term memory + proactive + expert characters
+ device integration kombinasyonunu sunan başka bir uygulama yok.

---

## Başarı Metrikleri

- Kullanıcı günde ortalama kaç mesaj atıyor?
- Proaktif bildirimlere tıklanma oranı
- Haftalık aktif kullanım oranı
- Memory büyüme hızı (AI ne kadar öğreniyor?)
- 30. gün retention: Uygulama hala kullanılıyor mu?
- Karakter oluşturma oranı (premium feature adoption)
