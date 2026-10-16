# infra/ — زیرساخت سکوی پایه (مال Claude سرور)

| پوشه | چه چیزی |
|---|---|
| `compose/` | فایل Docker Compose، پروفایل‌های حافظه (`lean` و `full`) و `hq.sh` (تنها راه اجرای compose) |
| `caddy/` | Caddyfile و صفحه‌ی ساده‌ی عمومی |
| `observability/` | Prometheus، Grafana، Loki، Alloy، Tempo و otel-collector |
| `backup/` | backup شبانه، `restore-test` و ارسال به Object Storage (فعلاً خاموش) |
| `postgres/` | اسکریپت اولیه: سه دیتابیس و سه نقش با کمترین دسترسی |
| `valkey/`، `nats/`، `temporal/`، `openbao/` | پیکربندی هر سرویس |
| `systemd/` | تایمرهای backup و unseal خودکار OpenBao |

راهنمای عملیات: `docs/ops/RUNBOOK.md`.
