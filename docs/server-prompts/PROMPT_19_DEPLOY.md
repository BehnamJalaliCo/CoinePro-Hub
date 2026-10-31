# پرامپت ۱۹: deploy پاک‌سازی خروجی‌ها، کاتالوگ شرکت، دیده‌بان و استحکام شورا، به‌علاوه‌ی عیب‌یابی زنده‌ی دستورالعمل‌های وب

> Claude سشن مشورت، ۲۰۲۶-۱۰-۳۱.
> - **کد:** کد پرامپت ۱۹ (قرارداد §۲۸ ⟨1.10⟩) را سشن مشورت نوشته، تست کرده و روی شاخه‌ی اصلی push کرده است.
> - **کار تو دو بخش دارد:**
>   - بخش اول فقط deploy است. کدی ننویس. اگر چیزی خراب بود، گزارش بده.
>   - بخش دوم عیب‌یابی زنده‌ی دستورالعمل‌های Gemini و DeepSeek است. آنجا فقط فایل‌های دستورالعمل را اصلاح میکنی.
> - **شاخه:** `server/p19-deploy` از سر شاخه‌ی اصلی، `claude/coinepro-hub-setup-hsvnw7` بعد از pull.
> - **گزارش:** `docs/ops/reports/PROMPT_19.md`.

## آنچه در شاخه است (مرجع: قرارداد §۲۸)
- **migration ۰۰۳۴:**
  - تابع `cartable.owner_delete_deliverables` (SECURITY DEFINER، مالکش hq). guardهای append-only فقط برای همین تابع DELETE را رد نمیکنند.
  - جدول‌های تازه با FORCE RLS: `infra.catalogues`، `ops.client_errors` و `ops.watch_runs`.
  - `oversight.findings`: ستون‌های `kind`، `fix_md` و `fix`.
  - `work.councils.note_fa`، `substitutes.players.web_error_until` و `substitutes.calls.attempt`.
  - downgrade هم دارد.
- **§۲۸.۱ خروجی‌ها:**
  - `POST /api/v1/deliverables/file` چند خروجی را با هم بایگانی میکند.
  - `DELETE /api/v1/deliverables` حذف همیشگی است. 🔏 `deliverables.delete` روی SHA-256 فهرست مرتب‌شده‌ی refها لازم است.
  - با هر خروجی، امتیازها و فایل‌های فقط‌مال‌خودش هم حذف میشوند. فقط یک ردیف Audit میماند. رکوردهای بایگانی میمانند.
- **§۲۸.۲ کاتالوگ شرکت:**
  - `POST` و `GET /api/v1/companies/{code}/catalogue`.
  - روی هر سرور جفت‌شده، برای هر بخش یک کار `claude` فقط‌خواندنی میرود. شش بخش دارد: محصولات، اتوماسیون‌ها، داده، رابط‌ها، کد، ریسک‌ها.
  - هر جا Claude Code نباشد، نقشه‌ی runner جایش را میگیرد.
  - نتیجه یک خروجی است و در بایگانی رکورد `report` میشود.
  - ابزار `company.catalogue` برای CEO و نقش‌های دیده‌بان است. هر هفته هم خودکار تازه میشود و تفاوتش میرسد.
- **§۲۸.۳ دیده‌بان:**
  - سه پروتکل تازه‌ی ناظر:
    - PR-140: امنیت روزانه
    - PR-141: سلامت روزانه‌ی اپ‌ها
    - PR-142: بازبینی هفتگی کد هر مخزن
  - `POST` و `GET /api/v1/client/errors`، و ابزار `client.errors`.
  - یادداشت رشد هفتگی مشاور برای هر شرکت.
  - «پیشنهاد هلدینگ» ماهانه‌ی مدیرعامل دیجیتال، به‌شکل یافته‌ای از نوع `holding`.
  - این‌ها را Maintenance ‏worker اجرا میکند (activity ‏`watch_sweep`). منشورهای CEO، ناظر، مشاور و SRE به‌روز شده‌اند.
