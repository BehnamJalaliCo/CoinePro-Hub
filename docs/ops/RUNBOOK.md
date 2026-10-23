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
  - ابزار `files.read` (A0، فقط شرکت خود ایجنت؛ در پرامپت ۶ با نام `file.view` ساخته شد و طبق `agents/tools.md` تغییر نام داد).
- **صدا به متن:** `POST /api/v1/transcribe?purpose=message|order|note`، فقط صدا.
  - مسیر کار: Whisper روی خود هاب (سرویس `stt`، پروفایل opt-in، فقط روی شبکه‌ی `hq-stt` با worker)، بعد نرمال‌ساز قطعی فارسی (`hq_common.persian`)، بعد نقطه‌گذاری با مدل سبک (`stt_punctuation`، P1). خروجی مدل اگر بیش از ۸٪ کلمه‌ها را عوض کند رد میشود و متن نرمال‌شده میماند. هر دو متن در `files.processing` نگه داشته میشوند.
  - اگر متن ماسک‌شدنی داشته باشد (رمزی بلند خوانده شده)، گذر مدل اصلاً انجام نمیشود.
  - پیامی که فایل صدای `purpose=message` را پیوست دارد `kind: voice_transcript` است.
  - وقتی پروفایل `stt` خاموش است: `503 channel_not_configured`.
- **ffmpeg** نسخه‌ی `7:7.1.5-0+deb13u1` (Debian trixie) است. **Pillow** ‏13.0.0 (MIT-CMU) و **pillow-heif** ‏1.8.0 (BSD-3) در image مشترک api و worker هستند.
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

### بازبینی ۷.۱ §۰.۲ (۲۰۲۶-۱۰-۲۲): جا برای STT
- **کارهای انجام‌شده:**
  - **الف) مرورگر:** در full هم یک session دارد. سقفش 768m است، چون یک session اوج ۳۸۰ مگ دارد و قاعده‌ی دو برابر ۷۶۰ میخواهد (۶۴۰ کمتر از قاعده بود).
  - **ب) claude-runtime:** ۴ اجرای هم‌زمان (`RUNTIME_MAX_CONCURRENCY` و `LLM_MAX_CONCURRENCY` ۴) و سقف 1856m.
  - **ج) Tempo و otel-collector:** به پروفایل اختیاری `tracing` رفتند. پیش‌فرض خاموش‌اند؛ `make tracing-on` و `make tracing-off`. Prometheus فقط وقتی روشن‌اند آن‌ها را scrape میکند.
- **قاعده‌ی «سقف دست‌کم دو برابر بیشترین مصرف اندازه‌گیری‌شده»:** سه سقف زیر قاعده بودند و بالا رفتند:
  - alloy: ۱۸۰ ← 384m
  - grafana: ۲۷۵ ← 576m
  - openbao: ۱۵۳ ← 320m
  - otel-collector: ۲۳۱ ← 512m (در `tracing`)
- **نتیجه:** full برابر 10896 از 11673 مگ است، و full+tracing برابر 11664 از 12288 که جا میشود. egress در full یک پردازش هم‌زمان دارد و سقفش 512m است (اوج ۲۳۵ ضرب در ۲).
- **کمبود STT:** full+stt برابر 13072 از 12288 مگ است، یعنی **۷۸۴ مگ کمبود** با سقف فعلی STT (2048m، یعنی اوج ۱۶۴۴ به‌علاوه‌ی ۲۵٪).
  - با قاعده‌ی دو برابر روی خود STT (3328m)، کمبود **۲۰۶۴ مگ** است.
  - مدل کوچک انتخاب نشد (دستور بازبینی). **STT خاموش میماند تا مالک تصمیم بگیرد.**
- **lean:** قاعده‌ی دو برابر را برای مرورگر (448m با اوج ۳۸۰) و چند سرویس دیگر برآورده نمیکند. پروفایل فعال full است؛ lean پشتیبان سرور کوچک‌تر است.
- **پاک شد (اجازه‌ی صریح مالک، §۰.۳):** volume ‏`stt-measure-models` و image ‏`coinepro-hq/stt:measure`.

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

## ۱۸. backup ساعتی رمزنگاری‌شده، WAL پیوسته و PITR (پرامپت ۷ §۱، قرارداد §۱۸.۹)
**هدف:** در بدترین حالت بیرونی حداکثر **یک ساعت** داده از دست برود، و روی خود سرور فقط **چند دقیقه**. همه‌چیز رمزنگاری‌شده است و بازیابی هر هفته خودکار آزموده میشود. backup شبانه‌ی قبلی (§۳، محلی، ۷ روز) هم سر جایش میماند.

### WAL پیوسته و PITR
- **image تازه‌ی Postgres:** `coinepro-hq/postgres:0.1.0` همان pgvector پین‌شده است، به‌علاوه‌ی **WAL-G v3.0.9** (Apache-2.0، با sha256).
- **تنظیم آرشیو:**
  - `archive_mode=on`
  - `archive_timeout=60s`: آرشیو هیچ‌وقت بیش از یک دقیقه عقب نمیماند.
  - `archive_command = wal-g wal-push %p`
  - مقصد: `/home/Hub/backups/wal`، با مالک uid 999 (postgres) و دسترسی `0700`.
  - فشرده‌سازی zstd. اندازه‌گیری روی همین سرور: حدود ۲۰۰ KB در دقیقه، یعنی حدود ۳ GB در ۷ روز.
- **ساخت و چک پوشه‌ها:** پوشه‌ی WAL و مخزن محلی restic (`/home/Hub/backups/restic`، مالک root، `0700`) را `make bootstrap` میسازد. `make up` فقط چک میکند. بدون این پوشه‌ها `make up` جلو نمیرود، چون اگر Docker پوشه را خودش بسازد، آرشیو شکست میخورد و `pg_wal` بزرگ میشود.
- **base backup روزانه:** در اولین اجرای ساعتیِ هر **روز تقویمی UTC** (۷.۱ §۲.۶؛ قاعده‌ی قبلی «بیش از ۲۳ ساعت» هر روز جلوتر میافتاد). **۹ base backup نگه داشته میشود:** PITR تا هر دقیقه‌ی ۷ روز کامل گذشته (`HQ_WAL_KEEP_FULL`). `prune` و `restic check` هم با همین روز تقویمی‌اند.
- **علامت پایان PITR:** هر اجرای ساعتی پیش از snapshot یک commit و یک `pg_switch_wal()` میزند و صبر میکند تا آرشیو شود. پس آرشیو هر snapshot تا همان لحظه میرسد، و هر هدف PITR پیش از آن یک commit بعد از خودش دارد (بازیابی تا یک زمان روی اولین commit بعد از هدف میایستد؛ بدون آن شکست میخورد).
- **مهلت PITR:** دیگر عدد ثابت ۱۲۰ ثانیه نیست (۷.۱ §۲.۱). replay یک روز WAL (حدود ۱۴۴۰ segment) طول میکشد. شکست فقط وقتی است که `pg_last_wal_replay_lsn()` (و پیش از آن، شمار segmentهای بازیابی‌شده) `HQ_PITR_STALL_S` (۱۲۰ ثانیه) جلو نرود، یا کل کار از `HQ_PITR_DEADLINE_S` (۴۵ دقیقه) بگذرد.
- **تمرین PITR** (هرگز روی production نیست):
  ```bash
  make pitr-test at="2026-10-18 09:41"    # UTC، مگر منطقه‌ی زمانی بنویسی
  ```
  base backup پیش از آن لحظه به‌علاوه‌ی WAL تا همان لحظه، در یک Postgres موقت بدون شبکه بازیابی میشود. نتیجه یک خط JSON است: `recovered_to`، دیتابیس‌ها و تعداد جدول‌های `hq`. بعد همه‌چیز پاک میشود.
- **بازیابی واقعی PITR روی production** فقط با اجازه‌ی مالک انجام میشود، در ترمینال خودش و از روی همین اسکریپت. API هیچ راه restore ندارد.

### backup ساعتی (`coinepro-hq-backup-hourly.timer`)
- **زمان:** هر ساعت، با تأخیر تصادفی تا ۳ دقیقه. اجرای دستی: `make backup-hourly`.
- **مجموعه‌ی هر ساعت:**
  - `pg_dump -Fc -Z0` هر دیتابیس (بدون فشرده‌سازی: restic خودش با zstd فشرده میکند و dedup فقط روی dump فشرده‌نشده کار میکند؛ ۷.۱ §۲.۷)، به‌علاوه‌ی `globals.sql`
  - کپی لنگرهای Audit
  - sha256 همه‌ی فایل‌های api
  - snapshot ‏OpenBao، فقط با توکن مالک (پایین)
  - `manifest.json` و `SHA256SUMS`
- **snapshot ‏restic:** از مجموعه، آرشیو WAL و خود فایل‌های `hq-files`:
  1. اول در مخزن محلی
  2. بعد با `restic copy` به **Google Drive** (`rclone:gdrive:CoinePro HQ Backup`؛ خود پوشه مخزن restic است)
  3. و اگر روشن باشد، به Hetzner
- **نگهداری:**
  - Drive و Hetzner: `--keep-hourly 168 --keep-daily 90 --keep-weekly 52 --keep-monthly 36 --keep-yearly 10`
  - محلی: ۴۸ ساعتی و ۷ روزانه
  - روزی یک بار: `prune` و `restic check --read-data-subset 5%`
  - شکست `forget` یا `prune` هر مقصد (از جمله Drive) دیگر فقط لاگ نیست: `retention_ok: false` در وضعیت آن مقصد، و اعلان `decision`.
  - وقتی تست بازیابی هفتگی در حال خواندن یک مخزن است، `forget`، `prune` و `check` (قفل انحصاری restic میخواهند) به ساعت بعد میروند، تا هشدار دروغ نیاید.
- **رمزها:**
  - رمز restic در `kv/backup/restic` است. `make up` آن را یک بار میسازد و هیچ‌وقت عوض نمیکند (`infra/openbao/restic-password.sh`): فقط پاسخ 404 یعنی «نیست»، و نوشتن با KV check-and-set (`{"options":{"cas":0}}`) است. پس اگر رمز باشد، خود OpenBao نوشتن را رد میکند، هر چه خواندن قبلی جواب داده باشد (۷.۱ §۲.۹).
  - اسکریپت با AppRole ‏`hq-backup` (فقط خواندن `kv/backup/*`؛ `~/.secrets/backup/approle.json`، ‏600) فقط برای همان اجرا رمزها را در یک پوشه‌ی tmpfs و 0700 میگذارد: `RuntimeDirectory=` همان unit (`/run/coinepro-hq-backup-hourly`، `/run/coinepro-hq-restore-weekly`). systemd آن را بعد از اجرا، هر طور تمام شود، پاک میکند. اجرای دستی از `$XDG_RUNTIME_DIR` استفاده میکند.
  - container ‏restic فقط زیرپوشه‌ی رمز restic را فقط‌خواندنی mount میکند. config ‏rclone در زیرپوشه‌ی جدایی است و نوشتنی است، تا توکن تازه‌شده‌ی Drive برای فراخوانی‌های بعدی همان اجرا بماند.
  - **هیچ رمزی در argv، env کانتینر، لاگ یا فایل وضعیت نیست.** رمزها فقط از stdin به jq میرسند. gate ‏`backup` همین را اسکن میکند.
- **OpenBao فقط با 404 یعنی «پیکربندی نشده»** (۷.۱ §۲.۳). هر پاسخ دیگر (503، sealed، 403) برای Drive یعنی خطای همان مقصد و `ok:false` برای اجرا. نسخه‌ی محلی باز هم گرفته میشود. اجرا هیچ‌وقت بی‌صدا به «فقط محلی» نمیافتد.
  - اولین اجرایی که توکن Drive را میبیند، `gdrive_configured_at` را در `hourly/state.json` ثبت میکند. اگر آن توکن بعداً از OpenBao ناپدید شود، backup ساعتی و تست هفتگی هر دو خطا میدهند.
  - قطع عمدی Drive (فقط با تصمیم مالک): بعد از پاک کردن `kv/backup/gdrive`، کلید `gdrive_configured_at` را از `/home/Hub/backups/hourly/state.json` بردارید.
- **container:** `coinepro-hq/backup:0.1.0`، یعنی rclone ‏1.75.2 (digest) به‌علاوه‌ی restic ‏0.19.1 (sha256).
  - چرا root: ورودی‌ها مال چند uid هستند (WAL مال 999، فایل‌های api مال 10001، dumpها مال Hub).
  - ولی محدود است: فقط `DAC_READ_SEARCH` (خواندن)، rootfs فقط‌خواندنی، `no-new-privileges`. فقط `restore` تست هفتگی `DAC_OVERRIDE`، `CHOWN` و `FOWNER` هم میگیرد (۷.۱ §۳).
  - شبکه فقط وقتی مقصد بیرونی دارد.
  - سقف حافظه `MEM_BACKUP`: ‏256m در full و 192m در lean (`profiles/*.env`). ‏restic با ۴۰۰ MB ورودی در 192m بی‌خطا تمام شد.
  - **profile جدا (`backup-tools`):** هیچ سرویسی به آن وابسته نیست (worker دیگر به آن depends_on ندارد) و `up --wait` آن را اجرا نمیکند. `make up` بعد از بالا آمدن stack آن را میسازد و `restic version` را چک میکند. gateهای کیفیت آن را همیشه در بودجه‌ی حافظه میشمارند (`scripts/quality/lib.sh`، `ALWAYS_COUNTED`)، و `hq.sh` هم در حساب stt.
- **وضعیت:**
  - فایل‌های `status/hourly.json`، `status/snapshots.json` و `status/restore-weekly.json` فقط فراداده دارند.
  - worker هر ۵ دقیقه (Maintenance) آن‌ها را در `backup.*` میخواند.
  - رویدادها: `backup.done` و `backup.failed` روی topic ‏`backups`.
  - مشاهده: `GET /api/v1/backups/status`، `/backups/snapshots`، و ابزار `backups.status` برای ناظر و platform SRE.
  - `systemctl list-timers 'coinepro-hq-*'` و `journalctl -u coinepro-hq-backup-hourly.service`.
- **هشدارها** (هر کدام یک بار در هر رخداد):
  - مقصد بیرونی شکست بخورد ← اعلان `decision`
  - **آخرین backup موفق قدیمی‌تر از ۲ ساعت** ← **فوری** (از دست رفتن داده)
  - **شکست تست بازیابی** ← **فوری**
  - **شکست `restic check`** ← **فوری** (`backup:check:{at}`)
  - **نبودن `status/hourly.json` در حالی که `backup.runs` ردیف دارد** ← **فوری** (اسکریپت، پوشه یا mount ‏worker خراب است)
  - snapshot ‏OpenBao پیکربندی شده ولی `ok` نیست (توکن باطل شده یا تمدید نمیشود) ← `decision`
  - شکست `forget`/`prune` یک مقصد ← `decision`
  - یافته‌ی ناظر (`PR-070`) در پرامپت ۸ به `oversight_finding()` در `domain/backups.py` وصل میشود.
- **dead-man's switch در Prometheus** (۷.۱ §۲.۴)، بسته به worker و Temporal نیست:
  - هر اجرای ساعتی، موفق یا ناموفق، `hq_backup.prom` را در پوشه‌ی textfile ‏node-exporter (`/var/lib/coinepro-hq/textfile`) مینویسد: `hq_backup_last_success_timestamp_seconds`، `hq_backup_last_run_ok`، `hq_backup_destination_ok{destination}`، `hq_backup_check_ok`، `hq_backup_wal_failing` و `hq_backup_openbao_snapshot_ok`.
  - قاعده‌ها در `infra/observability/prometheus/rules/backup.rules.yml`: `HqBackupDeadMansSwitch` (آخرین موفقیت بیش از ۲ ساعت پیش)، `HqBackupMetricsMissing` (۲ ساعت بی‌گزارش)، `HqBackupCheckFailed`، `HqWalArchivingFailing` و `HqOpenBaoSnapshotFailing`.
  - دیدن: Grafana (فهرست alertها) یا `curl -s 127.0.0.1:9090/api/v1/alerts`. Alertmanager نداریم؛ اعلان مالک همچنان از worker است و این خط دوم مستقل است.
- **مقصد دوم، Hetzner Object Storage (اختیاری، خاموش):** با `HQ_BACKUP_S3_ENABLED=true` و `HQ_BACKUP_S3_*` در `.env` روشن میشود. یک مخزن restic دوم است با همان رمز. `offsite.sh` دیگر کپی خام شبانه نمیفرستد.

### تست بازیابی هفتگی (`coinepro-hq-restore-weekly.timer`)
- **زمان:** یکشنبه ۰۶:۰۰ تهران (۰۲:۳۰ UTC). اجرای دستی: `make restore-weekly`.
- **روند:**
  1. آخرین snapshot از Drive (اگر هیچ‌وقت وصل نشده، از مخزن محلی؛ Drive که یک بار وصل بوده و حالا نیست، شکست است) در پوشه‌ای موقت بازیابی میشود.
  2. همه‌ی بررسی‌های `restore-test.sh` روی مجموعه‌اش اجرا میشود.
  3. sha256 همه‌ی فایل‌ها چک میشود.
  4. **PITR به یک لحظه‌ی تصادفی ۲۴ ساعت گذشته** از آرشیو WAL بازیابی‌شده انجام میشود.
- **قفل‌ها (۷.۱ §۲.۵):** اول `flock` گرفته میشود، بعد trap. اجرای دومی که قفل را گرفته میبیند بی‌صدا خارج میشود و نتیجه‌ی اولی را خراب نمیکند. همه‌ی فراخوانی‌های restic در این مسیر `--retry-lock 30m` دارند.
- **جای دیسک (۷.۱ §۲.۷):** پیش از بازیابی، `restic stats --mode restore-size` با `df` مقایسه میشود. باید اندازه‌ی snapshot به‌علاوه‌ی `HQ_RESTORE_MIN_FREE_BYTES` (پیش‌فرض ۵ GiB) جا باشد؛ وگرنه با یادداشت روشن رد میشود و هیچ چیزی بازیابی نمیشود.
- **نتیجه:** در `backup.restore_tests` ثبت میشود. شکست ← اعلان فوری.

### کارهای مالک (به ترتیب، در ترمینال SSH خودش)
1. **`make gdrive-auth`** (لینک و کد؛ درخواست مالک ۲۰۲۶-۱۰-۲۲، چیزی نصب نمیشود):
   - اسکریپت یک لینک Google چاپ میکند. مالک آن را روی گوشی یا کامپیوتر خودش باز میکند، وارد میشود و «Allow» میزند.
   - مرورگر به `127.0.0.1:53682/?state=…&code=…` میرود که باز نمیشود (درست است). مالک همه‌ی آن آدرس را کپی میکند و بی‌نمایش در پرسش اسکریپت میچسباند.
   - پشت صحنه: `rclone authorize` با client عمومی rclone و scope ‏`drive.file` در یک کانتینر موقت backup-tools ‏(`hq-gdrive-auth`، بدون root، root filesystem فقط‌خواندنی) منتظر است. آدرس فقط به صفحه‌ی محلی همان کانتینر داده میشود و rclone کد یک‌بارمصرف را همان‌جا با توکن عوض میکند. توکن مستقیم به `kv/backup/gdrive` میرود و هیچ‌جا چاپ نمیشود. اسکریپت اتصال را آزمایش میکند و پوشه‌ی `CoinePro HQ Backup` را میسازد.
   - **دو مرحله‌ای:** `make gdrive-auth step=link` فقط لینک را میدهد و ورود ۳۰ دقیقه منتظر میماند (`HQ_GDRIVE_AUTH_WAIT_S`). بعد `make gdrive-auth step=code` آدرس را میگیرد: بی‌نمایش در ترمینال، یا از stdin وقتی مالک آدرس را به Claude سرور میدهد. کد درون آدرس فقط یک بار و فقط چند دقیقه معتبر است و بعد از مصرف بی‌ارزش است.
   - **client اختصاصی مالک (`own=1`، راه ماندگار):** client عمومی rclone سهمیه‌ی مشترک همه‌ی کاربران rclone را دارد و خود rclone میگوید در ۲۰۲۶ کنار میرود. اولین copy به Drive (۲۰۲۶-۱۰-۲۲) با `403 rateLimitExceeded` همان سهمیه شکست خورد.
     - **کار مالک در Google Cloud:** یک پروژه بسازد، Google Drive API را Enable کند، consent screen را بسازد و در Audience، «Publish app» بزند تا **«In production»** شود (در حالت «Testing»، refresh token بعد از ۷ روز باطل میشود). بعد در Clients یک OAuth client از نوع **Desktop app** بسازد.
     - با `make gdrive-auth own=1` (همراه `step=link` هم میشود) اسکریپت client ID و client secret را میپرسد (secret بی‌نمایش؛ با `step=link` دو خط از stdin) و همان لینک و آدرس بالا را با client مالک میگیرد. ID و secret از stdin به tmpfs کانتینر میرسند، نه argv و نه env کانتینر، و کنار توکن در `kv/backup/gdrive` ذخیره میشوند. scope همچنان `drive.file` است.
     - **عوض کردن client:** با `drive.file` هر client فقط فایل‌های خودش را میبیند. client تازه پوشه و مخزن restic خودش را میسازد (اولین copy کامل است). پوشه‌ی client قبلی در Drive میماند تا مالک خودش پاکش کند. ۲۰۲۶-۱۰-۲۲: از client عمومی به client خود مالک (پروژه‌ی `coinepro-hq-backup`، In production) رفتیم؛ ۵۱ snapshot در ۲۶۶ ثانیه کپی شد.
   - تا این کار نشده، backup ساعتی فقط محلی است و وضعیت Drive «پیکربندی نشده» است.
