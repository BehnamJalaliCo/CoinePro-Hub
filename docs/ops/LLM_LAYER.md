# لایه‌ی مدل‌ها (پرامپت ۳): llm-router، claude-runtime و پایه‌ی خزانه‌ی توکن

> **قانون اصلی:** **هر** فراخوانی مدل در کل هلدینگ فقط از `llm-router` رد میشود. هیچ سرویسی مستقیم به Claude یا یک API وصل نمیشود.
> این سرویس‌ها فقط داخلی‌اند: **هیچ پورتی منتشر نمیشود.**

## ۱. معماری

```
(فراخواننده‌های بعدی: ایجنت‌ها، مشاور، n8n، محصولات)
        │  HTTP داخلی + توکن سرویس (Bearer)
        ▼
  llm-router ──► claude-runtime ──► اشتراک Claude (Claude Agent SDK / Claude Code CLI 2.1.286)
     │   └─────► LiteLLM (کتابخانه، داخل خود router) ──► APIها (فعلاً همه خاموش)
     ├──► Postgres: جدول‌های llm.* (خزانه‌ی توکن)
     └──► NATS JetStream: رویدادهای hq.llm.* و hq.alerts.*
```

| سرویس | شبکه | کاربر و فایل‌سیستم | اسرار |
|---|---|---|---|
| `llm-router` (Python 3.12، FastAPI) | `hq-internal` + `hq-llm` | uid 10001؛ rootfs فقط‌خواندنی؛ tmpfs ۳۲MB؛ `cap_drop: ALL` | AppRole ‏`llm-router` |
| `claude-runtime` (Python 3.12، `claude-agent-sdk==0.2.163`) | **فقط** `hq-llm` | uid 10001؛ rootfs فقط‌خواندنی؛ tmpfs ۲۵۶MB؛ `cap_drop: ALL` | AppRole ‏`claude-runtime` |

- شبکه‌ی **`hq-llm`** (`172.30.1.0/24`) فقط این‌ها را دارد: router، runtime، OpenBao و Prometheus. پس runtime به اینترنت (API ‏Anthropic) میرسد، ولی **به Postgres، Valkey، NATS، Temporal و Grafana دسترسی ندارد.** این را آزمایش هم کرده‌ایم.
- **فقط router میتواند runtime را صدا بزند:** شبکه‌ی جدا، به‌علاوه‌ی یک توکن مشترک که فقط در OpenBao است.
- **هیچ** سوکت Docker، کلید SSH یا mount از ریپوها داخل این دو کانتینر نیست.

## ۲. ایمنی هر اجرا در claude-runtime
- **ابزارها کاملاً خاموش‌اند** (`tools=[]`). MCP، skills، plugins و فایل‌های تنظیمات و `CLAUDE.md` هم بار نمیشوند (`setting_sources=[]`).
- **system prompt جایگزین کامل است.** از یک فایل داخل پوشه‌ی اجرا خوانده میشود، نه از آرگومان خط فرمان. پس در `ps` دیده نمیشود. خود prompt از stdin میرود.
- **پوشه‌ی کاری و HOME جدا و خالی برای هر اجرا** روی tmpfs ساخته میشوند و بعد از اجرا پاک میشوند.
- `CLAUDE_CODE_OAUTH_TOKEN` فقط به پروسه‌ی CLI داده میشود، نه به env کانتینر. موقع start از OpenBao خوانده میشود و هرگز چاپ نمیشود.
- خروجی stderr ‏CLI فقط شمرده میشود و لاگ نمیشود.
- **effort:** SDK و CLI از `--effort` پشتیبانی میکنند و مقدار درخواستی اعمال میشود. در ledger، `meta.effort_applied` ثبت میشود.
- **توکن فکر:** Claude Code آن را جدا گزارش نمیکند. پس `thinking_tokens` برای اشتراک `NULL` است و این توکن‌ها **داخل `output_tokens`** حساب شده‌اند. برای APIها، اگر ارائه‌دهنده `reasoning_tokens` بدهد، ثبت میشود.

