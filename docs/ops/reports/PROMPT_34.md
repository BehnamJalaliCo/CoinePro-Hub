# گزارش پرامپت ۳۴: اجازه‌ی دائمی انتشار (deploy)

> Claude سرور هاب، ۲۰۲۶-۱۱-۱۰.
> - **شاخه:** `server/p34-deploy` = شاخه‌ی اصلی `d1842d64` + merge ‏`server/p33-deploy`. commit کد از خودم لازم نشد.
> - **alembic:** `0058` → **`0059`**.

## ۳۲ و ۳۳
- **پیش‌تر deploy شده بودند.** پرامپت میگوید «۳۲ هنوز اجرا نشده»، اما مالک امروز صبح، پیش از رسیدن ۳۴، دستور «۳۲ و بعد ۳۳ را پشت سر هم اجرا کن» داده بود. هر دو deploy و گزارش شدند: `PROMPT_32.md` (`59cc19c2`) و `PROMPT_33.md` (`165f9f56`)، و کل مجموعه‌ی api روی کد ۳۲ ‏۱۵۷۰ سبز شد.
- **کار این پرامپت:** فقط تفاوت ۳۴ رفت. شاخه‌ی ۳۴ آن دو را در خود دارد.

## خلاصه
- **deploy:**
  - بکاپ گرفته شد، بعد migration ‏`0059` (ستون افزودنی `growth.memberships.publish`).
  - api و worker (همان image) و gateway تازه‌اند. منشورهای نسخه‌ی ۱۵ با همین image میآیند.
- **تست‌ها:**
  - api: `test_w18_standing_publish`، `test_w17_session_publish`، `test_w10_playbooks`، `test_p21_groups`، `test_p12f_join`، `test_p13f_join`، `test_w8_capabilities`، `test_w16_direct_sessions`، `test_rls_all_tables`، `test_schema_rules` و سند OpenAPI: **۷۶ از ۷۶ سبز**.
  - gateway و hq-common سبز. OPA ‏۳۰۳ از ۳۰۳. lint و mypy سبز.
- **`verify-live`:** سبز است: rc=0، بی FAIL؛ فقط دو GAP همیشگی.
- **بکاپ پیش از migration:** `20261110T103151Z`
- **دست‌نخورده:**
  - هیچ اجازه‌ی دائمی‌ای روشن نشد (`growth.memberships.publish` همه‌جا خالی است، ۰ ردیف).
  - هیچ چیزی منتشر نشد.
  - هیچ داده‌ای پاک، بسته یا لغو نشد، و در هیچ جلسه‌ای چیزی نوشته نشد.
  - به هیچ سروری جز هاب دست زده نشد.

## سنجش‌ها (فقط خواندنی، از دیتابیس هاب)

**ورودها:**

| سنجش | نتیجه |
|---|---|
| Google AI Studio (ورود وب، `voice.aistudio`) | **`unknown`**: در ۳۰ روز گذشته هیچ صدایی ساخته نشده، پس هاب پاسخی از آن ندیده است. اگر نخستین صدا `signed_out` گفت، مالک یک بار `make aistudio-web-login` بزند. کلید API ‏(`kv/hq/voice/google`) جداست و ثبت است. |
| ChatGPT (`gpt`) | **`signed_in`**، هم `codex_cli` و هم وب؛ `ready`. خطای وب قبلی (`recipe_failed`، 11-09) مهلتش گذشته است. |

**حساب‌های Claude:**

| حساب | حال |
|---|---|
| `claude-max-2` | **`enabled`**؛ هنوز `quota_status` ندارد |
| `claude-max` | `enabled`، `warning`، پنجره‌ی `seven_day`، **۹۱٪**، ریست 2026-11-12 00:00 UTC |

**سرورها:**

| سرور | حال |
|---|---|
| IG-Hub | شرکت **IG**، runner **0.3.2**، **online** |
| کارگاه هلدینگ (`workshop`) | runner **0.3.3**، online. هنوز 0.3.4 نیست، پس `sandbox` نوبت‌ها گزارش نمیشود. ارتقا با مالک است. Audit ‏`workshop.sandbox_off`: ۰. |

**اتصال `instagram` هر شرکت** (`growth.connections`):

| شرکت | کلیدهای `config` | `accounts` | `command` | `publish_command` |
|---|---|---|---|---|
| FX | `accounts`، `server`، `via` | ۱ | نیست | نیست |
| IG | `accounts`، `server`، `via` | ۲ | نیست | نیست |
| PC | `accounts`، `server`، `via` | ۱ | نیست | نیست |
| TY | `accounts`، `server`، `via` | ۰ | نیست | نیست |

| سنجش | نتیجه |
|---|---|
| کار فنی باز با `ig_setup` یا `ig_publish` | **نیست** (۰) |
| صندلی مدیر فنی IG-Hub و AIOPS هلدینگ | **هر دو پر و فعال‌اند** (`IG-TECH-MGR`، `HQ-AIOPS-MGR`) |
| کارگروه‌های مُهرشده (`owner.playbooks`، `sealed`) | **هیچ**: جدول خالی است (پاک کردن ۲۰۲۶-۱۱-۱۰ ساعت 00:28 به دستور مالک) |

**یعنی:** نخستین کارگروهی که مالک مُهر میکند، اجازه‌ی دائمی را در همان مُهر میگیرد. اما تا مسیر انتشار شرکت (`publish_command`) ثبت نشود، هاب انتشار را به کار فنی مدیر فنی IG-Hub میسپارد.

این گزارش را برای Claude سشن مشورت ببر.
