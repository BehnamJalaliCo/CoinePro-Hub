# هسته‌ی هلدینگ (پرامپت ۴): API، worker، سیاست‌ها و داده‌ها

> **مرجع:** قرارداد `contracts/HQ_CORE_API_v1.md` و `docs/OPERATING_MODEL.md`. هر endpoint، فیلد و کد خطا از قرارداد است. تفاوت‌ها در گزارش پرامپت ۴ زیر «Contract notes» آمده‌اند.
> **کد:** `apps/api/` (یک پکیج پایتون `hq_api` با دو entrypoint: `python -m hq_api` و `python -m hq_api.worker`).

## ۱. معماری

```
 مرورگر / اندروید ──HTTPS──► Caddy ──(/api/* فقط وقتی دامنه هست)──► api :8000
                                │    (/internal/* هرگز)                │
                                └──(هر مسیر دیگر)──► web :3000 (پروفایل web)
 ایجنت‌ها: worker ──► gateway (hq-agent) ──► /internal/v1 ──────────────┤
                                                                      ├──► Postgres (RLS FORCE)
                                                                      ├──► OPA (سیاست‌ها، fail-closed)
                                                                      ├──► NATS JetStream HQ_CORE ──► SSE /api/v1/stream
                                                                      └──► Temporal (best effort)
 worker (Temporal، task queue hq-core) ──► Postgres، NATS (پل hq.llm.* و hq.alerts.* به HQ_CORE)
```

| سرویس | نقش | کاربر و فایل‌سیستم | اسرار |
|---|---|---|---|
| `api-migrate` (یک‌باره) | Alembic (جدول نسخه‌ی `alembic_version_api`) + seed از YAML، با نقش مالک `hq` | uid 10001؛ rootfs فقط‌خواندنی | پسورد `hq` از `.env` |
| `api` | `/api/v1` و `/internal/v1` | uid 10001؛ rootfs فقط‌خواندنی؛ tmpfs ۳۲MB؛ `cap_drop: ALL`؛ volume ‏`hq-files` | AppRole ‏`hq-api` |
| `worker` | گردش‌کارهای Temporal و پل NATS | مثل api | AppRole ‏`hq-worker` |
| `opa` | سیاست‌های `infra/opa/policy` | uid 1000 (ایمیج distroless)؛ rootfs فقط‌خواندنی | — |
| `gateway` (پرامپت ۵) | Tool Gateway: هر اقدام ایجنت، با توکن `hqa1` همان اجرا (`docs/ops/AGENTS.md`) | uid 10001؛ rootfs فقط‌خواندنی؛ `cap_drop: ALL`؛ **فقط `hq-agent`** | فقط SHA-256 توکن worker |
| `web` (پرامپت ۵) | پنل Next.js (`apps/web`، مال Claude سشن مشورت) | uid 10001؛ rootfs فقط‌خواندنی؛ tmpfs برای `/tmp` و کش | — |

- **شبکه‌ها (۴.۱):**
  - `api` و `worker` روی `hq-internal`، `hq-core` و `hq-agent` هستند.
  - `temporal`، `temporal-namespace` و `temporal-ui` **فقط** روی `hq-core` (`172.30.2.0/24`) هستند. Postgres و Prometheus هم به آن وصل‌اند: Temporal به Postgres نیاز دارد و Prometheus متریک Temporal را میخواند.
  - `opa` و `gateway` **فقط** روی `hq-agent` (`172.30.3.0/24`، internal؛ پرامپت ۵.۱ §۲.۹) هستند، با worker و api. gateway به Temporal و Postgres نمیرسد.
  - هیچ کانتینر دیگری روی `hq-internal` به OPA، gateway یا پورت 7233 ‏Temporal نمیرسد. `compose-rules` و `make verify-live` این را بررسی میکنند.
  - هیچ‌کدام پورت عمومی ندارند؛ فقط Caddy روی 80/443 است.
- نقش‌های دیتابیس: `hq_api` و `hq_worker`، هر دو با کمترین دسترسی (`infra/postgres/provision.sh`؛ grantها در migrationها). **هیچ نقشی حق DELETE روی داده‌ی کسب‌وکار ندارد.**
- OpenBao: policy‌های `hq-api` (خواندن `kv/hq-api/*`؛ کلید اتصال‌ها فقط **نوشتنی**) و `hq-worker` (Web Push، کانال‌ها، `kv/hq-api/config` و از پرامپت ۵ `kv/hq-agents/runtime`: توکن فراخواننده‌ی `hq-agents` روی llm-router و توکن gateway). `make bootstrap` و `make up` آن‌ها را میسازند (`infra/openbao/provision.sh`).

