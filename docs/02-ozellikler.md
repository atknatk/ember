# 02 — Özellikler ve Kullanıcı Hikayeleri

## MVP Özellikleri (v1.0)

### Kullanıcı Hesabı
- E-posta + şifre ile kayıt ve giriş
- Profil fotoğrafı yükleme
- Hesap silme (GDPR)

### Onboarding
- İlk açılışta 5–7 kısa kişiselleştirme sorusu
- Sorular: meslek, yaşam tarzı, günlük rutinler, hedefler, ilgi alanları, uyku saatleri
- Her yanıt Mem0.ai'a "başlangıç belleği" olarak eklenir
- AI ilk konuşmadan itibaren kişiselleştirilmiş olur

### Akıllı Chat
- ChatGPT benzeri sohbet arayüzü
- Yanıtlar anlık (streaming — karakter karakter)
- AI önceki konuşmaları ve öğrendiklerini hatırlar
- Markdown render (kalın, liste, başlık)
- Konuşma başlıkları AI tarafından otomatik oluşturulur

### Fotoğraf Gönderme
- Galeriden veya kameradan fotoğraf seçme
- Yemek fotoğrafı → kalori ve makro besin tahmini
- Aktivite / ortam fotoğrafı → AI yorumlar ve konuşmaya dahil eder
- Fotoğraflar kalıcı olarak saklanır (AWS S3)

### Bellek Sistemi
- Her konuşmadan AI yeni şeyler öğrenir (Mem0.ai ile otomatik)
- Kullanıcı "ne biliyorsun benim hakkımda?" diye sorabilir
- Ayrı ekranda tüm bilgiler listelenir
- Kullanıcı istediği belleği silebilir

### Proaktif Bildirimler
- Sabah check-in (08:00–09:30, bugün henüz mesaj yoksa)
- Öğlen nudge (14:00–15:30, bugün hiç aktif değilse)
- Akşam yansıma (20:00–21:00)
- Uyku hatırlatması (23:00+, son 1 saatte aktifse)
- Bildirime tıklayınca chat açılır, AI bağlamı hazır

### Bellek Şeffaflık Ekranı
- "AI Seni Ne Biliyor?" ekranı
- Kategorilere ayrılmış bellek listesi
- Her belleği silme butonu

---

## Sonraki Fazlardaki Özellikler

### Sesli Deneyim (Faz 5)
- Sesli mesaj: kullanıcı konuşur → Whisper metne çevirir → chat'e eklenir
- Sesli yanıt: AI yanıtını ElevenLabs Flash v2.5 ile seslendirir
- Gerçek zamanlı sesli arama: LiveKit + Deepgram Nova-3 (Faz 12)

### Partner Bağlantısı (Faz 8)
- İki kullanıcı birbirini partner olarak bağlayabilir
- Opsiyonel anonim ilerleme paylaşımı
- Çiftler için motivasyon mekanizması

### Fitness Entegrasyonu (Faz 10)
- Vücut ölçümleri takibi (kilo, yağ oranı vb.)
- Fitness Coach karakteri + Mem0 ile egzersiz ve beslenme takibi
- ExerciseDB API: hareket görselleri / GIF'leri (veri saklanmaz)

### Web Versiyonu
- Karar: Yok — sadece iOS + Android native uygulama

---

## Kullanıcı Hikayeleri

### Kayıt ve Onboarding

**Hikaye:** Kullanıcı olarak uygulamaya ilk kez girdiğimde AI arkadaşımın beni hemen tanıması
için birkaç kısa soruya cevap vermek istiyorum.

Kabul kriterleri:
- Onboarding 3 dakikadan kısa sürmeli
- 5–7 soru, kısa ve açık uçlu
- Her yanıt Mem0'a kaydedilmeli
- Tamamlandığında AI ilk mesajında bu bilgilere atıfta bulunabilmeli

---

**Hikaye:** Kullanıcı olarak e-posta ve şifremi kullanarak kayıt olmak istiyorum.

Kabul kriterleri:
- Şifre en az 8 karakter
- Hata mesajları Türkçe ve anlaşılır
- Kayıt sonrası doğrudan onboarding'e yönlendir

---

### Chat

**Hikaye:** Kullanıcı olarak mesaj gönderdiğimde yanıtın hemen gelmeye başlamasını istiyorum.

Kabul kriterleri:
- İlk token 1 saniyeden kısa sürede gelmeli
- Karakterler akarak gelir (streaming)
- Bağlantı kesilirse hata mesajı gösterilmeli

---

**Hikaye:** Kullanıcı olarak AI'ın 3 hafta önce söylediğim bir şeyi hatırlamasını istiyorum.

Kabul kriterleri:
- Mem0'da saklanan bilgi geri çağrılabilmeli
- AI yanıt içinde bu bilgiye doğal şekilde atıfta bulunabilmeli
- Eski konuşmalar silinse bile öğrenilen bilgi Mem0'da kalmalı

---

### Fotoğraf

**Hikaye:** Kullanıcı olarak yemek fotoğrafı gönderdiğimde kalori tahminini öğrenmek istiyorum.

Kabul kriterleri:
- Fotoğraf yükleme 5 saniyeden kısa sürmeli
- Tahmin şunu içermeli: yemek adı, kalori (kcal), protein (g), karbonhidrat (g), yağ (g)
- AI tahminin güven düzeyini belirtmeli (yüksek / orta / düşük)
- Bu bilgi memory'e eklenebilmeli (kullanıcı onayı ile)

---

### Proaktif Bildirimler

**Hikaye:** Kullanıcı olarak sabah uyandığımda AI'ın beni kişiselleştirilmiş günaydın mesajıyla
karşılamasını istiyorum, ama her gün aynı mesajı görmek istemiyorum.

Kabul kriterleri:
- Sabah bildirimi 08:00–09:30 arasında gelmeli (kullanıcının timezone'una göre)
- Aynı gün içinde sadece bir sabah bildirimi
- Her mesaj memory'den türetilmiş, kişiselleştirilmiş
- Bildirime tıklayınca chat açılmalı, AI bağlamı hazır olmalı

---

### Bellek Şeffaflığı

**Hikaye:** Kullanıcı olarak AI'ın benim hakkımda ne bildiğini görmek ve yanlış olanları
silebilmek istiyorum.

Kabul kriterleri:
- Tüm bellek kayıtları listelenmeli
- Her belleğin ne zaman eklendiği görünmeli
- Silme işlemi onay istenmeli
- Silinen bellek Mem0'dan gerçekten kaldırılmalı
