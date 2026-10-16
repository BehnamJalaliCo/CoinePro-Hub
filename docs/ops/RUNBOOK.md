# CoinePro HQ — RUNBOOK (سکوی پایه)

> سند عملیاتی Claude سرور. همه‌ی دستورها از ریشه‌ی ریپو (`/home/Hub/CoinePro-Hub`) و با کاربر `Hub` اجرا میشوند.
> **قانون:** هیچ رمزی چاپ نمیشود. هیچ حذف یا ریبوتی بدون اجازه‌ی مالک انجام نمیشود.

## ۱. نمای کلی

- **پروژه‌ی Compose:** `coinepro-hq`. فایل اصلی: `infra/compose/compose.yaml`.
- **همیشه از `make` استفاده کن** (یا `infra/compose/hq.sh`). `hq.sh` پروفایل حافظه را انتخاب میکند و `profiles/<profile>.env` و `.env` را بار میکند. `docker compose` خالی، پروفایل و سقف‌های حافظه را نمیشناسد.
- **رمزها:** `infra/compose/.env` (دسترسی `600`، در gitignore). کلیدهای OpenBao: `/home/Hub/.secrets/openbao-init.json` (دسترسی `600`).
- **شبکه:** همه‌ی سرویس‌ها روی شبکه‌ی `hq-internal` (`172.30.0.0/24`) هستند. هر پورت فقط روی `127.0.0.1` منتشر میشود. تنها استثنا Caddy روی 80 و 443 است.

| دستور | کار |
|---|---|
| `make help` | فهرست دستورها |
| `make env` | ساختن `.env` با رمزهای تصادفی (هیچ‌وقت فایل موجود را بازنویسی نمیکند) |
| `make profile` | پروفایل فعال (`lean` یا `full`) |
| `make up` | بالا آوردن همه‌ی سرویس‌های پروفایل فعال و صبر تا healthy شدن |
| `make down` | توقف و حذف کانتینرها؛ **volumeها (داده‌ها) میمانند** |
| `make ps` | وضعیت سرویس‌ها |
| `make logs s=<service>` | دنبال کردن لاگ یک سرویس |
| `make backup` | backup فوری |
| `make restore-test` | تست بازیابی آخرین backup |
| `make check` | گیت‌های کیفیت (همان CI) |
| `make openbao-init` | مقداردهی اولیه‌ی OpenBao (فقط یک بار) |
| `make unseal` | unseal کردن OpenBao |
| `make install-systemd` | نصب یا تازه‌سازی تایمرهای backup و unseal (sudo لازم است) |
| `make llm-provision` | OpenBao: ‏KV، policyها، AppRoleها و توکن‌های سرویس (idempotent؛ جزو `make up` هم هست) |
| `make claude-token` | **فقط مالک:** ثبت توکن `claude setup-token` در OpenBao (ورودی پنهان) |
| `make llm-smoke` | یک فراخوانی واقعی خیلی کوچک (Haiku، «OK»)، همراه ردیف ledger و رویداد NATS |
| `make test-services` | سرویس‌های Python: hadolint، ruff، mypy، pytest و pip-audit |
| `make lock` | ساختن دوباره‌ی lock فایل‌های Python (با hash) |

## ۲. بالا آوردن و پایین آوردن

**اولین بار روی یک سرور تازه:**
```bash
make env               # .env با رمزهای تصادفی
make up                # همه‌چیز + init و unseal کردن OpenBao
make install-systemd   # تایمرهای backup شبانه و unseal خودکار
make check
```

