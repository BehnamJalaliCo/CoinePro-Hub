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
| قدم در هر اجرا | `limits.steps_per_run` منشور؛ پاسخ استریم‌شده‌ی مشاور هم یک قدم است و داخل همین سقف شمرده میشود |
| توکن در هر اجرا | کمترینِ `limits.tokens_per_run` منشور، بودجه‌ی باقی‌مانده‌ی کار و `token_cap_per_run` امانت (escrow). **سخت** (۵.۱): قدم بعدی فقط وقتی شروع میشود که prompt آن و خروجی‌اش در باقیمانده جا شوند |
| خروجی هر قدم | `min(limits.tokens_per_step, باقیمانده منهای prompt)` به router میرود (`max_output_tokens`، حداکثر `LLM_MAX_OUTPUT_TOKENS` = ۳۲٬۰۰۰). CLI با `CLAUDE_CODE_MAX_OUTPUT_TOKENS` همان‌جا میایستد |
| اقدام در هر قدم / ابزار در هر اجرا | `AGENT_ACTIONS_PER_STEP` (۸) و `AGENT_TOOL_CALLS_PER_RUN` (۴۸)، در SQL اعمال میشوند؛ بیشتر ← `429 rate_limited` با `Retry-After` |
| زمان | `AGENT_MAX_RUN_S` (۳۰۰۰)، هر قدم `AGENT_STEP_TIMEOUT_S` (۳۰۰) |
| مصرف روزانه‌ی همه‌ی اجراها | `AGENT_DAILY_TOKEN_CAP` (روی هاب `600000`، تصمیم مالک؛ پیش‌فرض کد ۲٬۰۰۰٬۰۰۰ در روز UTC؛ `0` یعنی بی‌سقف). ورودی + خروجی + cache. در `claim` و **پیش از هر فراخوانی مدل** بررسی میشود ← `refused` / `failed` با `daily_cap` |
| کار حادثه | `AGENT_INCIDENT_BUDGET_TOKENS` (۶۰٬۰۰۰)، بودجه‌ی کاری که پایش سایت میسازد |
| درخواست ایجنت به ایجنت (`work.request`) | کار ریشه‌ی تازه به کار درخواست‌کننده بسته است (پیش‌فرض: کار همان اجرا). بودجه‌اش باقیمانده‌ی آن کار است، حداکثر `AGENT_REQUEST_BUDGET_TOKENS` (۶۰٬۰۰۰)، و هرگز بیشتر از آنچه خواسته شده. زنجیره‌ی درخواست‌ها حداکثر `AGENT_REQUEST_CHAIN_MAX` (۲) حلقه است؛ بیشتر ← `409 delegation_depth_exceeded` |

