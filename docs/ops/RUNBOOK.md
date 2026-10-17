# CoinePro HQ — RUNBOOK (سکوی پایه)

> سند عملیاتی Claude سرور. همه‌ی دستورها از ریشه‌ی ریپو (`/home/Hub/CoinePro-Hub`) و با کاربر `Hub` اجرا میشوند.
> **قانون:** هیچ رمزی چاپ نمیشود. هیچ حذف یا ریبوتی بدون اجازه‌ی مالک انجام نمیشود.

## ۱. نمای کلی

- **پروژه‌ی Compose:** `coinepro-hq`. فایل اصلی: `infra/compose/compose.yaml`.
- **همیشه از `make` استفاده کن** (یا `infra/compose/hq.sh`). `hq.sh` پروفایل حافظه را انتخاب میکند و `profiles/<profile>.env` و `.env` را بار میکند. `docker compose` خالی، پروفایل و سقف‌های حافظه را نمیشناسد.
- **رمزها:** `infra/compose/.env` (دسترسی `600`، در gitignore). کلیدهای OpenBao: `/home/Hub/.secrets/openbao-init.json` (دسترسی `600`).
- **شبکه:** سرویس‌ها روی شبکه‌ی `hq-internal` (`172.30.0.0/24`) هستند، جز آن‌هایی که عمداً جدا شده‌اند (§۷):
  - Temporal روی `hq-core` است.
  - OPA و Tool Gateway روی `hq-agent` هستند.
  - وب روی `hq-edge` است.
  - claude-runtime روی `hq-llm` است.
  - هر پورت فقط روی `127.0.0.1` منتشر میشود. تنها استثنا Caddy روی 80 و 443 است.
- **سرور (از ۲۰۲۶-۱۰-۱۷، پرامپت ۴.۲):** هتزنر Cloud ‏CPX42، با Rescale «فقط CPU و RAM»:
  - ۸ vCPU ‏AMD EPYC Genoa، **16GB RAM** (`MemTotal` حدود 15608 MiB)، swap ‏8GB
  - دیسک همان ۱۵۰GB قبلی است، تا برگشت به پلن کوچک‌تر ممکن بماند.
  - کرنل `6.8.0-147-generic`، Ubuntu 24.04، منطقه‌ی زمانی UTC
- **دامنه:** `hq.coinepro.com`، با HTTPS خودکار (§۱۲).

| دستور | کار |
|---|---|
| `make help` | فهرست دستورها |
| `make env` | ساختن `.env` با رمزهای تصادفی (هیچ‌وقت فایل موجود را بازنویسی نمیکند) |
| `make bootstrap` | **یک بار، با sudo** (پرامپت ۵ §۱.۵): پوشه‌ی لنگر Audit و فایل‌های رمز کانتینرها. بعد از آن `make up` هیچ sudo نمیخواهد |
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
| `make lock` | ساختن دوباره‌ی lock فایل‌های Python (با hash)، شامل `apps/api` |
| `make owner-enroll` | **فقط مالک، در ترمینال خودش:** لینک یک‌بارمصرف ثبت کلید عبور (۱۵ دقیقه). همین دستور مسیر بازیابی هم هست. بدون دامنه کار نمیکند |
| `make openapi` | ساختن دوباره‌ی `apps/api/openapi/hq-api.v1.json` از روی کد (CI بررسی میکند که با کد بخواند) |
| `make verify-live` | تست‌های زنده روی stack در حال اجرا: جدا بودن شبکه‌ها و نبودن مقدار پارامتر در لاگ Postgres. کانتینر موقت روی `hq-internal` به OPA، Temporal و gateway نمیرسد. از داخل `web` فقط Caddy جواب میدهد. از داخل `gateway` فقط api و OPA جواب میدهند (§۷) |
| `make audit-reanchor reason="..."` | فقط بعد از restore دیتابیس، **فقط در ترمینال**: لنگر تازه‌ی زنجیره‌ی Audit، با تأیید تایپی و ردیف audit (§۳) |
| `make prompt-check role=<role>` | یک فراخوانی **واقعی** با prompt یک منشور (پیش‌فرض مشاور) از راه `hq-ops`؛ schema و پاسخ سنجیده میشوند؛ هیچ چیزی جز ledger ذخیره نمیشود |
| `make bootstrap-month1` | کارهای راه‌اندازی ماه ۱ (`apps/api/seed/bootstrap/month1.yaml`) به نام سرویس `bootstrap`؛ **اجرای واقعی مدل بیدار میکند** (`docs/ops/AGENTS.md`) |

## ۲. بالا آوردن و پایین آوردن

**اولین بار روی یک سرور تازه:**
```bash
make env               # .env با رمزهای تصادفی
make bootstrap         # یک بار با sudo: پوشه‌ی لنگر، init و unseal و provision کردن OpenBao، فایل‌های رمز
make up                # همه‌چیز (بدون sudo)
make install-systemd   # تایمرهای backup شبانه، unseal خودکار و متریک کانتینرها
make check
make verify-live
```

**`make up` به این ترتیب کار میکند:**
1. `gen-env.sh`: کلیدهایی که پرامپت‌های جدید اضافه کرده‌اند به `.env` اضافه میشوند. رمزها تصادفی‌اند، خط‌های موجود دست نمیخورند و هیچ مقداری چاپ نمیشود.
2. فقط `openbao` بالا میاید. بعد، اگر لازم باشد: `init.sh`، ‏`unseal.sh`، و در هر حال `provision.sh` (idempotent). این مرحله فایل‌های AppRole و توکن metrics را **قبل** از بالا آمدن سرویس‌ها میسازد.
   - **sudo فقط در `make bootstrap`** (پرامپت ۵ §۱.۵): مالک فایل‌های رمز uid کانتینرهاست. `provision.sh` فهرست فایل‌های نصب‌شده را در `/home/Hub/.secrets/.provisioned` نگه میدارد. در `make up` بعدی، فایلی که هست دوباره نصب نمیشود و sudo نمیخواهد. اگر فایل تازه‌ای لازم باشد و sudo نباشد، **پیش از هر تغییری** با پیام «run make bootstrap» متوقف میشود.
   - پوشه‌ی لنگر را هم فقط `make bootstrap` میسازد. `make up` فقط وجودش را چک میکند (`anchor-dir.sh --check`).
3. `up -d --build --wait`: ایمیج‌های خودمان (`coinepro-hq/llm-router` و `coinepro-hq/claude-runtime`) ساخته میشوند و همه‌چیز بالا میاید. ترتیب وابستگی‌ها:
   - `postgres` ← `temporal-schema` ← `temporal` ← `temporal-namespace` ← `temporal-ui`
   - `postgres` ← `db-provision` ← `llm-migrate` ← `llm-router`
   - `hq-tools` قبل از Loki و Alloy
   صبر تا همه healthy شوند، حداکثر ۵ دقیقه.

