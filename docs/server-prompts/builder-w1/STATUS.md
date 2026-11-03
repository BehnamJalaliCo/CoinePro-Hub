# وضعیت کار Claude ساخت (هفته‌ی ۱، برنامه‌ی تمرکز مدیر کل)

> به‌روز: ۲۰۲۶-۱۱-۰۳ 00:30 UTC. اگر نشست قطع شد، Claude بعدی از همین‌جا ادامه میدهد.

## مرحله‌ها
| مرحله | وضعیت | کجا |
|---|---|---|
| A کاهش هزینه و GPT وب (۲۰.۱) | ✅ ساخته و آزموده؛ در شاخه‌ی اصلی merge شد (2741c81) | `docs/server-prompts/PROMPT_20_1_DEPLOY.md` |
| B بازبینی مدیریت | ✅ | `docs/MANAGEMENT_REVIEW_2026-11.md`، منشورهای `publisher` و `content_analyst` |
| C قرارداد §۲۹ (v1.11) | ✅ | `contracts/HQ_CORE_API_v1.md` §۲۸.۷ و §۲۹ |
| D ساخت هاب (۲۱) | 🟡 سه بخش موازی، هر کدام روی شاخه‌ی خودش | پایین |
| E اپ‌ها (0.11.0) | 🟡 دو بخش موازی | پایین |
| F هفته‌ی پذیرش | ⏳ بعد از deploy ۲۱ | — |

## شاخه‌ها
- **کار اصلی:** `build/w1-owner-focus` (همه‌ی A تا C، به‌علاوه‌ی `humanize`، و **جای خالی migration 0037 تا 0039**).
  - ⚠️ **جای خالی migrationها را پیش از پر شدن هرگز در شاخه‌ی اصلی merge نکن.** اگر 0037 تا 0039 خالی deploy شوند، alembic آن‌ها را اجراشده میداند و نسخه‌ی واقعی بعدی اجرا نمیشود.
- **آماده‌ی deploy ۲۰.۱:** `build/w1-a-ready` (بی جای خالی migration) → merge شده در `claude/coinepro-hub-setup-hsvnw7`.
- **D (پرامپت ۲۱):** `build/w1-d-p21a` (مسیر حوزه، گزارش فرمان، بودجه، استخدام خودکار، وضعیت کارمند، خاموش کردن پروتکل‌ها؛ migration 0037)، `build/w1-d-p21b` (منشی، صدای بلند، قانون مالک، زبان، شورای v2؛ 0038)، `build/w1-d-p21c` (کارگروه‌ها، اتصال‌ها، خانه، آمادگی، seed؛ 0039). شرح کار هر کدام: `common.md` و همین پوشه.
- **E:** `build/w1-e-web` و `build/w1-e-android`. شرح کار: `apps.md`.

## کارهای مانده (به ترتیب)
1. سه شاخه‌ی D را در `build/w1-owner-focus` merge کن؛ تعارض‌ها معمولاً در `app.py`، `worker/schedules.py`، `agents/tools.md`، ابزارهای gateway و OPA است.
   - تابع‌هایی که بخش‌ها از هم صدا میزنند: `order_report.on_order_routed`، `hiring.auto_fill`، `dispatch.remember`. هر کدام با `ImportError` محافظت شده؛ بعد از merge مستقیم وصلشان کن.
2. `apps/api/openapi/hq-api.v1.json` را یک بار از کد بساز (`python -m hq_api.openapi_export` در image تست).
3. تست سرتاسری: فرمان کلیپ تریدیار (متن دقیق در `docs/ops/reports/PROMPT_20.md` §1.1) از منشی تا کارگروه و گزارش فرمان؛ بازنویسی انسانی روی همه‌ی انواع اعلان؛ هیچ یافته‌ی فنی غیربحرانی در خانه.
4. `docs/server-prompts/PROMPT_21_DEPLOY.md`: deploy مرحله‌ای (migration 0037 تا 0039)، روشن کردن کارگروه و روال‌ها جدا، سنجش با عدد، گزارش `docs/ops/reports/PROMPT_21.md`.
5. E: دو شاخه را merge کن، `apps/VERSION` و `package.json` (و lock) را 0.11.0 کن، یک خط در `apps/CHANGELOG.md`. APK فقط از CI شاخه‌ی اصلی منتشر میشود.
6. F: فهرست کارهای یک‌باره‌ی مالک (کدام اتصال با کدام حساب، کدام سری انتشار را مُهر کند).

## نکته‌های محیط (نشست ابری، بی سرور هاب)
- **Docker:** `dockerd` دستی بالا میآید. Docker Hub محدودیت دارد؛ image‌ها از `mirror.gcr.io/...` گرفته و با نام اصلی tag شدند.
- **image تست:** با CA پروکسی ساخته میشود (Dockerfile موقت در scratchpad)؛ `services/scripts/test-env.sh` در نسخه‌ی scratchpad گام build را ندارد.
- **pytest:** `addopts` خودش `-q` دارد؛ `-q` دوم خلاصه را پنهان میکند. از `-rA` استفاده کن.
- **CI `quality` چند روز است همیشه با سقف ۴۵ دقیقه لغو میشود** (روی شاخه‌ی اصلی هم، پیش از این کار). علت: آزمون fuzz کل API (`tests/test_openapi.py`) طولانی است؛ nightly با ۹۰ دقیقه هم لغو میشود. باید یا fuzz روی push سبک شود یا سقف زمان بالا برود (تصمیم کوچک CI). سنجش‌ها تا آن موقع محلی است و `make check` روی هاب هنگام deploy.
- **اندروید:** SDK نصب نمیشود؛ CI کامپایل میکند و اجرای دستی `clients.yml` با `record: true` عکس‌ها را میسازد و به شاخه commit میکند.
