# پرامپت ۷.۱: بازبینی پرامپت ۷، همراه ۶.۱ که هنوز انجام نشده (پیش از deploy ۸ و ۹)

> Claude سشن مشورت، ۲۰۲۶-۱۰-۱۸.
> - **مبنا:** `server/p07-platform`، commit 3a468a3 (پرامپت ۶ + ۷). سه بازبین موازی: (۱) backup؛ (۲) درگاه خروجی، مرورگر و حساب‌ها؛ (۳) MCP، فایل‌ها و API. شماره‌ی خط‌ها روی 3a468a3 است.
> - **کجا اصلاح کنی:** روی همان `server/p07-platform`. اول شاخه‌ی اصلی را merge کن (قرارداد v1.4.5، `agents/tools.md`، پروتکل‌های `paused`).
> - **ترتیب:** forkهای ۸ و ۹ که الان در جریان‌اند کدشان را تمام و روی شاخه‌ی خودشان push کنند، ولی **deploy نشوند**. بعد ۶.۱، بعد ۷.۱، deploy. بعد `server/p07-platform` و شاخه‌ی اصلی در ۸ و ۹ merge شوند و آن‌ها deploy شوند.
> - **گزارش:** زیر «Review of 6» در `docs/ops/reports/PROMPT_06.md` و «Review of 7» در `docs/ops/reports/PROMPT_07.md`، برای هر بند یک خط.
> - **قرارداد:** §۱۸.۱۳ (v1.4.5) همین بازبینی است. هر جا کد با آن نخواند، کد را درست کن.

## ۰. اول این‌ها
1. **پرامپت ۶.۱ کامل** (`PROMPT_06_1_FIXES.md`)، به‌جز بندهای ⛔. از آن فقط `files.read` انجام شده است.
   - **بند ۱.۴ آن** (تمیز کردن عکس، api را میکُشد) با بند ۱.۲ همین سند **یک راه‌حل مشترک** دارد. دو بار نساز.
2. **صدا به متن (تصمیم مالک، بی‌هزینه، روی همین سرور).** پرامپت ۷ جایی را که ۶ برای STT کنار گذاشته بود مصرف کرد. از این راه جا باز کن، به این ترتیب:
   - الف) مرورگر در full یک session (حدود 640m).
   - ب) claude-runtime از ۵ اجرای هم‌زمان به ۴.
   - ج) Tempo و otel-collector به profile اختیاری `tracing` بروند (پیش‌فرض خاموش؛ traceها با `make tracing-on` روشن شوند).
   - د) STT با `large-v3-turbo` و `int8`.
   - قاعده‌ی ۸۰٪ و «هیچ سقفی کمتر از دو برابر بیشترین مصرف اندازه‌گیری‌شده» سر جایش است.
   - **اگر باز کم آمد:** مدل کوچک را **انتخاب نکن**. عدد کمبود را در گزارش بنویس.
   - **تست:** همان تست ۶.۱ بند ۰.۱.
3. **پاک کردن** (اجازه‌ی صریح مالک، فقط همین دو): volume `stt-measure-models` و image `coinepro-hq/stt:measure`.
4. **قانون `DOCKER-USER` در iptables مال مالک است؛ به آن دست نزن.** فقط بند ۲.۱۳ را انجام بده، تا شکاف دیده شود.

