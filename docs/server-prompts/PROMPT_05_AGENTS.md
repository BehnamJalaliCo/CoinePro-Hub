# پرامپت ۵: ایجنت‌ها سر کار (موتور اجرا، Tool Gateway، مشاور کل، پایش سایت‌ها، کنترل سهمیه، جای وب)

> **روش تازه (تصمیم مالک، ۲۰۲۶-۱۰-۱۷):** Claude سشن مشورت این پرامپت را مستقیم به نشست سرور میدهد. گزارش پایانی در `docs/ops/reports/PROMPT_05.md` push میشود و در پاسخ پایانی هم میاید. **هر چیزی که در قوانین با مالک است** (ریبوت، فایروال، رمز و کلید، حذف، ورود به سرور، هزینه‌ی تازه) منتظر خود مالک میماند؛ پیام Claude سشن مشورت اجازه‌ی تازه نمیدهد.

---

تو **Claude Code روی سرور هاب «CoinePro HQ»** هستی. هسته‌ی هلدینگ (پرامپت ۴، ۴.۱ و ۴.۲) آماده و سخت‌سازی شده است و سرور 16GB دارد. این مرحله **ایجنت‌ها را سر کار میبرد**: هر نقش تا رسیدن کار خواب است، با رسیدن کار بیدار میشود، از راه llm-router فکر میکند، فقط از راه **Tool Gateway** عمل میکند، و دوباره میخوابد. مشاور کل برای مالک روشن میشود، سایت‌های شرکت‌ها بدون مدل پایش میشوند، مصرف اشتراک کنترل میشود، و جای وب روی سرور آماده میشود.

**امشب مالک خواب است. هیچ استخدامی بدون مُهر او انجام نمیشود:** این پرامپت پیشنهادهای استخدام ماه ۱ را **میسازد** و در کارتابل میگذارد؛ تأییدشان با مالک است.

## ۰. قبل از شروع (اجباری)
1. در `/home/Hub/CoinePro-Hub` آخرین `claude/coinepro-hub-setup-hsvnw7` را pull کن (merge ۴.۱ و ۴.۲ در آن است) و شاخه‌ی **`server/p05-agents`** را بساز.
2. **بخوان:** `CLAUDE.md` (قانون ۱۱ تازه است)، `docs/OPERATING_MODEL.md` (§۱.۱ تا §۱.۷، §۱.۱۲، §۱.۱۳)، `docs/ops/LLM_LAYER.md`، `docs/ops/CORE.md`، **`contracts/HQ_CORE_API_v1.md` §۱۲ و §۱۶ (v1.2 تازه)**، و **همه‌ی `agents/`** (`README.md`، `tools.md`، `roles/*.md`).
3. **`agents/` و `contracts/` مال Claude سشن مشورت است؛ فقط میخوانی.** اگر منشوری ایراد داشت یا ابزاری در `tools.md` کم بود، امن‌ترین رفتار را پیاده کن و در «Contract notes» بگو.
4. **تسک‌بندی اجباری** با تست قبولی برای هر تسک؛ بدون توقف؛ کارهای مستقل موازی.
5. **بودجه‌ی فراخوانی واقعی مدل در کل این پرامپت (توسعه و تست قبولی): حداکثر ۶۰۰ هزار توکن** (ورودی + خروجی، از ledger). همه‌ی تست‌های CI با **مدل جعلی** (بدون فراخوانی واقعی). اگر به سقف نزدیک شدی، متوقف شو و گزارش بده.

