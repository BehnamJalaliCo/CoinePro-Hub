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
| `make connection-secret KEY=<key>` | **فقط مالک، در ترمینال خودش** (پرامپت ۱۲ §۹): کلید API یک اتصال LLM تازه (ورودی پنهان، مستقیم به OpenBao)؛ روتر بی خرج توکن وارسیش میکند (§۳۰.۳) |
| `make chatgpt-login`، `make gemini-login` | **فقط مالک، در ترمینال خودش:** ورود CLI بازیکن ذخیره (Codex با کد دستگاه، Gemini با کد تأیید)؛ همین از اپ هم هست (§۳۰.۴) |
| `make chatgpt-web-login`، `make gemini-web-login`، `make deepseek-web-login` | **فقط مالک، با تونل SSH خودش:** ورود یک‌باره در پروفایل مرورگر هاب؛ noVNC فقط روی `127.0.0.1:6080`، حداکثر ۱۵ دقیقه (§۳۰.۴) |
| `make tts-on`، `make tts-off`، `make tts-bench` | صدای فارسی گزارش‌ها (پرامپت ۱۲ §۴): روشن و خاموش کردن profile اختیاری `tts` و timer آن (بیرون از بودجه‌ی حافظه رد میشود)، و اندازه‌گیری RTF و RAM روی متن ثابت (§۳۰.۱۱، حافظه‌ی همه‌ی profileها در §۳۰.۶) |
| `make tts-bakeoff [OUT=…]` | bake-off صدا (پرامپت ۱۳ §۴): هر صدای image روی متن‌های ثابت، RTF و peak هر ساخت، Ogg در `OUT`؛ بی‌شبکه (§۳۱.۱۳) |
| `make account-secret KEY=mail` | **فقط مالک:** رمز صندوق ایمیل مشاور حقوقی (پرامپت ۱۳ §۳؛ §۳۱.۱۲) |
| `make mcp-build`، `make mcp-test`، `make mcp-index` | MCP روی کانتینر (پرامپت ۱۲ §۱۴): ساخت تکرارپذیر imageها با digest فهرست مجاز، آزمون روی شبکه‌ی دورانداختنی، ایندکس CodeCortex (§۳۰.۵) |
| `make media-on`، `make media-off`، `make media-bench` | render worker استودیوی رسانه (پرامپت ۱۳ §۲.۳): روشن و خاموش کردن profile اختیاری `media` و timer آن (بیرون از بودجه‌ی حافظه رد میشود)، و اندازه‌گیری یک ریلز ۳۰ ثانیه‌ای، یک عکس Lottie و یک صفحه‌ی طراحی در همان سندباکس بی‌شبکه (§۳۱.۵) |
| `make account-secret KEY=telegram-<co>`، `KEY=instagram-<co>` | **فقط مالک، در ترمینال خودش:** توکن ربات کانال تلگرام و توکن حساب business اینستاگرام هر شرکت برای انتشار رسمی (§۳۱.۶) |
| `make ocr-fetch [set=fast\|best]` | OCR بایگانی (پرامپت ۱۴ §۴): یک‌بار دانلود traineddataی پین‌شده‌ی `fas` و `eng` در volume ‏`ocr-models` با sha256 (§۳۲.۴) |
| `make ocr-on`، `make ocr-off`، `make ocr-bench`، `make ocr-test` | روشن و خاموش کردن profile اختیاری `ocr` (بیرون از بودجه‌ی حافظه رد میشود)، اندازه‌گیری و آزمون Tesseract واقعی روی نمونه‌ی اسکن فارسی، بی‌شبکه (§۳۲.۴) |

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
  3. **روشن کردن** با `POST /api/v1/tools/mcp/<key>/enable` و 🔏 `mcp.enable` روی `key`. سرور `container` از پرامپت ۱۲ اجراشدنی است، فقط دقیقاً همان‌طور که فهرست مجاز میگوید و فقط وقتی پروفایل `mcp` روشن است (وگرنه `409 not_ready`): §۳۰.۵.
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
  - از پرامپت ۱۲ شبکه‌ی `hq-mcp`، پل stdio→HTTP و فهرست مجاز بازبینی‌شده ساخته شده‌اند (پروفایل اختیاری `mcp`، پیش‌فرض خاموش): §۳۰.۵.
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
## ۳۰. ابزار مدیریت (پرامپت ۱۲؛ قرارداد §۲۱)
بخش A ‏(§۱، §۹، §۹.۱، §۱۴، §۱۵) در ۳۰.۱ تا ۳۰.۷، سه بخش ساخته‌شده روی پرامپت ۱۱ (§۲، §۳، §۱۳) در ۳۰.۸ تا ۳۰.۱۰، و بخش B ‏(§۴ تا §۸، §۱۰ تا §۱۲) در ۳۰.۱۱ تا ۳۰.۱۸.
- **migration ‏`0027`** (`0027_management_tools_a.py`): دو schema تازه، `advisor` (یادداشت‌ها و محرک‌ها) و `substitutes` (بازیکن‌ها، جایگاه‌ها، فراخوانی‌ها، ورودها، creativeها). همه‌ی جدول‌ها `company_id` و RLS **FORCE** دارند؛ ردیف‌های مالک و هلدینگ با `company_id` هلدینگ. هیچ نوع کارت تازه‌ای اضافه نمیشود.
  - همچنین: بلوک‌های `advisor` و `substitutes` در `owner.settings`، ستون `work.work.run_meta` (task class اجرا و پرچم سهم مالک، فقط با کدی که کار را میسازد)، وضعیت‌های تازه‌ی `llm.connections` (`pending_secret`، `verifying`، `ready`، `error`) و نوع `subscription`، task classهای تازه، سه اتصال بازیکن ذخیره و سه حساب پروفایل مرورگر.
- **migration ‏`0027_1`** (`0027_1_management_reports.py`، بخش B، بعد از `0027`): schemaهای `reports` و `quality` و جدول‌های تازه‌ی `people`، `llm` و `owner` (۳۰.۱۱ تا ۳۰.۱۸).
  - **زنجیره (روی پرامپت ۱۱):** `0025` ← `0026` ← `0026_1` ← `0027` ← `0027_1` ← `0027_2` (۳۰.۸).
    `0027` حالا روی `0026_1` پرامپت ۱۱ مینشیند.
- **دروازه‌ی راه‌اندازی:** هیچ چیزی از این بخش تا کلید توقف هلدینگ روشن است مدل یا سرویس بیرونی صدا نمیزند:
  - یادداشت خودکار ساخته نمیشود و درخواست مالک ← `423 company_locked`.
  - هر محرک تازه `deferred` (با `holding_locked`) ثبت میشود؛ خود قاعده‌ها فقط دیتابیس میخوانند.
  - هر فراخوانی بازیکن ذخیره `skipped` میشود؛ `claim` هیچ کاری نمیدهد؛ worker هیچ کار وبی اجرا نمیکند.
  - وارسی اتصال تازه صبر میکند (`verifying`).
- **تصمیم‌های منتظر مالک (§۰.۸)، پیش‌فرض‌ها تا جواب او:** یادداشت خودکار روشن، حداکثر ۳ در روز؛ گزارش فعال ۳ در روز؛ `OWNER_ZONE_DAILY_SHARE=0.25`؛ رمز اتصال تازه از هر دو راه (`CONNECTION_SECRET_ROUTE=api`)؛ جایگاه‌ها و سقف‌های جدول §۹.۱، همه روشن؛ بازیکن پیش‌فرض عکس `gpt`؛ عکس و ویدیو فقط از مسیر وب؛ هیچ پروفایل اختیاری (MCP، runner، مرورگر وب) روشن نمیشود تا مالک بگوید.

### ۳۰.۱ مشاور پریمیوم: یادداشت تصمیم، مخالف‌خوان، گزارش فعال (§۱، قرارداد §۲۱.۱)
- **یادداشت تصمیم** (`advisor.memos`، شماره‌ی `DM-0001`):
  - **درخواست مالک:** `POST /api/v1/decisions/{ref}/memo {mode: standard|devil}` ← `202`. همان کارت، mode و `version` همان یادداشت را برمیگرداند. کارت تصمیم‌گرفته ← `409 decision_not_pending`.
  - **خودکار:** sweep مشاور در worker (`hq-advisor-sweep`، هر ۲ دقیقه) برای کارت‌های امروزِ مالک با `risk: high` یا نوع `deploy`، `company_found` یا `server_plan` یادداشت میسازد، به ترتیب ساخت و حداکثر `owner_settings.advisor.auto_memo.max_per_day` (۳) در روز مالک. اضافه‌ها به فردا نمیروند؛ فقط دکمه‌ی درخواست میماند.
  - **اجرا:** یک کار برای `HQ-ADV` با بودجه‌ی ۸۰ هزار توکن، task class ‏`advisor_memo` و `owner_zone` برابر `auto` یا `direct`. بسته‌ی شاهد (کارت، ماسک‌شده) در brief است و در `advisor.memos.facts` میماند.
  - **`memo.write`** (A1، فقط مشاور، فقط کارت `pending` و همان `version`): `against_md` خالی ← ۴۲۲؛ نسخه‌ی دیگر کارت ← `409 version_conflict`؛ هر ارجاع سمت سرور سنجیده میشود و ارجاع ساختگی حذف و در `citations_dropped` شمرده میشود. کار یادداشت با شاهد `DM-…` بسته میشود.
  - **کارت قفل است:** trigger پایگاه‌داده (`advisor.stale_on_change`) یادداشت کارتی را که هنوز `pending` است و عوض شده `stale` میکند (ستون‌های دفتری مثل `reminded_at` حساب نیستند). نسخه‌ی تازه یادداشت تازه میگیرد؛ خودکار فقط اگر شرط خودکار برقرار باشد.
  - یادداشتی که اجرایش بی `memo.write` تمام شد، بعد از ۵ دقیقه `failed` میشود.
  - **نظر دوم و سوم:** کنار هر یادداشت، با کد، دو فراخوانی بازیکن ذخیره روی همان بسته‌ی شاهد ماسک‌شده و **بی دیدن یادداشت**: جایگاه `advisor_second_opinion` (GPT) و `third_opinion` (DeepSeek). `agrees` با کد است (همان `recommendation`). بازیکن خاموش، خارج‌شده یا بالای سقف روزانه ← نظر `null`.
- **مخالف‌خوان:** پیام مالک در رشته‌ی `A` با `mode: "devil"` (در هر رشته‌ی دیگر ← ۴۲۲). runner دستور مخالف‌خوان را فقط برای همان اجرا به system prompt مشاور اضافه میکند و جواب `meta.mode: "devil"` میگیرد.
- **گزارش فعال** (`advisor.triggers`): محرک‌ها با کد و بی مدل: بودجه‌ی ماه ≥ ۹۰٪، سهمیه‌ی اشتراک بیش از ۲ ساعت `limited`، افت انطباق ≥ ۱۰ امتیاز در یک روز، حادثه‌ی `sev1` باز بیش از ۳۰ دقیقه، هشدار افت کمیسیون رادار درآمد، ≥ ۳ کارت منتظر بیش از ۷۲ ساعت، یافته‌ی `critical` باز بیش از ۲۴ ساعت، و KR عقب از OKR (بعد از merge پرامپت ۱۱؛ تا جدولش نیست، چیزی نمیسازد).
  - `key` هر محرک در هر روز یکتاست؛ همان محرک دوباره مشاور را بیدار نمیکند.
  - مشاور با واقعیت‌های از پیش جمع‌شده بیدار میشود (۵۰ هزار توکن، `advisor_proactive`) و یک پیام کوتاه در `A` مینویسد (`meta.proactive: {kind, key}`) با یک اعلان سطح `report`؛ **هرگز `urgent`**.
  - سقف `owner_settings.advisor.proactive_per_day` (۳)؛ بقیه `capped`. قفل هلدینگ یا پر بودن سهم مالک ← `deferred`.
- **API:** `GET /decisions/{ref}/memo?mode`، `GET /advisor/memos?decision&cursor`، `GET /advisor/triggers?since&kind`؛ `Decision.memos`. stream: `memo.ready` و `advisor.proactive` روی topic ‏`advisor`.

### ۳۰.۲ سهم توکن مالک و task classهای تازه (§۱۵، قرارداد §۲۱.۰)
- **`OWNER_ZONE_DAILY_SHARE`** (در `.env`، خالی یعنی `0.25`): کارهای **خودکار** منطقه‌ی مالک (یادداشت خودکار، گزارش فعال، خلاصه‌ی مرور هفتگی، کتابدار، پیش‌بینی و اصول مدیر کل دیجیتال) روی هم حداکثر این سهم از `AGENT_DAILY_TOKEN_CAP` را در روز UTC مصرف میکنند (با ۶۰۰ هزار: ۱۵۰ هزار).
  - LLM Router مثل سهم نظارت اجرایش میکند: فراخوانی task classهای منطقه با `meta.owner_zone` غیر از `direct` بعد از پر شدن سهم ← `429 budget_exhausted` (در دفتر `rejected_budget` / `owner_zone_share`). فراخوانی بی پرچم هم خودکار حساب میشود (سمت امن).
  - **درخواست مستقیم مالک** (یادداشت به درخواست، پرسش، پیام) همیشه اجرا میشود، داخل سقف کل، و در منطقه شمرده میشود.
  - api هم پیش از ساختن کار خودکار همین را میپرسد: یادداشت خودکار ساخته نمیشود و محرک `deferred` میشود.
- **task classهای تازه** (seed روتر و migration ‏0027): `advisor_memo`، `advisor_proactive`، `advisor_review`، `ask_hub`، `ceo_letter`، `hr_eval`، `dceo_predict`، `dceo_principles`؛ و برای بازیکن‌های ذخیره `sub_code_review`، `sub_second_opinion`، `sub_cross_check`، `sub_errand`، `sub_draft`، `sub_long_read`، `sub_creative` (فقط در دفتر، با هزینه‌ی معادل؛ روتر هرگز آن‌ها را اجرا نمیکند).
  - task class اجرای ایجنت از `work.work.run_meta` میآید (فقط کلاس‌های همین فهرست؛ هرگز انتخاب ایجنت).
- **بازیکن‌های ذخیره** از هیچ سقف یا سهم Claude نمیخورند: سقفشان سهمیه‌ی اشتراک و سقف روزانه‌ی هر جایگاه است.

### ۳۰.۳ افزودن اتصال تازه (§۹، قرارداد §۲۱.۷)
- **ساخت:** `POST /api/v1/connections` با 🔏 `connection.create` روی SHA-256 بدنه و `Idempotency-Key` اجباری: `{key, provider, kind, display_name, base_url?, models[], default_model?, pricing{}, limits{}, fallback_priority?}`.
  - provider فقط `anthropic`، `openai`، `google`، `deepseek`، `mistral` یا `openai_compatible`. `base_url` فقط برای `openai_compatible`، فقط `https` و نه آدرس خصوصی، loopback یا داخلی هاب (مثلاً `10.10.1.2` ← ۴۲۲). key تکراری ← `409 version_conflict`.
  - `kind: subscription` اینجا ساخته نمیشود (`409 not_ready`): اشتراک‌ها با CLI خودشان کار میکنند و اشتراک‌های بازیکن ذخیره seed شده‌اند.
  - نتیجه `pending_secret` است. اتصال تازه فقط با `PUT /assignments` 🔏 به کار میرود؛ تا وارسی نشده، روتر هیچ فراخوانی به آن نمیدهد و `PATCH status: enabled` ← `409 not_ready`.
- **رمز، از دو راه:**
  - مسیر API موجود `POST /connections/{id}/secret` 🔏 `connection.secret` (write-only) اتصال تازه را به `verifying` میبرد.
  - ترمینال خود مالک: `make connection-secret KEY=<key>` (ورودی پنهان، مستقیم به OpenBao در `kv/llm-connections/<key>`). Claude سرور هرگز آن را اجرا نمیکند.
  - با `CONNECTION_SECRET_ROUTE=terminal` (تصمیم مالک) مسیر API برای اتصال تازه `409 validation_failed` میدهد و دستور ترمینال را میگوید.
- **وارسی:** روتر هر `LLM_CONNECTION_VERIFY_INTERVAL_S` (۳۰ ثانیه) اتصال‌های `pending_secret` را که رمزشان رسیده `verifying` میکند و هر `verifying` را با فهرست مدل‌های همان ارائه‌دهنده (`GET .../models`) میسنجد، **بی خرج هیچ توکنی** ← `ready` (با `verified_at`) یا `error` با `status_reason` کوتاه.
  - پیش از تماس، نام میزبان resolve میشود و آدرس غیرعمومی رد میشود (قاعده‌ی محافظ egress).
  - تا کلید توقف هلدینگ روشن است هیچ تماسی نمیرود.
  - هیچ پاسخ، لاگ، رویداد یا ردیف Audit رمز را ندارد.

### ۳۰.۴ بازیکن‌های ذخیره: ChatGPT، Gemini و DeepSeek (§۹.۱، قرارداد §۲۱.۱۳)
#### api، worker و ابزار ایجنت
- **قاعده‌ی نیمکت در کد:** هر فراخوانی جایگاه یک سؤال محدود است، با برچسب `source {player, model, connection, at}`، و **هرگز شاهد نیست** (هیچ مسیر نوشتنی ندارد و رکورد قابل ارجاع نیست). ورودی ماسک‌شده است؛ داده‌ی شخصی یا رمز (حتی داخل base64/hex) ← `policy_denied`. `quick_search` از کل محافظ `web.search` رد میشود (هیچ نام، ref یا کد کارمند داخلی). کد ریپو فقط در `code_review`.
  - **هیچ جابه‌جایی پنهانی نیست:** بازیکن `limited`، خارج‌شده، منقضی یا `off`، یا جایگاهی که سقف روزانه‌اش پر است ← فراخوانی `skipped` (در `month.skipped`) و صداکننده با مدل خودش ادامه میدهد. اجرای Claude هرگز به بازیکن ذخیره نمیرود و برعکس.
  - این فراخوانی‌ها از هیچ سقف یا سهم Claude نمیخورند؛ هر کدام یک ردیف در `llm.calls` (caller ‏`substitutes`، task class ‏`sub_*`) با هزینه‌ی معادل از جدول قیمت اتصال میگیرند. جدول قیمت اتصال‌های بازیکن ذخیره خالی است تا مالک پر کند؛ تا آن موقع `equiv_usd` صفر است و اعلان «عقب ماندن» نمیآید.
