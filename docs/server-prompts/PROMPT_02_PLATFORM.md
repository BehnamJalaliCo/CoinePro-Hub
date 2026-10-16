# پرامپت ۲: سکوی پایه‌ی CoinePro HQ

> **برای مالک:** کل متن زیر خط را کپی کن و به Claude Code روی سرور هاب بده. گزارش کوتاه آخرش را برای Claude سشن مشورت بیاور.

---

تو **Claude Code روی سرور هاب «CoinePro HQ»** هستی. این مرحله **سکوی پایه** است: همه‌ی سرویس‌های زیرساخت، ساختار ریپو، backup و CI. **هیچ منطق برنامه، ایجنت، n8n، وب یا اپی در این مرحله ساخته نمیشود.**

## ۰. قبل از شروع (اجباری)
1. در `/home/Hub/CoinePro-Hub` آخرین نسخه‌ی شاخه‌ی `claude/coinepro-hub-setup-hsvnw7` را pull کن. از روی آن، شاخه‌ی **`server/p02-platform`** را بساز.
2. **این فایل‌ها را کامل بخوان:**
   - `CLAUDE.md` (قوانین؛ لازم‌الاجرا)
   - `docs/TECH_STACK.md`
   - `docs/OPERATING_MODEL.md` §۰
   - `docs/server-prompts/README.md`
3. **تسک‌بندی اجباری:** قبل از هر کاری، **همه‌ی کارهای این پرامپت را در لیست تسک خودت بشکن.** هر تسک یک تست قبولی دارد. بعد:
   - **بدون توقف** یکی‌یکی انجامشان بده.
   - کارهای مستقل را در صورت امن بودن **موازی** کن.
   - وضعیت لیست را به‌روز نگه دار.
4. **فقط در این موارد متوقف شو و از مالک بپرس:**
   - تصمیمی که با مالک است
   - خطر غیرمنتظره
   - اطلاعاتی که فقط مالک دارد

## ۱. پروفایل حافظه (خودکار)
- RAM سرور را بخوان.
- **اگر کمتر از ۱۲GB بود: پروفایل `lean`.** Tempo، otel-collector و cAdvisor بالا نمیایند و سقف‌های حافظه کمتر است.
- **اگر بیشتر بود: پروفایل `full`.**
- هر دو پروفایل را با Docker Compose profiles بساز تا بعد از ارتقای سرور فقط پروفایل عوض شود.
- **جمع سقف حافظه‌ی همه‌ی کانتینرها حداکثر ۶۰٪ RAM باشد.** بقیه برای API، runtime و ایجنت‌های مراحل بعد میماند.

## ۲. ساختار ریپو (monorepo)
فقط پوشه‌ها و فایل README کوتاه برای هر پوشه بساز. **به پوشه‌های مال Claude مشورت دست نزن.**

```
infra/compose/         ← Docker Compose (مال تو)
infra/caddy/           ← Caddyfile (مال تو)
infra/observability/   ← Prometheus، Grafana، Loki و Tempo (مال تو)
infra/backup/          ← اسکریپت‌های backup و restore (مال تو)
apps/api/              ← فقط README؛ منطق در پرامپت‌های بعد (مال تو)
services/claude-runtime/  services/gateway/  ← فقط README (مال تو)
automations/           ← فقط README؛ n8n در ماه ۲ (مال تو)
scripts/quality/       ← گیت‌های کیفیت (مال تو)
docs/ops/              ← RUNBOOK (مال تو)
apps/web/  apps/android/  design/  contracts/  ← ❌ مال Claude مشورت؛ نساز و دست نزن
```

## ۳. سرویس‌ها (Docker Compose، پروژه‌ی `coinepro-hq`)
**قانون‌های مشترک همه‌ی سرویس‌ها:**
- ایمیج رسمی، با **نسخه‌ی ثابت** (نه `latest`)
- `restart: unless-stopped`
- healthcheck
- سقف حافظه
- volume نام‌دار
- شبکه‌ی داخلی `hq-internal`
- **هر پورت فقط روی `127.0.0.1` منتشر میشود.** تنها استثنا: Caddy روی 80 و 443.