**`make up` به این ترتیب کار میکند:**
1. `gen-env.sh`: کلیدهایی که پرامپت‌های جدید اضافه کرده‌اند به `.env` اضافه میشوند. رمزها تصادفی‌اند، خط‌های موجود دست نمیخورند و هیچ مقداری چاپ نمیشود.
2. فقط `openbao` بالا میاید. بعد، اگر لازم باشد: `init.sh`، ‏`unseal.sh`، و در هر حال `provision.sh` (idempotent). این مرحله فایل‌های AppRole و توکن metrics را **قبل** از بالا آمدن سرویس‌ها میسازد. sudo لازم است، چون مالک این فایل‌ها uid کانتینرهاست.
3. `up -d --build --wait`: ایمیج‌های خودمان (`coinepro-hq/llm-router` و `coinepro-hq/claude-runtime`) ساخته میشوند و همه‌چیز بالا میاید. ترتیب وابستگی‌ها:
   - `postgres` ← `temporal-schema` ← `temporal` ← `temporal-namespace` ← `temporal-ui`
   - `postgres` ← `db-provision` ← `llm-migrate` ← `llm-router`
   - `hq-tools` قبل از Loki و Alloy
   صبر تا همه healthy شوند، حداکثر ۵ دقیقه.

**پایین آوردن:** `make down`. کانتینرهای همه‌ی پروفایل‌ها حذف میشوند و داده‌ها در volumeها میمانند.
**هرگز `down -v` نزن.** این دستور همه‌ی داده‌ها را پاک میکند و فقط با اجازه‌ی صریح مالک اجرا میشود.

**یک سرویس:** `infra/compose/hq.sh restart <service>` یا `infra/compose/hq.sh up -d <service>`.

**کارهای یک‌باره** (`hq-tools`، `temporal-schema`، `temporal-namespace`، `db-provision`، `llm-migrate`) اجرا میشوند و با کد 0 خارج میشوند. این وضعیت طبیعی است. برای دیدنشان: `infra/compose/hq.sh ps -a`.

**بعد از ریبوت:** Docker کانتینرها را خودش بالا میاورد (`restart: unless-stopped`). تایمر `coinepro-hq-openbao-unseal.timer` یک دقیقه بعد از boot، و بعد هر ۵ دقیقه، OpenBao را unseal میکند. چک کن: `make ps`.

## ۳. backup و restore

- **شبانه:** `coinepro-hq-backup.timer` هر شب ساعت **۰۲:۳۰ UTC** (با تأخیر تصادفی تا ۱۵ دقیقه) اجرا میشود. اگر سرور در آن ساعت خاموش بوده باشد، بعد از روشن شدن اجرا میشود.
- **چه چیزی:** برای هر دیتابیس (به جز `postgres`) یک `pg_dump -Fc` جدا، به‌علاوه‌ی `globals.sql` (نقش‌ها؛ شامل hash رمزها)، `manifest.json` و `SHA256SUMS`.
- **کجا:** `/home/Hub/backups/<YYYYMMDDTHHMMSSZ>/` (دسترسی `700`/`600`). **نگهداری ۷ روز.** فقط پوشه‌هایی با همین الگوی نام پاک میشوند.
- **وضعیت:** `systemctl list-timers 'coinepro-hq-*'` و `journalctl -u coinepro-hq-backup.service`.
- **تست بازیابی:** `make restore-test`. آخرین backup را در یک Postgres موقت (همان ایمیج، بدون شبکه، 512MB) بازیابی میکند و این‌ها را چک میکند: checksumها، `pg_restore --exit-on-error`، برابر بودن تعداد جدول‌ها با فهرست آرشیو، افزونه‌ی `vector` در `hq` و نسخه‌ی schema در Temporal. بعد کانتینر را پاک میکند. **حداقل ماهی یک بار اجرا شود.**
- **OpenBao در این backup نیست.** OpenBao داده‌ی raft خودش را دارد. snapshot آن (`bao operator raft snapshot save`) توکن لازم دارد و در پرامپت بعدی، همراه با policyها، اضافه میشود.

