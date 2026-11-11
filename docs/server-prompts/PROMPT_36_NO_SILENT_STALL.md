# پرامپت ۳۶: هیچ جلسه‌ای بی‌صدا نمی‌ایستد (جلسه‌ی ریلز پروچارت)

> Claude سشن مشورت، ۲۰۲۶-۱۱-۱۲.
> - **پیش‌نیاز:** پرامپت ۳۵ (deploy شده، ۲۰۲۶-۱۱-۱۱؛ گزارش `docs/ops/reports/PROMPT_35.md`).
> - **شاخه:** `server/p36-deploy` از `claude/coinepro-hub-setup-hsvnw7`.
> - **گزارش:** `docs/ops/reports/PROMPT_36.md`.
> - **قرارداد:** §۵۶ (v1.34).

## چرا
مالک، ۲۰۲۶-۱۱-۱۲: جلسه‌ی «به هرچه میگویم دقت کن و …» (ریلز هر روز پروچارت، روش «با من»، کار ۳ از ۱۸) بعد از
خط مسئول «پیش‌نویس متن … از ChatGPT خواسته شد و در صف است» بیش از ۱۲ ساعت هیچ کاری نکرد و اپ فقط «آرام» نشان داد.
پنج بازبینی کد علت‌ها را پیدا کرد و همه درمان شد؛ هر درمان را یک بازبین ارشد سنجید و بعد هشت بازبین تازه خط‌به‌خط
گشتند. این پرامپت درمان را مستقر میکند.

## چه عوض شده (قرارداد §۵۶)
- **بازیکن ذخیره (ChatGPT/Gemini)** (`domain/substitutes.py`، `players.py`، `worker/management_activities.py`):
  - هر درخواست مهلت دارد: در صف ۱۵ دقیقه (عکس و ویدیو ۳۰)، از وقتی نوبت گرفتنش رسیده؛ در حال اجرا تا `timeout_s + 120`.
  - هر پایان (جواب، رد، «جواب نداد») به ایجنتِ پرسنده میرسد تا با مدل خودش ادامه دهد، با یک خط در جلسه.
  - مرورگرِ از کار افتاده ۱۰ دقیقه کنار گذاشته میشود؛ درخواست بی‌جا به صف نمیرود.
  - درخواست‌هایی که پیش‌تر بی‌خبر تمام شده بودند، یک بار دیگر خبر داده میشوند (حداکثر ۲۵ در هر دور؛ کاری که بسته شده، کار تازه نمیگیرد).
  - **ChatGPT متن ریلز را مینویسد:** صندلی `content_draft` برای GPT (migration `0062`).
- **موتور جلسه** (`session_activity.py`، `order_report.py`، `order_turns.py`، `work.py`، `sessions.py`):
  - ریشه‌ی جلسه تا برنامه قدم باز دارد با «تحویل» بسته نمیشود؛ اگر بسته شده باشد، باز و مسئول بیدار میشود.
  - درخواست بیرونی و صدای در راه «کار زنده» است (`Worker.kind = call`).
  - بیدارباش با دستور روشن، حداکثر دو بار برای هر حرف مالک؛ بعد «گیر کرده» با یک جمله و یک اعلان.
  - نگهبان جلسه‌ها برنامه‌ی Temporal جدای خودش را دارد: `hq-order-tick`، هر ۲ دقیقه.
  - همه‌ی جمله‌هایی که مالک میخواند «تو» میگویند.
- **اکانت‌های Claude و راستی ایجنت** (`domain/servers.py`، `worker/activities.py`، `agents/runner.py`، `services/llm-router`، `services/claude-runtime`):
  - پر شدن اکانت در کارهای Claude Code ثبت میشود و کاری که هنوز کاری نکرده یک بار به اکانت دیگر میرود.
  - کار ناموفق به‌خاطر سقف، بعد از خالی شدن اکانت برمیگردد.
  - ایجنت کار ردشده را «انجام شد» نمیگوید.
- **مسیر انتشار** (`connections.py`، `session_publish.py`، `seed/channels.yaml`):
  - `publish_command` از تنظیم `ig_hub` هلدینگ می‌آید.
  - حساب‌ها را تیم فنی با کد میشناسد و ثبت میکند.
  - روال کارگروهِ بی‌نفر برای مدیرعامل کار باز میکند.
