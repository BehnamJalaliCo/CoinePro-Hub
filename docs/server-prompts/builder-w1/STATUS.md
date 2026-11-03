# وضعیت کار Claude ساخت (هفته‌ی ۱، برنامه‌ی تمرکز مدیر کل)

> به‌روز: ۲۰۲۶-۱۱-۰۳ 06:00 UTC. اگر نشست قطع شد، Claude بعدی از همین‌جا ادامه میدهد.

## مرحله‌ها
| مرحله | وضعیت | کجا |
|---|---|---|
| A کاهش هزینه و GPT وب (۲۰.۱) | ✅ ساخته و آزموده؛ در شاخه‌ی اصلی merge شد (2741c81) | `docs/server-prompts/PROMPT_20_1_DEPLOY.md` |
| B بازبینی مدیریت | ✅ | `docs/MANAGEMENT_REVIEW_2026-11.md`، منشورهای `publisher` و `content_analyst` |
| C قرارداد §۲۹ (v1.11) | ✅ | `contracts/HQ_CORE_API_v1.md` §۲۸.۷ و §۲۹ |
| D ساخت هاب (۲۱) | ✅ هر سه بخش merge شد، با تست سرتاسری فرمان کلیپ؛ مسیر `readiness/fix` و کلید `HQ_GROUPS`؛ ۹ شکست اجرای کامل درست شد؛ ۵۰۳های طراحی‌شده‌ی صدا و اتصال حالا ۴۰۹ `channel_not_configured` هستند | `PROMPT_21_DEPLOY.md` |
| E اپ‌ها (0.11.0) | ✅ وب و اندروید هر دو در `build/w1-owner-focus` merge شدند؛ عکس‌های v29 با اجرای `record` در CI ساخته و دیده شدند | `apps/CHANGELOG.md` |
| F هفته‌ی پذیرش | 🟡 فهرست کارهای یک‌باره‌ی مالک آماده است | `OWNER_STEPS.md` |

## شاخه‌ها
- **کار اصلی:** `build/w1-owner-focus` (همه‌ی A تا C، به‌علاوه‌ی `humanize`، و **جای خالی migration 0037 تا 0039**).
  - ⚠️ **جای خالی migrationها را پیش از پر شدن هرگز در شاخه‌ی اصلی merge نکن.** اگر 0037 تا 0039 خالی deploy شوند، alembic آن‌ها را اجراشده میداند و نسخه‌ی واقعی بعدی اجرا نمیشود.
- **آماده‌ی deploy ۲۰.۱:** `build/w1-a-ready` (بی جای خالی migration) → merge شده در `claude/coinepro-hub-setup-hsvnw7`.
- **D (پرامپت ۲۱):** `build/w1-d-p21a` (مسیر حوزه، گزارش فرمان، بودجه، استخدام خودکار، وضعیت کارمند، خاموش کردن پروتکل‌ها؛ migration 0037)، `build/w1-d-p21b` (منشی، صدای بلند، قانون مالک، زبان، شورای v2؛ 0038)، `build/w1-d-p21c` (کارگروه‌ها، اتصال‌ها، خانه، آمادگی، seed؛ 0039). شرح کار هر کدام: `common.md` و همین پوشه.
- **E:** `build/w1-e-web` و `build/w1-e-android`. شرح کار: `apps.md`.

## کارهای مانده (به ترتیب)
1. CI `quality` و `clients` روی `build/w1-owner-focus` سبز شود.
2. `git merge --no-ff build/w1-owner-focus` در `claude/coinepro-hub-setup-hsvnw7`، و push. APK 0.11.0 را CI شاخه‌ی اصلی در `android-latest` منتشر میکند.
3. گزارش کوتاه D، E و F به مالک: پرامپت‌های `PROMPT_20_1_DEPLOY.md` و `PROMPT_21_DEPLOY.md` برای Claude سرور هاب، و `OWNER_STEPS.md`.

## نکته‌های محیط (نشست ابری، بی سرور هاب)
- **Docker:** `dockerd` دستی بالا میآید. Docker Hub محدودیت دارد؛ image‌ها از `mirror.gcr.io/...` گرفته و با نام اصلی tag شدند.
- **image تست:** با CA پروکسی ساخته میشود (Dockerfile موقت در scratchpad)؛ `services/scripts/test-env.sh` در نسخه‌ی scratchpad گام build را ندارد.
- **pytest:** `addopts` خودش `-q` دارد؛ `-q` دوم خلاصه را پنهان میکند. از `-rA` استفاده کن.
- **CI `quality` چند روز همیشه با سقف ۴۵ دقیقه لغو میشد.**
  - **علت:** `HQ_FUZZ_EXAMPLES` هرگز به کانتینر تست نمیرسید (`services/scripts/test-env.sh` آن را رد نمیکرد). پس fuzz همیشه با ۸ نمونه و همه‌ی فازها اجرا میشد: حدود ۲۰٬۰۰۰ مورد و ۲۸ دقیقه.
  - **درست شد (6889d258):** `test-env.sh` حالا `HQ_FUZZ_EXAMPLES` و `HQ_FUZZ_PHASES` را رد میکند. push فقط فازهای `examples,fuzzing` را اجرا میکند و nightly همه‌ی فازها را.
- **اندروید:** SDK نصب نمیشود؛ CI کامپایل میکند و اجرای دستی `clients.yml` با `record: true` عکس‌ها را میسازد و به شاخه commit میکند.