## ۱. مسدودکننده‌ها
1. **خرابی آرشیو WAL هیچ‌وقت دیده نمیشود و دیسک را پر میکند.** کد: `infra/backup/hourly.sh:169-175` و `backups.py`.
   - **چرا مهم است:** `archive_timeout=60s` هر دقیقه یک segment کامل ۱۶ مگی میسازد. اگر `wal-push` شکست بخورد (پوشه‌ی پر یا مالک اشتباه)، `pg_wal` روزی حدود ۲۳ گیگ بزرگ میشود تا Postgres از کار بیفتد. در همین مدت hourly میگوید `ok:true` و PITR بی‌صدا قطع است.
   - **اصلاح در `hourly.sh`:**
     - `failing = last_failed_time > coalesce(last_archived_time, '-infinity')`
     - `ready_count` = تعداد فایل‌های `.ready` از `pg_ls_archive_statusdir()`
     - هر دو به JSON `wal` اضافه شوند (قرارداد §۱۸.۱۳).
   - **اگر `failing` یا `ready_count > 5`:**
     - `ok:false` و exit غیرصفر، و base backup رد شود.
     - `ingest` **همان لحظه** هشدار فوری بدهد (`backup:wal:{last_failed_at}`)، بدون انتظار ۲ ساعته.
   - **تست:**
     - در gate (`scripts/quality/backup.sh`): `/wal` آزمایشی را `chmod 000` کن، یک ردیف بنویس و `pg_switch_wal()` بزن، صبر کن تا `failed_count>0`، بعد `hourly.sh` را اجرا کن. باید exit غیرصفر و `.wal.failing==true` بدهد.
     - یک تست API: همین وضعیت دقیقاً یک هشدار فوری میسازد.

2. **یک PDF کوچک api را میکُشد؛ عکس بزرگ هم (۶.۱ بند ۱.۴).** کد: `media.py:221-248`، `routes/internal.py:1226`، `routes/files.py:187`، و در egress `extract.py:121` و `app.py:258,265`.
   - **اندازه‌گیری بازبین با pypdf 6.19.0:**
     - یک PDF ۴۹ کیلوبایتی (۲۰ مگ محتوای فشرده‌ی بی‌متن): ۷۵ ثانیه CPU، ۹۵۸ مگ حافظه، و هنوز تمام نشده بود.
     - یک PDF ۱۵ کیلوبایتی با ۵ مگ متن: ۱۱.۷ ثانیه و ۲۱۸ مگ.
   - **چرا خطرناک است:**
     - سقف حافظه‌ی api در full و lean به‌ترتیب 384m و 224m است.
     - دانلودهای `web.browse` از `/internal/v1/files` رد میشوند (`gateway/web.py:297`). پس هر صفحه‌ای که ایجنتی دانلود کند میتواند api را بکُشد.
     - `wait_for(to_thread)` بعد از ۳۰ ثانیه منتظر نمیماند، ولی thread همچنان کار میکند؛ آن هم داخل یک تراکنش باز، با یک اتصال pool در دست.
   - **اصلاح: یک ابزار مشترک، «پردازش فایل نامطمئن».** هر پردازش عکس، PDF یا HTML که از بیرون آمده، در api، worker و egress، از این راه برود:
     - **در یک child process**، با این سقف‌ها:
       - `RLIMIT_AS` حدود 192 MiB (از اندازه‌گیری تعیین کن)
       - `RLIMIT_CPU`
       - مهلت کل که در آن child **kill** میشود (همان الگوی subprocess در `media.py:132`)
     - **بیرون از تراکنش دیتابیس:** فایل اول با `processing` ثبت میشود، پردازش جدا انجام میشود، و نتیجه (`ready` یا `failed`) در تراکنش دوم نوشته میشود.
     - **در egress:** هیچ parse همگامی روی event loop نماند.
     - **عکس (۶.۱ بند ۱.۴):** کپی اضافه نسازد، `MAX_PIXELS` از اندازه‌گیری تعیین شود، و بمب پیکسلی 415 بگیرد.
   - **تست:** همان PDF بمب و یک عکس ۴۰ مگاپیکسلی از هر دو مسیر آپلود. انتظار:
     - 201 در کمتر از ۳۵ ثانیه، با `text` برابر null
     - child کشته شده باشد
     - رشد حافظه‌ی api کمتر از ۵۰ مگ
     - همین PDF از egress هم event loop را قفل نکند (یک `web.read` هم‌زمان جواب بدهد).

