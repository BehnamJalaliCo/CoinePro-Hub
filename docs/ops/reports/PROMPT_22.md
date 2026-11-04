# گزارش پرامپت ۲۲: خط تولید و رشد (مرحله‌ی ۱)

> Claude سرور هاب، ۲۰۲۶-۱۱-۰۴.
> - **وضعیت deploy:**
>   - مرحله‌ی ۱ 🟢 سبز. migration **0042** روی دیتابیس است.
>   - مرحله‌ی ۲ انجام **نشد**، چون فقط با دستور مالک است.
> - **شاخه‌ی زنده:** `server/p22-deploy`.
>   - **پایه:** از `cc78707a` ساخته شد، یعنی merge پرامپت ۲۲ در شاخه‌ی اصلی.
>   - **چرا نه سر شاخه:** سر شاخه‌ی اصلی (`b32e99c0`) پرامپت ۲۳ را هم دارد (migration 0043 و 0044). مثل ۲۰.۱، فقط تا پرامپت ۲۲ deploy شد.
> - **کد:** یک اصلاح پیکربندی در یک commit جدا، با اجازه‌ی مالک (بخش ۳). هیچ commit قالب‌بندی یا وابستگی لازم نشد.
> - **`.env`:** فقط کلیدهای غایب با `make env` اضافه شد، با اجازه‌ی مالک (بخش ۲). `HQ_LINES` گذاشته **نشد**.
> - **کلید توقف:** همان است که مالک گذاشت. هلدینگ (`HQ`) از ۱۱-۰۳ 19:51Z **روشن** است («توقف فوری به دستور مدیر کل»). به آن دست نزدم.
> - **دست نزدم به:**
>   - پاکت ماه و سقف‌ها.
>   - پروفایل‌های `automations` (n8n) و `newsletter` (Listmonk).
>   - هیچ سرور شرکتی و هیچ کاتالوگ.
>   - جایگاه Codex، `media-on` و `tts-on`.

## ۱. `make check` و تست مرورگر
- **کجا:** worktree جدا در scratchpad، روی `cc78707a`. از 12:59 تا 14:34.
- **سبزها:**
  - gitleaks، compose-config، ports، compose-rules، memory-budget، shellcheck، yamllint، hadolint، opa (223 از 223)، infra، backup، provisioning و python lint.
  - audit وابستگی‌ها: هیچ CVE تازه‌ای نبود.
- **تست‌ها:**
  - api: ‏1233 قبول، ۳ رد شده (۷۱ دقیقه).
  - سرویس‌ها: 1178 قبول.
  - gateway و runner: ‏79 قبول.
  - این بار هیچ تست ناپایداری قرمز نشد.
- **live:** فقط همان قرمز همیشگی worktree: `media-render: the sandbox probe failed`. علتش این است که worktree فایل `.env` ندارد. روی خود هاب `verify-live` سبز است (بخش ۵).
- **`services/scripts/browser-test.sh`:** **۱۹ از ۱۹ قبول.**

## ۲. مانع اول: رمزهای n8n در `.env` نبودند (پیش از deploy)
- **چه دیدم:** در compose تازه، سرویس `n8n` سه رمز را با `:?` اجباری کرده است:
  - `N8N_DB_PASSWORD`
  - `N8N_ENCRYPTION_PASSWORD`
  - `N8N_SIGNING_PASSWORD`
- **نتیجه:** Docker Compose همه‌ی سرویس‌ها را میخواند، حتی سرویس پروفایل خاموش را. پس با `.env` هاب، هیچ فرمانی از `hq.sh` اجرا نمیشد، حتی `config`، و build و up هم شکست میخوردند.
- **چرا `make check` این را نگرفت:** گیت compose-config با یک `.env` تازه از `gen-env.sh` اجرا میشود که همه‌ی کلیدها را دارد.
- **کاری که کردم (با اجازه‌ی مالک):**
  - `infra/compose/gen-env.sh --output infra/compose/.env`، یعنی همان `make env`.
  - این ابزار فقط کلیدهای غایب را اضافه میکند و هیچ خط موجودی را عوض نمیکند.
  - **رمزهای تصادفی:** `N8N_DB_PASSWORD`، `N8N_ENCRYPTION_PASSWORD`، `N8N_SIGNING_PASSWORD`، `LISTMONK_DB_PASSWORD` و `LISTMONK_ADMIN_PASSWORD`.
  - **کلیدهای خالی (یعنی خاموش):** `HQ_AUTOMATIONS` و `HQ_NEWSLETTER`.
  - هیچ مقداری چاپ نشد. فایل همچنان `600` است.