- هر سقفی که زودتر برسد، اجرا با یک `deliver` بخشی (`partial`) یا `failed` تمام میشود.
- دو خروجی نامعتبر پشت هم ← `failed` با `invalid_output`.
- **مصرف فراخوانی ناموفق هم ثبت میشود.** فقط خطای `HQB01` (بودجه‌ی کار تمام) یعنی «توکن تمام»؛ هر خطای دیگر اجرا را `failed` میکند.
- **کلید توقف، قفل و توقف deploy:** پیش از هر قدم و پیش از پاسخ مشاور بررسی میشوند، و API هم پیش از هر اقدام نوشتنی بررسی میکند. هر کدام (کلید هلدینگ، کلید شرکت یا توقف deploy؛ `control.lock_state` غیر NULL) ← `refused` و audit. اجرای refused بعد از آزاد شدن قفل دوباره صف میشود (`requeue_runs` در Maintenance).
- **`claim` رد میکند:** کاری که بسته شده (`done`، `cancelled`، `failed`) ← `work_closed`؛ کاری که بودجه‌ی دلاری‌اش تمام است ← `budget_used_up`.
- **heartbeat:** هر فراخوانی مدل، از جمله استریم پاسخ مشاور، هر ۲۰ ثانیه heartbeat میزند (timeout خود activity ۳ دقیقه است)، و هر delta هم heartbeat میزند. پس پاسخ Opus بلندتر از ۳ دقیقه هم ذخیره میشود.
- **ماسک (۵.۱ §۲.۱):** هر چه مدل میخواند و هر چه ایجنت مینویسد از `hq_common.redact` رد میشود. این شامل context اجرا (brief، پیام‌ها، کارت تصمیم و payload، حافظه، خلاصه‌ی خروجی‌ها)، `summary_fa` قدم‌ها و delta‌های زنده به مالک است. delta‌ها خط‌به‌خط ماسک میشوند (`ScrubBuffer`)، تا رمزی که بین دو delta بریده شده هم دیده شود. متن بیرونی فقط ماسک میشود و **هرگز کوتاه نمیشود**.

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
| رزرو | `POST /internal/v1/runs/self/reserve`: اجرا `running` است، سقف ابزار در هر قدم و هر اجرا (بیشتر ← `429 rate_limited`، با audit) |
| کاتالوگ | ابزار ناشناخته ← `unknown_tool`. هیچ ابزار A3 یا A4 وجود ندارد |
| منشور | ابزار بیرون از `tools` منشور ← `tool_not_in_charter` |
| سیاست | OPA ‏`hq.actions`: کلاس بر اساس نقش، A4 هرگز، شرکت قفل ← نوشتن رد |
| اعتبارسنجی | Pydantic هر ابزار؛ خطا فقط نام فیلد را میگوید، نه مقدار را |
| انجام | API داخلی با توکن همان اجرا. timeout هر ابزار ۲۵ ثانیه، و یک مهلت کلی برای کل فراخوانی (`GATEWAY_DEADLINE_S` = ۳۰، کمتر از ۴۰ ثانیه‌ی worker) |
| redaction | `hq_common.redact` (یک ماژول برای کل هاب): نرمال‌سازی NFKC و حذف نویسه‌های قالب‌بندی، کلید و توکن (`KEY=value`، `"key": "value"`، Bearer/Basic، PEM حتی بدون END، `hvs.`، `AIza`، `sk_live_`)، ایمیل، تلفن (لاتین، فارسی، عربی-هندی، ثابت، `00`)، کارت (فقط با Luhn)، IBAN، کد ملی و کلیدهای dict. زمان خطی است. **نتیجه‌ای که به مدل برمیگردد** حداکثر ۱۶٬۰۰۰ کاراکتر است؛ **متنی که ایجنت مینویسد** کامل میرود و بزرگ‌تر از سقف قرارداد ← `invalid_args` |
| audit | `POST /internal/v1/runs/self/tool-calls`: یک ردیف `tool.call` برای **هر** فراخوانی، هر چه شد (رد در رزرو، سقف، استثنا ← `internal_error`، timeout). شامل ابزار، کلاس، نتیجه، کد و ref است، بدون ورودی و خروجی. فقط توکنی که اجرایش تمام شده audit نمیشود (API آن را رد میکند) |

- **ورودی:** نام ابزار با `fullmatch` (یعنی `work.get\n` ابزار نیست). آرگومان غیر object ← `invalid_args`. عدد بودجه و سهمیه strict و `≥ 0`. بدنه‌ی chunked بزرگ‌تر از سقف ← `413`.
- **راهنمای فارسی رد:** `message_fa` پاسخ API در نتیجه‌ی ابزار به شکل `hint_fa` به مدل میرسد. مثال: `hiring_closed` ← «استخدام بسته است؛ کمبود تیم را در خروجی‌ات بنویس».
- **اعلان فوری زیر قفل:** نام ابزار `notify` در OPA به اقدام `notification.raise` نگاشت میشود (یک جا، `hq.actions`). پس 🔴 حادثه‌ی دسته‌ی مجاز از ایجنت شرکت قفل‌شده میرسد، و اعلان غیرفوری رد میشود. نبودِ `company_locked` در هر دو سیاست یعنی قفل.

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
- deltaها فقط در حافظه‌ی api میمانند (`LiveHub`). روی NATS فقط متادیتای `run.*` میرود (topic ‏`runs` استریم: `run.started`، `run.step`، `run.finished`). وقتی پاسخ زنده خاموش است، `/threads/{code}/live` جواب `503 live_unavailable` میدهد.
- **مشاور هیچ ابزار نوشتنی ندارد** جز `message.thread` در thread خودش (`A`) و `memory.write`.
- «با مشاور بررسی کن» (`POST /decisions/{ref}/review-with-advisor`): همین مسیر، با کارت تصمیم به‌عنوان زمینه.
- پیام مالک در thread یک مدیرعامل، مدیر یا کارمند ← اجرای همان نقش. پاسخ ایجنت با `message.thread`.
- **گزارش صبحگاهی:** اول نسخه‌ی قاعده‌محور (Deliverable ‏`HQ-SYS`). بعد یک فراخوانی Sonnet 5.5 (effort `medium`، P3) آن را به متن فارسی خوش‌خوان تبدیل میکند. خروجی فقط وقتی نگه داشته میشود که **همه‌ی عددهایش در نسخه‌ی قاعده‌محور باشد** (`report.same_numbers`). نتیجه Deliverable دوم «(متن خوش‌خوان)» است و اعلان به آن لینک میدهد. خاموش کردن: `HQ_MORNING_REPORT_LLM=off`.
- **گزارش روزانه‌ی مدیرعامل‌ها:** فقط زیرساخت. Schedule ‏`hq-ceo-daily` ساخته میشود ولی تا `HQ_CEO_DAILY_REPORTS=on` نشود pause است.

