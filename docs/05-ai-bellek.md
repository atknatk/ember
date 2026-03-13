# 05 — AI ve Bellek Sistemi

## Mem0.ai Entegrasyonu

### Memory Ekleme

Her konuşma tamamlandıktan sonra arka planda çalışır (kullanıcı beklemez):

```python
client = MemoryClient(api_key=settings.mem0_api_key)
await asyncio.to_thread(
    client.add,
    [kullanıcı_mesajı, ai_yanıtı],
    user_id=mem0_user_id,
    agent_id=agent_id,
)
```

Mem0 konuşmadan otomatik gerçek çıkarır. Manuel etiketleme gerekmez.

Örnek: Kullanıcı "sol dizim biraz ağrıdı bugün squat'ta" derse Mem0 şunu saklar:
→ "Sol dizi hassas, squat'ta dikkat gerekiyor"

---

### Memory Arama

Her yeni mesaj gelmeden önce çalışır:

```python
client = MemoryClient(api_key=settings.mem0_api_key)
results = await asyncio.to_thread(
    client.search,
    kullanıcı_mesajı,
    user_id=mem0_user_id,
    agent_id=agent_id,
    limit=10,
)
```

Dönen memories sistem prompt'una eklenir. AI mesajın bağlamına en uygun memories otomatik çekilir.

Örnek: Kullanıcı "bugün antrenman yorucu oldu" derse şunlar çekilebilir:
- "Sabah antrenmanını tercih eder"
- "Sol dizi hassas, squat'ta dikkat"
- "Squat PR'ı 100kg"

---

## Memory Kategorileri

| Kategori | Örnek memory'ler |
|----------|-----------------|
| **Kişilik** | "Kısa ve öz cevapları tercih eder", "Veri odaklı konuşmayı sever" |
| **Fitness** | "Sabah antrenmanları", "Sol dizi hassas", "Squat PR: 100kg" |
| **Beslenme** | "Kahvaltıda yulaf sever", "Brokoli sevmez", "1800 kcal hedefi" |
| **İş / Yaşam** | "Pazartesi toplantı günü", "Serbest çalışıyor", "07:00 kalkıyor" |
| **Hedefler** | "75 kg olmak istiyor", "Maratona hazırlanıyor" |
| **İlişkiler** | "Tuvik ile evli, o da uygulamayı kullanıyor" |
| **Önemli olaylar** | "Gelecek hafta iş seyahati", "Annesi rahatsız" |

---

## Onboarding Memory Seed

İlk kurulumda sorulan sorular ve Mem0'a eklenecek format:

| Soru | Memory Formatı |
|------|---------------|
| "Nasıl çağırayım seni?" | `{isim} adını tercih ediyor` |
| "Ne iş yapıyorsun?" | `{meslek} olarak çalışıyor` |
| "Sabahçı mısın akşamcı mı?" | `{sabah/akşam} kişisi` |
| "Sağlık / fitness hedefin?" | `Hedefi: {hedef}` |
| "Stres yönetimi için ne yapıyorsun?" | `Stres yönetimi: {yöntem}` |
| "Uyku düzenin nasıl?" | `Uyku düzeni: {uyku saati} - {kalkış saati}` |
| "Benden nasıl bir arkadaşlık bekliyorsun?" | `İletişim tercihi: {tercih}` |

---

## Prompt Mimarisi

Sistem prompt her AI çağrısında 3 bloktan oluşur:

### Blok 1 — Karakter Tanımı (sabit)

> Sen {kullanıcı_adı}'nın kişisel AI arkadaşısın.
> Koç değilsin, terapist değilsin — arkadaş.
> Samimi, dürüst, sıcak ama aşırı pozitif değil.
> Türkçe konuş. Kısa ve öz mesajlar yaz.
> Gerektiğinde soru sor, monolog yapma.
> Öğrendiklerini doğal şekilde kullan — "hatırlıyorum ki..." deme, sadece bil.

Bu blok nadiren değişir → Anthropic Prompt Caching ile cache'lenir → token tasarrufu.

### Blok 2 — Öğrenilmiş Bilgiler (Mem0'dan)

> Bu kullanıcı hakkında bildiklerin:
> - Sabah antrenmanını tercih eder
> - Sol dizi hassas, squat'ta dikkat
> - Pazartesi toplantıları stresli geçiyor
> - 75 kg olmak istiyor (şu an 87 kg)

Her mesajda Mem0 search sonuçlarıyla yenilenir. Maksimum 10 memory (token sınırı).

### Blok 3 — Günlük Bağlam (dinamik)

> Bugün: Perşembe, 23 Şubat 2026, saat 14:30
> Timezone: Europe/Istanbul
> Son mesaj zamanı: 2 saat önce

---

## Maliyet Optimizasyonu

### Model Seçim Stratejisi

| İşlem | Model | Neden |
|-------|-------|-------|
| Ana konuşma | claude-sonnet-4-6 | En yüksek kalite, Türkçe akıcılık |
| Fotoğraf analizi | claude-sonnet-4-6 | Vision desteği zorunlu |
| Intent sınıflandırma | claude-haiku-4-5 | Basit JSON çıktı, ucuz ve hızlı |
| Proaktif bildirim metni | claude-haiku-4-5 | Kısa metin üretimi |

### Anthropic Prompt Caching

Blok 1 (sabit karakter) her çağrıda değişmez → cache_control ile işaretlenir.
5 dakika içindeki tekrarlı çağrılarda bu blok yeniden işlenmez.
Tahmini tasarruf: Her konuşmada %30–50 token azalması.

### Konuşma Geçmişi Sınırı

Sadece son 50 mesaj Claude'a gonderilir (`max_context_messages` config ile ayarlanabilir). Daha eski mesajlar Mem0'da memory olarak yasar.
Bu sayede uzun konusmalarda token maliyeti sabit kalir.

