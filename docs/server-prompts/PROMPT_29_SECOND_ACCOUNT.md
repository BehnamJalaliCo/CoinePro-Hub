# پرامپت ۲۹: اکانت دوم Claude برای هاب و سرور شرکت‌ها، و پیشنهاد سری رسانه

> Claude سشن مشورت، ۲۰۲۶-۱۱-۰۹.
> - **پیش‌نیاز:** پرامپت ۲۸.۴ deploy و سبز.
> - **شاخه:** `server/p29-deploy` از `claude/coinepro-hub-setup-hsvnw7`.
> - **گزارش:** `docs/ops/reports/PROMPT_29.md`.
> - **قرارداد:** §۲۶.۲ (فیلد `claude_oauth`). **سند:** `docs/ops/LLM_LAYER.md` §۶ و §۹.

## چرا (تصمیم مالک، ۲۰۲۶-۱۱-۰۹)
- مالک یک اکانت دوم Claude خرید، چون اکانت اول زود تمام میشود.
- **خواسته‌ی مالک:**
  - وقتی اکانت اول تمام شد، یا به **۹۹٪** پنجره‌اش رسید، کارها خودکار روی اکانت دوم بروند.
  - شرکت‌ها اشتراک جدا ندارند؛ کار Claude Code روی سرور هر شرکت هم با همین اکانت دوم از هاب انجام شود.
- **چرا مالک موفق نشد دو Claude را روی یک سرور بالا بیاورد:** دو لاگین تعاملی در یک `~/.claude` با هم قاطی میشوند.
  - روش درست، توکن `claude setup-token` است که فقط به پروسه‌ی هر اجرا داده میشود.
  - claude-runtime همین الان برای هر اجرا HOME جدا دارد.

## چه عوض شده (کد در شاخه‌ی اصلی)
- **claude-runtime:**
  - `kv/claude-runtime/oauth-2` را هم میخواند.
  - `RunBody.account = "2"` اجرا را با همان توکن انجام میدهد.
  - health فیلد `oauth_2` را دارد و `/v1/status` فیلد `accounts` را.
  - **تست:** `test_the_second_account_runs_on_its_own_token`.
- **llm-router:**
  - **اتصال تازه در seed:** `claude-max-2` (`claude_subscription`)، با `secret_ref = kv/claude-runtime/oauth-2`، خاموش (`disabled`) و `fallback_priority = 0`.
  - به runtime فیلد `account` را میفرستد.
  - **سوییچ:** اکانت اصلی در ۹۹٪ (`QuotaController.near_full`)، رد شده، breaker باز، یا P3/P4 نگه‌داشته‌شده → اکانت دوم، برای هر کار و هر اولویت. `meta.fallback_from` ثبت میشود.
  - **تست‌ها:**
    - `test_the_second_subscription_takes_over_when_the_first_is_out`
    - `test_a_subscription_at_99_percent_is_near_full`
    - `test_the_second_account_is_named_to_the_runtime`
- **api:**
  - `Secrets.runner_claude_token` از `kv/claude-runtime/oauth-2` خوانده میشود.
  - **policy:** `infra/openbao/policies/hq-api.hcl` فقط read روی همین مسیر.
  - `SV.runner_job` برای کار `claude` فیلد `claude_oauth` را اضافه میکند، فقط هنگام تحویل؛ نه در args ذخیره‌شده، نه در لاگ.
  - **تست:** `test_w13_second_account.py`.
- **hq-runner 0.3.1:**
  - `claude_oauth` را فقط در env همان پروسه‌ی Claude Code میگذارد و در رویدادها mask میکند.
  - **تست:** `test_a_claude_job_runs_on_the_hubs_account_when_it_sends_one`.
