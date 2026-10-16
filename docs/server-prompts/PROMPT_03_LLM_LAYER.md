# پرامپت ۳: لایه‌ی مدل‌ها (LLM Router، claude-runtime، پایه‌ی خزانه‌ی توکن)

> **برای مالک:** کل متن زیر خط را کپی کن و به Claude Code روی سرور هاب بده. وسط کار یک بار از تو میخواهد `claude setup-token` را بزنی (بخش ۸). گزارش کوتاه آخرش را برای Claude سشن مشورت بیاور.

---

تو **Claude Code روی سرور هاب «CoinePro HQ»** هستی. این مرحله **لایه‌ی مدل‌ها** را میسازد: تنها مسیری که **هر** فراخوانی مدل هوش مصنوعی در کل هلدینگ از آن رد میشود. **هیچ ایجنت، UI، n8n یا API عمومی در این مرحله ساخته نمیشود.** این سرویس‌ها فقط داخلی‌اند.

## ۰. قبل از شروع (اجباری)
1. در `/home/Hub/CoinePro-Hub` آخرین نسخه‌ی `claude/coinepro-hub-setup-hsvnw7` را pull کن و شاخه‌ی **`server/p03-llm-layer`** را از آن بساز.
2. **این‌ها را کامل بخوان و رعایت کن:**
   - `CLAUDE.md`
   - `docs/OPERATING_MODEL.md` (به‌خصوص **§۰**، **§۱.۶**، **§۱.۱۳**، **§۱.۴** بخش «مسیر دستور»)
   - `docs/TECH_STACK.md`
   - `docs/ops/RUNBOOK.md`
   - `docs/server-prompts/README.md`
3. **تسک‌بندی اجباری:** قبل از هر کاری، **همه‌ی کارهای این پرامپت را در لیست تسک بشکن.** هر تسک یک تست قبولی دارد. بعد:
   - بدون توقف یکی‌یکی جلو برو.
   - کارهای مستقل را موازی کن.
   - لیست را به‌روز نگه دار.
4. **فقط در این موارد متوقف شو و بپرس:**
   - تصمیمی که با مالک است
   - خطر غیرمنتظره
   - **بخش ۸** (توکن Claude)، که فقط مالک انجامش میدهد

## ۱. معماری این مرحله
```
(future callers: agents, advisor, n8n, products)
        │  internal HTTP + service token
        ▼
  llm-router  ──►  claude-runtime  ──►  Claude subscription (Claude Agent SDK / Claude Code)
     │   └────────►  LiteLLM (Python library, in-process)  ──►  API providers (ALL DISABLED now)
     ├──►  Postgres: llm.* ledger (Token Treasury)
     └──►  NATS: hq.llm.* events (for the future live stream)
```
- **`llm-router`** (`services/llm-router/`، Python 3.12، FastAPI): تنها درگاه.
  - تخصیص اتصال را حل میکند.
  - بودجه و اولویت را اعمال میکند.
  - به backend مناسب میفرستد.
  - **برای هر فراخوانی یک ردیف در ledger ثبت میکند.**
  - رویداد NATS میفرستد.
- **`claude-runtime`** (`services/claude-runtime/`، Python 3.12): اجرای مدل با **اشتراک Claude** از طریق **Claude Agent SDK رسمی (`claude-agent-sdk`)**، با نسخه‌ی ثابت. **فقط llm-router حق صدا زدنش را دارد.**
- **LiteLLM** (فقط بخش متن‌باز MIT): به‌صورت **کتابخانه‌ی داخل llm-router**، نه proxy جدا. **همه‌ی اتصال‌های API در این مرحله خاموش‌اند.**
- **هر دو سرویس:**
  - فقط روی شبکه‌ی `hq-internal`، **بدون پورت منتشرشده.** اگر برای تست لازم شد، فقط `127.0.0.1`.
  - کاربر غیر root، rootfs فقط‌خواندنی و tmpfs.
  - **هیچ سوکت Docker، هیچ SSH، و هیچ mount از ریپوهای دیگر.**

## ۲. داده‌ها (Postgres، دیتابیس `hq`)
- **migration با Alembic** (`apps/api/` هنوز خالی است، پس migrationهای این لایه در `services/llm-router/migrations/` قرار میگیرند).
- **schema `core`، فقط جدول حداقلی `core.companies`:**
  - ستون‌ها: `id` (uuid)، `code` (یکتا، مثل `HQ` و `TY`)، `name`، `kind` (`holding` یا `company`)، `status`، `created_at`
  - داده‌ی اولیه از یک **فایل seed** (نه در کد): `HQ` (CoinePro HQ, holding)، `TY` (TradeYar)، `FX` (CoinePro FX)، `PC` (Pro-Chart)
  - **هیچ فهرست ثابتی از شرکت‌ها در کد نیست** (§۰). جدول در پرامپت‌های بعد کامل میشود.
