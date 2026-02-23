# Ember Agent Pipeline — Kullanım Kılavuzu

Bu belge, tüm pipeline skill'lerinin ne yaptığını, nasıl kullanılacağını ve bir featurın baştan sona nasıl
implement edildiğini açıklar. **Yeni bir seans açtığında bu belgeyi okuman yeterli — her şey burada.**

---

## Skill Özeti (TL;DR)

| Skill | Kullanım | Ne Yapar |
|-------|---------|---------|
| `/pipeline-run P01-01` | Tek feature | Bir feature'ı 9 ajanla implement eder, PR açar |
| `/queue-run 1` | Faz bazlı | Faz 1'deki tüm feature'ları sırayla işler |
| `/queue-run 1 2 3` | Çok faz | Birden fazla fazı sırayla işler |
| `/queue-run` | Tam proje | Tüm 69 feature'ı otomatik implement eder |
| `/queue-run --from P01-03` | Devam | Belirli feature'dan devam eder |
| `/queue-run 1 --dry-run` | Önizleme | Ne yapacağını gösterir, kod yazmaz |
| `/verify` | Kalite kontrolü | Test + lint + security scan çalıştırır |
| `/create-pr` | Manuel PR | Manuel implement sonrası PR açar |

---

## İçindekiler

1. [Genel Bakış](#1-genel-bakış)
2. [Temel Kavramlar](#2-temel-kavramlar)
3. [İlk Kullanım — Adım Adım](#3-ilk-kullanım--adım-adım)
4. [pipeline-run Kullanımı](#4-pipeline-run-kullanımı)
5. [queue-run Kullanımı](#5-queue-run-kullanımı)
6. [verify Kullanımı](#6-verify-kullanımı)
7. [create-pr Kullanımı](#7-create-pr-kullanımı)
8. [Pipeline Aşamaları](#8-pipeline-aşamaları)
9. [Hangi Feature'ı Çalıştıracağını Seçmek](#9-hangi-featureı-çalıştıracağını-seçmek)
10. [Bağımlılık Yönetimi](#10-bağımlılık-yönetimi)
11. [Durum Takibi](#11-durum-takibi)
12. [Çıktılar — Ne Üretilir?](#12-çıktılar--ne-üretilir)
13. [Hata Durumları ve Çözümleri](#13-hata-durumları-ve-çözümleri)
14. [Faz Sıralaması ve Öncelikler](#14-faz-sıralaması-ve-öncelikler)

---

## 1. Genel Bakış

Ember'ın 4 pipeline skill'i vardır:

### `/pipeline-run` — Tek Feature

Tek bir feature'ı 9 uzman ajanın işbirliğiyle implement eder.

```
Sen                 →  /pipeline-run P01-01
Orchestrator        →  9 ajan koordine eder
Çıktı              →  Kod + Testler + Dokümantasyon + PR
```

### `/queue-run` — Faz/Proje Bazlı Toplu Çalışma

Bir fazın (veya tüm projenin) feature'larını sırayla işler. Her feature tamamlanıp PR merge olmadan
bir sonrakine geçmez. Bağımlılık grafiğine göre otomatik sıralama yapar.

```
Sen                 →  /queue-run 1
Queue Runner        →  Faz 1'i bağımlılık sırasıyla işler
                        P01-01 → merge → P01-02 → merge → ...
Çıktı              →  Tüm faz implement edilmiş, develop'a merge
```

### `/verify` — Kalite Kontrolü

Herhangi bir anda test + lint + security scan çalıştırır.

### `/create-pr` — Manuel PR

Manuel implement ettikten sonra PR açar (pipeline dışı kullanım için).

---

## 2. Temel Kavramlar

### Feature ID Formatları

Her feature'ın iki ID'si vardır:

| Format | Örnek | Kullanım |
|--------|-------|---------|
| `P{faz}-{sıra}` | `P01-01` | GitHub issue takibi, kısa referans |
| `p{faz}/{isim}` | `p01/project-setup` | Branch adı, dosya yolları |

Her iki format da `/pipeline-run` komutuna verilebilir.

### Layer (Katman) Kavramı

Her feature bir veya birden fazla platformu kapsar:

| Layer | Kapsam | Spawn edilen ajanlar |
|-------|--------|---------------------|
| `backend` | Sadece Python/FastAPI | backend-dev, backend-tester |
| `ios` | Sadece Swift/SwiftUI | ios-dev, ios-tester |
| `android` | Sadece Kotlin/Compose | android-dev, android-tester |
| `mobile` | iOS + Android | ios-dev + android-dev (paralel) |
| `fullstack` | Backend + iOS + Android | 3 dev + 3 tester (paralel) |

### Kritik Dosyalar

| Dosya | Ne İçerir |
|-------|-----------|
| `scripts/feature-queue.jsonl` | 69 feature tanımı (id, layer, deps, description) |
| `scripts/issue-map.json` | Feature ID → GitHub issue no eşlemesi |
| `scripts/feature-status.json` | Hangi feature'lar tamamlandı (pipeline tarafından yönetilir) |
| `CLAUDE.md` | Tüm ajanların uyması gereken global kurallar |
| `docs/PIPELINE-GUIDE.md` | Ajan spawnlama konvansiyonları (teknik referans) |

---

## 3. İlk Kullanım — Adım Adım

### Adım 1: Sıradaki Feature'ı Bul

```bash
# Faz 1'deki feature'ları listele
grep '"phase":1' scripts/feature-queue.jsonl | jq -r '"\(.id) [\(.layer)] \(.name)"'
```

Çıktı:
```
P01-01 [backend] project-setup
P01-02 [backend] user-auth
P01-03 [backend] database-schema
...
```

### Adım 2: Bağımlılıkları Kontrol Et

```bash
# P01-02'nin bağımlılıklarına bak
grep '"id":"P01-02"' scripts/feature-queue.jsonl | jq -r '.deps'
```

Eğer bağımlı feature'lar varsa, onları önce tamamla.

### Adım 3: Pipeline'ı Başlat

Claude Code içinde:
```
/pipeline-run P01-01
```

### Adım 4: Pipeline Çalışırken

Pipeline otomatik ilerler. Ajan tamamlama bildirimleri gelir.
Her aşama tamamlandığında orchestrator devam eder.

Sen müdahale etmeden bekliyorsun.

### Adım 5: PR'ı İncele ve Merge Et

Pipeline bitince:
```
## ✅ Pipeline Complete: P01-01 — project-setup

Branch: feature/p01/project-setup
PR: https://github.com/atknatk/ember/pull/72
Issue: #3
Layer: backend
```

GitHub'da PR'ı aç, gözden geçir, merge et.

---

## 4. pipeline-run Kullanımı

```
/pipeline-run <feature-id> [--issue <N>] ["<açıklama>"]
```

### Örnekler

```bash
# Temel kullanım
/pipeline-run P01-01

# Issue numarasını manuel belirterek (issue-map.json'ı geçersiz kılar)
/pipeline-run P01-06 --issue 8

# Özel açıklama ile (spec'e ek context sağlar)
/pipeline-run P03-07 --issue 23 "Chat streaming SSE implementasyonu"

# Pipeline ID formatı ile (her iki format eşdeğer)
/pipeline-run p01/project-setup
```

### Özel Durumlar

```bash
# Feature zaten done ise → onay ister:
# "Feature P01-01 is already done. Re-run? (yes to continue)"

# Feature in-progress ise → devam mı sorar:
# "Feature P01-01 is in-progress. Continue? (yes to resume)"

# Bağımlılık tamamlanmamış → uyarı verir:
# "Dependency P01-01 is not done yet. Are you sure you want to proceed?"
```

---

## 5. queue-run Kullanımı

Bir veya birden fazla fazın feature'larını **sırayla** implement eder. Her feature PR merge
olmadan sıradaki başlamaz.

```
/queue-run [all|<faz>|<faz> <faz> ...] [--from <feature-id>] [--dry-run]
```

### Örnekler

```bash
# Faz 1'deki tüm feature'ları sırayla çalıştır
/queue-run 1

# Birden fazla faz (sırayla)
/queue-run 1 2 3

# Tüm 69 feature (12 faz, bağımlılık sırasıyla)
/queue-run

# Yarım kalan queue'ya devam et
/queue-run --from P01-04

# Sadece belirli faz, yarım kalmışsa devam et
/queue-run 1 --from P01-06

# Ne yapacağını önce gör (kod yazmaz, sadece sıralamayı gösterir)
/queue-run 1 --dry-run
```

### --dry-run Çıktısı

```
=== Queue Run Plan — Phase 1 ===

  1. P01-01 [backend] project-setup         deps: none
  2. P01-02 [backend] user-auth             deps: P01-01
  3. P01-03 [backend] database-schema       deps: P01-01
  4. P01-04 [backend] chat-stream           deps: P01-02, P01-03
  5. P01-05 [backend] mem0-integration      deps: P01-02, P01-03
  ...

Total: 10 features
Already done: 0
To process: 10

Run without --dry-run to start.
```

### queue-run Akışı

```
/queue-run 1
    │
    ├─ develop'tan başla, git pull
    │
    ├─ Bağımlılık sırası: P01-01 önce (bağımlılığı yok)
    │
    ├─ /pipeline-run P01-01
    │      → feature/p01/project-setup branch
    │      → 9 ajan çalışır
    │      → PR açılır, auto-merge aktif
    │      → CI geçince develop'a merge olur
    │
    ├─ P01-01 merge olunca P01-02 ve P01-03 unblock olur
    │
    ├─ /pipeline-run P01-02
    │   ...
    │
    └─ Faz tamamlanınca özet rapor
```

### Hata Durumunda

Queue herhangi bir feature'da hata alırsa **durur** (sıradakine geçmez):

```
❌ Queue paused at P01-04.

Error: [hata detayı]

Resume with:
  /queue-run --from P01-04
```

---

## 6. verify Kullanımı

Herhangi bir anda test + lint + security scan çalıştırır.

```
/verify [--backend] [--ios] [--android] [--all]
```

### Örnekler

```bash
# Otomatik detect (değişen dosyalara göre platform seç)
/verify

# Sadece backend
/verify --backend

# Sadece Android
/verify --android

# Tüm platformlar
/verify --all
```

### Çıktı

```
## Verify Report — feature/p01/project-setup

| Check          | Platform | Result   | Detail                      |
|----------------|----------|----------|-----------------------------|
| Ruff lint      | Backend  | ✅ Pass  | 0 errors                    |
| MyPy types     | Backend  | ✅ Pass  | 0 errors                    |
| Pytest         | Backend  | ✅ Pass  | 47 passed, coverage 84%     |
| Gradle lint    | Android  | ✅ Pass  | 0 errors                    |
| Gradle test    | Android  | ✅ Pass  | 23 passed                   |
| SwiftLint      | iOS      | ⚠️ Skip  | Not installed locally       |
| Security scan  | All      | ✅ Pass  | No hardcoded secrets        |

Overall: ✅ PASS
```

---

## 7. create-pr Kullanımı

Pipeline dışında manuel implement ettikten sonra PR açmak için.

```
/create-pr [feature-id] [--draft]
```

### Örnekler

```bash
# Mevcut feature branch'inden PR aç (branch adından feature ID'yi çıkarır)
/create-pr

# Feature ID'yi explicit belirt
/create-pr P01-03

# Draft PR aç (auto-merge kapalı)
/create-pr P01-03 --draft
```

### Ne Yapar?

1. Mevcut branch'i `origin`'e push eder
2. Handoff dosyalarını okuyarak PR açıklaması oluşturur
3. `agent:pipeline` label'ı ekler
4. Auto-merge aktif eder (draft değilse)
5. GitHub issue'ya PR URL'ini comment olarak ekler

---

## 8. Pipeline Aşamaları

Pipeline 8 adımda ilerler:

```
[1] Pre-flight       → Queue'dan feature oku, branch oluştur, issue güncelle
[2] Architect        → Spec + handoff yaz
[3] Developer(s)     → Kod implement et (paralel — layer'a göre)
[4] Quality Gate 1   → Pre-test kontrolleri
[5] Tester(s)        → Testleri yaz (paralel)
[6] Quality Gate 2   → Post-test kontrolleri
[7] Doc-writer +     → Dokümantasyon + Kod review (paralel)
    Reviewer
[8] Finalize         → Status güncelle, PR aç, issue kapat
```

### Paralel Çalışma

Aynı anda birden fazla ajan çalışır:

```
Faz 3: Developer Wave (fullstack için)
├── backend-dev  ──────────────────┐
├── ios-dev      ─────────────────┤ (hepsi aynı anda)
└── android-dev  ──────────────────┘

Faz 5: Tester Wave
├── backend-tester  ───────────────┐
├── ios-tester      ──────────────┤ (hepsi aynı anda)
└── android-tester  ───────────────┘

Faz 7: Final Wave
├── doc-writer  ─────────────────┐
└── reviewer    ─────────────────┘ (aynı anda)
```

---

## 9. Hangi Feature'ı Çalıştıracağını Seçmek

### Faz Bazlı Sıralama

```bash
# Tüm feature'ları faz ve sıra ile göster
cat scripts/feature-queue.jsonl | jq -r '"\(.id)\t[\(.layer)]\t\(.name)"' | sort
```

### Bir Sonraki Feature'ı Bulmak

```bash
# Hangi feature'lar henüz başlanmadı?
# (feature-status.json'da olmayan = başlanmamış)
python3 -c "
import json
queue = [json.loads(l) for l in open('scripts/feature-queue.jsonl') if l.strip()]
try:
    status = json.load(open('scripts/feature-status.json'))
except:
    status = {}
pending = [f for f in queue if status.get(f['id']) != 'done']
for f in pending[:10]:
    print(f\"{f['id']}\t[{f['layer']}]\t{f['name']}\t deps:{f['deps']}\")
"
```

### Faz 1 Örnek Çıktısı

```
P01-01  [backend]  project-setup       deps:[]
P01-02  [backend]  user-auth           deps:["P01-01"]
P01-03  [backend]  database-schema     deps:["P01-01"]
P01-04  [backend]  chat-stream         deps:["P01-02","P01-03"]
P01-05  [backend]  mem0-integration    deps:["P01-02","P01-03"]
...
```

### Önerilen Sıra

Faz 1'de başla, bağımlılık grafiğine göre ilerle:

```
P01-01  ──→  P01-02, P01-03
P01-02  ──→  P01-04, P01-05
P01-03  ──→  P01-04, P01-05
...
```

---

## 10. Bağımlılık Yönetimi

Bir feature, başka feature'lara bağımlı olabilir.

### Bağımlılık Kontrolü

Pipeline otomatik kontrol eder. Bağımlılık tamamlanmamışsa:

```
⚠️ WARNING: Dependency P01-01 is not done yet.
   Status: not_started (not in feature-status.json)
   Are you sure you want to proceed? (yes/no)
```

**Öneri:** Her zaman bağımlılıkları önce tamamla.

### Bağımlılık Durumunu Kontrol Etme

```bash
# Belirli bir feature'ın bağımlılıklarının durumu
cat scripts/feature-status.json
```

```json
{
  "P01-01": "done",
  "P01-02": "in-progress"
}
```

### Paralel Pipeline Çalıştırma

**Bağımsız feature'lar** paralel pipeline'da çalışabilir. Örnek:

```
Terminal 1: /pipeline-run P01-02   (user-auth backend)
Terminal 2: /pipeline-run P01-03   (database-schema backend)
```

Bu ikisi birbirinden bağımsız — paralel çalıştırılabilir.

**DİKKAT:** Aynı dosyaları değiştiren feature'ları asla paralel çalıştırma.

---

## 11. Durum Takibi

### feature-status.json

Pipeline bu dosyayı otomatik günceller. Manuel olarak da okunabilir/değiştirilebilir.

```json
{
  "P01-01": "done",
  "P01-02": "in-progress",
  "P01-03": "done"
}
```

**Olası değerler:**
- `"in-progress"` — Pipeline başlamış, henüz bitmemiş
- `"done"` — Pipeline tamamlandı, PR açıldı

**Yoksa** — Feature henüz başlanmamış demek.

### GitHub Issue Takibi

Her pipeline adımında issue'ya comment eklenir:

```
🚀 Pipeline started for P01-01 (project-setup)
   Branch: feature/p01/project-setup
   Layer: backend

✅ Architect complete — spec at shared/feature-specs/project-setup.md

✅ Implementation complete for backend. Starting tests.

✅ Tests complete. Starting docs + review.

🎉 Pipeline complete!
   PR: https://github.com/atknatk/ember/pull/72
   All tests passing. Review approved.
```

### Oluşan Handoff Dosyaları

```
docs/pipeline/
├── {name}-architect.handoff.md      ← Spec özeti + kararlar
├── {name}-backend-dev.handoff.md    ← Oluşturulan dosyalar + test komutu
├── {name}-ios-dev.handoff.md        ← iOS dosyaları
├── {name}-android-dev.handoff.md    ← Android dosyaları
├── {name}-backend-test.handoff.md   ← Coverage + test sayısı
├── {name}-ios-test.handoff.md       ← iOS test özeti
├── {name}-android-test.handoff.md   ← Android test özeti
├── {name}-doc.handoff.md            ← Dokümantasyon özeti
└── {name}-review.handoff.md         ← APPROVED / CHANGES_REQUESTED
```

---

## 12. Sık Karşılaşılan Durumlar

### Durum 1: Backend-Only Feature

```bash
/pipeline-run P01-01    # layer: backend
```

Spawn edilen ajanlar: `architect → backend-dev → backend-tester → doc-writer + reviewer`

iOS ve Android ajanları spawn edilmez.

---

### Durum 2: Fullstack Feature

```bash
/pipeline-run P03-01    # layer: fullstack
```

Spawn edilen ajanlar:
```
architect
  ↓
backend-dev + ios-dev + android-dev  (paralel)
  ↓
backend-tester + ios-tester + android-tester  (paralel)
  ↓
doc-writer + reviewer  (paralel)
```

---

### Durum 3: Yarım Kalan Pipeline'ı Devam Ettirme

Eğer pipeline yarıda kaldıysa (network hatası, session kesilmesi vb.):

```bash
/pipeline-run P02-03    # Aynı komutu tekrar çalıştır
```

Pipeline:
```
Feature P02-03 is in-progress. A previous pipeline may have started. Continue? (yes to resume)
```

`yes` diyince mevcut handoff dosyalarını kontrol eder ve kaldığı yerden devam eder.

---

### Durum 4: Manuel Override

Eğer issue numarası yanlışsa:

```bash
/pipeline-run P01-05 --issue 7
```

---

### Durum 5: Review CHANGES_REQUESTED

Eğer reviewer sorun bulursa, orchestrator otomatik fix cycle başlatır:

```
Round 1: Fix cycle başlıyor...
  ❌ backend/app/routes/auth.py:45 — user_id body'den alınıyor, JWT'den alınmalı
  → backend-dev fix spawning...

Round 2: Re-review...
  ✅ Tüm sorunlar giderildi. APPROVED.
```

Maximum 3 round. Hâlâ başarısız olursa sana rapor eder.

---

## 13. Çıktılar — Ne Üretilir?

Başarılı bir `/pipeline-run` şunları üretir:

### Kod Dosyaları

```
backend/
├── app/routes/{name}.py              ← FastAPI routes
├── app/services/{name}_service.py    ← Business logic
├── app/models/{name}.py              ← SQLAlchemy models
├── app/schemas/{name}.py             ← Pydantic schemas
└── tests/
    ├── test_{name}_routes.py         ← Route tests
    └── test_{name}_service.py        ← Service tests

ios/Ember/Feature/{CapitalizedName}/
├── Data/
│   ├── {Name}APIClient.swift
│   └── {Name}Repository.swift
├── Domain/
│   ├── {Name}UseCase.swift
│   └── {Name}Model.swift
└── Presentation/
    ├── {Name}ViewModel.swift
    └── {Name}View.swift

android/app/src/main/java/com/ember/feature/{name}/
├── data/
│   ├── {Name}ApiService.kt
│   └── {Name}Repository.kt
├── domain/
│   └── {Name}Model.kt
└── presentation/
    ├── {Name}ViewModel.kt
    └── {Name}Screen.kt
```

### Dokümantasyon Dosyaları

```
shared/
└── feature-specs/{name}.md           ← Tam spec (API, DB, ekranlar)
    api-contracts/{name}.yaml         ← OpenAPI spec (varsa)

docs/
├── features/{name}.md                ← Feature dokümantasyonu
└── pipeline/
    └── *.handoff.md                  ← Ajan handoff dosyaları
```

### GitHub

- PR açılır (`develop` branch'e)
- PR label: `agent:pipeline` (auto-merge aktif)
- Issue: tüm adımlar comment olarak eklenir, `Closes #N` ile kapatılır

### CHANGELOG.md

```markdown
## [Unreleased]

### Added
- [P01-01] FastAPI project scaffold with Docker, Poetry, and PostgreSQL setup
```

---

## 14. Hata Durumları ve Çözümleri

### "Feature not found in scripts/feature-queue.jsonl"

Feature ID yanlış yazılmış. Doğru format için:
```bash
grep '"id"' scripts/feature-queue.jsonl | head -20
```

---

### "Dependency X is not done yet"

Bağımlı feature önce tamamlanmalı:
```bash
/pipeline-run P01-01    # önce bağımlılığı çalıştır
/pipeline-run P01-02    # sonra asıl feature'ı
```

---

### Ajan Handoff Dosyası Yazmadı

Orchestrator yeniden spawn eder:
```
"You didn't write the handoff file.
 Please write docs/pipeline/{name}-{agent}.handoff.md with status: COMPLETE"
```

---

### Test Başarısız — Quality Gate Fail

Dev ajan fix prompt ile yeniden çağrılır (max 2 deneme).
2 denemede de başarısız olursa sana rapor eder:

```
⛔ Quality gate failed after 2 fix cycles.
   Error: backend/tests/test_auth.py::test_login FAILED
   AssertionError: expected 401, got 200

   Manual intervention needed. Review: backend/app/routes/auth.py
```

---

### Merge Conflict

```
⚠️ Merge conflict detected in:
   - backend/app/models/user.py
   - ios/Ember/Core/Models/User.swift

   Resolve conflicts manually, then re-run:
   /pipeline-run P01-04
```

---

### API Rate Limit

Orchestrator 30 saniye bekler, bir kez daha dener. Hâlâ başarısız olursa:
```
⛔ API rate limit hit. Please retry in a few minutes.
/pipeline-run P02-01
```

---

## 15. Faz Sıralaması ve Öncelikler

12 faz, 69 feature:

| Faz | Kapsam | Feature'lar | Önerilen Sıra |
|-----|--------|-------------|---------------|
| Faz 1 | Backend Temeli | P01-01 → P01-10 | **Buradan başla** |
| Faz 2 | Proaktif Bildirimler | P02-01 → P02-04 | Faz 1 bittikten sonra |
| Faz 3 | iOS Native App | P03-01 → P03-10 | Faz 1-2 bittikten sonra |
| Faz 4 | Android Native App | P04-01 → P04-10 | Faz 1-2, Faz 3 paralel |
| Faz 5 | Sesli Deneyim | P05-01 → P05-06 | Faz 3-4 bittikten sonra |
| Faz 6 | Cihaz Entegrasyonu | P06-01 → P06-06 | Faz 3-4 bittikten sonra |
| Faz 7 | Fotoğraf ve Medya | P07-01 → P07-03 | Faz 1-3 bittikten sonra |
| Faz 8 | Partner Bağlantısı | P08-01 → P08-03 | Faz 3-4 bittikten sonra |
| Faz 9 | Karakter Sistemi | P09-01 → P09-03 | Faz 1-3 bittikten sonra |
| Faz 10 | Fitness Entegrasyonu | P10-01 → P10-04 | Faz 3-4 bittikten sonra |
| Faz 11 | Cila ve Yayın | P11-01 → P11-06 | Tüm fazlar bittikten sonra |
| Faz 12 | Gerçek Zamanlı Ses | P12-01 → P12-04 | Faz 5 bittikten sonra |

### Hemen Başlamak İçin

```bash
# 1. İlk feature'ı başlat
/pipeline-run P01-01

# 2. PR merge edildikten sonra
/pipeline-run P01-02

# 3. P01-01 done, P01-03 bağımsız → paralel çalıştırılabilir
/pipeline-run P01-03
```

---

## Referanslar

### Skill Tanımları (teknik implementasyon)
- `.claude/skills/pipeline-run/SKILL.md` — Tek feature orchestrator
- `.claude/skills/queue-run/SKILL.md` — Faz/proje bazlı toplu işlemci
- `.claude/skills/verify/SKILL.md` — Kalite kontrol runner
- `.claude/skills/create-pr/SKILL.md` — PR oluşturucu

### Proje Dosyaları
- `scripts/feature-queue.jsonl` — Tüm 69 feature tanımı
- `scripts/issue-map.json` — GitHub issue eşlemeleri
- `scripts/feature-status.json` — Çalışma zamanı durum takibi
- `docs/PIPELINE-GUIDE.md` — Ajan konvansiyonları, handoff formatları
- `docs/standards/` — Backend, iOS, Android, testing standartları
- `docs/03-mimari.md` — Sistem mimarisi