**پایین آوردن:** `make down`. کانتینرهای همه‌ی پروفایل‌ها حذف میشوند و داده‌ها در volumeها میمانند.
**هرگز `down -v` نزن.** این دستور همه‌ی داده‌ها را پاک میکند و فقط با اجازه‌ی صریح مالک اجرا میشود.

**یک سرویس:** `infra/compose/hq.sh restart <service>` یا `infra/compose/hq.sh up -d <service>`.

**کارهای یک‌باره** (`hq-tools`، `temporal-schema`، `temporal-namespace`، `db-provision`، `llm-migrate`) اجرا میشوند و با کد 0 خارج میشوند. این وضعیت طبیعی است. برای دیدنشان: `infra/compose/hq.sh ps -a`.

**بعد از ریبوت:** Docker کانتینرها را خودش بالا میاورد (`restart: unless-stopped`). تایمر `coinepro-hq-openbao-unseal.timer` یک دقیقه بعد از boot، و بعد هر ۵ دقیقه، OpenBao را unseal میکند. چک کن: `make ps`. این مسیر در Rescale ‏۲۰۲۶-۱۰-۱۷ آزموده شد: هر ۱۷ سرویس بدون دخالت healthy شدند. بعد یک `make up` بزن تا کارهای یک‌باره هم دوباره اجرا شوند.

## ۳. backup و restore

- **شبانه:** `coinepro-hq-backup.timer` هر شب ساعت **۰۲:۳۰ UTC** (با تأخیر تصادفی تا ۱۵ دقیقه) اجرا میشود. اگر سرور در آن ساعت خاموش بوده باشد، بعد از روشن شدن اجرا میشود.
- **چه چیزی:**
  - برای هر دیتابیس (به جز `postgres`) یک `pg_dump -Fc` جدا، به‌علاوه‌ی `globals.sql` (نقش‌ها؛ شامل hash رمزها)، `manifest.json` و `SHA256SUMS`.
  - (پرامپت ۴.۱) فایل‌های api (volume ‏`hq-files`): `files.tar.gz` و `files.sha256` (sha256 هر فایل).
  - یک کپی از لنگرهای زنجیره‌ی Audit: `audit-chain.jsonl`.
- **کجا:** `/home/Hub/backups/<YYYYMMDDTHHMMSSZ>/` (دسترسی `700`/`600`). **نگهداری ۷ روز.** فقط پوشه‌هایی با همین الگوی نام پاک میشوند.
- **لنگر زنجیره‌ی Audit (پرامپت ۴.۱ §۱.۱۱):**
  - فایل: `/home/Hub/backups/audit-anchors/audit-chain.jsonl`. append-only است و بیرون از volume پستگرس.
  - پوشه را `make bootstrap` میسازد (`infra/backup/anchor-dir.sh`، مالک uid 10001، `0750`). `make up` فقط وجودش را چک میکند.
  - `worker` آن را خواندنی و نوشتنی در `/anchors` دارد و `api` فقط خواندنی.
  - retention هرگز این پوشه را پاک نمیکند. هر backup یک کپی از آن را برمیدارد، که offsite هم میرود.
- **وضعیت:** `systemctl list-timers 'coinepro-hq-*'` و `journalctl -u coinepro-hq-backup.service`.
- **فایل‌های وضعیت** (پرامپت ۵): `backup.sh` و `restore-test.sh` نتیجه را در `/home/Hub/backups/status/backup.json` و `restore-test.json` مینویسند (زمان، ok، اندازه، مدت؛ بدون مسیر رمز). worker آن را فقط‌خواندنی میبیند (ابزار `health.hub`).
- **تست بازیابی:** `make restore-test`. آخرین backup را در یک Postgres موقت (همان ایمیج، بدون شبکه، 512MB) بازیابی میکند و این‌ها را چک میکند:
  - checksumها و `pg_restore --exit-on-error` (نقش‌ها اول از `globals.sql` ساخته میشوند)
  - برابر بودن تعداد جدول‌ها با فهرست آرشیو (ردیف‌های `TABLE ATTACH` پارتیشن‌ها شمرده نمیشوند)
  - افزونه‌ی `vector` در `hq` و نسخه‌ی schema در Temporal
  - **فایل‌ها:** در یک volume موقت بازیابی میشوند و sha256 همه‌ی آن‌ها بررسی میشود. اگر backup فایلی نداشته باشد، همین مسیر روی یک فایل نمونه آزموده میشود.
  - **لنگرها:** JSONL معتبر با `seq` و `hash`.

  بعد کانتینر و volumeهای موقت پاک میشوند. **حداقل ماهی یک بار اجرا شود.**
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

**لنگر Audit بعد از restore** (پرامپت ۵ §۱.۴): بعد از restore، سرِ زنجیره در Postgres از آخرین لنگر بیرون آن قدیمی‌تر است، پس `GET /api/v1/audit/verify` جواب `anchor: mismatch` میدهد. این رفتار درست است، چون همین تشخیص میدهد که دیتابیس عقب رفته. وقتی restore عمدی بوده:
```bash
make audit-reanchor reason="restore of backup <stamp>"   # باید عبارت re-anchor را تایپ کنی
```
- **فقط در ترمینال** (پرامپت ۵.۱ §۳). بدون ترمینال، مثل pipe، cron یا اجرای یک ایجنت، اسکریپت پیش از هر کاری متوقف میشود.
- `HQ_REANCHOR_CONFIRM=re-anchor` فقط تایپ کردن را در همان ترمینال حذف میکند، نه شرط ترمینال را.
- زنجیره‌ی بازیابی‌شده باید خودش سالم باشد، وگرنه کاری انجام نمیشود.
- یک ردیف audit ‏`audit.reanchor` (A3) با دلیل و هر دو سر زنجیره ثبت میشود.
- یک خط لنگر تازه اضافه میشود که لنگر قبلی را در فیلد `previous` نگه میدارد. **هیچ خطی از فایل لنگر پاک نمیشود.**

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