- **§۲۸.۴ استحکام شورا:**
  - **مدل ردشده:** اگر ارائه‌دهنده مدلی را رد کند، یک بار دیگر با مدل دیگری امتحان میشود. فهرست مدل‌ها هم دوباره از CLI پرسیده میشود.
  - **`recipe_failed`:** یک بار دیگر با بارگذاری دوباره‌ی صفحه امتحان میشود. بعد شکست میخورد و تصویر صفحه پیوست میشود. آن بازیکن ۶ ساعت در وضعیت `error` میماند و شوراهای بعدی ردش میکنند.
  - **سنتز:** هیچ‌وقت منتظر عضوی که تمام شده نمیماند. اگر فقط یکی جواب داد، صریح میگوید.
  - دلیل هر عضو فارسی است و JSON خام هیچ‌وقت نشان داده نمیشود.

## بخش اول: deploy
1. **pull و سنجش:**
   - `git pull`.
   - `make check` را در یک worktree جدا اجرا کن (`git worktree add`).
   - هر قرمزی را گزارش کن و جلو نرو. بعد worktree را بردار.
2. `make backup`.
3. **migration ۰۰۳۴:** در گزارش تأیید کن که `alembic current` روی `0034` است.
4. **image‌ها:**
   - `api`، `worker`، `gateway`، `egress` و `browser` را دوباره بساز. ‏`browser-web` همان image ‏`coinepro-hq/browser` است.
   - این‌ها را بالا بیاور: api، worker، gateway، egress و (اگر `substitutes-web` روشن است) browser-web.
5. **OPA:** با سیاست‌های تازه reload کن (`watch.rego`، `owner_tools.rego`، `internal.rego`).
6. **seed** (api هنگام بالا آمدن انجامش میدهد). تأیید کن:
   - در `GET /api/v1/oversight/protocols`، PR-140، PR-141 و PR-142 هستند و فعال‌اند.
   - نسخه‌ی منشورها: ceo 9، overseer 7، advisor 7، hub_platform_sre 4.
7. **`make verify-live` و این سنجش‌ها** (فقط کد وضعیت):
   - `DELETE /api/v1/deliverables` با `{"refs":["O-000001"]}`، بی‌step-up: `403 step_up_required`. **هیچ خروجی را واقعاً حذف نکن.**
   - `POST /api/v1/client/errors` با `entries: []`: `422`.
   - `GET /api/v1/companies/<کد یک شرکت>/catalogue`: `404` (هنوز ندارد) یا `200`.
   - `/internal` همچنان `404` بدهد.
   - بعد از ۵ دقیقه، در لاگ worker، Maintenance ‏`watch_sweep` را بدون خطا اجرا کرده باشد.
   - **کاتالوگ را خودت شروع نکن.** مالک از اپ شروعش میکند، یا دیده‌بان شنبه.
8. حافظه: هیچ سرویس تازه‌ای اضافه نشده است. `scripts/quality/memory-budget.sh` روی همین سرور سبز باشد.

## بخش دوم: چرا دستورالعمل‌های Gemini و DeepSeek روی هاب شکست میخورند (زنده)
**زمینه:** در شورای امروز، Gemini و DeepSeek هر دو `recipe_failed` دادند.

سربرگ هر دو فایل این را میگوید: «selectorها از روی مستندات ۲۰۲۶-۱۰-۲۲ نوشته شده‌اند و روی سایت زنده تأیید نشده‌اند.»
- `infra/egress/recipes/gemini-web.yaml`
- `infra/egress/recipes/deepseek-web.yaml`

پس محتمل‌ترین علت selectorهای غلط است. این را زنده بسنج؛ حدس نزن.

1. **وضعیت فعلی (بی‌prompt، بی‌cookie):**
   ```
   infra/compose/hq.sh exec -T postgres psql -U postgres -d hq -c "SELECT player, web_state, recipe_version, web_last_ok_at, web_last_failure, web_error_until FROM substitutes.players ORDER BY player"
   infra/compose/hq.sh exec -T postgres psql -U postgres -d hq -c "SELECT player, seat, attempt, state, state_reason, created_at FROM substitutes.calls WHERE via = 'web' ORDER BY created_at DESC LIMIT 20"
   ```
   - `web_last_failure` قدم شکست را نشان میدهد (مثلاً `recipe_failed: 2:wait`). یعنی شماره‌ی قدم در `tasks.text.steps` و نوع آن.
   - اگر `web_state` برابر `signed_in` نیست، مشکل ورود است، نه دستورالعمل. این را گزارش کن تا مالک دوباره وارد شود (`make gemini-web-login` یا `make deepseek-web-login`).