## ۳. API داخلی llm-router (پورت 8000، فقط داخل شبکه)
| endpoint | کار |
|---|---|
| `POST /v1/run` | ورودی‌ها: `company_code`، `actor_ref`، `work_ref?`، `department?`، `role?`، `task_class`، `priority` (`P0` تا `P4` یا 0 تا 4)، `model?`، `effort?`، `system?`، `messages` یا `prompt`، `json_schema?`، `timeout_s`، `store_transcript?`. خروجی: `call_id`، `status`، `text`، `json`، `usage`، `connection`، `model`، `effort`، `cost_usd`، `equiv_cost_usd`، `latency_ms`. |
| `POST /v1/run/stream` | همان، به‌صورت SSE: رویدادهای `start`، `delta` و `end` |
| `GET /v1/health` | وضعیت DB، NATS و صف |
| `GET /v1/connections` | اتصال‌ها، وضعیت و breaker (بدون هیچ secret یا secret_ref) |
| `GET /metrics` | متریک‌های Prometheus، **با توکن جدای metrics** |

- **هیچ endpoint بی‌احرازی وجود ندارد.** `/docs` و `/openapi.json` خاموش‌اند. healthcheck ‏Docker از یک فایل heartbeat میخواند، نه از HTTP.
- **احراز هویت:** `Authorization: Bearer <token>`. فراخواننده‌ها در OpenBao (`kv/llm-router/callers`) فقط با **SHA-256 توکن** ثبت شده‌اند. اولین فراخواننده `hq-ops` است و توکنش در `/home/Hub/.secrets/llm-router-caller-hq-ops.token` با دسترسی `600` قرار دارد.
- **سقف‌ها:**
  - حجم بدنه: ۵۱۲KB (`413`)
  - متن ورودی برای هر فراخواننده (`max_input_chars`)
  - `timeout_s` حداکثر ۶۰۰ ثانیه
  - rate limit برای هر فراخواننده (`rpm`؛ `429` با `Retry-After`). روی همه‌ی درخواست‌ها شمرده میشود.
- خطای اعتبارسنجی (`422`) **هیچ‌وقت مقدار ورودی را برنمیگرداند.**

## ۴. اولویت‌ها و صف
| اولویت | چه چیزی |
|---|---|
| P0 | اتاق جنگ و حادثه‌ی SEV1 |
| P1 | چیزهایی که کاربر محصولات مستقیم میبیند |
| P2 | گفت‌وگوی مالک و مشاور کل |
| P3 | تحلیل هشدارهای غیر SEV1، و کارهای زمان‌بندی‌شده‌ی عملیاتی |
| P4 | پس‌زمینه (محتوا، گزارش‌های غیرفوری) |

- **همزمانی:** `LLM_MAX_CONCURRENCY` (۳ در lean، ۵ در full). **یک جایگاه همیشه برای P0 تا P2 رزرو است:** P3 و P4 فقط تا وقتی `active < capacity − 1` باشد شروع میشوند.
- **ترتیب سرویس‌دهی:** اولویت بالاتر اول، و در هر اولویت به ترتیب رسیدن.
- **صف پر:**
  - P4 اگر نتواند فوراً شروع کند و ۴ درخواست P4 دیگر منتظر باشند، رد میشود (`429`، «دوباره تلاش کن»، `Retry-After`).
  - همه‌ی اولویت‌ها اگر ۳۲ درخواست در صف باشد رد میشوند (`503`).
- **صف حافظه‌ای است.** صف ماندگار با Temporal در پرامپت‌های بعد میاید.

## ۵. تخصیص اتصال (ارث‌بری)
`holding` → `company` → `department` → `role` → `task_class`. هر سطح سطح بالاتر را **فیلد به فیلد** بازنویسی میکند (اتصال، مدل، effort).