**بازیابی واقعی یک دیتابیس روی production** (فقط با اجازه‌ی مالک؛ مثال برای `hq`):
```bash
make backup                                    # اول از وضعیت فعلی backup بگیر
B=/home/Hub/backups/<stamp>
infra/compose/hq.sh stop <سرویس‌هایی که از این دیتابیس استفاده میکنند>
infra/compose/hq.sh exec -T postgres pg_restore -U postgres -d hq --clean --if-exists --exit-on-error < "$B/hq.dump"
infra/compose/hq.sh up -d
```
برای Temporal، قبل از restore سرویس‌های `temporal` و `temporal-ui` را متوقف کن.

**ارسال به Hetzner Object Storage (فعلاً خاموش):**
1. مالک bucket را میسازد و این‌ها را میدهد: endpoint (مثلاً `https://fsn1.your-objectstorage.com`)، region، نام bucket، access key و secret key.
2. Claude سرور متغیرهای `HQ_BACKUP_S3_*` را در `.env` پر میکند (`HQ_BACKUP_S3_ENABLED=true`). هیچ مقداری چاپ نمیشود.
3. بعد از هر backup، `offsite.sh` آن را با `rclone` (ایمیج رسمی، نسخه‌ی ثابت) به `<bucket>/<prefix>/<stamp>/` میفرستد.
4. نگهداری در bucket با lifecycle rule خود bucket تنظیم میشود.
5. ⚠️ backupها رمزنگاری سمت کلاینت ندارند. قبل از فعال کردن، درباره‌ی آن تصمیم گرفته شود.

## ۴. به‌روزرسانی نسخه‌ها

قانون: **ایمیج رسمی با نسخه‌ی ثابت**؛ هرگز `latest`. (`make check` آن را چک میکند.)

1. release notes نسخه‌ی جدید را بخوان، به‌خصوص breaking changes.
2. فقط tag همان سرویس را در `infra/compose/compose.yaml` عوض کن.
3. `make check`
4. `make backup`
5. `infra/compose/hq.sh pull <service>` و بعد `make up`.
6. با `make ps` و داشبوردها چک کن. یک commit جدا برای هر به‌روزرسانی.

موارد خاص:
- **Temporal:** `temporal-schema` در هر `make up` اجرا میشود و schema را با `update-schema` به نسخه‌ی جدید میبرد. سرور، admin-tools و UI را با هم به‌روز کن و نسخه‌ها را **یکی‌یکی** بالا ببر (minor به minor).
- **PostgreSQL:** به‌روزرسانی patch (مثلاً 17.x) فقط عوض کردن ایمیج است. **ارتقای major** (مثلاً 17 به 18) با dump و restore یا `pg_upgrade` انجام میشود و پرامپت جدا لازم دارد.
- **`NUM_HISTORY_SHARDS=512`** در Temporal **برای همیشه ثابت** است و بعد از ساخت cluster قابل تغییر نیست.
- **Grafana:** داشبوردها از ریپو بار میشوند. تغییر را در JSON داخل ریپو بده، نه در UI.

## ۵. OpenBao: init و unseal

- **Init یک‌باره:** `make openbao-init` (درون `make up` هم اجرا میشود). با **۱ key share و threshold ۱**. خروجی (کلید unseal و root token) **فقط** در `/home/Hub/.secrets/openbao-init.json` (پوشه `700`، فایل `600`) ذخیره میشود و چاپ نمیشود.
  - اگر OpenBao init شده باشد ولی فایل کلید نباشد، یا برعکس، اسکریپت **متوقف میشود** و چیزی را تغییر نمیدهد. **از مالک بپرس.**
- **Unseal دستی:** `make unseal`. کلید از stdin به `bao write sys/unseal key=-` داده میشود. نه در آرگومان دیده میشود، نه در خروجی.
- **Unseal خودکار:** `coinepro-hq-openbao-unseal.timer`، یک دقیقه بعد از boot و بعد هر ۵ دقیقه. اگر OpenBao unseal باشد، کاری نمیکند. ری‌استارت کانتینر هم خودبه‌خود ترمیم میشود.
- **وضعیت:** `infra/compose/hq.sh exec -T openbao bao status`. Healthcheck فقط وقتی سالم است که OpenBao init و unseal شده باشد.