- **پنل وب ۱.۰.۲:** جلسه‌ی ایستاده «ایستاده» میشود با «ادامه بده».

## کار تو (Claude سرور هاب)
### ۱. اول فقط بخوان (پیش از deploy؛ برای گزارش، بی هیچ تغییر)
با `infra/compose/hq.sh exec -T postgres psql -U postgres -d hq`. پیشوند P برای جلسه:
```sql
WITH r AS (SELECT r.* FROM owner.order_reports r JOIN owner.orders o ON o.id = r.order_id
           WHERE o.text LIKE 'به هرچه میگویم دقت کن%' ORDER BY o.created_at DESC LIMIT 1),
     w AS (SELECT w.* FROM work.work w, r WHERE w.ref = ANY(r.work_refs))
```
- **جلسه:** `P SELECT ref, state, badge, turn IS NOT NULL t, last_step_at, ended_at, closed_at FROM r;`
- **ریشه‌ها و برنامه:**
  - `P SELECT w.ref, w.status, w.progress_pct, w.updated_at FROM w ORDER BY w.created_at;`
  - شمار قدم‌های `owner.session_tasks` همان سفارش به تفکیک `state`.
- **درخواست ChatGPT همین جلسه:**
  ```sql
  P SELECT c.player, c.via, c.seat, c.state, c.state_reason, c.created_at, c.claimed_at, c.finished_at, c.delivered_at
    FROM substitutes.calls c
    WHERE c.purpose_kind = 'caller_work' AND c.purpose_ref IN (SELECT id::text FROM w)
    ORDER BY c.created_at;
  ```
- **صف کل:**
  - `SELECT player, via, state, count(*), min(created_at), min(claimed_at) FROM substitutes.calls WHERE state IN ('queued','running') GROUP BY 1,2,3;`
  - شمار درخواست‌های ایجنت که در ۲۴ ساعت گذشته تمام شده‌اند و `delivered_at` ندارند. این‌ها پس از deploy خبر داده میشوند.
- **بازیکن‌ها:** `SELECT player, runner IS NOT NULL, status, login_state, web_state, web_last_failure FROM substitutes.players;`
- **اجراهای مسئول بعد از جواب مالک:**
  - از `agents.runs` ستون‌های `queued_at`، `state`، `error_code` و `reason`.
  - از `agents.steps`، `actions[].tool/outcome/code` هر قدم. مثلاً آیا `order.progress` یا `deliver` بعد از کاری که رد شده بود اجرا شد؟
- **لاگ و حال سرویس‌ها:**
  - `logs worker` و `logs egress` از آن ساعت تا حالا: فقط خط‌های `substitute` و `Traceback`.
  - `docker inspect` کانتینر `browser-web`: `OOMKilled` و `RestartCount`.
  - Temporal: آیا اجرای `Maintenance` در این مدت `TimedOut` یا `Failed` داشته است؟
- **ردیف‌های `llm.quota_status`:** هر اکانت با `window_kind`، `utilization`، `resets_at` و `observed_at`.

### ۲. تست
- شاخه را بساز و شاخه‌ی اصلی را merge کن.
- **کل** `pytest tests` در `apps/api` را روی دیتابیس تازه و به ترتیب الفبا اجرا کن، همان‌طور که CI میکند. ترتیب دیگر تست رفت‌وبرگشت migration را میشکند.
- مجموعه‌های `services/llm-router` و `services/claude-runtime`، `opa test`، ruff و mypy.
- تست‌های تازه: `test_w23_substitutes`، `test_w23_session_stall`، `test_w23_quota`، `test_w23_publish_route`، `test_w23_owner_tu`.

### ۳. بکاپ، migration، deploy
1. **بکاپ.**
2. **migration `0062`:**
   - ستون `substitutes.calls.queued_at` و نمایه‌اش.
   - صندلی `content_draft` برای GPT.
   - `GRANT INSERT, UPDATE ON llm.quota_status TO hq_api`.
3. **deploy:** `api`، `worker`، `gateway` (منشورها: `_common.md` نسخه‌ی ۱۷)، `llm-router`، `claude-runtime` و `web` (پروفایل `web`، ‏۱.۰.۲).
4. **آزمون رفت‌وبرگشت migration را روی هاب انجام نده.**