| scope_type | scope_ref |
|---|---|
| holding | کد هلدینگ (`HQ`) |
| company | کد شرکت (`TY`) |
| department | `<شرکت>-<دپارتمان>` (`TY-TECH`) |
| role | `<role>` یا `<شرکت>:<role>` (حالت دوم مشخص‌تر است) |
| task_class | `<task_class>` یا `<شرکت>:<task_class>` |

- اگر اتصال عوض شود، مدلِ به ارث رسیده کنار گذاشته میشود.
- درخواست میتواند `model` و `effort` را تعیین کند، ولی مدل باید در `models` همان اتصال باشد. **فراخواننده نمیتواند اتصال را انتخاب کند.**
- **تخصیص‌های پیش‌فرض (seed):**
  - کل هلدینگ: `claude-max`، مدل `claude-sonnet-5-5`، effort `medium`
  - نقش `advisor` (مشاور کل): `claude-opus-5-5`، effort `xhigh`

## ۶. نگهبان سهمیه، breaker و اتصال جایگزین
- برای هر اتصال یک **circuit breaker** وجود دارد: `closed` ← `open` ← `half_open` با **فقط یک درخواست آزمایشی** ← `closed`.
  - ۵ خطای پشت‌سرهم breaker را باز میکند. cooldown از ۳۰ ثانیه شروع میشود و هر بار دو برابر میشود تا سقف ۱۰ دقیقه.
  - **درس Claude Intel در TradeYar:** وضعیت `open` بدون `opened_at` و `retry_at` **قابل ساختن نیست.** این در کد قفل شده و با تست بررسی میشود.
- **سقف مصرف اشتراک** را این نشانه‌ها نشان میدهند:
  - رویداد `rate_limit_event` با وضعیت `rejected`
  - خطای `rate_limit` یا `billing_error` همراه متن «usage limit»
  - HTTP 429

  در این حالت اتصال `quota_exhausted` میشود. **زمان ریست** را اگر گزارش شده باشد از همان میگیرد، وگرنه backoff پنج دقیقه‌ای که دو برابر میشود تا سقف یک ساعت. این وضعیت در DB ذخیره میشود و بعد از restart هم میماند. بعد از ریست، یک probe میرود و اگر موفق شد اتصال خودکار `enabled` میشود.
- **وقتی سهمیه تمام است (§۱.۶):**
  - P4 رد میشود (`429` + `Retry-After`).
  - P0 تا P3 **فقط** اگر `task_class` قابل انتقال باشد و یک اتصال جایگزین **روشن** باشد به آن میروند. در ledger، `meta.fallback_from` ثبت میشود.
  - در غیر این صورت خطای روشن `quota_exhausted` (`503` + `Retry-After`) برمیگردد.
  - **الان همه‌ی جایگزین‌ها خاموش‌اند.**
- **کلاس‌های قابل انتقال (seed):** `translate`، `summarize`، `classify`، `extract`، `draft`.
- **هرگز منتقل نمیشوند:** `advisor`، `coding`، `decision`، `customer_message`، `ops_alert`، `general`.

## ۷. بودجه و ناهنجاری
- **قبل از هر فراخوانی،** بودجه‌ی همه‌ی سطح‌های مربوط (`llm.budgets`) با شمارنده‌های `llm.usage` (روزانه و ماهانه، UTC) مقایسه میشود.
  - در ۷۰٪ و ۹۰٪: رویداد `hq.alerts.budget.<شرکت>`، یک بار برای هر سطح در هر دوره.
  - در ۱۰۰٪: **P4 رد میشود** (`rejected_budget`، `429`، و `Retry-After` تا شروع دوره‌ی بعد). P0 تا P3 انجام میشوند و هشدار ۱۰۰٪ میدهند.
- **توکن‌های بودجه** = ورودی + خروجی + خواندن cache + نوشتن cache.
- **دلار بودجه** = هزینه‌ی واقعی API، به‌علاوه‌ی `equiv_cost_usd` برای اشتراک (به‌عنوان شاخص مصرف سهمیه).
- **ناهنجاری:** هر ۵ دقیقه چک میشود. اگر تعداد فراخوانی یک `actor_ref` در ساعت جاری بیشتر از ۳ برابر میانه‌ی ساعتی ۷ روز گذشته باشد (ساعت‌های بی‌فراخوانی صفر حساب میشوند)، و حداقل ۳۰ باشد، رویداد `hq.alerts.llm.anomaly` ارسال میشود.

