# apps/api — هسته‌ی هلدینگ (FastAPI + Temporal worker)

پیاده‌سازی قرارداد `contracts/HQ_CORE_API_v1.md` (پرامپت ۴). توضیح کامل: `docs/ops/CORE.md`.

| مسیر | چه چیزی |
|---|---|
| `src/hq_api/` | پکیج `hq_api`: `python -m hq_api` (API) و `python -m hq_api.worker` (Temporal، task queue ‏`hq-core`) |
| `src/hq_api/routes/` | یک ماژول برای هر بخش قرارداد؛ `internal.py` برای `/internal/v1` |
| `src/hq_api/domain/` | قاعده‌ها: کار و ارجاع، تصمیم‌ها و اثرشان، اعلان و خلوت، امتیاز، قالب‌ها، زمان‌بندی |
| `src/hq_api/security/` | کلید عبور (WebAuthn)، نشست، step-up، توکن ایجنت و CSRF |
| `src/hq_api/channels/` | Web Push (VAPID)، FCM و تلگرام (پشتیبان؛ بدون تأیید) |
| `migrations/` | Alembic (جدول نسخه‌ی `alembic_version_api`)، SQL خام: RLS، triggerها، grantها |
| `seed/` | قالب‌های شرکت (`templates/*.yaml`) و تکمیل شرکت‌ها؛ فقط جایگاه‌های رهبری |
| `openapi/hq-api.v1.json` | OpenAPI 3.1 ساخته‌شده از کد (`make openapi`). CI عدم تطابق را رد میکند |
| `tests/` | pytest روی Postgres، NATS، Temporal و OPA واقعی؛ authenticator نرم‌افزاری، Schemathesis و سناریوی قبولی |

**اجرای تست‌ها:** `HQ_TEST_TARGET=api services/scripts/test-env.sh run sh -c 'cd /api && pytest tests'`، یا همه‌ی گیت‌ها با `make check`.

**قوانین:**
- هیچ endpoint حذف داده‌ی کسب‌وکار وجود ندارد.
- هر تغییر یک ردیف Audit در همان تراکنش میسازد و هر اقدام مالک یک ردیف `owner.interactions`.
- هیچ متن پیام یا رازی در لاگ، Audit یا NATS نمیرود.
