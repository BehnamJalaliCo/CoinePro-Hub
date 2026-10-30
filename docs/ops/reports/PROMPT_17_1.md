# گزارش پرامپت ۱۷.۱: deploy متوقف شد (make check قرمز)

> Claude سرور هاب، ۲۰۲۶-۱۰-۳۰.
> - **وضعیت:** 🔴 قرمز. طبق قدم ۱ پرامپت، جلوتر نرفتم.
> - **deploy:** انجام نشد. نه `make backup`، نه migration ۰۰۳۲، نه ساخت image، نه OPA و نه Caddy.
> - **سرور زنده:** دست نخورده است و همان `server/p15-2-companies` است. کلید توقف هم همان است که مالک گذاشته.
> - **شاخه:** `server/p17-1-deploy` از `claude/coinepro-hub-setup-hsvnw7` در 45d81c5. هیچ کدی عوض نشد؛ فقط همین گزارش اضافه شد.

## ۱. نتیجه‌ی `make check` (۷۸ دقیقه، rc=2)
- **سبز:** compose-config، ports، compose-rules، shellcheck، yamllint، hadolint، opa (183/183)، backup، provisioning، python lint، python audit و live.
  - live همان دو GAP قبلی را دارد: رسیدن egress و searxng با IP. بستنشان قانون DOCKER-USER مالک است.
- **قرمز:** gitleaks، memory-budget، infra و python test.

## ۲. قرمزهایی که از کد پرامپت ۱۷ است (کار سشن مشورت)
python test: ۴ شکست و 921 قبول.

1. **`test_identity.py::test_no_endpoint_works_without_authentication`**
   - `POST /api/v1/runners/pair` بدون احراز هویت `422` میدهد (`fields.company: Field required`)، ولی آزمون `401` میخواهد.
   - این مسیر برای جفت‌سازی runner عمداً عمومی است. پس یا آزمون باید آن را در فهرست مسیرهای عمومی با پاسخ مورد انتظارش بیاورد، یا مسیر باید پیش از اعتبارسنجی بدنه جواب درستی بدهد. تصمیمش با طراح قرارداد است.
2. **`test_p16_fresh_start.py`، دو آزمون:**
   - `test_what_ran_goes_what_the_hub_is_made_of_stays`
   - `test_a_table_in_no_list_or_a_kept_row_pointing_at_wiped_data_stops_it`
   - هر دو با این پیام می‌ایستند:
     `fresh start: tables in no list: infra.runner_pairings, infra.runners, infra.server_jobs, infra.server_job_events, infra.network_links, control.server_policy`
   - شش جدول تازه‌ی migration ۰۰۳۲ باید در یکی از فهرست‌های WIPE، KEEP یا ASK در `hq_api.fresh_start` بیایند.
   - **اثر در سرور زنده:** فقط `make fresh-start` امن می‌ایستد؛ بقیه‌ی کارها اثری نمی‌گیرند.
3. **`test_p11_meetings.py::test_a_meeting_runs_end_to_end_with_the_fake_model`**
   - نوبت‌های دیده‌شده `statement، challenge، minutes` است، یعنی نوبت `vote` جا افتاده.
   - **قطعی است، نه تصادفی:** تنها دوباره اجرا شد و باز شکست خورد.
   - **روی سرور زنده سبز است:** همین آزمون روی `server/p15-2-companies` در یک worktree موقت سبز شد. پس از تغییرات بعد از ۱۵.۲ آمده است.
   - **علت:** بررسی نشد، چون این پرامپت فقط deploy است.
   - **فایل‌های عوض‌شده در این بازه:** `agents/roles/*.md`، `agents/tools.md`، `agents/protocols/oversight.yaml`، `hq_api/domain/decisions.py`، `studio*.py` و `routes/workshop.py`.
4. **gitleaks:** سه یافته‌ی `generic-api-key` در `apps/android`:
   - `app/src/test/java/com/coinepro/hq/ErrorLogTest.kt:60`، رشته‌ی آزمون پوشاندن کلید.
   - `app/src/debug/assets/demo-fixtures.json:44502` و `:49489`.
   - به نظر مثبت کاذب‌اند، چون داده‌ی آزمون و نمونه‌اند. ولی `apps/android` مال سشن مشورت است: یا نمونه‌ها عوض شوند، یا fingerprintها در فهرست مجاز gitleaks بیایند.

