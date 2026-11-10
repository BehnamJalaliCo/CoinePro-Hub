# گزارش پرامپت ۳۱: «با من» واقعاً قدم‌به‌قدم، و اصلاح‌های بازبینی عمیق (deploy)

> Claude سرور هاب، ۲۰۲۶-۱۱-۱۰.
> - **شاخه:** `server/p31-deploy` = شاخه‌ی اصلی `acbb120a` + merge گزارش ۳۰.۱ (`server/p30-1-deploy`). commit کد از خودم لازم نشد.
> - **alembic:** `0058` (migration ندارد).

## خلاصه
- **deploy:**
  - api و worker (همان image)، gateway و llm-router تازه‌اند.
  - OPA سیاست تازه را خودش خواند (`--watch`).
  - runner کارگاه هلدینگ **0.3.3** شد.
- **`verify-live`:** سبز است: rc=0، بی FAIL؛ فقط دو GAP همیشگی.
- **بکاپ پیش از deploy:** `20261110T024011Z`
- **دست‌نخورده:** هیچ داده‌ای پاک، بسته یا لغو نشد. هیچ جوابی از طرف مالک فرستاده نشد. هیچ رمزی چاپ نشد.

## ۱. تست‌ها
همه‌ی مجموعه اجرا شد، نه فقط فایل‌های نام‌برده، چون ۱۶ فایل api عوض شده بود.

| بخش | نتیجه |
|---|---|
| services: ‏hq-common، llm-router (با تست‌های دیتابیسی)، claude-runtime، gateway و بقیه | **۱۲۸۰ سبز** |
| company-runner | **۱۳۶ سبز** |
| api (کل، با fuzz و پوشش) | **۱۵۶۴ سبز، ۱ قرمز** (۱ ساعت و ۱۸ دقیقه) |
| `opa test` | **۳۰۳ از ۳۰۳** |
| lint، format و mypy | سبز |

**آن یک قرمز:** `test_runs_hard.py::test_a_long_streamed_answer_keeps_beating_and_is_stored`.
- **علت:** آزمون زمان‌سنج است. نخستین فاصله‌ی ضربان 0.598 ثانیه شد، در حالی که حدش 0.5 است. ۲۳ فاصله‌ی دیگر 0.05 بودند، پس سرور زیر بار مجموعه‌ی کامل برای یک لحظه کند شده بود.
- **این تست در ۳۱ عوض نشده است.** آخرین تغییرش `8c04a3e5` (پرامپت ۲۸) است.
- **تکرار:** جدا **۳ بار از ۳** سبز شد، و کل `test_runs_hard.py` هم ۱۳ از ۱۳.
- **نتیجه:** لرزش زمان‌بندی است، نه عیب کد. چیزی عوض نشد.

## ۲. deploy
| زمان (UTC) | کار | نتیجه |
|---|---|---|
| 02:40 | `make backup` | `20261110T024011Z` |
| 02:41 | checkout ‏`server/p31-deploy`؛ build ‏`api`، `gateway` و `llm-router` | ساخته شد |
| 02:42 | `up -d --wait llm-router api worker gateway` | همه healthy |
| 02:42 | OPA | `a2_grants.system` در OPA زنده هست؛ `workshop.stop` در ابزارهای gateway هست |
| 02:44 | runner کارگاه: `git archive` → `pip install --require-hashes` و `--force-reinstall` → restart ‏`hq-runner@studio` | **0.3.3**، هاب: `online`؛ پیش از restart هیچ کار کارگاهی در صف یا در جریان نبود |
| 02:45– | `make verify-live` | **rc=0**، بی FAIL؛ فقط دو GAP همیشگی |

## ۳. سنجش‌های فقط خواندنی
| سنجش | نتیجه |
|---|---|
| کلید صدای Google AI Studio در هاب | **هست**: `kv/hq/voice/google` (Gemini TTS از `generativelanguage.googleapis.com`)، ۲ نسخه، آخرین تغییر 2026-11-05. از راه دوم، پروفایل مرورگر `aistudio-web`، هیچ صدایی ساخته نشده است (Audit ‏`speech.account` خالی است). |
| حساب دوم Claude (`claude-max-2`) | `status` = **`enabled`**؛ هنوز هیچ `quota_status` ندارد، چون تا امروز هیچ فراخوانی رویش نرفته است |
| حساب اول (`claude-max`) | `enabled`؛ `quota_status` = `warning`، پنجره‌ی `seven_day`، **۹۱٪**، ریست 2026-11-12 00:00 UTC (دیده‌شده 2026-11-10 00:21) |
| جلسه‌ی «با من» باز | **نیست.** صفر فرمان روی هاب. مالک ۲۰۲۶-۱۱-۱۰ ساعت 00:28 پاک کردن هاب را خواست، با «هیچ کاری باز نباشد». |

این گزارش را برای Claude سشن مشورت ببر.
