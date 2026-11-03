# پرامپت ۲۰.۱: کاهش هزینه و متن GPT از چت وب (فقط deploy)

> Claude ساخت، ۲۰۲۶-۱۱-۰۲. کد نوشته و تست شده است. **فقط deploy.**
> - **شاخه:** `server/p20-1-deploy` از سر شاخه‌ی اصلی (`claude/coinepro-hub-setup-hsvnw7`)، بعد از pull.
> - **گزارش:** `docs/ops/reports/PROMPT_20_1.md`.
> - **migration:** `0036` (یک ستون تازه و جابه‌جایی جایگاه‌های GPT).
> - **runner شرکت‌ها:** نسخه‌ی تازه‌ی `0.2.2` (بخش آخر).
> - **قرارداد:** §۲۸.۷ (نسخه‌ی 1.10.2).

## چه شد
ریشه از گزارش ۲۰ (یافته‌ی ۶): **۹۷٫۶٪** توکن‌های هفته مال یک اجرای کاتالوگ بود.
- **چرا:** پاک‌سازی ۱۰-۳۱ 20:28 جدول `ops.watch_runs` را هم پاک کرد. دیده‌بان در دور بعدی (هر ۵ دقیقه) دید «این هفته کاتالوگی نگرفته» و برای هر شرکت دارای سرور کاتالوگ زد.
- **نتیجه:** ۴ سرور × ۶ بخش = ۲۴ نشست Claude Code، هر کدام تا ۶۰ دور، بی هیچ سقف توکنی. حدود ۵۰ میلیون توکن در یک ساعت، بیشترش خواندن دوباره‌ی زمینه (cache).

### ۱. کاتالوگ فقط با دستور مالک، با سقف (قرارداد §۲۸.۷)
- **دیده‌بان دیگر کاتالوگ نمیزند.** فقط اجرای جامانده روی سرور خاموش را میبندد.
- **ایجنت:** `company.catalogue {start: true}` فقط وقتی اجرا میزند که کار ایجنت از فرمان مالک آمده باشد (در زنجیره‌ی ارجاع). وگرنه آخرین کاتالوگ را میدهد، یا `409 owner_order_required`.
- **سقف هر اجرا:** `HQ_CATALOGUE_RUN_TOKENS` (پیش‌فرض ۱٬۵۰۰٬۰۰۰، همه‌ی سرورها و بخش‌ها روی هم).
  - هر نشست سهم خودش را به‌شکل `token_cap` میگیرد، و حداکثر ۲۵ دور.
  - تلاش دوم یک بخش فقط وقتی است که هنوز در سقف جا هست.
- **runner 0.2.2:** مصرف هر پیام را جمع میکند و با رد شدن از `token_cap` نشست را متوقف میکند (کد خروج `125`). runner قدیمی فقط سقف دور را رعایت میکند.
- **ثبت:** ردیف‌های `server_claude` در `llm.calls` حالا `meta.quota = "company_server"` و `meta.via` دارند (پیشنهاد ۶ گزارش ۲۰).
- **تست:** `apps/api/tests/test_p20_1_cost.py`، `test_p19_watch.py`، `services/company-runner/tests/test_claude.py`.

### ۲. دیده‌بان، اول قاعده
- **PR-140 (امنیت روزانه):** کد نقشه‌ی هر سرور را میخواند: پورت عمومی غیر از 22/80/443، دیسک بالای ۸۰٪، گواهی سایت کمتر از ۲۱ روز. اگر چیزی نبود، اجرا بی مدل `pass` میشود. اگر بود، brief مدل با همان یافته‌ها شروع میشود.
- **PR-141 (سلامت اپ):** فقط روزی که اپ خطای `error` فرستاده، مدل صدا زده میشود.
- **PR-142 (بازبینی کد):** ماهانه، روز اول ماه شمسی. نسخه‌ی تازه‌ی پروتکل خودش با reconcile زمان‌بندی ساخته میشود (نسخه‌ای که مالک دستی عوض کرده دست نمیخورد).

