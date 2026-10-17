# پرامپت ۴.۱: سخت‌سازی هسته پیش از ورود ایجنت‌ها

> **برای مالک:** کل متن زیر خط را کپی کن و به Claude Code روی سرور هاب بده (یا بگو: «`git pull` کن و `docs/server-prompts/PROMPT_04_1_HARDENING.md` را اجرا کن»). این پرامپت **هیچ کاری از تو نمیخواهد** و هیچ سرویس تازه‌ای اضافه نمیکند. گزارش کوتاه آخرش را برای Claude سشن مشورت بیاور.

---

تو **Claude Code روی سرور هاب «CoinePro HQ»** هستی. پرامپت ۴ بازبینی و در شاخه‌ی اصلی merge شد؛ کار خوبی بود. بازبینی چند نقطه پیدا کرد که **باید پیش از پرامپت ۵** (وقتی ایجنت‌های واقعی روی `hq-internal` کار میکنند) بسته شوند. امروز هیچ ایجنتی کار نمیکند، پس هیچ‌کدام الان قابل سوءاستفاده نیست؛ ولی «خشت اول» است.

## ۰. قبل از شروع (اجباری)
1. در `/home/Hub/CoinePro-Hub` آخرین نسخه‌ی `claude/coinepro-hub-setup-hsvnw7` را pull کن (merge پرامپت ۴ در آن است) و شاخه‌ی **`server/p04-1-hardening`** را از آن بساز.
2. **این‌ها را بخوان:** `CLAUDE.md`، `docs/server-prompts/README.md`، و **`contracts/HQ_CORE_API_v1.md` نسخه‌ی 1.1** (همه‌ی بندهای علامت‌خورده با ⟨1.1⟩). `contracts/` مال Claude سشن مشورت است و تغییرش نمیدهی؛ اگر جایی با کد نخواند، امن‌ترین رفتار را پیاده کن و در «Contract notes» بگو.
3. **تسک‌بندی اجباری:** همه‌ی بندهای زیر را در لیست تسک بشکن. **هر بند یک تست دارد** که اول باید روی کد فعلی **شکست بخورد** و بعد از اصلاح پاس شود. بدون توقف جلو برو.
4. **هیچ سرویس تازه، هیچ ریبوت، هیچ تغییری در ورود به سرور.** جمع سقف حافظه نباید بالا برود.

## ۱. باید (پیش از پرامپت ۵)

**۱.۱ کلید توقف و توقف deploy به ترتیب اختیار آزاد میشوند**
- کلیدی که **مالک** زده فقط با **مالک و step-up** آزاد میشود. مدیرعامل (ایجنت) فقط کلیدی را آزاد میکند که **یک ایجنت از همان شرکت** زده باشد. همین قاعده برای کلید هلدینگ.
- توقف deploy: توقف مالک فقط با مالک؛ توقف pipeline با pipeline یا مالک؛ مدیرعامل فقط توقف خودش. `set_deploy_freeze` دیگر «همه‌ی توقف‌های فعال» را برنمیدارد.
- قاعده هم در OPA (`changed_by_kind`/`changed_by_code` در ورودی) و هم در کد. تست: مالک میزند ← `TY-CEO` آزاد میکند ← **403**؛ مالک با step-up آزاد میکند ← ok.

**۱.۲ تاریخچه‌ی امتیاز append-only**
- `core.employee_scores`: ماه‌های گذشته **هیچ تغییری** نمیپذیرند؛ ماه جاری فقط ستون‌های امتیاز را (GRANT روی ستون‌های نام‌برده). `company_id`، `employee_id` و `month` هرگز عوض نمیشوند. DELETE و TRUNCATE برای همه رد. تست برای هر سه.

**۱.۳ OPA و Temporal فقط برای سرویس‌های مجاز**
- OPA با `--authorization=basic` و یک `system.authz` که فقط `POST /v1/data/hq/...` و `GET /health` را میپذیرد. PUT/DELETE روی policy و data از هر کانتینر رد میشود. policyها فقط از فایل بار میشوند.
- Temporal (پورت 7233 بی‌احراز): `api`، `worker`، `opa` و `temporal` (و فقط سرویس‌هایی که واقعاً به Temporal نیاز دارند، مثل `temporal-namespace` و `temporal-ui`) روی یک **شبکه‌ی جدا** (`hq-core`) بروند و Temporal از `hq-internal` برداشته شود. فهرست دقیق را در گزارش بیاور. اگر سرویسی از پرامپت‌های قبل به Temporal وصل است، روی همان شبکه بماند و نامش در گزارش بیاید.
- تست: یک کانتینر موقت روی `hq-internal` نه به OPA (PUT) دسترسی دارد و نه به `temporal:7233`.

**۱.۴ هیچ‌کس پیشنهاد خودش را تأیید نمیکند**
- `proposer` در ورودی OPA؛ `proposer == approver` همیشه رد. پیشنهاد کار دائمی خود مدیرعامل به مالک میرود. تست.