3. **سرور بدخواه میتواند درخواست را از `egress.log` و در نتیجه از سقف‌ها بیرون نگه دارد.**
   - **راه‌های فرار:**
     - **charset بد:** `charset=hex` یا `rot13` در `decode()` (`app.py:261,268,316`) به `LookupError` میرسد. نتیجه 500 است و `_carry` (`web.py:238-243`) پیش از `_log` خطا میدهد. آدرس، با هر چه ایجنت در آن گذاشته، تا آن لحظه رفته است.
     - **سرور کند:** `net.py:118-128` فقط مهلت هر read را دارد. سروری که هر ۱۰ ثانیه یک بایت میدهد از `wait_for` ۲۵ ثانیه‌ای gateway (`gateway.py:225`) بیشتر میماند و هیچ log‌ی ثبت نمیشود. اتصال هم از pool مشترک ۲۰تایی گرفته میماند: ۲۰ فراخوانی این‌طوری `web.read` و `http.request` را برای همه‌ی شرکت‌ها میبندد.
     - **یک ردیف بد کل batch را میاندازد:** `routes/egress.py:131-142` طول `method` را ۱۰ و `status` را 100 تا 999 میگیرد، ولی proxy هر method و هر status را رد میکند (`proxy.py:149,248,285`). نتیجه 422 برای همه‌ی ردیف‌هاست. `_log` (`web.py:182-190`) status را نگاه نمیکند و بعد از ۲۰۰ ردیف میبُرد.
     - **خطای parser:** `extract.py:326` فقط چهار نوع خطا را میگیرد.
   - **اصلاح:**
     - codec با `codecs.lookup(n)._is_text_encoding` بررسی شود.
     - هر handler در egress یک catch-all داشته باشد که ردیف‌هایش را باز هم برگرداند.
     - هر فراخوانی یک مهلت کل (`asyncio.timeout`) کمتر از مهلت gateway داشته باشد.
     - `method`، `status` و `reason` در خود egress بریده و محدود شوند.
     - در gateway، log در یک `finally` محافظت‌شده (shielded) نوشته شود، جواب 204 بررسی شود، و بیش از ۲۰۰ ردیف جمع زده شود.
     - **`reserve` پیش از رفتن درخواست یک ردیف بنویسد** تا جواب گم‌شده هم شمرده شود.
   - **تست:** سه سایت ساختگی (`charset=hex`، قطره‌چکان، status 9999). در هر سه، برای آن host یک ردیف log هست و فراخوانی در مهلت تمام میشود.

4. **مرز `needs_owner` (A3) دور زده میشود.**
   - **چهار راه:**
     - **فرزند دکمه:** `FACTS_JS` و `commitment` (`rules.py:135-191`) فقط خود عنصر کلیک‌شده را میبینند. کلیک روی `button[type=submit] span` یا یک `<label for=submit>` در فرم `/checkout` یا فرم رمز، tag را SPAN میکند و اجازه میگیرد.
     - **segmentهای نقطه‌دار:** `non_committing` (`domain/egress.py:94-101`) مسیر خام را میسنجد. قاعده‌ی `POST /api/search`، مسیر `/api/search/../../v1/charges` را هم میپذیرد، و httpx آن را `/v1/charges` میفرستد.
     - **redirect:** 307 و 308 همان POST را با اعتبار تزریق‌شده دوباره میفرستند (`net.py:180-186`)، بی آن‌که policy دوباره سنجیده شود.
     - **browse:** `web.browse` با حساب، قاعده‌های allow حساب را هیچ‌وقت اعمال نمیکند (`routes/egress.py:370` فقط `http.request` را میسنجد).
   - **اصلاح:**
     - در `FACTS_JS`، عنصر به هدف فعال‌سازی‌اش برسد: `el.closest('button,input,a,[role=button],label')`، و label به control خودش.
     - مسیر نرمال شود (unquote، بعد normpath). هر `.`، `..`، `%2e` یا `//` رد شود.
     - برای methodهای غیر GET، redirect دنبال نشود.
     - **پشتوانه در مرورگر:** یک handler `ctx.route` که هر درخواست غیر GET/HEAD را که با یک قاعده‌ی allow حساب نمیخواند abort کند و قدم را `needs_owner` کند.
   - **تست:** فرم checkout که از راه span کلیک میشود ← `needs_owner`. `reserve` برای `POST …/api/search/../../pay` ← `needs_owner`.