- **خودکار:** اگر `HQ_PROFILE` در `.env` خالی باشد، `hq.sh` از روی RAM انتخاب میکند: `MemTotal` کمتر از 15GiB (یعنی سرور کمتر از ۱۶GB اسمی) → `lean`، وگرنه `full`.
- **دستی:** `HQ_PROFILE=lean` یا `HQ_PROFILE=full` در `.env`.
- **فرق پروفایل‌ها:** `full` به‌علاوه‌ی Tempo و otel-collector است، با سقف‌های حافظه‌ی بیشتر (`infra/compose/profiles/*.env`).
- **cAdvisor در هیچ پروفایل پیش‌فرضی نیست** (پرامپت ۵ §۱۱): به سوکت Docker و containerd نیاز دارد، یعنی root روی host. فقط با پروفایل جدای `cadvisor` روشن میشود.
  - **جایگزین بی‌سوکت:** `infra/observability/container-metrics.sh` روی host (تایمر `coinepro-hq-container-metrics.timer`، هر ۳۰ ثانیه) متریک هر کانتینر (`hq_container_up`، حافظه، سقف، CPU، شبکه، ری‌استارت) را در textfile ‏node-exporter مینویسد (`/var/lib/coinepro-hq/textfile`). داشبورد «HQ / Containers» از همین میخواند.
- **قانون:** جمع سقف حافظه‌ی همه‌ی کانتینرها ≤ **۸۰٪** RAM. این عدد در پرامپت ۳ از ۶۰٪ بالا رفت، چون سرویس‌های لایه‌ی مدل اضافه شدند. `make check` آن را چک میکند.

**وضعیت فعلی (پرامپت ۵، ۲۰۲۶-۱۰-۱۷): `full`.**
- **چرا `full`:**
  - سرور 16GB است.
  - با `full`، سقف سرویس‌هایی که در ۴.۱ تنگ شده بودند به اندازه‌ی سالم برمیگردد (Valkey، Alloy، Grafana، Loki، Prometheus، OpenBao).
  - claude-runtime ظرفیت ۵ اجرای همزمان دارد (`LLM_MAX_CONCURRENCY=5`). اندازه‌گیری: هر پروسه‌ی CLI حدود 180MB بیکار و 250 تا 300MB هنگام پاسخ.
    - از پرامپت ۵.۱ سقفش `2304m` است، در برابر `1600m` قبلی: ۵ × 300 به‌علاوه‌ی خود سرویس، با جای اضافه.
  - Tempo و otel-collector، tracing را برای اجراهای ایجنت‌ها میدهند.
  - cAdvisor (سوکت Docker) بیرون است.
- **عددها** (پرامپت ۵.۱ §۲.۱۰؛ `scripts/quality/memory-budget.sh`):
  - **قاعده‌ی گیت:**
    - هر پروفایل ≤ ۸۰٪ RAM مرجعش، با دست‌کم ۵٪ از این بودجه آزاد.
    - هر پروفایل همراه هر پروفایل opt-in (`cadvisor`) هم ≤ ۸۰٪.
    - RAM مرجع `full` همان آستانه‌ی انتخاب `full` در `hq.sh` است (15360 MiB)، نه `MemTotal` یک سرور.
  - **`full`:** 11216 MiB در برابر 11673 MiB (۸۰٪ از 15360 منهای ۵٪). با cAdvisor: 11408 از 12288. روی همین سرور: 11216 از 12486 (۸۰٪ رم 15608 MiB).
    - otel-collector از 256m به 384m رفت: ۲۰۲۶-۱۰-۱۷ با 231 MiB بالای مرز ۸۰٪ ‏memory_limiter خودش بود.
  - **`lean`** (برای برگشت به سرور کوچک‌تر): 5792 MiB در برابر 5886 MiB (۸۰٪ از 7745 منهای ۵٪). با cAdvisor: 5984 از 6196.
    - برای این جا، claude-runtime در `lean` دو اجرای همزمان دارد (`768m`).
    - postgres، Prometheus، Loki و Temporal UI به اندازه‌ی مصرف واقعی‌شان کوچک شدند.
    - tmpfsهای وب جزو سقف خود کانتینر حساب میشوند، پس کوچک شدند: `/tmp` 16m و `.next/cache` 32m، از 224m (`WEB_TMPFS_*` در پروفایل).
- `.env` حالا `HQ_PROFILE=full` دارد.

**رفتن به `full`** (فقط وقتی تصمیمش گرفته شد):
```bash
# در .env:  HQ_PROFILE=full   (یا خالی، برای انتخاب خودکار)
make down          # توقف همه (داده‌ها میمانند)
make profile       # باید full باشد
make up
make check
```
**برگشت به lean:** همان مراحل با `HQ_PROFILE=lean`. ‏`make down` کانتینرهای Tempo و otel را هم حذف میکند.

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
| Temporal (gRPC) | `127.0.0.1:7233` | **فقط شبکه‌ی `hq-core`:** `temporal:7233` (HTTP: 7243، metrics: 9090) | همه |
| Temporal UI | `127.0.0.1:8233` | `temporal-ui:8080` (`hq-core`) | همه |
| OPA | — (**بدون پورت منتشرشده**) | **فقط `hq-agent`:** `opa:8181` (فقط `POST /v1/data/hq/...` و `GET /health`) | همه |
| api / worker | — (**بدون پورت منتشرشده**) | `api:8000` (`hq-internal`، `hq-core` و `hq-agent`) | همه |
| OpenBao | `127.0.0.1:8200` | `openbao:8200` | همه |
| Tempo | `127.0.0.1:3200` | `tempo:3200`، OTLP: `tempo:4317`/`4318` | full |
| otel-collector (OTLP) | `127.0.0.1:4317` (gRPC)، `127.0.0.1:4318` (HTTP) | `otel-collector:4317`/`4318` | full |
| cAdvisor | — | `cadvisor:8080` | فقط پروفایل `cadvisor` (opt-in) |
| gateway (Tool Gateway) | — (**بدون پورت منتشرشده**) | **فقط `hq-agent`:** `gateway:8080` (فقط worker صدایش میزند) | همه |
| web (پنل Next.js) | — (**بدون پورت منتشرشده**) | **فقط `hq-edge`:** `web:3000`؛ Caddy هر مسیر جز `/api` را به آن میدهد | پروفایل `web` (وقتی `apps/web/Dockerfile` هست) |
| llm-router | — (**بدون پورت منتشرشده**) | `llm-router:8000` (شبکه‌های `hq-internal` و `hq-llm`) | همه |
| claude-runtime | — (**بدون پورت منتشرشده**) | `claude-runtime:8100` (**فقط** شبکه‌ی `hq-llm`) | همه |
| SSH (مال مالک) | `0.0.0.0:1367` | — | — |

**شبکه‌ی `hq-core` (`172.30.2.0/24`، پرامپت ۴.۱):**
- Temporal (بی‌احراز روی 7233) فقط اینجاست و **روی `hq-internal` نیست.**
- اعضای مجاز: `temporal`، `temporal-namespace`، `temporal-ui`، `api`، `worker`، `postgres` (دیتابیس Temporal) و `prometheus` (متریک Temporal).

