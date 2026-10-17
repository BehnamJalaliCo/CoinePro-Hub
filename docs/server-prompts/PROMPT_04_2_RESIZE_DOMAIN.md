# پرامپت ۴.۲: ارتقای سرور به 16GB و دامنه‌ی `hq.coinepro.com`

> **برای مالک (تصمیم شما، ۲۰۲۶-۱۰-۱۷):** رم سرور هاب به **16GB** میرود و دامنه‌ی پنل **`hq.coinepro.com`** است. این پرامپت **دو بخش** دارد و کار شما بینشان است:
> 1. **همین حالا (کار شما):** در DNS دامنه‌ی `coinepro.com` یک رکورد **A** بسازید: `hq` ← IPv4 عمومی سرور هاب (از کنسول هتزنر). اگر DNS روی Cloudflare است، **فقط DNS** (ابر خاکستری). در **فایروال هتزنر** ورودی **TCP 80 و 443** به سرور هاب باز باشد (برای گرفتن گواهی HTTPS لازم است).
> 2. به Claude سرور بگویید: «`git pull` کن و **بخش الف** `docs/server-prompts/PROMPT_04_2_RESIZE_DOMAIN.md` را اجرا کن.» صبر کنید تا بگوید «آماده‌ی خاموش شدن».
> 3. **کار شما در کنسول هتزنر:** سرور هاب ← **Shutdown** (نه Power off) ← **Rescale** ← پلنی با **16GB رم** (ترجیحاً همان خانواده‌ی AMD فعلی) و گزینه‌ی **«فقط CPU و RAM»** (دیسک بزرگ نشود تا برگشت ممکن بماند) ← **Power on**. ریبوت کرنل که از پرامپت ۱ مانده بود هم با همین روشن شدن انجام میشود.
> 4. به Claude سرور بگویید: «**بخش ب** همان پرامپت را اجرا کن.» گزارش کوتاهش را برای Claude سشن مشورت بیاورید.
>
> اگر پرامپت ۴.۱ در حال اجراست، اول گزارشش را بگیرید، بعد این پرامپت. اگر هنوز شروع نشده، اول این پرامپت، بعد ۴.۱.

---

تو **Claude Code روی سرور هاب «CoinePro HQ»** هستی. مالک سرور را به 16GB ارتقا میدهد و دامنه‌ی `hq.coinepro.com` را برای پنل ساخته است. **خاموش کردن، Rescale و روشن کردن را خود مالک از کنسول هتزنر انجام میدهد؛ تو سرور را خاموش یا ریبوت نکن.** به SSH، کاربرها، کلیدها، fail2ban، ufw و iptables دست نزن. فایروال فقط فایروال هتزنر است و مال مالک.

## بخش الف: پیش از خاموش شدن
1. در `/home/Hub/CoinePro-Hub` روی شاخه‌ای که هستی، هر کار commit‌نشده را commit و push کن. اگر کاری نیمه‌کاره است، همان را گزارش کن و **متوقف شو** (مالک صبر میکند).
2. `make backup`، سپس `make restore-test`. هر دو باید سالم باشند. حجم و زمان backup را بنویس.
3. بررسی کن همه‌ی سرویس‌های دائمی `restart: unless-stopped` دارند و Docker با سیستم بالا میاید (`systemctl is-enabled docker`). کار یک‌باره‌ها (`*-migrate`، `*-schema`، `*-namespace`) با `make up` دوباره اجرا میشوند.
4. برای مقایسه ثبت کن: `uname -r`، `free -h`، `docker compose ps` (تعداد healthy)، و `ss -tlnp` (فقط پورت‌ها و نام سرویس).
5. گزارش بخش الف (حداکثر ۶ خط) با خط آخر **«آماده‌ی خاموش شدن است؛ مالک میتواند Shutdown و Rescale کند.»** سپس **متوقف شو.**

## بخش ب: بعد از روشن شدن با 16GB
1. `uname -r` (باید کرنل تازه باشد)، `free -h` (حدود 16GB)، `nproc`.
2. `make up`؛ همه healthy؟ `ss -tlnp`: **هیچ پورت عمومی تازه** (فقط 80، 443 و پورت SSH قبلی).
3. **پروفایل حافظه:** فعلاً `lean` بماند؛ پرامپت ۵ با بودجه‌ی تازه تصمیم میگیرد. فقط عدد را گزارش کن: جمع سقف‌ها در برابر ۸۰٪ رم تازه، و مصرف واقعی.
4. **دامنه:**
   - صبر کن تا `dig +short hq.coinepro.com A` همان IPv4 عمومی همین سرور را برگرداند (حداکثر ۳۰ دقیقه، هر ۲ دقیقه). اگر نشد، فقط گزارش کن.
   - با ابزار موجود (`infra/compose/.env` و `hq.sh`) `HQ_SITE_ADDRESS=hq.coinepro.com`، سپس `make up`. Caddy گواهی Let's Encrypt میگیرد.
   - اگر گرفتن گواهی شکست خورد (مثلاً 80 یا 443 در فایروال هتزنر بسته است)، **به فایروال دست نزن**؛ فقط گزارش کن.
   - بررسی‌ها (فقط کد وضعیت و هدر، بدون بدنه‌ی حساس):
     - `https://hq.coinepro.com/api/v1/health` ← `200`
     - `https://hq.coinepro.com/api/v1/meta` بدون نشست ← `401`
     - `https://hq.coinepro.com/internal/...` ← `404`
     - HSTS و هدرهای امنیتی روی پاسخ‌ها
     - `http://` به `https://` هدایت میشود
     - تنظیم WebAuthn: `rp_id = hq.coinepro.com`، `origin = https://hq.coinepro.com`؛ endpointهای ورود دیگر `503 origin_not_configured` نمیدهند.
     - Web Push (VAPID) حالا روشن است.
   - **`make owner-enroll` را اجرا نکن.** مالک خودش، وقتی وب یا اپ آماده شد، اجرا میکند.
5. `docs/ops/RUNBOOK.md` را با دامنه و مشخصات تازه‌ی سرور به‌روز کن (فقط نام متغیرها، هیچ مقدار محرمانه).

## گزارش بخش ب (حداکثر ۱۲ خط)
```
PROMPT_04_2 REPORT
- Kernel before/after ; RAM ; vCPU
- Services healthy n/n ; public ports unchanged?
- Memory: sum of limits vs 80% of new RAM ; used/free
- DNS ok? ; certificate ok? (issuer, expiry)
- health 200 / meta 401 / internal 404 / http->https / HSTS: ok/fail
- WebAuthn rp_id + origin ; login endpoints no longer 503 ; Web Push on?
- Backup before resize: size, restore-test ok
- Branch / last commit / pushed
- Decisions for owner: ...
- Problems: ...
```
**خط آخر:** «این گزارش را برای Claude سشن مشورت ببر.» بعد **متوقف شو.**