- **صف کارها (api):** `substitutes.calls` هم صف CLI است و هم صف وب.
  - CLI: `POST /internal/v1/substitutes/jobs/claim` (فقط principal سرویسی `substitutes`؛ یک کار در لحظه برای هر دو؛ تا قفل هست هیچ کاری) و `.../jobs/{id}/done` (idempotent). سهمیه‌ی تمام‌شده ← بازیکن `limited` با `limited_until` و جایگاه `skipped`. جوابی که بعد از `queued` رسید به‌صورت یک کار برای ایجنت صداکننده برمیگردد.
  - وب: worker (`hq-substitute-web`، هر دقیقه) کارهای وب را از `POST egress /v1/substitutes/web` اجرا میکند: یکی در لحظه برای هر بازیکن و دست‌کم ۶۰ ثانیه فاصله؛ تا قفل هست هیچ. پروفایل منقضی ← `web.state: expired`، کارهای منتظرش `skipped` و **یک** اعلان `report`. recipe شکسته ← فراخوانی `failed` با شماره‌ی قدم، و اگر SRE پلتفرم هلدینگ استخدام شده باشد یک کار fallback برای او.
- **جایگاه‌ها:** از جدول §۹.۱ seed شده‌اند (همه روشن، جز `code_review` جمنای). `PUT /api/v1/substitutes/{player}/seats` با 🔏 `substitute.seats` روی هش بدنه و `If-Match`؛ جایگاهی که در فهرست نیست خاموش میشود؛ `creative` و همه‌ی جایگاه‌های DeepSeek فقط `via: web`.
  - مدل‌ها داده‌اند: روزی یک بار (`hq-substitute-daily`، ۰۹:۱۵ تهران) برای هر بازیکن CLI واردشده یک کار `models` (Gemini: یکی برای هر مدل). مدلی که CLI نمیدهد `available: false` و جایگاهش به نزدیک‌ترین مدل موجود همان ردیف میرود؛ گزارش صبحگاهی میگوید.
  - روز ۱۵ ماه شمسی، بازیکن پولی واردشده‌ای که `value_ratio` آن زیر `owner_settings.substitutes.behind_ratio` (۰٫۴) است یک اعلان `report` میگیرد؛ هیچ چیز خودش گسترده نمیشود.
- **creative (عکس و ویدیو، `CR-0001`):** `POST /api/v1/creatives` (مالک، `Idempotency-Key`؛ prompt با قالب خود هاب از brief و جای انتشار، با «هیچ متنی در تصویر نباشد») یا `substitute.call` با `seat: creative` (prompt را ایجنت مسئول مینویسد).
  - دانلود از پردازش §۱۷.۱ رد میشود (نوع از روی بایت‌ها، حذف EXIF در child، سقف اندازه). **متن فارسی را خود هاب میگذارد:** IRANYekanX، راست‌به‌چپ، رنگ و نشان برند شرکت، داخل حاشیه‌ی امن همان جای انتشار (مثلاً استوری اینستاگرام: ۱۴٪ بالا و ۲۰٪ پایین خالی)، با resvg در child ← `composed` ← `review`. فونت از `design/fonts/static` فقط‌خواندنی (`HQ_FONTS_DIR`) در worker.
  - مالک `accept` یا `reject` میکند. **پذیرفتن یعنی انتشار نیست:** انتشار در کانال یا استوری کار بیرونی است و کارت A3 میخواهد.
- **ورود CLI از اپ:** `POST /api/v1/connections/{id}/login` با 🔏 `connection.login` روی id؛ تا runner خاموش است (یا برای DeepSeek) ← `409 not_ready` با دستور ترمینال. `GET .../login/{login_id}` برای poll؛ `POST .../login/{login_id}/code` فقط برای `auth_code`، write-only، حداکثر ۱۰ دقیقه، یک بار به runner داده و پاک میشود؛ در هیچ پاسخ، لاگ یا Audit نیست. خروج: `POST /connections/{id}/logout` 🔏 `connection.logout`؛ پاک کردن پروفایل وب: `POST /substitutes/{player}/web/logout` 🔏 `substitute.web_logout` (egress در دور بعد worker پاکش میکند).
- **ابزار `substitute.call`** (A0): مشاور، ناظر، دستیار و مدیرعامل‌ها در جایگاه‌های خودشان و فقط در شرکت خودشان؛ مدیر فنی و QC فقط `code_review` (OPA ‏`advisor_substitutes.rego`). تا قفل هست ← ۴۲۳. ردها: `channel_not_configured`، `rate_limited`، `policy_denied`.
- **بازبینی دوم کد:** یافته‌ها `verified: null` میمانند تا مدیر فنی یا QC بسنجد؛ هیچ یافته‌ی سنجیده‌نشده‌ای به `risk_note` کارت نمیرسد و تأیید کارت با یا بی آن همان است.

#### runner، dispatcher، مرورگر وب و ورود
- **همه خاموش است تا مالک بگوید:** دو profile اختیاری `substitutes` (runner CLIها) و `substitutes-web` (پروفایل‌های لاگین‌شده‌ی مرورگر) با `HQ_SUBSTITUTES=on` و `HQ_SUBSTITUTES_WEB=on` در `.env` روشن میشوند. `hq.sh` هر کدام را که با بودجه‌ی حافظه جا نشود رد میکند (exit 3)، مثل STT. api فقط وقتی runner روشن است `SUBSTITUTES_RUNNER=on` میگیرد (`hq.sh --print-substitutes-runner`). کلید توقف هلدینگ هم هر کار را متوقف میکند: api تا قفل هست هیچ کاری تحویل نمیدهد.
- **runner:** image `coinepro-hq/substitutes` با OpenAI Codex CLI ‏0.160.0 و Google Gemini CLI ‏0.63.0 (هر دو Apache-2.0، از `services/substitutes/cli/package-lock.json` با hash). هر فراخوانی یک container یک‌بارمصرف است: Job روی stdin، prompt روی stdin خود CLI (هرگز در argv)، خروجی خط‌های JSON.
  - ابزارهای خود CLI خاموش‌اند: Codex با `--sandbox read-only` در پوشه‌ی خالی tmpfs؛ Gemini با فایل تنظیمات سیستمی `/etc/gemini-cli/settings.json` که هیچ core tool ثبت نمیکند. فقط بازبینی کد (`code_review`) checkout فقط‌خواندنی را با ابزارهای خواندن فایل میبیند (`review.json`).
  - ورود CLIها فقط در volume `hq-substitute-auth` است (فایل‌ها ۶۰۰، بیرون از backup). اگر گم شد، مالک دوباره وارد میشود.
- **dispatcher:** `infra/substitutes/dispatch.sh` با `coinepro-hq-substitutes.timer` هر ۲۰ ثانیه، به نام کاربر Hub (نصب با `make install-systemd`). وقتی خاموش است همان لحظه بیرون میرود.
  - یک کار در لحظه برای هر دو بازیکن (flock). با یک container موقت curl روی `hq-internal` کار را از `POST /internal/v1/substitutes/jobs/claim` میگیرد؛ توکنش (`kv/hq-api/config` → `service_tokens.substitutes`، خود توکن فقط در `~/.secrets/substitutes/api-auth` با دسترسی ۶۰۰) هرگز در خط فرمان نیست. `make up` یک بار آن را میسازد؛ بعدش api را restart کن.
  - بازبینی کد: `git archive` همان `head_sha` از clone خود هاب (`HQ_SUBSTITUTE_REPOS`، پیش‌فرض `coinepro-hub=/home/Hub/CoinePro-Hub`)، فایل‌هایی که اسکن رمز (`hq_common.secret_files`) پیدا میکند کامل حذف، و mount فقط‌خواندنی. ریپو یا commit ناشناخته ← `no_access`.
- **hostهای egress (فقط CONNECT روی 443):** runner روی `hq-subs` فقط به listener ‏`:3131` میرسد: `chatgpt.com`، `auth.openai.com`، `cloudcode-pa.googleapis.com`، `oauth2.googleapis.com`، `www.googleapis.com` (با زیردامنه‌ها؛ `EGRESS_SUBSTITUTES_HOSTS`). `api.openai.com` نه. مرورگر پروفایل روی `hq-browser-web` فقط به `:3132` میرسد و هر کار فقط به hostهای recipe خودش. پنجره‌ی ورود روی `hq-web-login` فقط به `:3133` (hostهای خود سایت‌ها و ورودشان).
- **probe قابلیت‌ها (کار `models`):** Codex فهرست مدل‌های حساب را میدهد (`codex debug models`)؛ Gemini فهرستی ندارد و هر کار یک مدل را با یک کلمه امتحان میکند. فقط وقتی ورود هست و قفل نیست، و از سهمیه‌ی اشتراک (نه توکن Claude).
- **ورود CLIها (فقط مالک، در ترمینال خودش):** `make chatgpt-login` (کد دستگاه: لینک و کد را روی گوشی میزنی) و `make gemini-login` (لینک را باز میکنی و کد را برمیگردانی، بعد `/quit`). همین از اپ هم هست (تنظیمات ← اتصال‌ها، با step-up). خروج از اپ: `POST /connections/{id}/logout` 🔏.
- **مرورگر وب و ورود یک‌باره (فقط مالک):** `make chatgpt-web-login`، `make gemini-web-login` یا `make deepseek-web-login`.
  - پروفایل در یک Chromium قابل دیدن باز میشود، حداکثر ۱۵ دقیقه. noVNC فقط روی `127.0.0.1:6080` سرور است (از راه `web-login-relay`). با تونل SSH خودت: `ssh -L 6080:127.0.0.1:6080 …`، بعد `http://127.0.0.1:6080/vnc.html` با رمز یک‌باره‌ای که همان ترمینال نشان میدهد. **تنظیم SSH سرور عوض نمیشود.**
  - وارد شو و مرورگر را ببند. هاب رمزت را نمیبیند. پروفایل در volume `hq-substitute-web` است (فایل‌ها ۶۰۰، بیرون از backup) و فقط `browser-web` و همین پنجره mountش میکنند.
  - پیش از روشن کردن `substitutes-web` وارد شو: پنجره‌ی ورود و مرورگر پروفایل با هم از جمع سقف‌های حافظه بیشترند.
  - خروج از اپ: `POST /substitutes/{player}/web/logout` 🔏 که پروفایل را پاک میکند.
- **recipeها و fallback:** `infra/egress/recipes/{chatgpt-web,gemini-web,deepseek-web}.yaml` فایل‌های بازبینی‌شده‌اند: گفت‌وگوی تازه (در ChatGPT موقت) ← چسباندن prompt ← صبر (عکس ≤ ۳ دقیقه، ویدیو ≤ ۱۰ دقیقه) ← خواندن جواب یا دانلود نسخه‌ی اصلی ← بستن. در DeepSeek فقط DeepThink و Search، همیشه روشن.
  - صفحه‌ی ورود ← `expired` (هیچ ورود خودکاری نیست؛ مالک دوباره وارد میشود). قدمی که شکست بخورد ← `recipe_failed` با شماره‌ی قدم؛ این نشانه‌ی fallback یک اجرای Claude با `web.browse` روی همان پروفایل است که اصلاح recipe را به‌صورت تغییر بازبینی‌شده پیشنهاد میدهد. selectorها هنوز روی سایت واقعی سنجیده نشده‌اند (هیچ ورودی ساخته نشده).
  - `web.browse` با حساب پروفایل همان قواعد مرور را دارد: POSTی که در `allow` حساب نیست `needs_owner` میشود. برای اینکه fallback بتواند پیام بفرستد، مالک باید فراخوان ارسال همان سایت را در `allow` حساب مُهر کند (🔏 `account.put`).
  - هیچ screenshot، لاگ یا جوابی کوکی ندارد: جواب فقط متن خوانده‌شده یا فایل اصلی است و نوع فایل از روی محتوا تعیین میشود.
- **بازبینی دوم کد:** checkout فقط‌خواندنی همان `head_sha`، بی فایل‌های رمزدار؛ Codex با `--output-schema` (`findings: [{path, line, severity, title_fa, detail_md}]`). یافته‌ها فقط پیشنهادند: مدیر فنی یا QC میسنجد، و هرگز تأیید یا مسدود نمیکنند.
- **حافظه:** `MEM_SUBSTITUTE=512m`، `MEM_BROWSER_WEB=768m`، `MEM_BROWSER_LOGIN=1024m`، `MEM_WEB_LOGIN_RELAY=32m` (اندازه‌گیری‌ها در گزارش). در full هر دو profile با هم جا میشوند، ولی همراه STT نه. اولویت با مالک است.

### ۳۰.۵ MCP روی کانتینر (پرامپت ۱۲ §۱۴، قرارداد §۲۱.۱۱)
- **پروفایل اختیاری `mcp`، پیش‌فرض خاموش** (`HQ_MCP=` در `.env`). `hq.sh` فایل `infra/compose/mcp.yaml` را به همه‌ی فرمان‌ها اضافه میکند و پروفایل را فقط با `HQ_MCP=on` و وقتی در بودجه‌ی حافظه جا شود روشن میکند؛ وگرنه `up` با کد ۳ رد میشود (مثل STT). api فقط وقتی پروفایل روشن است `MCP_CONTAINERS=on` میگیرد.
  - **عددها (۲۰۲۶-۱۰-۲۲):** `mcp-time` حدود ۹۲ مگ، پیک ۹۷ (`MEM_MCP_TIME=192m`)؛ CodeCortex روی ریپوی هاب ۷۶ مگ بیکار، ۱۳۳ بعد از چند فراخوانی، پیک ۳۰۷ (`MEM_MCP_CODECORTEX=384m`)؛ job ایندکس کامل پیک ۳۳۰ مگ در ۱۲ ثانیه (`MEM_MCP_CODECORTEX_INDEX=448m`).
  - **بودجه:** full با mcp ‏11920 از 12288 مگ (جا میشود، ۳۶۸ مگ میماند)؛ lean با mcp ‏700 مگ بیشتر از بودجه. همراه STT جا نمیشود. اولویت با مالک است (§۰.۸ بند ۷).
- **شبکه:** `hq-mcp` (internal، `172.30.12.0/24`): فقط سرورهای MCP و Tool Gateway. egress، api و دیتابیس روی آن نیستند. gateway مستقیم به `http://mcp-<key>:8080/mcp` وصل میشود (بی egress).
- **هر سرور:** کاربر 10001، rootfs فقط‌خواندنی، `cap_drop: ALL`، `no-new-privileges`، فقط `hq-mcp`، هرگز socket داکر، بی رمز. پل stdio→HTTP: ‏`mcp-proxy` (MIT) داخل همان image.
- **فهرست مجاز بازبینی‌شده:** `infra/mcp/servers.yaml` (key، image با digest، URL، دستور، لایسنس، منبع، ابزارهای بازبینی‌شده با کمترین کلاس، ابزارهای ممنوع، `mem_limit`، `needs_internet`/`needs_secret`).
  - `POST /api/v1/tools/mcp` با `transport: container` فقط دقیقاً همان key، image و URL، بی `auth_header`، بی ابزار ممنوع یا بازبینی‌نشده‌ی روشن، و بی کلاس پایین‌تر از بازبینی‌شده پذیرفته میشود؛ وگرنه ۴۲۲ (پیش از مصرف مُهر). سروری که اینترنت یا رمز بخواهد ← `409 not_ready` (نسخه‌ی بعد).
  - روشن کردن (🔏 `mcp.enable`) وقتی پروفایل خاموش است یا image مُهرشده دیگر همان بازبینی‌شده نیست ← `409 not_ready`؛ `mcp.call` همان وقت ← `503 channel_not_configured`. همه‌ی قواعد §۲۰ سر جایش است (pin فهرست، فهرست تغییرکرده ← خاموش + کارت `tool_enable`، کلاس مُهرشده، A3 به کارت، redaction، `mcp_calls`).
- **image با digest ثابت:** imageها روی خود هاب ساخته میشوند و هرگز pull نمیشوند (`pull_policy: never`). `make mcp-build` آن‌ها را تکرارپذیر میسازد (`SOURCE_DATE_EPOCH=0`، timestamp بازنویسی‌شده، بی attestation)؛ digest هر ساخت باید همان فهرست مجاز باشد وگرنه خطا میدهد و هر دو را چاپ میکند. `make up` با `HQ_MCP=on` همین را اول اجرا میکند. compose هر سرور را با همان digest اجرا میکند، پس ساخت دیگری بالا نمیآید.
  - به‌روزرسانی Debian (مثلاً git در image‌ی CodeCortex) digest را عوض میکند: digest تازه فقط با تغییر بازبینی‌شده‌ی `servers.yaml`، `mcp.yaml` و پیشنهاد در `apps/api/seed/mcp_proposals.yaml`.