- **اثر:** هیچ. هر دو پروفایل خاموش‌اند. `db-provision` در این deploy اجرا نشد (`--no-deps`)، پس نقش و دیتابیس n8n هنوز ساخته نشده‌اند. `make n8n-on` خودش هم همین `gen-env.sh` را اجرا میکرد.
- **پیشنهاد برای Claude ساخت:** در compose برای رمزهای n8n از `:-` استفاده شود، مثل Listmonk، یا گیت compose-config با یک `.env` قدیمی‌تر هم اجرا شود.

## ۳. مانع دوم: شبکه‌ی `hq-newsletter` نشانی `hq-ocr` را داشت
- **چه شد:** اولین `up` در 14:36:16Z این خطا را داد:
  ```
  failed to create network hq-newsletter: Error response from daemon: invalid pool request: Pool overlaps with other one on this address space
  ```
- **علت:** در `infra/compose/compose.yaml` شبکه‌ی تازه‌ی `hq-newsletter` نشانی `172.30.24.0/24` گرفته بود. این همان نشانی شبکه‌ی موجود `hq-ocr` (پرامپت ۱۴) است.
- **اثر روی هاب:** هیچ. api و worker عضو `hq-newsletter` هستند و بالا نیامدند. کانتینرهای قدیمی همچنان سالم کار کردند، حدود سه دقیقه. migration پیش از آن روی 0042 رفته بود.
- **اصلاح (با اجازه‌ی مالک):** commit ‏`7f05f972`:
  - `hq-newsletter` به `172.30.26.0/24` رفت.
  - این نشانی آزاد است و هیچ کد یا سنجشی به آن اشاره نمیکند.
  - `hq-newsletter-out` همان `172.30.25.0/24` ماند، که آزاد بود.
- **پیشنهاد برای Claude ساخت:**
  - این commit به شاخه‌ی اصلی برود.
  - گیت `compose-rules` نشانی تکراری بین شبکه‌ها را رد کند.

## ۴. deploy (UTC)
- **14:35:10:** `make backup` → `/home/Hub/backups/20261104T143510Z` (۳ دیتابیس).
- **14:35:47:** checkout شاخه‌ی `server/p22-deploy`.
- **`make llm-provision`:**
  - policyهای OpenBao دوباره نوشته شدند. `hq-api` و `hq-worker` حالا خواندن `kv/hq/n8n` و `kv/hq/newsletter/api` را دارند.
  - هیچ رمزی ساخته یا چاپ نشد.
- **14:35:55:** build ‏`api` (همان image ‏worker)، `llm-router`، `egress` و `browser`.
  - `browser-web` با image ‏`browser` اجرا میشود. `browser_web.py` (recipeهای تازه) هم در همان image است، پس `browser` هم ساخته شد.
  - `gateway` هم در فهرست build بود، ولی کدش در ۲۲ عوض نشده و image آن همان ماند.
- **14:36:09:** `up --no-deps api-migrate`: ‏0039 → 0040 → 0041 → 0042، و `seed done`.
- **14:36:16:** `up` به خطای شبکه خورد (بخش ۳).
- **14:39:05:** بعد از اصلاح، `up -d --no-deps --wait api worker gateway llm-router egress browser browser-web`.
  - همه `healthy` شدند.
  - `hq-newsletter` ساخته شد: `172.30.26.0/24`، internal، با دو عضو api و worker.
- **`make verify-live`:** 14:39 تا 14:51، **rc=0**. هیچ FAIL نبود. دو خط GAP همان دو خط همیشگی ۲۱ است (egress و SearXNG با IP؛ بستنش قانون DOCKER-USER مالک است).

## ۵. سنجش‌های مرحله‌ی ۱
- **`alembic current`:** **0042.**
- **قالب‌ها:**
  - `GET /api/v1/line-templates` → 200 و **۷ قالب**: `instagram_reel`، `instagram_story`، `newsletter`، `site_article`، `telegram_post`، `youtube_long` و `youtube_short`.
  - `GET /api/v1/kits` → 200 و **۲ kit**: `content_brand` و `saas_product`.
- **زمان‌بندی‌ها در Temporal:** هر چهار هستند و هیچ‌کدام مکث نیستند.

  | زمان‌بندی | فاصله | نتیجه |
  |---|---|---|
  | `hq-lines-tick` | ۵ دقیقه | اجرای 14:40Z: `{"skipped": "lines_off"}`، یعنی کاری نکرد. |
  | `hq-ops-tick` | ۵ دقیقه | اجرای 14:40Z: تبلیغات و اتوماسیون هر دو `holding_locked`. کلید توقف هلدینگ روشن است، پس هیچ کاری نکرد. |
  | `hq-newsletter-read` | ساعتی | اولین اجرا 15:00Z است. |
  | `hq-seo-read` | روزانه | اولین اجرا ۱۱-۰۵ 01:30Z است. |

