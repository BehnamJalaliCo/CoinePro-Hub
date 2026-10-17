# apps/web — پنل وب ستاد کوینه‌پرو (مال Claude سشن مشورت)

Next.js 16 (App Router) + React 19 + Tailwind 4 + TypeScript strict، روی سیستم طراحی «دیوان».

## دستورها
| دستور | کار |
|---|---|
| `npm ci` | نصب دقیق از lockfile |
| `npm run gen` | ساخت توکن‌ها، آیکون‌ها، نشان‌ها و فونت‌ها از `design/` و تایپ‌های API از `apps/api/openapi/` |
| `npm run gen:check` | اثبات اینکه خروجی‌های ساخته‌شده با منبعشان یکی‌اند (در CI) |
| `npm run dev:mock` | اجرای محلی با داده‌ی نمایشی، بدون سرور (فقط توسعه؛ در build نهایی حذف میشود) |
| `npm run typecheck` · `npm run lint` · `npm run build` | کیفیت و build |

## قواعد
- **یک منبع:** رنگ، فاصله، حرکت و فونت فقط از `src/styles/tokens.css` (ساخته‌شده از `design/tokens/divan.tokens.json`). هیچ رنگ دستی.
- **ارقام:** متن با `IRANYekanXFaNum` (ارقام فارسی برای شمارش‌ها)؛ پول، توکن، کد و نام مدل با کلاس `.fig` (ارقام لاتین، هم‌عرض).
- **شرکت‌ها داده‌اند:** هیچ کد شرکتی در منطق نیست؛ نشان هر شرکت از `design/brand/companies/<code>/` میاید و نبودش با کد جایگزین میشود.
- **امنیت:** CSP با nonce در `src/proxy.ts`؛ کوکی نشست `Path=/api` (HttpOnly)؛ همه‌ی درخواست‌های تغییرده `X-HQ-Client: web` و `Idempotency-Key` دارند؛ اقدام‌های 🔏 با step-up passkey.
- **قرارداد:** `contracts/HQ_CORE_API_v1.md`؛ تایپ‌ها از OpenAPI ساخته میشوند.

## deploy
سرویس `web` در compose از `apps/web/Dockerfile` ساخته میشود (پرامپت ۵ §۱۰). Caddy: `/api/*` به `api`، بقیه به `web`.

### متغیرهای سرویس web
| نام | کار |
|---|---|
| `HQ_ANDROID_PACKAGES` | بسته‌های اپ اندروید در `/.well-known/assetlinks.json`؛ پیش‌فرض `com.coinepro.hq` |
| `HQ_ANDROID_CERT_SHA256` | اثر انگشت SHA-256 کلید امضای اپ (`AA:BB:…`، چندتا با کاما). تا خالی است فایل `[]` است و passkey روی اندروید کار نمیکند. مقدار را اپ در «تنظیمات ← این اپ» نشان میدهد. |