2. **نسخه‌ی کاغذی رمز restic:** `make backup-password`.
   - فقط در ترمینال خود مالک، با تایپ `show`. بعد از Enter صفحه پاک میشود.
   - **بدون این رمز هیچ snapshotی، از هیچ مقصدی، باز نمیشود.** Claude سرور آن را نمیبیند و چاپ نمیکند.
3. **توکن فقط-snapshot برای OpenBao:**
   - مالک خودش میسازد: `bao token create -policy=backup-snapshot -orphan -period=768h -display-name=hq-backup-snapshot` (policy ‏`infra/openbao/policies/backup-snapshot.hcl` فقط `sys/storage/raft/snapshot` را میخواند).
   - بعد `make openbao-snapshot-token` و چسباندن بی‌نمایش.
   - اسکریپت چک میکند توکن **فقط** همین policy را داشته باشد.
   - تا آن موقع، این بخش از backup «منتظر مالک» است.
   - **تمدید خودکار (۷.۱ §۲.۲):** بعد از هر snapshot موفق، backup ساعتی `auth/token/renew-self` میزند (policy همین را اجازه میدهد). پس توکن periodic تا وقتی backup کار میکند منقضی نمیشود. اگر snapshot شکست بخورد، یا تمدید نشود، یا توکن کمتر از ۷ روز عمر بیشتر بگیرد (توکن غیر periodic)، `openbao_snapshot.ok` برابر `false` میشود و اعلان `decision` میآید.

### راه‌اندازی بعد از merge (Claude سرور)
`make bootstrap` (پوشه‌های wal و restic، با sudo)، بعد `make up` (image تازه‌ی Postgres؛ **ری‌استارت Postgres** برای `archive_mode`؛ AppRole ‏`hq-backup` و رمز restic؛ ساخت image ‏`backup-tools`)، بعد `make install-systemd` (unitها و timerها، با `RuntimeDirectory=`). از ۷.۱: `make install-systemd` دوباره (unitهای hourly و weekly عوض شدند) و `make up` (policy ‏`backup-snapshot` و mount قاعده‌های Prometheus).
## ۱۹. اینترنت ایجنت‌ها: egress، SearXNG و مرورگر (پرامپت ۷ §۲، قرارداد §۱۸.۷)
- **اصل:** ایجنت‌ها همچنان shell و شبکه‌ی مستقیم ندارند. اینترنت فقط از ابزار میرسد. این ابزارها در Tool Gateway هستند و از سرویس `egress` بیرون میروند:
  - `web.search`: SearXNG خود هلدینگ
  - `web.read`: یک صفحه، به‌صورت HTML یا PDF به متن
  - `web.browse`: مرورگر واقعی
  - `http.request`
  - `egress.recent`
- **مسیر هر فراخوانی:**
  1. gateway در api رزرو میکند (`/internal/v1/egress/reserve`). این گام سه چیز را بررسی میکند:
     - **محافظ داده:** کد کارمند یک شرکت واقعی، ارجاع داخلی (`W-`، `D-`، `O-`، `I-`، `S-`…)، ایمیل، تلفن، رمز یا توکن ← `403 internal_data`.
     - **سقف‌ها** ← `429 egress_limit`.
     - **حساب سرویس**، اگر خواسته شده باشد.
  2. egress درخواست را بیرون میبرد.
  3. هر درخواست یک ردیف در `egress.log` و یک ردیف Audit با کلاس خودش میگیرد.
  4. نتیجه با `source: "web"`، نشانی نهایی، زمان و `suspected_injection` به مدل میرسد. متن‌های دستوری مشکوک فقط علامت میخورند و حذف نمیشوند.
- **کلاس هر فراخوانی:**
  - خواندن A0 است.
  - استفاده از حساب سرویس، یا هر روشی جز GET/HEAD در `http.request`، A2 است. A2 فقط وقتی مجاز است که policy حساب، آن مسیر را «بی‌تعهد» اعلام کرده باشد.
  - **تعهد بیرونی** (پرداخت، خرید، انتشار، پیام به آدم بیرونی، ساخت حساب، تغییر امنیت حساب) ← `needs_owner`، و ایجنت باید `propose` کند.
  - در مرورگر، پیش از هر click، type یا select، عنصر هدف و فرم و صفحه‌اش بررسی میشود. در حالت شک (submit یک فرم غیر جستجو) رد میشود.
- **محافظ SSRF (در egress):** egress خودش DNS را حل میکند و **همان IP بررسی‌شده** را وصل میکند، پس DNS rebinding ممکن نیست. هر redirect دوباره بررسی میشود.
  - **مسدود:**
    - loopback
    - link-local، از جمله metadata ‏`169.254.169.254`
    - RFC 1918، از جمله `10.10.1.0/24` و همسایه‌های production
    - CGNAT
    - IPv6 خصوصی، ULA و link-local
    - IPv4 جاسازی‌شده در IPv6
    - نام‌های تک‌بخشی و داخلی (`postgres`، `api`، `*.internal`…)
    - `/internal` هاب، با هر املایی
  - پورت‌ها فقط 80 و 443 هستند، مگر حساب سرویس پورت خودش را بدهد.
  - مرورگر هاب (`hq.coinepro.com`) را اصلاً باز نمیکند.
- **شبکه‌ها** (`compose-rules` و `make verify-live` اثباتشان میکنند):

  | شبکه | اعضا | نوع |
  |---|---|---|
  | `hq-egress` | egress، searxng | تنها شبکه‌ی ایجنت‌ها با راه به بیرون |
  | `hq-egress-api` | gateway، egress | internal |
  | `hq-browser` | egress، browser | internal؛ مرورگر فقط از proxy ‏egress بیرون میرود |

  egress به Postgres، Valkey، NATS، OpenBao، api و Temporal هیچ راهی ندارد. هیچ‌کدام از این سه سرویس پورت منتشرشده ندارد.
- **proxy ‏egress:**
  - `:3128` برای مرورگر، با credential جدا برای هر فراخوانی.
  - `:3129` برای gateway (MCP روی HTTP، با `EGRESS_PROXY_URL`). سربرگ‌های `X-HQ-Call`، `X-HQ-Tool` و `X-HQ-Class` میگیرد و entryها با `POST /v1/proxy/drain` جمع میشوند.
  - داخل tunnel‌های TLS باز نمیشود؛ فقط host، پورت، حجم و زمان ثبت میشود.
- **مرورگر:**
  - Chromium با Playwright 1.63.0. ایمیج رسمی با digest pin شده است.
  - برای هر فراخوانی یک context تازه (پروفایل خالی) ساخته میشود و بعد بسته میشود.
  - همزمانی: `BROWSER_MAX_SESSIONS` (full ‏۲، lean ‏۱).
  - سقف زمان هر فراخوانی ۱۵ ثانیه است (`EGRESS_BROWSE_S`؛ egress حداکثر ۲۰)، تا زیر مهلت ۳۰ ثانیه‌ی gateway بماند. کار بلندتر چند فراخوانی میشود.
  - اسکرین‌شات و دانلود فایل‌های شرکت خود ایجنت میشوند (`files.read`).
  - **sandbox خود Chromium روشن است (۷.۱ §۲.۲۰):** کاربر غیر root، فقط‌خواندنی، `cap_drop: ALL`، `no-new-privileges` و پروفایل seccomp خود Playwright (`infra/browser/seccomp_profile.json`، نسخه‌ی v1.63.0، hash آن در `compose-rules` pin شده). فقط `SYS_CHROOT` به bounding set اضافه شده، تا آن پروفایل chroot را درون user namespace خود Chromium اجازه دهد. uid 10001 بیرون از آن هرگز این capability را ندارد. اگر روزی `BROWSER_SANDBOX=0` شود، هر فراخوانی process مرورگر خودش را دارد. **هیچ process ‏`--no-sandbox` بین فراخوانی‌ها، و پس بین شرکت‌ها، مشترک نیست.**
  - heap جاوااسکریپت هر renderer سقف دارد (`BROWSER_JS_HEAP_MB`، ۱۹۲). WebRTC هیچ UDP بیرون از proxy نمیفرستد.
  - فایل‌های یک فراخوانی (اسکرین‌شات و دانلود) روی هم سقف دارند (`EGRESS_BROWSE_FILES_BYTES`، ۱۶ MiB). دانلود بزرگ‌تر از سقف `download_too_large` میگیرد و بی‌صدا بریده نمیشود. ورود ناموفق حساب `sign_in_failed` میگیرد.
- **SearXNG:** موتورهای عمومی پیش‌فرض، بدون لاگ query، بدون metrics، limiter خاموش (تنها مشتری egress است). `server.secret_key` از `SEARXNG_PASSWORD` در `.env` میاید (`make env` آن را میسازد).
- **سقف‌ها** (env سرویس api):

  | دامنه | متغیر | پیش‌فرض |
  |---|---|---|
  | هر اجرا | `EGRESS_RUN_REQUESTS` | 150 |
  | هر اجرا | `EGRESS_RUN_BYTES` | 64 MB |
  | هر اجرا | `EGRESS_RUN_BROWSER_S` | 300 ثانیه |
  | هر شرکت در روز مالک | `EGRESS_DAY_REQUESTS` | 5000 |
  | هر شرکت در روز مالک | `EGRESS_DAY_BYTES` | 2 GB |
  | هر فراخوانی | `EGRESS_CALL_BYTES` | 20 MB |

- **حساب‌های سرویس:**
  - متادیتا و policy تزریق در اپ ثبت میشوند (`POST /api/v1/tools/accounts`، با 🔏 `account.put` روی sha256 بدنه و `Idempotency-Key`؛ 7.1: site، قاعده‌ی allow یا port تازه کار رمز ذخیره‌شده را گسترش میدهد). policy تزریق یکی از این‌هاست: `bearer`، `header`، `basic` یا `cookie`، به‌علاوه‌ی روش ورود مرورگر و فهرست `allow` مسیرهای بی‌تعهد.
  - **رمز را فقط مالک، در ترمینال خودش، میگذارد:** `make account-secret KEY=<key>`. ورودی بی‌نمایش است و مستقیم در `kv/tools/accounts/<key>` میرود.
  - رمز برای هر فراخوانی یک بار از OpenBao خوانده میشود و از api به gateway و egress میرسد. **در لحظه‌ی خروج** و **فقط برای host خود آن حساب** گذاشته میشود.
  - رمز در هیچ نتیجه‌ای به مدل نمیرسد: همه‌ی نتیجه‌ها از هر شکل رمز (خام، percent-encoded، base64 با و بی padding، و `base64("user:secret")` سربرگ Basic) پاک میشوند، **پیش از** بریدن متن (۷.۱). فایلی که رمز را دارد دور انداخته میشود. در اسکرین‌شات هم فیلدهای رمز ماسک میشوند، و صفحه‌ای که خود رمز را نشان میدهد اسکرین‌شات نمیگیرد (`secret_on_page`). در لاگ هم نیست.
  - رمز **فقط روی https** گذاشته میشود. پورت‌های policy حساب فقط برای سایت خود حساب باز میشوند، نه برای جایی که redirect میفرستد.
- **تعهد با GET (۷.۱ §۲.۲۱):** پاسخ Google Form ‏(`formResponse`)، trigger وب‌هوک و اتوماسیون (IFTTT، Zapier، Make، n8n، Pipedream، Slack، Discord) و فراخوانی ارسال bot ‏(`/bot<token>/send…`) هم `needs_owner` میگیرند: در `http.request` و `web.read` (هر hop) و در `goto`، دانلود و هر درخواست مرورگر. «Submit»، «Continue»، «Confirm»، «Share»، «Delete»، «Promote»، «ثبت» و «تایید» هم برچسب تعهدند؛ «ي» و «ك» عربی نرمال میشوند؛ `select`ی که `onchange` آن فرم را میفرستد مثل submit سنجیده میشود.
- **متن پنهان** (`hidden`، `aria-hidden="true"`، style پنهان‌کننده) از صفحه‌ی خوانده‌شده حذف میشود. هر نتیجه‌ی وب `untrusted: true` دارد، مثل MCP.
- **`429 egress_limit`** سربرگ `Retry-After` دارد: تا روز بعد مالک وقتی سقف روزانه‌ی شرکت پر است، و ۳۶۰۰ ثانیه برای سقف خود اجرا. هر رزرو ردشده یک ردیف audit ‏(`egress.refused`) هم مینویسد.
- **هاب با IP خودش هم هاب است:** `hq.sh` آدرس‌های global میزبان و جواب DNS دامنه را در `HQ_HUB_ADDRESSES` میگذارد. `/internal` با آن‌ها هم رد میشود، و هر نامی که به آن‌ها resolve شود هم.
- **شکاف شبکه (۷.۱ §۲.۱۹، فقط دیده میشود):** `make verify-live` از داخل egress و SearXNG، همسایه‌ها (`10.10.1.1-3`)، metadata و آدرس‌های خود میزبان را با IP روی 80 و 443 میآزماید. محافظ egress همه را برای درخواست ایجنت رد میکند، ولی خود شبکه نه. هر چه جواب دهد یک خط `live: GAP ...` است، نه شکست. بستنش با قانون `DOCKER-USER` مالک است (کار اختیاری مالک). از یک کانتینر موقت روی bridge پیش‌فرض (۲۰۲۶-۱۰-۲۲): هر سه همسایه روی 80 و 443 و metadata روی 80 جواب دادند.
- **دیدن:**
  - `GET /api/v1/egress` با پارامترهای `company`، `since` و `blocked`.
  - `GET /api/v1/egress/summary` با `period=day`، `week` یا `month`.
  - ابزار `egress.recent` برای نقش‌های holding (ناظر، تحلیل‌گر امنیت، AI safety).
- **حافظه (پرامپت ۷ §۲.۹):** در کانتینرهای موقت با جستجو، خواندن و دو نشست مرورگر واقعی اندازه گرفته شد:

  | سرویس | بیکار | اوج |
  |---|---|---|
  | egress | ۵۴ MiB | ۷۳ MiB |
  | searxng | ۱۱۰ MiB | ۱۲۴ MiB |
  | browser | ۳۲۰ MiB | ۴۳۵ MiB با دو نشست |

  سقف‌ها:

  | پروفایل | egress | searxng | browser |
  |---|---|---|---|
  | full | 256m | 256m | 896m |
  | lean | 256m (۷.۱) | 160m | 480m، یک نشست |

  - برای جا شدنشان چند سقف دیگر، از روی مصرف زنده، پایین آمد (عددها در `profiles/*.env`):
    - full: postgres ‏1536←1024، prometheus ‏768←512، loki ‏512←384، tempo ‏384←256، nats ‏256←192. این همان جایی است که گزارش ۶ برای STT نام برده بود.
    - lean: postgres، valkey، nats، temporal، caddy، prometheus، loki، web، temporal-ui، node-exporter، llm-router، api، opa و gateway.
  - نتیجه: full ‏11536 از 11673، lean ‏5872 از 5886.
  - **egress در lean (۷.۱ §۲.۲۰):** با یک بدنه‌ی ۲۰ مگی و درخت lxml دوباره اندازه گرفته شد (کانتینر موقت سرویس واقعی، `memory.peak` cgroup، یعنی سرویس و childهای parse با هم؛ در lean یک child در هر لحظه، `EGRESS_PARSE_SLOTS=1`): بیکار ۵۵، صفحه‌ی ۲۰ مگی ۱۴۹ (child فقط ۴ MiB اول را parse میکند، `EGRESS_HTML_PARSE_BYTES`)، PDF بمب ۲۰۹، بدنه‌ی ۲۰ مگی http ‏۶۰، browse با ۱۶ MiB فایل ۱۲۲، و بدترین جفت هم‌زمان ۲۳۵ MiB. پس 128m ← 256m. جایش از llm-router ‏(192←128)، worker ‏(256←224) و web ‏(192←160) آمد. بیش از دو فراخوانی سنگین هم‌زمان (۲۵۸) را kernel با کشتن child parse جواب میدهد، نه خود سرویس. در full ‏(256m، دو child): دو صفحه‌ی ۲۰ مگی هم‌زمان ۲۶۱ و دو PDF بمب ۳۸۲ MiB؛ همان‌جا هم child کشته میشود و سرویس میماند (برای نگه داشتن هر دو، 384m یا `EGRESS_PARSE_SLOTS=1` لازم است؛ تصمیم بودجه‌ی full با پرامپت ۷.۱ §۰.۲ است).
  - full+stt حالا 1424 MiB بیشتر از بودجه است.

## ۲۰. پل MCP و کاتالوگ ابزار (پرامپت ۷ §۳، قرارداد §۱۸.۷)
- **اصل:** هیچ سرور MCP بدون دو مُهر مالک برای ایجنت‌ها وجود ندارد. پیش‌فرض هیچ سروری روشن نیست.
- **چرخه‌ی روشن شدن:**
  1. **ثبت** با `POST /api/v1/tools/mcp` و 🔏 `mcp.add` روی sha256 همان بدنه. بدنه این‌ها را دارد:
     - `key`
     - `title_fa`
     - `transport` (`http` یا `container`)
     - `url`
     - `tools`: هر ابزار با `name`، `class` (A0 تا A3) و `enabled`
     - `companies`: `"all"` یا فهرست کد شرکت‌ها
     - `auth_header` (اختیاری)

     ثبت دوباره‌ی همان `key` با بدنه‌ی دیگر یک نسخه‌ی تازه است و وضعیتش دوباره `pending` میشود. ثبت دوباره‌ی **همان بدنه** هیچ چیز را عوض نمیکند (سرور روشن، روشن میماند). اگر host عوض شود، رمز قبلی دیگر فرستاده نمیشود (`has_secret: false`) تا مالک دوباره `make mcp-secret` بزند (7.1). URL سرور `http` فقط روی پورت 443 است و نقطه‌ی آخر نام میزبان برداشته میشود.
  2. **رمز سرور، اگر دارد:** مالک خودش در ترمینال میزند `make mcp-secret KEY=<key>` (ورودی بی‌نمایش). رمز در OpenBao در `kv/hq-api/tools/mcp/<key>` میرود. API فقط `has_secret` را نشان میدهد، هیچ‌وقت خود مقدار را.
     - **کلید JSON چندخطی** (مثل service account گوگل): `make mcp-secret KEY=<key> FILE=<path>`. اسکریپت بررسی میکند که فایل یک شیء JSON است، متن آن را همان‌طور ذخیره میکند و بعد پیشنهاد میدهد فایل پاک شود (`shred -u`). خود اسکریپت چیزی پاک نمیکند.
  3. **روشن کردن** با `POST /api/v1/tools/mcp/<key>/enable` و 🔏 `mcp.enable` روی `key`. سرور `container` **هنوز اجراشدنی نیست** (شبکه‌ی `hq-mcp` و پل stdio→HTTP ساخته نشده‌اند): جواب `409 not_ready` است و `status_reason` همین را میگوید.
  4. **خاموش کردن** با `POST /api/v1/tools/mcp/<key>/disable`. فوری است و step-up نمیخواهد.

  هر سه POST `Idempotency-Key` میخواهند. کلید پیش از مصرف step-up گرفته میشود، پس تکرار همان درخواست همان جواب را با `Idempotent-Replay` میدهد.
