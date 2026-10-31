# گزارش پرامپت ۱۸: deploy متوقف شد (make check قرمز)

> Claude سرور هاب، ۲۰۲۶-۱۰-۳۱.
> - **وضعیت:** 🔴 قرمز. طبق قدم ۱ پرامپت، جلوتر نرفتم.
> - **deploy:** انجام نشد. این کارها انجام نشد:
>   - `make backup`
>   - migration ۰۰۳۳
>   - ساخت image
>   - systemd و stt
>   - OPA و Caddy
>   - Web Push
> - **سرور زنده:** دست نخورده است و همان `server/p17-1-deploy` (fd0ac9c، migration 0032) است. کلید توقف هم همان است که مالک گذاشته.
> - **شاخه:** `server/p18-deploy` از سر شاخه‌ی اصلی، 4df8b7f. شاخه‌ی ۱۷.۱ از قبل در شاخه‌ی اصلی بود. جز این گزارش، هیچ کدی عوض نشد.

## ۱. نتیجه‌ی `make check`
- **کجا و کی:** در worktree جدا، از 22:47:39 تا 00:05:25Z (۷۸ دقیقه)، rc=2.
- **فایل `.env`:** worktree یک `.env` دورریختنی گرفت (`gen-env.sh`، از راه `HQ_ENV_FILE`). این بار سنجش media-render در دروازه‌ی live سبز شد.
- **سبز (۱۴ از ۱۶):**
  - gitleaks، compose-config، ports، compose-rules، shellcheck، yamllint، hadolint
  - memory-budget
  - opa
  - infra، backup، provisioning
  - python lint
  - live: همان دو GAP قبلی هست (رسیدن egress و searxng با IP، قانون DOCKER-USER مالک).
  - **python test، بخش سرویس‌ها:** 1161 passed. stt: 74 passed.
- **قرمز:** python test (apps/api: ۲ شکست، 942 قبول) و python audit.

## ۲. دو آزمون apps/api: از دو نقش تازه‌ی TECH
هر دو شکست قطعی‌اند، نه تصادفی. علتشان این است که منشورهای `devops_engineer` و `lead_developer` (پرامپت ۱۸) حالا زنده‌اند، ولی این دو آزمون هنوز وضع قبل از ۱۸ را میخواهند.

1. **`tests/test_p13a_departments.py:57`**، آزمون `test_a_new_company_has_media_with_its_mandate_identity_and_team`:
   - آزمون این را میخواهد: `assert [t["role"] for t in depts["TECH"]["team"]] == ["sre"]`
   - نتیجه‌ی واقعی: `['sre', 'devops_engineer', 'lead_developer']`
   - توضیح خود آزمون: «TECH's staged roles are not there yet». این دیگر درست نیست.
2. **`tests/test_agents_more.py:199`**، آزمون `test_propose_section_is_generated_from_the_api_models`:
   - آزمون این را میخواهد: `` "`role` must be one of: motion_designer (department MEDIA)" in co ``
   - فهرست نقش‌ها در بخش propose حالا نقش‌های تازه را هم دارد، پس این رشته‌ی دقیق دیگر پیدا نمیشود.
- **کار سشن مشورت:** دو آزمون با فهرست تازه‌ی نقش‌ها هماهنگ شوند. یا اگر این دو نقش باید staged بمانند، منشورها.

## ۳. python audit: هفت CVE تازه در pypdf
- `pypdf 6.21.2` هفت آگهی تازه دارد:
  - CVE-2026-119203 تا CVE-2026-119209
  - نسخه‌ی درست‌شده: 6.21.3، و برای 119203، 119204 و 119205 نسخه‌ی 6.21.4.
- **از کد ۱۸ نیست:** lock‌ها از 2026-10-29 (b9882c8) عوض نشده‌اند. این آگهی‌ها تازه منتشر شده‌اند، پس **سرور زنده هم همین نسخه را دارد.**
- **کجا به کار میرود:**
  - `services/egress/src/hq_egress/extract.py`: PDF وب، که داده‌ی غیرقابل‌اعتماد است و فقط در child process پردازش میشود.
  - `apps/api/src/hq_api/media.py` و `apps/api/src/hq_api/archive/jobs.py`: PDFهای آپلودشده و آرشیو.
- **پیشنهاد:** `pypdf` در `services/egress/requirements.lock` و `apps/api/requirements.lock` به 6.21.4 برود، با hash. یا اگر لازم شد، با دلیل و تاریخ در `scripts/quality/audit-ignore.txt` بیاید.
  - این lock‌ها در پوشه‌های سرور هاب‌اند. ولی این پرامپت «فقط deploy» است و کدی ننوشتم. با اجازه‌ی مالک یا سشن مشورت، خودم انجامش میدهم.

## ۴. worktree
طبق پرامپت، worktree بعد از این گزارش با `git worktree remove` برداشته شد. پوشه‌ی کاری سرور زنده دست نخورد.

## ۵. قدم بعدی
1. **سشن مشورت:** دو آزمون بخش ۲ را درست کند و برای pypdf تصمیم بگیرد.
2. **سرور هاب:** بعد از push، پرامپت ۱۸ را از اول اجرا میکند.
3. **مالک:**
   - runnerهای PC و IG online هستند.
   - FX و TY جفت شده‌اند ولی از 21:38Z آفلاین‌اند. سرویس runnerشان باید روشن شود.