- **افزودن سرور تازه = یک PR بازبینی‌شده** روی فهرست مجاز (و image در `infra/mcp/<key>/` و سرویس در `infra/compose/mcp.yaml`)، بعد دو مُهر مالک در اپ (🔏 `mcp.add` روی بدنه، 🔏 `mcp.enable` روی key). هیچ سروری خودش ثبت یا روشن نمیشود.
- **سرور مرجع `time`:** ‏`mcp-server-time` (MIT)، ابزارهای `get_current_time` و `convert_time` (A0)، منطقه‌ی زمانی Asia/Tehran؛ پیشنهاد آماده در `apps/api/seed/mcp_proposals.yaml`، منتظر مُهر مالک.
- **CodeCortex** (پروژه‌ی خود مالک، Apache-2.0، بدون `semantic` و بدون `parsers`): فقط ابزارهای خواندنی A0؛ ویرایش، حافظه‌ی خودش، همگام‌سازی و `cortex_dependency_docs` در فهرست مجاز ممنوع و در ثبت `enabled: false` هستند.
  - **ریپو:** ریپوی هاب فقط‌خواندنی به job یک‌بارمصرف `mcp-codecortex-index` (بی شبکه) mount میشود؛ job یک کپی git در HEAD ریپو (volume ‏`mcp-codecortex-repos`) و ایندکس را در volume وضعیت همان ریپو میسازد. سرور کپی را فقط‌خواندنی و فقط وضعیت را نوشتنی mount میکند؛ حین پاسخ‌گویی ایندکس نمیسازد.
  - **زمان job:** با `make up` (اگر پروفایل روشن است)، هر شب ۰۳:۳۰ تهران (`coinepro-hq-mcp-index.timer`) و وقتی HEAD ریپوی هاب جابه‌جا شود (`coinepro-hq-mcp-index.path`)؛ هر دو تا `HQ_MCP` خاموش است کاری نمیکنند. دستی: `make mcp-index` (`FULL=1` یعنی از نو). فقط قاعده است (بی مدل، بی تماس بیرونی)، پس با کلید توقف هلدینگ هم اجرا میشود. نصب unitها: `make install-systemd` (با sudo، کار مالک).
  - ریپوی workspaceها و تأسیس‌ها: برای هر ریپو یک mount فقط‌خواندنی و یک volume وضعیت (تغییر بازبینی‌شده‌ی `mcp.yaml`).
- **آزمون‌ها:** `make mcp-test` روی imageهای ساخته‌شده و یک شبکه‌ی internal دورانداختنی: فهرست و ساعت تهران از `time`، PR intelligence روی ریپوی نمونه، کپی فقط‌خواندنی، بی اینترنت، بی `10.10.1.1`، بی سرویس هاب. `make verify-live` وقتی سرورها بالا هستند: gateway به آن‌ها میرسد، آن‌ها به هیچ‌جا نمیرسند، و digest در حال اجرا همان فهرست مجاز است.
### ۳۰.۶ حافظه‌ی پروفایل‌های اختیاری پرامپت ۱۲ (همه پیش‌فرض خاموش)
- **چهار profile اختیاری،** هر کدام با یک متغیر خالی در `.env`:
  - `tts` (`HQ_TTS`): صدای فارسی، یک‌بارمصرف، `MEM_TTS=320m`
  - `mcp` (`HQ_MCP`): `mcp-time` ‏192m، `mcp-codecortex` ‏384m و job ایندکس ‏448m، روی هم ‏1024 مگ
  - `substitutes` (`HQ_SUBSTITUTES`): runner بازیکن‌های ذخیره، یک‌بارمصرف، `MEM_SUBSTITUTE=512m`
  - `substitutes-web` (`HQ_SUBSTITUTES_WEB`): مرورگر پروفایل‌های لاگین‌شده، `MEM_BROWSER_WEB=768m`
  - پنجره‌ی ورود `web-login` فقط با `make <x>-web-login` و حداکثر ۱۵ دقیقه: ‏1056 مگ (`MEM_BROWSER_LOGIN` و relay).
- **بودجه‌ی full** (مرجع ‏15360 مگ، بودجه ‏12288): خود full ‏10896 مگ.
  - **تنها، هر کدام جا میشود:** tts ‏11216، mcp ‏11920، substitutes ‏11408، substitutes-web ‏11664، web-login ‏11952.
  - **دوتایی‌هایی که جا میشوند:** tts+mcp ‏12240، tts+substitutes ‏11728، tts+substitutes-web ‏11984، substitutes+substitutes-web ‏12176.
  - **جا نمیشوند:** mcp+substitutes (۱۴۴ مگ بیشتر)، mcp+substitutes-web (۴۰۰)، tts+substitutes+substitutes-web (۲۰۸)، هر چهار با هم ‏13520 (۱۲۳۲). STT به‌تنهایی ۷۸۴ مگ بیشتر است.
- **بودجه‌ی lean** (مرجع ‏7745، بودجه ‏6196): فقط tts جا میشود (‏6192)؛ بقیه نه.
- **gate:** `hq.sh` profileها را به همین ترتیب روی هم میشمارد: `mcp`، `substitutes`، `substitutes-web`، `tts`. اولی که از بودجه بیرون بزند رد میشود و `up` با کد ۳ تمام میشود. هر کار یک‌بارمصرف با سقف کامل خودش شمرده میشود؛ قاعده‌ی «یک بار با بزرگ‌ترین سقف» هنوز در gate نیست، پس عددها محتاطانه‌اند.
- **اولویت با مالک است** (§۰.۸ بند ۷): هیچ‌کدام روشن نمیشود تا مالک بگوید.

### ۳۰.۷ پیوند دو بخش
- **بازبینی دوم کد کارت deploy:** کارت `deploy` که diff واقعی دارد (۳۰.۱۵)، بعد از ساخت یک فراخوانی `code_review` میگیرد.
  - صداکننده سرویس `deploy-review` است و ورودی همان diff ماسک‌شده‌ی کارت.
  - checkout را dispatcher از کلون خود هاب میسازد. ریپویی که در `HQ_SUBSTITUTE_REPOS` نیست ← `no_access`.
  - کارت `payload.second_review` را از همان فراخوانی میخواند: `{player, model, findings, verified}` یا null.
  - هیچ‌وقت تأیید یا مسدود نمیکند. یافته‌ی سنجیده‌نشده به `risk_note` نمیرود. کارت بی‌diff بازبینی نمیگیرد.
- **بررسی دوم ادعا:** ادعایی که با `protocol` ثبت شود (نمونه‌ی `PR-001` یا نمونه‌ی راستی‌آزما)، یک فراخوانی `overseer_cross_check` میگیرد.
  - ورودی: متن ماسک‌شده‌ی ادعا، عنوان و خلاصه‌ی خروجی. رأی و یادداشت بررسی‌کننده در آن نیست.
  - برای هر خروجی و متن ادعا فقط یک بار.
  - اگر رأیش فرق کند، ادعا با یک کار برای ناظر کل برمیگردد (Audit ‏`claim.returned`).
  - خودش هیچ ردیف `quality.claims` یا `claim.verdict` نمیسازد.
- **حوزه‌ی فراخوانی ایجنت شرکت:** `substitute.call` در حوزه‌ی هاب اجرا میشود، چون بازیکن‌ها و جایگاه‌ها ردیف‌های هلدینگ‌اند و سقف روزانه همه‌ی شرکت‌ها را میشمارد. فراخوانی برای شرکت خود ایجنت ثبت میشود.
- **یادداشت stale:** یادآوری کارتابل (۳۰.۱۷) ردیف `owner.decision_reminders` است و به خود کارت دست نمیزند. trigger فقط `version`، `updated_at` و `reminded_at` را کنار میگذارد.
- **محرک OKR:** از `governance.key_results` و `governance.objectives` پرامپت ۱۱ میخواند. پیشرفت مثل خود پرامپت ۱۱ است: (current − start) ÷ (target − start)، بین ۰ و ۱. KR وصل به KPI مقدار `last_value` همان KPI را میگیرد. روی جدول‌های واقعی پرامپت ۱۱ با `gov_okr.progress` و فصل شمسی `gov_common.quarter_bounds` خود آن کار میکند.

### ۳۰.۸ «از هاب بپرس» (پرامپت ۱۲ §۲، قرارداد §۲۱.۲)
- **migration ‏`0027_2`** (`0027_2_owner_tools.py`، بعد از `0027_1`): جدول‌های `knowledge.corpus_sources`، `corpus_files`، `corpus_chunks` و `knowledge.asks` (`AK-0001`)، `owner.reviews` (۳۰.۹)، schema تازه‌ی `dceo` (۳۰.۱۰)، بلوک‌های `weekly_review` و `digital_ceo` در `owner.settings`، و فعال شدن `PR-121`. همه با `company_id` و RLS **FORCE**؛ ردیف corpus ریپوی یک workspace مال شرکت همان workspace است، و پیش‌بینی مال شرکت همان کارت. هیچ نوع کارت تازه‌ای نیست؛ CHECK نوع کارت اینجا validate نمیشود؛ head همه‌ی نوع‌ها را با هم validate میکند: روی ۱۳ `0028_1` (۳۱) و از پرامپت ۱۴ `0029` با نوع‌های ۱۱ تا ۱۴ (۳۲).
- **منبع دانش (corpus)، بدون مدل:**
  - **ریپوی خود هاب:** پوشه‌ی `.git` آن فقط‌خواندنی در worker (`../../.git:/hub-repo.git:ro`، متغیر `HQ_HUB_REPO`). فقط فایل‌های commit‌شده‌ی `HEAD` خوانده میشوند، نه فایل‌های ignore‌شده‌ی working tree (مثل `infra/compose/.env`). `docs/`، `contracts/`، `agents/` (و RUNBOOK) و README/CLAUDE.md ریشه نوع `doc`‌اند، بقیه `code`.
  - **ریپوی هر workspace کارگاه:** `fetch --depth=1` شاخه‌ی پیش‌فرض در volume ‏`hq-git` (`/var/lib/hq-git/corpus/<WS>.git`)، با همان توکن workspace که `hq/<ref>` را push میکند (`hq-api/workshop/github/<WS>`؛ هیچ توکن تازه‌ای نیست). ریپویی که هاب نمیخواند ← `not_indexed` و هر جواب همین را میگوید.
  - **فایل‌ها:** فقط متن، ≤ ۲۰۰ کیلوبایت. vendor، node_modules، dist، build، lockfileها و باینری‌ها نه. فایل رمزی با نامش (`.env`، کلید، `credentials`) یا فایلی که اسکن رمز (`hq_common.redact`) در آن چیزی پیدا کند، **کامل** کنار گذاشته میشود (`state: secret`، بی هیچ قطعه).
  - **قطعه‌ها:** ۶۰ خط، با مسیر، شماره‌ی خط و commit. جستجو با `core.fa_normalize` (ی/ي، ک/ك، ZWNJ)، ایندکس pg_trgm و tsvector ساده؛ بدون embedding و vector DB.
  - **رکوردها** (مصوبه، تصمیم، خروجی، کار، پیام) کپی نمیشوند؛ همان‌جا که هستند جستجو میشوند و همیشه تازه‌اند.
  - **سندهای بایگانی** (`AR-…`، پرامپت ۱۴، §۳۲) هم کپی نمیشوند: `hq_api.archive.search.ask_hits` همان‌جا و **در مجوز پرسنده** میگردد (`archive.clearance.for_ask`). مجوز روی تراکنش گذاشته میشود و RLS سندِ بالاتر از آن را پیش از هر رتبه‌بندی حذف میکند، پس نه شمرده میشود، نه نقل. چون قطعه‌ها به کتابدار (یک مدل) میرسند، مجوز مالک در پرسش تا سطح `agents_max` (`confidential`) است: سند `secret` هرگز به مدل یا به `passages` ذخیره‌شده‌ی پرسش نمیرسد. متن فایل فقط وقتی محتوا دیدنی است تطبیق داده و نقل میشود؛ مقدار حساس فقط از `confidential` به بالا. نوع ارجاع: `record`.
  - **ساخت:** `hq-corpus-nightly` هر شب ۰۳:۳۰ تهران، افزایشی (فایلی که blob آن عوض نشده دوباره خوانده نمیشود؛ همان commit هیچ کاری ندارد). تا کلید توقف هلدینگ روشن است **هیچ کاری** نمیکند (هیچ fetch)؛ پس پیش از راه‌اندازی، corpus خالی است و پرسش‌ها فقط رکوردها را پیدا میکنند.
  - **پاک کردن:** corpus فقط ایندکس است. همه: `DELETE FROM knowledge.corpus_sources;` (با نقش مالک دیتابیس؛ فایل‌ها و قطعه‌ها cascade میشوند). یک ریپو: `... WHERE key = '<WS>'` (ریپوی هاب: `'hub'`). شب بعد از نو ساخته میشود.
- **پرسش مالک:** `POST /ask {q, scope?: {companies?, kinds?}}` (فقط مالک، `Idempotency-Key`) ← `202 Ask`.
  - جستجو کد است: ۲۰ قطعه‌ی برتر، حداکثر ۲۴ هزار توکن؛ کلمه‌ی کمیاب وزن بیشتری دارد.
  - **چیزی پیدا نشد ← بدون مدل:** `found: 0`، «چیزی پیدا نشد» با کلیدواژه‌های نزدیک، صفر توکن؛ حتی وقتی هلدینگ قفل است.
  - وگرنه یک کار برای `HQ-LIB` (task class `ask_hub`، `owner_zone: direct`، سقف ۶۰ هزار) با قطعه‌های ماسک‌شده در brief. کتابدار با `ask.answer` جواب میدهد. هر ارجاع با مجموعه‌ی بازیابی‌شده سنجیده میشود (رکورد با نوع و ref؛ سند و کد با ریپو، مسیر و خطوط هم‌پوشان). ارجاع بیرون از آن حذف و شمرده میشود؛ جواب بی هیچ ارجاع معتبر ← `failed` («جواب معتبری ساخته نشد»). اگر کتابدار یک بار دیگر جستجو کند، یافته‌هایش به همان مجموعه اضافه میشود.
  - تا کلید توقف روشن است و جواب مدل لازم است ← `423 company_locked` (هیچ ردیفی نمیماند).
  - `hq-ask-sweep` هر ۵ دقیقه: پرسشی که اجرای کتابدار بی `ask.answer` تمام شد، پس از ۵ دقیقه `failed`. در قفل هیچ کاری نمیکند.
- **ایجنت‌ها (`knowledge.search`):** نوع‌های `docs` و `code` برای مشاور، ناظر، کتابدار و CTO (RLS، CTO را به ریپوهای شرکت خودش محدود میکند؛ نام شرکت دیگر ← `403`، مثل شرکتی که نیست). `notes` (یادداشت‌های سریع باز) و `messages` فقط برای مشاور؛ پیام‌ها فقط در پرسش خود مالک خوانده میشوند.
- **کتابدار:** `HQ-LIB` (نقش system، منشور `agents/roles/librarian.md`) از قالب هلدینگ seed میشود، مثل منشی؛ استخدام، امتیاز و ستاره ندارد. از `0029` (پرامپت ۱۴) `agents.queue_run` نقش system دارای role را صف میکند و runner نقش system با منشور system را اجرا میکند: کتابدار برای پرسش، بایگان برای کارهایش، منشی فقط برای خلاصه‌ی جلسه، و سامانه‌ی گزارش (`HQ-SYS`، بی منشور) هرگز. (روی ۱۳ تنها، اجرای کتابدار رد میشد.)

### ۳۰.۹ مرور هفتگی با مشاور (پرامپت ۱۲ §۳، قرارداد §۲۱.۳)
- `owner.reviews` (`WR-0001`)، یکی برای هر هفته (شنبه‌ی آن، منطقه‌ی زمانی مالک). تنظیم `weekly_review: {enabled, day: "sa", at: "10:00"}`.
- **`hq-weekly-review` هر ۱۵ دقیقه:**
  - مرور هفته‌های گذشته که `done` نشده ← `skipped`، بی هیچ اعلان؛ فقط یک خط در گزارش صبحگاهی.
  - ۳۰ دقیقه پیش از زمان مرور، دستور جلسه با کد، حداکثر ۱۲ مورد، به همین ترتیب: کارت‌های منتظر مالک (قدیمی‌ترها اول)، ریسک باز با امتیاز ≥ ۱۵، نتیجه‌ی کلیدی عقب (سرعت < ۷۰٪، بعد از ربع اول فصل)، یافته‌ی `critical` و `high` باز، بودجه‌ی ماه ≥ ۷۰٪، افت درآمد ۷ روز اخیر، بازبینی ۳۰/۶۰/۹۰ روزه‌ی رسیده، یادداشت سریع باز.
  - یک کار برای مشاور: خلاصه‌ی یک‌صفحه‌ای (`advisor_review`، `owner_zone: auto`، سقف ۱۰۰ هزار). پیامش در `A` با `meta.review` میآید و مرور آن را نگه میدارد. اگر سهم مالک تمام شده، تیک بعدی دوباره میکوشد. یادداشت‌های باز را مشاور فقط همین‌جا میخواند.
  - تا کلید توقف هلدینگ روشن است **هیچ کاری** نمیکند: نه مرور تازه، نه skip، نه کار.
- **مالک:** `POST /reviews/weekly/{ref}/start`، `PATCH …/items/{n}` با `If-Match` (`done`، `deferred` یا دوباره `open`، و یادداشت)، `POST …/finish` ← صورت‌جلسه به‌صورت خروجی `O-…` از `HQ-ADV` (قاعده‌محور، بی مدل)، با فهرست موارد و `duration_s`. کارهایی که مالک در جلسه میکند (مُهر، رد، سفارش) رکوردهای عادی خودشان را دارند.