- **سنجاق فهرست ابزارها:** اولین بار که Gateway بعد از enable سرور را صدا میزند، فهرست ابزارهای آن را ثبت و سنجاق میکند (`listing_sha256`). فهرست همه‌ی صفحه‌های `tools/list` است، بدون cache، و برای هر ابزار نام، `title`، توضیح، schema ورودی و خروجی و `annotations` را میگیرد؛ هر ابزار digest خودش را هم دارد.
  - اگر بعداً فهرست فرق کند (مثلاً سرور آپدیت شده)، سرور با دلیل `tools changed` **خاموش** میشود و یک کارت `tool_enable` در کارتابل هلدینگ میآید: `{key, listing_sha256, diff: {added, removed, changed}}`. مُهر این کارت (🔏 `decision.approve` روی ref) سرور را **دقیقاً با همان فهرست** روشن میکند. اگر فهرست پیش از مُهر دوباره عوض شود، کارت کنار میرود (`withdrawn`؛ تأییدش `409 decision_not_pending`) و کارت تازه میآید. ثبت دوباره، enable یا disable مالک هم کارت باز را کنار میگذارد.
  - اگر Gateway نتواند فهرست تازه را به api بگوید، فراخوانی اجرا نمیشود ولی آن را «فهرست عوض شده» گزارش نمیکند.
  - ابزاری که در ثبت مُهرشده نیست، یا `enabled: false` است، **همیشه** رد میشود.
- **`mcp.call` در Gateway:** ورودی `{server, tool, args}`.
  1. Gateway از api میپرسد (`POST /internal/v1/tools/mcp/resolve`): آیا سرور روشن است، برای شرکت همین ایجنت است، ابزار مُهر شده است، و سقف‌ها جا دارد. جواب api کلاس مُهرشده‌ی ابزار است.
  2. سیاست `hq.actions` روی **همان کلاس** تصمیم میگیرد. A2 فقط برای `ceo` و `manager` مجاز است (`a2_grants` در `infra/opa/policy/data.json`).
  3. **ابزار A3 بدون کارت تأییدشده اجرا نمیشود.** api یک تصمیم `a3_action` میسازد: `action: mcp_call`، `server`، `tool`، `args` و `preview` (فقط رمزها پوشانده میشوند؛ گیرنده و مبلغ دیده میشوند)، `args_sha256` و `registration_sha256`. تا کارت باز است، همان فراخوانی همان کارت را میگیرد.
     - **تأیید = دقیقاً یک اجرا (7.1):** کار پیگیری ساخته میشود؛ اولین فراخوانی یکسان (همان شرکت، سرور، ابزار، `args_sha256` و ثبت)، از هر run، تا ۲۴ ساعت بعد از مُهر، کارت را به‌صورت اتمی مصرف میکند (یک ردیف `approved` در `tools.mcp_calls` با `decision_id` یکتا) و اجرا میشود. `hq.actions` آن را با `approved_decision` میپذیرد؛ قفل شرکت همچنان جلویش را میگیرد. فراخوانی بعدی کارت تازه میخواهد.
     - کارت ردشده (یا برگشت‌خورده) در ۲۴ ساعت بعد ← `denied` (`policy_denied`)، بدون کارت تازه.
  4. خروجی سرور برچسب `source: "mcp"`، `untrusted: true` و `suspected_injection` (همان الگوهای وب) میگیرد و مثل همه‌ی خروجی‌ها ماسک میشود. فقط متن به مدل میرسد؛ عکس یا resource فقط نام میبرد (`omitted`).
  5. هر فراخوانی یک ردیف Audit دارد (`mcp.call`، کلاس واقعی، `ref: mcp:<server>/<tool>`) و یک ردیف `tools.mcp_calls`.
- **سقف‌ها:**
  - `HQ_MCP_CALLS_PER_RUN`، پیش‌فرض ۲۰
  - `HQ_MCP_CALLS_PER_COMPANY_DAY`، پیش‌فرض ۳۰۰ در هر روز مالک

  عبور از سقف ← `429 rate_limited` با `Retry-After`. شمارش برای هر شرکت قفل میشود (دو فراخوانی هم‌زمان از آخرین جا رد نمیشوند) و A3 هم سقف دارد.
  - **سرور `http` پیش از هر اتصال از `egress/reserve` رد میشود** (ابزار `mcp.call`، host سرور و همه‌ی رشته‌های args): کد کارمند یا داده‌ی داخلی ← `internal_data` بدون CONNECT؛ سقف egress تمام‌شده ← `egress_limit`. entryهای پراکسی همان رزرو را تسویه میکنند.
- **transport:**
  - **`http`:** فقط URL با https و نام میزبان عمومی؛ نه IP، نه نام داخلی، نه `hq.coinepro.com`، و بدون اعتبار داخل URL. Gateway آن را **فقط از پراکسی egress** میزند (`EGRESS_PROXY_URL` در env سرویس gateway). محافظ SSRF همان‌جا IP نهایی را چک میکند. بدون پراکسی، جواب `channel_not_configured` است و هرگز اتصال مستقیم برقرار نمیشود.
  - **`container`:** آدرس `http://mcp-<name>:<port>/...`. یک سرویس compose جدا روی شبکه‌ی internal ‏`hq-mcp`، که فقط با gateway مشترک است. سرورهای stdio پشت یک پل stdio→HTTP بازبینی‌شده اجرا میشوند. هیچ‌جا docker socket نیست.
  - این سرویس و شبکه **وقتی مالک اولین سرور container را مُهر کند** اضافه میشوند (با قاعده‌های `compose-rules`). الان هیچ‌کدام وجود ندارد: سرور `container` ثبت میشود ولی **هنوز اجراشدنی نیست** (enable ← `409 not_ready`؛ در کاتالوگ `channel_not_configured` با «هنوز اجراشدنی نیست»).
- **سرورهای پیشنهادی** (`apps/api/seed/mcp_proposals.yaml`؛ فقط پیشنهاد، هیچ‌کدام ثبت نشده):

  | key | سرور | ابزارها |
  |---|---|---|
  | `github-read` | GitHub رسمی، MIT | فقط‌خواندنی، A0 |
  | `search-console` | Google Search Console (یک سرور متن‌باز جامعه، در زمان مُهر بازبینی شود) | A0 |
  | `analytics` | Google Analytics، سرور خود Google، Apache-2.0 | A0 |
  | `time` | سرور مرجع MCP، MIT | A0، بدون شبکه |
  | `fetch` | سرور مرجع MCP، MIT | A0؛ با `web.read` هم‌پوشانی دارد |

  پیش از مُهر، نام ابزارها را با فهرستی که خود سرور میدهد تطبیق بده.
- **کاتالوگ:** `GET /api/v1/tools/catalog` (مالک) هر ابزار `agents/tools.md` و هر ابزار مُهرشده‌ی MCP را با این‌ها نشان میدهد: کلاس (`A0/A2` یعنی کلاس هر فراخوانی جدا تعیین میشود؛ `per tool` یعنی از ثبت سرور میاید)، نقش‌هایی که در منشورشان دارند، و وضعیت:
  - `live`
  - `off`: هنوز در این build ساخته نشده
  - `channel_not_configured`: مثل `github.read` تا توکن مالک
  - `pending`

  فهرست ابزارهای ساخته‌شده‌ی Gateway در `hq_common.tool_status` است. تست Gateway آن را با جدول خودش یکی نگه میدارد.
- **`files.read`** (`agents/tools.md` v2): `variant` اختیاری است: `original`، `thumb` یا `poster`.
  - عکس: نسخه‌ی `agent` آن (≤ ۱۵۶۸ پیکسل، بدون EXIF) به مدل میرسد.
  - PDF: متنش هنگام آپلود با pypdf 6.21.1 (BSD-3) استخراج میشود؛ تا ۲۰۰ صفحه، ۲۰۰ هزار نویسه و ۳۰ ثانیه. متن در `files.processing.text` میماند و در meta ایجنت ماسک‌شده برمیگردد. PDF اسکن‌شده، رمزدار یا خراب متن ندارد و آپلودش هم شکست نمیخورد.

## ۲۱. ناظر کل: پروتکل‌ها، یافته‌ها، hold و حالت نگهبان (پرامپت ۸ §۲، قرارداد §۱۸.۱)
- **پروتکل‌ها:** پروتکل‌های `agents/protocols/oversight.yaml` (۵۲ پروتکل پرامپت ۸ در ۱۱ حوزه، به‌علاوه‌ی پروتکل‌های پرامپت‌های ۱۰ تا ۱۲) seed میشوند. seed فقط ref تازه را اضافه میکند و نسخه‌های بعدی را هرگز بازنویسی نمیکند؛ هم مرحله‌ی seed این کار را میکند و هم worker در `reconcile_schedules` (چون api-migrate پوشه‌ی agents را ندارد).
  - هر نسخه یک ردیف تازه است و ردیف‌ها append-only‌اند. ویرایش، توقف (paused) یا ادامه یک نسخه‌ی تازه میسازد.
  - راه‌های ساختن نسخه: `POST/PUT /oversight/protocols` با 🔏 (`oversight.protocol`، روی هش بدنه)، یا تصمیم `protocol` که ناظر پیشنهاد میدهد و مالک با step-up مُهر میکند.
  - **پروتکل `paused`** (قرارداد §۱۸.۱ v1.4.4): فیلد `status: paused` در yaml یعنی قابلیتی که میسنجد هنوز ساخته یا روشن نشده (مثل PR-043، PR-053، PR-082، PR-090 و پروتکل‌های پرامپت‌های ۱۰ تا ۱۲). چنین پروتکلی **هیچ schedule ندارد** (`reconcile_schedules` schedule مانده از قبل را هم پاک میکند)، اجرا نمیشود (`protocol_run` ردیف اجرا نمیسازد)، یافته نمیسازد و در نمره‌ی انطباق حساب نمیشود (اجراهای قبلی پروتکلی که الان paused است هم کنار میروند). پرامپتی که قابلیت را میسازد، آن را با migration داده و Audit فعال میکند.
- **زمان‌بندی:** فقط هر پروتکل `active` یک Temporal schedule دارد (`protocol-PR-001`، تقویم RRULE در منطقه‌ی زمانی مالک) که workflow ‏`ProtocolRun` را اجرا میکند. schedule ‏`hq-oversight-weekly` (شنبه ۰۷:۰۰ تهران) برای هر شرکتی که چالش هفته ندارد کار صدور چالش به ناظر میدهد. `HQ_OVERSIGHT_SCHEDULES=off` همه را paused نگه میدارد (تست‌ها).
- **اول قاعده:** ۲۳ پروتکل `rule` و `reconcile` با **کد** و بدون مدل اجرا میشوند: PR-010, 011, 012, 014, 015, 022, 024, 030, 033, 034, 050, 051, 052, 054, 060, 062, 070, 071, 072, 073, 080, 097, 099. هر مشکل یک یافته است. یافته‌ی باز با همان کلید دوباره ساخته نمیشود.
  - PR-034، PR-051 و PR-080 جدول‌های forkهای دیگر را میخوانند و تا ساخته نشده‌اند «هنوز ساخته نشده» گزارش میدهند.
  - **بیدار شدن ناظر:** پروتکل کدی که پاس شد ناظر را بیدار نمیکند. فقط رد (یافته‌ی تازه) یا آنچه کد نتوانست تصمیم بگیرد (`unclear`) ناظر را بیدار میکند، با همان شاهدی که کد جمع کرده (نه کل رکوردها)؛ روزی یک بار برای هر پروتکل و داخل سهم نظارت. رد را کد ثبت کرده و ناظر فقط آن را برای پاسخ‌گو بیان میکند. اجرای مبهم `pending` میماند تا ناظر با `protocol.result` تمامش کند.
  - بقیه‌ی پروتکل‌ها (`sample`، `llm`، `blind_test`، `mystery`، و `rule`/`reconcile` بی‌checker) کار ناظر یا QC میشوند. سقف: `HQ_OVERSIGHT_MODEL_RUNS_PER_DAY` (پیش‌فرض ۳ در روز مالک) و بودجه‌ی هر اجرا `HQ_OVERSIGHT_RUN_TOKENS` (پیش‌فرض ۶۰ هزار، **هرگز بیشتر از `tokens_per_run` منشور مجری**: ناظر v2 و مشاور v3 هر کدام ۲۰۰ هزار). بیرون از سقف، اجرا `skipped` ثبت میشود. هر پروتکل حداکثر یک بار در روز به مدل میرود (پروتکل ساعتی هم)، و PR-098 فقط وقتی که مدیرعاملی در ۲۴ ساعت گذشته استخدامی تأیید کرده باشد.
  - **سهم توکن نظارت، `OVERSIGHT_DAILY_SHARE`** (در `.env`، پیش‌فرض `0.2`؛ قرارداد §۱۸.۱ v1.4.4): ناظر و QC روی هم حداکثر این سهم از `AGENT_DAILY_TOKEN_CAP` را در روز UTC مصرف میکنند (با ۶۰۰ هزار: ۱۲۰ هزار). LLM Router آن را مثل بودجه اجرا میکند: وقتی مصرف امروز نقش‌های `overseer` و `inspector` هلدینگ به سهم رسید، هر فراخوانی بعدی آن‌ها با `429 budget_exhausted` (در دفتر: `rejected_budget` / `oversight_share`) رد میشود، در هر اولویتی. فقط اجرای پروتکل `critical` ادامه میدهد (runner شماره و شدت پروتکل را در meta فراخوانی میفرستد).
    - وقتی سهم پر است، اجرای پروتکل غیر `critical` نتیجه‌ی **`deferred`** میگیرد (کاری ساخته نمیشود). deferred رد نیست و در نمره‌ی انطباق حساب نمیشود. روز بعد (UTC)، اولین `oversight_tick` پروتکل‌های deferred را **اول صف** دوباره اجرا میکند: اول شدیدترها، بعد قدیمی‌ترها.
    - `AGENT_DAILY_TOKEN_CAP=0` یعنی «هیچ» (پرامپت ۸.۱): هیچ اجرای ایجنتی نیست و سهم نظارت هم صفر است. `OVERSIGHT_DAILY_SHARE=0` یعنی فقط پروتکل‌های `critical`. مقدار باید بین ۰ و ۱ باشد، وگرنه سرویس بالا نمیاید.
  - **برآورد مصرف:** حداکثر ۳ × ۶۰ هزار = ۱۸۰ هزار توکن در روز، به‌علاوه‌ی صدور چالش‌های هفتگی (۶۰ هزار در هفته) و پیام‌های مالک در رشته‌ی `N`؛ سهم نظارت (۱۲۰ هزار با سقف فعلی) زودتر جلوی آن را میگیرد. منشور ناظر v2 سقف هر اجرا را ۲۰۰ هزار گذاشته و هیچ اجرایی از آن نمیگذرد، حتی اگر `HQ_OVERSIGHT_RUN_TOKENS` بیشتر باشد.
- **یافته:** پاسخ‌گو (نقش پروتکل در همان شرکت، وگرنه مدیرعامل، وگرنه مالک) وضعیت را `acknowledged`، `fixing`، `fixed` یا `disputed` میکند؛ `fixed` شاهد میخواهد. `verified` فقط با شاهد رفع است و فقط با ناظر یا مالک؛ `closed` هم همین‌طور. مالک: `POST /oversight/findings/{ref}/status`.
- **hold:** هر hold یک ردیف `H-` روی یک هدف است و هر هدف فقط یک hold باز دارد. هدف‌ها و آنچه متوقف میشود:
  - `decision`: کارت تأیید نمیشود (`423 held`) و effect تأییدشده صبر میکند.
  - `employee`: آن ایجنت فقط میخواند و هر ابزار A1 به بالا `held` میگیرد.
  - `tool` (`EMP:tool`): همان ابزار اجرا نمیشود، حتی خواندنی.
  - `work`: همه‌ی اقدام‌های اجرای آن کار.
  - `session`: سشن کارگاه شروع نمیشود و پیام نمیگیرد.
  - `story`: برای fork استوری‌ها (`oversight.held`).

  **آزادسازی فقط با مالک است:** `POST /oversight/holds/{ref}/release` با 🔏 (`oversight.release`، هدف ref)، یا `/cancel` بدون step-up. هیچ مسیر agent برای این کار وجود ندارد.
- **کلید توقف و فریز:** ناظر کلید توقف هر شرکت را میزند (`kill_switch.engage`) و deploy هر شرکت را فریز میکند (`deploy.freeze`). باز کردن هر دو فقط با مالک است. ناظر هرگز تصمیم را تأیید نمیکند (`/internal/v1/decisions/{ref}/approve` ← 403).
- **حالت نگهبان:** هر ۵ دقیقه در Maintenance (`oversight_tick`) ارزیابی میشود. روشن میشود در این حالت‌ها:
  - خلوت روشن است.
  - مالک `owner.settings.watch_after_hours` ساعت (پیش‌فرض ۶، در `PUT /owner/settings`) هیچ کاری نکرده است.
  - مالک با `POST /oversight/watch {on}` دستور داده است (افزوده).

  در این حالت هر کارت پرریسک (ریسک high، کلاس A3، یا hire، dismissal، budget_change، code_session، deploy، protocol) خودکار hold میشود. گزارش «در نبودت» را کد میسازد و هر ساعت تازه میکند (PR-097). با برگشت مالک، حالت نگهبان بسته میشود.
- **دستور دائمی:** مالک `POST /oversight/orders` میفرستد (متن یا ویس) که `proposed` میماند. بعد از seal با 🔏 (`oversight.order`، هدف ref)، دستور بعد از منشور در system prompt ناظر میاید (`applies_to: all` یعنی در prompt همه). retire آن را برمیدارد. ابزاری برای پیش‌نویس دستور به دست ایجنت وجود ندارد.
- **چالش و انطباق:** چالش را ناظر صادر میکند، مدیرعامل همان شرکت تحویل میدهد، و ناظر یا QC نمره میدهد. چالش دیرکرده `missed` میشود. انطباق برای هر شرکت روزانه در `oversight.compliance` ثبت میشود. فرمول: میانگین نمره‌ی حوزه‌ها (سهم پاس‌شده‌ها در ۷ روز)، منهای یافته‌های باز (بحرانی ۲۵، جدی ۱۰، متوسط ۴، کم ۱)، منهای ۲ برای هر پرسش رسمی دیرکرده.
- stream روی topic ‏`oversight`: `oversight.finding`، `oversight.hold`، `oversight.watch`.

