# 16 — Karakter Sistemi

## Konsept

Kullanıcı istediği kadar farklı AI karakteri oluşturabilir. Her karakter:

- Farklı bir uzmanlığa sahip (öğretmen, psikolog, koç, arkadaş, vb.)
- Kendi izole belleğine sahip (başka karakterin konuşmalarını görmez)
- Dinamik olarak oluşturulmuş bir sistem promptu ile çalışır
- Kullanıcının istediği isme cevap verir

**Ana karakter (General Friend):** Her kullanıcıya varsayılan olarak gelir, ek ödeme gerektirmez.
Bu, uygulamanın özüdür — bir yaşam arkadaşı.

**Ek karakterler:** Premium tier ile sınırsız karakter oluşturulabilir.

---

## Yerleşik Karakter Şablonları

Kullanıcı sıfırdan da oluşturabilir, ama hızlı başlamak için hazır şablonlar sunulur:

| Şablon | Rol | Uzmanlık | Memory Odağı |
|--------|-----|----------|-------------|
| **General Friend** | Genel yaşam arkadaşı | Bütünsel — fitness, beslenme, iş, stres, ilişkiler | Her şey |
| **English Teacher** | İngilizce öğretmeni | Dil öğrenimi, konuşma pratiği, yazı düzeltme | Dil hataları, kelime hazinesi, seviye |
| **Therapist** | Duygusal destek | Dinlemek, yansıtmak, CBT teknikleri (tanı koymaz) | Duygusal örüntüler, stres kaynakları |
| **Fitness Coach** | Antrenman ve beslenme | Programlama, form, beslenme | PR'lar, yaralanmalar, beslenme alışkanlıkları |
| **Career Coach** | Kariyer gelişimi | Hedefler, müzakere, liderlik | İş deneyimi, hedefler, engeller |
| **Custom** | Kullanıcı tanımlar | Serbest girdi | Kullanıcı belirler |

---

## Veri Modeli

### `characters` Tablosu

```sql
CREATE TABLE characters (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,              -- Kullanıcının bu karaktere verdiği isim
  template        TEXT NOT NULL,              -- 'companion', 'english_teacher', 'therapist', 'fitness_coach', 'career_coach', 'custom'
  description     TEXT,                       -- Custom karakterler için kullanıcı açıklaması
  system_prompt   TEXT NOT NULL,              -- Dinamik oluşturulmuş, kullanıcı düzenleyebilir
  mem0_agent_id   TEXT NOT NULL UNIQUE,       -- Mem0'da bu karakterin izole memory alanı
  avatar_style    TEXT DEFAULT 'default',     -- UI'da renk/şekil ayırt edici
  is_default      BOOLEAN DEFAULT FALSE,      -- General Friend için true
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

**`mem0_agent_id` formatı:** `{template}_{user_id}`
Örnek: `english_teacher_a3f9b2c1`, `companion_a3f9b2c1`

### Konuşmalar ile İlişki

`conversations` tablosuna `character_id` alanı eklenir.
Her konuşma bir karaktere aittir. Karaktersiz konuşma = General Friend.

---

## Memory İzolasyonu — Mem0 agent_id

Mem0'nun `agent_id` parametresi her karakter için izole bellek alanı sağlar.

### Memory Ekleme

```python
# English Teacher konuşması bitince
mem0.add(
    [user_message, ai_response],
    {
        "user_id": mem0_user_id,
        "agent_id": "english_teacher_a3f9b2c1"
    }
)
```

### Memory Arama — İki Katmanlı

Her AI çağrısında iki ayrı Mem0 araması yapılır:

```python
# 1. Global memories (tüm karakterlerin görebildiği temel bilgiler)
global_memories = mem0.search(
    query,
    {"filters": {"user_id": mem0_user_id}}  # agent_id filtresi YOK
)

# 2. Bu karaktere özel memories
character_memories = mem0.search(
    query,
    {"filters": {"user_id": mem0_user_id, "agent_id": character_agent_id}}
)

