# گزارش پرامپت ۲۰.۱: کاهش هزینه و متن GPT از چت وب

> Claude سرور هاب، ۲۰۲۶-۱۱-۰۳.
> - **وضعیت deploy:** 🟢 سبز. migration **0036** روی دیتابیس است.
> - **شاخه‌ی زنده:** `server/p20-1-deploy`.
>   - از `906403d` ساخته شد، نه از سر شاخه‌ی اصلی (بند ۰).
>   - روی آن یک commit فقط برای تست هست: `a3ff93e`، با اجازه‌ی مالک.
> - **کد:** هیچ منطقی را عوض نکردم.
> - **کلید توقف:** همان است که مالک ۱۱-۰۲ 13:31Z زد، یعنی **روشن** (`holding`).
> - **سرورهای شرکت:** به هیچ‌کدام وصل نشدم.
> - **کاتالوگ:** هیچ کاتالوگی شروع نکردم.
> - **Codex:** `code_review` خاموش ماند.

## ۰. کدام commit
- **بعد از `git pull`،** سر شاخه‌ی اصلی `c04dd1b` بود. این commit merge کار پرامپت ۲۱ است و migrationهای `0037` تا `0039` را هم دارد.
- **چرا از سر شاخه نساختم:**
  - پرامپت ۲۰.۱ گفته `alembic current` باید `0036` باشد.
  - پرامپت ۲۱ هم ۲۰.۱ را پیش‌نیاز خودش میداند و جدا deploy میشود.
- **پس:** شاخه را از `906403d` ساختم. این آخرین commit شاخه‌ی اصلی است که ۲۰.۱ را دارد (merge ‏`2741c81`، به‌علاوه‌ی اصلاح mypy ‏`treasury.usage` و تنظیم CI) و هیچ چیزی از ۲۱ ندارد.

## ۱. `make check` و تست مرورگر
- **کجا:** worktree جدا در scratchpad، روی `906403d`. از 12:57 تا 14:28.
- **سبزها:**
  - gitleaks، compose، memory budget، lint و ruff/mypy.
  - audit وابستگی‌ها: هیچ CVE تازه‌ای نبود.
  - سرویس‌ها: 1165 قبول. gateway و runner: 79 قبول.
- **api: ‏1006 قبول، ۳ شکست (۶۴ دقیقه):**
  - `test_p12f_join::test_the_chain_runs_through_prompt_11_then_prompt_12` و `test_p13f_join::test_a_round_trip_keeps_a_card_of_every_later_kind`:
    - هر دو کهنه بودند و هنوز سر migration را `0035` میدانستند.
    - شاخه‌ی اصلی همین دو را بعداً در merge پرامپت ۲۱ برای `0039` درست کرده است (`96c7dda`، `87f7b68`).
    - **با اجازه‌ی مالک** در commit جدای `a3ff93e` فقط عدد سر به `0036` رسید. منطق دست نخورد.
  - `test_runs_hard::test_a_long_streamed_answer_keeps_beating_and_is_stored`:
    - این تست زمان‌بندی است. بزرگ‌ترین فاصله‌ی ضربان 0.545 ثانیه شد و سقفش 0.5 است.
    - زیر بار check اتفاق افتاد. در اجرای دوباره سبز شد.
  - **اجرای دوباره‌ی هر سه فایل** بعد از اصلاح: **۲۳ از ۲۳ قبول.**
- **live:** فقط قرمز همیشگی worktree: `media-render: the sandbox probe failed`، چون worktree `.env` ندارد. روی خود هاب `verify-live` سبز است (بند ۳).
- **`services/scripts/browser-test.sh`:** **۱۹ از ۱۹ قبول** (۳۳ ثانیه)، همراه با تست صفحه‌ی ChatGPT که فقط برچسب فارسی دارد.
- worktree پیش از deploy برداشته شد.

## ۲. مصرف پیش از deploy (فقط خواندن، `default_transaction_read_only=on`)
پرس‌وجوی «سنجش» خود پرامپت را در 12:57:39Z اجرا کردم.

| پنجره | نتیجه |
|---|---|
| یک ساعت گذشته | **۰ ردیف** |
| ۲۴ ساعت گذشته | **۰ ردیف** |