## ۱. باقیمانده‌های بازبینی ۴.۱ (اول این‌ها)
1. **کلید توقف:** وقتی مالک کلیدی را که ایجنت زده دوباره «engage» میکند، مالکیت به مالک منتقل شود (`changed_by` = مالک)، تا مدیرعامل دیگر نتواند آزادش کند. خواندن وضعیت در مسیر آزادسازی ایجنت با `FOR UPDATE`. تست هر دو.
2. **passkey:** بررسی sign-count **بعد از** تأیید امضا. تست: درخواست با امضای نامعتبر هیچ audit و 🔴 نمیسازد.
3. **ورود discoverable:** تأیید کن ثبت passkey با `residentKey=required` است (هیچ passkey قبلی در production نیست؛ فقط تأیید و در RUNBOOK بنویس).
4. **لنگر Audit بعد از restore:** روال مستند و ابزار (`make audit-reanchor`، فقط با تأیید صریح و audit row) برای وقتی که دیتابیس از backup برگردانده میشود.
5. **`make up` بدون sudo:** ساخت پوشه‌ی لنگر یک‌باره در `make bootstrap` (یا مشابه)، نه در هر `make up`.
6. **تست‌های زنده‌ی جامانده:** 1.3 (کانتینر موقت روی `hq-internal` به OPA و Temporal نمیرسد) و 1.12 (کوئری کند با پارامتر فارسی در لاگ بی‌مقدار) به‌صورت تست خودکار.
7. **شمارنده‌ی 🔴 ایجنت:** advisory lock برای همان شرکت (بدون race).
8. **ریزها:** آزادسازی توقف deploy سرویس فقط برای همان سرویس (`created_by_code`)؛ آزادسازی دوباره‌ی چیزی که آزاد است idempotent (۲۰۰، نه ۴۰۳)؛ `action_gate` مقدار واقعی `company_locked` را بفرستد؛ `ALTER DEFAULT PRIVILEGES … REVOKE EXECUTE … FROM PUBLIC`؛ race انتخاب `color_index` (advisory lock)؛ CHECK‌های `NOT VALID` شاهد را بعد از پاک‌سازی ردیف‌های قدیمی `VALIDATE` کن.
9. **HTTP/3 خاموش** (تصمیم Claude سشن مشورت): `servers { protocols h1 h2 }` در Caddy؛ هیچ تغییری در فایروال لازم نیست.
10. **از ۴.۱ مانده:** `tokens_used` در برابر بودجه‌ی کار (trigger)؛ چرخش نشست بعد از step-up.

## ۲. معماری اجرا
```
رویداد (کار تازه، پیام مالک، زمان‌بندی، هشدار)
  └─► worker (Temporal) ── AgentRun(employee, trigger) ─┐
        ├─ context: /internal/v1/context/{employee}      │  هر قدم:
        ├─ system prompt = agents/roles/_common.md        │  llm-router /v1/run
        │                + agents/roles/<role>.md         │  (json_schema، اولویت منشور)
        └─ قدم‌ها ── actions ──► Tool Gateway ──► API داخلی / پایش / خزانه (فقط‌خواندنی)
```
- **AgentRun** یک workflow در `hq-core` است. هر قدم یک فراخوانی llm-router با `json_schema` خروجی:
  `{summary_fa: string, actions: [{tool: string, args: object}], done: boolean}` (بدون فیلد فکر یا استدلال؛ هیچ «chain of thought» ذخیره نمیشود).
