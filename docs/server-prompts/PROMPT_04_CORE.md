# پرامپت ۴: هسته‌ی هلدینگ (سازمان، کار، کارتابل، پیام، اعلان، Audit و API)

> **برای مالک:** کل متن زیر خط را کپی کن و به Claude Code روی سرور هاب بده (یا بگو: «`git pull` کن و `docs/server-prompts/PROMPT_04_CORE.md` را اجرا کن»). این پرامپت **هیچ کاری از تو نمیخواهد**؛ اگر جایی تصمیم لازم شد، در گزارش میاید. گزارش کوتاه آخرش را برای Claude سشن مشورت بیاور.

---

تو **Claude Code روی سرور هاب «CoinePro HQ»** هستی. این مرحله **هسته‌ی هلدینگ** را میسازد: سازمان (شرکت، دپارتمان، کارمند)، کار و ارجاع، سه صندوق (کارتابل تصمیم، کارتابل خروجی، پیام‌ها)، دفتر مصوبات، اعلان و «خلوت»، Audit زنجیره‌ای، کلید توقف، خواندن خزانه‌ی توکن، استریم زنده، و **API داخلی که ایجنت‌ها در پرامپت ۵ از آن استفاده میکنند.** هیچ ایجنتی در این مرحله واقعاً کار نمیکند و هیچ UI ساخته نمیشود؛ تست‌ها با **ایجنت جعلی** انجام میشوند.

## ۰. قبل از شروع (اجباری)
1. در `/home/Hub/CoinePro-Hub` آخرین نسخه‌ی `claude/coinepro-hub-setup-hsvnw7` را pull کن و شاخه‌ی **`server/p04-core`** را از آن بساز.
2. **این‌ها را کامل بخوان و رعایت کن:**
   - `CLAUDE.md`
   - **`contracts/HQ_CORE_API_v1.md`** ← **مرجع این مرحله.** هر endpoint، فیلد، قاعده و کد خطا از همین سند است.
   - `docs/OPERATING_MODEL.md` (همه‌اش؛ به‌خصوص §۰، §۱.۱ تا §۱.۴، §۱.۷، §۱.۸، §۱.۹، §۱.۱۲، §۱.۱۶)
   - `docs/TECH_STACK.md`، `docs/ops/RUNBOOK.md`، `docs/ops/LLM_LAYER.md`، `docs/server-prompts/README.md`
3. **پوشه‌ی `contracts/` مال Claude سشن مشورت است و آن را تغییر نمیدهی.** اگر در قرارداد خطا، تناقض یا کمبودی دیدی، نزدیک‌ترین رفتار امن را پیاده کن و در گزارش زیر «Contract notes» بنویس.
4. **تسک‌بندی اجباری:** قبل از هر کاری **همه‌ی کارهای این پرامپت را در لیست تسک بشکن.** هر تسک یک تست قبولی دارد. بدون توقف یکی‌یکی جلو برو، کارهای مستقل را موازی کن، و لیست را به‌روز نگه دار.
5. **فقط در این موارد متوقف شو و بپرس:** تصمیمی که با مالک است، یا خطر غیرمنتظره. **این پرامپت هیچ کار دستی از مالک لازم ندارد.**

## ۱. معماری این مرحله
```
 Caddy (/api/* only when a domain is set) ──► api  (apps/api, FastAPI)  ◄── /internal/v1 ── (agent runtime, prompt 5; fake agent in tests)
                                               │  │  │
                       Postgres (core, org, work, cartable, msg, notify, auth, owner, audit, control)  + RLS FORCE
                                               │  ├──► OPA (policy: who may approve what, action classes, internal permissions)
                                               │  └──► NATS JetStream  HQ_CORE  (hq.core.<company>.<type>)  ──► SSE /api/v1/stream
                                     worker (same package, Temporal worker: decisions, recurring, escalation, digest, morning report, audit verify)
```
- **`api`** و **`worker`**: یک پکیج پایتون در `apps/api/` (Python 3.12، FastAPI، Pydantic v2، SQLAlchemy 2 async، Alembic)، با دو entrypoint. از `services/hq-common` (لاگ، heartbeat، OpenBao، توکن) دوباره استفاده کن.
- **`opa`**: ایمیج رسمی Open Policy Agent با نسخه‌ی ثابت، policyها در `infra/opa/policy/` و تست‌ها با `opa test`.
- **`api-migrate`**: سرویس یک‌باره‌ی Alembic، بعد از `llm-migrate`.
- **همه‌ی سرویس‌های جدید:** فقط روی شبکه‌ی `hq-internal`، **بدون پورت منتشرشده** (برای تست فقط `127.0.0.1`)، کاربر غیر root، rootfs فقط‌خواندنی، tmpfs، healthcheck، سقف حافظه در هر دو پروفایل. **هیچ سوکت Docker، SSH یا mount از ریپوهای دیگر.**
- **Caddy:** وقتی `HQ_SITE_ADDRESS` یک دامنه است (HTTPS)، `/api/*` را به `api` بفرست (SSE با `flush_interval -1`، هدرهای امنیتی، سقف حجم بدنه). **وقتی دامنه نیست، `/api` در لبه بسته میماند** (۴۰۴). `/internal` هرگز از Caddy رد نمیشود.