- **آخرین ردیف `llm.calls`:** ۱۱-۰۲ 10:30:01Z.
- **چرا صفر:** از آن وقت `claude-max` سهمیه‌ی هفتگی ندارد (گزارش ۲۰). از ۱۱-۰۲ 13:31Z هم کلید توقف روشن است.
- **برای مقایسه، ۷ روز گذشته:**

| حوزه | call | توکن |
|---|---|---|
| catalogue | 24 | 50,271,146 |
| oversight | 17 | 505,503 |
| advisor | 20 | 299,539 |
| work | 7 | 204,703 |
| media | 2 | 80,122 |
| meetings | 2 | 76,828 |
| council | 8 | 49,330 |

## ۳. deploy (به وقت UTC)
| زمان | قدم | نتیجه |
|---|---|---|
| 14:37:05 | `make backup` | `/home/Hub/backups/20261103T143705Z` (سه دیتابیس) |
| 14:37:38 | checkout `server/p20-1-deploy` در checkout زنده | `a3ff93e` |
| 14:37:40 تا 14:38 | ساختن image‌ها | `hq.sh build api worker gateway egress browser-web`، بعد `hq.sh build browser` |
| 14:38:06 | migration | `hq.sh up --no-deps api-migrate`: `Running upgrade 0035 -> 0036`. `alembic_version_api` = **0036** |
| 14:38 تا 14:39 | بالا آوردن | `hq.sh up -d --no-deps --wait api worker gateway egress browser-web`: هر پنج `healthy` |
| 14:39 تا 14:55 | `make verify-live` | **rc=0**. فقط همان دو GAP قبلی: رسیدن egress و searxng با IP، که قانون DOCKER-USER مالک است |

- **چرا `browser` هم ساخته شد:** سرویس `browser-web` خودش build ندارد و image ‏`coinepro-hq/browser:0.1.0` را به کار میبرد. آن image ‏`egress/src` (و `browser_web.py` تازه) را در خودش دارد. پس بدون ساختن `browser`، کد تازه به `browser-web` نمیرسید.
- **env:**
  - در `.env` چیزی اضافه نکردم.
  - در `api` و `worker` هر دو متغیر نشسته‌اند: `AGENT_COMPANY_DAILY_TOKEN_CAP=400000`، `HQ_CATALOGUE_RUN_TOKENS=1500000`.
- **فایل‌هایی که مستقیم mount شده‌اند:**
  - `infra/opa/policy/watch.rego` با `--watch` بی خطا بارگذاری شد.
  - `agents/` تازه است.
  - دستور وب `infra/egress/recipes/chatgpt-web.yaml` در egress نسخه‌ی **`2026-11-02.1`** دارد.

## ۴. سنجش‌های فوری
| سنجش | نتیجه |
|---|---|
| `substitutes.players` برای `gpt`: `capabilities.text` | **بله**: `web` (`{"text":"web","image":"web","video":"off"}`) |
| جایگاه‌های متنی `via = web` | **بله**: `advisor_second_opinion`، `overseer_cross_check`، `assistant_errand` (و `creative`) |
| `code_review` خاموش | **بله**: `via = cli`، `enabled = false` |
| ردیف‌های Audit مایگریشن | **بله**: ۴ ردیف `substitute.seats` (14:38:06)، و `oversight.protocol_update` برای `PR-142@2` |
| `PR-142`: زمان‌بندی و تقویم | **بله**: `FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=30`، تقویم `jalali`، نسخه‌ی 2 |
| زمان‌بندی Temporal ‏`protocol-PR-142` | **بله**: هر روز 09:30 `Asia/Tehran`. اجرای بعدی ۱۱-۰۴ 06:00Z. روزی که اول ماه شمسی نیست، خود اجرا `not_its_jalali_day` میدهد |
| ردیف تازه‌ی `catalogue:` در `ops.watch_runs` بعد از deploy | **خیر**، هیچ. آخرین ردیف ۱۰-۳۱ 20:30 است |
| `treasury.usage?period=week` | **سنجیده نشد** (پایین را ببینید) |

- **`treasury.usage`:**
  - توکن یک مدیر فقط در یک اجرای ایجنت ساخته میشود. کلید توقف روشن است و اجرای تازه هم کار تازه میسازد. پس طبق خود پرامپت «سنجیده نشد».
  - کد تازه `period` را `day|week|month` میپذیرد. `department` و `role` هم دارد.
  - تست‌های `test_p20_1_cost.py` در `make check` سبز بودند.