5. **اعتبار حساب browse با یک redirect بیرون میرود.**
   - `browser.py:159-168` header را با `route.continue_(headers=…)` میگذارد. مستند Playwright میگوید این headerها روی redirectهای همان درخواست هم میروند.
   - پس یک open redirect روی سایت خود حساب، اعتبار را به هر hostی میفرستد.
   - **اصلاح:** `route.fetch(headers=…, max_redirects=0)` و بعد `route.fulfill(response=…)`، تا هر hop دوباره از handler رد شود و با host خودش سنجیده شود.
   - **تست:** سایت حساب با 302 به host ساختگی دوم جواب میدهد. host دوم هیچ‌وقت header را نمیگیرد.

6. **محافظ داده، داده‌ی رمزگذاری‌شده را نمیبیند.**
   - `internal_data` (`domain/egress.py:49-60`) رشته‌ی خام را میگردد. همه‌ی این‌ها رد میشوند:
     - `ali%40example.com`، `FX%2DTECH%2DMGR`، `W%2D000123`
     - شماره‌ی تلفن فارسی percent-encode‌شده
     - `fx-tech-mgr` با حروف کوچک، و خط تیره‌ی full-width
   - ایجنت درستکاری که URLش را encode کند، بی‌آن‌که بخواهد داده را بیرون میدهد.
   - **اصلاح:**
     - `unquote_plus` تکرار شود تا دیگر تغییر نکند، بعد NFKC، بعد ارقام فارسی و عربی به لاتین.
     - کدهای کارمند بدون حساسیت به بزرگی حروف تطبیق داده شوند.
     - رشته‌های base64 یا hex با ۱۶ نویسه یا بیشتر هم بعد از decode گشته شوند.
   - **تست:** هر رشته‌ی بالا ← `internal_data`.

## ۲. باید
**Backup**
1. **PITR هفتگی سقف ثابت ۱۲۰ ثانیه دارد** (`pitr.sh:214`). replay ۲۴ ساعت WAL (حدود ۱۴۴۰ segment) از این بیشتر طول میکشد، و هر یکشنبه یک هشدار فوری دروغ میآید.
   - **اصلاح:** مهلت حدود ۴۵ دقیقه. فقط وقتی شکست حساب شود که `pg_last_wal_replay_lsn()` ۱۲۰ ثانیه جلو نرود.
   - **تست:** در gate، حدود ۳۰۰ دور insert + `pg_switch_wal()` پیش از نقطه‌ی هدف.
2. **توکن snapshot OpenBao بعد از ۳۲ روز منقضی میشود** و `openbao_snapshot.ok=false` هشداری نمیدهد.
   - بعد از هر snapshot موفق `auth/token/renew-self` زده شود.
   - وقتی snapshot پیکربندی شده ولی `ok` نیست، هشدار بیاید.
3. **off-site بی‌صدا به local تنها میافتد** (`restic-lib.sh:65-67, 96-103`). `bao_get` هر خطا را «پیکربندی نشده» میخواند.
   - فقط 404 یعنی «پیکربندی نشده»؛ هر کد دیگری run را شکست میدهد.
   - در `state.json` ثبت شود که Drive یک بار پیکربندی شده بود. اگر بعداً ناپدید شد، خطاست.
   - **تست:** OpenBao ساختگی برای gdrive جواب 503 میدهد ← `ok:false`.
