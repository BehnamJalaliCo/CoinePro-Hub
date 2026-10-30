# گزارش پرامپت ۱۷.۱: deploy کد runnerها (سبز)

> Claude سرور هاب، ۲۰۲۶-۱۰-۳۰.
> - **وضعیت:** 🟢 سبز. کد پرامپت ۱۷ روی هاب زنده است و migration آن **0032** است.
> - **شاخه:** `server/p17-1-deploy`. شاخه‌ی اصلی در e991d64، یعنی همراه پنج اصلاح سشن مشورت، در آن ادغام شد (343e6bb). جز این گزارش، هیچ کدی عوض نشد.
> - **checkout زنده:** حالا روی `server/p17-1-deploy` است.
> - **کلید توقف:** همان‌طور که مالک گذاشته بود ماند. هلدینگ (HQ) `engaged` است، نسخه‌ی ۴، با یادداشت خود مالک. FX، PC و TY `released` هستند.
> - **سرورهای شرکت:** به هیچ‌کدام وصل نشدم. runner روی هاب نصب نشد.
> - **اجرای اول:** متوقف شده بود. خلاصه‌اش در §۶ است.

## ۱. `make check` (اجرای دوم، در worktree جدا)
- **محل اجرا:** یک worktree موقت، نه checkout زنده. زمان: 19:43:54 تا 21:00:37Z (۷۷ دقیقه).
- **۱۵ دروازه از ۱۶ سبز:**
  - gitleaks، compose-config، ports، compose-rules، memory-budget، shellcheck، yamllint، hadolint، infra، backup، provisioning، python lint و python audit.
  - opa: 183/183، پوشش ۱۰۰٪.
  - python test:
    - سرویس‌ها: 1161 passed (پوشش 88.9٪).
    - stt: 74 passed.
    - apps/api: 925 passed، پوشش کل 82.9٪ و منطق دامنه ۹۱٪.
  - **پنج قرمز اجرای اول همه سبز شدند:** test_identity، دو آزمون fresh start، جلسه‌ها (vote) و gitleaks. دو دروازه‌ی حافظه هم سبز شدند.
- **live: یک FAIL، از worktree و نه از کد:**
  - پیام: «media-render: the sandbox probe failed (no answer)».
  - **علت:** worktree فایل `infra/compose/.env` ندارد. `live.sh` برخلاف دروازه‌های دیگر `ensure_env` را صدا نمیزند. پس `hq.sh` با پیام `.env not found` میایستد و سنجش جوابی نمیگیرد.
  - **سنجش جدا:** همین سنجش با یک `.env` موقت (`gen-env.sh`) سبز شد: `{"interfaces": ["lo"], "reached": [], "isolated": true}`.
  - **روی سرور زنده:** `make verify-live` همین سنجش را سبز گذراند (§۴). در ۱۵.۲ هم همین اتفاق افتاده بود.

## ۲. deploy (۲۰۲۶-۱۰-۳۰، به وقت UTC)
| زمان | قدم | نتیجه |
|---|---|---|
| 21:13:29 | `make backup` | `/home/Hub/backups/20261030T211329Z`: پایگاه‌های hq (5.6M)، temporal (60M) و temporal_visibility (1.7M)، فایل‌ها و لنگرهای audit |
| 21:13:50 | checkout `server/p17-1-deploy` در `/home/Hub/CoinePro-Hub` | تمیز |
| 21:13:54 تا 21:15:32 | `make up` (پروفایل full) | rc=0. `api-migrate` به 0032 رسید. api، worker، gateway و بقیه دوباره ساخته شدند و همه سالم‌اند |
| 21:15:50 تا 21:15:56 | ری‌استارت Caddy | سالم. بلوک `/api/v1/runners/*` و SSE ترمینال بارگذاری شد |
| 21:16:17 تا 21:28:26 | `make verify-live` | rc=0 (§۴) |

- **چرا Caddy ری‌استارت شد و reload نشد:**
  - `api-on.caddy` به‌صورت یک فایل تکی به کانتینر وصل است (bind mount). checkout فایل را با inode تازه مینویسد، ولی کانتینر هنوز inode قبلی را میبیند.
  - بعد از `make up`، داخل Caddy صفر خط `runners` بود؛ در ریپو چهار خط.
  - `caddy reload` همان فایل قدیمی را میخواند. پس کانتینر ری‌استارت شد: حدود ۶ ثانیه قطعی 80/443.
  - بعد از ری‌استارت، داخل کانتینر هم چهار خط `runners` بود.
  - **هشدار Caddy:** چهار هشدار بی‌خطر «Unnecessary header_up X-Forwarded-For» ثبت شد.
- **OPA:** با `--watch` خودش سیاست‌ها را بارگذاری میکند. این را از داخل api از خود OPA پرسیدم:
  - `hq.internal.server_ops` = `server.read`، `server.run` (از `servers.rego`).
  - `hq.config.a2_grants`: ابزارهای `server.*` در ceo، manager، employee و overseer هستند (از `data.json` تازه).