**۱.۵ 🔴 از ایجنت فقط برای حادثه**
- `level` در ورودی OPA. ایجنت فقط برای دسته‌های حادثه (سرویس از کار افتاده، امنیت، از دست رفتن داده، توقف سخت بودجه) میتواند `urgent` بفرستد، با سقف نرخ برای هر شرکت؛ بقیه به `decision` پایین میاید. ایجنت شرکت قفل‌شده جز حادثه‌ی `urgent` اعلان نمیفرستد. تست.

**۱.۶ اعتبارسنجی `budget_change`**
- `scope` نوع‌دار (`holding | company | department | role | task_class`) و فقط داخل شرکت پیشنهاددهنده (پیشنهاد مالک استثناست). ارجاع به شرکت دیگر ← 403. تست.

**۱.۷ اصلاح‌های مالک اجرا میشوند**
- `apply_effect` از payload اصلاح‌شده استفاده میکند و `render` هر دو را برمیگرداند (`payload` و `amendments`). تست: مالک مدل استخدام را عوض میکند ← تخصیص مدل همان مدل اصلاح‌شده است.

**۱.۸ سیاست کلاس اقدام واقعاً اجرا میشود**
- هر نوشتن ایجنت از `hq.actions` هم رد میشود (A0 تا A3 بر اساس نقش و پاکت اختیار، **A4 همیشه رد**). تست: یک عملیات داخلی با کلاس A4 (حتی ساختگی در تست) رد میشود؛ A2 بدون پاکت رد میشود.

**۱.۹ دامنه‌ی ایجنت هرگز باز نمیشود**
- `notify.py` شمارش سهمیه را با یک تابع `SECURITY DEFINER` انجام دهد (مثل `control.lock_state`)، نه با گشودن `app.company_ids` به همه‌ی شرکت‌ها.
- `routes/internal.py`: `allow` **پیش از** هر جستجو در شرکت دیگر. شرکت مقصد هم برای قفل بررسی شود. تست: کد کارمند ناموجود و موجود در شرکت دیگر هر دو **403 یکسان** میدهند.

**۱.۱۰ یکپارچگی داده در خود دیتابیس**
- **کلید خارجی ترکیبی** `(company_id, id)` برای همه‌ی ردیف‌های فرزند: `work.assignee_id`، `work_events.work_id`، `escrows.work_id`، `schedules.work_id`، `deliverables.work_id`/`producer_id`، `ratings.deliverable_id`، `messages.thread_id` (و هر مورد مشابه دیگری که پیدا کردی). تست: درج فرزند با `company_id` متفاوت از والد رد میشود.
- `msg.messages`: `seq`، `ref` و `company_id` را یک trigger از thread میسازد؛ مقدار داده‌شده از بیرون نادیده یا رد میشود.
- تصمیم نهایی‌شده **مُهرشده** است: `status`، `decided_*`، `seal_*`، `note` و `amendments` فقط یک بار نوشته میشوند (trigger). تست.
- `llm.assignments` (بدون `company_id` و RLS): نوشتن فقط از راه یک تابع که دامنه را بررسی میکند، یا فقط برای `hq_worker`. `hq_api` مستقیم نمینویسد.
- `audit.entries.at` همیشه `clock_timestamp()`؛ مقدار ورودی نادیده. ردیف audit آخرِ هر تراکنش نوشته شود (قفل سر زنجیره کوتاه بماند).

**۱.۱۱ لنگر زنجیره‌ی Audit بیرون از Postgres**
- کار شبانه‌ی `AuditVerify`، `seq` و `hash` سر زنجیره را به یک فایل append-only در مجموعه‌ی backup (بیرون از volume پستگرس) اضافه کند؛ `/audit/verify` با آخرین لنگر هم مقایسه کند. تست: بازنویسی کامل زنجیره به‌همراه سر آن، با لنگر پیدا میشود.
- مالک جدول‌ها یک نقش **NOLOGIN** شود؛ `api-migrate` با `SET ROLE` کار کند. اگر این تغییر ریسک دارد، فقط طرحش را در گزارش بده.

**۱.۱۲ لاگ و backup**
- Postgres: `-c log_parameter_max_length=0` (و `log_parameter_max_length_on_error=0`) تا متن پیام‌ها و تصمیم‌ها هرگز به Loki نرود. تست: یک کوئری کند با پارامتر فارسی، در لاگ بدون مقدار.
- volume `hq-files` در `backup.sh` و restore. تست restore روی یک فایل نمونه.
- `llm-router` و `claude-runtime` هم access log uvicorn را خاموش کنند (مثل `apps/api`).

**۱.۱۳ قیمت و رنگ**
- قیمت **cache read** برای `claude-sonnet-5-5` را دوباره از صفحه‌ی رسمی قیمت Anthropic بخوان. انتظار ما **$0.20 / MTok** است (۰٫۱ برابر ورودی)؛ در جدول الان $0.10 است. با `source_url` و `as_of` تازه اصلاح کن. اگر صفحه‌ی رسمی چیز دیگری گفت، همان را بگذار و در گزارش بگو.
- `color_index`: محدوده‌ی **1..8 یا null** (پالت نمودار v2، بی‌چرخش). seed: `PC 1`، `FX 2`، `TY 3`، `HQ null`. migration تازه، بدون تغییر کدها.

