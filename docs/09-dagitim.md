# 09 — Dağıtım — AWS

## Genel Bakış

Tüm altyapı AWS üzerinde çalışır. Mevcut AWS hesabındaki kaynaklar kullanılır.

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Account                          │
│                                                             │
│  CloudFront CDN                                             │
│       ↓                                                     │
│  ALB (Application Load Balancer)                            │
│       ↓                                                     │
│  ECS Fargate (Python FastAPI)                               │
│       ↓              ↓              ↓                       │
│  RDS PostgreSQL    S3 Bucket     ECR (Docker Images)        │
│  (+ pgvector)      (media)                                  │
│       ↓                                                     │
│  AWS Cognito (Auth)                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Servisler

### ECS Fargate — Backend

Python FastAPI uygulaması container olarak çalışır.

- **Cluster:** `ai-companion-cluster`
- **Service:** `ai-companion-api`
- **Task Definition:** `ai-companion-task`
- **CPU / Memory:** 0.5 vCPU / 1 GB (başlangıç, ölçeklenir)
- **Min tasks:** 1, **Max tasks:** 10 (Auto Scaling)
- **Health check:** `GET /health` → 200 OK

Auto Scaling kuralı:
- CPU %70'i aşarsa → task sayısını artır
- CPU %30'un altında 5 dk → task sayısını azalt

---

### RDS PostgreSQL — Veritabanı

- **Engine:** PostgreSQL 16
- **Instance:** `db.t3.micro` (başlangıç) → `db.t3.small` (ölçek)
- **Storage:** 20 GB gp3 (otomatik büyüme)
- **Multi-AZ:** Production'da açık, development'ta kapalı
- **Extension:** `pgvector` (self-hosted Mem0 geçişinde kullanılır)
- **Backup:** 7 gün otomatik backup

---

### S3 — Dosya Depolama

- **Bucket:** `ai-companion-media-{account_id}`
- **Klasör yapısı:**
  ```
  ai-companion-media/
  ├── photos/{user_id}/{timestamp}_{filename}
  └── audio/{user_id}/{timestamp}.mp3
  ```
- **Erişim:** Private (sadece presigned URL ile)
- **Lifecycle:** 90 gün sonra eski ses dosyaları Glacier'a taşınır

---

### AWS Cognito — Kimlik Doğrulama

- **User Pool:** `ai-companion-users`
- **Identity Pool:** Gerekmiyor (backend doğrulama kullanılır)
- **Token süresi:** Access Token 1 saat, Refresh Token 30 gün
- **MFA:** Opsiyonel (Faz 11+)
- **Email doğrulama:** Kayıt sırasında zorunlu

Akış:
1. Native uygulama → AWS Amplify Cognito SDK ile register/login (iOS + Android)
2. Cognito → JWT token döner
3. Native uygulama → her API isteğinde `Authorization: Bearer <token>` gönderir
4. FastAPI → Cognito public key ile token doğrular

---

### ECR — Container Registry

- **Repository:** `ai-companion/backend`
- **Image tagging:** `latest` + `{git_sha}` (her build)
- **Lifecycle:** Son 10 image saklanır, eskiler silinir

---

### CloudFront + ALB

- **CloudFront:** API önünde CDN + HTTPS (API için caching yok, sadece SSL ve geo-routing)
- **ALB:** ECS Fargate task'larına yük dağıtır
- **Domain:** `api.aicompanion.app` (Route 53 ile)

---

### Firebase FCM — Push Notification

Firebase, AWS dışında kalır çünkü iOS + Android push notification için en stabil çözüm.

- **Proje:** `ai-companion-fcm`
- **Backend:** Firebase Admin SDK (Python) ECS içinden çağrılır
- **iOS APNs + Android GCM:** Firebase üzerinden yönetilir
- **Maliyet:** Spark plan (ücretsiz, aylık 500k notification sınırı)

---

## CI/CD Pipeline

GitHub Actions ile otomatik deployment:

```
git push main
    ↓
GitHub Actions
    ↓
1. Python tests çalışır
2. Docker image build edilir
3. ECR'e push edilir
4. ECS service güncellenir (rolling deploy)
5. Health check geçerse deployment tamamlanır
6. Health check başarısız → rollback
```

---

## Ortam Değişkenleri

ECS Task Definition'a AWS Secrets Manager veya Parameter Store üzerinden enjekte edilir.

### Backend (ECS Environment)

