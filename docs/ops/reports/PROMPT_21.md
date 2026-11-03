# گزارش پرامپت ۲۱: مالک فقط کسب‌وکار میبیند

> Claude سرور هاب، ۲۰۲۶-۱۱-۰۳.
> - **وضعیت deploy:**
>   - مرحله‌ی ۱ 🟢 سبز. migration **0039** روی دیتابیس است.
>   - مرحله‌ی ۲ 🟢 روشن است (`HQ_GROUPS=on` فقط در worker).
> - **شاخه‌ی زنده:** `server/p21-deploy`. از سر شاخه‌ی اصلی (`c04dd1b`) ساخته شد و `906403d` (پرامپت ۲۰.۱) را در خود دارد. commit قالب‌بندی یا وابستگی لازم نشد.
> - **کد:** هیچ کدی ننوشتم.
> - **کلید توقف:** همان است که مالک گذاشت. مالک ۱۱-۰۳ 16:09Z برداشت و حالا **خاموش** است.
> - **پاکت ماه:** برای هیچ شرکتی نگذاشتم.
> - **دست نزدم به:** هیچ سرور شرکتی، هیچ کاتالوگ، جایگاه Codex، `media-on` و `tts-on`.

## ۱. `make check` و تست مرورگر
- **کجا:** worktree جدا در scratchpad، روی `c04dd1b`. از 16:13 تا 17:44.
- **سبزها:**
  - gitleaks، compose، ports، memory budget، shellcheck، yamllint، hadolint، opa، infra، backup، provisioning و python lint.
  - audit وابستگی‌ها: هیچ CVE تازه‌ای نبود.
  - سرویس‌ها: 1168 قبول. gateway و runner: 79 قبول.
- **api: ‏1098 قبول، ۱ شکست (۶۸ دقیقه):** `test_p19_1_whole::test_a_jobs_output_past_the_stream_and_a_long_answer_are_kept_whole`.
  - **چه شد:** جدول `products` یک ردیف داشت، نه 2200.
  - **علت:** این تست جواب بلند را فقط به «دو کار اولی که runner برمیدارد» میدهد. پس به ترتیب برداشتن کارها وابسته است.
  - **سنجش:** جدا **هفت بار** اجرا شد و هر هفت بار ۴ از ۴ قبول بود. در `make check` پرامپت ۲۰.۱ هم سبز بود، و نه خود تست، نه کد کاتالوگ در ۲۱ عوض نشده است.
  - **نتیجه:** تست ناپایدار است، نه خرابی کد. deploy را نگه نداشتم و چیزی را عوض نکردم.
  - **پیشنهاد برای Claude ساخت:** تست، جواب بلند را به بخش‌های `products` و `code` بدهد، نه به «دو کار اول».
- **live:** فقط قرمز همیشگی worktree: `media-render: the sandbox probe failed`، چون worktree `.env` ندارد. روی خود هاب `verify-live` سبز است.
- **`services/scripts/browser-test.sh`:** **۱۹ از ۱۹ قبول.**

## ۲. عدد پیش از deploy (فقط خواندن، 16:12Z)
**یافته‌ها و اعلان‌های مالک، به همان قاعده‌ی 0037:**

| چه | فنی | کسب‌وکاری |
|---|---|---|
| یافته‌ی باز | 3 | 2 |
| یافته‌ی بسته | 2 | 0 |
| اعلان خوانده‌نشده | 7 | 5 |

**مصرف ۲۴ ساعت گذشته (۱۱-۰۲ 16:12Z تا ۱۱-۰۳ 16:12Z):**

| حوزه | call | توکن |
|---|---|---|
| council | 1 | 6 |
| oversight | 3 | 0 |
| work | 1 | 0 |

سهمیه‌ی هفتگی `claude-max` تا ۱۱-۰۵ 00:00Z تمام است (`quota_exhausted`). پس همه‌ی اجراها پیش از مدل رد میشوند.

