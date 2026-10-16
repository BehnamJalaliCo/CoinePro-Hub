# infra/caddy — لبه‌ی عمومی

- Caddy تنها سرویسی است که روی `0.0.0.0` (پورت‌های 80 و 443) منتشر میشود.
- **فعلاً دامنه نداریم:** روی `:80` صفحه‌ی «CoinePro HQ» و مسیر `/health` را برمیگرداند.
- **فعال کردن HTTPS خودکار:** فقط یک خط در `infra/compose/.env` بنویس: `HQ_SITE_ADDRESS=hq.example.com`، بعد `make up`.
- پورت `2020` داخلی است (healthcheck و متریک‌های Prometheus) و منتشر نمیشود.