4. **خطاهای بی‌هشدار:**
   - شکست `restic check` (`hourly.sh:266-276`) ← هشدار فوری `backup:check:{at}`.
   - نبودن `hourly.json` در حالی که `backup.runs` ردیف دارد (`backups.py:164`) ← هشدار فوری.
   - یک متریک textfile با زمان آخرین موفقیت، به‌عنوان dead-man's switch در Prometheus، تا هشدار به worker و Temporal بسته نباشد.
5. **تست بازیابی دوم نتیجه‌ی اولی را خراب میکند** (`restore-weekly.sh:54-57`).
   - اول قفل (`flock`) گرفته شود، بعد trap. اگر قفل گرفته است، بی‌صدا خارج شود.
   - فراخوانی‌های restic در این مسیر `--retry-lock 30m` بگیرند.
6. **PITR ممکن است کمتر از ۷ روز را بپوشاند** (`hourly.sh:28,58-63`). شرط «due» بعد از ۲۳ ساعت درست میشود و base backupها جلو میافتند.
   - «due» با روز تقویمی (UTC) سنجیده شود و ۹ base backup نگه داشته شود.
   - **تست:** تست واحد shell برای `due` با ساعت‌های ثابت.
7. **هیچ محافظی برای دیسک نیست.**
   - `pg_dump -Fc -Z0` شود، چون restic خودش با zstd فشرده میکند و dedup فقط این‌طور کار میکند.
   - پیش از بازیابی، `restic stats --mode restore-size <id>` با `df` مقایسه شود. اگر جا کم است، با یک یادداشت روشن رد شود.
8. **مسیر OAuth client خود مالک دسترسی کامل Drive میگیرد** (`gdrive-auth.sh:25`).
   - یک JSON base64 بدون padding با `client_id`، `client_secret` و `"scope":"drive.file"` فرستاده شود.
   - RUNBOOK بگوید consent screen باید «In production» باشد. در حالت «Testing»، گوگل refresh token را بعد از ۷ روز باطل میکند. (این کار مالک است؛ فقط در RUNBOOK و فهرست کارهای مالک بیاید.)
9. **رمز restic ممکن است دوباره ساخته شود** (`provision.sh:296`). نوشتن با KV check-and-set (`{"options":{"cas":0}}`) باشد.

**MCP و فایل‌ها**

10. **فراخوانی A3 تأییدشده‌ی MCP هیچ‌وقت اجرا نمیشود و ایجنت در حلقه میافتد** (`tools.py:252-313`). قرارداد §۱۸.۱۳:
   - در `resolve`، یک کارت تأییدشده و استفاده‌نشده برای (company، server، tool، `args_sha256`، `registration_sha256`) از ۲۴ ساعت گذشته، از هر run، پیدا شود.
   - کارت به‌صورت اتمی مصرف شود (`decision_id` یکتا، outcome `approved`) و همان یک فراخوانی اجرا شود.
   - کارت ردشده ← `denied`، بدون کارت تازه.
   - پیش‌نمایش کارت گیرنده و مبلغ را نشان بدهد؛ فقط secretها پوشانده شوند.
   - **تست:** تأیید، بعد فراخوانی بعدی با همان args یک بار اجرا میشود؛ فراخوانی دوم کارت تازه میسازد.
11. **MCP روی `http` از `egress/reserve` رد نمیشود** (`gateway.py:272-344`)، در حالی که RUNBOOK §۲۰ میگوید میشود.
   - پیش از باز کردن سرور، `reserve` با ابزار `mcp.call`، host و رشته‌های args صدا زده شود.
   - **تست:** کد کارمند در args ← `internal_data` بدون CONNECT. سقف تمام‌شده ← `egress_limit`.
12. **schema `tools` در تست‌های RLS نیست** (`test_rls_all_tables.py:21`، `test_schema_rules.py:18`).
   - `"tools"` به هر دو فهرست اضافه شود، و یک ردیف `mcp_calls` در `_fill_agents` بیاید.
   - فهرست صریح جدول‌های بی‌شرکت (`mcp_servers`، `accounts`) assert شود.