**شبکه‌ی `hq-agent` (`172.30.3.0/24`، internal، پرامپت ۵.۱ §۲.۹):**
- مسیر ابزار ایجنت‌ها: worker ← gateway ← api (`/internal/v1`)، و OPA برای هر سه.
- اعضای مجاز: `worker`، `gateway`، `api` و `opa`.
- `gateway` و `opa` **فقط** اینجا هستند. پس gateway به Temporal، Postgres، NATS، Valkey و OpenBao نمیرسد و به اینترنت هم راهی ندارد.

**شبکه‌ی `hq-edge` (`172.30.4.0/24`، internal، پرامپت ۵.۱ §۲.۹):**
- فقط `caddy` و `web`.
- وب (Next.js، رو به اینترنت) **فقط** اینجاست. پس جز Caddy به هیچ چیز نمیرسد: نه دیتابیس، نه api، نه OpenBao، نه Prometheus و Loki، نه node-exporter، نه اینترنت.
- Caddy راه بیرون (ACME) و api را از `hq-internal` دارد.

**جدا بودن شبکه‌ها دو بار بررسی میشود:**
- `scripts/quality/compose-rules.sh` هر عضو دیگر و هر شبکه‌ی اضافه را رد میکند، و internal بودن `hq-agent` و `hq-edge` را میسنجد.
- `make verify-live` همین را روی stack زنده از داخل `web` و `gateway` آزمایش میکند.
- Valkey فقط cache است و **هیچ persistence ندارد** (نه AOF، نه RDB). پس fork بازنویسی هرگز حافظه را دو برابر نمیکند.
- Postgres مقدار پارامترهای کوئری را هرگز لاگ نمیکند (`log_parameter_max_length=0`، و همین برای خطاها).

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
| حافظه پر است | `docker stats --no-stream` و قانون ۸۰٪ (`make check`) |
| گواهی HTTPS گرفته یا تمدید نشد | `make logs s=caddy` (خط‌های `tls.obtain`)، رکورد DNS و باز بودن TCP 80 و 443 در فایروال هتزنر (§۱۲) |
| backup اجرا نشد | `journalctl -u coinepro-hq-backup.service` |

## ۹. لایه‌ی مدل‌ها (پرامپت ۳)
- **مستندات کامل:** `docs/ops/LLM_LAYER.md` (معماری، جدول‌ها، اولویت‌ها، و افزودن اتصال).
- **توکن Claude (فقط مالک):** در یک ترمینال جدا، با کاربر `Hub`:
  1. `claude setup-token`، لینک را در مرورگر باز کن و کدی که مرورگر میدهد (شامل `#`) را **در همان پنجره‌ی `claude setup-token`** paste کن. آن پنجره بعدش توکن را چاپ میکند که با `sk-ant-oat01-` شروع میشود.
  2. `make claude-token` و paste **کل** توکن `sk-ant-oat01-...` (حدود ۱۰۸ کاراکتر؛ اگر ترمینال آن را در دو خط شکسته، هر دو خط را با هم کپی کن). ورودی پنهان است، توکن مستقیم به OpenBao میرود و runtime restart میشود. اگر کد مرورگر یا مقدار با فرمت اشتباه paste شود، اسکریپت چیزی ذخیره نمیکند و خطا میدهد.
- **وضعیت:**
  - `infra/compose/hq.sh exec -T claude-runtime cat /tmp/hq-health.json` (فیلد `oauth`)
  - داشبورد «Token Treasury — Ops»
- **وقتی سهمیه تمام میشود:**
  - اتصال `claude-max` در `llm.connections` به `quota_exhausted` میرود، با `quota_reset_at`.
  - P4 با `429` رد میشود؛ P0 تا P3 خطای `quota_exhausted` میگیرند، چون همه‌ی جایگزین‌ها خاموش‌اند.
  - بعد از ریست، خودکار برمیگردد.
- **ledger:** `llm.calls`. خواندنش فقط با نقش‌های RLS ممکن است. viewها: `llm.v_usage_daily` و `llm.v_top_actors_30d`.

## ۱۰. هسته‌ی هلدینگ (پرامپت ۴)
- **مستندات کامل:** `docs/ops/CORE.md` (معماری، جدول‌ها، قاعده‌های دیتابیس، سیاست‌ها، گردش‌کارها و افزودن شرکت).
- **سرویس‌ها:** `api` و `worker` (یک ایمیج: `apps/api`)، `opa` و کار یک‌باره‌ی `api-migrate`. هیچ‌کدام پورت منتشرشده ندارند.
- **ورود:** فقط با دامنه. یک خط `HQ_SITE_ADDRESS=<دامنه>` در `.env`، سپس `make up` و بعد `make owner-enroll` (خود مالک). بدون دامنه، `/api` در Caddy ۴۰۴ است و endpointهای ورود جواب `503 origin_not_configured` میدهند.
  - **از ۲۰۲۶-۱۰-۱۷:** `HQ_SITE_ADDRESS=hq.coinepro.com` تنظیم شده است و ورود پیکربندی شده است (§۱۲).
  - **`make owner-enroll` هنوز اجرا نشده است.** مالک خودش، وقتی وب یا اپ آماده شد، اجرایش میکند.
  - **کلید عبور discoverable** (پرامپت ۵ §۱.۳، تأییدشده): ثبت با `residentKey=required` است (`security/passkeys.py`)، پس ورود هیچ فهرست credential نمیخواهد. هیچ passkey قبلی در production نیست.
  - **sign-count** فقط **بعد از** تأیید امضا مقایسه میشود. امضای نامعتبر هیچ audit یا 🔴 نمیسازد.
  - **بعد از step-up** توکن نشست کوکی (وب) عوض میشود. نشست Bearer اپ دست نمیخورد.
- **سلامت:**
  - `make ps`؛ لاگ `api ready` در `make logs s=api`؛ `schedules ensured` در `make logs s=worker`
  - از داخل شبکه: `infra/compose/hq.sh exec -T caddy wget -qO- http://api:8000/api/v1/health`
- **کلید توقف اضطراری** (اگر اپ در دسترس نیست):
  - از اپ: `POST /api/v1/control/kill-switch`. روشن کردن step-up نمیخواهد، آزاد کردنش 🔏 میخواهد.
  - بدون اپ (فقط مالک): `infra/compose/hq.sh exec -T postgres psql -U postgres -d hq -c "UPDATE control.kill_switches k SET state='engaged', reason='manual', changed_by_kind='owner', changed_by_code='owner', changed_at=now() FROM core.companies c WHERE c.id=k.company_id AND c.kind='holding'"`
  - اثر: router فقط P0 را اجرا میکند، اقدام نوشتنی ایجنت‌ها ۴۲۳ میگیرد و اجراهای دائمی صبر میکنند.