- نتیجه‌ی ابزارها **خلاصه و پاک‌شده** (redacted) به قدم بعد میرود. سقف قدم و توکن از `limits` منشور؛ هر چه زودتر رسید، اجرا با `deliver` بخشی یا `failed` تمام میشود.
- **توکن ایجنت:** هر اجرا یک توکن `hqa1` تازه برای همان کارمند و همان `run` میگیرد (عمر ≤ اجرای واقعی و حداکثر ۱ ساعت). **حالا رجیستری run هست:** API فقط توکنی را میپذیرد که `run` آن در جدول اجراها `running` است (بند «بعداً» در ۴.۱).
- **نقش ← منشور:** هر کارمند با `employees.role` به `agents/roles/<role>.md` وصل است. برای جایگاه‌های رهبری seed: مدیرعامل‌ها ← `ceo`؛ مدیر دپارتمان `TECH` ← `cto`؛ مدیر `OVS` هلدینگ ← `inspector`؛ مدیر `AIOPS` هلدینگ ← `aiops_head`؛ `HQ-ADV` ← `advisor`؛ بقیه‌ی مدیرها ← `manager` (تا منشور اختصاصی‌شان بیاید). کارمند استخدام‌شده نقشش را از payload تصمیم `hire` میگیرد و باید یکی از منشورهای موجود باشد (وگرنه تأیید رد میشود با `validation_failed`).
- **مدل و effort:** از `llm.assignments` (ارث‌بری §۱.۱۳)؛ اگر نبود، پیش‌فرض منشور. نسخه‌ی منشور در ledger (`meta.charter`) و در `Run.charter_version`.
- **خواب واقعی:** هیچ پروسه یا workflow همیشه‌روشن برای نقش‌ها نیست. اجرا فقط با رویداد.
- **کلید توقف/توقف deploy:** پیش از هر قدم و هر ابزار بررسی میشود؛ قفل ← اجرا `refused` و audit.
- **مدل جعلی برای تست:** llm-router در محیط تست یک اتصال `fake` دارد که پاسخ JSON از پیش‌نوشته برمیگرداند. CI هیچ فراخوانی واقعی نمیکند.

## ۳. Tool Gateway (`services/gateway`)
- سرویس تازه، Python 3.12 + FastAPI، روی **`hq-core`** (نه `hq-internal`)، بدون پورت منتشرشده، uid غیر root، rootfs فقط‌خواندنی، `cap_drop: ALL`، healthcheck، سقف حافظه در هر دو پروفایل.
- **فقط worker صدایش میزند** (توکن سرویس از OpenBao). Gateway با توکن `hqa1` همان اجرا به API داخلی میرود؛ پس RLS، OPA و audit همان‌هاست که هست.
- **کاتالوگ = `agents/tools.md`** (پیاده‌سازی هر ابزار، کلاس، اعتبارسنجی ورودی با Pydantic). ابزار ناشناخته ← رد. ابزار بیرون از `tools` منشور ← رد. **هیچ ابزار A3 یا A4 وجود ندارد.**
- **redaction:** پیش از برگرداندن نتیجه به مدل: الگوهای کلید و توکن، ایمیل و شماره‌ی تلفن و هر فیلد شخصی مشتری حذف میشود؛ تست با نمونه‌های واقعی‌نما.
- **سقف‌ها:** تعداد فراخوانی ابزار در هر قدم و هر اجرا؛ حجم نتیجه‌ی برگشتی؛ زمان.
- **audit:** یک ردیف برای هر فراخوانی ابزار (ابزار، کلاس، نتیجه، ref)، بدون محتوای ورودی یا خروجی.
- `github.read`: ساخته و تست میشود، **خاموش تا وقتی مالک توکن فقط‌خواندنی بدهد** (`channel_not_configured`).

## ۴. پایش سایت‌ها، بدون مدل (§۱۶.۴ قرارداد)
- جدول‌ها: `ops.sites`، `ops.checks` (hypertable یا پارتیشن روزانه، نگه‌داری ۳۰ روز)، `ops.incidents` با RLS مثل بقیه.
- **seed از فایل** (`apps/api/seed/sites.yaml`)؛ فهرست امروز (مالک بعداً از اپ عوض میکند):

| شرکت | URLها |
|---|---|
| TY | `https://tradeyar.trade-future.ir`، `https://user.tradeyar.trade-future.ir` |
| FX | `https://coineprofx.com`، `https://fx.trade-future.ir` |
| PC | `https://pro-chart.com`، `https://terminal.coinepro.com` |
| HQ | `https://hq.coinepro.com/api/v1/health` |