## ۸. جدول‌ها (دیتابیس `hq`)
| جدول | چه چیزی | RLS |
|---|---|---|
| `core.companies` | شرکت‌ها از seed (`HQ` هلدینگ، `TY`، `FX`، `PC`). **هیچ فهرست ثابتی در کد نیست.** | — |
| `llm.connections` | هر حساب اشتراک یا کلید API. `secret_ref` = **فقط مسیر OpenBao**. قیمت‌ها برای هر مدل به دلار به ازای هر یک میلیون توکن. `fallback_priority` | — |
| `llm.task_classes` | کلاس کار و قابل انتقال بودن | — |
| `llm.assignments` | تخصیص‌ها | — |
| `llm.calls` | **دفتر خزانه‌ی توکن:** یک ردیف برای هر فراخوانی، با پارتیشن ماهانه. ایندکس `(company_id, started_at)`. وضعیت‌ها: `running`، `ok`، `error`، `refusal`، `timeout`، `rate_limited`، `quota_exhausted`، `rejected_budget` | ✅ |
| `llm.usage` | شمارنده‌ی هر scope و دوره | ✅ |
| `llm.budgets` | بودجه‌ها | ✅ |
| `llm.transcripts` | متن فقط وقتی `store_transcript=true` باشد. ماندگاری ۳۰ روز (`LLM_TRANSCRIPT_RETENTION_DAYS`)، و هر ۶ ساعت پاک میشود. | ✅ |
| `llm.v_usage_daily`، `llm.v_usage_monthly`، `llm.v_top_actors_30d` | viewهای تجمیعی (`security_invoker`) | از جدول‌ها |

- **متن prompt و پاسخ هرگز در `llm.calls`، لاگ‌ها، Loki یا رویدادهای NATS نوشته نمیشود.** این با تست بررسی میشود.
- **RLS:** متغیر `app.company_ids` (یک آرایه‌ی uuid) برای هر تراکنش با `SET LOCAL` تنظیم میشود.
  - `hq_llm_writer`: select، insert و update فقط روی شرکت‌های مجاز
  - `hq_llm_reader`: فقط خواندن
  - **هیچ‌کس حذف نمیکند.**
  - `FORCE ROW LEVEL SECURITY` مالک جدول (`hq`) را هم محدود میکند.
  - پارتیشن‌ها grant ندارند، پس از آن‌ها نمیشود RLS را دور زد.
  - تست cross-company هم در CI و هم روی دیتابیس واقعی، در یک تراکنش rollback‌شده، پاس شد.
- **نقش‌ها:** `db-provision` (superuser، idempotent) نقش‌ها را میسازد: `hq_llm_writer`، `hq_llm_reader` و `llm_router` (login، عضو writer). migrationها را Alembic با نقش `hq` اجرا میکند (`llm-migrate`).

## ۹. OpenBao
| مسیر | چه کسی میخواند | محتوا |
|---|---|---|
| `kv/llm-router/config` | llm-router | توکن صدا زدن runtime، هش توکن metrics |
| `kv/llm-router/callers` | llm-router | فراخواننده‌ها (فقط هش توکن)، `rpm` و `max_input_chars` |
| `kv/llm-connections/<key>` | llm-router | `api_key` هر اتصال API (فعلاً خالی) |
| `kv/claude-runtime/config` | claude-runtime | هش توکن router و هش توکن metrics |
| `kv/claude-runtime/oauth` | claude-runtime | `token` = ‏`CLAUDE_CODE_OAUTH_TOKEN` (با `make claude-token`) |

