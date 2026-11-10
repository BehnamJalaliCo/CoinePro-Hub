# گزارش پرامپت ۳۳: «تأیید و انتشار» در جلسه، سمت هاب (deploy)

> Claude سرور هاب، ۲۰۲۶-۱۱-۱۰.
> - **شاخه:** `server/p33-deploy` = `567edb21` (کد ۳۳ و اپ 0.19.8) + merge ‏`server/p32-deploy` (گزارش ۳۲). commit کد از خودم لازم نشد.
> - **alembic:** `0058` (migration ندارد).
> - **ترتیب:** ۳۱ و ۳۲ پیش‌تر deploy شده بودند. ۳۲ همین امروز، پیش از ۳۳، جدا deploy و گزارش شد (`PROMPT_32.md`).

## خلاصه
- **deploy:** api و worker (همان image) و gateway تازه‌اند. مسیرهای `POST /api/v1/orders/{ref}/publish` و `GET/POST /api/v1/deliverables/{ref}/publish` در سند OpenAPI هستند.
- **تست‌ها:**
  - api: `test_w17_session_publish`، `test_p13a_media`، `test_w11_connections`، و ۸ فایل مرتبط (`test_w16_direct_sessions`، `test_p17_runners`، `test_decisions_messages`، `test_w11_decisions`، `test_w8_capabilities`، `test_w14_workshop`، `test_rls_all_tables`، `test_schema_rules`)، به‌علاوه‌ی سند OpenAPI: **۱۴۴ از ۱۴۴ سبز**.
  - gateway و hq-common سبز. OPA ‏۳۰۳ از ۳۰۳. lint و mypy سبز.
  - کل مجموعه‌ی api هم ساعتی پیش روی کد ۳۲ اجرا شد: ۱۵۷۰ سبز.
- **`verify-live`:** سبز است: rc=0، بی FAIL؛ فقط دو GAP همیشگی.
- **بکاپ پیش از deploy:** `20261110T060639Z`
- **دست‌نخورده:** هیچ چیزی منتشر نشد (نه آزمایشی، نه واقعی). هیچ داده‌ای پاک، بسته یا لغو نشد. در هیچ جلسه‌ای چیزی نوشته نشد. به هیچ سروری جز هاب دست زده نشد.

## سنجش‌ها (فقط خواندنی، از دیتابیس هاب)
| سنجش | نتیجه |
|---|---|
| سرور IG-Hub در هاب | شرکت **IG**، نام `IG-Hub`، runner **0.3.2**، **online** |

**اتصال `instagram` هر شرکت** (`growth.connections`):

| شرکت | کلیدهای `config` | `accounts` | `command` | `publish_command` |
|---|---|---|---|---|
| FX | `accounts`، `server`، `via` | ۱ | نیست | نیست |
| IG | `accounts`، `server`، `via` | ۲ | نیست | نیست |
| PC | `accounts`، `server`، `via` | ۱ | نیست | نیست |
| TY | `accounts`، `server`، `via` | ۰ | نیست | نیست |

| سنجش | نتیجه |
|---|---|
| کار فنی باز با `run_meta.ig_setup` یا `ig_publish` | **نیست** (۰). هاب آن را با نخستین «تأیید و انتشار» خودش میسازد. |
| صندلی مدیر فنی IG-Hub و AIOPS هلدینگ | **هر دو پر و فعال‌اند:** `IG-TECH-MGR` و `HQ-AIOPS-MGR`. پس کسی هست که مسیر انتشار را وصل کند. |

**یعنی:** هیچ شرکتی هنوز `publish_command` ندارد. نخستین «تأیید و انتشار» مالک به کار فنی‌ای میرسد که هاب برای مدیر فنی IG-Hub میسازد. جلسه همین را میگوید و انتشار بعد از وصل شدن مسیر انجام میشود.

این گزارش را برای Claude سشن مشورت ببر.
