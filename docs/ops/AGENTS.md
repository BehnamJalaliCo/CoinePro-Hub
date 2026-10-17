# CoinePro HQ — ایجنت‌ها سر کار (پرامپت ۵)

> سند عملیاتی موتور اجرای ایجنت‌ها، Tool Gateway، پایش سایت‌ها و کنترل سهمیه.
> منشور نقش‌ها (`agents/roles/*.md`) و کاتالوگ ابزارها (`agents/tools.md`) مال Claude سشن مشورت‌اند؛ این‌جا فقط خوانده میشوند.

## ۱. معماری اجرا

```
رویداد (کار تازه، تحویل فرزند، پیام مالک، زمان‌بندی، هشدار)
  └─ تریگر دیتابیس ← agents.queue_run() ← ردیف queued در agents.runs ← NOTIFY hq_runs
       └─ Dispatcher (در worker) ← Temporal: AgentRun (id = agent-run-<run>)
            ├─ run_claim    قفل، منشور، سقف روزانه، بودجه‌ی کار ← running (یا refused)
            ├─ run_execute  قدم‌ها: llm-router /v1/run (json_schema) ← اقدام‌ها ← Tool Gateway ← /internal/v1
            └─ run_finalize done / failed / refused + audit + رویداد run.finished
```

- **خواب واقعی:** هیچ پروسه یا workflow همیشه‌روشنی برای نقش‌ها نیست. نقش تا وقتی رویدادی برایش ثبت نشود هیچ هزینه‌ای ندارد.
- **چه چیزی اجرا را بیدار میکند** (تریگرهای `0008_agents`):
  - کار تازه یا عوض شدن گیرنده‌ی کار (نه قالب کارهای دائمی). `trigger` برابر `work`، `schedule` یا `alert` است.
  - تحویل یک کار فرزند: کارمند والد بیدار میشود (`child_delivered`).
  - پیام مالک در thread یک ایجنت (`advisor`، `ceo`، `manager`، `employee`). مشاور با P2.
- **یک اجرا در هر لحظه:** برای هر کارمند فقط یک اجرای `running` و برای هر (کارمند، کار، thread) فقط یک `queued` هست (ایندکس یکتا). رویداد تکراری روی همان ردیف queued مینشیند.
- **ماشین حالت** (`agents.runs`، با trigger): `queued → running → done | failed | refused`. حالت پایانی عوض نمیشود.
- **قدم:** هر قدم یک فراخوانی llm-router با خروجی JSON است: `{summary_fa, actions: [{tool, args}], done}`. هیچ فیلد فکر یا استدلال نیست و هیچ «chain of thought» ذخیره نمیشود.
- **چه چیزی ذخیره میشود** (`agents.steps`، append-only): خلاصه‌ی فارسی، اقدام‌ها (ابزار، کلاس، نتیجه، کد، ref) و مصرف توکن. **هیچ prompt، خروجی خام مدل یا payload ابزار** در دیتابیس، لاگ، audit یا NATS نیست. گفت‌وگوی هر اجرا فقط در حافظه‌ی همان activity است.

### سقف‌ها
| سقف | از کجا |
|---|---|
| قدم در هر اجرا | `limits.steps_per_run` منشور |
| توکن در هر اجرا | کمترینِ `limits.tokens_per_run` منشور، بودجه‌ی باقی‌مانده‌ی کار و `token_cap_per_run` امانت (escrow) |
| اقدام در هر قدم / ابزار در هر اجرا | `AGENT_ACTIONS_PER_STEP` (۸) و `AGENT_TOOL_CALLS_PER_RUN` (۴۸)، در SQL اعمال میشوند |
| زمان | `AGENT_MAX_RUN_S` (۳۰۰۰)، هر قدم `AGENT_STEP_TIMEOUT_S` (۳۰۰) |
| مصرف روزانه‌ی همه‌ی اجراها | `AGENT_DAILY_TOKEN_CAP` (پیش‌فرض ۲٬۰۰۰٬۰۰۰ در روز UTC). بعد از آن اجراها `refused` با `daily_cap` |
| کار حادثه | `AGENT_INCIDENT_BUDGET_TOKENS` (۶۰٬۰۰۰)، بودجه‌ی کاری که پایش سایت میسازد |

- هر سقفی که زودتر برسد، اجرا با یک `deliver` بخشی (`partial`) یا `failed` تمام میشود.
- دو خروجی نامعتبر پشت هم ← `failed` با `invalid_output`.
- **کلید توقف و قفل:** پیش از هر قدم بررسی میشود و API هم پیش از هر اقدام نوشتنی بررسی میکند. قفل ← `refused` و audit. اجرای refused بعد از آزاد شدن قفل دوباره صف میشود (`requeue_runs` در Maintenance).