### ۳۰.۱۰ مدیر کل دیجیتال، فقط پیش‌بینی (پرامپت ۱۲ §۱۳، قرارداد §۲۱.۱۰)
- **خط قرمز:** یک سرویس (`service:dceo`)، نه ایجنت: بی ابزار Gateway، بی رشته، بی اعلان. OPA ‏(`owner_tools.rego`) هر عملیاتی جز `dceo.*` را برایش رد میکند (`dceo_never_acts`) و `decisions.rego` هیچ سرویسی را برای تصمیم نمیپذیرد. در تولید توکن سرویسی ندارد؛ فقط درون worker و api کار میکند.
- **پیش‌بینی پایه (بی مدل، همیشه):** با خود کارت، در همان تراکنش پیشنهاددهنده: نرخ رأی‌های قبلی مالک برای همان (نوع، ریسک، نوع پیشنهاددهنده)، Laplace روی سه رأی، در همه‌ی شرکت‌ها (فقط شمارش، با تابع SECURITY DEFINER ‏`dceo.owner_verdicts`؛ حوزه‌ی پیشنهاددهنده آن را کوچک نمیکند). با `sealed_hash` (sha256 ‏JSON کانونی) و یک ردیف Audit که رأی را نشان نمیدهد. قاعده‌محور است و در قفل هلدینگ هم ثبت میشود (نه مدل، نه تماس بیرونی).
- **پیش‌بینی مدل:** `hq-dceo` هر ۵ دقیقه، برای کارت‌های ریسک متوسط و بالا: Haiku 5.5 ‏`medium`، task class `dceo_predict`، حداکثر `digital_ceo.max_model_per_day` (۲۰) در روز مالک، هر کدام ≤ ۸ هزار توکن (کارت ماسک‌شده، اصول فعال، ۱۰ تصمیم مشابه با رأی و یادداشت مالک). سهم مالک تمام شد ← فقط پایه. تا کلید توقف روشن است **هیچ کاری** نمیکند؛ پایه‌ی جاافتاده هم در همین تیک ساخته میشود.
- **پنهان تا تصمیم:** `digital_ceo.reveal: "after"` (پیش‌فرض) ← `Decision.digital_ceo_prediction` تا تصمیم null، بعد `{verdict, confidence, method, correct}`. با `before`، نمای کارت مالک آن را فوراً نشان میدهد و آن پیش‌بینی‌ها `seen_before: true` و بیرون از دقت تمیزند؛ تا ۳۰ پیش‌بینی پنهان نباشد، `GET /digital-ceo` هشدار میدهد.
- **سنجش:** رأی مالک `actual` و `correct` را مینویسد و `dceo.scored` روی topic `dceo` میرود. پیش‌بینی‌ای که بعد از تصمیم برسد دور ریخته میشود. آمار ۳۰ و ۹۰ روزه و کل: دقت، پایه در برابر مدل، Brier، calibration در سطل‌های ۰.۱، و به تفکیک نوع.
- **اصول:** `DP-001`، نسخه‌دار (هر ویرایش و بازنشستگی یک ردیف تازه؛ همه دیدنی‌اند). `hq-dceo-principles` شنبه ۱۱:۰۰ (منطقه‌ی مالک): Sonnet 5.5، `dceo_principles`، ≤ ۱۲۰ هزار توکن، حداکثر ۵ پیشنهاد `proposed` با منبع؛ مالک میپذیرد یا ویرایش میکند. در قفل هیچ کاری نمیکند؛ هفته‌ی بی داده هیچ مدلی صدا نمیزند.
- **PR-121:** با migration ‏`0027_2` (یا seed پایگاه تازه) فعال است: هر پیش‌بینی امتیازخورده‌ی روز پیش از تصمیم مُهر شده (`made_at < decided_at` و hash درست) و (با `after`) دیده نشده.

### ۳۰.۱۱ صدای فارسی گزارش‌ها: TTS (پرامپت ۱۲ §۴، قرارداد §۲۱.۴)
- **موتور:**
  - Piper 1.8.0 (`piper-tts`، GPL-3.0؛ espeak-ng درونش هم GPL-3.0). به‌صورت **برنامه‌ی جدا** اجرا میشود (`python -m piper`)، پس به کد ما link نمیشود.
  - رمزگذاری Ogg/Opus با ‏32 kbps با `opusenc` (opus-tools، BSD؛ libopus، BSD-3)، نه ffmpeg. همان codec و ظرف است، ولی ۶ بسته به جای ۲۰۵ بسته‌ی ffmpeg (ایمیج ۵۹۰ مگ به جای ۱٫۲ گیگ).
- **صدا:** `fa_IR-amir-medium` از `rhasspy/piper-voices` (لایسنس مخزن MIT) در revision ثابت `5041a7a4…`. sha256 هر فایل در `services/tts/voice.lock.json` و `ADD --checksum` در Dockerfile است.
  - **لایسنس دیتاست** از `MODEL_CARD` خود صدا: **CC0** (datacula.com).
    - `ganji` و `reza_ibrahim` هم CC0 اند.
    - `gyro` «See URL» است و پیش‌فرض نیست.
    - MMS-TTS متا (CC-BY-NC-4.0) پیش‌فرض نیست.
  - صدا و لایسنسش در `/meta.tts` است.
  - عوض کردن صدا: `HQ_TTS_VOICE` در `.env`، فقط از جدول `briefings.VOICES` (همه با لایسنس آزاد).
- **کار یک‌بارمصرف، نه سرویس:** image `coinepro-hq/tts`، profile `tts`. timer `coinepro-hq-tts.timer` هر ۲ دقیقه `infra/tts/run-once.sh` را اجرا میکند:
  - اگر `HQ_TTS` روشن نباشد، بی‌صدا تمام میشود.
  - روی `/run/hq/oneshot.lock` حداکثر ۱۰ دقیقه منتظر میماند.
    - این قفل مشترک با backup ساعتی است و `infra/systemd/coinepro-hq-oneshot.conf` آن را میسازد.
    - backup هم پیش از کارش همین قفل را میگیرد (حداکثر ۱۵ دقیقه صبر).
  - بعد `hq.sh run --rm --no-deps tts`: یک pass، حداکثر ۳ گزارش.
    - کانتینر از `POST /internal/v1/tts/claim` کار میگیرد. ۲۰۴ یعنی کاری نیست، و **همیشه وقتی کلید توقف هلدینگ روشن است** همین ۲۰۴ است.
    - صدا میسازد و Ogg را با `POST /internal/v1/tts/{id}/done` میفرستد.
    - شکست با `/fail` گزارش میشود. بعد از ۳ بار `audio_state: "failed"`.
  - **شبکه:** فقط `hq-tts` (internal، ‏172.30.21.0/24)، با api و OpenBao.
    - نه اینترنت، نه Postgres، نه سرویس دیگر (probe در `live.sh`؛ `compose-rules`).
    - principal سرویسی `tts`، با توکنی در `kv/tts/config` (AppRole `tts` روی همان subnet؛ `provision.sh` یک بار میسازد).
    - اعتبار AppRole در `${HQ_SECRETS_DIR}/services/tts/approle.json` است.
- **عددها** (اندازه‌گیری ۲۰۲۶-۱۰-۲۲ روی همین CPX42 با `make tts-bench`؛ ۱ thread، متن ثابت ۱۲۱ کلمه، ۵۱ ثانیه گفتار):
  - RTF ‏0.09 تا 0.10
  - peak RSS برنامه‌ی Piper ‏250 تا 253 مگ
  - peak کانتینر (cgroup) ‏239 تا 241 مگ
  - Ogg حدود ۲۰۵ کیلوبایت
  - `MEM_TTS=320m` در هر دو profile
  - راز حافظه: Piper هر خط را جدا میخواند. پس متن به جمله‌ها و بندهای ≤ ۸ کلمه شکسته میشود (`piper_lines`؛ پرامپت ۱۳ از ۱۴ به ۸، ۳۱.۱۳) و `MALLOC_ARENA_MAX=1`. بدون این دو، peak به ۳۴۰ تا ۳۸۴ مگ میرسید.
- **gate حافظه:**
  - full+tts: ‏11216 از 12288 مگ (جا میشود)
  - lean+tts: ‏6192 از 6196
  - gate هر یک‌بارمصرف را با سقف کامل خودش میشمارد (۳۲۰ مگ؛ قاعده‌ی «یک بار با بزرگ‌ترین سقف» هنوز در gate نیست). جمع همه‌ی profileهای اختیاری در ۳۰.۶ است.
- **روشن و خاموش (تصمیم مالک، §۰.۸ بند ۷):** پیش‌فرض خاموش است، چون STT جا نمیشود و اولویت حافظه با مالک است.
  - `make tts-on`: `HQ_TTS=on`، build، `up api worker` و فعال کردن timer. هر بار که بیرون از budget باشد، `hq.sh` رد میکند.
  - `make tts-off`: برگشت به حالت پیش‌فرض.
  - api فقط وقتی کار صوتی میسازد که `HQ_TTS_ACTIVE=on` باشد. وگرنه گزارش `audio_state: "off"` است و متن بی‌تغییر میماند.
- **متن گفتاری** را api با کد میسازد (`hq_api.speech.fa_speech_script`):
  - markdown حذف میشود.
  - refها به عنوانشان و کد کارمندها به عنوان فارسی تبدیل میشوند.
  - عدد، پول، درصد، تاریخ جلالی و ISO و ساعت به کلمه تبدیل میشوند.
  - هیچ رقم لاتینی یا فارسی نمیماند (`assert_spoken`).

### ۳۰.۱۲ گزارش صبحگاهی صوتی و نامه‌ی هفتگی مدیرعامل‌ها (پرامپت ۱۲ §۴.۲ و §۴.۳)
- **صبحگاهی:** بعد از گزارش نوشته‌شده‌ی پرامپت ۵، یک `BR-…` نوع `morning` با همان متن ساخته میشود (نسخه‌ی خوش‌خوان، اگر ساخته شده باشد).
  - صدا فقط با `owner_settings.audio_briefings.morning` و TTS روشن.
  - **وقتی هلدینگ قفل است هیچ briefing ساخته نمیشود.**
  - خود گزارش قاعده‌محور همچنان ساخته میشود و دو خط تازه دارد، هر دو فقط کد: «هدررفت دیروز» (§۸) و «یادآوری کارتابل» (§۱۱).
- **نامه‌ی هفتگی:** schedule `hq-ceo-letters` هر ساعت اجرا میشود، ولی فقط در روز و ساعت `owner_settings.ceo_weekly_letter` کار میکند (پیش‌فرض شنبه ۰۹:۰۰ در منطقه‌ی مالک).
  - برای هر شرکت عملیاتی فعال، یک کار برای مدیرعاملش با بسته‌ی واقعیت‌ها (JSON، با کد) و سقف ۴۰ هزار توکن.
  - قفل هلدینگ یا قفل خود شرکت ← هیچ.
  - **سنجش عدد** در `deliver`:
    - بیش از ۶۰۰ کلمه ← ۴۲۲ (این تلاش شمرده نمیشود).
    - عدد بی‌منبع، بار اول ← ۴۲۲ و `state: returned`.
    - بار دوم منتشر میشود، عنوانش «عدد بی‌منبع» میگیرد و یک یافته‌ی PR-001 باز میشود.
    - بعد یک `BR-…` نوع `ceo_letter` ساخته میشود.
- API:
  - `GET /briefings?kind&company&cursor`
  - `GET /briefings/latest?kind&company` (۴۰۴ تا وقتی چیزی نیست)
  - `GET /briefings/{ref}`
  - stream `briefing.ready` روی `briefings`

### ۳۰.۱۳ رتبه‌ی دپارتمان‌ها (پرامپت ۱۲ §۵)
- همراه برآیند ستاره‌ها (`hq-stars-rollup`، هفتگی و ماه جلالی)، با کد:
  - ۳۵٪ نیرو
  - ۳۰٪ تحویل: کار سررسیده‌ی done یا delivered، با شاهد و به‌موقع
  - ۲۰٪ کارایی: همان عدد برآیند
  - ۱۵٪ امتیاز مالک
- جزء بی‌داده کنار میرود و وزن‌ها دوباره تقسیم میشوند. دپارتمان بی کارمند فعال رتبه نمیگیرد.
- `rank_holding` بین دپارتمان‌های هم‌کد است و وقتی فقط یکی هست null است.
- `people.department_ranks` append-only است و هر دوره یک بار نوشته میشود.
- این محاسبه‌ی قاعده‌محور داخل برآیند موجود است و با کلید توقف هم انجام میشود.
- `GET /rankings/departments?period&key&company`، stream `rankings.updated` روی `stars`.

### ۳۰.۱۴ ارزیابی ماهانه‌ی HR و PR-082 (پرامپت ۱۲ §۶)
- **زمان:** schedule `hq-hr-rounds` هر روز ۱۰:۰۰ (منطقه‌ی مالک) اجرا میشود، ولی فقط روز یکم ماه جلالی برای هر شرکت عملیاتی فعال و هلدینگ `HR-…` میسازد.
  - اسم دور، ماه جلالیِ اجراست؛ واقعیت‌ها مال ماه تمام‌شده‌اند.
  - **با قفل هلدینگ هیچ.** قفل یک شرکت ← آن شرکت نه.
- **ارزیاب:** `<CO>-HR-MGR`، وگرنه مدیرعامل؛ برای هلدینگ، `aiops_head`.
  - OPA اجازه میدهد مدیر AIOPS هلدینگ `evaluation` پیشنهاد دهد.
  - کار با مهلت ۲۰ ساعت و سقف ۱۰۰ هزار توکن.
  - پرچم `coach` کارت ندارد؛ یک پیش‌نویس آموزش آکادمی برای مدیر AI Ops میسازد.
- **کارت `evaluation` نسخه‌ی ۲:** `round` اجباری است. کارمند بی‌پرچم فقط با `evidence` و `override_reason` (`unflagged: true`). تأیید با 🔏 `decision.approve`.
  - promote و demote: مدل باید یک اتصال enabled داشته باشد و پاکت جا شود، وگرنه `409 envelope_exceeded` و هیچ تغییری.
  - dismiss: همان مسیر برکناری. کار باز به مدیر یا مدیرعامل میرود و حافظه به `transfer_to`.
  - confirm: `probation_until` پاک میشود.
- **PR-082:** نسخه‌ی ۲، `active`، `FREQ=MONTHLY;BYMONTHDAY=3;BYHOUR=10`، `calendar: jalali`، با متن check تازه (migration ‏0027_1 یا seed، با ردیف Audit).
  - schedule آن روزانه ۱۰:۰۰ است و اجرا جز روز سوم ماه جلالی بی‌اثر تمام میشود (بی ردیف `protocol_runs`).
  - checker آن کد است (`hr.hr_rounds_ran`).
  - با قفل هلدینگ هیچ اجرایی نیست.
- loader پروتکل‌ها کلید ناشناخته را با یک هشدار نادیده میگیرد.

### ۳۰.۱۵ diff واقعی کارت deploy (پرامپت ۱۲ §۷)
- **دسترسی:** همان دسترسی git فعلی هاب، یعنی توکن workspace کارگاه در OpenBao (`hq-api/workshop/github/<WS>`)، همان که `hq/<ref>` را push میکند. توکن تازه‌ای از مالک خواسته نمیشود.
  - ریپو باید یک workspace **همان شرکت** باشد. وگرنه، یا وقتی توکن نیست ← `diff: null, diff_unavailable: "no_access"`.
  - کارت همیشه به `head_sha` (اجباری) بسته است.
- **ساخت:** api (git ‏1:2.47.3 در image) پیش از ساخت کارت `git fetch --depth=200` میکند: شاخه‌ی پیش‌فرض و `refs/pull/<n>/head`.
  - mirrorها در volume ‏`hq-git` (`/var/lib/hq-git`) میمانند.
  - توکن فقط در محیط git است (`GIT_CONFIG_*`)، نه در argv و نه روی دیسک.
  - `head_sha` در ریپو نیست ← ۴۲۲.
  - سقف‌ها: ۳۰۰ فایل، ۴۰۰ خط برای هر فایل، ۲۵۶ کیلوبایت کل. فایل باینری patch ندارد.
  - هر خط patch که رمز دارد ماسک میشود (`secret_masked`).
  - `diff` و `diff_unavailable` پیشنهاددهنده دور ریخته میشود.
- **بستن به `head_sha`:** schedule `hq-deploy-recheck` هر ۱۵ دقیقه (`git ls-remote`؛ **با قفل هلدینگ هیچ**)، و یک بار پیش از مُهر مالک.
  - push تازه ← کارت `withdrawn` («superseded: a new push»)، پیام سیستم و یک کار برای پیشنهاددهنده.
  - مُهر ← `409 decision_not_pending`.
- `GET /decisions/{ref}/diff?file=<path>`: patch کامل یک فایل تا ۲۰۰۰ خط، با همان ماسک.
- **پاک کردن mirrorها:** فقط با تصمیم مالک (`docker volume rm coinepro-hq_hq-git` وقتی stack پایین است). اولین کارت بعدی دوباره fetch میکند.

### ۳۰.۱۶ گزارش هدررفت روزانه و ROI (پرامپت ۱۲ §۸ و §۱۰)
- **هدررفت:** schedule `hq-waste-daily` ساعت ۰۷:۴۵ (منطقه‌ی مالک) برای دیروز، با کد، در `llm.waste_daily`: یک ردیف برای هر شرکت و یکی برای کل هلدینگ.
  - **با قفل هلدینگ چیزی ذخیره نمیشود.** `GET /treasury/waste` همان روز را با همان کد حساب میکند و نشان میدهد.
  - **دسته‌ها:**
    - failed_runs
    - cancelled_work
    - no_progress_runs
    - retry_loops: ≥ ۳ اجرا روی یک کار
    - router_errors
    - duplicate_calls: همان `request_sha256` در ۱۰ دقیقه
    - cache_miss: ورودی بیش از ۱۰ هزار، با همان `prefix_sha256` در یک ساعت و بدون cache read
    - over_model: haiku < sonnet < opus در برابر assignment پیش‌فرض task class
  - هر دسته جدا شمرده میشود. سهم روز، اجتماع فراخوانی‌های پرچم‌خورده است.
  - llm-router فقط hash درخواست و prefix را در `llm.calls.meta` نگه میدارد، هرگز متن را.
  - سهم بیش از ۱۵٪ ← اعلان `report`. کارایی ستاره‌ها همین عددها را میخواند (`waste.shares_between`).
