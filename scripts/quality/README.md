# scripts/quality — گیت‌های کیفیت

`make check` همه را اجرا میکند. GitHub Actions (`.github/workflows/quality.yml`) هم همین را روی هر push اجرا میکند.

| اسکریپت | چه چیزی را چک میکند |
|---|---|
| `gitleaks.sh` | secret در تاریخچه‌ی git و تغییرات commit‌نشده (خروجی redact میشود) |
| `compose-config.sh` | `docker compose config -q` برای هر دو پروفایل |
| `ports.sh` | هیچ پورتی جز 80 و 443 (Caddy) روی `0.0.0.0` منتشر نشده باشد |
| `compose-rules.sh` | ایمیج با نسخه‌ی ثابت، سقف حافظه، restart و healthcheck برای هر سرویس؛ کاربر غیر root، rootfs فقط‌خواندنی و `cap_drop: ALL` برای سرویس‌های خودمان؛ جدا بودن شبکه‌ها: عضوهای مجاز `hq-core`، `hq-agent` و `hq-edge`، سرویس‌هایی که فقط روی یک شبکه‌اند (`gateway` و `opa` روی `hq-agent`، `web` روی `hq-edge`، `claude-runtime` روی `hq-llm`)، و internal بودن `hq-agent` و `hq-edge` |
| `memory-budget.sh` | جمع سقف حافظه‌ها حداکثر ۸۰٪ RAM مرجع هر پروفایل، با دست‌کم ۵٪ بودجه‌ی آزاد؛ هر پروفایل همراه هر پروفایل opt-in (مثل `cadvisor`) هم جا شود؛ RAM مرجع `full` همان آستانه‌ی انتخاب `full` در `hq.sh` است |
| `shellcheck.sh` | همه‌ی اسکریپت‌های shell |
| `yamllint.sh` | همه‌ی فایل‌های YAML |
| `hadolint.sh` | همه‌ی Dockerfileها |
| `opa.sh` | تست policyهای OPA با پوشش کامل |
| `infra.sh` | رفتار اسکریپت‌های زیرساخت روی پوشه و کانتینر موقت: `provision.sh` بی sudo پیش از هر نوشتن در KV میایستد، backup ناموفق `ok:false` ثبت میکند، پوشه‌ی backup با `0700` ساخته میشود، `audit-reanchor.sh` فقط در ترمینال، `/__canary` و هدرها و سقف بدنه در Caddy، و sandbox واحد systemd متریک کانتینرها |
| `python.sh` | lint، type، تست و pip-audit سرویس‌های Python و `apps/api` |
| `live.sh` | روی stack در حال اجرا (`make verify-live`): جدا بودن شبکه‌ها از دید یک کانتینر موقت و از داخل خود `web` و `gateway`، و نبودن پارامتر کوئری در لاگ Postgres؛ جایی که stack نیست رد میشود |

همه‌ی ابزارها با ایمیج Docker و نسخه‌ی ثابت اجرا میشوند (`lib.sh`)، تا نتیجه روی سرور و CI یکی باشد.