- **دیتابیس:** شش جدول تازه هستند: `infra.runner_pairings`، `infra.runners`، `infra.server_jobs`، `infra.server_job_events`، `infra.network_links` و `control.server_policy`.
- **لاگ‌ها:** از 21:14Z در api، worker و gateway صفر خطا و صفر Traceback.

## ۳. migration ۰۰۳۲ و downgrade آن
- **زنجیره:** `revision = "0032"`، `down_revision = "0031"`.
- **downgrade این‌ها را برمیدارد:**
  - شش جدول تازه و تابع `infra.server_jobs_guard()`.
  - ستون‌های `server_id` و `cwd` از `workshop.sessions`.
  - ستون‌های تازه‌ی `infra.servers`.
  - CHECKهای قبلی با `NOT VALID` برمیگردند. ردیف‌های قبلی همان‌طور که هستند میمانند.
- **downgrade این‌ها را نگه میدارد:**
  - نوع `server_destructive` در CHECK کارت‌ها میماند، پس کارت‌هایش پاک نمیشوند.
  - ردیف‌های `infra.servers` هم میمانند.
- **اثرش:** داده‌ی جفت‌سازی، runnerها، کارها و نقشه‌ی شبکه با downgrade از بین میرود. پیش از downgrade واقعی، بکاپ لازم است.
- **آزمون:**
  - آزمون رفت‌وبرگشت در `make check` سبز بود (`test_p13f_join`: پایین تا 0009 و دوباره بالا تا head).
  - `test_p12f_join` (یک head واحد) هم سبز بود.
- **روی دیتابیس زنده** فقط upgrade اجرا شد.

## ۴. `verify-live` و سه سنجش پرامپت
- **`make verify-live`:** rc=0.
  - «media-render has no network at all».
  - «/internal are 404 at the edge».
  - همان دو GAP قبلی هست: رسیدن egress و searxng با IP. بستنشان قانون DOCKER-USER مالک است.
- **سه سنجش:**
  1. `GET https://hq.coinepro.com/api/v1/runners/pair`: **405**.
  2. همین مسیر از `10.10.1.4:443` (`--resolve hq.coinepro.com:443:10.10.1.4`): **405**. گواهی همان است: `CN=hq.coinepro.com`، Let's Encrypt YE2، `verify ok`.
  3. `/internal`: **404**. `/internal/health` و `/internal/x` از نشانی خصوصی هم 404 دادند.
- **سنجش اضافه:** `POST /runners/pair` بدون بدنه 422 میدهد. این مسیر عمومی است و آزمون test_identity هم همین را میخواهد.

## ۵. کلید توقف
پیش و پس از deploy یکسان است:
- **HQ:** `engaged`، نسخه‌ی ۴، از 2026-10-30 01:34:58Z، با یادداشت مالک: «هلدینگ تا نصب نسخه‌ی آخر متوقف بماند؛ خود مالک روشن میکند».
- **FX، PC و TY:** `released`.

## ۶. اجرای اول (متوقف شد)
- **چه شد:** `make check` روی 45d81c5 قرمز بود و deploy انجام نشد. گزارش آن اجرا در تاریخچه‌ی همین فایل است (03bdc7b).
- **پنج اصلاح سشن مشورت:** 55cabea (identity)، 66c1d80 (fresh start)، d360607 (جلسه‌ها)، 24f6126 (gitleaks) و e991d64 (دروازه‌های حافظه).
- **اشتباه من در آن اجرا:**
  - شاخه را در checkout زنده ساختم. ۸۱ دقیقه (17:23:56 تا 18:45:08Z) منشورها و سیاست‌های OPA شاخه‌ی اصلی روی کد ۱۵.۲ بارگذاری بود.
  - برش گرداندم. هیچ اجرای ایجنتی نبود و خطای تازه‌ای ثبت نشد.
  - این بار `make check` در worktree جدا اجرا شد.

## ۷. قدم بعدی
1. **مالک:**
   - نصب runner روی هر سرور با `docs/server-prompts/COMPANY_SERVER_ACCESS_SETUP.md`.
   - آزاد کردن کلید توقف هلدینگ هر وقت که خودتان صلاح دانستید.
2. **پیشنهاد کوچک (`scripts/` و `infra/` مال سرور هاب است؛ در پرامپت بعد، اگر مالک خواست):**
   - `live.sh` مثل دروازه‌های دیگر `ensure_env` را صدا بزند تا در worktree هم سبز شود.
   - خط‌های اضافه‌ی `header_up X-Forwarded-For` در `api-on.caddy` برداشته شوند.
   - Caddy پوشه‌ی `infra/caddy` را mount کند، نه فایل‌های تکی را. آن وقت deploy با `caddy reload` و بدون قطعی انجام میشود.