## ۳. قرمزهایی که پیش از پرامپت ۱۷ بود
این دو در سرور زنده هم هستند. `infra/compose`، `infra.sh` و `memory-budget.sh` بین `server/p15-2-companies` و شاخه‌ی اصلی عوض نشده‌اند.

1. **memory-budget:**
   - `lean+substitutes` (6384 > 6196 MiB) و `lean+substitutes-web` (6320 > 6196 MiB) بیش از بودجه‌اند، بدون یادداشت «not enabled».
   - **علت:** حافظه‌ی browser-web در ۱۵.۲، با اجازه‌ی مالک، 300 MiB بیشتر شد.
   - سرور روی پروفایل full است و همه‌ی ترکیب‌های full سبزند.
2. **infra:** پنج آزمون دروازه‌ی حافظه شکست خورد: stt، mcp، substitutes، media و ocr.
   - **علت:** از 478a4b7 (۲۰۲۶-۱۰-۳۰ 04:11Z، بعد از `make check` و deploy ۱۵.۲)، `hq.sh` پروفایل‌های اختیاری را با RAM همین سرور (15608 MiB) میسنجد. آزمون‌های infra هنوز بودجه‌ی مرجع را انتظار دارند.
   - باید یکی از این دو با دیگری هماهنگ شود: آزمون‌ها یا رفتار `hq.sh`.

## ۴. downgrade migration ۰۰۳۲
- آزمون رفت‌وبرگشت در `make check` سبز بود: `test_p13f_join.py::test_a_round_trip_keeps_a_card_of_every_later_kind`.
  - این آزمون دیتابیس آزمایشی را تا 0009 پایین میبرد، که downgrade ۰۰۳۲ را هم شامل است. بعد دوباره تا 0032 بالا میآورد.
- `test_p12f_join` هم سبز بود: زنجیره‌ی 0031 → 0032 و یک head واحد.
- روی دیتابیس زنده هیچ downgrade یا upgradeی اجرا نشد.

## ۵. یک اشتباه من در این اجرا (برطرف شد)
- **چه شد:** شاخه‌ی `server/p17-1-deploy` را در خود checkout زنده ساختم، از 17:23:56 تا 18:45:08 UTC.
  - چند کانتینر زنده از همین checkout فایل میخوانند: `agents/` در api، worker و gateway، و `infra/opa/policy` در OPA که با `--watch` خودکار بارگذاری میشود.
  - پس در این ۸۱ دقیقه، منشورها و سیاست‌های OPA شاخه‌ی اصلی روی کد ۱۵.۲ بارگذاری بود.
- **برطرف شد:** checkout به `server/p15-2-companies` برگشت و OPA دوباره همان سیاست‌های زنده را خواند.
- **اثرش:**
  - در این بازه هیچ اجرای ایجنتی نبود (`agents.runs`: 0).
  - api، gateway و OPA هیچ خطایی ثبت نکردند.
  - worker نُه بار `reconcile_schedules` را ناموفق گزارش داد. این خطا پیش از این بازه هم بود: پنج بار از 15:00 تا 17:23، همان خطای باز Temporal. بعد از برگشت، صفر بار.
- **از این به بعد:** `make check` را در یک worktree جدا اجرا میکنم. checkout زنده فقط هنگام خود deploy عوض میشود.

## ۶. قدم بعدی
1. **سشن مشورت:**
   - چهار آزمون بخش ۲ را درست کند.
   - برای gitleaks تصمیم بگیرد.
   - درباره‌ی هماهنگ کردن memory-budget و infra با `hq.sh` نظر بدهد.
2. **سرور هاب:** بعد از push، پرامپت ۱۷.۱ را از اول اجرا میکند.
3. **مالک:** نصب runner روی سرورها (`COMPANY_SERVER_ACCESS_SETUP.md`) تا deploy سبز صبر میکند.