## ۳. deploy مرحله‌ی ۱ (به وقت UTC)
| زمان | قدم | نتیجه |
|---|---|---|
| 18:00:10 | `make backup` | `/home/Hub/backups/20261103T180010Z` (سه دیتابیس) |
| 18:00:45 | checkout `server/p21-deploy` در checkout زنده | `c04dd1b` |
| 18:00:50 | `make llm-provision` | rc=0. policyها دوباره نوشته شدند، از جمله `hq-api` و `hq-worker` با `kv/hq/growth/*`. هیچ رمزی ساخته یا چاپ نشد. اسکریپت idempotent است و AppRoleهای موجود را دست نمیزند |
| 18:00:55 | ساختن image‌ها | `hq.sh build api worker gateway` (worker همان image ‏api است) |
| 18:01:04 | migration | `hq.sh up --no-deps api-migrate`: `0036 -> 0037 -> 0038 -> 0039`. `alembic_version_api` = **0039** |
| 18:01:30 | بالا آوردن | `hq.sh up -d --no-deps --wait api worker gateway`: هر سه `healthy` |
| 18:02 تا 18:18 | `make verify-live` | **rc=0**. فقط همان دو GAP قبلی: رسیدن egress و searxng با IP، که قانون DOCKER-USER مالک است |

- **`HQ_GROUPS`:** در مرحله‌ی ۱ در `.env` نبود.
- **seed:** `channels: 5`، `groups: 1`، `group_members: 4`.
- **OPA:** policyهای تازه را با `--watch` بی خطا گرفت.

## ۴. سنجش‌های مرحله‌ی ۱
| سنجش | نتیجه |
|---|---|
| `alembic current` | **0039** |
| یافته‌های فنی به صف CTO و SRE | **6** (4 باز `infra` و 2 بسته `security`)، همه `owner_visible = false` و `routed_to = HQ-AIOPS-MGR` |
| اعلان‌های فنی به صف CTO و SRE | **8**: ‏5 `HQ-AIOPS-MGR`، و یکی برای هر کدام از `IG-TECH-MGR`، `FX-TECH-MGR` و `PC-TECH-MGR` |
| ردیف Audit برای هر نوع | **بله**: دو ردیف `routing.move` (findings: 6، notifications: 8)، با «nothing deleted» |
| هیچ ردیفی پاک نشد | **بله**: یافته‌ها 7 → 8 و اعلان‌ها 12 → 13. هر کدام یک ردیف تازه دارد که بین سنجش و deploy ساخته شد (FI-0017 در 16:30) |
| `core.hiring` هلدینگ | **`open/auto`** (Audit ‏`hiring.start`) |
| PR-005، PR-081، PR-098، PR-041 | **`paused`** (نسخه‌ی 2) |
| PR-001، PR-004، PR-100 هفتگی | **بله**: SA 10:00، SA 12:00، TH 20:00 |
| PR-095 روزانه | **بله**: 15:00 |
| نسخه‌ی تغییریافته‌ی مالک دست نخورد | **بله**. مالک هیچ‌کدام از این‌ها را دستی عوض نکرده بود؛ نسخه‌ی 1 همه `seed` بود. ۸ ردیف Audit ‏`oversight.protocol_update` |
| کارگروه `content` در `growth.groups` | **بله**، نسخه‌ی 1 |
| شرکت‌های عضو | **FX، IG، PC، TY**، هر کدام ۸ جایگاه، `on` |
| زمان‌بندی `hq-groups-tick` | **بله**، هر ۱۰ دقیقه |
| زمان‌بندی `hq-connections-read` | **بله**، هر ساعت |
| زمان‌بندی `hq-home-morning` | **بله**، هر روز ۰۸:۰۰ تهران |
| `groups_tick` در 18:10 | **`{"skipped": "groups_off"}`** |
| `GET /api/v1/home` | **200**. `critical` = `[]`، ۳ کارت، کارگروه content با ۴ شرکت |
| `GET /api/v1/companies/TY/readiness?group=content` | **200**. `ready = false` (بند ۶) |

**اتصال‌هایی که ساخته شد (همه `not_connected`، `origin = seed`):**
- **FX:** instagram via IG-Hub.
- **IG:** instagram via IG-Hub.
- **PC:** instagram via IG-Hub.
- **TY:** telegram (signal: «کانال سیگنال تریدیار»)، instagram via IG-Hub.