### Policyها، AppRoleها و توکن ادمین (پرامپت ۳)
- **`make llm-provision`** (جزو `make up`):
  - KV v2 در `kv/` و AppRole
  - policyهای `llm-router`، `claude-runtime` و `hq-admin` (`infra/openbao/policies/`)
  - AppRole هر سرویس
  - توکن router↔runtime، توکن metrics، و اولین فراخواننده‌ی API ‏(`hq-ops`)
  - هیچ مقداری چاپ نمیشود.
- **توکن ادمین غیر root:** `/home/Hub/.secrets/openbao-admin.token` (`600`)، با policy ‏`hq-admin` و دوره‌ی ۳۲ روز. در هر `make up` تمدید میشود. اگر ۳۲ روز `make up` اجرا نشود منقضی میشود و `provision.sh` یک بار دیگر با root token یک توکن ادمین تازه میسازد.
- **root token هنوز معتبر است.** باطل کردنش تصمیم مالک است. بعد از باطل شدن، فقط توکن ادمین کار میکند و اگر منقضی شود، ساختن root تازه کلید unseal لازم دارد (`bao operator generate-root`).
- **فایل‌های سرویس‌ها** در `/home/Hub/.secrets/services/<service>/` هستند و مالکشان uid کانتینر است (10001؛ و 65534 برای Prometheus). برای دیدن یا عوض کردنشان sudo لازم است. برای ساختن دوباره‌ی secret_id، فایل را با sudo پاک کن و `make llm-provision` بزن.

### ⚠️ ریسک‌ها (آگاهانه پذیرفته شده برای این مرحله)
1. **کلید unseal و root token کنار داده‌ها، روی همین دیسک‌اند.** هر کس به root یا کاربر `Hub` دسترسی داشته باشد، یا یک کپی از دیسک داشته باشد (snapshot یا backup هتزنر)، میتواند OpenBao را باز کند و همه‌ی رمزها را بخواند. در عمل، unseal خودکار ارزش «sealed بودن» را از بین میبرد. محافظت اصلی، محدود بودن دسترسی به سرور است.
2. **۱ key share** یعنی یک کلید واحد. اگر فایل گم شود و OpenBao sealed باشد، داده‌ها برای همیشه از دست میروند. **مالک باید یک کپی امن از فایل خارج از سرور نگه دارد** (مثلاً password manager).
3. **root token** هنوز معتبر است. بعد از ساختن policyها و توکن‌های محدود (پرامپت بعد)، باید revoke شود.
4. **API بدون TLS است.** فقط از `hq-internal` و `127.0.0.1` در دسترس است. قبل از اینکه هر سرور دیگری به آن وصل شود، TLS لازم است.
5. **راه بهتر در آینده:** unseal با Transit یا KMS، یا چند key share بین چند نفر (`bao operator rekey`). تصمیمش با مالک است.

## ۶. عوض کردن پروفایل `lean` و `full`

- **خودکار:** اگر `HQ_PROFILE` در `.env` خالی باشد، `hq.sh` از روی RAM انتخاب میکند: `MemTotal` کمتر از 11GiB (یعنی سرور کمتر از ۱۲GB اسمی) → `lean`، وگرنه `full`.
- **دستی:** `HQ_PROFILE=lean` یا `HQ_PROFILE=full` در `.env`.
- **فرق پروفایل‌ها:** `full` به‌علاوه‌ی Tempo، otel-collector و cAdvisor است، با سقف‌های حافظه‌ی بیشتر (`infra/compose/profiles/*.env`).
- **قانون:** جمع سقف حافظه‌ی همه‌ی کانتینرها ≤ **۸۰٪** RAM. این عدد در پرامپت ۳ از ۶۰٪ بالا رفت، چون سرویس‌های لایه‌ی مدل اضافه شدند. `make check` آن را چک میکند.

