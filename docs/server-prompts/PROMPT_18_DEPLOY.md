# پرامپت ۱۸: فقط deploy کد runnerها، بازیکن، شورا و صدا به متن (بدون نوشتن کد)

> Claude سشن مشورت، ۲۰۲۶-۱۰-۳۰.
> - **کد:** کد پرامپت ۱۷، ۱۷.۱ و ۱۸ (قرارداد §۲۶ و §۲۷ ⟨1.9⟩) را سشن مشورت نوشته، تست کرده و روی شاخه‌ی اصلی push کرده است.
> - **این پرامپت جای ۱۷.۱ را هم میگیرد.** اگر ۱۷.۱ اجرا نشده، فقط همین را اجرا کن. اگر شده، قدم‌های تکراری بی‌ضررند و فقط تأیید میشوند.
> - **کار تو:** فقط deploy. کدی ننویس. اگر چیزی خراب بود، گزارش بده.
> - **شاخه:** `server/p18-deploy` از سر شاخه‌ی اصلی، `claude/coinepro-hub-setup-hsvnw7` بعد از pull.
> - **گزارش:** `docs/ops/reports/PROMPT_18.md`.

## آنچه در شاخه است
### runnerهای سرور شرکت‌ها (§۲۶، پرامپت ۱۷ و ۱۷.۱)
- **migration ۰۰۳۲:** سرورهای attach‌شده، جفت‌سازی و runnerها (فقط hash توکن)، کارهای سرور و رویدادهایشان، نقشه‌ی شبکه، سیاست سرورها و کارت `server_destructive`.
- **`apps/api`:** مسیرهای `/runners/*`، `/infra/servers/*`، `/infra/network` و `/control/server-policy`، و runtime ‏`company_server` در کارگاه.
- **`services/gateway`:** پنج ابزار `server.*` و قانون میان‌شرکتی.
- **OPA:** `servers.rego` و `a2_grants` تازه.
- **Caddy:** بلوک `/api/v1/runners/*` و SSE ترمینال مالک. `/internal` همچنان بسته است.
- **پروتکل و منشورها:** PR-130 (بررسی روزانه‌ی شبکه) و دو نقش تازه در TECH: `devops_engineer` و `lead_developer`، با هر پنج ابزار `server.*`.
- **`services/company-runner`:** برنامه‌ای که Claude هر سرور شرکت نصبش میکند. **روی هاب نصب نمیشود.**

### بازیکن، شورا و صدا به متن (§۲۷، پرامپت ۱۸)
- **migration ۰۰۳۳:**
  - `work.work`: بازیکن (`player`)، حالت (`mode`) و `media`، و زمان‌های انتظار و برگشت بازیکن.
  - جدول تازه‌ی `work.councils`، با FORCE RLS و بدون حذف.
  - `substitutes.creatives`: ستون‌های `picked_at` و `source_creative_id`.
- **بازیکن هر سفارش:**
  - کار با بازیکن ذخیره (ChatGPT، Gemini یا DeepSeek) به صندلی همان بازیکن میرود و خروجی برچسب منبع دارد.
  - بازیکنی که در دسترس نیست تا ۳۰ دقیقه منتظر میماند، بعد کار با انتخاب خودکار ادامه پیدا میکند، با یک اعلان.
  - این سنجش را Maintenance ‏worker هر ۵ دقیقه انجام میدهد (activity ‏`players_sweep`).
- **شورا:**
  - هر بازیکن آماده جواب میدهد و Claude جمع‌بندی را مینویسد. `GET /api/v1/work/{id}/council`.
  - شورای تصویر و ویدیو: هر بازیکن نسخه‌ی خودش را میسازد. `POST /api/v1/creatives/{ref}/pick` و `/animate`.
- **صدا به متن روی هاب، بر حسب نیاز:**
  - مدل `small` است. stt سرویس همیشه‌روشن نیست:
    - worker فایل `/run/hq/stt/want` را لمس میکند.
    - `coinepro-hq-stt.path` با کاربر Hub ‏`infra/stt/on-demand.sh` را اجرا میکند.
    - این اسکریپت زیر قفل one-shot ‏stt را بالا میآورد و ۵ دقیقه بعد از آخرین درخواست خاموشش میکند.
  - worker سوکت Docker ندارد.
  - `MEM_STT=832m`. worker هر صدا را در تکه‌های حداکثر ۳۰ ثانیه میفرستد.
  - گیت حافظه stt را به‌شکل burst میشمارد. روی همین هاب: full + substitutes + substitutes-web + stt برابر 12396 از 12486 MiB است. **پس دیگر شرطی نیست.**