- **Audit:** `GET /api/v1/audit/verify`. گردش‌کار شبانه هم آن را بررسی میکند و اگر زنجیره شکسته باشد اعلان 🔴 میدهد.
- **کانال‌های اعلان:**
  - FCM و تلگرام وقتی مالک credential را در OpenBao بگذارد روشن میشوند (`kv/hq-api/channels/fcm` و `kv/hq-api/channels/telegram`). api و worker ظرف ۵ دقیقه آن را میخوانند.
  - Web Push کلید VAPID دارد و با دامنه کار میکند.

## ۱۱. ملاحظات امنیتی این مرحله
- **Alloy** پوشه‌ی `/var/lib/docker/containers` را فقط‌خواندنی میخواند. این پوشه env کانتینرها را هم دارد، پس دسترسی Alloy عملاً در حد خواندن رمزهاست. به Docker socket دسترسی ندارد.
- **cAdvisor** به Docker socket و socket containerd دسترسی دارد، که عملاً هم‌ارز root است. از پرامپت ۵ در هیچ پروفایل پیش‌فرضی نیست (فقط `--profile cadvisor`). متریک کانتینرها بی‌سوکت از host میاید (§۶).
- **gateway** فقط روی `hq-agent` است (internal)، با کاربر 10001، rootfs فقط‌خواندنی و `cap_drop: ALL`. فقط hash توکن worker را دارد، نه خود توکن را. به Temporal، دیتابیس، NATS، Valkey، OpenBao و اینترنت نمیرسد.
- **web** فقط روی `hq-edge` است (internal). کاربر 10001 دارد، rootfs فقط‌خواندنی (tmpfs برای `/tmp` و کش Next) و `cap_drop: ALL`. هیچ رمزی ندارد و جز Caddy به هیچ چیز نمیرسد.
  - Caddy هدر `X-Middleware-Subrequest` را پیش از رسیدن به وب حذف میکند (CVE-2025-29927).
  - بدنه‌ی درخواست به وب را 1MB محدود میکند.
- **واحد systemd متریک کانتینرها** sandbox دارد (پرامپت ۵.۱ §۳):
  - `NoNewPrivileges`، `ProtectSystem=strict` و `PrivateTmp`.
  - فقط پوشه‌ی textfile نوشتنی است.
  - تغییر واحد با `make install-systemd` (sudo) نصب میشود.
- **claude-runtime** فقط روی شبکه‌ی `hq-llm` است. به Postgres، Valkey، NATS، Temporal و Grafana دسترسی ندارد (آزمایش شده). اینترنت برای API ‏Anthropic باز است.
- **llm-router و claude-runtime:** کاربر 10001، rootfs فقط‌خواندنی، `cap_drop: ALL`، بدون پورت منتشرشده، بدون سوکت Docker و بدون mount از ریپوها.
- **Docker** قوانین iptables خودش را میسازد و از ufw رد میشود. برای همین، هر پورت فقط روی `127.0.0.1` منتشر میشود. مرجع فایروال فقط فایروال هتزنر است.

## ۱۲. دامنه و HTTPS (پرامپت ۴.۲)
- **دامنه‌ی پنل:** `hq.coinepro.com`. تنظیمش در `.env` فقط یک خط است: `HQ_SITE_ADDRESS=hq.coinepro.com`.
- **مقدارهایی که `hq.sh` از روی دامنه میسازد:**
  - `HQ_API_EDGE=on`: ‏`/api` در Caddy باز میشود.
  - `HQ_PUBLIC_ORIGIN=https://hq.coinepro.com`
  - `HQ_WEBAUTHN_RP_ID=hq.coinepro.com`
- **DNS (مال مالک):**
  - رکورد **A** با نام `hq` در zone ‏`coinepro.com` (Cloudflare)، روی IPv4 عمومی همین سرور
  - **فقط DNS** (ابر خاکستری)، بدون رکورد AAAA
  - پراکسی Cloudflare (ابر نارنجی) را بدون تصمیم روشن نکن. با آن، IP واقعی کاربر به api نمیرسد و `X-Forwarded-For` و محدودیت نرخ برای هر IP عوض میشود.
- **گواهی:**
  - Caddy گواهی را خودش از Let's Encrypt میگیرد (چالش HTTP-01) و خودش تمدید میکند.
  - گواهی در volume ‏`caddy-data` نگه داشته میشود.
  - **TCP 80 و 443 باید در فایروال هتزنر باز بمانند.** بستن 80 تمدید را میشکند.
  - اولین گواهی ۲۰۲۶-۱۰-۱۷ گرفته شد: issuer ‏Let's Encrypt ‏YE2، انقضا ۲۰۲۷-۰۱-۱۵.
- **HSTS:** `max-age=31536000; includeSubDomains` روی کل سایت (`infra/caddy/api-on.caddy`). مرورگری که یک بار آن را دیده، تا یک سال `hq.coinepro.com` و زیردامنه‌هایش را فقط با HTTPS باز میکند.
- **کلید عبور (WebAuthn):** به `rp_id` بسته است. **عوض کردن دامنه یعنی همه‌ی کلیدهای عبور ثبت‌شده از کار میافتند** و ثبت دوباره (`make owner-enroll`) لازم است.
- **Web Push:**
  - با دامنه روشن میشود (`meta.channels.web_push`).
  - subject کلید VAPID خالی است، پس origin دامنه به جایش به کار میرود.
- **بررسی‌ها** (فقط کد وضعیت و هدر):
```bash
H=https://hq.coinepro.com
curl -s -o /dev/null -w '%{http_code}\n' $H/api/v1/health          # 200
curl -s -o /dev/null -w '%{http_code}\n' $H/api/v1/meta            # 401 (بدون نشست)
curl -s -o /dev/null -w '%{http_code}\n' $H/internal/v1/health     # 404
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://hq.coinepro.com/   # 308 -> https
curl -s -D - -o /dev/null $H/api/v1/health | grep -i -E 'strict-transport|content-security|x-frame'
curl -s -D - -o /dev/null $H/ | grep -i -c alt-svc                   # 0 (HTTP/3 خاموش)
curl -s -o /dev/null -w '%{http_code}\n' $H/__canary              # 404 (قناری خاموش؛ 503 فقط وقتی روشن است)
echo | openssl s_client -connect hq.coinepro.com:443 -servername hq.coinepro.com 2>/dev/null | openssl x509 -noout -issuer -enddate
```
- **HTTP/3 خاموش است** (پرامپت ۵ §۱.۹): `servers { protocols h1 h2 }` در Caddyfile، پس هدر `alt-svc` هم نیست. هیچ تغییری در فایروال لازم نبود. روشن کردنش (UDP 443) تصمیم مالک است.
- **برگشت به حالت بی‌دامنه:**
  1. `HQ_SITE_ADDRESS=` خالی شود، سپس `make up`.
  2. نتیجه: ‏`/api` جواب ۴۰۴ میدهد و endpointهای ورود جواب ۵۰۳.