- **وضعیت `gpt` در جدول:**
  - `status = limited` هنوز از سهمیه‌ی Codex مانده است: «try again at Nov 4th, 2026 3:05 PM».
  - طبق ۲۰.۱، آماده بودن متن GPT حالا از ورود وب خوانده میشود (`web_state = signed_in`). سهمیه‌ی Codex دیگر چت وب را نمیبندد.
  - `recipe_version` در ردیف هنوز `2026-10-31.5` است. با اولین کار وب به `2026-11-02.1` میرسد.

## ۵. GPT از وب
- **ورود وب:** `web_state = signed_in`. آخرین کار موفق وب ۱۰-۳۱ 12:57Z بوده. `web_last_failure` خالی است.
- **call آزمایشی (HQ-PA، `assistant_errand`، «سلام؛ فقط بنویس: آزمایش"):** ⏸ **انجام نشد.**
  - **علت:** کلید توقف روشن است. `seat_call` قفل هلدینگ را پیش از هر چیز میسنجد. call بی هیچ تماسی `skipped` با `holding_locked` میشد.
  - به کلید توقف دست نزدم.
  - **قدم بعد:** هر وقت مالک کلید را برداشت، یا گفت فقط برای همین آزمایش بردارم، همین call را میزنم. `via`، وضعیت، جواب، `recipe_version` و `web_last_failure` را اضافه میکنم.
- **call تازه به Codex (`via = cli`) بعد از deploy:** `SELECT count(*) … created_at > '2026-11-03T14:37:38Z'` = **۰**.

## ۶. هزینه، پیش و بعد
پنجره‌ها از زمان deploy (14:37:38Z) حساب شده‌اند.

| حوزه | پیش (۱ ساعت) | پیش (۲۴ ساعت) | ۱ ساعت بعد | ۲۴ ساعت بعد |
|---|---|---|---|---|
| همه‌ی حوزه‌ها | ۰ | ۰ | ۰ (۰ ردیف، سنجیده 15:38Z) | در انتظار (۱۱-۰۴ 14:38Z؛ در این نشست سنجیده نشد) |

- **قبولی `catalogue` = ۰:** 🟢 در یک ساعت بعد ۰ است. در ۲۴ ساعت بعد هنوز سنجیده نشده. در یک ساعت بعد هم ردیف تازه‌ی `catalogue:` در `ops.watch_runs` ۰ و call تازه‌ی Codex ۰ بود.
- **قبولی «`oversight` بیشترین سهم نیست»:** 🟢 در یک ساعت بعد هیچ حوزه‌ای مصرف نداشت.
- **هشدار:** تا کلید توقف روشن است و سهمیه‌ی `claude-max` تا ۱۱-۰۵ 00:00Z نیامده، عددها صفر میمانند. پس این سنجش درباره‌ی رفتار سقف‌ها زیر بار چیزی ثابت نمیکند. اولین سنجش معنادار بعد از برداشتن کلید است.

## ۷. runner سرورهای شرکت (از `infra.servers`، فقط خواندن)
| شرکت | سرور | runner فعلی | آخرین دیده‌شدن |
|---|---|---|---|
| FX | fx-main | 0.2.1 | ۱۱-۰۳ 14:59Z |
| IG | IG-Hub | 0.2.1 | ۱۱-۰۳ 14:59Z |
| PC | Pro-Chart | 0.2.1 | ۱۱-۰۳ 15:00Z |
| TY | ty-main | 0.2.1 | ۱۱-۰۳ 14:59Z |

هیچ‌کدام هنوز `0.2.2` نیست. بی 0.2.2، سقف توکن به نشست نمیرسد و فقط سقف ۲۵ دور، کاتالوگ را محدود میکند.

## ۸. قدم بعدی مالک
1. **runner 0.2.2 روی هر چهار سرور:**
   - کار Claude خود هر سرور است، طبق بخش «به‌روزرسانی runner» در `docs/server-prompts/COMPANY_SERVER_ACCESS_SETUP.md`.
   - در پایان `hq-runner --version` باید `0.2.2` باشد.
2. **کلید توقف:** هر وقت خواستید بردارید. بعد به من بگویید تا call آزمایشی GPT از وب (بند ۵) را بزنم.
3. **پرامپت ۲۱:** حالا پیش‌نیازش (`0036`) سر جایش است.
