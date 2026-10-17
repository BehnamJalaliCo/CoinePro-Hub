# infra/observability — مشاهده‌پذیری

| ابزار | پروفایل | نقش |
|---|---|---|
| Prometheus | همه | متریک‌ها (`scrape/` برای همه، `scrape-profile/<profile>/` مخصوص هر پروفایل) |
| Grafana OSS | همه | datasourceهای آماده و داشبوردهای «HQ / Server» و «HQ / Containers» |
| Loki | همه | لاگ‌ها |
| Alloy | همه | ارسال لاگ کانتینرها به Loki؛ فایل‌های لاگ را فقط‌خواندنی میخواند و به Docker socket دسترسی ندارد |
| node-exporter | همه | متریک‌های خود سرور |
| Tempo، otel-collector | فقط `full` | trace و دریافت OTLP |
| `container-metrics.sh` (روی host، تایمر systemd) | همه | متریک هر کانتینر بدون Docker socket در هیچ کانتینری، از راه textfile ‏node-exporter (پرامپت ۵ §۱۱) |
| cAdvisor | فقط پروفایل opt-in ‏`cadvisor` | به Docker socket نیاز دارد، پس در هیچ پروفایل پیش‌فرضی نیست. گیت حافظه جا شدن آن را هم میسنجد |

داشبوردها از روی ریپو بار میشوند و در Grafana فقط‌خواندنی‌اند. داشبورد «HQ / Containers» در هر دو پروفایل از متریک‌های `hq_container_*` میخواند.