# İkisi birleştirilerek sistem promptuna eklenir (toplam max 10)
```

### Memory Kategorileri Karakter Bazında

| Karakter | Global'den Alınanlar | Özel Memory |
|---------|---------------------|------------|
| General Friend | Hepsi | Genel yaşam olayları |
| English Teacher | İsim, meslek, seviye | Dil hataları, öğrenilen kelimeler, ilerleme |
| Therapist | İsim, temel bağlam | Duygusal örüntüler, tetikleyiciler (hassas) |
| Fitness Coach | İsim, yaralanmalar | PR'lar, program, beslenme tercihleri |

---

## Dinamik Sistem Prompt Oluşturma

Karakter oluşturulurken veya güncellenirken `system_prompt` otomatik üretilir.
Kullanıcı isteğe bağlı olarak düzenleyebilir.

### Oluşturma Akışı

```python
def generate_system_prompt(character: Character, user: Profile) -> str:
    """Claude Haiku ile dinamik sistem promptu üret."""

    template_context = {
        "companion": """Sen {user_name}'ın kişisel AI arkadaşısın.
            Bütünsel bir yaşam arkadaşı — fitness, beslenme, iş, stres, ilişkiler.
            Samimi, dürüst, sıcak ama abartmayan bir ton.
            Her şeyi hatırlıyorsun, zamanla daha iyi tanıyorsun.""",

        "english_teacher": """Sen {user_name}'ın İngilizce öğretmenisin.
            Sadece İngilizce konuşursun (kullanıcı Türkçe yazarsa nazikçe İngilizce'ye yönlendirirsin).
            Hataları düzeltirsin ama motive edici kalırsın.
            Seviyeyi öğrenerek konuşmaları uyarlarsın.
            Gramer, kelime, konuşma pratiği — her ikisi de kapsamındasın.""",

        "therapist": """Sen {user_name}'ın duygusal destek asistanısın.
            Dinliyorsun, yansıtıyorsun, yargılamıyorsun.
            Tanı koymuyorsun, ilaç önermiyorsun.
            Gerektiğinde profesyonel yardım almanı tavsiye ediyorsun.
            CBT bazlı yaklaşım — düşünce örüntülerini fark ettiriyorsun.""",

        "fitness_coach": """Sen {user_name}'ın fitness ve beslenme koçusun.
            Antrenman programlama, form önerileri, beslenme desteği.
            Yaralanmalarına dikkat ediyorsun (özellikle {injury_notes}).
            Veri odaklı — PR'ları, ilerlemeni takip ediyorsun.""",

        "career_coach": """Sen {user_name}'ın kariyer koçusun.
            Hedef belirleme, müzakere, liderlik, iş-hayat dengesi.
            Pragmatik ve dürüstsün — boş gurur vermiyorsun.""",
    }

    # Custom için Claude Haiku ile üret
    if character.template == "custom":
        # Haiku: "Bu açıklamaya göre sistem promptu yaz: {description}"
        return generate_custom_prompt_with_haiku(character.description, user)

    base = template_context[character.template].format(
        user_name=character.name,  # Kullanıcının bu karaktere verdiği isim
        injury_notes=get_injury_notes(user)
    )
    return base