## ۲. لبه و ورود

- **بدون دامنه:** `/api/*` در Caddy با ۴۰۴ بسته است و endpointهای ورود جواب `503 origin_not_configured` میدهند. این خطا نیست؛ ورود فقط با دامنه و HTTPS معنا دارد.
- **با دامنه:** کافی است در `infra/compose/.env` یک خط بگذاری: `HQ_SITE_ADDRESS=hq.example.com` و `make up`. `infra/compose/hq.sh` از روی آن `HQ_API_EDGE=on`، ‏`HQ_PUBLIC_ORIGIN=https://<دامنه>` و `HQ_WEBAUTHN_RP_ID=<دامنه>` را میسازد. Caddy گواهی میگیرد و `/api/*` را با SSE (`flush_interval -1`)، سقف بدنه‌ی ۲MB و هدرهای امنیتی (HSTS، CSP، ...) به `api` میدهد.
- **`/internal/*` هرگز از لبه رد نمیشود.**
- **ثبت کلید عبور (مالک):** `make owner-enroll` در ترمینال خود مالک یک لینک یک‌بارمصرف ۱۵ دقیقه‌ای چاپ میکند (`<origin>/enroll#token=...`). این لینک **هیچ‌جا ذخیره یا لاگ نمیشود** و همین دستور مسیر بازیابی هم هست. دو کلید عبور (گوشی و کامپیوتر) پیشنهاد میشود.
- **نشست‌ها:** opaque، ذخیره‌شده به‌صورت SHA-256، تمدید لغزنده‌ی ۳۰ روز و سقف مطلق ۹۰ روز. وب: کوکی `hq_session` (`HttpOnly; Secure; SameSite=Strict; Path=/api`) + `X-HQ-Client: web` و Origin درست (وگرنه `403 csrf_rejected`). اندروید: `Authorization: Bearer`.
- **step-up 🔏:** کلید عبور دوباره با UV. توکن یک‌بارمصرف ۱۲۰ ثانیه‌ای، بسته به نشست، action و target، در هدر `X-Step-Up`. **(پرامپت ۵)** بعد از step-up موفق، توکن کوکی نشست وب عوض میشود (نشست Bearer اپ دست نمیخورد):

| action | target | کجا |
|---|---|---|
| `decision.approve` | `D-…` | تأیید A3، `hire`، `dismissal`، `budget_change` |
| `employee.dismiss` | کد کارمند | برکناری |
| `company.create` / `company.archive` | کد شرکت | ساخت شرکت / بایگانی |
| `department.create` | کد شرکت | دپارتمان جدید |
| `kill_switch.release` | `holding` یا `company:XX` | **آزاد کردن** کلید توقف (روشن کردنش step-up نمیخواهد) |
| `sites.update` (پرامپت ۵) | SHA-256 (hex) بایت‌های بدنه | `PUT /api/v1/ops/sites`، فهرست سایت‌های پایش |
| `connection.update` / `connection.secret` | id اتصال | تغییر اتصال / ثبت کلید |
| `assignments.update` / `budgets.update` | SHA-256 (hex) **همان بایت‌های بدنه‌ی درخواست** (۴.۱) | تخصیص مدل / بودجه |
| `device.revoke` / `passkey.register` | id / `self` | دستگاه‌ها |

## ۳. داده‌ها (دیتابیس `hq`)