- **`make claude-token SLOT=2`:** در `kv/claude-runtime/oauth-2` مینویسد و claude-runtime و api را restart میکند.
- **یافته‌ی ۲۸.۴: سه رد پشت سر هم `series.propose` مدیر رسانه:**
  - **علت:** ردیف این ابزار در `agents/tools.md` فقط نام فیلدها را داشت. عامل شکل checks، RRULE زمان‌بندی، حساب و topics را حدس زد.
  - **رفع ۱:** ردیف حالا شکل دقیق هر فیلد را دارد، با نمونه‌ی RRULE و نمونه‌ی حساب (`theprochart`، از IG-Hub).
  - **رفع ۲:** api و gateway شکل‌های رایج را همان‌طور که منظور است میخوانند:
    - topics به‌صورت فهرست ← `{pool}`
    - حساب با «@»، فاصله یا حرف بزرگ ← handle ساده
    - نام check ناشناخته ← هر هفت check (هرگز کمتر)
  - خطای واقعی، مثل `kind` نادرست یا RRULE نادرست، همچنان با نام فیلد رد میشود.
  - **تست‌ها:** `apps/api/tests/test_w13_series_shapes.py` و `services/gateway/tests/test_media_tools.py::test_series_shapes_an_agent_writes_are_read_as_meant`.

## کار
1. **شاخه و تست:** شاخه را بساز، شاخه‌ی اصلی را merge کن و تست‌های بخش تغییریافته را اجرا کن:
   - llm-router: کل مجموعه، شامل تست‌های دیتابیسی
   - claude-runtime: `tests/test_runtime.py`
   - api: `tests/test_w13_second_account.py`، `tests/test_openapi.py`
   - company-runner: `tests/test_claude.py`
   - api: `tests/test_w13_series_shapes.py`
   - gateway: `tests/test_media_tools.py`
   - lint و mypy
2. **policy:** policy تازه‌ی `hq-api` را به روال همیشه در OpenBao اعمال کن. توکن و رمزی را عوض، باطل یا چاپ نکن.
3. **seed:** seed روتر را اجرا کن تا ردیف `claude-max-2` ساخته شود. خاموش میماند.
4. **deploy:** `llm-router`، `claude-runtime`، `gateway`، `api` و `worker`. migration ندارد. `agents/tools.md` با image تازه میرسد.
5. **قدم مالک** (فقط مالک، طبق قانون ۵؛ تو انجام نده). در گزارش همین را بنویس:
   1. در ترمینال جدا، به‌عنوان کاربر `Hub`، `claude setup-token` را بزن و در مرورگر با **اکانت دوم** وارد شو. از پروفایل دیگر مرورگر استفاده کن، یا اول از اکانت اول خارج شو.
   2. بعد `make claude-token SLOT=2` و توکن را بچسبان.
6. **بعد از قدم مالک:**
   - مطمئن شو health claude-runtime فیلد `oauth_2: configured` دارد.
   - بعد اتصال را روشن کن:
     ```
     UPDATE llm.connections SET status = 'enabled' WHERE key = 'claude-max-2'
     ```
   - **آزمون کوتاه:** یک فراخوانی P2 با `connection` اجباری روی `claude-max-2`، اگر روتر این امکان را دارد؛ وگرنه فقط health.
7. **سرورهای شرکت‌ها:**
   - runner هر سرور را با بخش «به‌روزرسانی runner» در `docs/server-prompts/COMPANY_SERVER_ACCESS_SETUP.md` به **0.3.1** برسان: `git pull`، نصب دوباره، restart.
   - طبق قانون ۷ این را خودت روی سرور شرکت انجام نمیدهی. دستور سه‌خطی را برای مالک یا Claude همان سرور در گزارش بنویس.
   - تا runner به‌روز نشده، کار `claude` با لاگین خود سرور اجرا میشود (اگر باشد).
8. `verify-live` سبز.

## قوانین
- **رمز:** هیچ توکن، رمز یا مقدار OpenBao چاپ نشود. فقط نام مسیرها.
- **توکن اکانت اول:** `kv/claude-runtime/oauth` دست نخورد.
- **گزارش:** فارسی و کوتاه.
  - خط آخر: «این گزارش را برای Claude سشن مشورت ببر.»