- **ROI:** `GET /treasury/roi?by=employee|department|company&period=week|month&key&company`، هنگام خواندن با کد.
  - درآمد فقط برای شرکت است (`revenue.days`): `roi = revenue / cost`.
  - شرکت بی‌درآمد ← null.
  - کارمند و دپارتمان همیشه null.

### ۳۰.۱۷ یادداشت سریع و یادآوری کارتابل (پرامپت ۱۲ §۱۱)
- **یادداشت `NT-…`:**
  - `POST /notes` (Idempotency-Key)
  - `PATCH` (If-Match؛ متن، برچسب، `archived`). حذف وجود ندارد.
  - `POST /notes/{ref}/promote {to, company?, title?}` از همان مسیرهای موجود (`POST /work`، `POST /orders`، `POST /errands`) میگذرد.
  - `/transcribe?purpose=note&save=true` یادداشت صوتی میسازد و `note_ref` برمیگرداند.
  - هیچ مدلی روی یادداشت اجرا نمیشود.
- **یادآوری:** schedule `hq-cartable-reminders` هر ۱۵ دقیقه (**با قفل هلدینگ هیچ**).
  - فقط کارت‌هایی که مالک تصمیم‌گیرنده است، و هر آستانه یک بار (`owner.decision_reminders`، append-only).
  - آستانه‌ها: نیمه‌ی مهلت، ۶ ساعت پیش از انقضا، ۲۴ ساعت، ۷۲ ساعت و ۷ روز.
  - اعلان سطح `decision`؛ در خلوت نگه داشته میشود.
  - کارت `waiting_h` و `reminders[]` میگیرد. تنظیم در `owner_settings.reminders`.

### ۳۰.۱۸ ادعاهای رد شده و تابلوی سلامت ایجنت‌ها (پرامپت ۱۲ §۱۲)
- **ابزار `claim.verdict`** (A2؛ راستی‌آزما، ناظر، QC) ← `POST /internal/v1/claims`. OPA در `mgmt.rego`، A2 grant در `data.json`.
  - ادعا ماسک‌شده و حداکثر ۳۰۰ نویسه است.
  - `refuted` بی شاهد ← ۴۲۲.
  - `quality.claims` (`CL-…`) append-only است. stream `claim.verdict` روی `quality`.
- **تابلو:** `GET /runs/health?company&period=7d|30d`، با این پرچم‌ها:
  - `truth`: ≥ ۲۰٪ رد شده، با دست‌کم ۵ ادعا
  - `reliability`: ≥ ۲۵٪ شکست
  - `loops`: ≥ ۲ حلقه
- ادعاهای رد شده در بسته‌ی HR (§۶) هم میآیند. فهرست: `GET /claims?company&employee&verdict&cursor`.

## ۳۱. استودیوی رسانه و مشاور حقوقی (پرامپت ۱۳؛ قرارداد §۲۲)
بخش رسانه (§۱، §۱.۱، §۲، §۵ و §۶ پرامپت) در ۳۱.۱ تا ۳۱.۹. بخش حقوقی و صدا (§۳ و §۴) در ۳۱.۱۱ به بعد (کار شاخه‌ی r13b).
- **migration ‏`0028`** (`0028_media_studio.py`، بعد از `0027_2` پرامپت ۱۲):
  - ستون‌های `mandate` و `identity_md` روی `core.departments` و `identity_doc` روی `agents.runs`.
  - schema تازه‌ی `media`: ‏`series`، `items`، `compositions` (append-only)، `render_jobs`، `publish_log` (append-only).
  - جدول `people.role_drafts`.
  - نوع استوری `role`.
  - task classهای `media_script`، `media_direction`، `media_motion`، `media_review` و `ui_design` (همین‌ها در seed روتر).
  - همه‌ی جدول‌ها `company_id` و RLS **FORCE** دارند و حذف نمیشوند.
  - داده: دپارتمان `MEDIA` (با مدیر خوابش و دو رشته) برای هر شرکت عملیاتی؛ `LEGAL` و `HQ-LGL` (خواب، بی مدیر) برای هلدینگ. **هیچ کارمندی ساخته نمیشود.** رشته‌ی `L` و نوع رشته‌ی `legal` مال ۳۱.۱۱ است (رشته‌ی `L` را seed از `holding.yaml` میسازد).
  - نوع‌های کارت `media_series`، `media_publish` و `role_new` از روی نوع‌هایی که CHECK الان دارد، `NOT VALID` اضافه میشوند. `email_send` مال `0028_1` است.
  - **زنجیره (روی پرامپت ۱۲ نهایی):** `0025` ← `0026` ← `0026_1` ← `0027` ← `0027_1` ← `0027_2` ← `0028` ← `0028_1` (حقوقی و صدا) ← `0029` (بایگانی، پرامپت ۱۴، آخرین). فقط آخرین migration هر دو CHECK ‏`decisions_kind_check` و `threads_kind_check` را با همه‌ی نوع‌های ۱۱ تا ۱۴ validate میکند: تا پرامپت ۱۳ این کار `0028_1` بود (production همان را اجرا کرده و دست نمیخورد) و از پرامپت ۱۴ کار `0029` است (§۳۲). هر بازنویسی پیش از آن (۰۰۱۸، ۰۰۲۳، ۰۰۲۵، ۰۰۲۶، ۰۰۲۶_۱، ۰۰۲۸، ۰۰۲۸_۱) `NOT VALID` است و `0027_2` چیزی validate نمیکند، تا اجرای پایین و بالای migrationها (test_hiring) ردیف‌های بعدی را نگه دارد.
- **دروازه‌ی راه‌اندازی:** تا کلید توقف هلدینگ روشن است، هیچ چیزی از این بخش مدل یا سرویس بیرونی صدا نمیزند:
  - sweep رسانه (`hq-media-sweep`، هر ۵ دقیقه) هیچ کاری نمیکند (`skipped: holding_locked`): هیچ آیتمی از برنامه‌ها ساخته نمیشود، هیچ انتشاری نیست و بازسنجی هم نیست.
  - `POST /internal/v1/media/render/claim` و `POST /internal/v1/voices/jobs/claim` (صف صدای ۳۱.۱۳) جواب `204` میدهند. کار شرکتی که قفل است هم منتظر میماند.
  - انتشار بعد از مُهر کارت هم صبر میکند (اثر کارت تا قفل هست اجرا نمیشود).
  - اجرای ایجنت‌ها مثل همیشه رد میشود (`locked`). کار هر گام فقط رکورد است.
  - برداشتن پستی که قبلاً منتشر شده کار خود مالک است و با مُهر خودش اجرا میشود (فقط برمیدارد).
- **پیش‌فرض‌های §۰.۹ تا جواب مالک:**
  - مدل موشن‌گرافی Opus 5.5 (منشور `motion_designer`).
  - صدا: ParsVoice-XTTS (۳۱.۱۱)؛ تا نصبش Piper `fa_IR`.
  - بی GPU و بی کتابخانه‌ی موسیقی: `music` فقط `none`.
  - سقف روزانه‌ی هر برنامه: ریلز ۲، استوری ۳، پست و کاروسل ۲.
  - صندوق ایمیل: ندارد (۳۱.۱۱).

### ۳۱.۱ مأموریت، شخصیت و تیم شروع هر دپارتمان (§۱، قرارداد §۲۲.۱)
- **از قالب:** `apps/api/seed/templates/standard.yaml` و `holding.yaml` برای هر دپارتمان این‌ها را دارند:
  - `mandate`: ‏`from_fa`، `to_fa`، `outputs_fa`، `boundaries_fa`، `tool_ceiling`، `model_ceiling`.
  - `identity_md`.
  - `team`.
  - seed فقط جای خالی را پر میکند؛ ویرایش مالک میماند.
- **سقف ابزار:** هیچ‌وقت `hire.decide`، `role.decide`، `message.owner`، قدرت نظارت، ابزار A3/A4 یا ابزار ناشناخته را نمیپذیرد (۴۲۲).
  - MEDIA: سقف مدل Opus، ابزارهای `media.item`، `media.render`، `media.voice`. **`media.review` فقط مال مدیر رسانه است** و در سقف نیست.
  - بقیه‌ی دپارتمان‌ها: Sonnet.
- **تیم:** فقط نقش‌هایی که منشورشان در `agents/roles/` هست و در همان دپارتمان‌اند. نقش staged روزی که فعال شود، خودش در فهرست میآید.
- **API:**
  - `GET /companies/{code}/departments`: هر دپارتمان `mandate`، `identity_md` و `team` دارد.
  - `GET /templates`: `blueprint` هر قالب.
  - `company.state`: مأموریت و تیم هر دپارتمان، و شخصیت دپارتمان خود صداکننده.
  - ویرایش: `PUT /companies/{code}/departments/{dept}/mandate` با 🔏 `department.mandate` روی SHA-256 بدنه و `If-Match`.
- **runtime:** `identity_md` بعد از منشور و پیش از مهارت‌ها در system prompt مدیر و هر کارمند همان دپارتمان میآید. نسخه‌اش روی اجرا در `agents.runs.identity_doc` (مثلاً `TY-MEDIA@4`) ثبت میشود. CEO و نقش‌های بی دپارتمان هیچ شخصیتی نمیخوانند.

### ۳۱.۲ نقش‌هایی که به‌موقع نوشته میشوند (§۱.۱، قرارداد §۲۲.۵)
- **درخواست:**
  - مالک: `POST /roles/drafts {company, department, brief_md}`. مدیر دپارتمان با یک کار بیدار میشود.
  - یا خود مدیر با `role.draft` (A1) مینویسد.
- **سقف با کد (۴۲۲ برای هر فیلد):**
  - ابزارها داخل `tool_ceiling` دپارتمان؛ هیچ قدرت نظارت، اختیار استخدام، خط مالک یا ابزار A3/A4.
  - مدل داخل `model_ceiling`؛ `limits` حداکثر به اندازه‌ی خود مدیر.
  - دست‌کم ۳ مورد آزمون.
- **دروازه‌ها به ترتیب:**
  1. چک تکراری بودن (8-gram، بی مدل)
  2. بازبینی ناظر روی متن کامل ماسک‌شده و sha256 (`skill.review` با ref `RD-…`، چک پنجم `ceiling`)
  3. آزمون‌های خودش در آکادمی (قبولی ۷۰ از ۱۰۰، که baseline نقش میشود؛ تا قفل هست اجرا نمیشود)
  4. تأیید
- **تأیید:**
  - با `role.decide` مدیرعامل همان شرکت، فقط وقتی استخدام `delegated` است.
  - وگرنه، و همیشه برای هلدینگ، کارت `role_new` برای مُهر مالک (🔏).
  - هر نقش تازه یک استوری `role` میسازد.
- **کجا میماند:** نقش فعال یک منشور روی سرور است، برای همان شرکت و دپارتمان. `agents/` هرگز نوشته نمیشود. `_common.md` همیشه اول است.
  - `GET /roles` هر دو را با `source: file|draft` نشان میدهد. استخدام هر دو را میپذیرد.
  - بازنشسته کردن: `POST /roles/drafts/{ref}/retire` (بی مُهر؛ استخدام تازه نه، کارمندهای فعلی کار میکنند).

### ۳۱.۳ برنامه‌ی انتشار (§۲، قرارداد §۲۲.۲)
- **ساخت:**
  - مالک: `POST /media/series` (`Idempotency-Key`) ← `draft`.
  - یا مدیر رسانه با `series.propose` (A1) ← `proposed` با کارت `media_series` (A3).
  - شکل: `targets` (حساب خود همان شرکت: `telegram-<co>` و `instagram-<co>`)، `schedule` (RRULE در منطقه‌ی مالک)، `topics.pool`، `format`، هر هفت چک، `auto_publish`، `max_per_day`.
  - قالبی که خط تولید نمیتواند بسازد ۴۲۲ میگیرد؛ مثلاً ریلز غیر 9:16، موسیقی `library` یا حساب شرکت دیگر.
- **مُهر:** `POST /media/series/{ref}/seal {digest}` با 🔏 `media.series` روی همان `digest`. digest دیگر ← `409 version_conflict`.
  - مُهر کارت `media_series` منتظر را هم تأیید میکند و برنامه‌ی متوقف را ادامه میدهد.
  - تأیید همان کارت از کارتابل ← `409 validation_failed` (مثل طرح سرور).
- **ویرایش برنامه‌ی مُهرشده** (`PUT …` با `If-Match`) آن را به `proposed` برمیگرداند: مُهر قبلی دیگر آن را نمیپوشاند و تا مُهر دوباره هیچ چیز خودکار منتشر نمیشود.
  - `POST …/pause` و `…/retire` بی مُهرند.
- **زمان‌بندی:** sweep رسانه برای هر برنامه‌ی مُهرشده یک آیتم برای هر رخداد RRULE میسازد، با موضوع بعدی pool. برای هر رخداد فقط یک آیتم ساخته میشود، و حداکثر `max_per_day` در هر روز مالک.
  - رخدادی که بیش از ۳۰ دقیقه پیش گذشته جبران نمیشود.
  - `next_at[]` و `today {made, published}` را سرور حساب میکند.

### ۳۱.۴ خط تولید (§۲.۳)
هر گام یک کار برای نقش همان گام در دپارتمان رسانه‌ی همان شرکت است (کم‌کارترین کارمند). جابه‌جایی بین گام‌ها با کد است.
- **ویدیو** (ریلز، استوری با مدت): سناریو (`scriptwriter`) ← کارگردانی (`video_director`) ← ترکیب‌بندی (`motion_designer`) ← صدا (`voice_producer`، اگر قالب صدا دارد) ← render (کد) ← چک‌ها (کد) ← بازبینی (`media_director`).
- **تصویر** (پست، کاروسل، استوری تصویری): سناریو ← ترکیب‌بندی ← چک‌ها ← بازبینی. ترکیب‌بندی یکی از این دو است:
  - فریم‌های `visual_designer` (creativeهای `substitute.call`، که با `deliver` و ref‌های `CR-…` تحویل میشوند)
  - یا ترکیب‌بندی کد `motion_designer` که render worker به عکس تبدیل میکند: کاروسل با `data-slides="N"` و قاب k در [k-1, k) ثانیه؛ عکس تک در ثانیه‌ی ۳.
- **طراحی UI** (`design`، `ui_designer`): بریف ← ترکیب‌بندی ← render (phone با 390×844 @2x و desktop با 1440×900، کل صفحه) ← بازبینی. هرگز منتشر نمیشود و به‌صورت خروجی برای CTO میماند.
- **نقشی که استخدام نشده:** آیتم `held` میشود، با یادداشت. مدیر رسانه یک بار برای هر گام کار «نقش لازم است» میگیرد.
- **ابزارها** (`agents/tools.md`):
  - `media.item` (A1، گام جاری، فقط نقش همان گام؛ بعد از ثبت، کار گام با شاهد آیتم `done` میشود)
  - `media.render` (A2، پیش‌نمایش؛ تا profile ‏`media` خاموش است ← `503 channel_not_configured`)
  - `media.voice` (A2، فقط `voice_producer`)
  - `media.review` (A2، **فقط مدیر رسانه**؛ `changes` آیتم را به زودترین گام نقشی که در یادداشت آمده برمیگرداند، `reject` تمامش میکند)
  - `series.propose` (A1)
- **schema ترکیب‌بندی** (`hq_common/composition.py`، یک بار در api پیش از ذخیره و یک بار در render worker):
  - یک سند HTML با `lang="fa" dir="rtl"`.
  - فقط `/lib/anime.min.js` (anime.js 3.2.2) و `/lib/lottie.min.js` (lottie-web 5.12.2 light).
  - عکس فقط `/assets/<file id>` از فایل‌های همین شرکت (یا data:image).
  - IRANYekanX تنها قلم.
  - هیچ `fetch`، XHR، WebSocket، worker، import، URL با scheme، `<link>`، `<iframe>`، `<base>`، `<form>`، `@import`، `@font-face`، storage یا eval.
  - یا یک Lottie بی expression.
  - متن دیدنی نباید رمز یا ایمیل داشته باشد.
  - رد ← `422` با نام قاعده. هر تغییر نسخه‌ی تازه با sha256 است (`media.compositions`).
- **صدا:** `media.voice` متن گوینده را با `fa_speech_script` به کلمه تبدیل میکند و با صدای فعال رجیستری (یا صدایی که قالب نام میبرد) در صف رجیستری میگذارد (`media.speech_jobs`، کار `narration`؛ ۳۱.۱۳). TTS one-shot آن را از `POST /internal/v1/voices/jobs/claim` میگیرد.
  - وقتی روایت آماده شد (`voices.ON_NARRATION`)، فایل روی آیتم میآید و آیتم به render میرود. روایتی که سه بار شکست خورد، آیتم را بی‌صدا و با زیرنویس جلو میبرد.
  - روایت کار شرکتی که قفل است (کلید توقف یا freeze) تا باز شدن قفل گرفته نمیشود.
  - تا profile ‏`tts` خاموش است، آیتم بی‌صدا و با زیرنویس ادامه میدهد. یادداشتش همین را میگوید.
- **چک‌ها با کد** (`studio_checks.py`):
  - `brand`: برند فعال، رنگ‌های ترکیب‌بندی از پالت (به‌علاوه‌ی سیاه و سفید)، فقط IRANYekanX، و نشان که خود render گذاشته.
  - `red_lines`: الگوهای قاعده‌ای اساسنامه‌ی مُهرشده (`governance.charters` پرامپت ۱۱)، و تا مُهر نشده الگوهای `agents/charter/HOLDING.md`. روی سناریو، صدا، زیرنویس، متن صفحه، متن تصویر و کپشن.
  - `risk_warning`: محتوای ترید هشدار ریسک را هم در صدا یا زیرنویس (برای تصویر: روی قاب) دارد و هم در کپشن.
  - `facts`: هر عدد سناریو در یادداشت منبعی آمده (عدد «فرض کنید» حساب نیست).
  - `rights`: فقط فایل خود شرکت یا ساخته‌ی هاب، و موسیقی `none`.
  - `platform`: نسبت، مدت و حجم برای هر جای انتشار.
  - `qc`: رأی مدیر رسانه.

