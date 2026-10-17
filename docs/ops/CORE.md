# هسته‌ی هلدینگ (پرامپت ۴): API، worker، سیاست‌ها و داده‌ها

> **مرجع:** قرارداد `contracts/HQ_CORE_API_v1.md` و `docs/OPERATING_MODEL.md`. هر endpoint، فیلد و کد خطا از قرارداد است. تفاوت‌ها در گزارش پرامپت ۴ زیر «Contract notes» آمده‌اند.
> **کد:** `apps/api/` (یک پکیج پایتون `hq_api` با دو entrypoint: `python -m hq_api` و `python -m hq_api.worker`).

## ۱. معماری

```
 مرورگر / اندروید ──HTTPS──► Caddy ──(/api/* فقط وقتی دامنه هست)──► api :8000
                                     (/internal/* هرگز)                │
 ایجنت‌ها (پرامپت ۵)، سرویس‌ها ──hq-internal──► /internal/v1 ─────────┤
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

- همه روی شبکه‌ی `hq-internal`، **بدون پورت منتشرشده**. فقط Caddy روی 80/443 است.
- نقش‌های دیتابیس: `hq_api` و `hq_worker`، هر دو با کمترین دسترسی (`infra/postgres/provision.sh`؛ grantها در migrationها). **هیچ نقشی حق DELETE روی داده‌ی کسب‌وکار ندارد.**
- OpenBao: policy‌های `hq-api` (خواندن `kv/hq-api/*`؛ کلید اتصال‌ها فقط **نوشتنی**) و `hq-worker` (فقط Web Push و کانال‌ها). `make up` آن‌ها را میسازد (`infra/openbao/provision.sh`).

## ۲. لبه و ورود

- **بدون دامنه:** `/api/*` در Caddy با ۴۰۴ بسته است و endpointهای ورود جواب `503 origin_not_configured` میدهند. این خطا نیست؛ ورود فقط با دامنه و HTTPS معنا دارد.
- **با دامنه:** کافی است در `infra/compose/.env` یک خط بگذاری: `HQ_SITE_ADDRESS=hq.example.com` و `make up`. `infra/compose/hq.sh` از روی آن `HQ_API_EDGE=on`، ‏`HQ_PUBLIC_ORIGIN=https://<دامنه>` و `HQ_WEBAUTHN_RP_ID=<دامنه>` را میسازد. Caddy گواهی میگیرد و `/api/*` را با SSE (`flush_interval -1`)، سقف بدنه‌ی ۲MB و هدرهای امنیتی (HSTS، CSP، ...) به `api` میدهد.
- **`/internal/*` هرگز از لبه رد نمیشود.**
- **ثبت کلید عبور (مالک):** `make owner-enroll` در ترمینال خود مالک یک لینک یک‌بارمصرف ۱۵ دقیقه‌ای چاپ میکند (`<origin>/enroll#token=...`). این لینک **هیچ‌جا ذخیره یا لاگ نمیشود** و همین دستور مسیر بازیابی هم هست. دو کلید عبور (گوشی و کامپیوتر) پیشنهاد میشود.
- **نشست‌ها:** opaque، ذخیره‌شده به‌صورت SHA-256، تمدید لغزنده‌ی ۳۰ روز و سقف مطلق ۹۰ روز. وب: کوکی `hq_session` (`HttpOnly; Secure; SameSite=Strict; Path=/api`) + `X-HQ-Client: web` و Origin درست (وگرنه `403 csrf_rejected`). اندروید: `Authorization: Bearer`.
- **step-up 🔏:** کلید عبور دوباره با UV. توکن یک‌بارمصرف ۱۲۰ ثانیه‌ای، بسته به نشست، action و target، در هدر `X-Step-Up`:

| action | target | کجا |
|---|---|---|
| `decision.approve` | `D-…` | تأیید A3، `hire`، `dismissal`، `budget_change` |
| `employee.dismiss` | کد کارمند | برکناری |
| `company.create` / `company.archive` | کد شرکت | ساخت شرکت / بایگانی |
| `department.create` | کد شرکت | دپارتمان جدید |
| `kill_switch.release` | `holding` یا `company:XX` | **آزاد کردن** کلید توقف (روشن کردنش step-up نمیخواهد) |
| `connection.update` / `connection.secret` | id اتصال | تغییر اتصال / ثبت کلید |
| `assignments.update` / `budgets.update` | `*` | تخصیص مدل / بودجه |
| `device.revoke` / `passkey.register` | id / `self` | دستگاه‌ها |

## ۳. داده‌ها (دیتابیس `hq`)

| schema | جدول‌ها |
|---|---|
| `core` | `companies` (کامل‌شده)، `departments`، `employees`، `employee_code_seq`، `employee_scores`، `counters`، `outbox`، `idempotency_keys` |
| `work` | `work`، `work_events`، `escrows`، `schedules` |
| `cartable` | `decisions`، `deliverables`، `ratings`، `resolutions` |
| `msg` | `threads`، `messages` |
| `notify` | `notifications`، `settings`، `web_push_subscriptions`، `fcm_tokens`، `digest_batches` |
| `auth` | `passkeys`، `sessions`، `challenges`، `step_ups`، `enrolment_tokens` |
| `owner` | `presence`، `settings`، `interactions` |
| `audit` | `entries`، `chain_head` |
| `control` | `kill_switches`، `deploy_freezes` |
| `files` | `files` (محتوا روی volume ‏`hq-files` از راه interface ‏`Storage`؛ بعداً S3) |

**قاعده‌هایی که در خود دیتابیس اجرا میشوند** (trigger و constraint؛ با SQLSTATE کلاس `HQ` که API به کد قرارداد تبدیل میکند):
1. **عمق ارجاع ≤ ۲:** عمق فرزند همیشه عمق والد + ۱ است (`HQD01` ← `409 delegation_depth_exceeded`).
2. **بودجه:** بودجه‌ی فرزند ≤ باقیمانده‌ی والد و جمع فرزندها ≤ والد. فرزند بی‌بودجه باقیمانده را به ارث میبرد (`HQB01` ← `409 budget_exceeded`).
3. **`done` فقط با خروجی یا شاهد** (`HQE01` ← `422 evidence_required`).
4. **append-only:** `audit.entries`، `msg.messages`، `cartable.resolutions`، `cartable.ratings`، `cartable.deliverables`، `owner.interactions`، `work.work_events` و `files.files`. UPDATE، DELETE و TRUNCATE برای همه رد میشود، حتی مالک دیتابیس.
5. **کدهای انسانی یکتا و ثابت:** `TY-TECH-01`، `D-000123`، `O-000456`، `W-000789`، `M-0001`، `A-0142`. شماره‌ی کارمند برای هر شرکت و دپارتمان **فقط رو به جلو** میرود و بعد از برکناری دوباره داده نمیشود. مصوبه‌ها یک دنباله‌ی **بی‌فاصله** برای کل هلدینگ دارند.
6. **تصمیم تصمیم‌گرفته‌شده دیگر عوض نمیشود** (`HQS01` ← `409 decision_not_pending`).

**RLS:** روی **همه‌ی** جدول‌های دارای `company_id`، با FORCE و همان قرارداد `llm.*`: هر تراکنش با `SET LOCAL app.company_ids` (uuid[]) شروع میشود. مالک همه‌ی شرکت‌ها را میبیند و ایجنت فقط شرکت خودش را. ردیف‌های سطح هلدینگ `company_id` خود هلدینگ (`HQ`) را دارند، هرگز NULL.

**Audit زنجیره‌ای:** `hash = sha256(prev_hash || canonical_json(entry))`، که trigger (`audit.chain`، SECURITY DEFINER) زیر قفل ردیف سر زنجیره حساب میکند. `audit.verify_chain()` کل زنجیره را دوباره حساب میکند (`GET /api/v1/audit/verify` و گردش‌کار شبانه). نقش API روی این جدول فقط INSERT و SELECT دارد.

**جستجوی فارسی:** `core.fa_normalize()`: ي/ى→ی، ك→ک، ۀ→ه، ارقام فارسی و عربی→لاتین، و حذف نیم‌فاصله، ZWJ، کشیده و اعراب. بعد FTS با پیکربندی `simple` + `pg_trgm`.

**seed از فایل:** `apps/api/seed/templates/standard.yaml` (۸ دپارتمان + مدیرعامل + ۸ مدیر) و `holding.yaml` (`OVS` با بازرس کل، `AIOPS`، مشاور کل `HQ-ADV` و `HQ-SYS` که نویسنده‌ی قاعده‌محور گزارش‌هاست). همه‌ی جایگاه‌ها با `activity = sleeping` ساخته میشوند. **هیچ کارمند شماره‌دار seed نمیشود.** seed هر بار اجرا میشود، فقط چیزهای جاافتاده را اضافه میکند و ویرایش‌های بعدی را بازنویسی نمیکند.

## ۴. افزودن یک شرکت (یک رکورد + یک قالب)

- **از اپ:** `POST /api/v1/companies` با 🔏 `company.create`. دپارتمان‌ها، جایگاه‌های رهبری، threadها و ردیف کلید توقف در یک تراکنش از روی قالب ساخته میشوند.
- **از فایل:** یک خط در `services/llm-router/seed/companies.yaml` (کد، نام، `kind: company`) و یک خط در `apps/api/seed/companies.yaml` (`name_fa`، `color_index`، `template`)، سپس `make up`.
- **هیچ کد یا زیرساختی عوض نمیشود.** قالب جدید هم فقط یک فایل YAML در `apps/api/seed/templates/` است.

## ۵. سیاست‌ها (OPA)

`infra/opa/policy/`، پکیج‌های `hq.decisions` (چه کسی چه تصمیمی را تأیید میکند)، `hq.actions` (A0 تا A4؛ **A4 برای هر غیرمالک همیشه رد**) و `hq.internal` (هر ایجنت فقط در شرکت، دپارتمان و نقش خودش؛ ارجاع بین شرکت‌ها فقط مدیرعامل به مدیرعامل؛ کلید توقف فقط برای شرکت خود). قرارداد ورودی و خروجی در `infra/opa/README.md` است. اگر OPA جواب ندهد، API **fail-closed** است: `503 policy_denied`. تغییر سیاست یعنی تغییر فایل `.rego` به‌علاوه‌ی تستش (پوشش ۱۰۰٪ در `make check`).

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
| `hq-maintenance` ← `Maintenance` | هر ۵ دقیقه | پله‌ی بعدی کار عقب‌افتاده (مدیر ← مدیرعامل ← مالک)، همسان‌سازی schedule‌ها و تصمیم‌ها، انقضای پاکت‌ها، پاک‌سازی کلیدهای idempotency، challengeها و outbox منتشرشده |
| `hq-notification-digest` | هر ۵ دقیقه | دسته‌های اعلان |
| `hq-morning-report` | `owner.settings.morning_report_at` در منطقه‌ی زمانی مالک | گزارش صبحگاهی **قاعده‌محور، بدون LLM** (خروجی `HQ-SYS` + اعلان 🔵). نسخه‌ی نوشته‌شده با مدل در پرامپت ۵ |
| `hq-audit-verify` | هر شب ۰۲:۳۰ | بررسی زنجیره؛ شکستگی ← 🔴 |
| `hq-score-job` | هر شب ۰۳:۰۰ | امتیاز کارمندها |

`Reconcile` را api بعد از هر تغییر زمان‌بندی صدا میزند. اگر Temporal در دسترس نباشد، درخواست‌ها شکست نمیخورند و Maintenance بعداً همسان میکند.

## ۱۱. کلید توقف و توقف deploy

| حالت | api | llm-router | worker |
|---|---|---|---|
| کلید **هلدینگ** روشن | هر اقدام نوشتنی ایجنت‌ها ← `423 company_locked` | فقط P0 | اجراهای دائمی و اثر تصمیم‌ها صبر میکنند؛ گزارش، Audit، امتیاز و پله‌ی عقب‌افتادگی ادامه دارند |
| کلید **یک شرکت** روشن | همان، فقط برای آن شرکت | فقط P0 برای آن شرکت | اجراهای دائمی همان شرکت رد میشوند |
| **توقف deploy** | اقدام نوشتنی ایجنت‌های آن شرکت ← `423` | بی‌اثر (فکر کردن مجاز است) | — |

مالک هیچ‌وقت قفل نمیشود. روشن کردن کلید step-up نمیخواهد، چون سرعت مهم است، ولی **آزاد کردنش 🔏 میخواهد.** مدیرعامل فقط کلید شرکت خودش را از `/internal/v1/control/kill-switch` روشن یا خاموش میکند.

## ۱۲. خزانه‌ی توکن (سمت خواندن)

`/api/v1/treasury/summary|breakdown|calls|what-if`، به‌علاوه‌ی `connections`، `assignments` و `budgets`. هزینه **فقط از جدول قیمت خود ما** میاید (`llm.connections.pricing`، با `source_url` و `as_of`). «اگر با مدل X بود چقدر میشد» هم با همان جدول حساب میشود. کلید اتصال‌ها **فقط نوشتنی** است: به OpenBao میرود و هیچ پاسخی آن را برنمیگرداند.

## ۱۳. قرارداد OpenAPI

`apps/api/openapi/hq-api.v1.json` (OpenAPI 3.1) از خود کد ساخته میشود: `make openapi`. **CI اگر فایل با کد نخواند رد میکند.** هر operation یک `operationId` پایدار (نام تابع)، توضیح و مثال دارد. خود سرور در production این سند را سرو نمیکند.

## ۱۴. کیفیت

`make check` (و CI): ruff، mypy strict، pytest روی Postgres، NATS، Temporal و OPA واقعی (`services/scripts/test-env.sh` با `HQ_TEST_TARGET=api`)، `opa test` با پوشش ۱۰۰٪، Schemathesis روی همه‌ی operationها (بدون هیچ 5xx)، pip-audit، hadolint و gitleaks. پوشش: منطق دامنه ≥ ۸۵٪ و کل ≥ ۸۰٪.

## ۱۵. حافظه

سقف‌ها در `infra/compose/profiles/*.env`: lean ‏`api` 256m، `worker` 256m، `opa` 96m و `api-migrate` 160m. برای اینکه جمع سقف‌ها زیر ۸۰٪ RAM بماند، سقف valkey، NATS، Prometheus، Loki، Temporal UI و llm-migrate به اندازه‌ی مصرف اندازه‌گیری‌شده به‌علاوه‌ی حاشیه کم شد. جزئیات در گزارش پرامپت ۴ است.