---

## Karakter Sistemi ile Memory İzolasyonu

Her karakter kendi izole bellek alanında çalışır. Mem0'nun `agent_id` parametresi bunu sağlar.

### Memory Ekleme (Karaktere Özel)

```python
# English Teacher konusmasi bitince
client = MemoryClient(api_key=settings.mem0_api_key)
await asyncio.to_thread(
    client.add,
    [user_message, ai_response],
    user_id=mem0_user_id,
    agent_id="english_teacher_a3f9b2c1",
)
```

### Memory Arama — İki Katmanlı Strateji

Her AI çağrısında iki arama **paralel** olarak çalışır:

```python
import asyncio
from mem0 import MemoryClient

async def get_memories(query: str, user_id: str, agent_id: str):
    client = MemoryClient(api_key=settings.mem0_api_key)
    # 1. Global memories: temel kullanici bilgileri (tum karakterlerin gorebildigi)
    # 2. Karaktere ozel memories: sadece bu karakterin biriktirdikleri
    global_task = asyncio.to_thread(
        client.search, query, user_id=user_id, limit=5,
    )
    character_task = asyncio.to_thread(
        client.search, query, user_id=user_id, agent_id=agent_id, limit=5,
    )
    global_mems, character_mems = await asyncio.gather(global_task, character_task)
    return global_mems[:5] + character_mems[:5]  # Toplam max 10
```

### Hangi Karakter Ne Saklar

| Karakter | Global Memory | Karaktere Özel Memory |
|---------|---------------|----------------------|
| General Friend | İsim, meslek, hedefler | Yaşam olayları, duygusal örüntüler |
| English Teacher | İsim, dil seviyesi | Hatalar, öğrenilen kelimeler, ilerleme |
| Therapist | İsim | Duygusal örüntüler, stres kaynakları |
| Fitness Coach | İsim, yaralanmalar | PR'lar, antrenman tercihleri |

Detaylı karakter sistemi için bkz. [16-karakterler.md](16-karakterler.md).

---

## Memory Şeffaflık İlkeleri

- Kullanıcı her zaman ne saklandığını görebilir (karakter bazında)
- Her kayıt silinebilir, bu Mem0'dan gerçekten kaldırır
- "Bunu not aldım" ipucu gösterilebilir (UX kararı)
- Veri export: Tüm memories JSON olarak indirilebilir
- Therapist memory'leri şifreli saklanır ve ayrıca silinebilir

---

## Self-Hosted Geçiş

### Mem0 Open Source

Mem0, 37.000+ GitHub star'lı açık kaynak projeye sahip.
Cloud ile aynı adaptive memory engine'i kullanır.
GitHub: https://github.com/mem0ai/mem0

### Altyapı

Self-hosted Mem0 şunları kullanır:
- **Vector store:** PostgreSQL + pgvector (önerilen) veya Qdrant, Pinecone
- **Audit/history:** SQLite (memory versiyon geçmişi için)
- **API:** FastAPI tabanlı REST server (port 8888)
- **LLM:** Herhangi bir provider (Anthropic, OpenAI, Ollama vb.)

### Cloud → Self-Hosted Geçiş Planı

1. Self-hosted Mem0 instance ayağa kaldır (Docker Compose)
2. Cloud API'sinden tüm memories export et:
   ```
   GET /v1/memories/?user_id={uid}&page_size=1000
   ```
3. Export edilen memories self-hosted instance'a import et:
   ```
   POST /v1/memories/ (her memory için)
   ```
4. Backend'deki Mem0 API URL'sini cloud → self-hosted olarak değiştir
5. Test: Aramalar çalışıyor mu, yeni memories ekleniyor mu?

**Durum:** Migration araçları Mem0 ekibi tarafından geliştirilmeye devam ediyor.
Şu an manuel export/import gerekiyor ama API tam erişim sağlıyor.

### Neden Cloud ile Başlanmalı

- MVP'de self-hosting altyapı yönetimi zaman ister
- Ürün doğrulandıktan sonra self-hosted geçiş daha anlamlı
- Geçiş pgvector kullandığı için AWS RDS'e kolayca taşınır (zaten mevcut)

---

## Mem0 Degradation Stratejisi

### Circuit Breaker Pattern

Mem0 Cloud erişilemezken chat fonksiyonu çalışmaya devam etmeli:

1. **Normal mod:** Mem0 search + add her mesajda çalışır
2. **Degraded mod (circuit open):** 3 ardışık Mem0 hatası → circuit açılır (60s)
   - Chat memory'siz devam eder (sadece son 20 mesaj context'i)
   - Mem0 add işlemleri kuyruğa alınır, circuit kapanınca gönderilir
3. **Half-open mod:** 60s sonra tek deneme, başarılıysa normal moda dön

### Local Memory Cache

Son başarılı Mem0 search sonuçları in-memory cache'te tutulur (TTL 5dk).
Circuit open durumda cache'ten servis edilir.

### Health Check

`/health` endpoint'i Mem0 API durumunu raporlar:

- `mem0_status: "healthy" | "degraded" | "unavailable"`

Detaylı implementasyon: P1.5-04 (mem0-circuit-breaker) issue'da.

---

## Memory Growth ve Kalite

Premium kullanıcılarda sınırsız memory birikir. Zaman içinde:

- Mem0 search kalitesi büyük corpus'ta düşebilir (daha az ilgili sonuçlar)
- Mem0'nun dahili deduplication algoritması çelişen memory'leri yönetir
- Memory sayısı monitoring: per-user memory count takibi (P11-08)
- Gelecekte: memory pruning stratejisi (eski/düşük relevance memory'leri arşivle)