## ۲. داده‌ها (Postgres، دیتابیس `hq`)
- **Alembic مخصوص `apps/api`** با `version_table = alembic_version_api`. migrationهای `llm-router` دست نمیخورند؛ `core.companies` موجود را با `ALTER` کامل کن (`name_fa`، `name_en`، `color_index`، `template`، `version`) و اسم موجود را در `name_en` نگه دار.
- **schemaها و جدول‌ها** (طبق قرارداد): 
  - `core`: companies (کامل)، departments، employees، `employee_code_seq` (برای هر شرکت و دپارتمان، **فقط رو به جلو؛ کد هرگز دوباره داده نمیشود**)
  - `work`: work، work_events، escrows، schedules
  - `cartable`: decisions، deliverables، ratings (با تاریخچه)، resolutions (یک دنباله‌ی `M-0001` برای کل هلدینگ)
  - `msg`: threads، messages (شماره‌ی `<code>-<seq>` برای هر thread)
  - `notify`: notifications، settings، web_push_subscriptions، fcm_tokens، digest_queue
  - `auth`: passkeys، sessions (توکن **hash‌شده**)، step_ups، enrolment_tokens (hash‌شده، یک‌بار مصرف، ۱۵ دقیقه)
  - `owner`: presence، settings، interactions
  - `audit`: entries (زنجیره‌ی hash)
  - `control`: kill_switches، deploy_freezes
  - `files`: metadata فایل‌ها (محتوا روی volume محلی `hq-files` از راه یک interface ذخیره‌سازی که بعداً backend S3 میگیرد)
- **قواعدی که باید در خود دیتابیس اجرا شوند** (trigger یا constraint، نه فقط کد):
  1. `depth ≤ 2` در ارجاع کار.
  2. بودجه‌ی فرزند ≤ باقیمانده‌ی والد؛ جمع فرزندها ≤ والد.
  3. `done` فقط با حداقل یک خروجی یا شاهد.
  4. **append-only** برای `audit.entries`، `msg.messages`، `cartable.resolutions` و تاریخچه‌ی امتیاز: UPDATE و DELETE برای همه رد میشود.
  5. یکتایی و ثابت ماندن همه‌ی کدهای انسانی (`TY-TECH-01`، `D-…`، `O-…`، `W-…`، `M-…`، `A-0142`).
- **RLS با FORCE روی همه‌ی جدول‌های دارای `company_id`**، با همان قرارداد `app.company_ids` (uuid[] با `SET LOCAL`) که `llm.*` دارد. نقش‌های دیتابیس: `hq_api` و `hq_worker` با کمترین دسترسی لازم؛ `audit.entries` فقط INSERT و SELECT. مالک همه‌ی شرکت‌ها را میبیند، ایجنت فقط شرکت خودش را.
- **جستجوی فارسی:** تابع نرمال‌سازی (ی/ي، ک/ك، نیم‌فاصله، اعراب) + FTS با پیکربندی `simple` + `pg_trgm`.
- **seed از فایل** (`apps/api/seed/`، نه در کد): قالب‌های `standard` (۸ دپارتمان) و `holding` (`OVS`، `AIOPS`، مشاور کل `HQ-ADV`)؛ برای `HQ`، `TY`، `FX`، `PC` دپارتمان‌ها و **فقط جایگاه‌های رهبری** (مدیرعامل هر شرکت و ۸ مدیر، با `activity = sleeping`). **هیچ کارمند شماره‌دار seed نمیشود**؛ کارمند فقط از راه تصمیم `hire` ساخته میشود. seed idempotent است و ردیف‌های ویرایش‌شده را بازنویسی نمیکند.

