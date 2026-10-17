# infra/ — زیرساخت سکوی پایه (مال Claude سرور)

| پوشه | چه چیزی |
|---|---|
| `compose/` | فایل Docker Compose، پروفایل‌های حافظه (`lean` و `full`) و `hq.sh` (تنها راه اجرای compose) |
| `caddy/` | Caddyfile، `api-on.caddy` و `api-off.caddy` (لبه‌ی `/api`؛ فقط با دامنه باز است) و صفحه‌ی ساده‌ی عمومی |
| `observability/` | Prometheus، Grafana، Loki، Alloy، Tempo و otel-collector |
| `backup/` | backup شبانه، `restore-test` و ارسال به Object Storage (فعلاً خاموش) |
| `postgres/` | اسکریپت اولیه (سه دیتابیس و سه نقش) و `provision.sh` (نقش‌های لایه‌ی مدل و هسته: `hq_api` و `hq_worker`، و `pg_trgm`؛ idempotent) |
| `valkey/`، `nats/`، `temporal/` | پیکربندی هر سرویس |
| `openbao/` | پیکربندی، init/unseal، `provision.sh`، `policies/` (از جمله `hq-api` و `hq-worker`) و `claude-token.sh` |
| `opa/` | سیاست‌های OPA (`policy/*.rego` و تست‌ها) و `IMAGE` (تنها منبع نسخه‌ی ایمیج OPA) |
| `systemd/` | تایمرهای backup و unseal خودکار OpenBao |

راهنمای عملیات: `docs/ops/RUNBOOK.md`.