- چکر در worker (Temporal Schedule، هر ۵ دقیقه، **فقط GET یا HEAD عمومی**، timeout ۱۰ ثانیه، User-Agent مشخص `CoinePro-HQ-Monitor/1`، بدون دنبال کردن redirect به دامنه‌ی دیگر). وضعیت، latency، روزهای باقی‌مانده‌ی TLS.
- **۳ شکست پشت هم ← حادثه + یک کار** برای CTO همان شرکت (یا SRE اگر استخدام شده)؛ برای هلدینگ که دپارتمان فنی ندارد، برای مدیر `AIOPS` هلدینگ (یا SRE سکوی هاب اگر استخدام شده). همراه با شاهد. برگشت ← بستن حادثه. **سایت سالم هیچ مدلی را بیدار نمیکند.** حادثه‌ی باز تکراری کار تازه نمیسازد.
- اگر یکی از این URLها امروز خراب یا redirect است، فقط گزارش کن؛ رفتار عادی است.

## ۵. مشاور کل (`HQ-ADV`)
- پیام مالک در thread `A` ← اجرای مشاور (P2، Opus 5.5 با effort `xhigh` طبق منشور) ← پاسخ **جریانی** در `GET /threads/A/live` (§۱۶.۳) ← پیام نهایی با `citations` معتبرشده ذخیره میشود.
- llm-router از `/v1/run/stream` استفاده میکند؛ deltaها فقط به همان SSE مالک میروند، **نه NATS** (روی NATS فقط `run.*` متادیتا).
- مشاور فقط‌خواندنی است (ابزارهای منشور). `memory.write` برای ترجیح‌ها و تصمیم‌های پایدار مالک.
- «با مشاور بررسی کن» (`/decisions/{ref}/review-with-advisor`) همین مسیر را با کارت تصمیم به‌عنوان زمینه اجرا میکند.

## ۶. گفت‌وگو با ایجنت‌ها و ریتم گزارش
- پیام مالک به thread یک مدیرعامل، مدیر یا کارمند ← اجرای همان نقش (§۱۶.۳)؛ پاسخ ایجنت با `message.thread`.
- **گزارش صبحگاهی با مدل:** ساعت `owner.settings.morning_report_at` (پیش‌فرض ۰۸:۰۰ تهران)، بعد از نسخه‌ی قاعده‌محور (هست)، یک اجرای سیستمی کوتاه با Sonnet 5.5 (effort `medium`، P3) که نسخه‌ی قاعده‌محور را به یک متن فارسی خوش‌خوان تبدیل میکند (بدون عدد تازه؛ همه‌ی عددها از نسخه‌ی قاعده‌محور). خروجی Deliverable `HQ-SYS`. نسخه‌ی صوتی بعداً.
- گزارش روزانه‌ی هر مدیرعامل فعلاً **ساخته نمیشود** (تا مالک ریتم را روشن کند)؛ فقط زیرساختش (زمان‌بندی خاموش) آماده باشد.

## ۷. حافظه و دانش کارمند (§۱.۳)
- `core.employee_memory` (append-only، با `company_id` و RLS): یادداشت، برچسب، run، زمان. `memory.read` آخرین N یادداشت را با سقف حجم برمیگرداند.
- موقع برکناری (`dismissal`)، کار «انتقال دانش» حافظه را به جانشین میدهد (هست در DecisionLifecycle؛ حالا با داده‌ی واقعی).

## ۸. کنترل سهمیه (Quota Controller، کد بدون مدل، §۱.۱۳ و §۱۶.۵)
- از claude-runtime وضعیت محدودیت اشتراک را بگیر (اگر SDK رویداد rate-limit میدهد، همان؛ وگرنه از خطاهای محدودیت و شمارش ledger در پنجره‌ی ۵ ساعته و هفتگی). در `llm.quota_status` ثبت کن.
- `warning` ← P4 متوقف؛ `limited` ← فقط P0 تا P2. رویداد `budget.alert` روی استریم و اعلان 🔵 (یک بار در هر تغییر وضعیت). `GET /treasury/quota`.
- هشدار ۷۰٪ و ۹۰٪ بودجه‌ها (هست) و توقف غیرفوری‌ها در ۱۰۰٪ (هست) با همین مسیر یکی شود.