**بعد از ارتقای RAM سرور** (مثلاً به ۱۶GB):
```bash
make down          # توقف همه (داده‌ها میمانند)
make profile       # باید full باشد
make up
make check
```
**برگشت به lean:** همان مراحل. `make down` کانتینرهای Tempo، otel و cAdvisor را هم حذف میکند.

## ۷. پورت‌ها و آدرس‌ها

| سرویس | روی سرور (host) | داخل `hq-internal` | پروفایل |
|---|---|---|---|
| Caddy (عمومی) | `0.0.0.0:80`، `0.0.0.0:443` | `caddy:2020` (health و metrics) | همه |
| Grafana | `127.0.0.1:3000` | `grafana:3000` | همه |
| Prometheus | `127.0.0.1:9090` | `prometheus:9090` | همه |
| Loki | `127.0.0.1:3100` | `loki:3100` | همه |
| Alloy | — | `alloy:12345` | همه |
| node-exporter | `172.30.0.1:9100` (فقط gateway شبکه‌ی `hq-internal`) | `172.30.0.1:9100` | همه |
| PostgreSQL | `127.0.0.1:5432` | `postgres:5432` | همه |
| Valkey | `127.0.0.1:6379` | `valkey:6379` | همه |
| NATS (client) | `127.0.0.1:4222` | `nats:4222` | همه |
| NATS (monitoring) | `127.0.0.1:8222` | `nats:8222` | همه |
| Temporal (gRPC) | `127.0.0.1:7233` | `temporal:7233` (HTTP: 7243، metrics: 9090) | همه |
| Temporal UI | `127.0.0.1:8233` | `temporal-ui:8080` | همه |
| OpenBao | `127.0.0.1:8200` | `openbao:8200` | همه |
| Tempo | `127.0.0.1:3200` | `tempo:3200`، OTLP: `tempo:4317`/`4318` | full |
| otel-collector (OTLP) | `127.0.0.1:4317` (gRPC)، `127.0.0.1:4318` (HTTP) | `otel-collector:4317`/`4318` | full |
| cAdvisor | — | `cadvisor:8080` | full |
| llm-router | — (**بدون پورت منتشرشده**) | `llm-router:8000` (شبکه‌های `hq-internal` و `hq-llm`) | همه |
| claude-runtime | — (**بدون پورت منتشرشده**) | `claude-runtime:8100` (**فقط** شبکه‌ی `hq-llm`) | همه |
| SSH (مال مالک) | `0.0.0.0:1367` | — | — |

**دسترسی از لپ‌تاپ مالک** با تونل SSH، بدون باز کردن پورت:
```bash
ssh -p 1367 -L 3000:127.0.0.1:3000 -L 8233:127.0.0.1:8233 -L 9090:127.0.0.1:9090 Hub@<IP سرور>
# بعد: http://localhost:3000 (Grafana، کاربر admin)  http://localhost:8233 (Temporal UI)
```
رمز Grafana در `.env` (`GRAFANA_ADMIN_PASSWORD`) است. آن را فقط روی سرور بخوان و چاپ نکن.

**کاربران و رمزهای سرویس‌ها:**

| سرویس | کاربر | متغیر رمز در `.env` |
|---|---|---|
| Postgres (ادمین) | `postgres` | `POSTGRES_PASSWORD` |
| دیتابیس `hq` | `hq` | `HQ_DB_PASSWORD` |
| دیتابیس `temporal` | `temporal` | `TEMPORAL_DB_PASSWORD` |
| دیتابیس `temporal_visibility` | `temporal_visibility` | `TEMPORAL_VISIBILITY_DB_PASSWORD` |
| Valkey | (پیش‌فرض) | `VALKEY_PASSWORD` |
| NATS | `hq` | `NATS_PASSWORD` |
| Grafana | `admin` | `GRAFANA_ADMIN_PASSWORD` |
| دیتابیس `hq` برای llm-router | `llm_router` | `LLM_ROUTER_DB_PASSWORD` |
| API ‏llm-router | فراخواننده‌ی `hq-ops` | فایل `/home/Hub/.secrets/llm-router-caller-hq-ops.token` |