### ۳۱.۵ render worker (§۲.۳، §۶)
- profile اختیاری `media`، **پیش‌فرض خاموش**، با دو یک‌بارمصرف که volume کارها (`hq-media-jobs`) را با هم دارند:
  - `media-courier`: روی شبکه‌ی داخلی `hq-media` (172.30.23.0/24)، که فقط به api و OpenBao میرسد. کار را میگیرد و فایل‌ها را برمیگرداند. principal سرویسی `media` با توکنی در `kv/media/config` (AppRole `media`؛ `provision.sh` یک بار میسازد).
  - `media-render`: **بی هیچ شبکه** (`network_mode: none`)، root فقط‌خواندنی، uid 10001، `cap_drop: ALL` و فقط `SYS_CHROOT`، seccomp خود Playwright، no-new-privileges، ۲ CPU، ۵۱۲ پردازه، tmpfs ‏256m، و مهلت ۶۰۰ ثانیه برای هر کار (container یک دقیقه بعد کشته میشود).
  - Chromium بی‌سر ترکیب‌بندی را **قاب به قاب** با ساعت مجازی render میکند، نه ضبط زنده. هر درخواست صفحه بیرون از `/lib`، `/fonts` و `/assets` کار رد میشود و به‌صورت violation برمیگردد (api آیتم را با همان به سازنده‌اش برمیگرداند).
  - ffmpeg: H.264 High، yuv420p، AAC (سکوت وقتی صدا نیست)، `+faststart`.
  - نشان شرکت پایین چپ حاشیه‌ی امن است (۱۲٪ ضلع کوتاه). زیرنویس فارسی و CTA روی لایه‌ای جدا که ترکیب‌بندی به آن دسترسی ندارد.
  - خروجی‌ها: ویدیو، poster، WebVTT. همه از بررسی نوع و حجم api (§۱۷.۱) رد میشوند. poster، `variant=poster` همان ویدیو است.
- **روشن و خاموش (تصمیم حافظه با مالک):**
  - `make install-systemd` یک بار، بعد `make media-on`: `HQ_MEDIA=on`، build، `up api worker`، و timer ‏`coinepro-hq-media.timer` (هر ۲ دقیقه، زیر قفل یک‌بارمصرف مشترک با backup و TTS).
  - `make media-off` برمیگرداند. بیرون از budget، `hq.sh` رد میکند (exit 3).
  - هر دور (`infra/media/run-once.sh`) حداکثر `MEDIA_MAX_JOBS=2` کار.
  - تا خاموش است، render در صف میماند و آیتم همین را میگوید.
- **عددها** (`make media-bench`، ۲۰۲۶-۱۰-۲۳ روی همین CPX42، سقف 960m، ۳ بار؛ ریلز ۳۰ ثانیه‌ای 1080×1920، ۹۰۰ قاب):
  - زمان ۵۱ تا ۵۶ ثانیه
  - peak کانتینر ۷۱۸ تا ۷۷۶ مگ
  - Chromium ‏۲۸۴ تا ۲۹۱ مگ
  - ریلز ۱٫۵ تا ۱٫۸ مگابایت
  - عکس Lottie ‏۱٫۶ ثانیه / ۲۵۹ مگ؛ صفحه‌ی طراحی ۱٫۷ ثانیه / ۲۸۰ مگ
  - `MEM_MEDIA_RENDER=960m` و `MEM_MEDIA_COURIER=64m` (۱۷ مگ اندازه‌گیری‌شده)
- **gate حافظه:**
  - full+media: ‏11920 از 12288 (جا میشود)؛ با TTS هم 12240 (جا میشود).
  - با MCP، runner یا مرورگر وب بازیکن‌ها جا نمیشود.
  - lean+media: ‏700 مگ بیشتر (رد میشود).
- **probe زنده** (`make verify-live`): `hq-media` فقط api و OpenBao را میبیند. خود سرویس `media-render` جز loopback هیچ چیز نمیبیند. URL امضاشده‌ی ساختگی و هر مسیر دیگر `/public` در لبه `404` است.

### ۳۱.۶ انتشار: تلگرام و اینستاگرام (§۲.۳)
- **کی منتشر میشود:**
  - **خودکار** فقط وقتی همه‌ی این‌ها برقرار است: برنامه مُهرشده و digest همان است که مُهر شد، `auto_publish`، هر هفت چک `pass`، همه‌ی جاها با API رسمی و حسابشان کلید دارد، و حالت نگهبان خاموش است. آیتم `scheduled` میشود، در رخداد بعدی برنامه منتشر میشود و حداکثر `max_per_day` در هر روز.
  - **وگرنه** `waiting_owner` و کارت `media_publish` (A3). `why` یکی از این‌هاست: `one_off`، `check_failed`، `not_sealed`، `not_auto`، `no_api`، `account_not_configured`، `platform_limit`، `watch_mode` یا `publish_failed`.
  - تأیید کارت (🔏 `decision.approve`، از کارتابل یا `POST /media/items/{ref}/publish`) همان آیتم را همان موقع منتشر میکند.
  - **استوری کانال تلگرام Bot API ندارد:** همیشه کارت با فایل است. مالک خودش میگذارد (`external_id: "manual"`).
- **مسیر:** worker از راه egress (`POST /v1/media/publish`) میفرستد:
  - تلگرام: `sendVideo`، `sendPhoto`، `sendMediaGroup`. کپشن ساده، با برچسب «ساخته‌شده با کمک هوش مصنوعی».
  - اینستاگرام: Graph API ‏(`graph.instagram.com/v23.0`): `me`، بررسی نام کاربری، `limit`، container (`REELS`، `STORIES`، `IMAGE`، `CAROUSEL`) با `is_ai_generated: true`، بررسی وضعیت، بعد `media_publish` و `permalink`.
  - اینستاگرام فایل را از **URL امضاشده‌ی همان یک فایل، حداکثر ۱۵ دقیقه** میگیرد: `https://hq.coinepro.com/public/v1/media/<token>` (HMAC، فقط فایل‌های ساخته‌ی render یا creative). هر چیز دیگر `404` است. Caddy فقط GET/HEAD این مسیر را به api میدهد.
  - هیچ انتشاری از مرورگر یا کوکی نیست.
- **متوقف میشود با:** قفل هلدینگ (هیچ)، کلید توقف یا deploy freeze شرکت (آیتم `scheduled` میماند)، hold روی کار گام‌ها یا کارت، و حالت نگهبان (کارت).
- **سقف خود پلتفرم:** اینستاگرام ۵۰ پست API در ۲۴ ساعت برای هر حساب ← `429 platform_limit` با `Retry-After`. انتشار خودکار هم پس میافتد.
  - `GET /media/limits`: هر حساب `per_24h`، `used_24h`، `resets_at` و `note_fa` دارد.
- **برداشتن:** `POST /media/items/{ref}/unpublish` با 🔏 `media.unpublish` روی ref.
  - پیام کانال تلگرام با `deleteMessage` برداشته میشود (`removed`).
  - اینستاگرام از API حذف ندارد، پس `remove_by_hand`.
  - آیتم `rejected` میشود. همه در `media.publish_log` ثبت میشود.
- **کار مالک برای هر شرکت (`<co>` با حرف کوچک):**
  1. در اپ، حساب `telegram-<co>` بساز:
     - `site: api.telegram.org`
     - `companies: [<CO>]`
     - `policy.inject.username`: کانال (`@name` یا `-100…`)
     - ربات باید مدیر کانال با اجازه‌ی ارسال و حذف باشد.
  2. در ترمینال خودت: `make account-secret KEY=telegram-<co>` (توکن ربات).
  3. در اپ، حساب `instagram-<co>` بساز:
     - `site: graph.instagram.com`
     - `policy.inject.username`: نام کاربری صفحه‌ی business یا creator
  4. در ترمینال خودت: `make account-secret KEY=instagram-<co>` (توکن long-lived).
  - اینستاگرام دامنه و HTTPS میخواهد (`HQ_SITE_ADDRESS`، و egress با `EGRESS_PUBLIC_HOST`).
  - تا این‌ها نیست، هر جا `account_not_configured` است و چیزی منتشر نمیشود.

### ۳۱.۷ بازسنجی روزانه‌ی پست‌های منتشرشده (§۲.۶)
- sweep رسانه پست‌هایی را که دست‌کم یک ساعت از انتشارشان گذشته، **با کد و بی مدل** دوباره میسنجد: خطوط قرمز، هشدار ریسک، عدد بی‌منبع و برند. حداکثر ۵ پست در روز برای هر شرکت. تا قفل هست، هیچ.
- **پست مشکل‌دار:**
  - یافته‌ی `high` برای ناظر با `dedupe_key` همان آیتم
  - برنامه‌اش `paused` با یادداشت «ناظر کل… متوقفش کرد»، تا مالک
- پروتکل نمونه‌گیری با مدل ناظر در `agents/protocols` نیست. اضافه کردنش کار Claude سشن مشورت است.

### ۳۱.۸ API و stream
- **مالک:**
  - `GET|POST /media/series`، `GET|PUT /media/series/{ref}`، `POST …/seal|pause|retire`
  - `GET|POST /media/items`، `GET /media/items/{ref}`، `POST …/publish|unpublish`
  - `GET /media/limits`
- **ایجنت‌ها:** `POST /internal/v1/media/item|render|voice|review` و `/media/series/propose`.
- **one-shotها:**
  - `POST /internal/v1/media/render/claim`، `GET …/{id}/files/{file_id}`، `POST …/{id}/output|done|fail` (سرویس `media`)
  - `POST /internal/v1/voices/jobs/claim|{id}/done|{id}/fail` (سرویس `tts`؛ روایت آیتم‌ها و نمونه‌های bake-off، ۳۱.۱۳)
- **عمومی:** فقط `GET|HEAD /public/v1/media/{token}`.
- **stream:** `media.item` و `media.series` روی topic ‏`media`؛ `role.updated` روی `people`.
- **کدهای خطا:** `series_not_sealed` (409) و `platform_limit` (429).

### ۳۱.۹ حافظه و هزینه (§۶)
- render worker: ۹۶۰ مگ، و فقط وقتی مالک روشنش کند (۳۱.۵). poller، چک‌ها و انتشار داخل worker موجودند و سرویس تازه نیستند.
- **پاکت توکن:** هر ریلز از پاکت ماهانه‌ی همان شرکت پرداخت میشود و در ستاره‌ی کارایی دیده میشود.
  - prompt ثابت هر گام اندازه گرفته شد: سناریست ۵٫۴، کارگردان ۵٫۲، موشن ۵٫۶، صدا ۴٫۸ و مدیر رسانه ۷٫۱ هزار توکن.
  - برآورد هر ریلز ۱۳۰ تا ۲۸۵ هزار توکن (بیشترش Opus ترکیب‌بندی). جزئیاتش در گزارش `PROMPT_13.md`.
  - **این عدد با سقف روزانه‌ی ۶۰۰ هزار توکن ایجنت‌ها جور نیست** (۲ تا ۴ ریلز در روز برای همه‌ی هاب). سقف با مالک است.

### ۳۱.۱۱ مشاور حقوقی: پرونده، ایمیل مُهرشده، پاسخ‌ها (پرامپت ۱۳ §۳، قرارداد §۲۲.۴)
- **جایگاه:** دپارتمان `LEGAL` («حقوقی») در قالب هلدینگ، **بی‌مدیر** (`manager: false` در `seed/templates/holding.yaml`)، و کارمند seed‌شده‌ی **`HQ-LGL`** (منشور `legal_counsel`، scope هلدینگ) با رشته‌ی **`L`** (kind `legal`). خواب است تا کار برسد:
  - پیام مالک در رشته‌ی `L` (با P2، مثل A، N و P)؛
  - کار مدیرعامل یک شرکت: `work.request {company: HQ, department: LEGAL}` (تنها مسیر میان‌شرکتی غیر از CEO به CEO؛ OPA در `legal_voice.rego`)؛
  - پاسخی که به یکی از پرونده‌هایش رسید.
- **پرونده `LC-0001`** (`legal.cases`، با `company_id` همان شرکتی که پرونده درباره‌ی آن است؛ کار هلدینگ مال هلدینگ است):
  - `GET /legal/cases?company&status&cursor` (تازه‌ترین اول)، `GET /legal/cases/{ref}` (timeline کامل و همه‌ی ایمیل‌ها).
  - `POST /legal/cases {company, title_fa, kind, brief_md, file_ids?}` (مالک، Idempotency-Key) ← پرونده و یک کار P2 برای مشاور (`run_meta.task_class: legal_case`).
  - `POST /legal/cases/{ref}/close {note_fa?}`؛ تا وقتی ایمیلی منتظر مُهر یا ارسال است ← ۴۰۹.
  - timeline در `legal.case_events` (append-only): `note`، `form`، `decision`، `email_out`، `email_in`.
  - stream: `legal.case` روی topic `legal`.
- **ابزارهای مشاور** (Tool Gateway، فقط منشور `legal_counsel`؛ هر کدام فقط روی پرونده‌های خود همان مشاور، وگرنه ۴۰۴):
  - `case.open`، `case.note` (با `deadline {at, what_fa}` و وضعیت `open | waiting_reply | resolved`)،
  - `email.draft` (A1): پیام دقیق ← کارت **`email_send`** (A3)،
  - `mail.read` (A0): ایمیل‌های ماسک‌شده‌ی پرونده.
  - فرم و پورتال: `propose` با `a3_action` و `action: "form_submit"` (مقدار هر فیلد در `preview`)؛ مالک خودش میفرستد.
- **ایمیل، دقیقاً همان، یک بار:**
  - `digest` = SHA-256 شکل canonical پیام: JSON با کلیدهای مرتب و بی‌فاصله از `{from, to, cc, subject, body_md, attachments: [sha256…], lang}` (`hq_api.domain.legal.canonical`). کارت همین را نشان میدهد و مُهرش (step-up `decision.approve`) روی **همین digest** است، نه روی ref کارت.
  - تأیید: اصلاحیه (amendments) ← ۴۲۲. ایمیل تغییرکرده یا کنار رفته ← ۴۰۹ `decision_not_pending`. صندوق وصل نیست ← ۴۰۹ `account_not_configured` و کارت همان کارت میماند (تصمیم مالک §۰.۹ بند ۶).
  - بعد از مُهر، ایمیل `queued` است. effect کارت در worker (`decision_apply_effect`) **بعد از چک قفل‌ها** (کلید توقف هلدینگ و شرکت، hold) آن را میفرستد:
    - ادعا (`sending`) در تراکنش خودش، ارسال از egress، ثبت `sent` یا `failed`.
    - ادعایی که با crash در `sending` مانده هرگز دوباره فرستاده نمیشود (`unknown_outcome`). شکست هم خودکار تکرار نمیشود: پیش‌نویس تازه، کارت تازه.
  - پیش‌نویس تازه وقتی یکی منتظر است ← قبلی `superseded` و کارتش `withdrawn`.
  - رد یا برگشت کارت ← ایمیل `rejected`، پرونده دوباره `open` و یک کار برای مشاور با یادداشت مالک.
  - stateهای ایمیل: `waiting_seal`، `queued`، `sending`، `sent`، `failed`، `received`، `superseded`، `rejected`.
- **پاسخ‌ها:** schedule `hq-legal-mail-poll` هر ۵ دقیقه (`LegalMailPoll` ← `legal_mail_poll`):
  - **با قفل هلدینگ هیچ کاری نمیکند** (نه صندوق، نه کار). بی‌صندوق: `account_not_configured` در `legal.mailbox.last_result`.
  - از آخرین UID به بعد میخواند (`BODY.PEEK`، پرچم‌های صندوق دست نمیخورند؛ UIDVALIDITY تازه ← از اول، تکراری‌ها با Message-ID کنار میروند).
  - فقط پیامی که `In-Reply-To` یا `References` آن یکی از پیام‌های فرستاده‌ی ما را نام ببرد وارد پرونده میشود. بقیه ذخیره نمیشوند (فقط شمرده میشوند).
  - متن و موضوع ماسک میشوند (`hq_common.redact.scrub`). نشانی فرستنده دست نمیخورد تا مشاور آن را با دامنه‌های رسمی بسنجد.
  - پیوست‌ها از §۱۷.۱ رد میشوند: نوع از روی بایت‌ها، عکس بی‌متادیتا (در child)، متن PDF بیرون از تراکنش. بقیه فقط نامشان در timeline میآید. پیوست‌ها در هلدینگ نگه داشته میشوند تا `files.read` مشاور به آن‌ها برسد.
  - مشاور با یک کار P2 بیدار میشود (`run_meta.task_class: legal_email`).
- **هیچ ایمیلی خودکار فرستاده نمیشود.** تنها راه ارسال، effect کارت مُهرشده است.

### ۳۱.۱۲ صندوق ایمیل مشاور (کار مالک)
- **حساب سرویس `mail`** در `/tools/accounts` (اپ، 🔏 `account.put`):
  - `site`: دامنه‌ی سرویس (مثلاً `gmail.com` برای Gmail و Workspace).
  - `policy.inject: {kind: "basic", username: "<نشانی صندوق>"}`.
  - `policy.ports: [465, 993]` (یا `587` با STARTTLS اجباری).
  - `policy.mail: {imap_host, smtp_host}` فقط وقتی سرورها `imap.<site>` و `smtp.<site>` نیستند. هر دو باید روی همان site باشند، وگرنه ۴۲۲.