## ۲۲. پرسش رسمی، مشاور v2 و دستیار شخصی (پرامپت ۸ §۳ و §۵، قرارداد §۱۸.۲ و §۱۸.۳)
- **پرسش رسمی (`Q-…`):**
  - چه کسی میپرسد:
    - ناظر کل و مشاور کل از هر کسی.
    - مدیرعامل فقط داخل شرکت خودش.
    - بقیه نمیپرسند (OPA ‏`inquiry.ask`).
  - پرسش یک ردیف در `oversight.inquiries` (شرکتِ پرسش‌گیرنده) است، به‌علاوه‌ی یک کار با **P1** برای پرسش‌گیرنده. P1 بالاتر از کار عادی است، و پرسش در brief همان کار میاید.
  - جواب با `inquiry.answer` میرسد و در رشته‌ی پرسنده مینشیند (`A`، `N` یا رشته‌ی مدیرعامل)، با `links.inquiry` و شاهدها. کار مربوط هم بسته میشود.
  - **پرسش رتبه‌ی ۲ باید جواب بگیرد.** کارش را نمیشود fail یا decline کرد (`409`).
  - **دیرکرد:** گام `inquiries_late` در Maintenance (هر ۵ دقیقه) پرسش گذشته از مهلت را `late` میکند، یک بار اعلان 🟡 برای مالک میدهد و رویداد `inquiry.late` میفرستد. پرسش دیرکرده هنوز جواب‌پذیر است.
  - اثر دیرکرد در انطباق شرکت (پروتکل `PR-051`) را بخش ناظر حساب میکند، از روی ردیف‌های `late`.
  - مالک همه‌ی پرسش‌ها را در `GET /api/v1/inquiries` میبیند (`?from&to&status`). topic ‏stream: ‏`inquiries`.
- **مشاور v2:** ابزارهای خواندنی منشورش زنده‌اند:
  - `files.read`، `github.read`، `backups.status`، وب و MCP
  - `workshop.read`: سشن و رویدادهایش. مشاور و ناظر سشن‌های هر شرکت را میخوانند و هیچ‌کدام را هدایت نمیکنند.
- **دستیار شخصی:**
  - **ساخت errand:** هر پیام مالک در رشته‌ی `P` یک errand (`E-…`) باز میکند. اگر پیام `links.errand` یک errand باز را داشته باشد، ادامه‌ی همان است. `POST /api/v1/errands` هم همان پیام را در `P` میگذارد. پیام دستیار را بیدار میکند و errand در context اجرایش میاید.
  - **پیشبرد:** دستیار گام‌ها را با `errand.step` ثبت میکند، با `errand.finish` تمام میکند (نتیجه در `P` میاید) و یادآوری را با `planner.add` میگذارد (`PL-…`).
  - **یادآوری‌ها:** در `GET /planner?scope=owner` با `kind: "reminder"` میایند. هیچ‌کس را بیدار یا escalate نمیکنند.
  - **تعهد بیرونی:** پرداخت، خرید، رزرو، ثبت‌نام، ارسال و تغییر امنیت حساب تصمیم `errand_action` (A3، مُهر مالک با step-up) است. errand تا تصمیم مالک `waiting_owner` میماند.
    - **تأییدشده:** errand ادامه پیدا میکند و دستیار یک کار پیگیری میگیرد.
    - **حتی پس از مُهر،** هیچ ایجنتی تعهد را انجام نمیدهد (Gateway تعهد را رد میکند). آخرین قدم با خود مالک است.
  - **مصرف هر errand** از دفتر خزانه، از روی اجراهای همان errand، حساب میشود. topic ‏stream: ‏`errands`.
## ۲۳. ستاره‌ها، درس‌ها، استخدام با مدیرعامل‌ها و استوری‌ها (پرامپت ۸ §۴، §۸ و §۹؛ قرارداد §۱۸.۴، §۱۸.۱۱ و §۱۸.۱۲)
- **ستاره‌ها:**
  - مدیرعامل هر شرکت آیین‌نامه‌اش را با `star.rubric` مینویسد. هر تغییر یک نسخه‌ی تازه است و همیشه آخرین نسخه فعال است.
  - وزن‌ها با هم ۱۰۰ میشوند و معیار `efficiency` باید دست‌کم ۱۵٪ وزن داشته باشد، وگرنه `422`.
  - ستاره‌ی هر هفته را با `star.give` به کارمندهای شرکت خودش میدهد: ۰ تا ۵ با گام نیم، با هفته‌ی شنبه تا جمعه به وقت مالک.
  - ستاره‌ای که دلیل یا شاهد ندارد نگه داشته میشود ولی `counted=false` است. ناظر کل با `star.audit` میتواند ستاره‌ای را از شمارش بیرون ببرد. هفته‌ای که برآیندش بسته شده دیگر ستاره نمیگیرد (`409`).
  - مالک ستاره نمیدهد؛ امتیاز ۱ تا ۱۰ مالک جدا میماند.
- **زمان‌بندی** (Temporal، به وقت مالک):

  | Schedule | زمان | کار |
  |---|---|---|
  | `hq-stars-reminder` | جمعه ۱۸:۰۰ | برای هر مدیرعامل یک کار «ستاره‌های هفته» (هر هفته یک بار) |
  | `hq-stars-rollup` | هر روز ۰۸:۰۰ | شنبه‌ها برآیند هفته‌ای که تمام شد؛ اولِ هر ماه شمسی برآیند ماه گذشته (هر دوره یک بار) |

- **امتیاز شرکت** (`domain/stars.py`، تابع‌های خالص و تست‌شده):
  - ۳۵٪ KPI + ۲۰٪ چالش‌های ناظر + ۱۵٪ انطباق + ۱۵٪ میانگین ستاره‌ی کارمندها (×۲۰) + ۱۵٪ کارایی. ستاره‌ی شرکت = امتیاز ÷ ۲۰.
  - بخشی که داده ندارد کنار گذاشته میشود و وزن بقیه دوباره تقسیم میشود. KPI فعلاً ذخیره‌گاهی ندارد و چالش و انطباق از جدول‌های ناظر میایند (وقتی هستند).
- **کارایی** (فقط از دفتر خزانه، هرگز از گزارش ایجنت):
  - **شرکت:**
    - ۴۰٪ ماندن در پاکت ماه: داخل پاکت ۱۰۰، بیرون از آن ۰
    - ۳۰٪ هدررفت: سهم توکنِ اجراهای شکست‌خورده یا ردشده و کارهایی که تحویل نشدند
    - ۳۰٪ هزینه‌ی هر خروجی پذیرفته‌شده (امتیاز مالک ≥ ۶) نسبت به میانه‌ی هلدینگ
  - **کارمند:**
    - ۵۰٪ توکن هر خروجی پذیرفته‌شده نسبت به میانه‌ی دپارتمانش
    - ۲۵٪ سهم اجراهای شکست‌خورده
    - ۲۵٪ دقت برآورد: مصرف ماه تا امروز در ±۲۵٪ برآورد استخدام، به نسبت روزهای گذشته، ۱۰۰ است و بعد به‌طور خطی تا ۰ در ±۱۰۰٪
- **تورم:** اگر بیش از ۷۰٪ ستاره‌های شمرده‌شده‌ی یک شرکت در یک دوره پنج باشد (دست‌کم ۳ ستاره)، یک خط `report` برای مالک ساخته میشود. وقتی جدول یافته‌های ناظر وصل شود، به یافته تبدیل میشود (`stars.star_inflation`).
- **درس‌ها:**
  - ناظر کل یا مدیر عملیات AI با `lesson.write` درس شرکت برتر را مینویسد (`L-0001`).
  - مدیرعامل هر شرکت دیگر یک کار «پیشنهاد به‌کارگیری درس» میگیرد. جوابش یک تصمیم `lesson_adoption` است (`{lesson, adopt, plan_md}`) که مالک تصمیمش را میگیرد.
  - نتیجه در `adoption` درس است: `proposed`، `adopted` یا `rejected`.
- **API مالک:** `GET /stars/rubrics` و `/stars/rubrics/{company}`، `GET /stars`، `GET /stars/rollup?period=week|month&key`، `GET /lessons`. رویداد `stars.rollup` روی topic ‏`stars` میرود.
- **استخدام با مدیرعامل‌ها (`delegated`):**
  - **شروع:** `POST /owner/hiring/start {mode: "delegated"}` 🔏. هر شرکت عملیاتی فعال باید پاکت ماهانه داشته باشد (`/budgets`، scope ‏`company`، period ‏`month`)، وگرنه `422 envelope_required` با نام شرکت‌ها، پیش از مصرف step-up.
  - **کارت‌ها:** کارت `hire` ایجنتِ یک شرکت عملیاتی `approver` = مدیرعامل همان شرکت میگیرد، به‌علاوه‌ی یک کار «تصمیم درباره‌ی D-…» برای او. کارت هلدینگ و کارتی که مالک خودش مینویسد با مالک میماند. مالک هر کارتی را میتواند زودتر تصمیم بگیرد.
  - **کارتابل مالک:** `GET /decisions` به‌طور پیش‌فرض فقط کارت‌های خود مالک را نشان میدهد (`?approver=all` همه را). `decisions_pending` در صندوق هم فقط کارت‌های مالک را میشمارد.
  - **ابزار `hire.decide`** (A2، فقط مدیرعامل همان شرکت و فقط کارت‌هایی که approver آن‌هاست): `approve`، `reject` یا `return`.
  - **بررسی‌های سخت هر تأیید**، هر کس تأیید کند، در همان تراکنش:
    - منشور جور است
    - مدل را یک اتصال `enabled` میدهد
    - برآورد ماهانه هست و دست‌کم `tokens_per_run` منشور است
    - تعهد ماه به‌علاوه‌ی برآورد ≤ پاکت، وگرنه `409 envelope_exceeded`
    - کلید توقف شرکت آزاد است (`423`)
    - حداکثر ۵ استخدام در روز برای هر شرکت (`429`)

    شکست هیچ کارمندی نمیسازد.
  - **بعد از استخدام:** هر استخدام یک استوری `hire` دارد. استخدامی که مدیرعامل تصمیمش را گرفته این‌ها را هم دارد: دوره‌ی آزمایشی ۷ روزه (`probation_until`)، یک اعلان `report` برای بسته‌ی مالک (هرگز push فوری)، و یک کار بازبینی ۲۴ ساعته برای `HQ-OVR` (پروتکل PR-098).
  - **برگرداندن:** از صفحه‌ی کارمند یا استوری، `POST /employees/{code}/dismiss` 🔏.
- **استوری‌ها** (`owner.stories`، `ST-000001`؛ ۲۴ ساعت زنده، بعد آرشیو؛ **هرگز push**):
  - **سیستمی** (یک بار برای هر رویداد، `event_key`): `hire`؛ `deliverable` (امتیاز ۹ یا ۱۰ مالک)؛ `stars` (شرکت برتر هفته و بهترین کارمندش). استوری `milestone` سیستمی منتظر یک ذخیره‌گاه KPI است.
  - **مدیرعامل‌ها و رئیس‌های هلدینگ** (`story.post`، A1):
    - حداکثر ۳ در روز برای هر شرکت (`429 story_limit`)
    - متن ماسک میشود
    - عکس فقط از فایل‌های خود شرکت (`403`)
    - بدون لینک بیرونی (`422`)
    - `milestone` شاهد میخواهد: یک کار، یک خروجی یا یک عدد (`422`)
  - **API:** `GET /stories` (حلقه‌ها: نادیده‌ها اول، بعد تازه‌ترها؛ آیتم‌ها از قدیم به جدید)، `GET /stories/archive?company&cursor`، `POST /stories/seen {refs}`، `POST /stories/{ref}/welcome` (فقط `hire`، وگرنه `422`؛ مدیرعامل و مدیر کارمند پیامش را در thread میبینند). رویداد `story.created` روی topic ‏`stories` میرود.
## ۲۴. کتابخانه‌ی مهارت و آکادمی هلدینگ (پرامپت ۸ §۶ و §۷، قرارداد §۱۸.۵ و §۱۸.۶)
- **داده:** `knowledge.skills` و `knowledge.skill_versions`، به‌علاوه‌ی `academy.curricula`، `eval_suites`، `eval_runs`، `teachings` و `addenda` (migration ‏0022؛ مال هلدینگ، با RLS). متن هر نسخه هرگز عوض نمیشود و هر تغییر یک نسخه‌ی تازه است.
- **seed:** `api-migrate` پوشه‌ی `agents/` را فقط‌خواندنی میخواند:
  - مهارت‌های `agents/skills` با همان نسخه‌ی فایلشان و در وضعیت `in_review` وارد میشوند.
  - برنامه‌ها و آزمون‌ها از `agents/academy` میایند.
  - هیچ مهارتی بی‌صدا فعال نمیشود، seedها هم نه: هر کدام بررسی ناظر، آزمون و مُهر مالک میخواهد.
- **چرخه‌ی مهارت:**
  1. مالک مهارت را میسازد با `POST /skills` (متن، متن ویس از `/transcribe`، یا متن PDF) یا یک نسخه‌ی تازه با `PUT`.
  2. **پیش‌بررسی کد**، پیش از اینکه هر مدلی متن را بخواند. این‌ها را رد میکند:
     - دستور «دستورهای قبلی را نادیده بگیر»، به فارسی و انگلیسی
     - رمز یا داده‌ی شخصی (همان ماسک `hq_common.redact`)
     - عبارت‌هایی که اختیار میدهند
     - نام ابزاری که در منشور نقش‌های دامنه نیست

     متن ردشده با بررسی `reject` از طرف `skills-precheck` ذخیره میشود و برای ناظر نمیرود.
  3. **ناظر** با یک کار «Review skill SK-…@N» بیدار میشود و `skill.review` میدهد. AI Safety هم این ابزار را دارد.
  4. pass ← **آزمون آکادمی**. قبولی ← `approved`؛ رد ← `rejected` با گزارش.
  5. **مُهر مالک:** `POST /skills/{ref}/activate` 🔏 با هدف `ref@version`. فقط بعد از pass بررسی و قبولی در آزمون انجام میشود، و خط پایه‌ی آزمون بالا میرود.
  6. خارج کردن: `/retire`، بدون step-up.
- **در اجرا:** مهارت‌های فعال نقش (بر اساس نقش، شرکت و دپارتمان؛ تا ۱۶٬۰۰۰ نویسه) و قاعده‌های مُهرشده‌ی مالک برای آن نقش بعد از منشور در system prompt میایند. هر اجرا `agents.runs.skills` را پر میکند، و `llm.calls.meta` هم `skills` و `addenda` میگیرد.
- **آزمون** (workflow ‏`EvalRun` روی worker، یک بار و بدون retry):
  - هر مورد را نقشِ زیر آزمون جواب میدهد: منشور، به‌علاوه‌ی مهارت یا قاعده‌ی زیر آزمون، روی مدل خودش یا مدلی که آزموده میشود. کلاس کار `academy_eval` است.
  - داور (`academy_judge`) با rubric از ۰ تا ۱۰ نمره میدهد:
    - داور: `ACADEMY_JUDGE_MODEL`، پیش‌فرض `claude-haiku-5-5`
    - برای مورد حساس، مدل QC: `ACADEMY_QC_MODEL`
  - **دروازه:** نمره‌ی وزن‌دار ۰ تا ۱۰۰ باید ≥ خط پایه − ۱ باشد. اگر خط پایه هنوز نیست، اولین اجرا آن را میسازد.
  - همه‌ی فراخوانی‌ها در خزانه ثبت میشوند.
  - مدیر عملیات AI با `eval.run` آزمون دستی اجرا میکند. نتیجه‌ی آزمون دستی چیزی را فعال نمیکند.
- **سقف ماهانه:** `ACADEMY_BUDGET_SHARE` (پیش‌فرض ۰٫۰۵) از جمع پاکت ماهانه‌ی شرکت‌ها. اگر پاکتی تعریف نشده باشد، `ACADEMY_MONTHLY_TOKENS` (۱٬۰۰۰٬۰۰۰).
  - با ۸۰٪ مصرف، یک اعلان `report` در ماه میاید.
  - با پر شدن سقف، آزمون تازه `409 academy_budget` میگیرد.
  - مصرف و سقف: `GET /academy/budget`.
- **آموزش مالک:**
  1. مالک: `POST /academy/teach` (متن یا ویس؛ هدف یک نقش یا یک کارمند).
  2. مدیر عملیات AI بیدار میشود و `teach.draft` میدهد، با یکی از این نوع‌ها: `charter_rule`، `skill`، `memory`، `playbook`. پیش‌بررسی کد روی همین پیشنهاد اجرا میشود.
  3. ناظر: `skill.review` با ref ‏`TE-…`.
  4. آزمون (برای `memory` نیست).
  5. **تأیید مالک:** `POST /academy/teach/{ref}/approve` 🔏 با هدف ref. نتیجه:
     - `charter_rule`: قاعده‌ی مُهرشده بعد از منشور نقش (`academy.addenda`). **`agents/` هرگز ویرایش نمیشود.**
     - `skill` و `playbook`: مهارت فعال تازه برای آن نقش.
     - `memory`: یادداشت در حافظه‌ی همان کارمند.

  رد: `/reject`.
- **کارنامه:** `GET /academy/records/{employee}`. شامل نسخه‌ی منشور، نسخه‌ی برنامه‌ی آموزشی، مهارت‌های فعال، قاعده‌های مُهرشده، آزمون‌ها با روند نمره و درس‌ها (وقتی `knowledge.lessons` هست).
- **رویدادها:** `skill.updated` روی topic ‏`skills`؛ `academy.eval` و `academy.teaching` روی topic ‏`academy`.
## ۲۵. ساخت سرور شرکت تازه: provisioner (پرامپت ۹ §۱ و §۴، قرارداد §۱۸.۸)
- **provisioner کد است، نه ایجنت** (`services/provisioner`، کتابخانه‌ی رسمی `hcloud` ‏2.27، MIT).
  - فقط طرحی را اجرا میکند که مالک **مُهر کرده**، دقیقاً همان را. digest طرح را پیش از هر فراخوان هتزنر دوباره حساب میکند (`hq_common.provisioning`). طرحی که بعد از مُهر عوض شده باشد اجرا نمیشود.
  - فقط منابعی را تغییر میدهد که **خودش** با برچسب `managed-by=coinepro-hq` ساخته است:
    - سرورها، فایروال‌ها و شبکه‌های موجود (هاب و همسایه‌های production) دست نمیخورند.
    - کلیدی که مالک خودش پیش‌تر در پروژه گذاشته، همان‌طور به کار میرود.
  - **حذف، بازسازی، خاموش کردن و rescue در کدش وجود ندارد.** این کارها فقط در کنسول هتزنر و به دست مالک است.
  - **رمز root ساخته نمیشود:** کلید عمومی مالک همیشه داده میشود. اگر هتزنر رمزی برگرداند، اجرا متوقف میشود و آن رمز هیچ‌جا نمیماند.
- **پروفایل اختیاری `provisioning`:**
  - خاموش است تا مالک آن را روشن کند: `HQ_PROVISIONING=on` در `.env`، بعد `make bootstrap` (یک بار، برای AppRole) و `make up`.
  - `hq.sh` فقط وقتی روشن است `PROVISIONER_URL` را به api میدهد.
  - حافظه: 128m در full و 96m در lean (۴۳ MiB بیکار). ‏full+provisioning برابر 11728 از 12288 است و lean+provisioning ‏5968 از 6196.
- **شبکه:**
  - `hq-prov` شبکه‌ی internal است، با provisioner و api (endpointهای داخلی) و OpenBao (AppRole محدود به 172.30.10.0/24).
  - `hq-prov-out` هم internal است، فقط provisioner و egress. تنها راه بیرون، listener ‏`:3130` روی egress است: فقط CONNECT، فقط `api.hetzner.cloud:443`، با همان محافظ SSRF.
  - provisioner **هیچ‌وقت به سرور تازه SSH نمیزند**؛ مسیری هم به آن ندارد.
  - `make verify-live` این‌ها را میسنجد (وقتی پروفایل روشن است).
- **کار خود مالک، در ترمینال SSH خودش:**
  1. `make hetzner-token`:
     - توکن API پروژه‌ی هتزنر (Read & Write)، با ورودی نامرئی.
     - پیش از ذخیره، یک بررسی فقط‌خواندنی با هتزنر انجام میشود.
     - توکن در `kv/provisioning/hetzner` ذخیره میشود. فقط provisioner آن را میخواند و فقط در لحظه‌ی کار.
  2. `make owner-ssh-key`:
     - یک کلید **عمومی** SSH. چند کلید هم مجاز است. کلید خصوصی رد میشود.
     - کلیدها در `kv/provisioning/ssh-keys` ذخیره میشوند.
     - کار‌بر کاری سرور تازه همین کلیدها را میگیرد.
  - تا این دو انجام نشده‌اند، `/v1/pricing` و ساخت جواب `channel_not_configured` میدهند.
  - **IPهای مجاز SSH** را مالک در طرح تعیین میکند. SSH باز به کل اینترنت (`0.0.0.0/0` روی 22) پذیرفته نمیشود.
    - ⟨۹.۲⟩ هر بازه‌ی tcp که ۲۲ را شامل شود SSH است، و منبع‌هایش باید **درون** `provision_ssh_sources` مالک باشند (تا تنظیم نشده‌اند، هیچ طرحی با SSH مُهر نمیشود).
    - منبع‌هایی که روی هم کل فضای IPv4 یا IPv6 را میپوشانند (مثلاً `0.0.0.0/1` و `128.0.0.0/1`) فقط روی 80 و 443 مجازند.