**خلاصه‌ی فنی هفتگی:** زمان‌بندی Temporal جدا ندارد. فعالیت `tech_summary` در گردش کار `Maintenance` اجرا میشود، کنار `order_tick` (`worker/workflows.py`)، و خودش شنبه ۰۹:۰۰ تهران را میسنجد. هر هفته یک بار با کلید `tech_summary:<شنبه>` در `ops.watch_runs` ثبت میشود.

**API بی نشست مالک:**
- خود اپ را در کانتینر api با `httpx.ASGITransport` اجرا کردم و `deps.owner` را در همان پردازه جایگزین کردم (روش ۱۹.۲).
- هیچ نشست یا توکنی ساخته نشد و چیزی نوشته نشد.

## ۵. deploy مرحله‌ی ۲: روشن کردن کارگروه
- **18:14:56:**
  - `HQ_GROUPS=on` یک خط تازه در آخر `.env` است. `set-env.sh` این کلید را نمیشناسد. هیچ خط دیگری عوض نشد و فایل `600` ماند.
  - **فقط** `hq.sh up -d --no-deps --wait worker`: `healthy`.
- **env:** worker ‏`HQ_GROUPS=on`، api ‏`HQ_GROUPS=off`، همان‌طور که پرامپت گفته فقط worker دوباره بالا آمد.

### روال‌ها (`growth.routine_runs`)
| tick | asked (استخدام) | queued | skipped |
|---|---|---|---|
| 18:20 | 20 | 4 | 4 |
| 18:30 | 0 (هر جایگاه خالی روزی یک بار) | 0 | 0 |

| شرکت | روال | جایگاه | وضعیت | چرا |
|---|---|---|---|---|
| FX | `evening_line` | media_director | `queued` → W-000111 | — |
| FX | `publishing` | publisher | `skipped` | «سری انتشار مُهرشده‌ای نیست؛ چیزی برای انتشار نیست.» |
| IG | `evening_line` | media_director | `queued` → W-000109 | — |
| IG | `publishing` | publisher | `skipped` | همان |
| PC | `evening_line` | media_director | `queued` → W-000112 | — |
| PC | `publishing` | publisher | `skipped` | همان |
| TY | `evening_line` | media_director | `queued` → W-000110 | — |
| TY | `publishing` | publisher | `skipped` | همان |

- **سرنوشت چهار کار:** اجرای هر چهار در 18:20:02 با **`quota_exhausted`** شکست خورد. مدل `claude-sonnet-5-5` است و سهمیه‌ی هفتگی `claude-max` تا ۱۱-۰۵ 00:00Z تمام است. هیچ توکنی مصرف نشد.
- روال‌های دیگر کارگروه هنوز موعدشان نرسیده است.

### استخدام خودکار جایگاه‌های خالی
- **جایگاه‌های خالی:** هر چهار شرکت پنج جایگاه خالی دارند: `scriptwriter`، `visual_designer`، `motion_designer`، `publisher` و `content_analyst`. `media_director` پر است.
- **نتیجه:** **هیچ کسی استخدام نشد.** ۲۰ درخواست رد شد. هیچ کارمند یا کارتی ساخته نشد.
- **علت (همان شرط‌های کد، در یک تراکنش rollback‌شده سنجیده شد؛ چیزی نوشته نشد):**
  - همه‌ی ۲۰ با `422 validation_failed` و `payload.model: no enabled connection offers it` رد شدند.
  - **چرا:** مدل‌های منشور این نقش‌ها (`claude-sonnet-5-5`، `claude-opus-5-5`، `claude-haiku-5-5`) فقط در `claude-max` هستند. `claude-max` الان `quota_exhausted` است، نه `enabled`، و `anthropic-api` هم `disabled` است.