- **schema `llm`:**
  - **`connections`:**
    - `id`، `kind` (`claude_subscription` یا `api`)، `provider`، `display_name`، `status` (`enabled`، `disabled` یا `quota_exhausted`)
    - **`secret_ref`** (فقط مسیر در OpenBao؛ **هرگز خود کلید**)
    - مدل‌های مجاز، **جدول قیمت** (ورودی، خروجی، خواندن cache و نوشتن cache به ازای هر یک میلیون توکن، به دلار)
    - سقف‌ها
  - **`assignments`:**
    - `scope_type` (`holding`، `company`، `department`، `role` یا `task_class`)، `scope_ref`، `connection_id`، `model`، `effort`
    - **حل ارث‌بری:** task_class ← role ← department ← company ← holding. هر سطح، سطح بالاتر را بازنویسی میکند.
  - **`budgets`:**
    - `scope_type`، `scope_ref`، دوره (`day` یا `month`)، `token_limit` و `usd_limit`
    - آستانه‌ی هشدار ۷۰٪ و ۹۰٪
    - **در ۱۰۰٪ توقف کارهای P4**
  - **`calls`** (دفتر خزانه‌ی توکن):
    - `id` (uuid v7)، `started_at`، `finished_at`، **`company_id`**، `department`، `actor_ref` (مثل `TY-TECH-01`، `owner` یا `advisor`)، `work_ref`، `task_class`، `priority`، `connection_id`، `provider`، `model`، `effort`
    - **`input_tokens`، `output_tokens`، `cache_read_tokens`، `cache_write_tokens`، `thinking_tokens`**. اگر توکن فکر جدا گزارش نشد، `NULL` بماند و در مستندات بنویس که داخل `output_tokens` حساب شده.
    - **`cost_usd`** (برای API)، **`equiv_cost_usd`** (برای اشتراک؛ همان `total_cost_usd` که SDK برمیگرداند)، `latency_ms`
    - `status` (`ok`، `error`، `refusal`، `timeout`، `rate_limited`، `quota_exhausted` یا `rejected_budget`)، `error_class`
    - **پارتیشن ماهانه**، و ایندکس روی `(company_id, started_at)`.
  - **`transcripts`** (اختیاری و پیش‌فرض خاموش): فقط وقتی فراخواننده `store_transcript=true` بفرستد. retention آن قابل تنظیم است.
    - **متن prompt و پاسخ هرگز در ledger، لاگ‌ها یا Loki نوشته نمیشود.**
- **Row-Level Security روی `llm.calls`، `llm.budgets` و `llm.transcripts`**، بر اساس `company_id` و یک متغیر session (مثلاً `app.company_ids`):
  - نقش **`hq_llm_writer`** فقط insert و update روی ردیف‌های خودش.
  - نقش **`hq_llm_reader`** فقط خواندن، محدود به شرکت‌های مجاز.
  - **تست cross-company اجباری است:** یک session با مجوز `TY` نباید هیچ ردیفی از `FX` ببیند.
- **viewهای تجمیعی:** مصرف روزانه به تفکیک شرکت، اتصال و مدل؛ مصرف ماهانه؛ پرمصرف‌ترین `actor_ref`ها.

## ۳. API داخلی llm-router
| endpoint | کار |
|---|---|
| `POST /v1/run` | ورودی: `company_code`، `actor_ref`، `work_ref?`، `task_class`، `priority` (P0 تا P4)، `model?`، `effort?`، `system`، `messages` یا `prompt`، `json_schema?`، `timeout_s`، `store_transcript?`. خروجی: متن یا JSON، `usage`، `call_id`، `connection`، `model`. |
| `POST /v1/run/stream` | همان، به‌صورت SSE |
| `GET /v1/health` | سلامت |
| `GET /v1/connections` | فهرست اتصال‌ها با وضعیت (بدون secret) |

- **احراز هویت اجباری:** هدر توکن سرویس (از OpenBao). **هیچ endpoint بدون احراز هویتی وجود ندارد.**
- **سقف حجم ورودی، timeout و rate limit** برای هر فراخواننده.

