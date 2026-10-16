# scripts/quality — گیت‌های کیفیت

`make check` همه را اجرا میکند. GitHub Actions (`.github/workflows/quality.yml`) هم همین را روی هر push اجرا میکند.

| اسکریپت | چه چیزی را چک میکند |
|---|---|
| `gitleaks.sh` | secret در تاریخچه‌ی git و تغییرات commit‌نشده (خروجی redact میشود) |
| `compose-config.sh` | `docker compose config -q` برای هر دو پروفایل |
| `ports.sh` | هیچ پورتی جز 80 و 443 (Caddy) روی `0.0.0.0` منتشر نشده باشد |
| `compose-rules.sh` | ایمیج با نسخه‌ی ثابت، سقف حافظه، restart و healthcheck برای هر سرویس |
| `memory-budget.sh` | جمع سقف حافظه‌ها حداکثر ۶۰٪ RAM باشد |
| `shellcheck.sh` | همه‌ی اسکریپت‌های shell |
| `yamllint.sh` | همه‌ی فایل‌های YAML |

همه‌ی ابزارها با ایمیج Docker و نسخه‌ی ثابت اجرا میشوند (`lib.sh`)، تا نتیجه روی سرور و CI یکی باشد.
