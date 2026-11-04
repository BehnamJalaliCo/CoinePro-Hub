# وضعیت کار Claude ساخت (هفته‌ی ۲، خط تولید و رشد)

> به‌روز: ۲۰۲۶-۱۱-۰۴. اگر نشست قطع شد، Claude بعدی از همین‌جا ادامه میدهد.

## چه ساخته شد
| بخش | وضعیت | کجا |
|---|---|---|
| قرارداد §۳۰ خط تولید و §۳۱ رشد (v1.13) | ✅ | `contracts/HQ_CORE_API_v1.md` |
| موتور خط تولید (migration `0040`) | ✅ | `apps/api/src/hq_api/lines/`، `routes/lines.py` |
| مرحله‌ها، n8n، recipeهای `aistudio-web` و `pinterest-web` | ✅ | `lines/adapters/`، `infra/` پروفایل `automations` |
| حلقه‌ی یادگیری §۳۱.۱ و شرکت آماده §۳۱.۲ | ✅ | `lines/learning.py`، `domain/kits.py`، `seed/kits/` |
| خبرنامه، سئو و رقبا، تقویم کمپین (migration `0041`) | ✅ | `domain/newsletter.py`، `domain/campaigns.py`، پروفایل `newsletter` |
| تبلیغات با توقف خودکار و اتوماسیون از یک جمله (migration `0042`) | ✅ | `domain/ads.py`، `domain/automations.py` |
| اپ‌ها 0.12.0 (اندروید و وب) | ✅ | `ui/v30`، `ui/v31`، `components/v30`، `components/v31` |
| پرامپت deploy | ✅ مرحله‌ای | `docs/server-prompts/PROMPT_22_DEPLOY.md` |
| کارهای مالک | ✅ | `OWNER_STEPS.md` (همین پوشه) |
| بازبینی جاهای خالی در برابر Grok | ✅ | `docs/GAP_REVIEW_2026-11-04.md` |

## شاخه‌ها
- **یکپارچه:** `build/w2-lines`. همه‌ی شاخه‌های هفته‌ی ۲ در آن merge شده است: `w2-engine`، `w2-adapters`، `w2-kit`، `w2-growth`، `w2-ops`، `w2-web` و `w2-android`.
- **ترتیب migrationها:** `0039` ← `0040` ← `0041` ← `0042`. تست‌های زنجیره (`test_p12f_join`، `test_p13f_join`) head را `0042` میدانند.

## درس‌های این هفته
- **نام مدل‌های Pydantic یکتا باشد.** اگر دو مدل هم‌نام شوند، FastAPI هر دو را در OpenAPI به نام کامل ماژول تغییر میدهد (مثلاً `hq_api__domain__work__ScheduleIn`). آن وقت تست‌های اندروید که نام schema را میخوانند، با NPE میشکنند.
  - **پیش از commit:** نام‌های schema را با شاخه‌ی اصلی مقایسه کن. هیچ نامی نباید گم شود.
- **حین اجرای `record` در CI روی همان شاخه push نکن.** push خود record شکست میخورد.
- **کد وضعیت:** خطای ورودی (جمله‌ای که قاعده نمیشود) ۴۲۲ است. ردِ پلتفرم بیرونی (مثلاً Google Ads) ۵۰۲ است.

## کارهای مانده
- **deploy:** پرامپت ۲۲ (مرحله‌ی ۱) به Claude هاب داده شود. مرحله‌ی ۲ فقط با گفته‌ی مالک انجام میشود.
- **0.12.1، صیقل اپ:**
  - کلیدهای خام (`content`، `reach`، `followers`) در پیش‌نمایش شرکت آماده.
  - فیلد خام RRULE در ویرایشگر خط باید زیر «پیشرفته» برود.
  - کلیدهای خام داده در مرحله‌ی کنترل کیفیت.