2. **یک بار بازتولید، با تصویر:**
   - از اپ، مالک یک سفارش «با جمنای …» بدهد. یا خودت یک کار متنی کوتاه بی‌داده‌ی محرمانه بفرست، با نقش HQ-PA و `substitute.call` روی جایگاه `content_draft` (یا `quick_search` برای DeepSeek). متنش این باشد: «سلام؛ فقط بنویس: آزمایش».
   - بعد از دو تلاش (۶۰ ثانیه فاصله)، call شکست میخورد و فایل تصویرش در `substitutes.calls.result ->> 'screenshot_file'` است.
   - تصویر را بخوان. اول `storage_key` آن را بگیر:
     ```
     infra/compose/hq.sh exec -T postgres psql -U postgres -d hq -Atc "SELECT f.storage_key FROM files.files f WHERE f.id = (SELECT (result ->> 'screenshot_file')::uuid FROM substitutes.calls WHERE result ? 'screenshot_file' ORDER BY finished_at DESC LIMIT 1)"
     ```
     بعد فایل را از volume ‏`hq-files` (مسیرش `<دو حرف اول>/<key>`) با کانتینر worker بیرون بیاور:
     ```
     infra/compose/hq.sh exec -T worker sh -c 'cat /data/files/<دو حرف اول>/<key>' > /tmp/hq-recipe-shot.png
     ```
     و با ابزار Read ببین. بعد فایل `/tmp` را پاک کن.
   - تصویر صفحه‌ی حساب مالک است: در گزارش فقط توصیفش کن. خود تصویر را جایی نفرست و commit نکن.
3. **بررسی selectorها روی صفحه‌ی زنده:**
   - در کانتینر `browser-web`، با همان پروفایل و از راه پراکسی egress، یک اسکریپت Playwright کوتاه اجرا کن.
   - فقط بخوان: `start_url` را باز کن و برای هر selector دستورالعمل `count()` را چاپ کن.
   - این‌ها را هم چاپ کن: `textarea`، `[contenteditable=true]`، دکمه‌ی ارسال (`button[aria-label*=Send]`، `button[type=submit]`) و جای پاسخ آخر.
   - هیچ متنی نفرست، هیچ کوکی‌ای نخوان و چاپ نکن، و پروفایل را عوض نکن.
   - اگر پراکسی اجازه نداد، مسیر آماده همین است: یک بار `web.browse` با حساب پروفایل (اجرای Claude ‏SRE). کار SRE که خود هاب پس از شکست میسازد همین را انجام میدهد و تصویر را هم دارد.
4. **اصلاح:**
   - selectorهای قدم شکسته را در فایل yaml همان حساب درست کن و `version` را بالا ببر.
   - در `services/egress`، تست `tests/test_substitutes_web.py` را اجرا کن. این تست شِمای دستورالعمل‌ها را میسنجد.
   - روی شاخه‌ی `server/p19-recipes` commit کن.
   - egress و browser-web را دوباره بساز و بالا بیاور.
   - مرحله‌ی ۲ را تکرار کن تا call ‏`done` شود.
   - فقط بعد از پاس شدن:
     ```
     UPDATE substitutes.players SET web_error_until = NULL WHERE player IN ('gemini', 'deepseek')
     ```
5. **گزارش به مالک:** برای هر بازیکن:
   - قدمی که شکست
   - selector قدیم و جدید
   - تصویر قبل و بعد (فقط توصیف)
   - نتیجه‌ی call آزمایشی
   - اگر مشکل ورود یا Cloudflare بود: همان را بگو و چیزی را دور نزن.

## قوانین
- **دسترسی به سرورها:** به هیچ سرور شرکتی وصل نشو و دست نزن. کاتالوگ با runner و از اپ مالک شروع میشود.
- **رمزها:** رمز، کوکی یا کلیدی چاپ نشود، فقط نام متغیرها.
- **حذف:** هیچ خروجی‌ای را برای آزمایش حذف نکن. حذف همیشگی فقط کار مالک است.
- **کلید توقف:** همان‌طور که مالک گذاشته بماند.