| سرویس | توضیح |
|---|---|
| **PostgreSQL 17 + pgvector** (ایمیج رسمی pgvector) | دیتابیس‌های `hq`، `temporal` و `temporal_visibility`. برای هر کدام یک نقش جدا با کمترین دسترسی. تنظیمات حافظه متناسب با پروفایل. `pg_stat_statements` فعال. |
| **Valkey 8** | پسورد، AOF روشن، `maxmemory` و سیاست eviction مناسب. |
| **NATS 2** با **JetStream** | ذخیره روی volume؛ مانیتورینگ روی localhost. |
| **Temporal** | سرور رسمی، persistence روی همین Postgres، **روش production رسمی** برای ساختن schema (نه حالت dev). **Temporal UI** روی localhost. |
| **OpenBao** | حالت server با storage `raft`. **مقداردهی اولیه با ۱ key share و threshold ۱.** خروجی init (کلید unseal و root token) را **فقط در فایل `/home/Hub/.secrets/openbao-init.json` با دسترسی `600` ذخیره کن و هرگز چاپ نکن.** یک اسکریپت unseal خودکار بعد از ریبوت بساز که کلید را از همان فایل بخواند. ریسکش را در RUNBOOK بنویس. |
| **Caddy 2** | تنها سرویس عمومی (80 و 443). **فعلاً دامنه نداریم:** روی `:80` یک صفحه‌ی ساده‌ی «CoinePro HQ» و مسیر `/health` برمیگرداند. Caddyfile طوری باشد که بعد از دادن دامنه، فعال شدن TLS خودکار فقط یک خط تغییر باشد. |
| **Prometheus، Grafana OSS، Loki، node-exporter** | همه‌ی پروفایل‌ها. Grafana با datasourceهای از پیش تنظیم‌شده و داشبورد سرور و کانتینرها. |
| **Tempo، OpenTelemetry Collector، cAdvisor** | فقط پروفایل `full`. |

**رمزها:**
- همه در `infra/compose/.env` با پسوردهای تصادفی قوی، دسترسی `600`، و **gitignore**.
- یک `infra/compose/.env.example` **فقط با نام متغیرها** commit شود.
- **هیچ رمزی چاپ نشود.**

**Makefile** در ریشه‌ی ریپو، با این دستورها:
- `make up`، `make down`، `make ps`، `make logs s=<service>`
- `make backup`، `make restore-test`
- `make check`

## ۴. backup
- **هر شب** (systemd timer یا cron کاربر `Hub`): `pg_dump -Fc` جدا برای هر دیتابیس، به `/home/Hub/backups/` با **نگهداری ۷ روز**.
- **`make restore-test`:** آخرین backup را در یک کانتینر Postgres موقت بازیابی و صحتش را چک میکند، بعد کانتینر را پاک میکند. **این تست باید یک بار با موفقیت اجرا شود.**
- **ارسال به Hetzner Object Storage** آماده باشد ولی خاموش. نام متغیرها در `.env.example` بیاید. وقتی مالک اطلاعات bucket را داد، فعال میشود.

## ۵. گیت‌های کیفیت و CI
- `scripts/quality/`:
  - **gitleaks** (اسکن secret)
  - **`docker compose config -q`**
  - **بررسی اینکه هیچ پورتی جز 80 و 443 روی `0.0.0.0` منتشر نشده**
  - **shellcheck** برای اسکریپت‌ها
  - **yamllint**
- `make check` همه را اجرا کند.
- **GitHub Actions** (`.github/workflows/quality.yml`): همان چک‌ها روی هر push.

## ۶. مستندات عملیاتی
`docs/ops/RUNBOOK.md` شامل:
- بالا آوردن و پایین آوردن سرویس‌ها
- backup و restore
- به‌روزرسانی نسخه‌ها
- unseal کردن OpenBao
- عوض کردن پروفایل `lean` و `full`
- **فهرست پورت‌ها و آدرس‌های localhost**

## ۷. تست قبولی نهایی (همه باید پاس شوند)
- `docker compose ps`: همه‌ی سرویس‌های پروفایل فعال **healthy** هستند.
- **`ss -tlnp`:** روی `0.0.0.0` فقط 80، 443 و 1367 (SSH خود سرور) باز است.
- **`curl http://localhost/health`** از طریق Caddy جواب میدهد.
- اتصال به Postgres، Valkey، NATS و Temporal از داخل شبکه‌ی Docker موفق است. دیتابیس `hq` افزونه‌ی `vector` را دارد.
- **`make restore-test`** موفق است.
- **`make check`** سبز است.
- **`free -h`** و یک **`docker stats --no-stream`** (برای گزارش).

## ۸. گیت
- **commitهای کوچک و منطقی** روی `server/p02-platform`، و push.
- **اگر push به خاطر اطلاعات ورود نشد، خودت تنظیمش نکن.** فقط گزارش بده.

## ۹. گزارش پایانی
گزارش کوتاه، **حداکثر ۲۰ خط:**

```
PROMPT_02 REPORT
- Profile: lean/full (RAM ...)
- Services healthy: ...
- Public ports (0.0.0.0): ...
- RAM used / free; top 3 containers by memory
- Backup + restore-test: ok/fail
- make check: ok/fail
- Branch / last commit / pushed: yes/no
- Problems: ...
- Owner needs to provide: (e.g. domain, Object Storage bucket)
```

**خط آخر:** «این گزارش را برای Claude سشن مشورت ببر.» بعد **متوقف شو.**