| schema | جدول‌ها |
|---|---|
| `core` | `companies` (کامل‌شده)، `departments`، `employees` (از پرامپت ۵ با `role` = منشور)، `employee_code_seq`، `employee_scores`، `employee_memory` (append-only، پرامپت ۵)، `counters`، `outbox`، `idempotency_keys` |
| `work` | `work`، `work_events`، `escrows`، `schedules` |
| `cartable` | `decisions`، `deliverables`، `ratings`، `resolutions` |
| `msg` | `threads`، `messages` |
| `notify` | `notifications`، `settings`، `web_push_subscriptions`، `fcm_tokens`، `digest_batches` |
| `auth` | `passkeys`، `sessions`، `challenges`، `step_ups`، `enrolment_tokens` |
| `owner` | `presence`، `settings`، `interactions` |
| `audit` | `entries`، `chain_head` |
| `control` | `kill_switches`، `deploy_freezes` |
| `agents` (پرامپت ۵) | `runs` (رجیستری اجراها، ماشین حالت با trigger)، `steps` (append-only: خلاصه، اقدام‌ها، مصرف؛ بدون prompt یا خروجی خام) |
| `ops` (پرامپت ۵) | `sites`، `checks` (پارتیشن روزانه، ۳۰ روز)، `incidents` (`I-0001`)، `hub_health` |
| `files` | `files` (محتوا روی volume ‏`hq-files` از راه interface ‏`Storage`؛ بعداً S3) |

**قاعده‌هایی که در خود دیتابیس اجرا میشوند** (trigger و constraint؛ با SQLSTATE کلاس `HQ` که API به کد قرارداد تبدیل میکند):
1. **عمق ارجاع ≤ ۲:** عمق فرزند همیشه عمق والد + ۱ است (`HQD01` ← `409 delegation_depth_exceeded`).
2. **بودجه:** بودجه‌ی فرزند ≤ باقیمانده‌ی والد و جمع فرزندها ≤ والد. فرزند بی‌بودجه باقیمانده را به ارث میبرد (`HQB01` ← `409 budget_exceeded`).
   - **(پرامپت ۵)** `tokens_used` و `usd_used` کار هرگز کم نمیشوند (`HQV01`). وقتی بودجه تمام شده، دیگر بالا نمیروند (`HQB01`).
   - موتور اجرا سقف توکن هر اجرا را از باقی‌مانده‌ی بودجه میگیرد، پس مصرف واقعی هیچ‌وقت از بودجه رد نمیشود.
3. **`done` فقط با خروجی یا شاهد** (`HQE01` ← `422 evidence_required`).
4. **append-only:** `audit.entries`، `msg.messages`، `cartable.resolutions`، `cartable.ratings`، `cartable.deliverables`، `owner.interactions`، `work.work_events` و `files.files`. UPDATE، DELETE و TRUNCATE برای همه رد میشود، حتی مالک دیتابیس.
5. **کدهای انسانی یکتا و ثابت:** `TY-TECH-01`، `D-000123`، `O-000456`، `W-000789`، `M-0001`، `A-0142`. شماره‌ی کارمند برای هر شرکت و دپارتمان **فقط رو به جلو** میرود و بعد از برکناری دوباره داده نمیشود. مصوبه‌ها یک دنباله‌ی **بی‌فاصله** برای کل هلدینگ دارند.
6. **تصمیم تصمیم‌گرفته‌شده مُهر میشود** (`HQS01` ← `409 decision_not_pending`؛ ۴.۱): `status`، `decided_*`، `seal_*`، `note`، `reason_code` و `amendments` فقط یک بار نوشته میشوند (`HQI01`).
7. **(۴.۱) کلید خارجی ترکیبی `(company_id, id)`** برای همه‌ی ردیف‌های فرزند (کار، رویداد کار، پاکت، زمان‌بندی، تصمیم، خروجی، امتیاز، مصوبه، پیام، thread، کارمند، تاریخچه‌ی امتیاز). فرزند هرگز در شرکتی جز شرکت والدش نیست.
8. **(۴.۱) پیام:** `seq`، `ref` و `company_id` را trigger از روی thread میسازد و مقدار ورودی نادیده گرفته میشود.
9. **(۴.۱) تاریخچه‌ی امتیاز** (`core.employee_scores`): ماه‌های گذشته هیچ تغییری نمیپذیرند. ماه جاری فقط ستون‌های امتیاز را تغییر میدهد. کلیدها ثابت‌اند و DELETE و TRUNCATE برای همه رد میشوند.
10. **(۴.۱) `llm.assignments`:** نقش api مستقیم نمینویسد. فقط از راه `llm.put_assignment()` (SECURITY DEFINER) مینویسد، که دامنه را در شرکت‌های مجاز فراخواننده نگه میدارد.
11. **(۴.۱) شاهد `done`** باید `kind` و `ref` غیرخالی داشته باشد (`[{}]` کافی نیست). کدهای انسانی فقط از sequence یا تابع ساخته میشوند (روی `core.counters` حق UPDATE نیست). هیچ تابعی برای `PUBLIC` اجراشدنی نیست.