## ۸. عیب‌یابی سریع

| نشانه | کار |
|---|---|
| یک سرویس unhealthy است | `make logs s=<service>` و داشبورد «HQ / Containers» |
| `openbao` unhealthy است | احتمالاً sealed است: `make unseal` |
| `make up` روی `--wait` شکست خورد | `infra/compose/hq.sh ps -a`؛ کار یک‌باره‌ای که کد غیرصفر دارد را با `make logs s=<job>` ببین |
| حافظه پر است | `docker stats --no-stream` و قانون ۶۰٪ (`make check`) |
| backup اجرا نشد | `journalctl -u coinepro-hq-backup.service` |

## ۹. لایه‌ی مدل‌ها (پرامپت ۳)
- **مستندات کامل:** `docs/ops/LLM_LAYER.md` (معماری، جدول‌ها، اولویت‌ها، و افزودن اتصال).
- **توکن Claude (فقط مالک):** در یک ترمینال جدا، با کاربر `Hub`:
  1. `claude setup-token`، لینک را در مرورگر باز کن و کدی که مرورگر میدهد (شامل `#`) را **در همان پنجره‌ی `claude setup-token`** paste کن. آن پنجره بعدش توکن را چاپ میکند که با `sk-ant-oat01-` شروع میشود.
  2. `make claude-token` و paste همان خط `sk-ant-oat01-...`. ورودی پنهان است، توکن مستقیم به OpenBao میرود و runtime restart میشود. اگر کد مرورگر یا مقدار با فرمت اشتباه paste شود، اسکریپت چیزی ذخیره نمیکند و خطا میدهد.
- **وضعیت:**
  - `infra/compose/hq.sh exec -T claude-runtime cat /tmp/hq-health.json` (فیلد `oauth`)
  - داشبورد «Token Treasury — Ops»
- **وقتی سهمیه تمام میشود:**
  - اتصال `claude-max` در `llm.connections` به `quota_exhausted` میرود، با `quota_reset_at`.
  - P4 با `429` رد میشود؛ P0 تا P3 خطای `quota_exhausted` میگیرند، چون همه‌ی جایگزین‌ها خاموش‌اند.
  - بعد از ریست، خودکار برمیگردد.
- **ledger:** `llm.calls`. خواندنش فقط با نقش‌های RLS ممکن است. viewها: `llm.v_usage_daily` و `llm.v_top_actors_30d`.

## ۱۰. ملاحظات امنیتی این مرحله
- **Alloy** پوشه‌ی `/var/lib/docker/containers` را فقط‌خواندنی میخواند. این پوشه env کانتینرها را هم دارد، پس دسترسی Alloy عملاً در حد خواندن رمزهاست. به Docker socket دسترسی ندارد.
- **cAdvisor** (فقط `full`) به Docker socket و socket containerd دسترسی دارد، که عملاً هم‌ارز root است. این روش رسمی خود cAdvisor است.
- **claude-runtime** فقط روی شبکه‌ی `hq-llm` است. به Postgres، Valkey، NATS، Temporal و Grafana دسترسی ندارد (آزمایش شده). اینترنت برای API ‏Anthropic باز است.
- **llm-router و claude-runtime:** کاربر 10001، rootfs فقط‌خواندنی، `cap_drop: ALL`، بدون پورت منتشرشده، بدون سوکت Docker و بدون mount از ریپوها.
- **Docker** قوانین iptables خودش را میسازد و از ufw رد میشود. برای همین، هر پورت فقط روی `127.0.0.1` منتشر میشود. مرجع فایروال فقط فایروال هتزنر است.
