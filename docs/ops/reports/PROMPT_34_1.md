# گزارش پرامپت ۳۴.۱: ساعت انتشار، کامنتِ همان پست و اسلاید (deploy)

> Claude سرور هاب، ۲۰۲۶-۱۱-۱۰.
> - **شاخه:** `server/p34-1-deploy` = شاخه‌ی اصلی `150fd13e`. گزارش ۳۴ را در خود دارد؛ commit کد از خودم لازم نشد.
> - **alembic:** `0059` (migration ندارد).

## خلاصه
- **deploy:** api و worker (همان image) و gateway تازه‌اند. در 2026-11-10 14:50 UTC بالا آمدند.
- **تست‌ها:**
  - api: `test_w19_publish_time`، `test_w18_standing_publish`، `test_w17_session_publish`، `test_w8_capabilities`، `test_w11_connections`، `test_p17_runners` و سند OpenAPI: **۹۸ از ۹۸ سبز**.
  - gateway و hq-common سبز. OPA ‏۳۰۳ از ۳۰۳. lint و mypy سبز.
- **`verify-live`:** سبز است: rc=0، بی FAIL؛ فقط دو GAP همیشگی.
- **بکاپ پیش از deploy:** `20261110T144842Z`
- **دست‌نخورده:**
  - هیچ چیزی منتشر نشد.
  - هیچ اجازه‌ی دائمی‌ای روشن نشد و هیچ `publish_command`ی ثبت نشد.
  - هیچ داده‌ای پاک، بسته یا لغو نشد، و در هیچ جلسه‌ای چیزی نوشته نشد.
  - به هیچ سروری جز هاب دست زده نشد.
- **gitleaks:** پیش از push، `scripts/quality/gitleaks.sh` روی همین گزارش (پیش از push) اجرا شد و **سبز** بود.

## سنجش‌ها (فقط خواندنی، از هاب)
| سنجش | نتیجه |
|---|---|
| سرور IG-Hub | runner **0.3.4**، **online** |
| fx-main، Pro-Chart و ty-main | همه **0.3.4** و online (به‌روزرسانی را Claude هر سرور با متنی که مالک داد انجام داد) |
| کارگاه هلدینگ | هنوز **0.3.3** (ارتقا به 0.3.4 با مالک است) |

**اتصال `instagram` هر شرکت:**

| شرکت | `command` | `publish_command` |
|---|---|---|
| FX | نیست | نیست |
| IG | نیست | نیست |
| PC | نیست | نیست |
| TY | نیست | نیست |

| سنجش | نتیجه |
|---|---|
| کارهای `publish` در `infra.server_jobs`، ۲۴ ساعت گذشته | **۰**، در هیچ `state`ی |
| sweep، پنج دقیقه بعد از deploy (14:50 تا 14:55) | **بی خطا**: هیچ خطی از `follow_up`، و ۰ خط `error` یا Traceback در لاگ api و worker |

این گزارش را برای Claude سشن مشورت ببر.