### توکن ایجنت (`hqa1`)
- در خود activity ساخته میشود (هرگز در تاریخچه‌ی Temporal نیست). به همان کارمند و همان `run` بسته است. عمرش برابر اجرای واقعی است و حداکثر ۱ ساعت.
- **رجیستری:** API فقط توکنی را میپذیرد که `run` آن `running` است، مال همان کارمند است و `token_expires_at` آن نگذشته. بعد از پایان اجرا، همان توکن ۴۰۱ میگیرد.

### نقش ← منشور
- هر کارمند با `core.employees.role` به `agents/roles/<role>.md` وصل است. فهرست: `GET /api/v1/roles`.
- **جایگاه‌های رهبری از قالب** (`seed/templates/*.yaml`، فیلد `head_role`):
  - مدیرعامل‌ها ← `ceo`، مدیر `TECH` ← `cto`، بقیه‌ی مدیرها ← `manager`
  - هلدینگ: مدیر `OVS` ← `inspector`، مدیر `AIOPS` ← `aiops_head`، `HQ-ADV` ← `advisor`
- **کارمند استخدام‌شده:** نقشش از `payload.role` تصمیم `hire` میاید. باید منشوری از نوع `employee` باشد که با `scope` شرکت جور است (شرکت ← `company`، هلدینگ ← `holding`). وگرنه پیشنهاد و تأیید هر دو `422 validation_failed` میگیرند.
- **مدل و effort:** از `llm.assignments` (ارث‌بری کارمند ← دپارتمان ← شرکت)؛ اگر نبود، پیش‌فرض منشور.
- نسخه‌ی منشور در ledger (`meta.charter = role@version`) و در `agents.runs.charter_version` ثبت میشود.

### افزودن نقش
**یک فایل منشور** در `agents/roles/<role>.md` (کار Claude سشن مشورت). frontmatter آن `role`، `kind`، `scope`، `model`، `effort`، `priority`، `tools` و `limits` دارد. api و worker منشورها را موقع بالا آمدن میخوانند، پس بعد از merge فقط `make up` لازم است. هیچ کدی عوض نمیشود. مشکل‌های منشور (ابزار ناشناخته، ابزار A3/A4، frontmatter خراب) در لاگ api با پیام `charter problem` میایند و آن ابزار یا منشور کنار گذاشته میشود.

## ۲. Tool Gateway (`services/gateway`)

```
worker ──(توکن سرویس)──► gateway ──(توکن hqa1 همان اجرا)──► api /internal/v1 ──► RLS + OPA + audit
```

| مرحله | کار |
|---|---|
| رزرو | `POST /internal/v1/runs/self/reserve`: اجرا `running` است، سقف ابزار در هر قدم و هر اجرا (بیشتر ← `429 rate_limited`) |
| کاتالوگ | ابزار ناشناخته ← `unknown_tool`. هیچ ابزار A3 یا A4 وجود ندارد |
| منشور | ابزار بیرون از `tools` منشور ← `tool_not_in_charter` |
| سیاست | OPA ‏`hq.actions`: کلاس بر اساس نقش، A4 هرگز، شرکت قفل ← نوشتن رد |
| اعتبارسنجی | Pydantic هر ابزار؛ خطا فقط نام فیلد را میگوید، نه مقدار را |
| انجام | API داخلی با توکن همان اجرا، timeout هر ابزار ۲۵ ثانیه |
| redaction | کلید و توکن، ایمیل، تلفن (رقم لاتین و فارسی)، کارت، IBAN و فیلدهای شخصی؛ نتیجه حداکثر ۱۶٬۰۰۰ کاراکتر |
| audit | `POST /internal/v1/runs/self/tool-calls`: یک ردیف `tool.call` برای هر فراخوانی (ابزار، کلاس، نتیجه، ref)، بدون ورودی و خروجی |

- **شبکه:** فقط `hq-agent` (internal؛ پرامپت ۵.۱ §۲.۹)، با worker، api و OPA. بدون پورت منتشرشده. به Temporal، Postgres، NATS، Valkey، OpenBao و اینترنت نمیرسد.
- **احراز:** فقط worker. gateway فقط SHA-256 توکن worker را دارد (`/home/Hub/.secrets/services/gateway/worker-token.sha256`، ۶۰۰، uid 10001). خود توکن در OpenBao است (`kv/hq-agents/runtime`).
- **`github.read`:** ساخته و تست شده، ولی تا مالک توکن فقط‌خواندنی ندهد `channel_not_configured` برمیگرداند.