- **رمز:** `make account-secret KEY=mail` (app password؛ ورودی پنهان، `kv/tools/accounts/mail`). هیچ‌جا چاپ، لاگ یا پاسخ نمیشود. فقط برای همان یک فراخوانی به egress میرود.
- **egress** (`hq_egress/mail_out.py`): `POST /v1/mail/send` و `/v1/mail/fetch`، فقط از worker:
  - فقط hostهای همان site و فقط portهای خود حساب (۴۶۵ یا ۵۸۷ برای SMTP، ۹۹۳ برای IMAP).
  - TLS همیشه، با گواهی بررسی‌شده برای همان نام. اتصال به نشانیِ بررسی‌شده‌ی guard (نه نشانی خصوصی یا خود هاب).
  - فرستنده‌ی envelope همیشه خود صندوق است. هر entry در `egress.log` با ابزار `mail.send` (A3) یا `mail.fetch` (A0).
- تا مالک وصل نکند، پیش‌نویس‌ها فقط کارت‌اند و poller هیچ نمیخواند.

### ۳۱.۱۳ صدا: رجیستری `media.voices` و bake-off (پرامپت ۱۳ §۴، قرارداد §۲۲.۳)
- **یک رجیستری برای همه:**
  - گزارش‌های صوتی §۲۱.۴ با صدای فعال رجیستری حرف میزنند (وقتی image آن را دارد؛ وگرنه `HQ_TTS_VOICE`).
  - روایت آیتم‌های رسانه (`media.voice`، A2، فقط `voice_producer` در شرکت خودش) هم همین‌طور.
  - صدای غیرتجاری که مالک انتخاب نکرده ← ۴۰۹ با `voice_id: licence_not_chosen`.
- **ردیف‌ها** (هر موتور و گوینده یک ردیف؛ seed یک بار، بعد عدد اندازه‌گیری و انتخاب مالک میماند):
  - `piper-amir` (فعال، پیش‌فرض تا انتخاب مالک)، `piper-ganji`، `piper-ganji-adabi`، `piper-reza-ibrahim`: MIT و دیتاست CC0، در image.
  - `piper-gyro`: لایسنس دیتاست روی کارتش نیامده («See URL»): غیرتجاری حساب میشود و در image نیست.
  - `manatts-piper`: هنوز آموزش ندیده (پایین را ببین).
  - `parsvoice-xtts`، `parsvoice-xtts-owner`: CPML، غیرتجاری. دانلودش gated است (حساب Hugging Face مالک) و XTTS-v2 روی CPU حدود ۲٫۵ تا ۳ گیگ میخواهد. نصب نیست.
  - `chatterbox-fa`، `chatterbox-fa-owner`: CC BY-NC 4.0، gated، بیرون از بودجه. نصب نیست.
  - مدل چندزبانه‌ی آزاد با فارسی روی کارت پیدا نشد (Kokoro‏ Apache-2.0 فارسی ندارد؛ Chatterbox چندزبانه MIT فارسی ندارد؛ MMS-TTS‏ fas‏ CC-BY-NC است).
- **API مالک:**
  - `GET /media/voices`: با `licence`، `licence_commercial`، `rtf`، `mem_mb`، `installed`، `samples[]`.
  - `POST /media/voices/{id}/score {score: 1..10}`.
  - `POST /media/voices/{id}/activate` 🔏 `voice.activate` (target = id):
    - غیرتجاری بی `{accept_non_commercial: true}` ← ۴۲۲.
    - نصب‌نشده یا اندازه‌نگرفته ← ۴۰۹ `not_ready`.
    - همیشه یک صدای فعال.
  - `GET /media/voices/reference` (۴۰۴ وقتی نیست)، `POST /media/voices/reference {file_id}`:
    - فقط فایل صوتی خود مالک، ۶۰ تا ۱۸۰ ثانیه، که به هیچ پیامی پیوست نشده.
    - هیچ ایجنتی آن را نمیخواند (حتی ایجنت‌های هلدینگ) و به هیچ‌جا فرستاده نمیشود.
    - موتور کلون‌کننده‌ای روی هاب نصب نیست، پس فعلاً فقط نگه داشته میشود.
- **bake-off روی هاب:**
  - schedule `hq-voice-bakeoff` روزانه ۰۳:۴۰ (منطقه‌ی مالک): برای هر صدای نصب‌شده و هر متن ثابت، کار `sample` میسازد (یک بار برای هر round). **با قفل هلدینگ هیچ.**
  - TTS one-shot (همان timer `coinepro-hq-tts`، فقط با `HQ_TTS=on`): بعد از گزارش‌ها از `POST /internal/v1/voices/jobs/claim` کار میگیرد (۲۰۴ وقتی کاری نیست، و **همیشه با قفل هلدینگ**).
  - هر کار صدای خودش را نام میبرد. صدایی که image ندارد ← `voice not installed`، هرگز صدای دیگر.
  - Ogg با `?duration_s&synth_s&peak_mb` برمیگردد و از §۱۷.۱ رد میشود: نوع از بایت‌ها، طول از ffprobe، ردیف processing برای worker رسانه (بی pass نشانه‌گذاری مدل).
  - نام فایل خنثی است (`voice-xxxxxxxx.ogg`) تا شنیدن کور بماند. `rtf` صدا = جمع زمان کار ÷ جمع ثانیه‌های گفتار همان round؛ `mem_mb` بیشترین peak.
- **متن‌های ثابت** (`hq_api.domain.voices.SCRIPTS`؛ صدا همان شکل گفتاری `fa_speech_script` را میخواند و image همان را در `services/tts/bakeoff_scripts.json` دارد):
  - `numbers`: عدد، دلار و درصد
  - `latin`: RSI، MACD، Bitcoin، Ethereum، Fibonacci
  - `crypto`: کلمه‌های کریپتو
  - `long`: یک جمله‌ی ۶۶ کلمه‌ای
  - `reel60`: متن ریلز با هشدار ریسک (۱۵۹ کلمه، ۶۴ تا ۷۶ ثانیه)
- **اجرای اپراتور:** `make tts-bakeoff [OUT=/tmp/hq-bakeoff]`: همان image، بی‌شبکه، با سقف `MEM_TTS`. خروجی JSON است و Ogg‌ها در `OUT`.
- **عددها** (۲۰۲۶-۱۰-۲۳، همین CPX42، سقف ۳۲۰ مگ، ۱ thread، بی‌شبکه، پنج متن، ۱۴۴ تا ۱۷۷ ثانیه گفتار برای هر صدا):

| صدا | RTF | peak یک ساخت | لایسنس |
|---|---|---|---|
| piper-amir | 0.177 | 236.3 مگ | MIT + CC0 (تجاری) |
| piper-ganji | 0.170 | 254.5 مگ | MIT + CC0 (تجاری) |
| piper-ganji-adabi | 0.187 | 270.5 مگ | MIT + CC0 (تجاری) |
| piper-reza-ibrahim | 0.185 | 269.8 مگ | MIT + CC0 (تجاری) |
  - peak کانتینر (cgroup) ‏264.8 مگ.
  - RTF شامل بار کردن مدل در هر کار است.
  - با خط‌های ۱۴ کلمه‌ای، دو صدای سنگین‌تر به ۳۳۷ مگ میرسیدند و کانتینر به سقف ۳۲۰ میخورد. پس `CLAUSE_WORDS` از ۱۴ به ۸ آمد (۱۰ کلمه: ۳۰۷ مگ). `MEM_TTS=320m` همان میماند.
- **ManaTTS (برنامه و برآورد؛ کرایه‌ی GPU تصمیم مالک، §۰.۹ بند ۳):**
  - fine-tune صدای Piper/VITS از `fa_IR-amir-medium` روی ۸۶ ساعت ManaTTS (CC0، یک گوینده‌ی زن)؛ متن‌ها با همان normaliser.
  - برآورد: یک GPU ‏24GB حدود ۲۴ تا ۴۸ ساعت، ۱۵ تا ۷۰ دلار کرایه.
  - خروجی ONNX با sha256 در `voice.lock.json`، بعد همین bake-off و شنیدن کور مالک.

### ۳۱.۱۴ حافظه و هزینه‌ی بخش حقوقی و صدا (پرامپت ۱۳ §۶)
- **poller ایمیل:** داخل worker موجود، سرویس تازه ندارد. **ارسال ایمیل:** effect همان worker. **صندوق:** از egress موجود (بی سرویس و بی پورت تازه).
- **TTS:** همان one-shot پروفایل `tts` (خاموش)، `MEM_TTS=320m`، قفل مشترک با backup. سه صدای تازه در image: روی هم ۱۹۰ مگ دیسک (۳ × ۶۳٫۵)، بی اثر روی حافظه (هر کار یک صدا را بار میکند).
  - gate: full+tts ‏11216 از 12288؛ lean+tts ‏6192 از 6196. هیچ‌کدام تغییر نکرد.
- **ParsVoice-XTTS و Chatterbox:** به بودجه نمیخورند (≈۲٫۵ تا ۳ گیگ؛ full+tts فقط حدود ۱ گیگ جا دارد). اندازه‌گیری نشدند (دانلود gated، حساب مالک).
- **توکن:** کار مشاور با پاکت هلدینگ است (task classهای `legal_case` و `legal_email`، هرگز روی provider دیگر). سقف منشور: ۸ گام و ۲۰۰ هزار توکن در هر اجرا. تا راه‌اندازی هاب هیچ اجرایی نیست.

## ۳۲. بایگانی رسمی هلدینگ و شرکت‌ها، لایه‌باز (پرامپت ۱۴؛ قرارداد §۲۳)
- **migration ‏`0029`** (`0029_archive.py`، بعد از `0028_1`؛ **آخرین**):
  - schema تازه‌ی `archive`: لایه‌ی باز (`levels`، `clearance`، `classes` با `class_versions`، `fields`، `folders`، `party_kinds`، `parties`، `link_kinds`، `retention_rules`، `reminder_rules`، `automations` و `automation_runs`، `sources`) و سندها (`records`، `record_versions`، `record_files`، `intake`، `links`، `holds`، `reminders`، `access_log`، `fixity_runs`، `tombstones`، `destroy_queue`).
  - همه `company_id` و RLS **FORCE** دارند و DELETE هیچ‌جا نیست. `class_versions`، `automation_runs`، `access_log`، `fixity_runs` و `tombstones` فقط‌افزودنی‌اند.
  - نسخه‌ی مُهرشده و فایلش با trigger تغییرناپذیرند (SQLSTATE ‏`HQR01` ← `409 sealed_record`).
  - نوع‌های کارت `archive_schema` و `archive_disposal` (CHECK از روی نوع‌های موجود `NOT VALID` و بعد **validate**، چون `0029` آخرین است؛ `threads_kind_check` هم validate میشود).
  - task class ‏`archive` (همین در seed روتر)؛ `agents.queue_run` کارمند `system` دارای منشور را بیدار میکند (`HQ-ARC`؛ `HQ-SYS` منشور ندارد و هرگز بیدار نمیشود).
  - `GRANT UPDATE (transcript)` روی `files.processing` برای api، و CHECK ‏`auth.step_ups.action` یک بخش سوم میپذیرد (`archive.hold.release`).
  - **زنجیره (روی ۱۳ deploy‌شده):** `0025` ← `0026` ← `0026_1` ← `0027` ← `0027_1` ← `0027_2` ← `0028` ← `0028_1` ← `0029`. `0029` آخرین است و تنها migrationی است که CHECKهای kind را (با همه‌ی نوع‌های ۱۱ تا ۱۴) validate میکند؛ `0028_1` دیگر validate نمیکند (production آن را پیش‌تر اجرا کرده و دست نمیخورد).
- **قانون‌های قطعی:**
  1. هیچ رمزی وارد بایگانی نمیشود: `422 secret_in_document`؛ فایل نگه داشته نمیشود و هیچ بخشی از آن لاگ نمیشود.
  2. هیچ چیزی بی مُهر مالک پاک نمیشود: امحا فقط با کارت مُهرشده‌ی `archive_disposal`. سند توقیف‌شده هرگز.
  3. سطح دیدن نشت نمیکند، و این را RLS پایگاه داده تضمین میکند.
  4. مدل فقط پیشنهاد میدهد.

### ۳۲.۱ سطح‌ها و مجوز دیدن در خود پایگاه داده (§۲۳.۴)
- هر تراکنشی که بایگانی را میخواند اول `app.clearance` را با `set_config(..., true)` میگذارد (`hq_api.archive.clearance`). بدون آن هیچ سندی دیده نمیشود.
  - مالک و jobهای خود هاب: `{"all": true}`.
  - ایجنت: `{"code", "grants": {<company uuid>|"*": rank}, "meta": rank}` از ردیف `employee:<code>`، وگرنه `role:<charter>`، وگرنه `role:*`.
- `archive.can_see(rank, scope)` (محتوا) و `archive.can_see(rank, scope, filed_by)` (metadata؛ استثنای بایگان برای چیزی که خودش ثبت کرده تا `metadata_level`) در policyهای `records`، `record_files` (فقط محتوا)، `record_versions`، `links`، `reminders`، `access_log` و `tombstones`.
- seed: `public` 0، `internal` 10، `confidential` 20 (واترمارک، `agents_max`)، `secret` 30 (واترمارک، رمزنگاری، step-up برای دیدن). هر نقش ایجنت `internal` در شرکت خودش؛ مشاور حقوقی `confidential` در همه؛ بایگان `confidential` برای محتوا و `secret` برای metadata. مجوز ایجنت هیچ‌وقت از سطح `agents_max` بالاتر نمیرود.
- metadata‌ی حساس زیر `confidential` پنهان است؛ `id_code` و `iban` برای هر ایجنت تا ۴ رقم آخر.
- رویدادهای stream (موضوع `archive`: `record.filed`، `record.updated`، `record.sealed`، `reminder.due`، `hold.changed`، `fixity.failed`، `schema.changed`) فقط ref، سطح، رده و وضعیت دارند؛ نه عنوان، نه مقدار.
- آزمون: «RLS حتی با SQL مستقیم نقش api» در `tests/test_p14_archive.py`.

### ۳۲.۲ لایه‌ی باز: طرح بایگانی (§۲۳.۲، §۲۳.۳، §۲۳.۷، §۲۳.۱۰، §۲۳.۱۲)
- **seed:** `infra/seed/archive/*.yaml`، که در api، worker و api-migrate روی `/app/seed/archive` (فقط‌خواندنی، `HQ_ARCHIVE_SEED`) سوار است. seed هر `make up` اجرا میشود و فقط چیزی را که نیست اضافه میکند. **هر چیزی که مالک عوض یا بازنشسته کرده دوباره نوشته نمیشود.** پوشه‌های هر scope هم وقتی اولین سند آن scope ثبت میشود ساخته میشوند.
- `GET /archive/schema`: همه‌ی ردیف‌ها با شمار استفاده، `vocab` بسته (رویدادها، اقدام‌ها، عملگرها، نوع‌های ref، ارزها، mimeها) و `owner_settings.agents_max`.
- `PUT /archive/schema/{part}/{key}`:
  - 🔏 `archive.schema` (برای `clearance`: `archive.clearance`) روی SHA-256 بدنه.
  - `If-Match`؛ برای کلید تازه `If-None-Match: *`. پوشه، قاعده‌ی نگهداری، یادآور و اتوماسیون با کلید `new` ساخته میشوند و ref را سرور میدهد.
  - `?dry_run=1` فقط اثر را میگوید و passkey نمیخواهد.
  - خطا: `422 schema_invalid` با `fields`. فیلد هیچ‌وقت حذف نمیشود (فقط `status: retired`)، نوعش عوض نمیشود و گزینه‌ی enum کم نمیشود. rank سطحی که سند دارد ثابت است.
  - تغییر رده = نسخه‌ی تازه‌ی رده (`class_versions`)؛ سند نسخه‌ای را نگه میدارد که با آن ثبت شده. اگر فیلد اجباری تازه سندهای ثبت‌شده را ناقص کند، بایگان یک کار «تکمیل N سند» میگیرد.
- `POST …/retire` با همان 🔏 روی hash بدنه‌ی `{part, key, version}`.
- **پیشنهاد ایجنت:** کارت `archive_schema` با payload ‏`{part, key, base_version, body, impact}` (بدنه همان بدنه‌ی PUT است و موقع پیشنهاد اعتبارسنجی میشود). مالک با step-up معمول `decision.approve` (target = ref کارت) مُهر میکند و همان بدنه در همان تراکنش اعمال میشود. اگر آن ردیف از `base_version` به بعد عوض شده باشد، کارت باطل است (`409 decision_not_pending`).
- **اتوماسیون:** فقط قاعده، هرگز مدل. رویدادهای بسته، شرط‌های ساده، و اقدام‌ها: `notify` (هرگز urgent)، `work_item` (نقش هاب؛ تا هلدینگ یا آن شرکت قفل است `deferred`)، `link`، `move_to_folder`، `raise_level` (فقط بالا؛ سطحی که رمزنگاری دارد کار PATCH مالک است)، `add_reminder`. هر اجرا یک ردیف `automation_runs` و یک ردیف audit است.

### ۳۲.۳ سند، نسخه، فایل (§۲۳.۱، §۲۳.۱۲)
- فایل از همان مسیر §۱۷.۱ میآید (`POST /files`). بعد `POST /archive/intake {file_ids}` (یا هر ساخت سند از file id) **پیش از هر تراکنش**:
  1. متن: لایه‌ی متن PDF در child process؛ عکس و اسکن از OCR worker (اگر profile روشن است، تا `HQ_ARCHIVE_OCR_WAIT_S`=60 ثانیه منتظر میماند، وگرنه در صف میرود).
  2. اسکن رمز روی نام و متن (`hq_api.archive.scan`): قاعده‌های credential در `hq_common.redact` (همان شکل‌های gitleaks و نگهبان خروجی §۱۹.۶)، عبارت بازیابی BIP-39 و کلید خصوصی `customer_mask`، و `otpauth://`، کلید hex برچسب‌دار و کدهای پشتیبان. مقدارها، عنوان و یادداشت هم اسکن میشوند.
  3. اگر رمز پیدا شد: `422 secret_in_document`. فایل مالک که هنوز در هلدینگ منتظر است (bytes، نسخه‌های کوچک‌شده و متن استخراج‌شده) همان‌جا نابود میشود و چیزی از آن لاگ نمیشود.
  4. وگرنه ردیف `archive.intake` با hash، صفحه‌ها، متن و پیشنهاد قاعده‌محور.