## ۳. API عمومی (`/api/v1`)
- **همه‌ی endpointهای قرارداد** (§۲ تا §۱۱): هویت، شرکت‌ها و دپارتمان‌ها، کارمندها و چارت، کار و پلنر، تصمیم‌ها، خروجی‌ها و امتیاز، thread و پیام و جستجو، مصوبات، خلاصه‌ی صندوق‌ها، اعلان و تنظیمات و push، حضور مالک و «در نبودت چه گذشت»، Audit، کنترل، خزانه‌ی توکن، `/health` و `/meta`.
- **قواعد مشترک قرارداد** همه پیاده شوند: problem+json با `code` و `message_fa`، cursor pagination، `If-Match`/`version`، `Idempotency-Key`، CSRF برای وب، rate limit، و **step-up** روی همه‌ی موارد 🔏.
- **هر تغییر = یک ردیف Audit در همان تراکنش.** **هر اقدام مالک = یک ردیف `owner.interactions`.**
- **هیچ endpoint حذف داده‌ی کسب‌وکار وجود ندارد.**
- **OpenAPI 3.1** از خود FastAPI ساخته و در `apps/api/openapi/hq-api.v1.json` commit میشود. CI اگر فایل با کد نخواند رد میکند. توضیح و مثال برای هر endpoint، و `operationId` پایدار (برای ساخت کلاینت وب و اندروید).

## ۴. هویت (Passkey)
- کتابخانه‌ی متن‌باز **`webauthn` (py_webauthn)**. user verification **اجباری**. نشست‌ها opaque و hash‌شده، طبق قرارداد §۲.
- **`make owner-enroll`:** یک لینک ثبت یک‌بار مصرف (۱۵ دقیقه) میسازد و **فقط در ترمینال همان کسی که اجرایش کرده** نشان میدهد؛ در لاگ، فایل یا خروجی تو هرگز نمیاید. **تو آن را اجرا نکن**؛ مالک بعداً، وقتی دامنه و اپ آماده شد، خودش اجرا میکند. همین دستور مسیر بازیابی هم هست.
- **بدون دامنه و HTTPS، ورود خاموش است** (`503 origin_not_configured`)؛ این خطا نیست، فقط در گزارش بیاید.
- تست‌ها با یک **authenticator نرم‌افزاری** (کلید ES256 ساخته‌شده در تست) کل چرخه‌ی ثبت، ورود و step-up را میآزمایند، به‌علاوه‌ی حالت‌های رد: challenge کهنه، origin اشتباه، بدون UV، replay و step-up با action دیگر.

## ۵. سیاست‌ها (OPA)
- `decisions.rego`: چه کسی چه نوع تصمیمی را تأیید میکند (جدول قرارداد §۵.۱؛ مثلاً `deploy` فقط مالک، `recurring_approval` مالک یا مدیرعامل همان شرکت در سقف سهمیه، پست تقویم محتوای تأییدشده با مدیرعامل).
- `actions.rego`: کلاس‌های **A0 تا A4**؛ **A4 برای هر principal غیر مالک همیشه deny** (ترید، برداشت و انتقال پول، حذف داده و backup، تغییر دسترسی‌های اصلی).
- `internal.rego`: هر ایجنت فقط در شرکت، دپارتمان و نقش خودش؛ ارجاع بین شرکت‌ها فقط مدیرعامل به مدیرعامل؛ کلید توقف فقط برای شرکت خود.
- **`opa test` با پوشش کامل قواعد** در `make check` و CI. API در صورت در دسترس نبودن OPA **fail-closed** است.