**سنجش بعد از deploy:**
- `alembic current` برابر `0062` باشد.
- `healthz` جواب ۲۰۰ بدهد و پنل وب ۱.۰.۲ باشد.
- برنامه‌ی Temporal ‏`hq-order-tick` ساخته شده باشد و هر ۲ دقیقه اجرا شود.
- `Maintenance` دیگر `order_tick` نداشته باشد. اجرای `Maintenance`ای که هنگام deploy در جریان بود باید با `workflow.patched` بی خطا تمام شود.

### ۴. مسیر انتشار پروچارت (این بار اجازه داری)
- تصمیم دائمی مالک این است: اینستاگرام هر شرکت روی IG-Hub است و تیم فنی خودش تنظیمش میکند. حساب پروچارت در اسناد روشن است: `theprochart`.
- همین یکی را با نقش `hq` ثبت کن:
  ```sql
  UPDATE growth.connections k
     SET config = k.config || '{"via":"ig_hub","accounts":["theprochart"],"server":{"company":"IG","name":"IG-Hub"}}'::jsonb,
         updated_at = now()
    FROM core.companies c
   WHERE c.id = k.company_id AND k.kind = 'instagram' AND c.code = 'PC';
  ```
- **`publish_command` را ننویس.** از تنظیم هلدینگ می‌آید.
- حساب بقیه‌ی شرکت‌ها را کار فنی هاب خودش پیدا و ثبت میکند. آن را دستی ثبت نکن؛ فقط بنویس آیا کار فنی `ig_setup` برایشان باز شد.
- این ثبت چیزی منتشر نمیکند. هیچ کارگروه مُهرشده یا «انتشار خودکار»ی نیست.

### ۵. پانزده دقیقه بعد از deploy (فقط بخوان و در گزارش بنویس)
- **جلسه‌ی ریلز:**
  - درخواست ChatGPT تمام شد؟ با چه `state_reason`؟ خبرش رسید (`delivered_at` و `reply_work_id`)؟
  - خط «ChatGPT جواب نداد …» در جلسه نشست؟
  - مسئول دوباره کار کرد؟ چه ابزاری صدا زد؟
  - یا جلسه «گیر کرده» شد؟ با چه جمله‌ای؟
  - **دستی هیچ کاری نکن.** اگر جلسه هنوز ساکت و «آرام» است، همین را با داده‌اش بنویس.
- **موج اول خبرها:** چند کار پاسخ ساخته شد و چند تا برای کار بسته بی‌کار ماند.
- **سقف:** حال هر دو اکانت Claude. اگر کار Claude Code اجرا شد، آیا ردیف `llm.quota_status` از آن ثبت شد؟
- **ورودها:** `web_state` ChatGPT و Gemini. اگر هر دو بیرون افتاده‌اند، فقط بنویس «مالک یک بار وارد ChatGPT شود». خودت وارد نشو.
- **runner کارگاه:** هنوز ۰.۳.۳ است. همان دستور ۰.۳.۵ گزارش ۳۵ با `sudo` مالک است؛ فقط یادآوری کن.

## یک نکته درباره‌ی گزارش
پیش از push گزارش، `scripts/quality/gitleaks.sh` را اجرا کن.

## قوانین
- **داده:** هیچ داده‌ای پاک نشود.
- **کارها:** از طرف مالک جواب نفرست و در هیچ جلسه‌ای چیزی ننویس. هیچ چیزی منتشر یا لغو نکن.
- **تنظیم:** جز همان یک ثبت بند ۴، هیچ اتصال، گوینده یا اجازه‌ی دائمی را تنظیم نکن.
- **سرور:** به ورود سرور (SSH، کاربرها، فایروال) و به هیچ سرور دیگری دست نزن. هیچ حذف یا ریبوتی بی اجازه.
- **رمز:** هیچ رمز یا توکنی چاپ نشود؛ فقط نام متغیر.
- **گزارش:** فارسی و کوتاه (حداکثر ۲۵ خط).
  - خط آخر: «این گزارش را برای Claude سشن مشورت ببر.»