## ۱۳. ایجنت‌ها، پایش سایت‌ها و سهمیه (پرامپت ۵)
- **مستندات کامل:** `docs/ops/AGENTS.md` (چرخه‌ی اجرا، Tool Gateway، مشاور، پایش سایت‌ها، Quota Controller، افزودن نقش و ابزار).
- **سرویس‌ها:** `gateway` (فقط `hq-agent`) و `web` (پروفایل `web`، فقط `hq-edge`). هیچ‌کدام پورت منتشرشده ندارند. اجراها داخل `worker` هستند. هیچ پروسه‌ای برای نقش‌ها همیشه روشن نیست.
- **Caddy و وب:**
  - `/api/*` ← `api`. هر مسیر دیگر ← `web` (`infra/caddy/web-on.caddy`) وقتی `apps/web/Dockerfile` هست (`HQ_WEB=on` در `hq.sh`).
  - وگرنه یک صفحه‌ی ثابت «ستاد کوینه‌پرو» (`web-off.caddy`).
  - CSP صفحه‌های وب را خود وب میگذارد (nonce). Caddy فقط روی `/api` CSP میگذارد.
  - HSTS، nosniff، Referrer-Policy، COOP و CORP روی کل سایت.
  - `/internal` همچنان ۴۰۴ است.
- **رمزهای اجرای ایجنت** (`make bootstrap` یک بار، بعد `make up`):
  - فراخواننده‌ی `hq-agents` روی llm-router (۲۴۰ درخواست در دقیقه)
  - `kv/hq-agents/runtime` (`llm_router_token`، `gateway_token`) که worker میخواند
  - فایل hash توکن gateway
  - هیچ‌کدام چاپ نمیشود.
- **سقف مصرف:**
  - `AGENT_DAILY_TOKEN_CAP` در `.env` (پیش‌فرض ۲٬۰۰۰٬۰۰۰ در روز UTC، برای همه‌ی اجراها؛ ورودی، خروجی و cache با هم شمرده میشوند). **روی هاب از ۲۰۲۶-۱۰-۱۷: ‏600000** (سقف پرامپت ۵). بالا بردنش تصمیم مالک است.
  - `AGENT_INCIDENT_BUDGET_TOKENS` (۶۰٬۰۰۰ برای هر کار حادثه)
  - سقف منشور هر نقش
- **کلیدها:**
  - `HQ_CEO_DAILY_REPORTS=on` (پیش‌فرض خاموش)، گزارش روزانه‌ی مدیرعامل‌ها
  - `HQ_MORNING_REPORT_LLM=off`، فقط نسخه‌ی قاعده‌محور گزارش صبحگاهی
- **پایش سایت‌ها:**
  - فهرست در `apps/api/seed/sites.yaml`. مالک از اپ عوض میکند (`PUT /api/v1/ops/sites` 🔏).
  - Schedule ‏`hq-site-checks` هر ۵ دقیقه. ۳ شکست پشت هم ← حادثه و یک کار.
  - دیدن: `GET /api/v1/ops/incidents?open=true`
- **سهمیه:** `GET /api/v1/treasury/quota`. `warning` ← P4 متوقف؛ `limited` ← فقط P0 تا P2.
- **کارهای ماه ۱:** `make bootstrap-month1`. هر نتیجه‌ی استخدام فقط یک تصمیم `hire` منتظر مُهر مالک است. **هیچ‌کدام خودکار تأیید نمیشود.**
- **قناری:**
  - `/__canary` همیشه ۵۰۳ میدهد.
  - سایت قناری در seed با `enabled: false` خاموش است.
  - برای آزمودن دوباره‌ی خط کامل: `enabled: true` در `sites.yaml` و `make up`. این کار یک اجرای واقعی مدل الزامی میکند.

## ۱۴. تصمیم‌های ثبت‌شده‌ی مالک و اپ اندروید (پرامپت ۶ §۱)
- **سه سؤال گزارش ۴.۱** (تصمیم مالک، ۲۰۲۶-۱۰-۱۷):
  - نقش NOLOGIN برای مالک دیتابیس **بعداً**.
  - سقف **۵ اعلان فوری در ساعت** برای هر شرکت **میماند**.
  - Valkey **بدون persistence** میماند.
  - هیچ کاری لازم نیست، فقط همین ثبت.
- **passkey در اپ اندروید:** `HQ_ANDROID_ORIGINS` در `infra/compose/.env` (به api میرود) برابر `android:apk-key-hash:<SHA-256 گواهی امضا، base64url>` است.
  - این مقدار **عمومی** است و رمز نیست.
  - فایل `/.well-known/assetlinks.json` را خود وب میسازد.
  - بررسی: `curl -sI https://hq.coinepro.com/.well-known/assetlinks.json` (Content-Type `application/json`، اثر انگشت `D6:D4:…:15:BF`).
- **وب** از پرامپت ۵ بالاست. Caddy مسیر `/api/*` را به api میفرستد و بقیه را به web. CSP را خود web میگذارد.

## ۱۵. فایل‌ها، رسانه و صدا (پرامپت ۶ §۲ و §۳)
- **آپلود مالک:** `POST /api/v1/files`، بدنه‌ی خام با `Content-Type` و `X-File-Name` (UTF-8 با percent-encoding).
  - **نوع از روی محتوا (magic bytes) تعیین میشود.** اگر header با محتوا نخواند، جواب `415` است.
  - **سقف حجم هر نوع حین stream نگه داشته میشود** (`413` پیش از پایان آپلود):

    | نوع | سقف |
    |---|---|
    | عکس | ۲۰ MB |
    | فیلم | ۲۰۰ MB / ۱۰ دقیقه |
    | صدا | ۲۵ MB / ۱۵ دقیقه |
    | PDF | ۳۰ MB |

  - Caddy روی مسیرهای `/api/v1/files` و `/api/v1/transcribe` بدنه‌ی تا ۲۰۱ MB را رد میکند، با timeout ده دقیقه.
- **عکس:** همان لحظه در api پاک میشود: چرخش درست، **بدون EXIF، GPS و XMP**، با سقف ۴۰ مگاپیکسل. نسخه‌ی ذخیره‌شده همان نسخه‌ی پاک است. دو variant هم ساخته میشود:
  - `thumb`: WebP، حداکثر ۵۱۲ پیکسل
  - `agent`: JPEG، لبه‌ی بلند ≤ ۱۵۶۸ پیکسل؛ همان چیزی که مدل میبیند