- **گام‌ها** (هر کدام با لاگ کوتاه به api، و قابل ادامه):
  1. `ssh-key`
  2. `firewall`: یک Hetzner Cloud Firewall تازه، دقیقاً با قاعده‌های طرح. اگر طرح شبکه‌ی خصوصی بخواهد، شبکه‌ی **خود شرکت** (`10.20.0.0/16`) هم ساخته میشود. به شبکه‌ی موجود هاب وصل نمیشود، چون آن تغییر شبکه‌ی production است و با مالک است.
  3. `server`: Ubuntu 24.04، کلید مالک، `user_data`.
  4. `boot`
  5. `cloud-init`: انتظار برای فراخوان یک‌بارمصرف سرور، حداکثر ۶۰ دقیقه.
  6. `verify`: نسخه‌ها و نتیجه‌ی هر گام.
  7. `login`: `ssh <work_user>@<ipv4>` و بعد `claude`.

  رفتار در خطا:
  - گامی که شکست بخورد گزارش میشود. api دوباره اجرایش میکند؛ گام‌های تمام‌شده تکرار نمیشوند و چیزی دو بار ساخته نمیشود.
  - سروری که ساخته شده بود و بعد در کنسول حذف شد، دوباره ساخته نمیشود (`server_gone`). سرور تازه یعنی یک طرح مُهرشده‌ی تازه.
  - ⟨۹.۲⟩ اجرایی که provisioner درباره‌اش ۷۵ دقیقه چیزی نگفته (`HQ_PROVISION_QUIET_S`، مثلاً restart وسط کار یا api که جواب نداد) را reaper در api روی همان گام `failed` میکند. فقط قاعده است، بدون مدل و بدون فراخوان بیرونی، و فقط وقتی provisioner روشن است.
  - اجرای شکست‌خورده تأسیس را به `sealed` برمیگرداند: مالک `resume` میکند یا تأسیس را لغو میکند. اجرایی که `refused` شد (مثلاً هتزنر رمز root داد) دیگر ادامه نمیگیرد.
- **cloud-init** از قالب‌های بازبینی‌شده‌ی `infra/provisioning/templates/` ساخته میشود، یکی برای هر کلید نرم‌افزار. هیچ قالبی ورودی نمیگیرد؛ همه‌ی مقدارها یک بار با `shlex.quote` میایند. حداکثر 32 KiB.
  - `system-upgrade`: ‏`full-upgrade`. اگر لازم باشد، **همین سرور تازه** یک بار، فقط حین ساخت، ریبوت میشود و بقیه‌ی گام‌ها را `coinepro-provision.service` بعد از بوت تمام میکند.
  - `unattended-upgrades`
  - `work-user`: کلید مالک، رمز قفل‌شده، sudo با کلید. ⟨۹.۲⟩ کاربر را خود ساخت میسازد؛ اگر از قبل باشد گام شکست میخورد. نام‌های سیستمی Ubuntu (مثل `mail` و `proxy`) رد میشوند و پیش‌فرض `<code>-ops` است.
  - ⟨۹.۲⟩ هر گام در یک subshell با `errexit` اجرا میشود، پس **شکست هر دستور گام را شکست میدهد**. `ssh-hardening`، `unattended-upgrades` و `work-user` در هر طرح اجباری‌اند.
  - `ssh-hardening`: فقط کلید، بدون root، بدون رمز، فقط کاربر کاری.
  - `docker`: از مخزن رسمی Docker. اثر انگشت کلید امضا (`9DC8…CD88`) پیش از اعتماد چک میشود.
  - `git`
  - `node-lts`: ‏Node 24.21.0 از nodejs.org، با sha256 ثابت.
  - `claude-code`: ‏2.1.294، همان نسخه‌ی runtime هاب، برای کاربر کاری. **ورود را خود مالک انجام میدهد** (`claude`). هیچ توکنی از هاب به سرور تازه نمیرود.
  - `repo-clone`: یک deploy key **روی همان سرور** ساخته میشود و فقط نیمه‌ی عمومی‌اش در گزارش گام `verify` میاید. مالک آن را read-only به ریپو اضافه میکند و بعد `~/coinepro-clone.sh` را اجرا میکند. ریپوی عمومی همان لحظه clone میشود. کلید میزبان GitHub ثابت شده است.
  - `private-network`
  - `hetzner-firewall`
  - `node-exporter`: فقط روی IP خصوصی.
  - لاگ هر گام در `/var/log/coinepro-provision.log` است (فقط root).
- **فراخوان یک‌بارمصرف:**
  - توکن تصادفی را provisioner میسازد. فقط sha256 آن به api میرود؛ متن آن فقط در `user_data` همان سرور است.
  - سرور آن را در هدر `Authorization`، با HTTPS به `/api/v1/provisioning/callback` میفرستد، نه در URL (تا در لاگ Caddy نماند).
  - همراهش این‌ها میرود: نتیجه‌ی هر گام، نیمه‌ی عمومی deploy key، و کلیدهای میزبان SSH (برای اولین ورود مالک).
  - بعد توکن و نسخه‌های cloud-init از `user_data` روی سرور پاک میشوند. توکن ۶۰ دقیقه اعتبار دارد و یک بار مصرف میشود.
- **بعد از آماده شدن** (`ready_for_login`):
  1. `ssh <work_user>@<ipv4>`. اثر انگشت میزبان را با گزارش مقایسه کنید.
  2. `claude` و ورود با حساب خودتان.
  3. deploy key را به ریپو اضافه کنید و `~/coinepro-clone.sh` را اجرا کنید.
  4. در اپ «فعال‌سازی» (🔏).
- **قیمت:** `GET http://provisioner:8110/v1/pricing?type&location` (فقط برای api). جواب هزینه‌ی ماهانه‌ی یورو است، از `/pricing` هتزنر، به‌اضافه‌ی IPv4 اصلی که هتزنر جدا حساب میکند.
- **تطبیق روزانه (PR-063):** `GET /v1/servers` همه‌ی سرورهای پروژه را با برچسب‌هایشان فقط‌خواندنی میدهد. api آن‌هایی را که برچسب ما را دارند ولی طرح مُهرشده ندارند یافته‌ی critical میکند.
- **آزمون (CI، بدون هزینه):**
  - هتزنر جعلی روی HTTP (`services/provisioner/tests`) این‌ها را میسنجد:
    - بدون مُهر هیچ فراخوانی انجام نمیشود.
    - سرور یا فایروال بی‌برچسب لمس نمیشود.
    - رمز root ساخته نمیشود.
    - شکست هر گام گزارش میشود و قابل ادامه است.
    - قیمت درست حساب میشود.
  - `make check` ← gate ‏`provisioning`: قالب‌ها در کانتینر Ubuntu 24.04 به‌عنوان root اجرا میشوند، بدون شبکه:
    - فقط apt، npm، docker CLI و systemctl جایگزین ضبط‌کننده‌اند.
    - کلید Docker و Node واقعی در زمان build ایمیج آزمون گرفته و چک میشوند.
    - چهار سناریو: کامل، اجرای دوباره، ریبوت، و گام شکست‌خورده.
    - ⟨۹.۲⟩ و سه سناریوی دیگر: sha256 غلط Node، پیکربندی‌ای که `sshd -t` رد میکند، و حسابی که از قبل با نام کاربر کاری هست. هر کدام گامش را شکست میدهد و چیزی را که آن گام نگه میدارد دست‌نخورده میگذارد.
  - `HQ_PROVISION_ONLINE=1 bash scripts/quality/provisioning.sh` همان را با apt، مخزن Docker و npm واقعی اجرا میکند.

## ۲۶. تأسیس شرکت و طرح سرور، سمت api (پرامپت ۹ §۲ تا §۴، قرارداد §۱۸.۸)
- **چرخه‌ی تأسیس** (`POST /api/v1/foundings` با `{source: {kind: "repo", repo} | {kind: "idea", brief_md}}`):
  1. `auditing`: یک کار ممیزی برای platform SRE هلدینگ، یا اگر نیست، برای مدیر عملیات AI.
     - **فقط‌خواندنی**: تا کارگاه کد runtime دارد، یک workspace و یک grant خودکار فقط `read` (بدون push، ۵ دلار، ۲ روز) میسازد. بدون runtime، ممیزی فقط با `github.read` و خواندن صفحه‌های عمومی است و **هیچ چیزی اجرا نمیشود**.
     - خروجی (`deliver`) گزارش است، به‌علاوه‌ی پنج نمره به‌شکل evidence از نوع `metric` با ref یکی از `architecture`، `quality`، `security`، `tests` و `debt` و note به‌شکل `N/10`.
  2. `proposed`: مدیر عملیات AI یک کارت `company_found` میسازد: کد، نام‌ها، دپارتمان‌های قالب standard، KPIها، تیم، نقشه‌ی راه ۹۰ روزه و هزینه.
     - کنار کارت، یک **طرح سرور قاعده‌ای** ساخته میشود: `cpx22` در `fsn1`، همه‌ی کلیدهای نرم‌افزار، و SSH فقط از نشانی‌های مالک.
     - مشاور کل طبق منشورش پیشنهاد نمیدهد؛ نظرش را مالک در رشته‌ی `A` میپرسد.
  3. `sealed`: مالک کارت را با 🔏 (`decision.approve`) تأیید میکند. نتیجه **فقط داده** است، بدون تغییر کد:
     - شرکت با دپارتمان‌های پیشنهادی و جایگاه‌های رهبری، در وضعیت `paused` تا فعال‌سازی
     - workspace ریپو (`<CODE>-APP`)
     - کارت جدای `server_plan` برای مُهر طرح
  4. `provisioning` و بعد `ready_for_login`: provisioner طرح مُهرشده را میسازد (بخش provisioner).
  5. `active`: بعد از ورود خود مالک، `POST /foundings/{ref}/activate` با 🔏 (هدف = ref). شرکت `active` میشود و مدیرعامل یک کار شروع میگیرد که نقشه‌ی راه، KPIها و تیم پیشنهادی را دارد. استخدام تیم با خود مدیرعامل است، طبق قاعده‌ی استخدام.
  - `POST /foundings/{ref}/cancel` تا پیش از `active` کار میکند. شرکتی که ساخته شده میماند (`paused`) و چیزی حذف نمیشود.
    - ⟨۹.۲⟩ لغو همه‌چیز را میبندد: کارت‌های pending `company_found` و `server_plan` withdraw میشوند، طرح مُهرشده‌ی اجرانشده به `proposed` برمیگردد، کار ممیزی و پیشنهاد لغو میشود و سشن کارگاه متوقف میشود. از تأسیس لغوشده هیچ چیز مُهر، ساخته یا build نمیشود.
    - تا وقتی ساخت در صف یا در حال اجراست، لغو `409` میگیرد.
- **طرح سرور** (`server.plan`، کلاس A1؛ مدیر فنی برای شرکت خودش، platform SRE برای هر شرکت یا تأسیس):
  - نرم‌افزار فقط از فهرست ثابت `hq_common.provisioning.SOFTWARE` است. کلید ناشناخته `422` میگیرد.
  - `digest` همان sha256 از JSON کانونی است و هر دو سمت آن را با یک کد حساب میکنند.
  - **هزینه** از `/pricing` هتزنر میآید، از راه provisioner. تا provisioner خاموش است، هزینه خالی میماند و **طرح مُهر نمیشود** (`409 price_unknown`). هیچ قیمتی ساخته نمیشود.
- **مُهر:** `POST /provisioning/plans/{ref}/seal` با 🔏 `provision.seal` روی **digest همان طرح**.
  - کارتابل طرح را مُهر نمیکند (`409`).
  - طرحی که بعد از دیدن مالک عوض شده با step-up قدیمی مُهر نمیشود. طرح مُهرشده‌ای که عوض شود مُهرش باطل میشود و کارت تازه میگیرد.
  - اگر طرحی پشت سر api عوض شود، provisioner هرگز آن را نمیگیرد: مُهر باطل میشود و مالک اعلان میگیرد.
- **SSH:** نشانی‌های مجاز در `PUT /owner/settings` با `provision_ssh_sources: ["x.x.x.x/32"]` تعیین میشوند. `0.0.0.0/0` رد میشود. بدون آن‌ها طرح قاعده‌ای قانون SSH ندارد و مُهر نمیشود.
- **اجرای ساخت:** `GET /provisioning/runs/{id}` و `/live` (SSE، با `Last-Event-ID`).
  - `POST /provisioning/runs/{id}/resume` اجرای شکست‌خورده را از همان گام ادامه میدهد. طرح همان طرح مُهرشده است و چیزی دو بار ساخته نمیشود.
  - **callback عمومی** فقط `POST /api/v1/provisioning/callback` است، با توکن یک‌بارمصرف در `Authorization`. حداکثر ۶۰ دقیقه اعتبار دارد و یک بار. فقط sha256 توکن نگه داشته میشود. هر چیز دیگری `401` میگیرد.
- **`GET /infra/servers`** فقط‌خواندنی است. **هیچ حذفی در API نیست**: سرور را فقط مالک در کنسول هتزنر حذف میکند.
  - این مسیر فهرست پروژه‌ی هتزنر را هم میدهد. api آن را هر ۶ ساعت و با هر بار باز شدن این صفحه تازه میکند.
  - پروتکل **PR-063** هر روز ساعت ۰۶:۰۰ با کد آن را با طرح‌های مُهرشده تطبیق میدهد. سرور بی‌طرح، از جمله سرورهای قدیمی همان پروژه، یافته‌ی critical میسازد. یافته‌ای که مالک ببندد (مثلاً «سرور خود ما، از قبل») دوباره ساخته نمیشود.

## ۲۷. نشان و مُهر شرکت از لوگوی PNG مالک (پرامپت ۹.۱، قرارداد §۱۸.۱۴)
- **مُهر هلدینگ داده نیست.** خورشید ۲۴ پرتو و CP دوفلزی در خود اپ‌هاست و هیچ مسیری آن را نمیسازد. `POST /companies/<holding>/brand` جواب `422` میدهد و `/brands` هیچ‌وقت هلدینگ را ندارد.
- **داده:** جدول `org.company_brands`، نسخه‌دار. چرخه: `processing` ← `proposed` ← `active` ← `retired`، یا `processing` ← `failed` با `status_reason`.
  - بعد از `processing` فقط `state` و زمان‌هایش عوض میشوند. trigger هر تغییر دیگری را رد میکند. DELETE هم نیست.
  - در هر شرکت حداکثر یک نسخه‌ی `active` هست. `Company.brand_version` و `Founding.brand` از همین جدول خوانده میشوند.
- **ساخت نشان از PNG** (فقط مالک؛ کد، بدون مدل):
  1. `POST /api/v1/files` با PNG (بهتر با زمینه‌ی شفاف)، WebP یا JPEG. HEIC و بقیه `422` میگیرند.
  2. `POST /api/v1/companies/<CODE>/brand` با `{file_id, part: "mark"|"wordmark", options?: {colors?: 1..4, detail: 1..5}}` و `Idempotency-Key` ← `202` با نسخه‌ی `processing`.
     - بخش دیگر (و برای wordmark، رنگ‌ها) از نسخه‌ی فعال منتقل میشود.
     - فایل اگر هنوز در هلدینگ است، مثل اولین پیوست به همان شرکت منتقل میشود.
  3. worker (فعالیت `brand_trace`، workflow `BrandTrace`) فایل را در یک **پردازه‌ی فرزند** میخواند (`hq_common.untrusted`):
     - بدون شبکه: فیلتر seccomp جلوی `socket()` را میگیرد.
     - سقف‌ها: ۳۸۴ MiB فضای آدرس، ۵۰ ثانیه CPU، مهلت ۶۰ ثانیه، بدون نوشتن فایل. هر بار فقط یک فرزند.
  4. نتیجه `proposed` است با `checks` (`iou`، `min_feature_px_16`، کنتراست شب و روز، هشدارها)، و رویداد `brand.updated` روی topic `companies`.
  5. مالک پیش‌نمایش را در اپ میبیند. یا با گزینه‌ی دیگر `retrace` میکند، یا `activate` میکند.
- **گزینه‌ها:**
  - `colors`: تعداد رنگ. خالی یعنی «به تعداد رنگ‌های خود لوگو، حداکثر ۴». `1` یعنی یک لایه‌ی `ink` و `accent: null`.
  - `detail`: از ۱ تا ۵، پیش‌فرض ۳. هر چه بیشتر، فیلتر نقطه‌های ریز کوچک‌تر و آستانه‌ی گوشه تیزتر.

| detail | فیلتر نقطه (px در ۱۰۲۴) | آستانه‌ی گوشه |
|---|---|---|
| ۱ | ۲۴ | ۱۲۰° |
| ۲ | ۱۶ | ۹۰° |
| ۳ | ۱۰ | ۶۰° |
| ۴ | ۶ | ۴۵° |
| ۵ | ۳ | ۳۰° |

- **خطاها (`status_reason`) و راه‌حلشان:**

| خطا | یعنی | راه‌حل |
|---|---|---|
| `no_background` | چهار گوشه هم‌رنگ نیستند (ΔE76 > ۵)، یا لبه‌ی تصویر بیشترش هم‌رنگ زمینه نیست | PNG با زمینه‌ی شفاف، یا زمینه‌ی یکدست |
| `too_complex` | همه‌ی `d`ها با هم بیش از ۴۸ کیلوبایت است، حتی با detail ۱ | لوگوی ساده‌تر، یا فقط نشان بدون نوشته |
| `too_large` | بیش از ۴۰۹۶ پیکسل، یا decompression bomb، یا حافظه‌ی فرزند پر شد | تصویر کوچک‌تر (۱۰۲۴ تا ۲۰۴۸ کافی است) |
| `too_small` | ضلع کوچک‌تر از ۱۶ پیکسل | تصویر بزرگ‌تر |
| `unreadable` / `unsupported` | فایل خراب است، یا PNG، WebP یا JPEG نیست | دوباره خروجی بگیر |
| `empty` | چیزی جز زمینه نماند | لوگو را روی زمینه‌ی متضاد بده |
| `invalid_path` | خروجی ردگیر با گرامر path نخواند | گزارش به Claude سرور (نباید رخ دهد) |
| `stopped` | فرزند در مهلت تمام نشد، یا سه بار تلاش شد | دوباره `retrace` |

- **هشدارها (نسخه `proposed` میماند):**
  - «بدون شفافیت»: JPEG یا هر تصویر بدون شفافیت.
  - ردگیری با اصل یکی نیست: `iou` کمتر از ۰٫۹. detail بیشتر را امتحان کن.
  - «در اندازه‌ی کوچک جزئیات گم میشود»: `min_feature_px_16` کمتر از ۱.
  - کنتراست کم: `accent_night` یا `accent_day` جایگزین شد.
  - detail خودکار پایین آمد.
- **مُهر:** `POST /companies/<CODE>/brand/<version>/activate` با 🔏 `company.brand`.
  - هدف step-up همان `digest` نسخه است: sha256 از JSON کانونی mark، wordmark، ink، accent، accent_night و accent_day. سرور آن را از ردیف ذخیره‌شده دوباره حساب میکند.
  - نسخه‌ای که بعد از دیدن مالک عوض شده باشد با همان step-up مُهر نمیشود (`403 step_up_invalid`).
  - نسخه‌ی فعال قبلی `retired` میشود. نسخه‌ی retired را میشود دوباره فعال کرد.
  - نسخه‌ای که mark ندارد `409 not_ready` با `missing: ["mark"]` میگیرد.