**RLS:** روی **همه‌ی** جدول‌های دارای `company_id`، با FORCE و همان قرارداد `llm.*`: هر تراکنش با `SET LOCAL app.company_ids` (uuid[]) شروع میشود. مالک همه‌ی شرکت‌ها را میبیند و ایجنت فقط شرکت خودش را. ردیف‌های سطح هلدینگ `company_id` خود هلدینگ (`HQ`) را دارند، هرگز NULL.

**شکل policy (پرامپت ۵، migrationهای api ‏0009 و llm-router ‏0008):** `company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])`. یعنی دامنه‌ی شرکت‌ها **یک بار در هر کوئری** حساب میشود (InitPlan)، نه برای هر ردیف، و ایندکس `company_id` به کار میرود. شکل قدیم (`ANY (core.allowed_company_ids())`) هزینه‌ی ردیف × شرکت داشت. روی دیتابیس تست با ۳۳۰ شرکت، خلاصه‌ی صندوق مالک از 778ms به 46ms رسید. **هر جدول تازه با همین شکل ساخته شود.**

**Audit زنجیره‌ای:** `hash = sha256(prev_hash || canonical_json(entry))`، که trigger (`audit.chain`، SECURITY DEFINER) زیر قفل ردیف سر زنجیره حساب میکند. `at` همیشه ساعت دیتابیس است (۴.۱). ردیف Audit آخرین دستور هر تراکنش است تا قفل سر زنجیره کوتاه بماند.

**لنگر زنجیره بیرون از Postgres (۴.۱):**
- کار شبانه بعد از بررسی سالم، `seq` و `hash` سر زنجیره را به فایل append-only ‏`/home/Hub/backups/audit-anchors/audit-chain.jsonl` اضافه میکند. این فایل جزو مجموعه‌ی backup است.
- `GET /api/v1/audit/verify` سر زنجیره را با آخرین لنگر هم مقایسه میکند (`anchor: ok | mismatch | none`). پس بازنویسی کامل زنجیره، حتی همراه با سر آن، پیدا میشود. `audit.verify_chain()` کل زنجیره را دوباره حساب میکند (`GET /api/v1/audit/verify` و گردش‌کار شبانه). نقش API روی این جدول فقط INSERT و SELECT دارد.

**جستجوی فارسی:** `core.fa_normalize()` نسخه‌ی ۲ (۴.۱): ي/ى→ی، ك→ک، ۀ/ة→ه، أ/إ/آ/ٱ→ا، ؤ→و، ارقام فارسی و عربی→لاتین، **نیم‌فاصله→فاصله**، و حذف ZWJ، کشیده و اعراب. بعد FTS با پیکربندی `simple` + `pg_trgm`. `%` و `_` ورودی کاربر در LIKE با `core.like_escape()` بی‌اثر میشوند.

**seed از فایل:** `apps/api/seed/templates/standard.yaml` (۸ دپارتمان + مدیرعامل + ۸ مدیر) و `holding.yaml` (`OVS` با بازرس کل، `AIOPS`، مشاور کل `HQ-ADV` و `HQ-SYS` که نویسنده‌ی قاعده‌محور گزارش‌هاست). همه‌ی جایگاه‌ها با `activity = sleeping` ساخته میشوند. **هیچ کارمند شماره‌دار seed نمیشود.** seed هر بار اجرا میشود، فقط چیزهای جاافتاده را اضافه میکند و ویرایش‌های بعدی را بازنویسی نمیکند.

## ۴. افزودن یک شرکت (یک رکورد + یک قالب)

- **از اپ:** `POST /api/v1/companies` با 🔏 `company.create`. دپارتمان‌ها، جایگاه‌های رهبری، threadها و ردیف کلید توقف در یک تراکنش از روی قالب ساخته میشوند.
- **رنگ (۴.۱):** `color_index` یک جایگاه 1..8 در پالت نمودار v2 است، یا null. هر جایگاه یکتاست و شرکت تازه اولین جایگاه خالی را میگیرد. امروز PC=1، FX=2، TY=3 و هلدینگ بدون رنگ است.
- **از فایل:** یک خط در `services/llm-router/seed/companies.yaml` (کد، نام، `kind: company`) و یک خط در `apps/api/seed/companies.yaml` (`name_fa`، `color_index`، `template`)، سپس `make up`.
- **هیچ کد یا زیرساختی عوض نمیشود.** قالب جدید هم فقط یک فایل YAML در `apps/api/seed/templates/` است.

