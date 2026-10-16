# infra/observability — مشاهده‌پذیری

| ابزار | پروفایل | نقش |
|---|---|---|
| Prometheus | همه | متریک‌ها (`scrape/` برای همه، `scrape-profile/<profile>/` مخصوص هر پروفایل) |
| Grafana OSS | همه | datasourceهای آماده و داشبوردهای «HQ / Server» و «HQ / Containers» |
| Loki | همه | لاگ‌ها |
| Alloy | همه | ارسال لاگ کانتینرها به Loki؛ فایل‌های لاگ را فقط‌خواندنی میخواند و به Docker socket دسترسی ندارد |
| node-exporter | همه | متریک‌های خود سرور |
| Tempo، otel-collector، cAdvisor | فقط `full` | trace، دریافت OTLP و متریک هر کانتینر |

داشبوردها از روی ریپو بار میشوند و در Grafana فقط‌خواندنی‌اند. در پروفایل `lean`، پنل‌های CPU و RAM هر کانتینر خالی میمانند، چون cAdvisor فقط در `full` اجرا میشود.