- **API (فقط خواندن، به روش ۲۱):**

  | مسیر | جواب |
  |---|---|
  | `GET /api/v1/companies/TY/lines` | 200، صفر خط |
  | `GET /api/v1/campaign-calendar?from=2026-11-01&to=2026-11-30` | 200، صفر مورد |
  | `GET /api/v1/automations` | 200، صفر |
  | `GET /api/v1/companies/TY/ads` | 200، صفر کمپین |
  | `GET /api/v1/companies/TY/keywords` | 200، صفر |
  | `GET /api/v1/companies/TY/newsletter` | 200، با `"active": false` و پیام «خبرنامه هنوز روشن نیست…» |

  - **campaign-calendar:** بی `from` و `to` جواب 422 `validation_failed` است. هر دو پارامتر اجباری‌اند.
  - **newsletter:** پرامپت 409 ‏`channel_not_configured` را میخواست. کد جواب 200 میدهد، با `active: false`. یعنی خاموش است، فقط شکل جوابش با پرامپت فرق دارد. **پیشنهاد برای Claude ساخت:** پرامپت یا کد یکی شوند.
- **خانه‌ی مالک:** `GET /api/v1/home` → 200 و `critical: []`.
- **کلیدها در کانتینرها:**
  - api و worker: `HQ_LINES=off` و `HQ_NEWSLETTER=off`.
  - worker: `HQ_N8N_URL` خالی است.
  - `HQ_GROUPS=on` حالا در api هم هست، چون api دوباره از `.env` ساخته شد. در ۲۱ فقط worker آن را داشت.
- **ورود ChatGPT در مرورگر هاب:** وارد است. `gpt` با `web_state=signed_in`، آخرین کار موفق ۱۱-۰۳ 16:11Z، recipe ‏`2026-11-02.1`.
- **حافظه (14:50Z):**
  - سرور: کل 15608 MiB، استفاده‌شده 5048، **در دسترس 10559 MiB**.
  - **روشن الان:** پروفایل `full` با `substitutes`، `substitutes-web` و `stt` (`stt` فقط هر وقت لازم شد بالا میآید). جمع سقف حافظه‌ی این‌ها **12220 MiB** است. بودجه 12486 MiB است، یعنی ۸۰٪ رم این سرور.
  - **با `automations` (n8n):** 12988 MiB. **502 MiB بیشتر از بودجه، جا نمیشود.** `make n8n-on` همین حالا رد میشود.
  - **با `newsletter` (Listmonk):** 12732 MiB. **246 MiB بیشتر از بودجه، جا نمیشود.**
  - **گیت `make check`** هر پروفایل را فقط تنها با `full` میسنجد: `full+automations` 11408 و `full+newsletter` 11152، هر دو در بودجه. ولی روی هاب `substitutes` و `substitutes-web` هم روشن‌اند.
  - **تصمیم با مالک است.** برای هر کدام، یکی از پروفایل‌های روشن باید خاموش شود، یا سقف‌ها کوچک شوند.
- **آزمون رفت‌وبرگشت migration:** روی هاب انجام نشد، همان‌طور که پرامپت گفته بود.

## ۶. قدم بعدی مالک (از `builder-w2/OWNER_STEPS.md`)
1. **ورودها در مرورگر هاب:**
   - `make aistudio-web-login` با حساب گوگل پرو.
   - `make pinterest-web-login`.
   - ChatGPT وارد است و لازم نیست.
2. **IG-Hub:**
   - فایل `docs/server-prompts/IGHUB_PUBLISH_API.md` را به Claude خود IG-Hub بدهید.
   - بعد در اپ: اتصال اینستاگرام. کلید را با `make growth-secret` بگذارید.
3. **کلیدهای دیگر، هر وقت خواستید:** یوتیوب، وردپرس، و Google Ads و Meta Ads.
4. **n8n و خبرنامه:** با پروفایل‌های روشن الان جا نمیشوند (بخش ۵). اول تصمیم بگیرید کدام پروفایل خاموش شود.
5. **کلید توقف هلدینگ:** هنوز روشن است. تا روشن است، تبلیغات و اتوماسیون‌ها و هیچ کار ایجنتی اجرا نمیشود.
6. **اولین خط تولید:**
   - در اپ، قالب «ریلز اینستاگرام» را بردارید و «آزمایش کامل» را بزنید.
   - اگر سبز بود، بگویید «مرحله‌ی ۲ پرامپت ۲۲ (روشن کردن خط‌ها)» تا `HQ_LINES=on` شود.

## ۷. سنجش‌های زمان‌دار
- **مصرف ۲۴ ساعت بعد:** ۱۱-۰۵ 14:39Z، با پرس‌وجوی ۲۰.۱ و حوزه‌ی `lines` جدا.
- **وضع فعلی خط‌ها:** تا `HQ_LINES` خاموش است، این حوزه صفر میماند.