- **کارت تصمیم در prompt (۵.۱ §۱.۱):** context اجرا در تراکنشی خوانده میشود که دامنه‌اش همان دامنه‌ی منشور است (شرکت خود کارمند، یا همه‌ی شرکت‌ها برای منشور `scope: holding`). کارت و هر پیوند پیام فقط وقتی دیده میشود که در همین دامنه باشد. پیامی که ایجنت (یا مالک) با `links` به چیزی بیرون از شرکت thread یا دامنه‌ی خواندن نویسنده میفرستد ← `422 validation_failed` (`fields.links`).
- **مصرف خروجی (۵.۱ §۲.۷):** `usage` و `produced_with` (اتصال، ارائه‌دهنده، مدل، effort) هر خروجیِ یک اجرا از ردیف‌های `llm.calls` همان اجرا پر میشوند. آنچه ایجنت میفرستد نادیده گرفته میشود.

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
- **ثبت:** `llm.quota_status` (یک ردیف برای هر اتصال) و وضعیت هر پنجره جدا در `windows` (`five_hour`، `seven_day`، …). وضعیت ردیف بدترینِ پنجره‌هایی است که هنوز معتبرند. بعد از `resets_at` خودکار `ok` میشود.
- **هرگز برای همیشه `limited` نمیماند (۵.۱ §۲.۴):** وقتی زمان reset در متن خطا نیست (همه‌ی `billing_error`ها)، نگه‌داشتن تا `retry_at` شکن مدار یا «الان + ۵ ساعت» است. `resets_estimated = true` این را نشان میدهد. هیچ ردیف غیر `ok` بدون `resets_at` ذخیره نمیشود (CHECK). ری‌استارت router همان پایان را میخواند. پنجره‌ی نامعتبر پیش از ذخیره رد و لاگ میشود. در حالت half-open شکن هم سهمیه بررسی میشود.
- **اثر:** `warning` ← P4 متوقف؛ `limited` ← فقط P0 تا P2.
- **خبر:** هر تغییر وضعیت یک پیام `hq.alerts.quota` میفرستد. worker آن را به `budget.alert` (kind ‏`quota`) و یک اعلان 🔵 تبدیل میکند (یک بار برای هر تغییر).
- **دیدن:** `GET /api/v1/treasury/quota`.

## ۷. استخدام با شروع مالک (۵.۱ §۱.۳، قرارداد §۱۸.۱۱)
- **وضعیت:** `core.hiring`، یک ردیف برای هلدینگ، با RLS. اگر ردیف نباشد یعنی «بسته». `core.hiring_state()` این وضعیت را به هر فراخواننده‌ای میدهد، چون تراکنش شرکتیِ ایجنت ردیف هلدینگ را نمیبیند. هر خطا هم «بسته» حساب میشود (fail-closed).
- **دروازه:** وقتی استخدام بسته است، پیشنهاد `hire` یک ایجنت **پیش از ساخته شدن کارت** رد میشود: `403 hiring_closed`. این در سه جا بررسی میشود: مسیر داخلی، `domain/decisions.propose` و OPA ‏`hq.internal` (وضعیت با `hiring` فرستاده میشود و نبودش یعنی بسته). برکناری، بودجه و بقیه‌ی انواع تصمیم اثری نمیگیرند. `company.state` فیلد `hiring` را برمیگرداند.
- **مالک:**
  - `GET /owner/hiring`
  - `POST /owner/hiring/start` 🔏 (`hiring.start`، target ‏`holding`):
    - `proposals`: استخدام باز میشود. هر مدیرعامل و هر رئیس هلدینگی که وظیفه‌ی استخدام دارد یک کار «تیمت را پیشنهاد بده» میگیرد (`seed/bootstrap/hiring_proposals.yaml`، با اولویت منشورش). شروع دوباره کار دوم نمیسازد.
    - `self`: برای ایجنت‌ها بسته میماند.
  - `POST /owner/hiring/close` (بدون step-up): کارت‌های در انتظار `withdrawn` میشوند.
  - `POST /org/hires` 🔏 (`hire.direct`، target = SHA-256 بدنه): کارت `hire` را که مالک هم پیشنهاد و هم مُهر کرده در یک تراکنش مینویسد، و بعد کارمند را میسازد.