## ۵. سیاست‌ها (OPA)

`infra/opa/policy/` (داده‌ها در `data.json`: دسته‌های حادثه، دپارتمان HR، مجوزهای A2 هر نقش)، پکیج‌های `hq.decisions` (چه کسی چه تصمیمی را تأیید میکند)، `hq.actions` (A0 تا A4؛ **A4 برای هر غیرمالک همیشه رد**) و `hq.internal` (هر ایجنت فقط در شرکت، دپارتمان و نقش خودش؛ ارجاع بین شرکت‌ها فقط مدیرعامل به مدیرعامل؛ کلید توقف فقط برای شرکت خود). قرارداد ورودی و خروجی در `infra/opa/README.md` است.

**قاعده‌های ۴.۱:**
- هیچ‌کس پیشنهاد خودش را تأیید نمیکند.
- `budget_change` فقط داخل شرکت پیشنهاددهنده است.
- **هر** نوشتن ایجنت از `hq.actions` هم رد میشود: A2 فقط با مجوز نقش یا پاکت اختیار، و A4 همیشه رد.

OPA با `--authorization=basic` و `system.authz` اجرا میشود: فقط `POST /v1/data/hq/...` و `GET /health` پذیرفته میشوند، و policy و data فقط از فایل بار میشوند.

اگر OPA جواب ندهد، API **fail-closed** است: `503 policy_unavailable` (۴.۱؛ از `403 policy_denied` جداست تا کلاینت بگوید «دوباره امتحان کن»). تغییر سیاست یعنی تغییر فایل `.rego` به‌علاوه‌ی تستش (پوشش ۱۰۰٪ در `make check`).

## ۶. کار، ارجاع و پلنر

- **مسیر:** مالک ← مدیرعامل (عمق ۰) ← مدیر (۱) ← کارمند (۲). سفارش مستقیم به یک دپارتمان از عمق ۱ شروع میشود و مدیرعامل بیدار نمیشود.
- **ارجاع یک ردیف است، نه صدا زدن یک ایجنت.** runtime پرامپت ۵ کار را از همین ردیف‌ها و از استریم برمیدارد.
- **درخواست بین دپارتمان‌ها:** مدیر یک کار ریشه در دپارتمان دیگر باز میکند (`requested_by_work_id`). مدیر مقابل میپذیرد (`accept`) یا رد میکند (`fail` با `decline: true`). **بین شرکت‌ها** فقط مدیرعامل به مدیرعامل.
- **کار دائمی:** پاکت اختیار (`escrow`: کلاس‌های مجاز A0 تا A2، سقف توکن هر اجرا، سقف دلار ماهانه، انقضا) + زمان‌بندی (`schedule`: زیرمجموعه‌ای از RRULE که دقیقاً به Temporal Schedule تبدیل میشود: HOURLY با INTERVAL مقسوم‌علیه ۲۴، و DAILY، WEEKLY و MONTHLY با BYHOUR و BYMINUTE). اگر مالک بسازد، فوراً فعال است. اگر ایجنت بسازد، تصمیم `recurring_approval` میخواهد که **مالک یا مدیرعامل همان شرکت در سقف بودجه‌ی ماهانه‌ی شرکت** تأییدش میکند. هر اجرا یک کار ریشه با بودجه‌ی پاکت است و بعد از انقضای پاکت متوقف میشود.
- **پلنر:** `GET /api/v1/planner` فقط یک نما روی همین کارهاست، با منطقه‌ی زمانی مالک.

## ۷. تصمیم‌ها، خروجی‌ها، پیام‌ها و مصوبات