- **بعد از برگشتن سهمیه (۱۱-۰۵):**
  - سنجش بعدی پاکت ماه است (`approve_by_code` با `by_ceo=True`).
  - هیچ شرکتی پاکت ماه ندارد: FX، IG، PC و TY همه `tokens_month = NULL`.
  - پس همین درخواست‌ها با **`envelope_required`** رد میشوند، تا مالک پاکت بگذارد. بی پاکت هیچ کسی استخدام نمیشود.
- **لاگ worker:** فقط «auto fill of a seat failed» با نام نقش، بی علت (`groups._auto_fill`).
  - **پیشنهاد برای Claude ساخت:** کد خطا (`envelope_required`، `validation_failed`…) در لاگ یا در `readiness` بیاید.

## ۶. آمادگی TY برای کارگروه (`readiness?group=content`)
| سنجش | وضعیت |
|---|---|
| group، seat:media_director، hiring، channels، players، runner | ✅ |
| seat:scriptwriter، visual_designer، motion_designer، publisher، content_analyst | ❌ (بند ۵) |
| envelope | ❌ پاکت ماه ندارد |
| connection:instagram، connection:telegram | ❌ `not_connected` |
| series:instagram، series:telegram | ❌ سری انتشار مُهرشده‌ای نیست |
| media_tools | ❌ پروفایل `media` و `tts` خاموش است (تصمیم مالک) |

## ۷. سنجش پس از deploy (از زمان مرحله‌ی ۲، 18:14:56Z)
| حوزه | پیش (۲۴ ساعت) | ۱ ساعت بعد | ۲۴ ساعت بعد |
|---|---|---|---|
| council | 1 call / 6 توکن | 0 | در انتظار (۱۱-۰۴ 18:15Z) |
| oversight | 3 / 0 | 0 | در انتظار |
| work | 1 / 0 | 0 | در انتظار |
| media | 0 | **4 call / 0 توکن** (چهار `evening_line`، همه `quota_exhausted`) | در انتظار |
| catalogue | 0 | 0 | در انتظار |

- **قبولی «`catalogue` و `oversight` بیشترین سهم نیستند»:** 🟢 در یک ساعت بعد بله. تنها حوزه‌ی دارای call ‏`media` است، با ۰ توکن. در ۲۴ ساعت بعد در این نشست سنجیده نشد.
- **قبولی `daily_cap`:** هیچ کار مالک بی‌صدا بسته نشد. در این بازه هیچ فرمانی از مالک نبود و هیچ اجرایی به سقف روزانه‌ی شرکت نرسید. همه پیش از آن با `quota_exhausted` رد شدند.
- **خانه‌ی مالک (19:15Z هم دوباره):** `critical` = `[]`. هیچ مورد فنی غیربحرانی در آن نیست.
- **صبح بعد (`growth.home_mornings`):** اولین اجرا ۱۱-۰۴ ۰۸:۰۰ تهران (04:30Z) است. در این نشست سنجیده نشد.
- **هشدار:** تا سهمیه‌ی `claude-max` برنگشته (۱۱-۰۵ 00:00Z)، عددها نزدیک صفر میمانند و درباره‌ی سهم حوزه‌ها زیر بار چیزی ثابت نمیکنند.

## ۸. قدم بعدی مالک (از `docs/server-prompts/builder-w1/OWNER_STEPS.md`)
1. **runner 0.2.2:** Claude هر چهار سرور شرکت، runner را به 0.2.2 ببرد (بخش آخر پرامپت ۲۰.۱). الان هر چهار 0.2.1 هستند.
2. **پاکت ماه هر شرکت:** اپ ← تنظیمات ← استخدام ← «پاکت‌ها». بی پاکت، جایگاه‌های کارگروه پر نمیشوند.
3. **اتصال‌ها، به ترتیب اثر:** در اپ، شرکت ← «اتصال‌ها»:
   - Search Console و GA4.
   - بات تلگرام، که مدیر کانال سیگنال تریدیار باشد.
   - دستور خواندن اینستاگرام از Claude خود IG-Hub.
   - YouTube و PageSpeed.