### افزودن ابزار
1. Claude سشن مشورت ابزار را در `agents/tools.md` (نام، کلاس، ورودی) و در `tools` منشورها مینویسد.
2. Claude سرور: مدل ورودی و handler در `services/gateway/src/hq_gateway/tools.py` (جدول `TOOLS`). اگر endpoint تازه‌ای لازم است، در `apps/api/src/hq_api/routes/agent_tools.py`، به‌علاوه‌ی op در `infra/opa/policy/internal.rego` و `OP_CLASS`.
3. تست در `services/gateway/tests` و `apps/api/tests`. پوشش gateway ≥ ۸۵٪.

## ۳. مشاور کل (`HQ-ADV`) و گفت‌وگو

- پیام مالک در thread ‏`A` ← اجرای مشاور با P2 ← قدم‌های پژوهش (فقط ابزارهای خواندنی، با دید کل هلدینگ) ← قدم پاسخ با `/v1/run/stream` ← `reply.delta` در `GET /api/v1/threads/A/live` (SSE فقط مالک) ← پیام نهایی با `citations`.
- **citation:** مدل فهرست را در `<citations>[...]</citations>` آخر پاسخ میدهد. این بخش هرگز stream نمیشود. هر ارجاعی که در دیتابیس نیست حذف و در `meta.citations_dropped` شمرده میشود.
- deltaها فقط در حافظه‌ی api میمانند (`LiveHub`). روی NATS فقط متادیتای `run.*` میرود.
- **مشاور هیچ ابزار نوشتنی ندارد** جز `message.thread` در thread خودش (`A`) و `memory.write`.
- «با مشاور بررسی کن» (`POST /decisions/{ref}/review-with-advisor`): همین مسیر، با کارت تصمیم به‌عنوان زمینه.
- پیام مالک در thread یک مدیرعامل، مدیر یا کارمند ← اجرای همان نقش. پاسخ ایجنت با `message.thread`.
- **گزارش صبحگاهی:** اول نسخه‌ی قاعده‌محور (Deliverable ‏`HQ-SYS`). بعد یک فراخوانی Sonnet 5.5 (effort `medium`، P3) آن را به متن فارسی خوش‌خوان تبدیل میکند. خروجی فقط وقتی نگه داشته میشود که **همه‌ی عددهایش در نسخه‌ی قاعده‌محور باشد** (`report.same_numbers`). نتیجه Deliverable دوم «(متن خوش‌خوان)» است و اعلان به آن لینک میدهد. خاموش کردن: `HQ_MORNING_REPORT_LLM=off`.
- **گزارش روزانه‌ی مدیرعامل‌ها:** فقط زیرساخت. Schedule ‏`hq-ceo-daily` ساخته میشود ولی تا `HQ_CEO_DAILY_REPORTS=on` نشود pause است.

## ۴. حافظه و انتقال دانش
- `core.employee_memory` (append-only، RLS): یادداشت، برچسب، run، زمان، و `source_employee_id` برای یادداشت‌های منتقل‌شده.
- ابزارها: `memory.read` (آخرین یادداشت‌های خود کارمند، با سقف حجم) و `memory.write`.
- **برکناری:** حافظه به گیرنده‌ی کارها کپی میشود (برچسب `transfer`) و کار «Knowledge transfer from …» تعداد یادداشت‌ها را میگوید.

## ۵. پایش سایت‌ها (بدون مدل)
- **داده:** `ops.sites` (از `seed/sites.yaml`؛ مالک با `PUT /api/v1/ops/sites` 🔏 عوض میکند؛ URLی که از فهرست بیرون برود خاموش میشود، حذف نمیشود)، `ops.checks` (پارتیشن روزانه، ۳۰ روز)، `ops.incidents` (`I-0001`، یک حادثه‌ی باز برای هر سایت).
- **چکر:** Schedule ‏`hq-site-checks` هر ۵ دقیقه. فقط GET یا HEAD عمومی، timeout ۱۰ ثانیه، User-Agent ‏`CoinePro-HQ-Monitor/1`. redirect فقط روی همان host دنبال میشود. redirect به دامنه‌ی دیگر با همان کد 3xx گزارش میشود. روزهای باقی‌مانده‌ی TLS هم ثبت میشود (کش ۱ ساعته).
- **۳ شکست پشت هم** ← حادثه + یک کار (`kind=event`، با شاهد، بودجه‌ی `AGENT_INCIDENT_BUDGET_TOKENS`) برای پاسخ‌دهنده:
  - شرکت: SRE (اگر استخدام شده)، وگرنه CTO
  - هلدینگ: SRE سکوی هاب (اگر استخدام شده)، وگرنه مدیر `AIOPS`