- **ذخیره:** هر سند نسخه‌ی خودش را در همان file store (volume ‏`hq-files`) دارد. وقتی سند ثبت شد، فایل منتظر مالک از آن بایگانی است و bytes و variantهایش برداشته میشوند. **فایلی که مالک در رشته‌ای پیوست کرده با همان پیام میماند.**
- **`secret`:** AES-256-GCM با کلید داده‌ی تازه از OpenBao transit ‏`archive-secret` (`datakey/plaintext`). فقط کلید wrapشده در پایگاه داده میماند و کلید transit هرگز از OpenBao بیرون نمیآید. کلید را `provision.sh` میسازد (exportable نیست، حذف نمیشود). api و worker فقط `datakey/plaintext` و `decrypt` همین کلید را دارند.
  - دیدن فایل 🔏 `archive.view` (target = ref) میخواهد.
  - بالا رفتن سطح به `secret` (یا پایین آمدن از آن) فایل‌ها را دوباره ذخیره میکند؛ نسخه‌ی قبلی بعد از commit از `destroy_queue` پاک میشود.
- **دانلود** (`GET /archive/records/{ref}/files/{file_id}`): hash ذخیره و hash plaintext سنجیده میشوند (ناهمخوانی ← `409`). سطح دارای `watermark` نسخه‌ی نشانه‌دار میگیرد (PDF با pypdf، عکس با Pillow، در child process؛ اصل دست‌نخورده). هر دیدن، دانلود، خواندن metadata و تغییر سطح یک ردیف `access_log` است (`GET …/access` فقط مالک).
- **مُهر:** `POST …/seal {manifest_sha256}` با 🔏 `archive.seal` روی همان manifest (SHA-256 خط‌های مرتب `"<sha256>  <name>"`). سرور آن را دوباره حساب میکند (`409 seal_mismatch`).
  - سند مُهرشده به هر PATCH جز `level` جواب `409 sealed_record` میدهد. بالا بردن سطح آزاد است و پایین آوردن 🔏 `archive.declassify` با target ‏`ref@version:level` میخواهد (`version` = نسخه‌ی ردیف، همان If-Match). مُهر دست‌نخورده میماند.
  - `POST …/versions` نسخه‌ی قبلی را `superseded` میکند و سند دوباره `filed` میشود.
- **draft:** کار ایجنت (`archive.file`)، import مالک (`POST /archive/import`: یک draft برای هر فایل و یک کار برای بایگان)، یا مالک با `file: false`. `POST …/file` (با `If-Match`) draft کامل را `filed` میکند.

### ۳۲.۴ OCR و جستجو (§۲۳.۹)
- **profile اختیاری `ocr`، پیش‌فرض خاموش:** Tesseract 5.5.0 با tessdata_fast پین‌شده‌ی `fas` و `eng` (`services/ocr/model.lock.json`). روی شبکه‌ی داخلی `hq-ocr` (172.30.24.0/24) که فقط worker در آن است؛ بی اینترنت، بی پورت، بی رمز، و یک کار در هر لحظه (درخواست دوم ← 429).
  - روشن کردن: یک‌بار `make ocr-fetch` (تنها دانلود از اینترنت)، بعد `make ocr-on`. خاموش: `make ocr-off`. `hq.sh` بیرون از بودجه‌ی حافظه `up` را رد میکند (exit 3).
  - بودجه: روی full تنها جا میشود، ولی نه همراه media یا mcp، و نه روی lean.
  - عددها: هر صفحه‌ی عکس ۰٫۲ تا ۰٫۵ ثانیه و حداکثر 61 MiB؛ هر صفحه‌ی PDF اسکن حدود ۱٫۳ ثانیه و حداکثر 149 MiB؛ `MEM_OCR=320m`. `make ocr-bench` و `make ocr-test` دوباره بی‌شبکه میسنجند.
  - حدها: ۳۰ مگ برای هر فایل، ۴۰ مگاپیکسل برای عکس، پیش‌فرض ۵۰ صفحه، ۱۲۰ ثانیه برای هر کار.
- **تا خاموش است** worker ‏`HQ_OCR_URL` ندارد و اسکن‌ها با `text_state: "none"` و `ocr_wanted` میمانند، بی هیچ خطا. وقتی روشن شود، صف (`hq-archive-ocr`، هر ۲ دقیقه، یک فایل در هر لحظه) آن‌ها را میخواند.
  - متن OCR هم اسکن رمز میشود. اگر رمز داشت، فایل `quarantined` میشود: دیگر سرو و جستجو نمیشود، متنش نگه داشته نمیشود و مالک یک اعلان report میگیرد. امحا با تصمیم خودش است.
  - صفحه‌ی با اطمینان کمتر از ۰٫۶ در `low_confidence_pages` علامت میخورد.
- **جستجو** (`GET /archive/search`): Postgres FTS (`simple` روی `hq_common.persian` و `core.fa_normalize`) روی سه بردار: `meta_tsv` (عنوان، ref، فیلدهای searchable، نام طرف‌ها)، `text_tsv` (متن فایل، فقط با مجوز محتوا) و `sens_tsv` (فیلدهای حساس، فقط از `confidential` به بالا)، به‌علاوه‌ی `pg_trgm` روی عنوان (`archive.title_similarity`). رتبه بعد از فیلتر مجوز است و snippet فقط از متنی است که خواننده مجاز است ببیند.
- `knowledge.search` نوع `records` میگیرد (هر نقش، در مجوز خودش)، کنار `knowledge` چهارلایه‌ی پرامپت ۱۱ و `docs`/`code`/`notes` پرامپت ۱۲. «از هاب بپرس» (§۲۱.۲، ۳۰.۸) سندها را در مجوز پرسنده میگردد (`archive.search.ask_hits`، فیلتر مجوز پیش از رتبه‌بندی)؛ مجوز مالک آنجا تا `agents_max` است، چون قطعه‌ها به کتابدار میرسند.
- **پیشنهاد قاعده‌محور:** تاریخ جلالی و میلادی، مبلغ با واحد، شبا، کد ملی، شماره‌ی ثبت، رده از روی کلیدواژه و طرف‌های رجیستری. فقط نشان داده میشود و هیچ‌وقت خودش ثبت نمیشود.

### ۳۲.۵ نگهداری، امحا، توقیف و پشتیبان (§۲۳.۵)
- **قاعده‌ی seed** (پیش‌فرض‌هایی که مالک بازبینی میکند، **نه مشاوره‌ی حقوقی**):
  - قرارداد و توافق: ۷ سال بعد از `end`
  - فاکتور: ۷ سال بعد از `date`
  - مجوز و دامنه: ۲ سال بعد از `expires_at`
  - مکاتبه‌ی حقوقی: ۱۰ سال بعد از بسته شدن پرونده
  - ثبت، سیاست مُهرشده، نشان و مصوبه‌ها: دائمی
  - سایر: بازبینی بعد از ۳ سال
- **job روزانه** (`hq-archive-daily`، ۰۴:۳۰ منطقه‌ی مالک؛ قاعده‌محور):
  - `then: review`: در هر اجرا **یک** کار برای بایگان، و فقط وقتی هلدینگ باز است.
  - `then: dispose_card`: حداکثر یک کارت `archive_disposal` در حال انتظار و یکی در هفته، برای مالک، **بی هیچ سند توقیف‌شده‌ای**.
  - رویداد `retention_due` اتوماسیون، یک بار برای هر سند.
- **بعد از مُهر کارت** (همان تراکنش تصمیم):
  - سندی که در این فاصله توقیف شده یا دیگر سررسید نیست کنار میماند و در مصوبه نام برده میشود.
  - برای بقیه: ردیف فایل‌ها `destroyed` میشود (کلید wrapشده‌ی `secret` هم)، سنگ‌نوشته با ref، رده، عنوان، تاریخ‌ها، hash هر فایل و ref کارت ثبت میشود، و metadata و متن پاک میشوند.
  - bytes بعد از commit از `destroy_queue` برداشته میشوند. job روزانه هم هر کلید جامانده را برمیدارد.
  - رد کارت یعنی مالک نگهشان داشته (`disposal_kept`؛ زیر همان قاعده دوباره پیشنهاد نمیشوند). برگشت، انقضا یا withdrawn یعنی کارت هفته‌ی بعد.
- **توقیف قانونی:**
  - مشاور حقوقی با `archive.hold` (A2، فقط برای پرونده‌ی خودش) یا مالک با `POST /archive/holds`.
  - scope: یا فهرست صریح `records`، یا facetهای `folders`، `classes`، `parties` و `from`/`to` که همه باید بخوانند.
  - سند توقیف‌شده به هر تغییری جز نسخه‌ی تازه `423 held` میدهد.
  - آزاد کردن فقط کار مالک است: `POST /archive/holds/{ref}/release` با 🔏 `archive.hold.release` روی ref.
- **پشتیبان:** فایل‌های بایگانی در همان volume ‏`hq-files` هستند، پس هر ساعت در restic میروند و با Drive همگام میشوند.
  - آزمون بازیابی (`make restore-test` و آزمون هفتگی) جدیدترین فایل بایگانیِ امحانشده را برمیگرداند و sha256 آن را با `stored_sha256` پایگاه داده‌ی بازیابی‌شده میسنجد. خط PASS نام سند را دارد (`archive=AR-…`).
  - نتیجه‌ی اولین آزمون هر ماه جلالی به منبع `backup_restore_test` بایگانی میشود.
- **امحا و snapshotهای قدیم:** امحا فایل را از هاب برمیدارد، ولی snapshotهای restic که پیش از آن گرفته شده‌اند هنوز آن را دارند (رمزنگاری‌شده با کلید restic). این snapshotها طبق retention خود restic پیر میشوند (§۱۸.۹: ساعتی، روزانه، هفتگی، ماهانه، سالانه) و `prune` آن‌ها را برمیدارد. **هیچ snapshotی برای یک امحا دستی پاک نمیشود.**
  - فایل `secret` در snapshot هم بی کلید wrapشده‌اش (که امحا شده) خواندنی نیست. بازیابی کامل پایگاه داده از snapshot قبل از امحا آن کلید را برمیگرداند. پس بازیابی کامل هم تصمیم مالک است.

### ۳۲.۶ یادآورها (§۲۳.۶)
- seed: پایان قرارداد ۶۰/۳۰/۷ روز، انقضای مجوز و دامنه ۹۰/۳۰/۷، بازبینی توافق افیلیت ۳۰/۷. همه به مالک، در کارتابل.
- job روزانه: برای هر قاعده و هر سند، **نزدیک‌ترین** مهلتی که رسیده یک یادآور است، یک بار برای هر (سند، فیلد، تاریخ، مهلت).
  - کارتابل: اعلان سطح `decision` (§۲۱.۸؛ در خلوت نگه داشته میشود، در digest).
  - digest: اعلان سطح `report`.
  - نقش یا مدیرعامل شرکت: کار؛ تا هلدینگ یا آن شرکت قفل است `pending` میماند و هیچ اجرایی بیدار نمیشود.
- بستن: `POST /archive/reminders/{id}/done`. اگر تاریخ سند عوض شود، یادآور قدیمش خودش بسته میشود.

### ۳۲.۷ منبع‌های سیستمی (§۲۳.۸)
- `GET /archive/sources` و `PUT /archive/sources {<key>: on}`. پیش‌فرض همه روشن‌اند.
- job ‏`hq-archive-sources` (هر ۱۵ دقیقه، قاعده‌محور) رخداد تازه‌ی هر منبع را **یک بار** (`source_ref` یکتا) به‌صورت سند `filed` با `source.kind: "system"` ثبت میکند:
  - `charter_sealed`: از `governance.charters` (پرامپت ۱۱)؛ تا آن جدول نیست هیچ.
  - `resolution_month`: مصوبه‌های یک ماه جلالیِ تمام‌شده‌ی هر شرکت.
  - `brand_sealed`، `founding_registration`، `server_plan_sealed`، `backup_restore_test`.
  - `legal_email`: هر ایمیل ارسال‌شده‌ی پرونده.
  - `case_closed`: پرونده‌ی بسته با روندش، پیوندخورده به پرونده؛ و ماشه‌ی نگهداری `case_closed`.
- PDF با کتابخانه‌های خود هاب ساخته میشود: resvg-py صفحه‌ی A4 را با IRANYekanX راست‌به‌چپ میکشد و Pillow صفحه‌ها را یک PDF میکند. این کار در child process است. متن همان منبع با `text_state: text_layer` ذخیره میشود.
- فیلد اجباری که منبع نمیداند (مثلاً شماره‌ی ثبت پیشنهاد تأسیس) خالی میماند و `impact` آن را میشمارد. موردی که الگوی رمز دارد ثبت نمیشود و فقط در `note_fa` منبع میآید.

### ۳۲.۸ سلامت فایل (fixity)
- `hq-archive-fixity` (۰۳:۲۰ منطقه‌ی مالک) هر شب یک‌هفتم فایل‌ها را دوباره hash میکند. برش هر فایل با id آن ثابت است، پس در یک هفته همه‌ی فایل‌ها سنجیده میشوند. `kind: manual` یا `weekly` همه را میسنجد. هر اجرا یک ردیف `fixity_runs` است و `GET /archive/fixity` جواب `{at, checked, failed, next_at}` میدهد.
- **ناهمخوانی یا فایل گم‌شده = هشدار از دست رفتن داده:** یک اعلان `urgent` (دسته‌ی data loss؛ تنها urgent بایگانی)، رویداد `fixity.failed`، و یک کار P1 برای SRE پلتفرم هاب (فقط وقتی هلدینگ باز است).
- **اقدام:** فایل را از آخرین snapshot سالم برگردان (§۱۸.۹). هیچ ردیف بایگانی را دستی عوض نکن.

### ۳۲.۹ ایجنت‌ها، OPA و gateway (§۲۳.۱۱)
- ابزارها (gateway: `hq_gateway/archive.py`؛ OPA: `archive.rego`):
  - `archive.search` و `archive.read` (A0)
  - `archive.file` و `archive.link` (A1)
  - `archive.hold` (A2، فقط مشاور حقوقی با پرونده‌ی خودش)
  - فقط بایگان و مشاور حقوقی، هر دو نقش هلدینگ. api نقش و مجوز را دوباره میسنجد.
- **بایگان** (`HQ-ARC`، kind ‏`system`، منشور `archivist`): نقش سیستمی هلدینگ است؛ استخدام، امتیاز یا ستاره ندارد و تا کاری برسد خواب است.
  - `archive.file` روی draft واردشده‌ی مالک فقط پیشنهاد (`suggestion.by: archivist`) مینویسد، و در بقیه‌ی موارد یک draft تازه. **هیچ‌وقت ثبت، مُهر، پایین آوردن سطح، آزاد کردن توقیف یا امحا نمیکند**؛ مسیرهای مالک برایش ۴۰۳ است.
  - تغییر طرح را فقط با کارت `archive_schema` پیشنهاد میدهد.
- تا کلید توقف هلدینگ روشن است، runner بایگان را اجرا نمیکند (`locked`). ثبت دستی مالک و همه‌ی jobهای قاعده‌محور کار میکنند.

### ۳۲.۱۰ زمان‌بندی‌ها و دروازه‌ی راه‌اندازی
| schedule | زمان | نوع |
|---|---|---|
| `hq-archive-daily` | روزانه ۰۴:۳۰ | قاعده‌محور: نگهداری، یادآور، صف نابودی، گزارش هفتگی بایگان (شنبه) |
| `hq-archive-fixity` | روزانه ۰۳:۲۰ | قاعده‌محور: hash محلی |
| `hq-archive-ocr` | هر ۲ دقیقه | قاعده‌محور: Tesseract خود هاب، بی شبکه؛ تا profile خاموش است هیچ |
| `hq-archive-sources` | هر ۱۵ دقیقه | قاعده‌محور: خواندن پایگاه داده و PDF |
- هیچ‌کدام مدل یا سرویس بیرونی صدا نمیزند، پس با کلید توقف هم اجرا میشوند (هشدار fixity، یادآور و کارت امحا برای مالک).
- هر چیزی که ایجنتی را بیدار کند (کار بازبینی بایگان، یادآور نقش، کار SRE، کار `work_item` اتوماسیون، گزارش هفتگی) با `gate.holding_lock` یا `gate.automation_lock` منتظر میماند: کار ساخته نمیشود و اجرایی صف نمیشود.
- آزمون: `test_the_archive_jobs_are_rule_only_and_wake_no_agent_while_the_holding_is_locked`.

### ۳۲.۱۱ عیب‌یابی
| علامت | کار |
|---|---|
| `503 channel_not_configured` موقع ثبت سند `secret` | transit یا کلید `archive-secret` در OpenBao آماده نیست: `provision.sh` آن را در هر `make up` میسازد (یا `make llm-provision`)؛ policyهای تازه‌ی api و worker هم همان‌جا نوشته میشوند |
| اسکن‌ها `text_state: none` میمانند | profile ‏`ocr` خاموش است (پیش‌فرض)؛ با `make ocr-fetch` و `make ocr-on` روشن کن؛ صف خودش میخواند |
| `409 seal_mismatch` موقع دانلود | fixity: فایل ذخیره‌شده با hash نمیخواند؛ ۳۲.۸ |
| کارت امحا نمیآید | یکی هنوز منتظر است، یا کمتر از یک هفته از قبلی گذشته، یا همه‌ی سررسیدها توقیف یا `disposal_kept` هستند (`GET /archive/retention/due`) |
| `423 held` | توقیف قانونی؛ فقط نسخه‌ی تازه، یا آزاد کردن با مُهر مالک |
