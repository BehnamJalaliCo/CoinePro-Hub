# گزارش پرامپت ۲۹: اکانت دوم Claude و پیشنهاد سری رسانه (deploy)

> Claude سرور هاب، ۲۰۲۶-۱۱-۰۹.
> - **شاخه:** `server/p29-deploy` = شاخه‌ی اصلی `19b04e01` + یک commit خودم (`6ff01321`). ‏`server/p28-4-deploy` را در خود دارد.
> - **alembic:** `0058` (migration ندارد).

## خلاصه
- **deploy:** llm-router، claude-runtime، gateway، api و worker تازه‌اند و همه healthy.
  - `agents/tools.md` تازه، با شکل دقیق فیلدهای `series.propose`، در image هست.
- **policy:** با `make llm-provision` اعمال شد. هیچ توکن یا اعتبارنامه‌ای عوض یا باطل نشد.
- **seed:** ردیف `claude-max-2` ساخته شد: `disabled`، `secret_ref = kv/claude-runtime/oauth-2`.
- **`verify-live`:** سبز است: rc=0، بی FAIL؛ فقط دو GAP همیشگی.
- **یک commit خودم، `6ff01321`: seed روتر قرمز بود.**
  - **مشکل:** `fallback_priority: 0` برای `claude-max-2` با قید جدول `llm.connections` (`CHECK (fallback_priority > 0)`، از migration ‏0002) رد میشد.
  - **اثر:** `llm_router.migrate` شکست میخورد و با آن ۴۳ تست دیتابیسی روتر و همه‌ی تست‌های api که روتر را بالا میآورند. روی هاب هم seed شکست میخورد.
  - **اصلاح:** مقدار ۱ شد.
  - **چرا رفتار عوض نمیشود:** اکانت دوم با نوعش (`claude_subscription`) انتخاب میشود و fallback عمومی فقط نوع `api` را میگیرد. پس فقط کافی است این عدد خالی نباشد، و ۱ همان کاری را میکند که از ۰ میخواستند.
- **وب:** در این پرامپت نبود. پنل زنده همان **0.19.2** است، در حالی که کد شاخه 0.19.4 است. اگر مالک بخواهد، با یک build و up وب به‌روز میشود.
- **دست‌نخورده:**
  - `kv/claude-runtime/oauth` (اکانت اول)
  - همه‌ی رمزها و توکن‌ها؛ هیچ‌کدام چاپ نشد
  - هیچ داده‌ای
  - هیچ سرویسی خاموش یا روشن نشد

## ۱. تست‌ها
| بخش | نتیجه |
|---|---|
| services (کل مجموعه: llm-router با تست‌های دیتابیسی، claude-runtime، gateway و بقیه) | **۱۲۷۰ سبز** (پیش از اصلاح: ۴۳ خطا، همه از seed) |
| company-runner (`tests/`، شامل `test_claude.py`) | سبز |
| api: `test_w13_second_account`، `test_w13_series_shapes`، `test_openapi` | **۶ از ۶ سبز** |
| lint، format و mypy (api و services) | سبز |

## ۲. deploy
| زمان (UTC) | کار | نتیجه |
|---|---|---|
| 07:22 | `make backup` | `20261109T072235Z` |
| 07:23 | checkout ‏`server/p29-deploy` و `make llm-provision` | policyها اعمال شد، از جمله `hq-api` با read روی `kv/claude-runtime/oauth-2` |
| 07:23 | build ‏`llm-router`، `claude-runtime`، `gateway` و `api` | ساخته شد |
| 07:23 | `up llm-migrate` (seed) | `claude-max-2` ساخته شد؛ `disabled` و `fallback_priority` = ۱ |
| 07:24 | `up -d --wait llm-router claude-runtime gateway api worker` | همه healthy |
| 07:24– | `make verify-live` | **rc=0**، بی FAIL؛ فقط دو GAP همیشگی |

## ۳. وضع الان
- **health ‏claude-runtime:** `oauth: configured` و `oauth_2: missing`. منتظر قدم مالک است.
- **`claude-max-2`:** خاموش میماند تا توکن برسد.
- **سرورهای شرکت‌ها:** هر چهار تا روی runner **0.3.0** و online هستند (fx-main، IG-Hub، Pro-Chart و ty-main). تا به 0.3.1 نرسند، کار `claude` روی آن‌ها با لاگین خود سرور اجرا میشود.

## ۴. قدم مالک (فقط مالک)
1. در ترمینال جدا، به‌عنوان کاربر `Hub`، این را بزنید:
   ```
   claude setup-token
   ```
   در مرورگر با **اکانت دوم** وارد شوید. از پروفایل دیگر مرورگر استفاده کنید، یا اول از اکانت اول خارج شوید.
2. بعد این را بزنید و توکن را بچسبانید (ورودی دیده نمیشود):
   ```
   make claude-token SLOT=2
   ```
3. به من بگویید. من این‌ها را انجام میدهم:
   - میسنجم که health فیلد `oauth_2: configured` دارد.
   - `claude-max-2` را روشن میکنم.
   - آزمون کوتاه را میزنم.

## ۵. به‌روزرسانی runner سرورهای شرکت‌ها به 0.3.1 (برای مالک یا Claude هر سرور)
با کاربر کاری همان سرور، وقتی `hq-runner status` هیچ کار در حال اجرایی نشان نمیدهد:
```
git -C ~/CoinePro-Hub pull
pipx install --force --python python3.12 ~/CoinePro-Hub/services/company-runner
sudo systemctl restart hq-runner@$USER
```
- **اگر نصب با venv یا uv است، یا سرویس کاربری است:** راه همان سرور را از بخش «به‌روزرسانی runner» در `docs/server-prompts/COMPANY_SERVER_ACCESS_SETUP.md` بردارید.
- **بعد بسنجید:** `hq-runner --version` باید `0.3.1` بدهد.
- **سرورها:** fx-main، IG-Hub، Pro-Chart و ty-main.

این گزارش را برای Claude سشن مشورت ببر.