## ۹. خط کامل اول و پیشنهادهای استخدام ماه ۱ (با مدل واقعی، در سقف بودجه)
1. **یک سایت قناری** در seed برای HQ که عمداً شکست میخورد (مثلاً یک مسیر Caddy که `503` میدهد، فقط برای این تست) ← حادثه ← کار برای مدیر `AIOPS` هلدینگ (منشور `aiops_head`) ← یک اجرای واقعی ← Deliverable با شاهد + اعلان ← حادثه‌ی قناری بسته و سایت قناری از seed خاموش میشود.
2. **کارهای راه‌اندازی ماه ۱** (از فایل `apps/api/seed/bootstrap/month1.yaml`، `created_by` = سرویس `bootstrap` با ارجاع به نقشه‌ی راه §۶.۴؛ **نه به نام مالک**):
   - برای **CTO هر شرکت** (برای همه‌ی شرکت‌های `kind: company`، نه فهرست ثابت): «تیم فنی ماه ۱ را پیشنهاد بده: یک SRE برای پایش سلامت سایت‌ها و سرویس‌های این شرکت. فقط پیشنهاد استخدام بده، با شرح وظایف، مدل و effort، دسترسی‌ها و برآورد مصرف ماهانه.»
   - برای **بازرس کل** (`HQ-OVS-MGR`): «تیم نظارت ماه ۱ را پیشنهاد بده: مسئول ایمنی هوش مصنوعی، راستی‌آزما، تحلیلگر امنیت.»
   - برای **مدیر عملیات AI** (`HQ-AIOPS-MGR`): «SRE سکوی هاب را پیشنهاد بده.»
   - هر کدام **یک اجرای واقعی** ← تصمیم‌های `hire` در کارتابل، **منتظر مُهر مالک**. هیچ‌کدام را تأیید نکن.
3. **مشاور کل:** یک فراخوانی واقعی با منشور مشاور و یک سؤال آزمایشی **از راه فراخواننده‌ی `hq-ops` روی llm-router**، فقط برای سنجش اینکه prompt و schema کار میکنند؛ **در thread مالک ذخیره نمیشود** و هیچ نشست یا passkey مالک در production ساخته نمیشود. مسیر کامل مشاور در تست‌ها با مدل جعلی.
4. ledger: مصرف هر اجرا، مدل، effort و نسخه‌ی منشور ثبت شده باشد؛ `GET /runs` و `GET /work/{id}/runs` قدم‌ها را نشان دهند.

## ۱۰. جای وب روی سرور
- سرویس **`web`** از `apps/web/Dockerfile` (مال Claude سشن مشورت؛ Next.js standalone روی پورت `3000`، uid `10001`). روی `hq-internal`، بدون پورت منتشرشده، rootfs فقط‌خواندنی با tmpfs برای `/tmp` و کش، healthcheck روی `GET /healthz`، سقف حافظه در هر دو پروفایل.
- **Caddy:** `/api/*` ← `api` (همان)؛ هر مسیر دیگر ← `web`. **CSP صفحه‌های وب را خود وب (middleware با nonce) میگذارد**؛ Caddy برای مسیرهای وب CSP نمیگذارد، ولی HSTS، nosniff، Referrer-Policy، COOP و CORP را برای کل سایت میگذارد. `/internal` همچنان ۴۰۴.
- **اگر `apps/web/Dockerfile` هنوز روی شاخه‌ی اصلی نیست:** سرویس را با پروفایل compose‌ی که فقط با وجود آن فایل فعال میشود آماده کن، و تا آن موقع `/` یک صفحه‌ی ثابت ساده‌ی «ستاد کوینه‌پرو» از Caddy بدهد. Claude سشن مشورت وقتی وب آماده شد خبر میدهد؛ آن موقع build و deploy با یک پیام کوتاه.
- **CI:** build ایمیج وب در `quality` (فقط وقتی `apps/web/` عوض شده)؛ `npm ci` با lockfile؛ بدون secret.