## ۶. گردش‌کارها (Temporal، task queue `hq-core`)
1. **DecisionLifecycle:** انقضا، یادآوری دسته‌ای، و **اثر تأیید**: `hire` ← ساختن کارمند با کد بعدی و تخصیص مدل در `llm.assignments` (سطح role)؛ `recurring_approval` ← فعال شدن زمان‌بندی؛ `dismissal` ← روند برکناری و کار انتقال دانش؛ بقیه ← ثبت مصوبه، اعلان به پیشنهاددهنده و کار پیگیری در صورت نیاز.
2. **RecurringWork:** Temporal Schedule برای هر کار دائمی؛ هر اجرا یک work با بودجه‌ی پاکت اختیار؛ بعد از انقضای پاکت متوقف میشود.
3. **OverdueEscalation:** هر ۵ دقیقه؛ کار عقب‌افتاده یک پله بالا میرود (مدیر ← مدیرعامل ← مالک) با اعلان.
4. **NotificationDigest:** پنجره‌ی دسته‌ای 🟡، **خلوت = فقط 🔴**، سهمیه‌ی روزانه‌ی توجه هر مدیرعامل، و ارسال به کانال‌ها.
5. **MorningReport:** ساعت `owner.settings.morning_report_at` در منطقه‌ی زمانی مالک؛ **نسخه‌ی قاعده‌محور و بدون LLM** (اعداد واقعی همه‌ی صندوق‌ها و شرکت‌ها) به‌صورت یک Deliverable و اعلان 🔵. نسخه‌ی نوشته‌شده با مدل در پرامپت ۵.
6. **AuditVerify:** هر شب زنجیره‌ی hash را بررسی میکند؛ اگر شکسته باشد اعلان 🔴.
7. **ScoreJob:** هر شب امتیاز کارمندها با فرمول §۱.۱۶.
- **کلید توقف** هلدینگ همه‌ی گردش‌کارهای ایجنتی را pause میکند (نه گزارش و Audit را).

## ۷. اعلان‌ها و کانال‌ها
- **در اپ:** از راه استریم.
- **Web Push (VAPID):** کلیدها را خودت بساز و در OpenBao بگذار (کتابخانه‌ی متن‌باز `pywebpush`).
- **FCM و ربات تلگرام:** آداپتورها ساخته و تست میشوند، ولی **تا وقتی credential ندارند خاموش‌اند** (`channel_not_configured`). **تلگرام فقط پشتیبان است و هیچ تأییدی از آن ممکن نیست.**
- رفتار پنج سطح، تنظیم برای هر شرکت و هر سطح، و سؤال‌های یادگیری با جواب یک‌لمسی، طبق قرارداد §۶.

## ۸. استریم زنده
- stream جدید JetStream به اسم `HQ_CORE` (retention ۳۰ روز)، subjectها `hq.core.<company>.<type>`.
- `GET /api/v1/stream` (SSE) با فیلتر topic و شرکت، بررسی tenant، `Last-Event-ID` برای ادامه بدون از دست رفتن، heartbeat هر ۱۵ ثانیه. رویدادهای `hq.llm.*` موجود هم (فقط متادیتا) از همین مسیر میایند.
- **فقط متادیتا؛ هیچ متن پیام یا secret روی NATS نمیرود.**

## ۹. باقیمانده‌ی پرامپت ۳ (تصمیم‌های مالک)
1. **منبع هزینه:** `equiv_cost_usd` و `cost_usd` از **جدول قیمت خود ما** در `llm.connections` محاسبه شوند. عدد SDK در `meta.sdk_cost_usd` بماند. متریک نسبت این دو، و هشدار 🔵 اگر یک ساعت پشت هم بیشتر از ۲ برابر شد.
2. **قیمت مدل‌ها:** قیمت Haiku 5.5، Sonnet 5.5 و Opus 5.5 را **فقط از صفحه‌ی رسمی قیمت Anthropic** بردار و با `source_url` و `as_of` ثبت کن. **اگر به منبع رسمی دسترسی نداشتی، عدد نساز**؛ خالی بگذار و در گزارش بگو.
3. **SDK و CLI:** اگر نسخه‌ی پایدار جدیدتری هست که Haiku 5.5 را میشناسد، pin را به‌روز کن (فقط اگر همه‌ی تست‌ها پاس شد).
4. **تصمیم قطعی مالک:** **root token در OpenBao و توکن Claude دست نمیخورند** (نه باطل، نه حذف، نه چرخش). این موضوع را دیگر مطرح نکن.