- **چرخه:** پیشنهاد (`/internal/v1/decisions`) ← کارتابل و اعلان 🟡 ← تصمیم مالک (با 🔏 برای A3، `hire`، `dismissal` و `budget_change`)، یا مدیرعامل در حد اختیارش ← مصوبه‌ی `M-…` ← پیام سیستمی به thread پیشنهاددهنده ← **اثر** در worker (`hire`: کارمند با کد بعدی + تخصیص مدل در `llm.assignments` با `role` و `<CO>:<کد>`؛ `recurring_approval`: پاکت و زمان‌بندی فعال و اجرای اول؛ `dismissal`؛ `budget_change`) ← کار پیگیری برای `deploy`، `a3_action` و `proposal`.
- **امتیاز ۱ تا ۱۰** روی هر خروجی؛ امتیازدهی دوباره تا ۷ روز نسخه‌ی جدید میسازد و تاریخچه میماند. فرمول امتیاز کارمند (§۱.۱۶) در `hq_api/domain/scoring.py` است و شبانه و بعد از هر امتیاز حساب میشود.
- **پیام‌ها تغییرناپذیرند.** اصلاح یعنی پیام تازه با `links.corrects`.

## ۸. اعلان‌ها و خلوت

| سطح | رفتار |
|---|---|
| 🔴 `urgent` | همیشه و فوری (در اپ + push + صدا)، حتی در خلوت |
| 🟡 `decision` | در اپ بی‌صدا؛ push دسته‌ای (پنجره‌ی پیش‌فرض ۳۰ دقیقه، یک push برای هر دسته) |
| 🔵 `report` | در اپ؛ push طبق ریتم (گزارش صبحگاهی) |
| 🟢 `info` | فقط در اپ، بی‌صدا |
| 🟣 `learning` | در اپ، با سقف روزانه و جواب یک‌لمسی |

- **خلوت روشن:** همه‌چیز جز 🔴 نگه داشته میشود. وقتی خاموش شود، نگه‌داشته‌ها آزاد میشوند و «در نبودت چه گذشت» (`GET /api/v1/owner/away-summary`) شمارش‌ها را میدهد.
- **سهمیه‌ی توجه هر مدیرعامل** (پیش‌فرض ۶ در روز): بیشتر از آن به دسته‌ی بعدی میرود.
- **🔴 از ایجنت فقط برای حادثه (۴.۱):**
  - فقط با یکی از دسته‌های `service_down`، `security`، `data_loss` یا `budget_hard_stop`، و حداکثر ۵ در ساعت برای هر شرکت.
  - بقیه به 🟡 پایین میایند.
  - ایجنت شرکت قفل‌شده جز 🔴 حادثه هیچ اعلانی نمیفرستد.
- شمارش‌های سهمیه با تابع SECURITY DEFINER ‏`notify.agent_notification_counts()` انجام میشود و دامنه‌ی شرکتِ فراخواننده هرگز باز نمیشود.
- **کانال‌ها:** در اپ (استریم) همیشه روشن است. Web Push (VAPID) کلیدش ساخته شده، ولی فقط با دامنه کار میکند. FCM و تلگرام **خاموش‌اند** تا مالک credential بدهد (`kv/hq-api/channels/fcm` و `.../telegram` در OpenBao). تلگرام فقط پشتیبان است و **هیچ تأییدی از آن ممکن نیست.**

## ۹. استریم زنده

- JetStream ‏`HQ_CORE` (نگهداری ۳۰ روز) با موضوع‌های `hq.core.<company>.<type>`. هر تغییر در **outbox همان تراکنش** نوشته میشود و relay در api آن را با `Nats-Msg-Id` منتشر میکند، پس هیچ تغییر ثبت‌شده‌ای بی‌رویداد نمیماند.
- `GET /api/v1/stream` (SSE) با فیلتر `topics` و `company`، ادامه با `Last-Event-ID` (همان sequence ‏JetStream) و heartbeat هر ۱۵ ثانیه. `company=*` فقط شمارنده و `activity.changed` میدهد.
- worker رویدادهای `hq.llm.*` و هشدارهای `hq.alerts.*` ‏llm-router را **فقط با متادیتا** به HQ_CORE میآورد. هشدار بودجه (۷۰/۹۰ ← 🔵، ۱۰۰ ← 🔴)، ناهنجاری (🔴) و نسبت هزینه‌ی SDK (🔵) اعلان هم میشوند.
- **هیچ متن پیام، prompt یا رازی روی NATS، در Audit یا در لاگ نمیرود.** این را تست هم میکنیم.

## ۱۰. گردش‌کارها (Temporal، task queue ‏`hq-core`)