- **`GET /api/v1/brands`:** همه‌ی نشان‌های فعال در یک پاسخ، با `ETag` و `Cache-Control: private, no-cache`. با `If-None-Match` جواب `304` است.
- **تأسیس:** `POST /foundings/{ref}/activate` بدون نشان فعال `409 not_ready` با `missing: ["brand"]` میدهد، مگر بدنه `{"skip_brand": true}` باشد. در آن حالت شرکت تا مُهر نشان، کدش را نشان میدهد.
- **seed:** در `api-migrate` (`hq_api.migrate` ← `seed`):
  - برای هر پوشه‌ی `design/brand/companies/<code>/` که شرکتش هست و هنوز هیچ نسخه‌ای ندارد، نسخه‌ی ۱ `active` با `source.kind: "seed"` ساخته میشود.
  - از `*-mark-flat.svg` و `*-wordmark*-flat.svg`، با لایه‌های `--logo-ink` و `--logo-accent`، همان قاعده‌ی `gen-assets.mjs`.
  - پوشه‌ها read-only در `/app/design/brand/companies` (`HQ_BRANDS_DIR`) mount میشوند. **هیچ کد شرکتی در کد نیست.**
  - seed idempotent است. شرکتی که پوشه ندارد seed نمیشود، و نسخه‌ی آپلودی هیچ‌وقت دست نمیخورد.
- **کلید توقف:** ردگیری کد است و مدل یا سرویس بیرونی ندارد. پس با کلید توقف هم کار میکند (مالک هیچ‌وقت قفل نیست).
  - `reconcile_decisions` نسخه‌هایی را که بیش از ۱۰ دقیقه `processing` مانده‌اند دوباره راه میاندازد. این هم کار قاعده‌ای است.

## ۲۸. درآمد و پشتیبانی: پایه (پرامپت ۱۰ §۱، قرارداد §۱۹)
- **پنج schema:** `revenue`، `support`، `growth`، `feedback`، `intake` (migration `0025`). همه‌ی جدول‌ها `company_id` و RLS **FORCE** دارند؛ هیچ جدول بی‌شرکتی نیست.
- **نام مستعار مشتری:** `subject = HMAC-SHA256(key, company || channel || external_id)` (`hq_common.pseudonym`).
  - کلید در `kv/support/pseudonym` است. `make up` آن را یک بار با KV check-and-set (`cas: 0`) میسازد (`infra/openbao/kv-once.sh`) و هرگز عوض نمیکند؛ چاپ نمیشود. api و worker فقط میخوانند.
  - **چرخاندن فقط با خواست مالک:** کلید تازه همه‌ی `subject`های گذشته را غریبه میکند (قیف، نجات، NPS از نو شروع میشوند).
  - handle، شناسه‌ی کاربر کانال و UID خام فقط در `support.customers` میمانند. بقیه‌ی جدول‌ها فقط `subject` دارند (CHECK: hex ۶۴).
- **ماسک پیش از ذخیره:** هر پیام مشتری از `hq_common.customer_mask.mask` رد میشود: ماسک §۱۶.۶ به‌علاوه‌ی عبارت بازیابی (۱۲+ کلمه‌ی BIP-39)، کلید خصوصی (hex ۶۴، WIF، xprv، هر بلوک `-----BEGIN`) و شماره‌ی کارت (Luhn). متن خام هرگز ذخیره نمیشود و به مدل نمیرسد. hash تراکنش هم hex ۶۴ است و ماسک میشود (سمت امن).
- **نگهداری:** job روزانه‌ی `hq-support-retention` (۰۴:۱۵ به وقت مالک) متن‌های مشتری قدیمی‌تر از `SUPPORT_RETENTION_DAYS` (پیش‌فرض ۱۸۰) را پاک میکند: بدنه‌ی پیام‌ها، توضیح NPS، نقل‌قول بازخورد و داده‌ی رویدادهای intake. ردیف، زمان، وضعیت و برچسب‌ها میمانند.
  - این job فقط قاعده است (بی‌مدل، بی‌تماس بیرونی)، پس با کلید توقف هلدینگ هم اجرا میشود.
  - **backup:** متنی که پاک شد، در snapshotهای restic تا پایان نگهداری همان snapshot میماند (§۱۸: ساعتی ۷ روز، روزانه ۹۰، هفتگی ۵۲، ماهانه ۳۶، سالانه ۱۰). پاک کردن آن از backup فقط با تصمیم مالک است.
- **دروازه‌ی راه‌اندازی:** هر چیزی از پرامپت ۱۰ که خودش اجرا میشود (pull، ارسال، پیش‌نویس، batch، پروتکل) اول `hq_api.domain.gate` را میپرسد و تا قفل هلدینگ یا شرکت هست، بی‌مدل و بی‌تماس بیرونی رد میشود (`skipped`).
- **متغیرها** (`.env`، خالی یعنی پیش‌فرض): `SUPPORT_RETENTION_DAYS`، `SUPPORT_DRAFT_DAILY_TOKENS` (۶۰ هزار برای هر شرکت در روز)، `SUPPORT_DAILY_OUTBOUND_CAP`، `SUPPORT_AUTO_REPLIES_PER_HOUR`، `SUPPORT_HANDOFF_DIGEST_MIN`، `REFERRAL_CHECKS_PER_HOUR`، `REFERRAL_CHECK_CACHE_S`، `REVENUE_BACKFILL_DAYS`، `REVENUE_PULL_MAX_DAYS`، `INTAKE_MAX_SKEW_S`.

### ۲۸.۱ رادار درآمد، قیف، نجات رفرال و صندوق بازخورد (پرامپت ۱۰ §۲، §۳، §۸؛ قرارداد §۱۹.۱، §۱۹.۲، §۱۹.۷)
- **حساب افیلیت** = یک حساب سرویس §۱۸.۱۳ با policy `{"inject": {"kind": "signer", "signer": "lbank-v2"}}` و `site` = میزبان API افیلیت LBank.
  - رمز: `make account-secret KEY=<key>` (مالک)، **در یک خط به شکل `api_key:secret_key`**. هرگز چاپ و هرگز از API برگردانده نمیشود.
  - بعد `POST /api/v1/revenue/accounts` 🔏 `revenue.account` (هش بدنه): `{company, exchange: "lbank", service_account: <key>, title_fa}`.
  - **whitelist:** IP عمومی هاب باید در پنل API افیلیت همان صرافی ثبت شود؛ LBank بدون آن جواب نمیدهد (کار مالک).
- **مسیر امضا:** worker ← gateway `POST /v1/connectors/call` (توکن worker) ← api `POST /internal/v1/egress/connectors/{adapter}/pull` (توکن سرویس `worker` در `kv/hq-agents/connector`؛ `make up` یک بار میسازد) ← egress `POST /v1/connectors/call`.
  - egress امضا میکند (`hq_egress/signers.py`، فهرست ثابت)، سقف مستند LBank (۵ درخواست در ۱۰ ثانیه، token bucket هر حساب) را نگه میدارد و پاسخ را **همان‌جا کوچک میکند**: از فهرست تیم فقط UID، روز دعوت و `meets_minimum`؛ موجودی خوانده و دور ریخته میشود.
  - secret در هیچ پاسخ، لاگ یا `egress.log` نیست (هر شکلش scrub میشود). حساب signer برای `http.request`، `web.read` و `web.browse` رد میشود (`policy_denied`، در api و در egress).
  - قیمت دلاری کوین‌های غیر USDT: قیمت بسته‌شدن همان روز از kline عمومی LBank (`EGRESS_LBANK_PUBLIC_URL`، پیش‌فرض `https://api.lbkex.com`)؛ منبع در `by_coin[].price_source`.
- **زمان‌ها (worker):** `hq-revenue-pull` هر روز ۰۷:۰۰ تهران، روز قبل (تسویه‌ی T+1 به وقت UTC+8)؛ اولین بار backfill `REVENUE_BACKFILL_DAYS` (۹۰). `hq-revenue-retry` ساعت ۱۱:۰۰ و ۱۸:۰۰، فقط روزهای ناقص یا نیامده‌ی ۳ روز اخیر. pull دستی: `POST /api/v1/revenue/accounts/{id}/pull?from&to` (حداکثر `REVENUE_PULL_MAX_DAYS`، `Idempotency-Key` اجباری).
  - هر pull اول دروازه را میپرسد: تا کلید توقف هلدینگ (یا شرکت) روشن است، ردیف `skipped` با `holding_locked` ثبت میشود و هیچ تماسی بیرون نمیرود.
  - روزی که یکی از صفحه‌هایش نیامد `complete: false` با `gaps` است؛ روز کامل هرگز با pull ناقص بعدی بازنویسی نمیشود.
- **هشدارها** (یکی برای هر رخداد، سطح `report`، بسته‌ی مالک + یک خط سیستمی در thread مدیرعامل): کمیسیون زیر ۶۰٪ میانه‌ی همان روزِ هفته در ۲۸ روز؛ دو pull شکست‌خورده‌ی پشت‌سرهم (+ یک کار برای SRE پلتفرم)؛ روزی که pull امتحانش کرد و ۳۶ ساعت بعد از تسویه هنوز ناقص است.
- **هزینه در برابر درآمد:** `token_cost_usd` = جمع `cost_usd + equiv_cost_usd` در `llm.calls` همان روزها (به وقت UTC+8)، هرگز از گزارش ایجنت؛ `net_usd = usdt − token_cost_usd` (USDT ≈ USD).
- **PR-103** (تطبیق رادار با داده‌ی خام): هر صفحه‌ی هر endpoint با ارقام کوچک‌شده و SHA-256اش در `revenue.days.source.pages` میماند؛ checker کد (`domain/revenue_checks.py`) سه روز اخیر را از همان‌ها دوباره حساب میکند. پروتکل در فایلش `paused` است تا کلید افیلیت مالک برسد.
- **قیف:** `visit` (بی‌منبع)، `signup` و `vip_active` (رویداد محصول، وقتی منبع `product` با آن نوع ثبت شد)، `referral_verified` (دعوت‌شده‌های تازه‌ی هر روز) و `min_balance` (از آن‌ها، بالای **همان یک عدد** مقاله‌ی `policy` با کلید `vip.min_balance`؛ بی‌آن مقاله وصل نیست). مرحله‌ی بی‌منبع `connected: false, count: null` است و هیچ نرخی تخمین زده نمیشود.
  - نشتی: نرخ هفته‌ی آخر کمتر از ۷۰٪ میانه‌ی چهار هفته‌ی قبل ← یک ردیف `growth.leaks` و یک کار برای مدیر SALES (بعد از هر pull).
- **نجات رفرال:** `referral.check` (پشتیبان و متخصص نجات) فقط `{invitee, meets_minimum}`؛ حداکثر `REFERRAL_CHECKS_PER_HOUR` در ساعت برای هر شرکت، جواب تا `REFERRAL_CHECK_CACHE_S` دوباره استفاده میشود؛ با قفل هلدینگ ۴۲۳.
  - «دعوت‌شده‌ی ما نیست» در یک گفت‌وگو (یا رویداد `referral_failed` محصول) ← پرونده `RC-…`؛ چک بعدی «هست» (یا `referral_verified` محصول) ← `rescued`؛ ۳۰ روز یا `max_follow_ups` ← `lost`؛ لغو مشتری ← `opted_out`.
  - **«قبلاً ثبت‌نام کردم» (§۴.۵):** پشتیبان UID میخواهد و `referral.check` میزند. api گفت‌وگویی را که run او جوابش را میدهد پیدا میکند، UID را فقط روی همان مشتری در `support.customers.uids` نگه میدارد و پرونده را به همان گفت‌وگو وصل میکند. پرونده‌ی محصولی که گفت‌وگو ندارد، با چک بعدی در یک گفت‌وگو به آن وصل میشود.
  - پیگیری‌ها (`hq-rescue-follow-ups`، ساعتی، پشت دروازه) فقط زیر قاعده‌ی **فعال** `rescue` و فقط از فرستنده‌ی §۷ (`growth.send_template`: قالب مُهرشده، لغو، سقف‌ها، ساعت سکوت، کانال `live`، نگهبان با جمله‌ی ایمنی). پیام صف‌شده بعد از commit با `desk.send` میرود (دروازه دوباره پرسیده میشود). مشتری بی‌کانال (`no_channel`) یک روز بعد دوباره امتحان میشود. متخصص نجات هیچ ابزار ارسالی ندارد.
- **صندوق بازخورد:** کلیدواژه‌های هر شرکت در `feedback.keywords` (داده) ← نوع و حوزه، بی‌مدل؛ بقیه در `hq-feedback-batch` (۰۲:۳۰ تهران، پشت دروازه) با یک فراخوانی مدل سبک (Haiku 5.5، P4) برای هر شرکت. نقل‌قول‌ها ماسک‌شده (بی handle و UID)، حداکثر ۳. موردی که در پنجره‌ی شرکت به آستانه برسد (پیش‌فرض ۵ در ۷ روز، `support.settings`) یک کار برای مدیر PRODUCT میشود.
  - هر پیام مشتری (بعد از لغو، جواب NPS/CSAT و چک ربات) و هر توضیح NPS از `feedback.ingest` رد میشود: برچسب کلیدواژه بی‌مدل، وگرنه `pending` برای batch شبانه. گفت‌وگوی mystery ثبت میشود ولی شمرده نمیشود.
  - گزارش هفتگی پشتیبانی (`hq-support-weekly`، شنبه ۰۸:۳۰ تهران): کار برای سرپرست پشتیبانی؛ شرکت بی‌سرپرست ← همان ارقام در گزارش صبحگاهی شنبه.
- **متغیرهای تازه‌ی egress:** `EGRESS_LBANK_PUBLIC_URL`، `EGRESS_CONNECTOR_WAIT_S` (انتظار حداکثر برای سقف نرخ، پیش‌فرض ۸ ثانیه).

### ۲۸.۲ پشتیبانی: مسیر جواب، نگهبان، go-live (پرامپت ۱۰ §۴ تا §۶، قرارداد §۱۹.۳ تا §۱۹.۶)
- **هیچ متن آزادی از ایجنت به مشتری نمیرسد.** فقط سه چیز میرود: جواب عین مقاله‌ی تأییدشده، پیش‌نویسی که سیاست `auto_send` همان کانال اجازه میدهد و همه‌ی چک‌ها را پاس کرده، یا قالب مُهرشده زیر قاعده‌ی مُهرشده.
- **مسیر هر پیام** (`SupportInbound` در worker، `hq_api.domain.desk.process`):
  1. ماسک و ذخیره (`store_inbound`).
  2. «لغو»، stop و مشابه‌ها: مشتری از همه‌ی قاعده‌های آن شرکت برای همیشه بیرون میرود. عدد ۰ تا ۱۰ بعد از NPS و ۱ تا ۵ بعد از CSAT جواب همان‌اند، نه پرونده‌ی تازه.
  3. گفت‌وگوی ربات‌با‌ربات (یک متن ۳ بار در ۲ دقیقه، یا ۶ پیام در ۲ دقیقه): گفت‌وگو `paused` و handoff.
  4. گزارش امنیتی (جعل، کلاهبرداری، «Ignore your rules»)، شکایت یا «با آدم حرف بزنم»: handoff فوری.
  5. **قاعده:** بهترین مقاله‌ی `faq` تأییدشده و منقضی‌نشده‌ی همان شرکت. اگر امتیاز ≥ `verbatim_threshold` و فاصله با دومی ≥ `verbatim_margin` (۰٫۱۵) بود، جواب عین مقاله میرود، **بی‌مدل**.
  6. وگرنه ایجنت پشتیبانی همان شرکت یک کار P1 میگیرد و با `support.draft` پیش‌نویس میدهد. شرکت بی‌ایجنت پشتیبانی، یا شرکتی که `SUPPORT_DRAFT_DAILY_TOKENS` امروزش تمام شده: handoff بی‌مدل.
- **پیش‌نویس** (`support.draft`، کد تصمیم میگیرد): grounded (هر لینک، کد و عدد باید عیناً در مقاله‌های ارجاع‌شده‌ی تأییدشده باشد) ← نگهبان ← `auto_send`:
  - `kb_verbatim` (پیش‌فرض): فقط جواب عین مقاله میرود.
  - `kb_grounded`: پیش‌نویسی هم که هر دو چک را پاس کرده و `confidence ≥ grounded_threshold` دارد.
  - `off`: هیچ.
  - بقیه به صف آموزش مالک (`GET /support/queue`) میرود. مشتری قالب مُهرشده‌ی `holding_reply` را میگیرد. بسته‌ی مالک هر `SUPPORT_HANDOFF_DIGEST_MIN` دقیقه **یک** خط میگیرد. handoff امنیتی `urgent` است، حداکثر ۳ بار در روز برای هر شرکت.
- **ارسال** (`SupportSend`، فقط worker): فقط کانال `live` به مشتری میرسد. `shadow`، `paused` و `not_configured` هیچ چیزی به تلگرام یا Chatwoot نمیفرستند.
  - قواعد تلگرام در کد چک میشود: ربات فقط به کسی مینویسد که خودش شروع کرده، و گفت‌وگوی Business با `business_connection_id` خودش جواب میگیرد. پیامی که تلگرام اجازه نمیدهد `failed: no_channel` ثبت میشود.
  - سقف‌ها: `SUPPORT_AUTO_REPLIES_PER_HOUR` (۲۰ جواب خودکار در ساعت برای هر گفت‌وگو؛ بیست‌ویکمی گفت‌وگو را `paused` و handoff میکند) و `SUPPORT_DAILY_OUTBOUND_CAP` (برای هر شرکت؛ جواب مالک بعد از آن `429 send_limit` با `Retry-After` میگیرد).
  - ارسال از egress است: `POST /v1/support/send` (worker روی `hq-egress-api`). توکن ربات (`kv/support/telegram/<CO>/<channel>`) یا حساب سرویس Chatwoot برای همان یک فراخوانی از OpenBao خوانده و فقط به egress داده میشود؛ در هیچ لاگ و پاسخی نیست.
  - جمله‌ی ایمنی (قالب مُهرشده‌ی `safety`) در اولین جواب هر گفت‌وگو و در هر پیام چرخه‌ی عمر میآید.
- **نگهبان خروجی** (`hq_common.outbound_guard`، کد، نه مدل) روی **هر** پیام خروجی همه‌ی کانال‌ها، حتی جواب خود مالک و کانال mystery:
  - کدهای رد: `asks_secret`، `unknown_link`، `unknown_code`، `profit_promise`، `customer_data`، `internal_data`، `too_long` (۳۵۰۰)، `red_line` (فهرستش با پرامپت ۱۱ پر میشود).
  - برای `asks_secret`، `profit_promise` و `red_line` هیچ استثنایی نیست. پیام ردشده `blocked` با دلیل‌ها میماند و جواب API برای مالک `422 send_blocked` با `fields.blocked_reasons` است. مالک متن را اصلاح و دوباره میفرستد.
  - لینک و کد فقط وقتی پاس میشوند که **عیناً** در مقاله‌های `official_link`/`referral` تأییدشده‌ی **همان شرکت** باشند.
- **دانشنامه:**
  - تأیید مقاله: `POST /support/kb/{ref}/approve` با step-up `support.kb` و هدف `ref@version`.
  - هر مقاله ۱۸۰ روز اعتبار دارد (`support.settings.kb_expiry_days`). ۱۴ روز قبلش سرپرست پشتیبانی (اگر هست) یک کار میگیرد. مقاله‌ی منقضی دیگر جواب خودکار نمیسازد.
  - کد و لینک رفرال را فقط مالک مینویسد. پیشنهاد ایجنت (`kb.propose`) لینک و کد ندارد.