- **پس گرفتن کارت:** `cartable.withdraw_pending_hires(note)` کارت را `withdrawn` میکند، با `decided_by` سیستم، یادداشت مالک، پیام سیستم در thread، `decision.updated`، audit ‏`decision.withdraw` و ref در `withdrawn`. **هیچ چیزی حذف نمیشود.** migration ‏0010 همین را یک بار اجرا کرد (D-000001 تا D-000007) و کارهای ماه ۱ را که هنوز باز بودند با همان یادداشت لغو کرد. Maintenance هر `DecisionLifecycle` را که هنوز منتظر کارتِ دیگر در انتظار نیست بیدار میکند تا با همان نتیجه تمام شود.
- **استریم:** `hiring.changed` روی topic ‏`control`.

## ۸. مدل جعلی و تست
- llm-router با `LLM_FAKE_BACKEND=1` یک backend ‏`fake` دارد که پاسخ‌های از پیش نوشته را برمیگرداند (صف برای هر actor، یا `script`). CI هیچ فراخوانی واقعی نمیکند.
- تست‌های api کل خط را در یک پروسه اجرا میکنند (`tests/agents_env.py`): router، gateway و api با ASGI، و Temporal و Postgres واقعی.
- پوشش ≥ ۸۵٪ برای runner، gateway، redaction، چکر سایت و quota controller (`scripts/quality/python.sh`).

## ۹. آزمودن prompt یک منشور با مدل واقعی
`make prompt-check role=advisor` (یا هر نقش دیگر): یک فراخوانی واقعی از راه llm-router با فراخواننده‌ی `hq-ops`، با system prompt منشور، پروتکل و یک سؤال آزمایشی. اعتبار JSON قدم با schema سنجیده میشود و برای مشاور، مرحله‌ی پاسخ و citationها هم.
- **هیچ چیزی ذخیره نمیشود** جز ردیف ledger (`meta.purpose = prompt_check`): نه اجرا، نه پیام در thread ‏`A`، نه نشست.
- فقط متادیتا چاپ میشود (اعتبار، ابزارها، توکن‌ها)، نه prompt و نه متن مدل.
- بعد از هر تغییر منشور مفید است. هزینه دارد: Opus 5.5 برای مشاور.

## ۱۰. عیب‌یابی
| نشانه | کار |
|---|---|
| اجرایی شروع نمیشود | `GET /api/v1/runs?state=queued`؛ لاگ `make logs s=worker` (Dispatcher)؛ Temporal UI، workflow ‏`agent-run-<id>` |
| `refused` با `runtime_not_configured` | `kv/hq-agents/runtime` در OpenBao نیست: `make llm-provision` |
| `refused` یا `failed` با `daily_cap` | مصرف امروز به `AGENT_DAILY_TOKEN_CAP` رسیده؛ فردا (UTC) خودکار باز میشود |
| `refused` با `work_closed` | کار پیش از شروع اجرا بسته یا لغو شد؛ کاری برای انجام نیست |
| پیشنهاد استخدام `403 hiring_closed` | استخدام بسته است (`GET /api/v1/owner/hiring`)؛ فقط مالک باز میکند |
| همه‌ی اقدام‌ها `policy_denied` | قفل یا کلید توقف (`GET /api/v1/control/state`) |
| gateway unhealthy | `make logs s=gateway`؛ فایل hash توکن worker (`make bootstrap` یک بار، بعد `make up`) |
| حادثه‌ای باز نمیشود | `ops.checks` آخرین نتیجه‌ها؛ `enabled` سایت؛ Schedule ‏`hq-site-checks` در Temporal UI |