- `sev1` وقتی همه‌ی سایت‌های شرکت خراب‌اند (کار P0)، وگرنه `sev2` (P3).
- **سایت سالم هیچ مدلی را بیدار نمیکند.** حادثه‌ی باز کار تازه نمیسازد. برگشت سایت ← حادثه بسته میشود.
- **سایتی که خاموش شود** (مالک با `PUT /ops/sites`، یا قناری با seed) دیگر پایش نمیشود. پس دور بعدی، حادثه‌ی بازش را با دلیل «monitoring switched off» میبندد (audit ‏`incident.close` و رویداد کار).
- **سلامت هاب** (`ops.hub_health`، ابزار `health.hub`): از Prometheus (سرویس‌های بالا، ری‌استارت ۲۴ ساعت، دیسک، حافظه)، فایل‌های وضعیت backup و restore-test (`/home/Hub/backups/status/*.json`)، گواهی و سهمیه.
- **قناری:** `https://hq.coinepro.com/__canary` (Caddy عمداً ۵۰۳ میدهد). در `sites.yaml` با `canary: true`. خط کامل را ثابت میکند و بعد با `enabled: false` خاموش میشود. برای آزمایش دوباره: `enabled: true` و `make up`.

## ۶. کنترل سهمیه (Quota Controller، در llm-router)
- **منبع وضعیت** (به ترتیب):
  1. رویداد rate-limit خود SDK ‏(`RateLimitEvent`، از claude-runtime)
  2. خطاهای سهمیه
  3. شمارش ledger در پنجره‌ی ۵ ساعته و ۷ روزه (`LLM_QUOTA_WARN_TOKENS_5H`، `LLM_QUOTA_LIMIT_TOKENS_5H`، `_7D`؛ صفر = خاموش)
- **ثبت:** `llm.quota_status` (یک ردیف برای هر اتصال). بعد از `resets_at` خودکار `ok` میشود.
- **اثر:** `warning` ← P4 متوقف؛ `limited` ← فقط P0 تا P2.
- **خبر:** هر تغییر وضعیت یک پیام `hq.alerts.quota` میفرستد. worker آن را به `budget.alert` (kind ‏`quota`) و یک اعلان 🔵 تبدیل میکند (یک بار برای هر تغییر).
- **دیدن:** `GET /api/v1/treasury/quota`.

## ۷. مدل جعلی و تست
- llm-router با `LLM_FAKE_BACKEND=1` یک backend ‏`fake` دارد که پاسخ‌های از پیش نوشته را برمیگرداند (صف برای هر actor، یا `script`). CI هیچ فراخوانی واقعی نمیکند.
- تست‌های api کل خط را در یک پروسه اجرا میکنند (`tests/agents_env.py`): router، gateway و api با ASGI، و Temporal و Postgres واقعی.
- پوشش ≥ ۸۵٪ برای runner، gateway، redaction، چکر سایت و quota controller (`scripts/quality/python.sh`).

## ۸. آزمودن prompt یک منشور با مدل واقعی
`make prompt-check role=advisor` (یا هر نقش دیگر): یک فراخوانی واقعی از راه llm-router با فراخواننده‌ی `hq-ops`، با system prompt منشور، پروتکل و یک سؤال آزمایشی. اعتبار JSON قدم با schema سنجیده میشود و برای مشاور، مرحله‌ی پاسخ و citationها هم.
- **هیچ چیزی ذخیره نمیشود** جز ردیف ledger (`meta.purpose = prompt_check`): نه اجرا، نه پیام در thread ‏`A`، نه نشست.
- فقط متادیتا چاپ میشود (اعتبار، ابزارها، توکن‌ها)، نه prompt و نه متن مدل.
- بعد از هر تغییر منشور مفید است. هزینه دارد: Opus 5.5 برای مشاور.

## ۹. عیب‌یابی
| نشانه | کار |
|---|---|
| اجرایی شروع نمیشود | `GET /api/v1/runs?state=queued`؛ لاگ `make logs s=worker` (Dispatcher)؛ Temporal UI، workflow ‏`agent-run-<id>` |
| `refused` با `runtime_not_configured` | `kv/hq-agents/runtime` در OpenBao نیست: `make llm-provision` |
| `refused` با `daily_cap` | مصرف امروز به `AGENT_DAILY_TOKEN_CAP` رسیده؛ فردا (UTC) خودکار باز میشود |
| همه‌ی اقدام‌ها `policy_denied` | قفل یا کلید توقف (`GET /api/v1/control/state`) |
| gateway unhealthy | `make logs s=gateway`؛ فایل hash توکن worker (`make bootstrap` یک بار، بعد `make up`) |
| حادثه‌ای باز نمیشود | `ops.checks` آخرین نتیجه‌ها؛ `enabled` سایت؛ Schedule ‏`hq-site-checks` در Temporal UI |