```

---

## API Endpoint'leri

### Karakter CRUD

```
GET    /characters              → Kullanıcının tüm karakterleri
POST   /characters              → Yeni karakter oluştur (şablondan veya custom)
GET    /characters/:id          → Karakter detayı
PUT    /characters/:id          → Karakter güncelle (isim, prompt, avatar)
DELETE /characters/:id          → Karakteri sil (General Friend silinemez)
```

### Karakter Memory

```
GET    /characters/:id/memories         → Bu karakterin tüm memory'leri
DELETE /characters/:id/memories/:memId  → Belirli memory'yi sil
DELETE /characters/:id/memories         → Tüm character memory'leri sil
```

### Mesajlaşma ile İlişki

Her karakterin tek ve otomatik oluşturulmuş bir konuşması vardır.
Mesaj göndermek için: `POST /characters/:id/messages`
Belirtilmezse General Friend varsayılır.

---

## App UI (Native)

### Karakter Seçim Ekranı

```
┌─────────────────────────────────┐
│  Karakterlerin                  │
│                                 │
│  ┌──────┐  ┌──────┐  ┌──────┐  │
│  │  🌟  │  │  📚  │  │  🧠  │  │
│  │ Alex │  │ Sarah│  │ Emma │  │
│  │Arkdş │  │ Eng  │  │Terapi│  │
│  └──────┘  └──────┘  └──────┘  │
│                                 │
│  ┌──────┐  ┌──────┐             │
│  │  💪  │  │  ➕  │             │
│  │ Mike │  │ Yeni │             │
│  │Coach │  │      │             │
│  └──────┘  └──────┘             │
└─────────────────────────────────┘
```

Her karakter kartında:
- Kullanıcının verdiği isim
- Rol ikonu / avatar rengi
- Son konuşma zamanı
- Okunmamış proaktif mesaj varsa badge

### Karakter Oluşturma Akışı

```
1. Şablon seç (veya Custom)
   ↓
2. İsim ver (ne diye çağırmak istiyorsun?)
   ↓
3. Sistem promptu önizle (düzenlenebilir)
   ↓
4. Avatar rengi / stili seç
   ↓
5. Oluştur → karakter listesine eklenir
```

Custom karakterler için ek adım:
```
2b. "Bu karakteri tanımla" serbest metin
    → Haiku anında sistem promptu üretir
    → Kullanıcı onaylar / düzenler
```

### Karakter Geçişi

Chat ekranının üst barında aktif karakter gösterilir.
Tıklayınca karakter listesi açılır → farklı bir karakterle konuşmaya başlanır.
Konuşma geçmişi karaktere göre filtrelenmiş gelir.

---

## Gizlilik ve Hassas Veriler

### Therapist Karakteri için Ek Önlemler

- Therapist memory'leri veritabanında şifreli saklanır (AES-256, kullanıcı anahtarı)
- "Therapist memory'lerini tümünü sil" seçeneği Profile ekranında ayrıca görünür
- Bu memory'ler data export'a dahil edilmeden önce kullanıcıya ayrıca sorulur
- AI şunu söyler: "Bu konuşmalar sadece seninle aramda kalır."

---

## Fiyatlandırma ile İlişki

Detaylar için bkz. [15-fiyatlandirma.md](15-fiyatlandirma.md).

| Plan | Karakter Hakkı |
|------|---------------|
| Ücretsiz | Sadece General Friend (1 karakter) |
| Premium ($9.99/ay) | Sınırsız karakter + tüm özellikler |

Yerleşik şablonlar premium'da ücretsiz gelir.
Custom şablon da premium kapsamındadır.

---

## Proaktif Bildirimler ile Entegrasyon

Her karakter bağımsız proaktif bildirim üretebilir:

- **General Friend:** Sabah check-in, akşam yansıma, uyku hatırlatması
- **English Teacher:** "Bugün 5 dakika pratik yapalım mı?"
- **Therapist:** "Geçen hafta stresli geçti dedin, bu hafta nasıl hissediyorsun?"
- **Fitness Coach:** "3 gündür antrenman yok, nasıl gidiyor?"

Kullanıcı her karakter için bildirimleri ayrı ayrı açıp kapatabilir.

---

## Teknik Notlar

### Sınırlamalar

- Bir karakter silinemez konuşma geçmişi varsa (sadece deaktive edilir)
- General Friend deaktive edilemez ve silinemez
- `mem0_agent_id` oluşturulduktan sonra değiştirilemez (memory kaybı olur)

### Performans

- Her chat çağrısında 2 Mem0 araması: global + character-specific
- İki arama paralel yapılır (async)
- Toplam gecikme etkisi: ~50–100ms ek
