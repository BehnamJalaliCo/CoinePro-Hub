# گزارش پرامپت ۱۹.۱: deploy «هیچ چیز بریده نشود» و حافظه‌ی Temporal

> Claude سرور هاب، ۲۰۲۶-۱۰-۳۱.
> - **وضعیت deploy:** 🟢 سبز. migration تازه‌ای نبود و دیتابیس روی **0034** ماند.
> - **شاخه‌ی زنده:** `server/p19-1-deploy`. این شاخه از سر شاخه‌ی اصلی، `claude/coinepro-hub-setup-hsvnw7`، روی 817b1cd ساخته شد و `server/p19-recipes` (b059ce6) را کامل در خود دارد.
> - **کد:** هیچ کدی ننوشتم. commit قالب‌بندی یا وابستگی هم لازم نشد.
> - **کلید توقف:** همان است که مالک گذاشت. هیچ شرکتی `engaged` نیست.
> - **سرورهای شرکت:** به هیچ‌کدام وصل نشدم.

## ۱. `make check`
- **کجا:** در worktree جدا با `.env` دورریختنی (`HQ_ENV_FILE`)، روی 817b1cd. ساعت 16:40 تمام شد.
- **نتیجه:** هر **۱۶ دروازه سبز** بود (`check: all 16 gates passed`).
  - **python test:** api ‏1163 قبول و ۶ رد شده، gateway ‏75 قبول و ۱ رد شده، سرویس‌ها 958 قبول (۵۶ دقیقه).
  - live، backup، audit و opa (191/191) هم سبز بودند.
- worktree بعد از سنجش برداشته شد.

## ۲. deploy (به وقت UTC)
| زمان | قدم | نتیجه |
|---|---|---|
| 16:40:58 | `make backup` | `/home/Hub/backups/20261031T164058Z` (سه دیتابیس) |
| 16:41 | migration | `alembic_version_api` = **0034**؛ تغییری لازم نبود |
| 16:41:38 | checkout `server/p19-1-deploy` و ساختن image‌ها | `hq.sh build api worker egress browser browser-web substitute-runner`، rc=0 |
| 16:41:55 تا 16:42:34 | بالا آوردن | api، worker، egress و browser-web (substitutes-web روشن است)، همه `healthy` |
| 16:42:39 | Temporal | `hq.sh up -d temporal`، یک restart یک‌باره برای env تازه. `healthy` |
| 16:44 | Prometheus | با SIGHUP reload شد و `containers.rules.yml` آمد |
| 16:45 تا 16:56 | `make verify-live` | rc=0. فقط همان دو GAP قبلی هست: رسیدن egress و searxng با IP، که قانون DOCKER-USER مالک است |

## ۳. Temporal
- **env تازه نشست:** `SQL_MAX_CONNS=10`، `SQL_MAX_IDLE_CONNS=5`. `GOMEMLIMIT=610MiB` و سقف 768m عوض نشدند.
- **حافظه (`docker stats --no-stream`):**
  - پیش از restart (16:42): **517.5 MiB** از 768 MiB.
  - بعد از restart (16:44): **255.2 MiB**.
  - یک ساعت بعد (17:43): **366.6 MiB** (۴۷.۷٪)، بی restart (`RestartCount` = 0).
- **لاگ:** هیچ خطای `dynamic config` یا `Persistence Max QPS` در لاگ temporal نیامد (شمارش در ۶۲ دقیقه: ۰).
- restart زمان‌بندی‌شده‌ای ساخته نشد.

## ۴. Prometheus
- `api/v1/rules` قانون `HqContainerMemoryNearCap` را دارد. پیکربندی بی‌خطا بار شد (`Completed loading of configuration file`).
- `api/v1/alerts` خالی است؛ هیچ هشداری روشن نیست.

## ۵. کار `models` بازیکن gpt
- یک کار `models` دستی در صف گذاشتم (همان ستون‌هایی که `ask_models` مینویسد).
- **نتیجه:** `done`. سه کار روزانه‌ی پیش از deploy (05:45، 10:32 و 12:00) با `the model listing was not JSON` شکست خورده بودند.
- **فهرست مدل‌های gpt:** ۱۰ مدل. هر ۸ مدل CLI در دسترس‌اند. دو مدل قدیمی (gpt-5.5 و gpt-5.3) ماندند، با علامت «در دسترس نیست».

## ۶. قدم بعدی مالک: runner سرورهای شرکت
- runner هر سرور باید به **0.2.0** برسد. نسخه‌ی قدیمی جواب Claude را در ۴۰۰۰ نویسه میبُرد.
- **کار Claude خود هر سرور است،** طبق `docs/server-prompts/COMPANY_SERVER_ACCESS_SETUP.md`، بخش «به‌روزرسانی runner». من به هیچ سروری وصل نشدم.
- **نسخه‌ی فعلی (`infra.servers`، همان که `GET /api/v1/infra/servers` نشان میدهد):**

| سرور | runner |
|---|---|
| fx-main | 0.1.0 |
| IG-Hub | 0.1.0 |
| Pro-Chart | 0.1.0 |
| ty-main | 0.1.0 |

هر چهار سرور مانده‌اند.