| Schedule / Workflow | زمان | کار |
|---|---|---|
| `DecisionLifecycle` (`decision-<ref>`) | با هر تصمیم | انقضا، اثر تأیید با retry (وقتی کلید هلدینگ روشن است صبر میکند)، شکست ← اعلان 🔴 |
| `recurring-<W-…>` ← `RecurringRun` | از RRULE کار، در منطقه‌ی زمانی خودش | یک اجرا با بودجه‌ی پاکت؛ وقتی شرکت قفل است رد میشود |
| `hq-maintenance` ← `Maintenance` | هر ۵ دقیقه | پله‌ی بعدی کار عقب‌افتاده (مدیر ← مدیرعامل ← مالک)، همسان‌سازی schedule‌ها و تصمیم‌ها، انقضای پاکت‌ها، پاک‌سازی کلیدهای idempotency، challengeها و outbox منتشرشده؛ از پرامپت ۵ صف دوباره‌ی اجراهای `refused` بعد از آزاد شدن قفل و اجراهای گیرکرده (`requeue_runs`) |
| `hq-notification-digest` | هر ۵ دقیقه | دسته‌های اعلان |
| `hq-morning-report` | `owner.settings.morning_report_at` در منطقه‌ی زمانی مالک | گزارش صبحگاهی **قاعده‌محور** (خروجی `HQ-SYS`). بعد (پرامپت ۵) یک بازنویسی فارسی خوش‌خوان با Sonnet 5.5، فقط اگر هیچ عدد تازه‌ای نداشته باشد. اعلان 🔵 به بهترین نسخه لینک میدهد |
| `AgentRun` (`agent-run-<id>`، پرامپت ۵) | با هر اجرای صف‌شده (Dispatcher) | claim ← قدم‌ها ← finalize (`docs/ops/AGENTS.md`) |
| `hq-site-checks` ← `SiteChecks` (پرامپت ۵) | هر ۵ دقیقه | پایش قاعده‌محور سایت‌ها، حادثه‌ها، `ops.hub_health` |
| `hq-ceo-daily` ← `CeoDaily` (پرامپت ۵) | ۰۷:۳۰ | گزارش روزانه‌ی مدیرعامل‌ها؛ **pause** تا `HQ_CEO_DAILY_REPORTS=on` |
| `hq-audit-verify` | هر شب ۰۲:۳۰ | بررسی زنجیره؛ شکستگی ← 🔴 |
| `hq-score-job` | هر شب ۰۳:۰۰ | امتیاز کارمندها |

`Reconcile` را api بعد از هر تغییر زمان‌بندی صدا میزند. اگر Temporal در دسترس نباشد، درخواست‌ها شکست نمیخورند و Maintenance بعداً همسان میکند.

## ۱۱. کلید توقف و توقف deploy

| حالت | api | llm-router | worker |
|---|---|---|---|
| کلید **هلدینگ** روشن | هر اقدام نوشتنی ایجنت‌ها ← `423 company_locked` | فقط P0 | اجراهای دائمی و اثر تصمیم‌ها صبر میکنند؛ گزارش، Audit، امتیاز و پله‌ی عقب‌افتادگی ادامه دارند |
| کلید **یک شرکت** روشن | همان، فقط برای آن شرکت | فقط P0 برای آن شرکت | اجراهای دائمی همان شرکت رد میشوند |
| **توقف deploy** | اقدام نوشتنی ایجنت‌های آن شرکت ← `423` | بی‌اثر (فکر کردن مجاز است) | — |

مالک هیچ‌وقت قفل نمیشود. روشن کردن کلید step-up نمیخواهد، چون سرعت مهم است، ولی **آزاد کردنش 🔏 میخواهد.**

**آزاد کردن به ترتیب اختیار (۴.۱):**
- کلیدی که **مالک** زده فقط با مالک و step-up آزاد میشود. **(پرامپت ۵)** اگر مالک کلیدی را که ایجنت زده دوباره روشن کند، مالکیت کلید به مالک میرسد و مدیرعامل دیگر نمیتواند آزادش کند. وضعیت در مسیر آزادسازی ایجنت با `FOR UPDATE` خوانده میشود.
- آزاد کردن چیزی که آزاد است idempotent است (`200`). برداشتن توقف deploy وقتی توقف فعالی نیست هم `200` است، اگر فراخواننده اجازه‌ی گذاشتن آن را دارد.
- مدیرعامل فقط کلید شرکت خودش را میزند، و فقط کلیدی را آزاد میکند که یک ایجنت **همان شرکت** زده باشد.
- توقف deploy:
  - توقف مالک فقط با مالک برداشته میشود.
  - توقف pipeline فقط با **همان سرویس** (`created_by_code`) یا مالک.
  - توقف مدیرعامل فقط با خود او.
  - یک توقف تازه توقف‌های دیگر را برنمیدارد.