## ۱۰. کیفیت، امنیت و تست
- **ابزارها:** ruff، mypy strict، pytest روی Postgres، NATS و Temporal واقعی (همان `test-env.sh`)، `opa test`، **Schemathesis** روی OpenAPI (بدون هیچ ۵xx)، `pip-audit`، hadolint، gitleaks. همه در `make check` و CI.
- **پوشش تست:** حداقل **۸۵٪** برای منطق دامنه (ارجاع، بودجه، تصمیم‌ها، اعلان و خلوت، کدها، هویت) و ۸۰٪ کل.
- **تست‌های اجباری:**
  - **RLS بین شرکت‌ها** برای همه‌ی جدول‌های جدید (session با مجوز `TY` هیچ ردیفی از `FX` نمیبیند)
  - هیچ endpoint بی‌احراز (به‌جز `/health` و شروع ورود)
  - CSRF، step-up، idempotency، `If-Match`
  - عمق ارجاع ۳ رد میشود؛ بودجه‌ی فرزند بیشتر از والد رد میشود؛ `done` بی‌شاهد رد میشود
  - UPDATE و DELETE روی جدول‌های append-only رد میشود؛ شکستن عمدی زنجیره‌ی Audit پیدا میشود
  - کد کارمند بعد از برکناری دوباره داده نمیشود
  - خلوت: فقط 🔴 ارسال میشود؛ «در نبودت چه گذشت» درست میشمارد
  - سهمیه‌ی توجه مدیرعامل
  - A4 برای ایجنت همیشه رد میشود؛ OPA خاموش ← fail-closed
  - **نبود متن پیام، prompt یا secret در لاگ‌ها، Audit و NATS**
- **بودجه‌ی حافظه:** سقف `api`، `worker` و `opa` در هر دو پروفایل. **جمع کل سقف‌ها حداکثر ۸۰٪ RAM.** اگر بیشتر شد، **متوقف نشو، فقط عددش را گزارش بده.**
- **مستندات:** `apps/api/README.md`، `docs/ops/CORE.md` (معماری، جدول‌ها، گردش‌کارها، policyها، نحوه‌ی افزودن شرکت با یک رکورد)، به‌روزرسانی RUNBOOK.

## ۱۱. تست قبولی نهایی (سناریوی کامل با ایجنت جعلی)
1. `make up`: همه healthy. `ss -tlnp`: **هیچ پورت عمومی جدیدی.**
2. **«خط کامل اول»:** ایجنت جعلی `TY-GROWTH-MGR` از `/internal/v1/decisions` یک **پیشنهاد استخدام** میدهد ← تصمیم `D-…` در کارتابل و اعلان 🟡 در استریم ← مالک (authenticator نرم‌افزاری) با step-up تأیید میکند ← کارمند **`TY-GROWTH-01`** ساخته میشود و تخصیص مدلش ثبت میشود ← مصوبه‌ی **`M-0001`** ← پیام به پیشنهاددهنده ← **`/audit/verify` سالم.**
3. مالک یک کار به `TY` میدهد ← مدیرعامل جعلی به مدیر ← مدیر به کارمند (عمق ۲) ← تلاش برای عمق ۳ رد میشود ← کارمند جعلی خروجی تحویل میدهد ← مالک امتیاز ۸ میدهد ← امتیاز کارمند به‌روز میشود.
4. یک کار دائمی که ایجنت پیشنهاد داده با **تأیید مدیرعامل همان شرکت** فعال میشود و اولین اجرایش ساخته میشود.
5. خلوت روشن ← یک 🟡 و یک 🔴 ← فقط 🔴 ارسال میشود ← خلوت خاموش ← «در نبودت چه گذشت» درست است.
6. کلید توقف `TY` ← اقدام نوشتنی ایجنت `TY` با `423` رد میشود ← آزاد کردن با step-up.
7. `make check` و CI سبز. `free -h` و `docker stats --no-stream`.

## ۱۲. گزارش پایانی
commitهای کوچک روی `server/p04-core` و push. گزارش **حداکثر ۲۰ خط:**

```
PROMPT_04 REPORT
- Services: api / worker / opa / api-migrate healthy? public ports unchanged?
- Schema + RLS: tables, cross-company test ok/fail; append-only + audit chain ok/fail
- Identity: passkey + step-up tests ok/fail; login state (domain set? yes/no)
- Acceptance 1-6: ok/fail each (refs: D-..., TY-GROWTH-01, M-0001)
- Workflows: decision / recurring / escalation / digest / morning report / audit verify / score
- Channels: in-app / web push / fcm / telegram (on/off)
- Cost source + model prices (source, as_of) ; SDK/CLI version
- Coverage domain x% / total y% ; Schemathesis ; make check / CI
- RAM: sum of limits vs 80%; used/free
- Branch / last commit / pushed
- Contract notes: ...
- Decisions for owner: ...
- Problems: ...
```

**خط آخر:** «این گزارش را برای Claude سشن مشورت ببر.» بعد **متوقف شو.**