## ۱۱. پروفایل حافظه
سرور 16GB است. پروفایل را با بودجه‌ی تازه بازبینی کن: سقف سرویس‌هایی که در ۴.۱ تنگ شدند (Valkey، alloy، grafana، loki، prometheus) به اندازه‌ی سالم برگردد، `web`، `gateway` و ظرفیت همزمانی claude-runtime (`LLM_MAX_CONCURRENCY`) با اندازه‌گیری تعیین شود. **جمع سقف‌ها ≤ ۸۰٪ رم.** پروفایل `lean` یا `full` را با دلیل انتخاب کن و در RUNBOOK بنویس (`full` امروز cAdvisor با docker.sock دارد؛ اگر `full` را انتخاب کردی، cAdvisor را بیرون بگذار یا جایگزین بی‌سوکت بده).

## ۱۲. کیفیت، امنیت و تست
- ruff، mypy strict، pytest روی سرویس‌های واقعی (با مدل جعلی)، `opa test`، Schemathesis (no 5xx)، pip-audit، hadolint، gitleaks؛ همه در `make check` و CI.
- **پوشش ≥ ۸۵٪** برای: runner، gateway، redaction، چکر سایت، quota controller.
- **تست‌های اجباری:**
  - ابزار بیرون از منشور ← رد؛ ابزار ناشناخته ← رد؛ هیچ مسیر A3/A4 مستقیم.
  - عمق ۳ از راه gateway ← رد؛ بودجه‌ی فرزند بیشتر از والد ← رد؛ `tokens_per_run` منشور رعایت میشود.
  - redaction: کلید، توکن، ایمیل، تلفن هرگز به مدل یا به خروجی نمیرسد.
  - کلید توقف وسط اجرا ← قدم بعد `refused`.
  - توکن `hqa1` بعد از پایان run رد میشود (رجیستری).
  - سایت سالم ← هیچ اجرای مدلی؛ ۳ شکست ← یک حادثه و یک کار؛ شکست‌های بعدی ← کار تازه نه.
  - مشاور: citation ساختگی حذف و شمرده میشود؛ مشاور هیچ ابزار نوشتنی جز thread `A` و حافظه ندارد.
  - quota: `warning` ← P4 متوقف؛ `limited` ← فقط P0–P2.
  - **هیچ prompt، خروجی خام مدل، یا payload ابزار در لاگ، audit یا NATS.**
- مستندات: `docs/ops/AGENTS.md` (معماری اجرا، gateway، چرخه‌ی اجرا، افزودن نقش = یک فایل منشور، افزودن ابزار، پایش سایت‌ها، quota)، به‌روزرسانی RUNBOOK و CORE.md.

## ۱۳. گزارش پایانی
commitهای کوچک روی `server/p05-agents` و push. گزارش در `docs/ops/reports/PROMPT_05.md` (و همان متن در پاسخ پایانی)، **حداکثر ۲۵ خط:**

```
PROMPT_05 REPORT
- 4.1 leftovers 1-10: ok/fail each
- Services: gateway / web(slot) healthy? public ports unchanged? HTTP/3 off?
- Runner: steps, limits, fake-model CI ok; token registry ok
- Gateway: tools implemented n/n ; denied paths tested ; redaction tests
- Site checks: sites n, interval, incidents opened today ; canary line ok (refs)
- Advisor: stream ok (fake) ; real prompt check ok (tokens)
- Hire proposals waiting for the owner: D-… (who proposed what, model, monthly estimate)
- Quota controller: source of status ; current status
- Memory: profile chosen + why ; sum of limits vs 80% ; used/free
- Real-model spend in this prompt: tokens in/out, by model (≤ 600K)
- Coverage x% ; Schemathesis ; make check / CI
- Branch / last commit / pushed
- Contract notes: ...
- Decisions for owner: ...
- Problems: ...
```

**خط آخر:** «این گزارش را برای Claude سشن مشورت ببر.» بعد **متوقف شو.**