| Değişken | Açıklama | Kaynak |
|----------|---------|--------|
| `ANTHROPIC_API_KEY` | Claude API | Secrets Manager |
| `MEM0_API_KEY` | Mem0.ai cloud | Secrets Manager |
| `ELEVENLABS_API_KEY` | TTS premium | Secrets Manager |
| `OPENAI_API_KEY` | Whisper STT | Secrets Manager |
| `COGNITO_USER_POOL_ID` | Auth | Parameter Store |
| `COGNITO_CLIENT_ID` | Auth | Parameter Store |
| `RDS_HOST` | DB bağlantısı | Parameter Store |
| `RDS_DATABASE` | DB adı | Parameter Store |
| `RDS_USERNAME` | DB kullanıcı | Secrets Manager |
| `RDS_PASSWORD` | DB şifre | Secrets Manager |
| `S3_BUCKET_NAME` | Medya bucket | Parameter Store |
| `AWS_REGION` | us-east-1 veya eu-central-1 | Parameter Store |
| `FIREBASE_CREDENTIALS` | FCM service account JSON | Secrets Manager |

### Native Apps — iOS + Android (build-time inject edilir)

| Değişken | Açıklama |
|----------|---------|
| `BACKEND_URL` | https://api.aicompanion.app |
| `COGNITO_USER_POOL_ID` | Cognito Auth için |
| `COGNITO_CLIENT_ID` | Cognito Auth için |
| `AWS_REGION` | Cognito için |

iOS: `xcconfig` / `Info.plist` build settings ile inject edilir.
Android: `gradle.properties` / `BuildConfig` ile inject edilir.

---

## Ortamlar

| Ortam | Branch | URL | RDS |
|-------|--------|-----|-----|
| Development | `develop` | api-dev.aicompanion.app | RDS dev instance |
| Staging | `staging` | api-staging.aicompanion.app | RDS staging |
| Production | `main` | api.aicompanion.app | RDS prod (Multi-AZ) |

---

## Mobil Dağıtım

### Geliştirme Aşaması
- iOS: **TestFlight** (App Store Connect → dahili test, invite ile)
- Android: **Internal Testing Track** (Google Play Console)

### Yayın Aşaması
- iOS: App Store Connect → Submit for Review (~1–3 gün)
- Android: Google Play Console → Production track (~1–7 gün)

App Store zorunlulukları:
- Gizlilik politikası URL'si
- Veri kullanım beyanı (App Privacy)
- Hesap silme akışı (GDPR / App Store Review)

---

## Maliyet Tahmini

### AWS Altyapısı (aylık, ~100 kullanıcı)

| Servis | Maliyet |
|--------|---------|
| ECS Fargate (1 task, 0.5 vCPU / 1 GB) | ~12 USD |
| RDS db.t3.micro | ~15 USD |
| S3 (10 GB storage + transfer) | ~1 USD |
| ALB | ~16 USD |
| CloudFront | ~1 USD |
| Cognito (50k MAU ücretsiz) | 0 USD |
| ECR | ~1 USD |
| **AWS Toplam** | **~46 USD/ay** |

### Dış Servisler

| Servis | Plan | Maliyet |
|--------|------|---------|
| Mem0.ai | Developer (ücretsiz) | 0 USD |
| Firebase FCM | Spark (ücretsiz) | 0 USD |
| App Store Developer | Yıllık | 99 USD/yıl |
| Google Play Developer | Tek seferlik | 25 USD |

### AI API (100 aktif kullanıcı, 20 mesaj/gün)

| Servis | Maliyet |
|--------|---------|
| Claude Sonnet (chat) | ~45 USD/ay |
| Claude Haiku (intent + bildirim) | ~3 USD/ay |
| ElevenLabs Creator Plan | 22 USD/ay (sabit) |
| OpenAI Whisper (STT) | ~5 USD/ay |
| **AI Toplam** | **~75 USD/ay** |

**Toplam ~121 USD/ay → kullanıcı başına ~1.21 USD/ay** (100 kullanıcı senaryosu)

---

## Güvenlik Notları

- RDS: Public erişim kapalı, sadece ECS security group'undan erişim
- S3: Block public access aktif, sadece presigned URL
- Secrets: AWS Secrets Manager (plain text env var değil)
- VPC: ECS + RDS aynı private subnet'te
- IAM: ECS task role yalnızca gerekli servislere erişim (least privilege)