### ۳. سقف روزانه‌ی هر شرکت و سهم هر حوزه
- **سقف:** `core.companies.daily_token_cap` (خالی = `AGENT_COMPANY_DAILY_TOKEN_CAP`، پیش‌فرض ۴۰۰٬۰۰۰؛ `0` = فقط سقف هاب). هم هنگام شروع اجرا و هم پیش از هر فراخوانی مدل سنجیده میشود.
- **سهم حوزه‌ها:** گزارش صبحگاهی سهم دیروز را به حوزه نشان میدهد (کاتالوگ، Claude سرورها، نظارت، مشاور، شورا، جلسه‌ها، رسانه، کار). شنبه‌ها سهم هفته‌ی گذشته هم میآید. اگر کاتالوگ یا نظارت بیشترین سهم را داشت، یک خط هشدار.
- **`treasury.usage` (یافته‌ی ۷):** کد شرکت، `week`، دپارتمان و نقش را میپذیرد و جواب را به حوزه و دپارتمان هم میدهد.

### ۴. متن GPT از چت وب ChatGPT، نه Codex
- متن GPT و سه جایگاه متنی‌اش (`advisor_second_opinion`، `overseer_cross_check`، `assistant_errand`) از پروفایل `chatgpt-web` میروند.
- **Codex:** فقط `code_review`، خاموش تا مالک بخواهد.
- **آماده بودن GPT:** از ورود وب. سهمیه‌ی تمام‌شده‌ی Codex دیگر چت وب را نمیبندد.
- **migration 0036:** فقط جایگاه‌هایی را جابه‌جا میکند که مالک دستی عوض نکرده (مثل 0029_1)، با یک ردیف Audit برای هر جایگاه.
- **دستور وب `chatgpt-web` (نسخه‌ی `2026-11-02.1`)** بر پایه‌ی ساختار صفحه است، نه متن یک زبان (درس ۱۹.۳):
  - ارسال با Enter.
  - اول testidها.
  - جواب = آخرین بلوک جواب (`.markdown`). سرتیتر فارسی/انگلیسی فقط پشتیبان است (`alt`).
  - تست با Chromium واقعی روی صفحه‌ای که فقط برچسب فارسی دارد: `services/egress/tests/test_browser_web.py` (‏`services/scripts/browser-test.sh`).

## deploy
1. `git pull` روی شاخه‌ی اصلی، شاخه‌ی `server/p20-1-deploy`، و `make check` در worktree جدا. اجازه‌ی دائمی قالب‌بندی و CVE سر جایش است.
   - `services/scripts/browser-test.sh` را هم اجرا کن (۱۹ تست، با تست صفحه‌ی فارسی ChatGPT).
2. **عدد پیش از deploy (فقط خواندن):** مصرف یک ساعت و ۲۴ ساعت گذشته، به حوزه. پرس‌وجو در بخش «سنجش» پایین است. در گزارش بنویس.
3. `make backup`.
4. image‌های `api`، `worker`، `gateway`، `egress` و `browser-web` را دوباره بساز و بالا بیاور. `make verify-live`.
   - **migration ۰۰۳۶:** در گزارش تأیید کن که `alembic current` روی `0036` است.
   - **env:** دو متغیر تازه در `infra/compose/compose.yaml` پیش‌فرض دارند (`AGENT_COMPANY_DAILY_TOKEN_CAP=400000`، `HQ_CATALOGUE_RUN_TOKENS=1500000`). در `.env` چیزی اضافه نکن؛ اگر مالک عدد دیگری خواست، او میگوید.
5. **سنجش‌های فوری (فقط بله/خیر و عدد):**
   - `substitutes.players` برای `gpt`: `capabilities.text = web`. جایگاه‌های متنی‌اش `via = web`، `code_review` خاموش.
   - `oversight.current_protocols` برای `PR-142`: زمان‌بندی `FREQ=MONTHLY`، تقویم `jalali`. زمان‌بندی Temporal آن (`protocol-PR-142`) روزانه ساعت ۰۹:۳۰ است و اجرا فقط روز اول ماه شمسی انجام میشود (بقیه‌ی روزها `not_its_jalali_day`).
   - در `ops.watch_runs` از بعد از deploy هیچ ردیف `catalogue:` تازه‌ای نیست.
   - `GET /internal/v1/treasury/usage?period=week` با توکن یک مدیر (مثلاً از راه `prompt-check` یا یک call ابزار در اجرای آزمایشی) دیگر `invalid_args` نمیدهد. اگر سنجیدنش بی ساختن کار تازه ممکن نیست، فقط بنویس «سنجیده نشد».