13. **`Idempotency-Key`** روی سه POST MCP و روی `POST /tools/accounts`: `idempotency.claim(required=True)` پیش از `stepup.consume`.
   - **تست:** همان key و body دو بار ← همان 201 با `Idempotent-Replay`.
14. **`POST /tools/accounts` مهر میخواهد:** 🔏 `account.put`، با target برابر sha256 body (قرارداد §۱۸.۱۰). site، قاعده‌ی allow یا port تازه، کاری را که secret ذخیره‌شده میتواند بکند گسترش میدهد.
15. **سرورهای پیشنهادی `container` اجراشدنی نیستند:** شبکه‌ی `hq-mcp` و پل stdio→HTTP وجود ندارد.
   - در این پرامپت ساخته **نشوند**.
   - `enable` برای transport `container` جواب `409 not_ready` بدهد، با `status_reason` روشن.
   - در گزارش و `/tools/catalog` «هنوز اجراشدنی نیست» بیاید.
   - `mcp-secret.sh` یک فایل JSON چندخطی (service account گوگل) را هم بپذیرد: بررسی شود که JSON است، همان‌طور ذخیره شود، و بعد پیشنهاد پاک کردن فایل بدهد.
16. **فهرست تغییرکرده:** سرور خاموش شود و یک کارت `tool_enable` بیاید، با `{key, listing_sha256, diff}`. تأییدش همان مهر معمول تصمیم (🔏 `decision.approve`) است و سرور را **دقیقاً با همان فهرست** روشن میکند. فهرستی که پیش از مهر دوباره عوض شده، کارت را کنار میگذارد (`409 decision_not_pending`) و کارت تازه میآید (قرارداد §۱۸.۱۳).

**درگاه خروجی**

17. **پاک کردن secret از خروجی** (`accounts.py:188-196`):
   - گونه‌ی `base64("user:secret")` هم پاک شود.
   - پاک کردن **پیش از** بریدن متن انجام شود (`app.py:321`، `browser.py:241`).
   - بایت‌های دانلودها و فایل‌ها هم گشته شوند؛ اگر secret داشتند، فایل دور انداخته شود.
   - secret فقط روی `https` تزریق شود.
18. **portهای حساب فقط برای سایت خود حساب باز شوند** (`net.py:158`، `guard.py:116`)، فقط وقتی `account.covers(host)`.
19. **`live.sh:110`** علاوه بر نام سرویس، با IP هم آزمایش کند: 10.10.1.1-3، 169.254.169.254 و آدرس‌های خود میزبان، از egress و SearXNG. نتیجه در گزارش بیاید. بستنش با قانون `DOCKER-USER` است، که مال مالک است (بند ۰.۴).
20. **سقف منابع:**
   - `MEM_EGRESS` در lean (128m) با بدنه‌ی ۲۰ مگی و درخت lxml نمیخواند؛ از اندازه‌گیری تعیین شود.
   - مجموع فایل‌های یک browse سقف داشته باشد.
   - heap کرومیوم سقف داشته باشد (`--js-flags=--max-old-space-size`).
   - **sandbox کرومیوم روشن شود** (کاربر غیر root، با پروفایل seccomp خود Playwright). اگر نشد، هر فراخوانی browser خودش را داشته باشد. **هیچ‌وقت یک process `--no-sandbox` بین شرکت‌ها مشترک نباشد.**
21. **تشخیص تعهد:**
   - تعهدهای GET (مثل `formResponse` گوگل فرم و trigger وب‌هوک) در `http.request` GET و `goto` مرورگر هم سنجیده شوند.
   - برچسب‌های Submit، Continue، Confirm، Share، Delete، Promote، «ثبت» و «تایید» به فهرست اضافه شوند.
   - «ي» و «ك» عربی نرمال شوند.
   - `select`ی که `onchange` آن فرم را میفرستد هم سنجیده شود.
