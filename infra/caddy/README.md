# infra/caddy — لبه‌ی عمومی

- Caddy تنها سرویسی است که روی `0.0.0.0` (پورت‌های 80 و 443) منتشر میشود.
- **دامنه:** `hq.coinepro.com` با HTTPS خودکار؛ تنظیمش یک خط در `infra/compose/.env` است: `HQ_SITE_ADDRESS=<دامنه>`، بعد `make up`. بی‌دامنه، روی `:80` فقط صفحه‌ی ثابت و `/health` میماند.
- پورت `2020` داخلی است (healthcheck و متریک‌های Prometheus) و منتشر نمیشود.
- **شبکه‌ها (پرامپت ۵.۱ §۲.۹):** Caddy روی `hq-internal` است، برای api و راه بیرون برای ACME. روی `hq-edge` هم هست، برای پنل وب. `hq-edge` فقط Caddy و `web` را دارد و internal است.
- **قطعه‌ها** (هر کدام را `infra/compose/hq.sh` با یک متغیر روشن یا خاموش میکند):
  - `api-on.caddy` / `api-off.caddy`: متغیر `HQ_API_EDGE`. فقط با دامنه روشن است.
  - `web-on.caddy` / `web-off.caddy`: متغیر `HQ_WEB`. وقتی `apps/web/Dockerfile` هست روشن است.
    - بدنه‌ی درخواست به وب حداکثر 1MB است، چون پنل خودش آپلود نمیگیرد.
    - هدر `X-Middleware-Subrequest` هرگز به Next.js نمیرسد (CVE-2025-29927).
  - `canary-on.caddy` / `canary-off.caddy`: متغیر `HQ_CANARY`.
    - وقتی ردیف قناری در `apps/api/seed/sites.yaml` روشن است، `/__canary` عمداً 503 میدهد.
    - خاموش که باشد، 404 میدهد، مثل هر مسیر ناشناخته.
- `scripts/quality/infra.sh` این رفتارها را روی کانتینر موقت آزمایش میکند.