**اولویت‌ها و صف:**
| اولویت | چه چیزی |
|---|---|
| **P0** | اتاق جنگ و حادثه‌ی SEV1 |
| **P1** | چیزهایی که کاربر محصولات مستقیم میبیند |
| **P2** | گفت‌وگوی مالک و مشاور کل |
| **P3** | تحلیل هشدارهای غیر SEV1، و کارهای زمان‌بندی‌شده‌ی عملیاتی |
| **P4** | پس‌زمینه (محتوا، گزارش‌های غیرفوری) |

- **همزمانی** قابل تنظیم است (پیش‌فرض ۳ در پروفایل lean). **یک جایگاه همیشه برای P0 تا P2 رزرو است.**
- **صف پر:** درخواست P4 با پاسخ «دوباره تلاش کن» و `Retry-After` رد میشود. صف ماندگار با Temporal در پرامپت‌های بعد میاید.

## ۴. claude-runtime
- **Claude Agent SDK** با نسخه‌ی ثابت. اطلاعات ورود: **`CLAUDE_CODE_OAUTH_TOKEN`** که موقع start **از OpenBao خوانده میشود** (بخش ۸). **هرگز در لاگ یا خروجی نمیاید.**
- **ایمنی هر اجرا:**
  - **ابزارها پیش‌فرض خاموش**
  - یک پوشه‌ی کاری موقت و جدا که بعد از اجرا پاک میشود
  - system prompt **جایگزین کامل**
  - **بدون دسترسی به ریپو، سوکت Docker و شبکه‌ی داخلی**
- **مصرف هر اجرا** از نتیجه‌ی SDK خوانده میشود: `usage` و `total_cost_usd`.
- **`effort`:** اگر نسخه‌ی SDK یا CLI آن را پشتیبانی میکند اعمالش کن. اگر نه، مقدار درخواستی را ثبت کن و محدودیت را در گزارش بگو.
- **نگهبان سهمیه:**
  - پیام‌های «سقف مصرف» اشتراک را تشخیص بده. اتصال به `quota_exhausted` میرود، با زمان ریست اگر گزارش شده بود، وگرنه با backoff.
  - **circuit breaker درست:** `closed` ← `open` ← `half-open` با **فقط یک درخواست آزمایشی** ← `closed`. **(درس قفل شدن Claude Intel در TradeYar:** وضعیت باز بدون زمان شروع هرگز نباید ممکن باشد.)
- **وقتی سهمیه تمام است:**
  - P4 رد میشود، با `Retry-After`.
  - P0 تا P3 طبق §۱.۶ فقط اگر `task_class` «قابل انتقال» باشد و اتصال جایگزین **روشن** باشد به جایگزین میرود. **الان همه خاموش‌اند،** پس خطای روشن `quota_exhausted` برمیگردد.

## ۵. LiteLLM و اتصال‌های API
- **اتصال‌های الگو، همه `disabled` و بدون کلید:** `anthropic-api`، `openai`، `google-gemini`، و یک «OpenAI-compatible» عمومی برای ارائه‌دهنده‌های دیگر.
- **مسیر کلید در OpenBao** آماده باشد. ثبت کلید در پرامپت‌های بعد و از UI انجام میشود.
- **محاسبه‌ی هزینه** از جدول قیمت خود ما (`llm.connections`). مقدار LiteLLM فقط برای مقایسه است.

## ۶. بودجه، ناهنجاری و رویدادها
- **قبل از هر فراخوانی:** بودجه‌ی همه‌ی سطح‌های مرتبط چک میشود.
  - در ۷۰٪ و ۹۰٪ رویداد هشدار ارسال میشود.
  - در ۱۰۰٪ کارهای P4 رد میشوند (`rejected_budget`). P0 تا P3 انجام میشوند و هشدار میدهند.
- **تشخیص ناهنجاری ساده:** تعداد فراخوانی هر `actor_ref` در ساعت، بیشتر از ۳ برابر میانه‌ی ۷ روز گذشته (با حداقل منطقی) ← رویداد `hq.alerts.llm.anomaly`. **(درس ۲۰ هزار فراخوانی روزانه‌ی TradeYar.)**
- **رویدادهای NATS** (JetStream؛ subject با کد شرکت):
  - `hq.llm.<company>.call.started`
  - `...call.finished`
  - `hq.alerts.budget.<company>`
  - `hq.alerts.llm.anomaly`
  
  **فقط متادیتا، بدون متن.** این‌ها پایه‌ی استریم زنده‌ی بعدی هستند.

## ۷. OpenBao
- KV v2 را فعال کن.
- **policy جدا** برای `llm-router` و `claude-runtime`؛ هر کدام فقط مسیر خودش را میخواند.
- **توکن سرویس محدود** (AppRole یا token با TTL) در فایل‌های `600`.
- **یک توکن ادمین غیر root** برای کارهای بعدی بساز.
- **root token را باطل نکن.** فقط در گزارش پیشنهاد بده تا مالک تصمیم بگیرد.