کلید یک شرکت اثر تصمیم‌ها و اجرای اول کار دائمی همان شرکت را هم نگه میدارد.

## ۱۲. خزانه‌ی توکن (سمت خواندن)

`/api/v1/treasury/summary|breakdown|calls|what-if|quota` (پرامپت ۵: وضعیت سهمیه‌ی اشتراک و اولویت‌های متوقف)، به‌علاوه‌ی `connections`، `assignments` و `budgets`. هزینه **فقط از جدول قیمت خود ما** میاید (`llm.connections.pricing`، با `source_url` و `as_of`). «اگر با مدل X بود چقدر میشد» هم با همان جدول حساب میشود. کلید اتصال‌ها **فقط نوشتنی** است: به OpenBao میرود و هیچ پاسخی آن را برنمیگرداند.

## ۱۳. قرارداد OpenAPI

`apps/api/openapi/hq-api.v1.json` (OpenAPI 3.1) از خود کد ساخته میشود: `make openapi`. **CI اگر فایل با کد نخواند رد میکند.** هر operation یک `operationId` پایدار (نام تابع)، توضیح و مثال دارد. خود سرور در production این سند را سرو نمیکند.

## ۱۴. کیفیت

`make check` (و CI): ruff، mypy strict، pytest روی Postgres، NATS، Temporal و OPA واقعی (`services/scripts/test-env.sh` با `HQ_TEST_TARGET=api`)، `opa test` با پوشش ۱۰۰٪، Schemathesis روی همه‌ی operationها (بدون هیچ 5xx)، pip-audit، hadolint و gitleaks. پوشش: منطق دامنه ≥ ۸۵٪ و کل ≥ ۸۰٪.

## ۱۵. حافظه

سقف‌ها در `infra/compose/profiles/*.env`. پروفایل فعال از پرامپت ۵ `full` است (`docs/ops/RUNBOOK.md` §۶):
- `full`: ‏`api` 384m، `worker` 512m (گفت‌وگوی اجراها در حافظه)، `opa` 128m، `gateway` 128m، `web` 384m.
- `lean` برای برگشت به سرور کوچک‌تر آماده است: ‏`api` 256m، `worker` 256m، `opa` 96m، `gateway` 96m، `web` 256m.


## تغییرهای ۴.۱ در قرارداد خطا
- `428 precondition_required`: یک درخواست PATCH بدون `If-Match` آمده است. کد این خطا قبلاً `validation_failed` بود. `PATCH /api/v1/connections/{id}` هم حالا `version` و `If-Match` دارد.
- `503 policy_unavailable`: OPA در دسترس نیست. از `403 policy_denied` جداست.
- **ورود:** گزینه‌های ورود دیگر فهرست `allowCredentials` ندارند، چون passkey قابل‌کشف (resident) است.
  - اگر شمارنده‌ی امضای یک passkey جلو نرود، ورود رد میشود. آن passkey علامت میخورد (`flagged_at`)، یک ردیف Audit ‏A4 ثبت میشود و یک 🔴 میرسد.
  - ورود تازه نشستی را که همان کلاینت فرستاده باطل میکند.
- **توکن ایجنت** `jti` دارد. همان توکن با همان `X-Request-ID` دوبار رد میشود (replay). درخواستی که به `/internal` با `X-Forwarded-For` برسد هم رد میشود.
- **(پرامپت ۵) رجیستری اجرا:** توکن فقط وقتی پذیرفته میشود که `run` آن `running` است، مال همان کارمند است و `token_expires_at` نگذشته. وگرنه `401`.
- **آپلود فایل:**
  - قفل شرکت پیش از نوشتن هر بایتی بررسی میشود.
  - سقف حجم هنگام خواندن جریان اعمال میشود (`413`).
