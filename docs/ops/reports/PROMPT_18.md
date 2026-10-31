# گزارش پرامپت ۱۸: deploy runnerها، بازیکن، شورا و صدا به متن (سبز)

> Claude سرور هاب، ۲۰۲۶-۱۰-۳۱.
> - **وضعیت:** 🟢 سبز. migration **0033** روی دیتابیس است.
> - **شاخه:** `server/p18-deploy`. شاخه‌ی اصلی در 94fde92 در آن ادغام شد، به‌علاوه‌ی سه commit کوچک من در بخش ۲. checkout زنده روی همین شاخه است.
> - **کلید توقف:** همان است که مالک گذاشت. HQ `engaged` (نسخه‌ی ۴). FX، IG، PC و TY `released`.
> - **سرورهای شرکت:** به هیچ‌کدام وصل نشدم.

## ۱. `make check`
همه‌ی اجراها در worktree جدا بود، با یک `.env` دورریختنی (`HQ_ENV_FILE`)، و worktree هر بار با `git worktree remove` برداشته شد.

1. **اجرای اول (4df8b7f):** قرمز بود.
   - دو آزمون apps/api نقش‌های تازه‌ی TECH را نمیشناختند.
   - pypdf هفت CVE داشت.
   - سشن مشورت هر دو را در 94fde92 درست کرد.
2. **اجرای دوم (bb522fb، از 00:09 تا 01:27Z):**
   - **سبز:**
     - python test: سرویس‌ها 1161، stt ‏74، apps/api ‏944، همه قبول.
     - live.
     - بقیه‌ی دروازه‌ها.
   - **دو قرمز:**
     - **python lint:** خط تازه‌ی `tests/test_p13a_departments.py:57` برای `ruff format` بلند بود.
     - **python audit:** چهار CVE تازه در `pyasn1 0.6.4` بود: CVE-2026-119194 تا 119197.
   - هر دو با اجازه‌ی مالک در چت درست شدند (بخش ۲). بعد `python.sh lint` و `python.sh audit` دوباره سبز شدند.

## ۲. سه commit کوچک من (با اجازه‌ی مالک)
1. **90855a5:** فقط قالب‌بندی همان یک assert، بدون تغییر منطق.
2. **c870018:** `pyasn1` به 0.6.5 رسید، در `apps/api/requirements.lock` و `requirements-test.lock`، با hashهای PyPI.
   - در image زنده: `pyasn1 0.6.5` و `pypdf 6.21.4`.
3. **d8dd574 (`services/stt/Dockerfile`):**
   - **ایراد:** `COPY --chmod=0644 stt/model.lock.json` پوشه‌ی تازه‌ی `/app/stt` را هم با 0644، یعنی بدون x، میساخت. پس uid 10001 به `/app/stt/src` نمیرسید و `make stt-on` با خطای `No module named hq_stt` میایستاد.
   - **اصلاح:** کپی سورس‌ها جلوتر رفت. بعد `import hq_stt.fetch` سبز شد.

## ۳. deploy (۲۰۲۶-۱۰-۳۱، به وقت UTC)
| زمان | قدم | نتیجه |
|---|---|---|
| 01:29:53 | `make backup` | `/home/Hub/backups/20261031T012953Z` |
| 01:30:10 تا 01:32:02 | checkout و `make up` (پروفایل full) | rc=0. migration از 0032 به **0033** رسید و همه‌ی سرویس‌ها سالم‌اند |
| 01:32 | `make install-systemd` | `coinepro-hq-stt.service`، `coinepro-hq-stt.path` و `/run/hq/stt` (10001:10001) نصب شد |
| 01:33:14 | `make stt-on` | rc=0. مدل `small` با sha256 گرفته شد، `HQ_STT=on`، و path `enabled` و `active` است |
| 01:34 | `make stt-cold` | جدول بخش ۴ |
| 01:35 | Caddy reload | rc=0. فایل‌های Caddy و OPA از ۱۷.۱ عوض نشده‌اند و بلوک runners از همان موقع بارگذاری است |
| 01:36 | Web Push | `make llm-provision` (idempotent) اجرا شد و api و worker دوباره بالا آمدند |
| 01:37 تا 01:50 | `make verify-live` و سنجش‌ها | rc=0، بخش ۵ |

- **migrationها:** هر دو، ۰۰۳۲ و ۰۰۳۳، تابع downgrade در کد دارند.
- **downgrade ۰۰۳۲:** در گزارش ۱۷.۱ بررسی شد.
- **آزمون رفت‌وبرگشت:** `test_p13f_join` (پایین تا 0009 و دوباره بالا تا head) در هر دو اجرای `make check` سبز بود.

## ۴. شروع سرد stt (`make stt-cold`)
| مرحله | زمان |
|---|---|
| روشن شدن کانتینر | 1275 ms |
| جواب `/health` | 3502 ms |
| اولین رونویسی (همراه بارگذاری مدل) | **5436 ms** |

بعد از اندازه‌گیری، stt خاموش شد. `hq.sh --profile stt ps stt` خالی است.

## ۵. `verify-live` و سنجش‌ها
- **`make verify-live`:** rc=0. فقط همان دو GAP قبلی هست: رسیدن egress و searxng با IP، که قانون DOCKER-USER مالک است.
- **مسیر جفت‌سازی runner:**
  - `GET /api/v1/runners/pair` از نشانی عمومی: **405**.
  - همین مسیر از `10.10.1.4:443`: **405**، با همان گواهی (`ssl_verify_result=0`).
- **`/internal`:** **404**.
- **`GET /api/v1/meta`:** با نشست مالک خوانده نشد، چون نشستی در دست نبود. پس همان دو مقدار را از داخل api و از همان کد سنجیدم:
  - `speech.enabled` = true، چون `STT_URL` تنظیم است.
  - `channels.web_push` = **روشن** (`web_push_ready` true و `login_configured` true). هیچ کلیدی چاپ نشد.
- **memory-budget روی این سرور:** `full+substitutes+substitutes-web+stt (on demand) ok (12396 MiB <= 12486 MiB)`.
- **`players_sweep`:** Maintenance در 01:35، 01:40 و 01:45 با `COMPLETED` تمام شد. هر سه `players_sweep` داشتند و هیچ activityی شکست نخورد.
- **worker:** صفر خطا در لاگ.
- **runnerها:**
  - PC و IG: `online` و `private`.
  - FX و TY: جفت شده‌اند ولی `offline` هستند. سرویس runnerشان باید روی خود سرورها روشن شود.

## ۶. قدم بعدی مالک
1. **runnerها:**
   - FX و TY: سرویس `hq-runner` روی خود سرور روشن شود.
   - PC و IG: کاری لازم نیست، هر دو online هستند.
2. **از اپ:**
   - یک فرمان صوتی «با جی‌پی‌تی …» برای آزمایش صدا به متن.
   - یک سفارش «شورا».
3. **کلید توقف هلدینگ:** فقط به تصمیم خود مالک باز میشود.