4. **سری انتشار هر شرکت:** کارتی که مدیر رسانه پیشنهاد میدهد، یک بار مُهر شود. تا آن وقت روال `publishing` `skipped` میماند.
5. **ابزار ویدیو و صدا:** تصمیم شماست: `make media-on` و `make tts-on`. این دو حافظه‌ی سرور را میگیرند.
6. **سهمیه‌ی Claude:** تا ۱۱-۰۵ 00:00Z هیچ اجرای ایجنتی کار نمیکند. این کار شما نیست؛ خودش برمیگردد.

## پیوست: پاک‌سازی تازه به دستور مالک (۲۰۲۶-۱۱-۰۳ 20:03Z)
پاک‌سازی به دستور مالک در چت انجام شد، و فهرست نهایی را خود مالک پیش از اجرا تأیید کرد.

**دستور مالک:**
- کاتالوگ‌ها پاک نشوند.
- آنچه در اپ ساخته شده و دوباره ساختنش لازم میشد، مثل استخدام، بماند.
- بقیه پاک شود.

**قدم‌ها:**
1. **پشتیبان:** `/home/Hub/backups/20261103T200230Z`.
2. **اجرای آزمایشی:** یک تراکنش rollback‌شده. سنجش ارتباط‌ها (هیچ ردیف مانده‌ای به ردیف پاک‌شده اشاره نکند) سبز بود و چیزی عوض نشد.
3. **اجرای واقعی:** در یک تراکنش، با همان سنجش ارتباط‌ها پیش از commit.
4. **Audit:**
   - seq 903 `hub.history_purge`.
   - seq 904 `hub.work_purge`.

**ماند (افزون بر فهرست KEEP کد):**
- Audit.
- ۴ کاتالوگ (`infra.catalogues`) با ۴ کار خودشان (W-000071 تا W-000074) و رویدادهای آن کارها.
- ۸ سند آرشیو با نسخه‌ها، فایل‌ها و پیوندهایشان: نشان مُهرشده‌ی IG و سندهای کاتالوگ.
- نقشه‌ی ارتباط سرورها (`infra.network_links`، ‏40). `job_id` آن‌ها خالی شد.
- سابقه‌ی عدد KPIها (`governance.kpi_values`، ‏1700).
- حافظه‌ی کارمندها (`core.employee_memory`، ‏3). `run_id` آن‌ها خالی شد.
- **دفترهایی که جلوی اجرای دوباره و خرج را میگیرند:**
  - `ops.watch_runs`: درس پاک‌سازی ۱۰-۳۱ و ۵۰ میلیون توکن.
  - `growth.routine_runs`.
  - `growth.home_mornings`.
  - ارجاع این‌ها به کارهای پاک‌شده خالی شد.
- شرکت‌ها (5)، کارمندها (50)، استخدام `open/auto`، دپارتمان‌ها، منشورها، پروتکل‌ها، کارگروه و اتصال‌ها، ورودها و تنظیمات.

**پاک شد:**
- **فهرست WIPE کد**، جز آنچه بالا ماند. از جمله:
  - کارها (47) و اجراها.
  - ۴ کارت مُهرشده‌ی کار ویرانگر سرور، که اجرا شده بودند.
  - ۴ خروجی.
  - یافته‌ها و اعلان‌ها.
  - دفتر توکن (`llm.calls` و `llm.usage`).
  - جلسه‌ها، کارهای سرورها، فرمان و گزارش فرمان، یادداشت‌های مشاور، و callهای GPT/Gemini.
- **از ASK:**
  - تاریخچه‌ی پشتیبان (`backup.runs`، `backup.snapshots`، `backup.restore_tests`).
  - `ops.checks` و `ops.incidents`.
  - `owner.interactions`.
  - outbox منتشرشده.

**پس از پاک‌سازی:**
- `GET /api/v1/home` و `readiness` هر دو 200 بودند و `critical` = `[]`.
- همه‌ی کانتینرها `healthy` بودند و `make verify-live` سبز تمام شد (exit 0)، با همان دو GAP همیشگی.
- عددهای هزینه‌ی بخش ۷ و گزارش ۲۰.۱ فقط در همین گزارش‌ها میمانند. سنجش ۲۴ ساعت بعد فقط callهای بعد از پاک‌سازی را میبیند.