22. **`egress_limit`** هدر `Retry-After` بگیرد.

## ۳. ریز
**Backup**
- `repo_ready` (`restic-lib.sh:157-167`) را به `init || return` تبدیل کن. چون داخل `if !` اجرا میشود، `set -e` کار نمیکند.
- خطایی که پیش از `load_secrets` رخ میدهد gdrive را «پیکربندی نشده» ثبت نکند.
- config rclone قابل‌نوشتن باشد، تا توکن تازه‌شده ذخیره شود.
- `/dev/shm` به `RuntimeDirectory=` در unitها تبدیل شود.
- capabilityهای اضافه فقط به restore داده شود.
- توکن‌ها از راه stdin به jq برسند، نه env.
- worker به `backup-tools` وابسته نباشد.
- `MEM_BACKUP` در RUNBOOK با `full.env` یکی شود.
- شکست `forget` remote هشدار بدهد.
- **تست‌ها:**
  - مسیر واقعی OpenBao بدون bypass
  - Drive پیکربندی‌نشده
  - قفل‌ها
  - هدف تصادفی PITR

**درگاه خروجی**
- متن پنهان و `aria-hidden` از `extract.py:212` حذف شود. نتیجه‌ی وب `untrusted: true` بگیرد، مثل MCP.
- IP عمومی هاب هم در `hub_hosts` باشد.
- WebRTC بسته شود: `--force-webrtc-ip-handling-policy=disable_non_proxied_udp`.
- `proxy.py:254` (query بدون path) و `proxy.py:114` (`LimitOverrunError`) درست شوند.
- بریدن دانلود در `_download` بی‌صدا نباشد.
- خطای `_sign_in` با کد خودش بیاید، نه `browser_unavailable`.
- ردشده‌های `reserve` یک ردیف audit هم بنویسند.
- `run_id` خالی، سقف‌های هر run را خاموش نکند.
- **تست‌های `classify`:** Teredo، `::a.b.c.d` و `64:ff9b:1::`.
- **تست مرورگر واقعی:** `needs_owner` و پوشاندن screenshot.

**MCP**
- `domain/mcp.py:93-101`: نقطه‌ی آخر host برداشته شود، و port غیر 443 رد شود.
- `domain/mcp.py:209`:
  - ثبت دوباره‌ی همان body، سرور روشن را pending نکند.
  - عوض شدن host، `has_secret` را صفر کند.
- `gateway/mcp.py:81`: hash فهرست `title`، `output_schema` و `annotations` را هم بگیرد، و paging `list_tools` خوانده شود.
- `tools.py:191-208`: شمارش سقف قفل شود، A3 هم سقف داشته باشد، و 429 هدر `Retry-After` بگیرد.
- `tools.py:325`: `row["companies"]` بررسی شود.
- `gateway.py:399`: POST ناموفق فهرست، `mcp_tools_changed` گزارش نشود.
- ستون بی‌استفاده‌ی `auth_scheme` (`0017:47`) در migration بعدی برداشته شود.
- متن MCP هم پرچم `suspected_injection` بگیرد.

## ۴. کارهای مالک (فقط در گزارش، به همین ترتیب)
`make gdrive-auth` · `make backup-password` · `make openbao-snapshot-token` · consent screen گوگل روی «In production» · مهر سرورهای MCP `http` که میخواهد · `make account-secret` · قانون `DOCKER-USER` (اختیاری).

## ۵. بعد
وقتی ۶.۱ و ۷.۱ deploy و push شدند، `server/p07-platform` و شاخه‌ی اصلی را در شاخه‌های ۸ و ۹ merge کن. در ۸، پروتکل‌های `paused`، `OVERSIGHT_DAILY_SHARE` و سقف 200000 ناظر و مشاور را حتماً بیاور (`PROMPT_08` §۲.۲ و §۲.۳). بعد ۸ و ۹ را deploy کن و گزارش بده.