## ۸. توکن Claude (فقط مالک)
1. **همه‌ی کارهای دیگر را اول تمام کن.** تست‌های این مرحله با **یک CLI جعلی** اجرا میشوند تا سهمیه مصرف نشود.
2. یک اسکریپت `make claude-token` بساز که:
   - توکن را با `read -s` (پنهان) از مالک بگیرد،
   - آن را **مستقیم در OpenBao** بنویسد،
   - **هرگز چاپش نکند،**
   - و runtime را restart کند.
3. **به مالک بگو** در یک ترمینال جدا، با کاربر `Hub`:
   1. `claude setup-token` را اجرا کند.
   2. بعد `make claude-token` را اجرا کند و توکن را paste کند.
4. **بعد از تأیید مالک:** **فقط یک فراخوانی واقعی و خیلی کوچک** انجام بده (مدل Haiku، prompt «فقط بنویس OK»)، و ثبت درست ردیف ledger را با توکن‌ها و `equiv_cost_usd` نشان بده.

## ۹. پایش
- **متریک‌های Prometheus:** تعداد فراخوانی، توکن‌ها، latency، عمق صف، وضعیت breaker و سهمیه، رد شدن به خاطر بودجه.
- **یک داشبورد Grafana** به اسم «Token Treasury — Ops». (UI اصلی خزانه‌ی توکن بعداً در اپ ساخته میشود.)
- **لاگ‌ها ساختاریافته (JSON) و بدون متن prompt و پاسخ.**

## ۱۰. کیفیت و تست
- **ابزارها:** ruff، mypy، pytest، و پوشش تست **حداقل ۸۵٪** برای منطق router (تخصیص، بودجه، صف، breaker).
- **امنیت وابستگی‌ها:** `pip-audit` یا `osv-scanner`. **hadolint** برای Dockerfileها.
- همه به `make check` و CI اضافه شوند.
- **تست‌های اجباری:**
  - حل ارث‌بری تخصیص
  - ترتیب اولویت و جایگاه رزرو
  - breaker با half-open
  - بودجه‌ی ۷۰، ۹۰ و ۱۰۰٪
  - **RLS بین شرکت‌ها**
  - بدون endpoint بی‌احراز
  - **نبود متن prompt در لاگ‌ها**
- **بودجه‌ی حافظه:**
  - سقف دو سرویس جدید در هر دو پروفایل اضافه شود (حساب کن هر پروسه‌ی Claude چقدر میگیرد).
  - **جمع کل سقف‌ها حداکثر ۸۰٪ RAM.** اگر بیشتر شد، **متوقف نشو، فقط گزارش بده** تا مالک درباره‌ی ارتقای سرور تصمیم بگیرد.
- **مستندات:**
  - `services/llm-router/README.md`
  - `services/claude-runtime/README.md`
  - `docs/ops/LLM_LAYER.md` (معماری، جدول‌ها، اولویت‌ها، نحوه‌ی اضافه کردن اتصال)
  - به‌روزرسانی RUNBOOK

## ۱۱. تست قبولی نهایی
- `make up`: همه healthy.
- **`make check`** و **CI** سبز.
- **`ss -tlnp`:** هیچ پورت عمومی جدیدی باز نشده.
- **تست cross-company RLS** پاس شده.
- **یک فراخوانی واقعی کوچک** (بعد از بخش ۸) در ledger با توکن‌ها ثبت شده و رویداد NATS آن دیده شده.
- **`free -h`** و **`docker stats --no-stream`**.

## ۱۲. گزارش پایانی
commitهای کوچک روی `server/p03-llm-layer` و push. گزارش **حداکثر ۲۰ خط:**

```
PROMPT_03 REPORT
- Services: llm-router / claude-runtime healthy? 
- Schema: core.companies (+seed), llm.* tables, RLS cross-company test: ok/fail
- Real call: model / input / output / cache tokens / equiv_cost_usd / ledger row ok?
- Effort support: yes/no (details)
- Breaker + quota + budget tests: ok/fail ; coverage: x%
- make check / CI: ok/fail
- RAM: sum of limits vs 80%; used/free
- Branch / last commit / pushed
- Decisions for owner: (e.g. revoke OpenBao root token? server upgrade?)
- Problems: ...
```

**خط آخر:** «این گزارش را برای Claude سشن مشورت ببر.» بعد **متوقف شو.**
