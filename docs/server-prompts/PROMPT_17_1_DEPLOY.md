# پرامپت ۱۷.۱: فقط deploy کد runnerها (بدون نوشتن کد)

> Claude سشن مشورت، ۲۰۲۶-۱۰-۳۰.
> - **کد:** به درخواست خود Claude سرور هاب، کد پرامپت ۱۷ را سشن مشورت نوشته، تست کرده و روی شاخه‌ی اصلی push کرده است.
> - **کار تو:** این پرامپت **فقط deploy** است. کدی ننویس. اگر چیزی خراب بود، گزارش بده.
> - **شاخه:** `server/p17-1-deploy` از سر شاخه‌ی اصلی، `claude/coinepro-hub-setup-hsvnw7` بعد از pull.
> - **گزارش:** `docs/ops/reports/PROMPT_17_1.md`.

## آنچه در شاخه است (مرجع: قرارداد §۲۶)
- **migration ۰۰۳۲:**
  - سرورهای attach‌شده
  - جفت‌سازی و runnerها (فقط hash توکن)
  - کارهای سرور و رویدادهایشان
  - نقشه‌ی شبکه
  - سیاست سرورها
  - کارت `server_destructive`
- **`apps/api`:** مسیرهای `/runners/*`، `/infra/servers/*`، `/infra/network` و `/control/server-policy`، و runtime `company_server` در کارگاه.
- **`services/gateway`:** پنج ابزار `server.*` و قانون میان‌شرکتی.
- **پروتکل و منشورها:** پروتکل PR-130 (بررسی روزانه‌ی شبکه)، و ابزارهای پیش‌فرض در منشورها.
- **Caddy:** بلوک `/api/v1/runners/*` و SSE ترمینال مالک. `/internal` همچنان بسته است.
- **`services/company-runner`:** برنامه‌ای که Claude هر سرور شرکت نصبش میکند. **روی هاب نصب نمیشود.**

## deploy
1. `git pull` و `make check`. هر قرمزی را گزارش کن و جلو نرو.
2. `make backup`.
3. migration ۰۰۳۲. downgrade آن را در گزارش تأیید کن.
4. image‌های api، worker و gateway را دوباره بساز و بالا بیاور.
5. OPA را با `servers.rego` و `a2_grants` تازه، و Caddy را reload کن.
6. `make verify-live`، و این سه سنجش:
   - `curl -s https://hq.coinepro.com/api/v1/runners/pair` با GET باید `405` بدهد.
   - همین مسیر از `10.10.1.4:443` با همان گواهی جواب بدهد.
   - `/internal` همچنان `404` بدهد.
7. گزارش کوتاه به مالک، فارسی:
   - سبز یا قرمز
   - شماره‌ی migration
   - قدم بعدی مالک: نصب runner روی هر سرور با `COMPANY_SERVER_ACCESS_SETUP.md`

## قوانین
- **دسترسی به سرورها:** به هیچ سرور شرکتی وصل نشو و دست نزن.
- **رمزها:** رمز چاپ نشود.
- **کلید توقف:** همان‌طور که مالک گذاشته بماند.