- **شروع تازه:** دیگر روی ردیف‌های نگه‌داشته‌ای که به داده‌ی پاک‌شده اشاره دارند گیر نمیکند. نمونه‌های صدای bake-off با کار گفتارشان میمانند.

## deploy
1. **pull و سنجش:**
   - `git pull`.
   - `make check` را در یک worktree جدا اجرا کن (`git worktree add`)، تا پوشه‌ی کاری سرور دست نخورد.
   - هر قرمزی را گزارش کن و جلو نرو. بعد worktree را با `git worktree remove` بردار.
2. `make backup`.
3. **migrationها:**
   - ۰۰۳۲ (اگر هنوز اجرا نشده) و ۰۰۳۳.
   - در گزارش تأیید کن که `alembic current` روی `0033` است و downgrade هر دو در کد هست.
4. **image‌ها:** `api`، `worker` و `gateway` را دوباره بساز و بالا بیاور. image ‏`stt` هم ساخته میشود (قدم ۶).
5. **واحدهای systemd:** `make install-systemd`. این فرمان `coinepro-hq-stt.service`، `coinepro-hq-stt.path` و پوشه‌ی `/run/hq/stt` را نصب میکند. path را روشن نمیکند.
6. **صدا به متن:**
   - `make stt-on`. این فرمان مدل `small` را با sha256 میگیرد، `HQ_STT=on` میگذارد، api و worker را بالا میآورد و `coinepro-hq-stt.path` را روشن میکند.
   - `make stt-cold`: شروع سرد را روی همین سرور اندازه میگیرد (روشن شدن کانتینر، `/health`، اولین رونویسی). عددها را در گزارش بنویس.
   - اگر `hq.sh` رد کرد (exit 3)، عددها را گزارش کن و `make stt-off` بزن. با این حساب نباید رد شود.
7. **OPA و Caddy:** OPA را با `servers.rego` و `a2_grants` تازه، و Caddy را reload کن.
8. **Web Push (پنل وب):**
   - `GET /api/v1/meta` را با نشست مالک بخوان.
   - اگر `channels.web_push` برابر `false` است، کلید VAPID در OpenBao (`kv/hq-api/webpush`) نیست. `make llm-provision` آن را میسازد. این فرمان idempotent است، فقط چیزهای نبوده را میسازد و هیچ مقداری چاپ نمیکند.
   - بعد api و worker را با `infra/compose/hq.sh up -d api worker` بالا بیاور تا کلید را بخوانند، یا ۵ دقیقه صبر کن.
   - در گزارش فقط بنویس `web_push` روشن است یا نه. هیچ کلیدی چاپ نشود.
9. **`make verify-live` و این سنجش‌ها:**
   - `curl -s https://hq.coinepro.com/api/v1/runners/pair` با GET باید `405` بدهد.
   - همین مسیر از `10.10.1.4:443` با همان گواهی جواب بدهد.
   - `/internal` همچنان `404` بدهد.
   - `GET /api/v1/meta`: ‏`speech.enabled` برابر `true` باشد (یعنی نصب است، نه در حال اجرا).
   - `scripts/quality/memory-budget.sh` روی همین سرور سبز باشد، با خط `full+substitutes+substitutes-web+stt (on demand) ok`. البته اگر این دو پروفایل روشن‌اند.
   - بعد از ۵ دقیقه، در لاگ worker، Maintenance ‏`players_sweep` را بدون خطا اجرا کرده باشد.
   - بعد از `make stt-cold`، کانتینر stt خاموش باشد (`infra/compose/hq.sh --profile stt ps stt`).
10. **گزارش کوتاه به مالک، فارسی:**
    - سبز یا قرمز
    - شماره‌ی migration
    - شروع سرد stt (میلی‌ثانیه)
    - Web Push روشن است یا نه
    - قدم بعدی مالک:
      - نصب runner روی هر سرور با `COMPANY_SERVER_ACCESS_SETUP.md`
      - از اپ: یک فرمان صوتی «با جی‌پی‌تی …» و یک سفارش «شورا»

## قوانین
- **دسترسی به سرورها:** به هیچ سرور شرکتی وصل نشو و دست نزن.
- **رمزها:** رمز یا کلیدی چاپ نشود، فقط نام متغیرها.
- **کلید توقف:** همان‌طور که مالک گذاشته بماند.
- **حافظه:** سقف حافظه‌ی هیچ سرویسی را عوض نکن. پروفایلی را که مالک روشن کرده خاموش نکن.