- **فیلم و صدا:** وضعیت `processing` است. workflow ‏`FileProcess` در worker با ffmpeg این‌ها را میسازد:
  - `poster`
  - تا ۱۲ فریم کلیدی (تغییر صحنه، حداکثر یکی در هر ۵ ثانیه؛ اگر صحنه عوض نشود، با فاصله‌ی یکسان)
  - صدای ۱۶ kHz، برای متن

  بعد `ready` یا `failed` میشود و رویداد `file.ready` یا `file.failed` روی topic ‏`files` میرود. فایلی که workflowش شروع نشده بود، در Maintenance دوباره شروع میشود.
- **پیوست:**
  - تا ۱۰ فایل در هر پیام. بدنه‌ی پیام با پیوست میتواند خالی باشد.
  - فایلی که هنوز پیوست نشده مال هلدینگ است. با اولین پیوست **به شرکت همان thread منتقل میشود**، فقط یک بار. فایلی که مال شرکت دیگری شده `422` میگیرد.
  - ایجنت فقط فایل‌های شرکت خودش را میبیند:
    - عکس به‌صورت **بلوک تصویر** میرسد، حداکثر ۲۰ تصویر در یک اجرا.
    - فیلم به‌صورت فریم‌های کلیدی و متن صدا میرسد.
    - صدا فقط به‌صورت متن میرسد.
    - نام فایل و EXIF هیچ‌وقت به مدل نمیرسد.
  - ابزار `file.view` (A0، فقط شرکت خود ایجنت) تا وقتی Claude سشن مشورت آن را به `agents/tools.md` اضافه نکند، `unknown_tool` میگیرد.
- **صدا به متن:** `POST /api/v1/transcribe?purpose=message|order|note`، فقط صدا.
  - مسیر کار: Whisper روی خود هاب (سرویس `stt`، پروفایل opt-in، فقط روی شبکه‌ی `hq-stt` با worker)، بعد نرمال‌ساز قطعی فارسی (`hq_common.persian`)، بعد نقطه‌گذاری با مدل سبک (`stt_punctuation`، P1). خروجی مدل اگر بیش از ۸٪ کلمه‌ها را عوض کند رد میشود و متن نرمال‌شده میماند. هر دو متن در `files.processing` نگه داشته میشوند.
  - اگر متن ماسک‌شدنی داشته باشد (رمزی بلند خوانده شده)، گذر مدل اصلاً انجام نمیشود.
  - پیامی که فایل صدای `purpose=message` را پیوست دارد `kind: voice_transcript` است.
  - وقتی پروفایل `stt` خاموش است: `503 channel_not_configured`.
- **ffmpeg** نسخه‌ی `7:7.1.5-0+deb13u1` (Debian trixie) است. **Pillow** ‏12.3.0 (MIT-CMU) و **pillow-heif** ‏1.8.0 (BSD-3) در image مشترک api و worker هستند.
## ۱۶. گفتار به متن فارسی، STT (پرامپت ۶ §۳، قرارداد §۱۷.۲)
- **سرویس `stt`** (`services/stt`):
  - faster-whisper ‏1.2.1 روی CTranslate2 ‏4.8.2، با int8 روی CPU، زبان `fa`، beam 5 و VAD ‏Silero.
  - مدل پیش‌فرض `large-v3-turbo` است.
  - **هیچ صدایی از هاب بیرون نمیرود:** سرویس آفلاین است (`HF_HUB_OFFLINE=1`) و مدل را فقط‌خواندنی از volume ‏`stt-models` میخواند.
- **شبکه:**
  - `hq-stt` شبکه‌ی internal است و فقط `worker` و `stt` رویش هستند (`compose-rules`). `stt` پورت منتشرشده ندارد.
  - API فقط از worker صدایش میزند، با یک activity ‏Temporal و `STT_URL=http://stt:8000`.
  - تنها بخشی که اینترنت دارد job یک‌باره‌ی `stt-fetch` است، روی شبکه‌ی جدای `hq-fetch`.
- **امنیت کانتینر:** کاربر 10001، rootfs فقط‌خواندنی، tmpfs روی `/tmp`، ‏`cap_drop: ALL` و healthcheck روی `/health`.
- **پروفایل:**
  - `stt` اختیاری است و پیش‌فرض خاموش است.
  - روشن کردن: `HQ_STT=on` در `.env`، بعد `make stt-fetch` و `make up`.
  - `hq.sh` فقط وقتی روشن است `--profile stt` و `STT_URL` را میدهد؛ وگرنه `STT_URL` خالی است.
  - **تا وقتی پروفایل فعال به‌علاوه‌ی stt از بودجه‌ی حافظه بیشتر است**، `up`، `run`، `create`، `start` و `restart` با `HQ_STT=on` رد میشوند (exit 3، با عددها). بقیه‌ی فرمان‌ها (`exec` پشتیبان و unseal، `ps`، `logs`) با یک هشدار و بدون stt اجرا میشوند.
  - گیت `memory-budget` هر ترکیب را چاپ میکند. ترکیب روشن باید جا شود. ترکیب خاموشی که بیشتر است فقط با `OVER by … (not enabled …)` گزارش میشود.

### مدل و پین
- `services/stt/model.lock.json` برای هر مدل (`large-v3-turbo`، `medium`، `small`؛ همه MIT) این‌ها را دارد: repo، ‏revision (commit) و اندازه و sha256 **هر فایل**.
  - `make stt-fetch [model=…]` فقط همان بایت‌ها را میگیرد. فایل درست موجود رد میشود. هر بایت اضافه یا hash نادرست ← خطا.
  - سرویس موقع بالا آمدن همه را دوباره میسنجد. اگر چیزی جور نباشد، **سرویس نمیدهد:** `stt: refusing to start: …` با exit 2 و کانتینر unhealthy. راه حل: `make stt-fetch` دوباره.
- **عوض کردن مدل:** `STT_MODEL=medium` (یا `small`) در `.env`، بعد `make stt-fetch model=medium` و `make up`.
- **مدل تازه:** یک ورودی تازه در `model.lock.json` لازم است. revision یک commit است، نه شاخه. sha256 هر فایل همان `lfs.oid` است در `https://huggingface.co/api/models/<repo>/tree/<revision>`. بعد از fetch، `sha256sum` باید همان را بدهد.

### API (فقط از worker)
- **`POST /v1/transcribe`:**
  - بدنه‌ی خام `audio/*` یا `video/*`.
  - حداکثر ۲۵ MiB، شمرده‌شده هنگام خواندن: بیشتر ← `413 too_large`.
  - حداکثر ۱۵ دقیقه: بیشتر ← `413 too_long`.
  - نوع اشتباه ← `415`. صدای خراب ← `422 undecodable`.
  - پاسخ: `{text_raw, text, language: "fa", duration_s, confidence, segments[{start_s, end_s, text}], engine{name, model, version}, timing{load_s, transcribe_s}}`.
  - `text` همان `hq_common.persian.normalise(text_raw)` است. سکوت ← `""`.
