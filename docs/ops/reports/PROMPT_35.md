# گزارش پرامپت ۳۵: به‌روزرسانی ۱.۰.۱ (deploy)

> Claude سرور هاب، ۲۰۲۶-۱۱-۱۱. شاخه‌ی `server/p35-deploy` = شاخه‌ی اصلی `b46deeb7` + همین گزارش. alembic: `0059` → **`0061`**.

- **تست‌ها:** OPA ‏۳۰۷ از ۳۰۷ (پوشش ۱۰۰٪). lint، format و mypy سبز. gateway، hq-common و company-runner سبز.
- **تست‌های api:** ۱۵ فایل پرامپت در یک اجرا، ۴ قرمز داد (`w11_activity`، دو تست `p13f_join`، fuzz سند OpenAPI). هر فایل جدا **سبز** است (fuzz: ۳ از ۳). همان وابستگی ترتیب گزارش ۳۲ است؛ قرمز واقعی نبود. commit کد از خودم لازم نشد.
- **deploy:** بکاپ `20261111T142753Z`، بعد migration ‏`0060` و `0061`. ساعت 14:30 تا 14:31 UTC، api و worker و gateway و web ‏(**1.0.1**) healthy شدند. OPA سیاست تازه را بی خطا خواند.
- **سنجش:** `healthz` ‏200. `runners/jobs/<uuid>/tools`، `publish-desk` و `treasury/limits` بی توکن **401** می‌دهند. `/internal` از بیرون 404 است.
- **`verify-live`:** **سبز**: rc=0، بی FAIL؛ فقط دو GAP همیشگی.
- **runner کارگاه:** هنوز **0.3.3** و online است (0.3.4 هم نصب نشده بود). دستورهای 0.3.5 در پایین آمده. پیش از restart، نوبت کارگاهی در جریان نباشد. بقیه‌ی runnerها روی 0.3.4 و online هستند، IG-Hub هم.
- **نوبت مستقیم:** **هنوز آزمایش نشده.** صفر job با `args.direct` و صفر اجرای `direct` در `agents.runs`. `HQ_DIRECT_SESSIONS` دست نخورد.
- **sweep** (14:30 تا 14:41): **بی خطا.** در لاگ api و worker نه خطی از `follow_up`، `read_due`، `connections_read` و `direct_tool` بود، نه هیچ `error` یا Traceback دیگری.
- **بهترین ساعت:** `growth.ig_post_reads` **۰ ردیف** دارد. اتصال instagram هیچ شرکتی `read_command` یا `publish_command` ندارد، پس هنوز هیچ خواندنی پرسیده نشده است.
- **شمارها:** `growth.topics` ۰، `media.narrators` ۰، روال دائمی ۰. میز انتشار: `ready` ۰، `queue` ۰ و `done` ۰.
- **سقف:** `claude-max` در حال `working` است (`warning`، `seven_day`، ۹۱٪، ریست 2026-11-12 00:00 UTC). `claude-max-2` در حال `ready` است و هنوز `quota_status` ندارد. کنتور امروز: ۰.
- **اتصال instagram:** FX، IG، PC و TY: هیچ‌کدام `command`/`read_command` یا `publish_command` ندارند.
- **AI Studio:** **`unknown`**، چون هنوز هیچ صدایی ساخته نشده. اگر نخستین صدا `signed_out` گفت، مالک یک بار `make aistudio-web-login` بزند.
- **دست‌نخورده:** هیچ چیزی منتشر نشد و هیچ گوینده، اجازه‌ی دائمی یا `publish_command`ی تنظیم نشد. هیچ داده‌ای پاک یا لغو نشد. به هیچ سروری جز هاب دست زده نشد. gitleaks روی همین گزارش سبز بود.

**runner کارگاه به 0.3.5** (مالک، روی هاب):
```bash
cd /home/Hub/CoinePro-Hub && git fetch -q origin
git archive origin/server/p35-deploy services/company-runner | sudo -u studio tar -x -C /home/studio
printf '%s\n' 'set -e' 'cd ~/services/company-runner' 'V=~/.local/share/hq-runner/venv/bin' \
  '$V/pip install -q --require-hashes -r requirements.lock' '$V/pip install -q --no-deps --force-reinstall .' \
  '$V/hq-runner --version' '$V/hq-runner sandbox-check' > /tmp/runner-035.sh
sudo -u studio -H bash /tmp/runner-035.sh && sudo systemctl restart hq-runner@studio
```

این گزارش را برای Claude سشن مشورت ببر.