6. **GPT از وب:**
   - اگر پروفایل `chatgpt-web` وارد نیست (`web_state` ≠ `signed_in`)، **کار مالک است:** `make chatgpt-web-login`. در گزارش بنویس و صبر کن.
   - اگر وارد است: یک call آزمایشی مثل پرامپت ۱۹: HQ-PA، جایگاه `assistant_errand`، بازیکن `gpt`، متن «سلام؛ فقط بنویس: آزمایش».
     - در گزارش: `via` (باید `web` باشد)، وضعیت، جواب دقیق، `recipe_version` (باید `2026-11-02.1` باشد)، و `web_last_failure`.
     - اگر `recipe_failed` شد: شماره‌ی گام و توصیف تصویر (نه خود تصویر). **دستور وب را خودت عوض نکن**؛ گزارش بده.
   - هیچ call تازه‌ای به Codex (`via = cli`) نباید ساخته شده باشد: `SELECT count(*) FROM substitutes.calls WHERE player='gpt' AND via='cli' AND created_at > <زمان deploy>` باید ۰ باشد.
7. **سنجش هزینه، یک ساعت و ۲۴ ساعت بعد از deploy (با عدد):** همان پرس‌وجوی بند ۲. در گزارش جدول «پیش / یک ساعت بعد / ۲۴ ساعت بعد» به حوزه.
   - **قبولی:** سهم `catalogue` در هر دو پنجره ۰ است، مگر مالک خودش کاتالوگ خواسته باشد. اگر خواسته، مصرف آن اجرا زیر ۱٬۵۰۰٬۰۰۰ توکن است.
   - **قبولی:** `oversight` بیشترین سهم نیست.
8. گزارش کوتاه فارسی به مالک، با قدم بعدی او (بخش پایین).

### سنجش: مصرف به حوزه (فقط خواندن)
روی دیتابیس `hq` با `default_transaction_read_only=on`. `:from` و `:to` را با زمان پنجره پر کن:
```sql
SELECT CASE
    WHEN c.task_class = 'server_claude' AND (c.meta->>'via' = 'catalogue' OR c.actor_ref = 'catalogue') THEN 'catalogue'
    WHEN c.task_class = 'server_claude' THEN 'server'
    WHEN c.meta ? 'protocol' OR split_part(c.meta->>'charter', '@', 1) IN ('overseer','inspector','ai_safety','fact_checker') THEN 'oversight'
    WHEN c.caller = 'substitutes' THEN 'council'
    WHEN c.meta ? 'meeting' THEN 'meetings'
    WHEN c.task_class LIKE 'media\_%' OR split_part(c.meta->>'charter', '@', 1) IN ('media_director','scriptwriter','video_director','motion_designer','voice_producer','visual_designer','ui_designer') THEN 'media'
    WHEN c.task_class LIKE 'advisor%' OR c.task_class LIKE 'dceo%' OR split_part(c.meta->>'charter', '@', 1) IN ('advisor','dceo') THEN 'advisor'
    ELSE 'work' END AS domain,
  count(*) AS calls,
  sum(COALESCE(c.input_tokens,0)+COALESCE(c.output_tokens,0)+COALESCE(c.cache_read_tokens,0)+COALESCE(c.cache_write_tokens,0)) AS tokens
FROM llm.calls c WHERE c.started_at >= :from AND c.started_at < :to
GROUP BY 1 ORDER BY tokens DESC;
```
(همان قاعده‌ی `apps/api/src/hq_api/domain/spend.py`.)

## قدم بعدی: به‌روزرسانی runner روی هر سرور شرکت به 0.2.2
- **کار Claude هاب نیست. به هیچ سرور شرکتی وصل نشو.**
- **چرا:** بی 0.2.2، سقف توکن به نشست نمیرسد و فقط سقف ۲۵ دور کاتالوگ را محدود میکند.
- **چطور:** Claude خود هر سرور، طبق `docs/server-prompts/COMPANY_SERVER_ACCESS_SETUP.md` بخش «به‌روزرسانی runner». در پایان `hq-runner --version` باید `0.2.2` باشد.
- **در گزارش:** فهرست سرورها و نسخه‌ی runner فعلی هر کدام (از `GET /api/v1/infra/servers`).

## قوانین
- **دسترسی به سرورها:** به هیچ سرور شرکتی وصل نشو و دست نزن.
- **رمزها:** رمز، کوکی یا کلیدی چاپ نشود، فقط نام متغیرها.
- **کلید توقف:** همان‌طور که مالک گذاشته بماند.
- **کاتالوگ:** خودت هیچ کاتالوگی شروع نکن.
- **Codex:** جایگاه `code_review` را روشن نکن؛ فقط مالک.