- **AppRole برای هر سرویس:**
  - token TTL یک ساعت و max چهار ساعت
  - `token_no_default_policy`
  - محدود به CIDRهای شبکه‌ی Docker
  - فایل `role_id`/`secret_id` در `/home/Hub/.secrets/services/<service>/approle.json`، با دسترسی `600` و مالک uid 10001
- **توکن ادمین غیر root:**
  - policy ‏`hq-admin`، periodic با دوره‌ی ۳۲ روز
  - در هر `make up` تمدید میشود
  - فایل `/home/Hub/.secrets/openbao-admin.token`
  - root token فقط بار اول استفاده شد و **باطل نشده** (تصمیمش با مالک است)
- **توکن metrics برای Prometheus:** فایل `/home/Hub/.secrets/services/prometheus/llm-metrics.token` با دسترسی `600` و مالک uid 65534.

## ۱۰. افزودن یا روشن کردن یک اتصال
1. **قبل از روشن کردن:** طبق §۱.۶، آزمون‌های SimGym برای آن ارائه‌دهنده و کلاس کار پاس شده باشند، و مالک تصمیم گرفته باشد. زودتر از ماه ۴ نه.
2. **کلید را در OpenBao بگذار** (با توکن ادمین، بدون چاپ):
   ```bash
   read -rs KEY
   KEY="$KEY" jq -n '{data:{api_key: env.KEY}}' | curl -sS -H "X-Vault-Token: $(cat /home/Hub/.secrets/openbao-admin.token)" \
     --data-binary @- http://127.0.0.1:8200/v1/kv/data/llm-connections/<key> >/dev/null; unset KEY
   ```
   (UI این کار در پرامپت‌های بعد میاید.)
3. در `llm.connections` این‌ها را تنظیم کن: `models`، `default_model`، `pricing` (دلار به ازای هر یک میلیون توکن)، `api_base` (برای OpenAI-compatible) و `fallback_priority`. بعد `status='enabled'`.
4. **اتصال جدید:** یک ردیف جدید با `secret_ref='kv/llm-connections/<key>'` بساز. providerهای پشتیبانی‌شده: `anthropic`، `openai`، `gemini`، `openai_compatible`. router بعد از حداکثر ۳۰ ثانیه آن را میبیند.
5. **تخصیص:** یک ردیف در `llm.assignments` در سطح دلخواه (مثلاً `company`/`TY`).

## ۱۱. پایش
- **داشبورد Grafana «Token Treasury — Ops»:**
  - فراخوانی‌ها بر اساس وضعیت، توکن‌ها، latency، عمق صف
  - breaker و سهمیه، رد شدن‌ها و هشدارها
  - مصرف هر شرکت، و وضعیت توکن Claude
- **متریک‌ها:** `llm_calls_total`، `llm_tokens_total`، `llm_cost_usd_total{kind=real|equiv}`، `llm_call_latency_seconds`، `llm_queue_depth`، `llm_active_calls`، `llm_breaker_state`، `llm_connection_quota_exhausted`، `llm_budget_rejections_total`، `llm_budget_alerts_total`، `llm_queue_rejections_total`، `llm_caller_rate_limited_total`، `llm_anomaly_alerts_total` و `claude_runtime_*`.
- **لاگ‌ها:** JSON و فقط متادیتا. فیلدهایی با اسم محتوا (`prompt`، `text` و غیره) در formatter حذف میشوند. از exceptionها فقط نوع خطا ثبت میشود.

## ۱۲. حافظه
- **CLI هر اجرا:** حدود ۱۸۰MB در حالت بیکار (اندازه‌گیری‌شده)، و حدود ۲۵۰ تا ۳۰۰MB هنگام پاسخ.
- **سقف‌ها در lean:** router ‏256m، runtime ‏1152m (۳ اجرای همزمان).
- **قانون جدید:** جمع همه‌ی سقف‌ها ≤ ۸۰٪ RAM. الان lean = ‏6032 MiB از 6196 MiB، و full = ‏8880 MiB از 9011 MiB. `make check` این را چک میکند.