- **حالت آموزش:** هر جواب مالک (`/reply`، `/teach`؛ هر دو `Idempotency-Key` اجباری دارند) یک مقاله‌ی پیشنهادی ماسک‌شده با `source: owner_answer` میسازد. اگر سرپرست پشتیبانی هست، یک کار تعمیم برای او ساخته میشود.
- **آزمون سایه و go-live** (فقط وقتی مالک تاریخچه را بدهد):
  1. فایل خروجی Telegram Desktop (`result.json`) یا CSV پرسش و پاسخ را در اپ بارگذاری کن، بعد `POST /support/history {company, file_id}`. خروجی حداکثر ۱۰۰ مورد ماسک‌شده است، به تفکیک موضوع، در suite خصوصی `support-shadow-<CO>` همان شرکت. این کار فقط قاعده است.
  2. `POST /support/shadow/{company}/run`: worker موردها را از همان مسیر §۴.۳ بی‌ارسال اجرا میکند (اول قاعده، بعد پیش‌نویس منشور پشتیبانی روی router)، با داوری کد و داور سبک. توکنش هزینه‌ی آکادمی است و تا قفل هلدینگ هست `skipped` میشود.
  3. **قبولی:** درست ≥ ۹۰٪ **و** صفر خطای ایمنی **و** صفر کد یا لینک اشتباه. با قبولی برای هر کانالی که در `shadow` است یک کارت `support_go_live` ساخته میشود، با آستانه‌های پیشنهادی همان اجرا. یک اعلان `decision` هم درباره‌ی خرید Premium میآید.
  4. مُهر کارت (step-up `decision.approve`) کانال را `live` و آستانه‌ها را همان عددهای کارت میکند. آستانه‌ها مسیر ویرایش ندارند.
  - کارت فقط به اجرای خودش بسته است. اجرای تازه‌تر کارت قبلی را باطل میکند (۴۰۹).
  - Telegram Business اتصال Premium را هم لازم دارد (`premium_connected`، از رویداد `business_connection` خود تلگرام).
  - قالب‌های `holding_reply` و `safety` باید مُهر شده باشند.
- **کانال‌ها:** `PATCH /support/channels/{company}/{kind}` (If-Match).
  - گشادتر کردن (رفتن به `kb_grounded`، یا برگرداندن کانال `paused`ی که قبلاً go-live گرفته به `live`) step-up `support.channel` با هدف `company/kind@auto_send` میخواهد.
  - تنگ‌تر کردن بی‌step-up است. توقف (`/pause`) فوری و بی‌step-up است.
  - کانالی که هرگز go-live نگرفته `409 shadow_not_passed` میگیرد.
- **سقف توکن پیش‌نویس** (`SUPPORT_DRAFT_DAILY_TOKENS`): llm-router در scope `support_draft:<CO>` اجرایش میکند. این همان شمارنده‌ی روزانه‌ی نقش `<CO>:support_agent` است و تمام که شد `429 budget_exhausted` میدهد. api پیش از بیدار کردن ایجنت همان شمارنده را میخواند و بی‌مدل handoff میکند (`support.settings.draft_daily_tokens` برای یک شرکت عدد دیگری میگذارد).
- **ناظر:** `support.mystery` (فقط ناظر) گفت‌وگویی روی کانال `mystery` میسازد که کل مسیر را میرود، هرگز به تلگرام یا Chatwoot نمیرسد و در هیچ آماری نیست. PR-043 بی‌کانال `live` نتیجه‌ی `deferred` و با قفل هلدینگ `skipped` میدهد. PR-043 و PR-101 تا PR-104 همه `paused` seed شده‌اند. روشن کردنشان با مالک است. PR-101 (کد یا لینک تأییدنشده در پاسخ خودکار)، PR-103 (تطبیق رادار) و PR-104 (پاسخ خودکاری که به مقاله‌ی منقضی، بازنشسته یا تأییدنشده استناد کرده) با کد سنجیده میشوند، بی‌مدل.

### ۲۸.۳ چرخه‌ی عمر، NPS، CSAT (پرامپت ۱۰ §۷، قرارداد §۱۹.۵)
- **قالب:** `POST /growth/templates` (پیشنهاد) و `POST /growth/templates/{ref}/seal` (step-up `growth.template`، هدف `ref@version:sha256` بدنه؛ توکن مُهر قالب یک شرکت برای قالب هم‌متن شرکت دیگر به کار نمیرود چون ref فرق دارد).
- **قاعده:** `POST /growth/rules` (پیشنهاد) و `POST /growth/rules/{ref}/seal` (step-up `growth.rule`، هدف `ref@version`؛ قالبِ همان نسخه باید مُهرشده و آخرین نسخه باشد، وگرنه `409 template_not_sealed`).
  - توقف بی‌step-up است. ادامه (`/resume`) step-up میخواهد. نسخه‌ی تازه‌ی قالب قاعده را تا مُهر نسخه‌ی تازه‌ی قاعده متوقف میکند.
  - ایجنت‌ها با `propose` کارت `message_template` یا `lifecycle_rule` میسازند. مُهر کارت همان مُهر است.
- **seed هر شرکت** در اولین استفاده: قالب‌های `holding_reply`، `safety`، `csat` و `nps` با امضای «پشتیبانی Coine»، و قاعده‌های `csat` و `nps`. همه `proposed`اند. تا مالک مُهر نکند هیچ پیامی نمیرود و هیچ کانالی `live` نمیشود.
- **ارسال:** فقط از `hq_api.domain.growth.send_template(...)`. ترتیب چک‌ها:
  1. دروازه‌ی قفل
  2. قاعده‌ی فعال
  3. قالب مُهرشده
  4. لغو
  5. `per_customer_days`
  6. ساعت سکوت (پیش‌فرض ۲۲:۰۰ تا ۰۹:۰۰ تهران؛ پیام صبح میرود)
  7. `daily_cap`
  8. کانال `live` و قواعد تلگرام
  9. نگهبان با جمله‌ی ایمنی
- **NPS:** موج فصلی `NP-<سال>Q<فصل>-<CO>`، نمونه‌ی تصادفی از مشتری‌های دارای گفت‌وگو در ۹۰ روز گذشته. امتیاز = ٪promoter − ٪detractor. توضیح‌ها به `feedback.signals` میروند.
- **CSAT:** بعد از بستن گفت‌وگو، اگر قاعده‌ی `csat` فعال است. جواب ۱ تا ۵ روی همان گفت‌وگو مینشیند.
- `welcome` و `reactivation` تا رسیدن رویدادهای محصول (CR-009/010) کاندیدی ندارند.
- **جاروب** (`hq-support-sweep`، هر `SUPPORT_HANDOFF_DIGEST_MIN` دقیقه) کارهای دوره‌ای را انجام میدهد و تا قفل هلدینگ هست هیچ کاری نمیکند:
  - انقضای مقاله‌ها و یادآوری‌ها
  - خط بسته‌ی مالک
  - ارسال‌های نگه‌داشته‌شده
  - موج‌های NPS
  - setWebhook تلگرام، یک بار برای هر کانال

### ۲۸.۴ ورودی از بیرون (پرامپت ۱۰ §۹، قرارداد §۱۹.۸)
- **سه مسیر Caddy** در `api-on.caddy` (فقط با دامنه؛ در `api-off.caddy` همه‌ی `/intake/*` ۴۰۴ است)، هر کدام با سقف بدنه‌ی ۱ مگ. `/internal` همچنان ۴۰۴ است. پورت تازه‌ای منتشر نشده.
  - `/intake/v1/telegram/{CO}/{channel}`: فقط از بازه‌های منتشرشده‌ی تلگرام (`149.154.160.0/20`، `91.108.4.0/22`) و فقط با `X-Telegram-Bot-Api-Secret-Token` درست. `update_id` فقط یک بار پذیرفته میشود.
  - `/intake/v1/chatwoot/{CO}`: `X-Chatwoot-Timestamp` و `X-Chatwoot-Signature: sha256=HMAC(secret, "<ts>.<body>")`.
  - `/intake/v1/product/{CO}`: `X-HQ-Timestamp` و `X-HQ-Signature`، با همان امضا ([CR-009](change-requests/CR-009.md)).
  - پنجره‌ی زمان `INTAKE_MAX_SKEW_S` (۳۰۰) است و `id` هر رویداد فقط یک بار پذیرفته میشود.
  - IPهای مجاز هر منبع را مالک در `POST /intake/sources` میدهد (step-up `intake.source`، هدف SHA-256 بدنه). ثبت منبع کانال را از `not_configured` به `shadow` میبرد، **نه** `live`.
- **رد:** پاسخ ۴۰۱/۴۰۳/۴۱۳/۴۲۹ بی‌جزئیات است و فقط یک ردیف شمارش در `intake.rejections` میسازد.
  - Caddy رسمی rate limiter ندارد. سقف را api میشمارد: `INTAKE_RATE_PER_MIN` (۱۲۰ در دقیقه برای هر منبع) و `INTAKE_MAX_BODY`.
- **رمزها** (فقط ترمینال مالک، ورودی پنهان، بار اول `cas: 0`، جایگزینی فقط با `REPLACE=yes`):
  - `make intake-secret COMPANY=… SOURCE=chatwoot|product`
  - `make telegram-bot-token COMPANY=… CHANNEL=telegram_bot|telegram_business`: توکن ربات، با webhook secret تازه کنارش.
- **رویدادهای محصول** ماسک‌شده ذخیره میشوند و UID فقط به `subject` تبدیل میشود. `support_message` وارد میز پشتیبانی روی `product_bot` میشود (CR-011). بقیه همان لحظه به `intake.APPLIERS` (`domain/product_events.py`) میروند: `referral_failed` پرونده‌ی نجات باز میکند، `referral_verified` آن را `rescued` میکند، `signup`، `vip_activated` و `uid_submitted` برای قیف میمانند (`applied`). رویداد بی `data.exchange` ← `ignored`. این کار فقط نوشتن در دیتابیس است، پس با کلید توقف هم انجام میشود؛ هیچ پیامی از اینجا نمیرود.

### ۲۸.۵ Chatwoot (پرامپت ۱۰ §۱۰؛ ساخته شده، **deploy نشده**، تصمیم هزینه با مالک)
- **روی هاب نه:** Rails حدود ۸۰۰ مگ، Sidekiq حدود ۷۰۰، Postgres ۵۱۲، Redis ۱۲۸ و Caddy ۶۴؛ جمعاً حدود ۲٫۲ گیگ سقف. بودجه‌ی هاب همین حالا پر است (پروفایل full ‏10896 از 12486 مگ و STT هم جا نشد)، پس gate حافظه رد میشود.
- **راه پیشنهادی:** یک سرور کوچک جدا (۲ vCPU، ۴ گیگ) با provisioner پرامپت ۹ و کلید نرم‌افزار `chatwoot` (`infra/provisioning/templates/chatwoot.sh`):
  - Chatwoot Community با ایمیج `v4.18.0-ce` (بخش enterprise فعال نیست).
  - رمزها روی خود سرور با openssl ساخته میشوند.
  - فقط ۴۴۳ منتشر میشود.
  - چیزی خودش شروع نمیشود. مالک بعد از ساخت `sudo chatwoot-start <domain>` میزند.
  - طرح سرور هزینه‌ی واقعی را از API هتزنر میگوید. مالک مُهر میکند.
- هاب و Chatwoot فقط از HTTPS عمومی با هم حرف میزنند:
  - هاب ← Chatwoot از egress، با حساب سرویس (`make account-secret`؛ `config` کانال `chatwoot` شامل `account` و `base_url` است).
  - Chatwoot ← هاب از `/intake/v1/chatwoot/<CO>`، با HMAC.
- **راه دوم** (profile روی خود هاب) فقط وقتی است که gate حافظه با اندازه‌گیری واقعی پاس شود؛ امروز نمیشود.

## ۲۹. حاکمیت (پرامپت ۱۱، قرارداد §۲۰)
- **migration:** `0026` (اتاق جلسه، اساسنامه، دانشنامه؛ نیمه‌ی اول) و `0026_1` (کارت‌ها، OKR، نتیجه‌ی تصمیم‌ها، ماتریس اختیار، ریسک، تقویم، مُهر گروهی؛ نیمه‌ی دوم). schemaهای تازه: `meetings` و `governance`؛ دانشنامه در `knowledge`. همه‌ی جدول‌ها `company_id` و RLS **FORCE** دارند.
- **هیچ سرویس همیشه‌روشن تازه‌ای نیست:** جلسه‌ها کد و اجراهای ایجنت در همان worker‌اند؛ جستجو همان LIKE/trgm با نرمال‌سازی فارسی Postgres است.
- **دروازه:** هر چیزی از این بخش که خودش اجرا میشود (schedule جلسه‌ها، نوبت، اتاق جنگ، کالبدشکافی، استندآپ، کار بازبینی دانش) اول قفل هلدینگ را میپرسد و تا روشن است **هیچ کاری** نمیکند: نه جلسه‌ای میسازد، نه نوبتی، نه اجرای ایجنتی. فقط انقضای دانش (قاعده‌ی خالص) با قفل هم اجرا میشود.

### ۲۹.۱ اتاق جلسه (پرامپت ۱۱ §۱، قرارداد §۲۰.۱)
- **نوع‌ها** (داده، `meetings.types`؛ seed از `apps/api/seed/meetings/types.yaml`، فقط یک بار؛ مالک در اپ عوض میکند، `PUT /meetings/settings` 🔏 `meetings.settings` = هش بدنه، هر ردیف با `version` خودش):

  | نوع | زمان | بودجه‌ی پیش‌فرض | حضور مالک |
  |---|---|---|---|
  | `board` | هفتگی، شنبه ۱۰:۰۰ (به وقت مالک) | ۱۲۰ هزار | زنده |
  | `company` | هفتگی ۱۱:۰۰، یکی برای هر شرکت فعال، پخش‌شده بین شنبه تا چهارشنبه | ۴۰ هزار | خلاصه |
  | `standup` | روزانه ۰۹:۰۰، هر دپارتمان، فقط کد | صفر | خلاصه |
  | `war_room` | با حادثه‌ی `sev1` یا 🔴 `service_down` | بی‌سقف جلسه | زنده |
  | `postmortem` | فردای بسته شدن هر حادثه، ۱۰:۰۰ | ۳۰ هزار | خلاصه |
  | `strategy` | آخرین پنجشنبه‌ی ماه شمسی، ۱۰:۰۰ (`calendar: jalali`) | ۱۵۰ هزار | زنده |

  سقف هر نوبت ۶ هزار، حداکثر ۲ دور و ۶ سخنگو برای هر دستور (مالک ۱ تا ۳ دور و ۲ تا ۸ سخنگو). مخالف‌خوان: بازرس کل (`members.devil: overseer` یعنی ناظر کل).
- **پخش جلسه‌های `company`:** هر شرکت روز هفته‌ی آخرین جلسه‌ی `company` خودش را نگه میدارد؛ شرکت تازه به کم‌بارترین روز (کمترین شرکت، بعد زودترین روز هفته) میرود، به ترتیب کد. داده‌ی ثابت همیشه همان پخش را میدهد.
- **چرخه:** `scheduled` (برنامه‌ریزی ۸ روز جلوتر، `hq-meetings` هر دقیقه) ← `prep` (T−۲۴ ساعت: دستور جلسه، سخنگوها، برآورد، trim) ← `live` ← `closing` ← `ended` (یا `cancelled`؛ جلسه‌ای که ۶ ساعت از وقتش گذشته و شروع نشده `missed`).
- **برآورد و trim:** برآورد = سقف نوبت × (سخنگوها × دورها + چالش مخالف‌خوان + نجوای مشاور) برای هر دستور + خلاصه‌ی منشی (۲۰ هزار). بیشتر از بودجه: اول دور آخر کم‌اهمیت‌ترین دستورها، بعد سخنگوها (به بیانیه‌ی نوشته)، بعد نجوا؛ متن فارسی در `trimmed_fa`. مالک پیش از شروع فقط **کم** میکند (`PATCH`)؛ افزایش فقط `POST …/control` با `raise_budget`، فقط مالک.
- **رزرو و حالت `written`:** موقع شروع، بودجه‌ی جلسه از سقف روزانه‌ی ایجنت‌ها (`AGENT_DAILY_TOKEN_CAP`) و از **سهم روزانه‌ی جلسه‌ها** (`MEETINGS_DAILY_SHARE`، پیش‌فرض `0.15`، در `.env`) رزرو میشود. اگر جا نشود، جلسه `written` است: فقط بیانیه‌های نوشته (رکوردهای خود شرکت، بی‌مدل)، بی‌دور بحث، و مالک یک اعلان `info` میگیرد. `war_room` بیرون از سهم است. llm-router هر دو را هم اجرا میکند (`meta.meeting`، `meeting_cap`، `meeting_kind`: ردیف `rejected_budget` با `meeting_budget` یا `meetings_share`).
  - با سقف روزانه‌ی ۶۰۰ هزار و سهم ۰٫۱۵ (۹۰ هزار در روز)، `board` (۱۲۰ هزار) و `strategy` (۱۵۰ هزار) جا نمیشوند و نوشتاری برگزار میشوند تا مالک بودجه، سقف یا سهم را عوض کند.
- **نوبت‌ها:** هر نوبت یک اجرای ایجنت با trigger `meeting` است (`meetings.queue_turn`). context را کد میسازد: دستور، منبع‌ها، ادعاهای همین دستور (نه کل متن)، حرف مالک، شرکت خود سخنگو؛ هیچ نجوایی. ابزارها: فقط ابزار همان نوبت (`meeting.statement`، `meeting.challenge`، `meeting.whisper`، `meeting.minutes`) و خواندنی‌های نقش؛ effort حداکثر `medium`؛ سقف توکن = سقف نوبت و آنچه از رزرو مانده. نوبتی که جا نشود اجرا نمیشود و جلسه به `closing` میرود.
- **ادعاها** مثل citation بررسی میشوند (در scope خواندن سخنگو): بی‌منبع یا منبع ناخوانا ← `unsourced`؛ چالش‌شده ← `challenged`. فقط ادعای `sourced` به صورت‌جلسه و کارت میرسد. منبع دانش منقضی ← `422 knowledge_expired`.
- **پایان:** صورت‌جلسه را کد میسازد (خروجی `O-…` در هلدینگ، تولیدکننده `HQ-SEC`)؛ منشی (`HQ-SEC`، نقش سیستمی، Haiku) از بودجه‌ی همان جلسه خلاصه مینویسد اگر دست‌کم ۲ هزار مانده باشد. هر پیش‌نویس یک کارت `meeting_resolution` (A1، مالک) میشود؛ فقط مُهر مالک مصوبه‌ی `M-…` و کار پیگیری میسازد.
- **اتاق جنگ:** خط زمانی کدساز (حادثه، رویدادهای کار، Audit)؛ نوبت‌هایش همان اجراهای کار حادثه است (اتاق جنگ نوبت مدلی اضافه نمیسازد). با بسته شدن حادثه بسته میشود؛ اتاقی که با 🔴 بی‌حادثه باز شده بعد از ۶ ساعت. تمام شدن سقف روزانه وسط اتاق جنگ ← یک اعلان `urgent` برای مالک (ناظر سقف را بالا نمیبرد).
- **استندآپ:** کار دیروز هر دپارتمان (انجام‌شده، در جریان، گیرکرده) در رشته‌ی دپارتمان؛ اگر چیزی عوض نشده، هیچ پیامی نمیرود (ردیف `cancelled`/`no_change`). خلاصه‌ی مدلی (`model_summary`) پیش‌فرض خاموش است.
- **پلنر** جلسه‌ها را با `kind: "meeting"` نشان میدهد (بی استندآپ‌ها).