- **همزمانی:** هر بار یک رونویسی. حداکثر `STT_MAX_WAITING` (۴) درخواست صبر میکنند؛ بیشتر ← `503 busy`.
- **`GET /health`** مدل را بار نمیکند. **`GET /metrics`** ‏Prometheus است: `stt_requests_total{outcome}`، `stt_transcribe_seconds`، `stt_audio_seconds_total`، `stt_model_loaded`، `stt_model_load_seconds`. Prometheus روی `hq-stt` نیست و scrape نمیکند. برای دیدن: `infra/compose/hq.sh exec stt python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/metrics').read().decode())"`.
- **بار شدن مدل:** با اولین درخواست. بعد از `STT_IDLE_UNLOAD_S` (۳۰۰) ثانیه بیکاری آزاد میشود (`malloc_trim`).
- **نرمال‌ساز** (`hq_common.persian`، قطعی):
  - `normalise(text)`: ی و ک عربی به فارسی، ZWNJ برای می/نمی و پسوندها، نشانه‌های فارسی و فاصله. هیچ کلمه و عددی عوض نمیشود.
  - `words`، ‏`word_edit_distance` و `wer(reference, hypothesis)`.

### عددهای اندازه‌گیری‌شده (۲۰۲۶-۱۰-۱۷، همین CPX42، int8، beam 5، ‏۴ thread، MiB)
| | large-v3-turbo | medium | small |
|---|---:|---:|---:|
| زمان بار شدن | 2.3 s | 2.7 s | 0.9 s |
| RSS بعد از بار شدن | 961 | 894 | 344 |
| اوج هنگام بار شدن (fp16 ← int8) | 1644 | 1581 | 610 |
| ۳۰ ثانیه صدا: زمان / اوج | 8.8 s / 1301 | 11.9 s / 1561 | 4.2 s / 648 |
| ۵ دقیقه صدا: زمان / اوج | 57.7 s / 1460 | 91.6 s / 1773 | 38.6 s / 1225 |
| بعد از آزاد شدن | 177 | 137 | 157 |
| WER روی ۵ نمونه‌ی مصنوعی | 82.9% | 63.4% | 92.7% |

- `MEM_STT=2048m` اوج turbo به‌علاوه‌ی ۲۵٪ است. `MEM_STT_FETCH=128m`.
- **WER بالا مال صدای رباتیک espeak-ng است، نه گفتار واقعی.** نمونه‌های `services/stt/tests/samples` برای تست‌اند و دقت واقعی را نشان نمیدهند. هدف (دقت کلمه ≥ ۹۵٪) را فقط با صدای واقعی میشود سنجید:
  - `make stt-eval dir=<پوشه>` با `<name>.ogg` و متن درستش در `<name>.txt`.
  - `model=…` مدل را عوض میکند. `write=1` گزارش را در `docs/ops/reports/stt-eval-<تاریخ>.md` مینویسد.
  - اجرا بدون شبکه است (`--network none`).

### تصمیم حافظه (با مالک)
`full` + stt برابر **13392 MiB** است، **1104 MiB** بیشتر از بودجه‌ی 12288 MiB (۸۰٪ از 15360). `lean` + stt برابر 7968 است، 1772 بیشتر از 6196. تا مالک تصمیم نگیرد stt خاموش میماند. سه راه:

1. **مدل کوچک‌تر.** `small` با سقف حدود 1536m (اوج ۵ دقیقه 1225) ← 12880، هنوز 592 بیشتر. `medium` (اوج 1773) کمکی نمیکند. پس `small` تنها، بدون راه ۲ یا کوتاه‌تر کردن سقف ۱۵ دقیقه، جا نمیشود.
2. **سقف‌های دیگر پایین‌تر** (مصرف زنده‌ی `docker stats` در ۲۰۲۶-۱۰-۱۷ / سقف فعلی):
   - postgres ‏174/1536 ← 1024 (‏`shared_buffers` 384MB میماند)
   - prometheus ‏159/768 ← 512
   - tempo ‏115/384 ← 256
   - loki ‏72/512 ← 384
   - otel-collector ‏40/384 ← 256
   - جمع: −1152 ← 12240، فقط ۴۸ MiB جای خالی.
   - یا claude-runtime ‏62 (بیکار)/2304 با ۳ اجرای همزمان CLI به جای ۵ ← حدود 1536 (−768).
   - temporal (326/832) و grafana (275/512) تنگ‌اند.
   - با `small`، فقط postgres و loki کافی‌اند (−640 ← 12240).
3. **سرور بزرگ‌تر** (فقط عدد؛ هزینه با مالک): Hetzner ‏CPX52 (12 vCPU، 24 GB) یا CCX33 (8 vCPU اختصاصی، 32 GB).
   - یک پروفایل تازه با `HQ_BUDGET_REF_RAM_MB` همان RAM لازم است. مثلاً 24576 ← بودجه‌ی 19660، که `full` + stt با حدود 6 GB جای خالی در آن جا میشود.
   - vCPU اختصاصی رونویسی را هم تندتر میکند.

## ۱۷. کارگاه کد و فرمان صوتی (پرامپت ۶ §۴ و §۵)
- راهنمای کامل: **`docs/ops/WORKSHOP.md`**. آنجا adapterها، قوانین ۱ تا ۷، طراحی `self_hosted` و مسیریابی فرمان آمده است.
- **وضعیت:**
  - کنترل‌پلن کامل است: workspace، grant، سشن، رویداد، approval، قفل کاری، بودجه و transcript.
  - `WORKSHOP_RUNTIME` خالی است. پس `GET /meta` مقدار `workshop.runtime = null` میدهد و `POST /workshop/sessions` جواب `503 runtime_not_configured` میدهد.
  - workspaceها از `apps/api/seed/workspaces.yaml` میایند: ریپوی هر شرکت، به‌علاوه‌ی `HQ-HUB`.
- **منتظر مالک:**
  - انتخاب محل اجرا: `managed` با یک API key جدا و سقف ماهانه، یا `self_hosted` روی هاستی جدا.
  - توکن GitHub مخصوص هر workspace (fine-grained، فقط همان ریپو). مالک خودش آن را در OpenBao میگذارد.
  - ری‌استارت api بعد از تنظیم.
- **فرمان صوتی:** `POST /api/v1/orders` سه مرحله دارد:
  1. قاعده (`apps/api/seed/order_rules.yaml`)
  2. مدل سبک (`order_routing`، P1)
  3. مشاور کل، فقط وقتی فرمان مبهم است

  رویداد `order.routed` روی topic ‏`orders` میرود.