**۱.۱۴ کدهای خطا**
- OPA جواب ندهد ← **`503 policy_unavailable`** (نه `policy_denied`). `If-Match` نباشد ← `428 precondition_required` (هست؛ فقط در OpenAPI و تست ثبت شود). `PATCH /connections/{id}` هم `If-Match` بخواهد.

## ۲. بهتر است (اگر ارزان بود همین‌جا؛ وگرنه فهرست در گزارش)
- `HQ-SYS` و `HQ-ADV` از کد ردیف `kind: holding` ساخته شوند؛ دپارتمان `HR` در `internal.rego` از داده بیاید، نه ثابت.
- CSRF: `Origin` غیر ASCII به جای 500، `403 csrf_rejected`.
- step-up برای `PUT /assignments` و `PUT /budgets` به hash بدنه‌ی درخواست بسته شود، نه `*`.
- نشست: ورود، نشست قبلی را باطل و step-up نشست را بچرخاند. خطای sign-count ← ردیف audit، اعلان 🔴 و علامت روی آن passkey.
- توکن ایجنت: `jti` یک‌بار مصرف در پنجره‌ی عمر توکن؛ `run` با اجرای واقعی بررسی شود.
- ورود: `allowCredentials` خالی (passkey قابل‌کشف) تا شناسه‌ی passkeyها به کاربر ناشناس داده نشود.
- آپلود: سقف حجم هنگام **خواندن جریان**، نه بعد از خواندن کامل؛ بررسی قفل شرکت پیش از نوشتن فایل.
- `/internal` درخواست دارای `X-Forwarded-For` را رد کند.
- `hq.sh`: regex دامنه حداقل یک حرف در آخرین بخش بخواهد (IP و `*.localhost` دامنه نیستند).
- Caddy: HSTS برای کل سایت؛ `read_timeout 0` فقط برای `/api/v1/stream`.
- `opa`: `user:` صریح و tmpfs؛ `compose-rules.sh` هم user، `read_only` و `cap_drop` را بررسی کند.
- `fa_normalize`: أ/إ/آ←ا، ة←ه، ؤ←و، و نیم‌فاصله به فاصله (نه حذف)؛ escape کردن `%` و `_` در LIKE.
- کدهای انسانی (`W-`، `D-`، `O-`، کد کارمند) فقط از sequence؛ GRANT UPDATE روی `core.counters` برداشته شود. `verify_chain` و `lock_state`: `REVOKE EXECUTE FROM PUBLIC`.
- `tokens_used` در برابر بودجه هم بررسی شود؛ شاهد خالی (`[{}]`) برای `done` کافی نباشد.
- کلید توقف یک شرکت اثر تصمیم‌ها و اولین اجرای کار دائمی همان شرکت را هم نگه دارد. ردیف audit برای اجرای کار دائمی و انقضای پاکت.
- Android: فهرست مجاز origin برای `android:apk-key-hash:` از تنظیمات (فعلاً خالی)؛ برای اپ اندروید لازم میشود.
- حافظه: سقف Valkey با `appendonly yes` برای fork بازنویسی AOF کم است؛ یا سقف را درست کن یا RDB. کش workflow در `worker` را اندازه بگیر و متناسب کن. **جمع سقف‌ها بالا نرود.**
- Schemathesis: نمونه‌ی بیشتر برای هر عملیات در CI شبانه (نه در هر push).

## ۳. کیفیت
- `make check` و CI سبز؛ پوشش منطق دامنه ≥ ۸۵٪ بماند؛ همه‌ی تست‌های پرامپت ۴ همچنان پاس.
- OpenAPI دوباره ساخته و commit شود.
- `docs/ops/CORE.md` و RUNBOOK برای هر تغییر رفتاری به‌روز شود.
- بعد از `make up`: همه healthy، **هیچ پورت عمومی تازه**، `free -h` و `docker stats --no-stream`.

## ۴. گزارش پایانی
commitهای کوچک روی `server/p04-1-hardening` و push. گزارش **حداکثر ۲۰ خط:**

```
PROMPT_04_1 REPORT
- Must 1.1-1.14: ok/fail each (one line, test name)
- Networks: services on hq-core; anything else still reaching Temporal
- Nice-to-have done: ... ; left for later: ...
- Price fix: sonnet-5-5 cache_read = ? (source, as_of)
- Coverage domain x% / total y% ; make check / CI
- RAM: sum of limits vs 80%; used/free
- Branch / last commit / pushed
- Contract notes: ...
- Decisions for owner: ...
- Problems: ...
```

**خط آخر:** «این گزارش را برای Claude سشن مشورت ببر.» بعد **متوقف شو.**