### ۲۹.۲ اساسنامه و الحاقیه‌ها (پرامپت ۱۱ §۲، قرارداد §۲۰.۲)
- نسخه‌ی ۱ هلدینگ از `agents/charter/HOLDING.md` با وضعیت **`proposed`** seed میشود. **فقط مالک** در اپ اصلاح (`PUT /charter/{scope}`) و مُهر میکند (`POST /charter/{scope}/versions/{v}/seal` 🔏 `charter.seal`، target = `body_sha256`).
- `body_sha256` = SHA-256 JSON کانونی `{body_md, red_lines}` (کلیدهای مرتب، بی‌فاصله، UTF-8). سرور آن را دوباره حساب میکند؛ توکن نسخه‌ای با همان متن و خطوط قرمز دیگر رد میشود.
- **سقف طول:** هلدینگ ۶۰۰۰ نویسه، الحاقیه‌ی هر شرکت ۳۰۰۰ (بیشتر ← `422`).
- ایجنت‌ها فقط میخوانند: نسخه‌ی مُهرشده‌ی هلدینگ و الحاقیه‌ی شرکت بعد از `_common` و پیش از منشور نقش در system prompt؛ هر فراخوانی `charter_docs` (مثلاً `["holding@3", "TY@1"]`) در `llm.calls.meta` دارد. تا مُهر نشده، فقط چهار خط قرمز مدل عملیاتی §۱.۱۵ (از همان فایل seed) میرود. هر تلاش ایجنت برای نوشتن `403` و ردیف Audit `charter.write_denied` است. اصلاحیه = کارت `charter_amendment` 🔏؛ پایه‌ی کهنه ← `409 decision_not_pending`.
- **خطوط قرمز `rule`:** روی هر پیام خروجی به مشتری (نگهبان §۱۹.۶، کد `red_line`، بی override) و روی خروجی‌ها، پیام‌ها و استوری‌های ایجنت‌ها (یافته‌ی `PR-115`، متن داخلی نگه داشته نمیشود). خطوط `sample` کار ناظر است.

### ۲۹.۳ دانشنامه‌ی چهارلایه (پرامپت ۱۱ §۳، قرارداد §۲۰.۳)
- لایه‌ها: هلدینگ (همه میخوانند)، شرکت، دپارتمان (همان دپارتمان، مدیرعامل، هلدینگ)، کارمند (= حافظه‌ی کارمند، فقط نمایش). مقاله‌های پشتیبانی پرامپت ۱۰ در لایه‌ی شرکت با kind `support` **فقط دیده میشوند** (view `knowledge.support_entries`، بی کپی)؛ ویرایش فقط در `/support/kb` (از `/knowledge`: `405`).
- **منبع و انقضا اجباری:** دست‌کم یک منبع؛ سقف `valid_until`: `fact` ۹۰ روز، `faq` ۱۸۰، `playbook` و `policy` ۳۶۵، `principle` ۷۳۰ (دیتابیس هم چک میکند).
- **job روزانه** (`hq-knowledge-daily`، ۰۶:۳۰ به وقت مالک): ورودی منقضی ← `expired` (قاعده‌ی خالص، با قفل هم)؛ ۱۴ روز پیش از انقضا یک کار بازبینی برای نگه‌دار لایه (مدیر دپارتمان، مدیرعامل، یا مدیر عملیات AI برای هلدینگ)؛ این کار تا قفل هلدینگ هست ساخته نمیشود.
- **چرخه:** پیشنهاد ایجنت (`in_review`) ← بازبینی (AI safety، وگرنه ناظر کل؛ اول کد: تزریق، رمز، تطبیق با خط قرمز `rule`؛ هر کدام رد شد حکم `reject` است) ← تأیید مدیرعامل همان شرکت (`knowledge.approve`، ردیف ماتریس `knowledge.approve.company`؛ مالک میتواند به خودش برگرداند) یا برای هلدینگ کارت `knowledge_entry` مالک. نوشته‌ی خود مالک با همان کار تأییدشده است.
- ورودی منقضی در جستجوی ایجنت‌ها نیست و به‌عنوان شاهد (`deliver`، ادعای جلسه) `422 knowledge_expired` میگیرد.
- **پروتکل‌های این نیمه:** `PR-111` (دانش)، `PR-114` (قاعده‌های جلسه) با کد؛ `PR-115` (خطوط قرمز) نمونه‌ای و کار ناظر. هر سه با اولین seed بعد از deploy فعال میشوند (نسخه‌ی ۲، ردیف Audit `protocol.activate`)؛ اجرایشان مثل هر پروتکل پشت قفل هلدینگ است.
- **متغیرهای تازه:** `MEETINGS_DAILY_SHARE` (worker و llm-router)؛ `HQ_MEETINGS_SCHEDULES` (پیش‌فرض `on`؛ `off` فقط در تست: schedule‌های `hq-meetings` و `hq-knowledge-daily` ساخته میشوند ولی متوقف میمانند).
### ۲۹.۴ سه کارت و کارت امتیاز زنده (پرامپت ۱۱ §۴، قرارداد §۲۰.۴)
- **جدول‌ها** (migration `0026_1`): `governance.kpis` (تعریف هر KPI برای هر شرکت)، `governance.kpi_values` (سری زمانی، فقط‌افزودنی)، `governance.kpi_sets` (نسخه‌ی If-Match)، `governance.kpi_changes` (هر تغییر تعریف).
- **منبع فقط از رجیستری بسته‌ی کد** (`hq_api/domain/gov_kpis.py`، `REGISTRY`)، هرگز SQL آزاد از داده:
  - سلامت: `health.uptime_24h`، `health.p95_latency_ms`، `health.open_incidents`، `health.tls_min_days`
  - خزانه: `treasury.cost_month_usd`، `treasury.budget_use_pct`، `treasury.cost_per_accepted` (ماه شمسی مالک)
  - کار و نظارت: `work.on_time_rate`، `work.overdue_open`، `oversight.compliance`، `oversight.findings_open_high`، `stars.company_score`
  - از ۱۰: `revenue.commission_7d_usdt`، `revenue.new_invitees_7d`، `funnel.signups_7d`، `funnel.conversion_7d`، `support.csat_30d`
  - خود هلدینگ: `hub.services_up_pct`، `hub.backup_age_hours`، `treasury.agents_cost_month_usd`
  - KPI دستی (`{kind: "manual"}`، مثل `users.active`) فقط با `kpi.record` و منبع `{kind, ref, note}`؛ ثبت‌کننده مدیرعامل یا مدیر همان شرکت.
- **seed:** `apps/api/seed/kpis/standard.yaml` (داده). شرکتی که از تأسیس آمده و `proposal.kpis` دارد، آن‌ها را KPI دستی کارت رشد میگیرد؛ کارت پایداری و ایمنی-هزینه استاندارد میماند. مالک هدف‌ها را در اپ عوض میکند: `PUT /api/v1/kpis/{company}` با `If-Match`.
- **جمع‌آوری:** schedule `hq-kpi-collect` هر ۱۵ دقیقه در worker، **بی‌مدل و بی‌تماس بیرونی**. مقدار فقط وقتی عوض شده یا یک ساعت گذشته ردیف تازه میشود. تا قفل هلدینگ هست هیچ کاری نمیکند (`skipped: holding_locked`).
- **وضعیت‌ها:** `ok`؛ `stale` («قدیمی»: کهنه‌تر از `freshness_hours`، با رویداد `kpi.stale` یک بار در هر دوره)؛ `no_source` («منبع وصل نیست»: منبعی ساخته نشده یا داده‌ای نیست). **عدد نبود هرگز صفر نیست.**
- **کارت هلدینگ:** KPIهای خود هلدینگ به‌علاوه‌ی KPIهای شرکت‌ها، تجمیع‌شده با `aggregate` هر KPI (`sum`، `avg`، `min`، `max`). شرکتی که مقدار ندارد بیرون میماند.
- **امتیاز شرکت** (۳۵٪ «تحقق KPI» فرمول پرامپت ۸): اگر OKR فصل جاری فعال است، پیشرفت وزنی KRها؛ وگرنه سهم KPIهای کارت امتیاز با مقدار و هدف که به هدف رسیده‌اند (`gov_kpis.attainment`).
- **PR-090** فعال است: KPIِ کهنه یک یافته میشود؛ KPIِ بی‌منبع یافته نیست.

### ۲۹.۵ OKR هر شرکت (پرامپت ۱۱ §۵، قرارداد §۲۰.۵)
- فصل شمسی: `1405-Q3` یعنی مهر تا آذر. مدیرعامل در ماه آخر فصل با `okr.draft` (فصل جاری بی‌OKR یا فصل بعد) هدف‌ها و نتیجه‌های کلیدی را مینویسد. نتیجه **یک** کارت `okr` برای مالک است.
- مالک کارت را با اصلاح (`amendments: {key_result_changes: [{ref, target?, weight?, title_fa?}], objective_changes: [{ref, title_fa?}]}`) یا بی‌اصلاح مُهر میکند؛ **فقط مُهر** OKR را `active` میکند و OKRهای فعال قبلی همان فصل بسته میشوند. کارتی که رد، برگشت یا منقضی شد، هدف‌ها را `draft` میکند.
- KR یا به KPI وصل است (مقدار جاری همان KPI) یا سنجه‌ی دستی با `okr.checkin` و شاهد. check-in دست‌کم هر ۱۴ روز؛ دیرکرد = یافته‌ی **PR-116**. پیشنهاد نشدن OKR فصل بعد ۳۰ روز پیش از شروعش هم یافته‌ی PR-116 است.
- `hq-governance-daily` (۰۶:۱۰ به وقت مالک، پشت قفل هلدینگ) در ماه آخر فصل برای هر مدیرعامل یک کار «OKR فصل بعد» میسازد (یک بار).
- `Work.key_result` از `POST /work` و `work.delegate` (کار فرزند KR والد را به ارث میبرد)؛ پلنر برچسب KR را نشان میدهد.

### ۲۹.۶ بازبینی نتیجه‌ی تصمیم‌ها (پرامپت ۱۱ §۶، قرارداد §۲۰.۶)
- `Decision.expected = {metric_fa, kpi?, baseline, target, by_days: 30|60|90}`. برای `proposal`ی که بعد از deploy این پرامپت ساخته شود اجباری است: **۷ روز اول** فقط هشدار `warnings: ["expected_missing"]` روی کارت، بعد `422`. شروع این ۷ روز ردیف `governance.rollout` با کلید `p11.governance` است (زمان اجرای migration). کارت‌های قبلی دست نمیخورند.
- با مُهر، برای روز ۳۰، ۶۰ و ۹۰ (تا `by_days`) ردیف `OR-…` ساخته میشود. در روز موعد (`hq-governance-daily` و PR-006):
  - با KPI: حکم با کد (`met` در هدف، `partly` در نیمه‌ی راه یا بیشتر، وگرنه `missed`)، وضعیت `verified`.
  - بی‌KPI: `unmeasurable`؛ پیشنهاددهنده `outcome.note` با شاهد میدهد؛ ناظر در PR-006 با `protocol.result` و فیلد `outcomes: [{ref, verdict, note_md}]` حکم میدهد. یادداشتی که ۷ روز بعد از موعد نیامده یافته‌ی PR-006 است.
- دقت پیش‌بینی هر پیشنهاددهنده: `GET /api/v1/outcomes/accuracy` = (met + partly/۲) / حکم‌شده‌ها.
- هیچ اجرای قبلی PR-006 حکمی ثبت نکرده بود (هلدینگ قفل بوده)، پس داده‌ای برای انتقال نبود.

### ۲۹.۷ ماتریس اختیار (پرامپت ۱۱ §۷، قرارداد §۲۰.۷)
- ردیف‌ها در `governance.authority` (بی‌شرکت، پیکربندی هلدینگ)، seed از `apps/api/seed/authority.yaml`. seed ردیف‌های قفل را هر بار از کد بازنویسی میکند؛ `actor` و `limit` ردیف‌های باز مال مالک است و میماند.
- **ثابت‌های قفل** (`locked: true`، از کد، غیرقابل تغییر):
  - `a4.never`: A4 هرگز برای هوش مصنوعی.
  - `a3.owner_only`: A3 فقط مالک. **ارسال پیشاپیش مُهرشده** (قاعده‌ی `lifecycle_rule` مُهرشده با قالب مُهرشده‌ی جاری، `auto_send` کانالی که با `support_go_live` زنده شد) تأیید A3 خود مالک است و مجاز میماند؛ rego و کد این را از خود مُهرها میخوانند، نه از ماتریس.
  - `a3.ceo_content_calendar`: انتشار پست تقویم محتوا با مدیرعامل خاموش است تا تقویم محتوا ساخته شود.
  - `decision.proposer_not_approver`، `control.release_owner_only` (کلید توقف و hold)، `authority.owner_only` (هیچ ایجنتی ماتریس را تغییر نمیدهد)، `batch.never`.
- **ردیف‌های باز و پیش‌فرض‌ها:** `hire.per_day` ۵ (۰ تا ۲۰)، `ceo.attention_per_day` ۶ (همان `owner.settings.ceo_daily_attention`)، `notify.urgent_per_hour` ۵ (۱ تا ۳۰)، `story.per_day` ۳ (۰ تا ۱۰)، `deploy.blackout_days` جمعه، `decision.recurring_approval.ceo` و `knowledge.approve.company` (مدیرعامل؛ مالک با `actor: "owner"` پس میگیرد)، `batch.max_usd` ۲ دلار (۰ تا ۲۰)، `batch.max_items` ۲۰ (۱ تا ۵۰)، `batch.kinds`.
- **تغییر:** مالک `PUT /api/v1/authority` 🔏 `authority.update` روی SHA-256 بدنه، `{rules: [{key, actor?, limit, version}]}`. ردیف قفل یا عدد بیرون از `bounds` → `422`؛ نسخه‌ی کهنه → `409`. ایجنت‌ها فقط کارت `authority_change` 🔏 پیشنهاد میدهند و `authority.read` ردیف‌های شرکت خودشان را میخوانند.
- **OPA:** api ردیف‌ها را به `data.hq.authority` میفرستد (`PUT /v1/data/hq/authority`، تنها نوشتن داده‌ای که `system.authz` اجازه میدهد): در اولین استفاده، بعد از هر تغییر، و هر وقت digest نسخه‌ی OPA (`POST /v1/data/hq/limits/version`) با پایگاه داده نخواند (مثلاً بعد از ری‌استارت OPA؛ حداکثر هر ۶۰ ثانیه در هر پروسه). package `hq.limits` هر عدد را در `bounds` فایل (`data.json` → `authority_bounds`، `authority_lists`، `never_batch`) نگه میدارد؛ پس داده‌ی جعلی فقط داخل همان مرزها حرکت میکند و ثابت‌های قفل اصلاً این داده را نمیخوانند.
- **مرزها دو جا هستند** (seed و `infra/opa/policy/data.json`)؛ اگر یکی عوض شد، دیگری هم (تست `test_the_bounds_of_the_files_agree` همین را میسنجد).

### ۲۹.۸ دفتر ریسک (پرامپت ۱۱ §۸، قرارداد §۲۰.۸)
- `RK-…`، امتیاز = احتمال × اثر. نگه‌دار: بازرس کل (QC). سقف `review_at`: امتیاز ۱۵+ ← ۱۴ روز، ۸+ ← ۳۰، بقیه ۹۰.
- `hq-governance-daily`: پذیرش منقضی ← `open`؛ بازبینی دیرکرده ← یک کار برای پاسخ‌گو (یک بار برای هر موعد)؛ یافته‌ی `critical` هفته‌ی اخیر ← پیش‌نویس ریسک (`draft: true`). **PR-112** بعد از آن یافته میسازد، و برای ریسک ۱۵+ بی‌راه کاهش و بی‌پذیرش.
- پذیرش فقط با کارت `risk_acceptance` 🔏، حداکثر ۹۰ روز. بستن فقط با بازرس (یا مالک)؛ پاسخ‌گو خودش نمیبندد.
- کالبدشکافی پیش‌نویس ریسک را با `gov_risks.draft_risk(..., origin="postmortem")` میسازد (نقطه‌ی ورود نیمه‌ی دیگر پرامپت).

### ۲۹.۹ تقویم تغییرات و انتشارها (پرامپت ۱۱ §۹، قرارداد §۲۰.۹)
- `CE-…`. کد پرش میکند: کارت deploy با `window` (پیش از ساختن کارت؛ `head_sha` از این پرامپت اجباری)، فریزها، پشتیبان شبانه‌ی هاب (۰۲:۳۰ UTC) و تست بازیابی هفتگی (یکشنبه ۰۶:۰۰ تهران)، جلسه‌ها (بی استندآپ‌ها؛ یک ساعت، `auto_key` = `meeting:MT-…`؛ جلسه‌ی `missed` از تقویم کنار میرود؛ پلنر خود جلسه را نشان میدهد، نه این رویداد را)، تعطیلات رسمی (`apps/api/seed/calendar/holidays.yaml`). کمپین و رویداد با `calendar.add` (مدیرعامل، مدیر رشد شرکت خودش، سرپرست‌های هلدینگ) یا مالک.
- **تعطیلات:** روزهای خورشیدی دقیق‌اند؛ روزهای قمری تخمین جدولی‌اند و ممکن است یک روز با تقویم رسمی فرق کنند. هر سال با تقویم رسمی چک و فایل را اصلاح کن (seed فقط روز تازه اضافه میکند؛ روز اشتباهِ ثبت‌شده را با `PATCH /api/v1/calendar/{ref}` جابه‌جا یا `cancelled` کن).
- **تداخل‌ها** (کد): انتشار داخل فریز و انتشار هم‌زمان با کمپین یا رویداد همان شرکت `high`؛ دو انتشار یک شرکت یا یک repo، روز ممنوع ماتریس، تعطیلی و نگه‌داری هم‌زمان `medium`. روی کارت در `payload.calendar_conflicts` و `risk_note` میآید و رویداد `calendar.conflict` میفرستد. **تقویم تصمیم نمیگیرد**؛ **PR-113** انتشار تأییدشده‌ی بی‌پنجره یا با تداخل `high` را یافته میکند.
- پلنر رویدادهای تقویم را هم نشان میدهد (`kind: "calendar"`)؛ پلنر همچنان نما است.

### ۲۹.۱۰ مُهر گروهی کارت‌های کم‌ریسک (پرامپت ۱۱ §۱۰، قرارداد §۲۰.۱۰)
- **فهرست مجاز** (ردیف `batch.kinds`، مالک فقط کوتاه‌ترش میکند): `proposal`، `meeting_resolution`، `knowledge_entry`. شرط‌های دیگر: A1، ریسک low، برگشت‌پذیر، pending، تأییدکننده مالک، بی‌hold، بی‌اصلاح، `quota_estimate.usd ≤ batch.max_usd` (کارتی که برآورد توکن دارد ولی دلار ندارد شایسته نیست).
- **هرگز گروهی** (ثابت قفل `batch.never`): هر A3، `hire`، `dismissal`، `budget_change`، `code_session`، `server_plan`، `deploy`، `company_found`، `tool_enable`، `protocol`، `errand_action`، `evaluation`، `charter_amendment`، `authority_change`، `risk_acceptance`، `okr`، `recurring_approval`، `lesson_adoption`، `message_template`، `lifecycle_rule`، `support_go_live`.
- `GET /api/v1/decisions/batchable` ← `POST /api/v1/decisions/batch/approve` 🔏 `decision.batch` روی SHA-256 JSON کانونی `[{ref, version}]` مرتب‌شده بر اساس ref (`Idempotency-Key` اجباری). همه یا هیچ: `422 batch_not_eligible` با `fields.items: [{ref, reason}]`. هر کارت مصوبه، ردیف Audit (`batch: B-…`) و interaction خودش را دارد.

### ۲۹.۱۱ دروازه‌ی راه‌اندازی برای کارهای حاکمیت (پرامپت ۱۱ §۴ تا §۱۰)
- `hq-kpi-collect` و `hq-governance-daily` اول `gate.holding_lock` را میپرسند و تا کلید توقف هلدینگ روشن است **هیچ کاری** نمیکنند (نه ردیف، نه کار، نه مدل، نه تماس بیرونی). هیچ‌کدام مدل صدا نمیزند.
- PR-006، PR-090، PR-112، PR-113 و PR-116 مثل همه‌ی پروتکل‌ها در قفل هلدینگ `skipped` میشوند (بی‌ردیف اجرا).
- کاری که این jobها میسازند (بازبینی ریسک، OKR فصل بعد) تنها چیزی است که میتواند ایجنتی را بیدار کند، و فقط وقتی قفل نیست.
