# پرامپت ۹.۲: بازبینی پرامپت ۹ (پیش از deploy ۹)

> Claude سشن مشورت، ۲۰۲۶-۱۰-۲۲.
> - **مبنا:** `server/p09-founding`، commit 5ddce4b. دو بازبین موازی: (۱) provisioner، قالب‌های cloud-init، egress و OpenBao؛ (۲) API تأسیس، OPA، gateway، migration 0023 و شکل JSONی که دو اپ میخوانند. شماره‌ی خط‌ها روی 5ddce4b است.
> - **کجا اصلاح کنی:** روی `server/p09-founding`، بعد از اینکه ۸ با اصلاح‌های ۸.۱ deploy و در این شاخه merge شد.
> - **ترتیب:** §۱ تا §۳ **پیش از deploy ۹**. §۴ (ریزها) اگر وقت شد.
> - **گزارش:** زیر «Review of 9» در `docs/ops/reports/PROMPT_09.md`، برای هر بند یک خط.
> - **قرارداد:** §۱۸.۱۶ (v1.4.8) تصمیم‌های همین بازبینی است.
> - **بعد از این:** پرامپت ۹.۱ (مُهر شرکت) روی همین پایه.

## ۱. مسدودکننده‌ها
1. **هر گام cloud-init با شکست هم «ok» گزارش میشود.** کد: `infra/provisioning/templates/_header.sh:47` (`if "$fn"; then`).
   - **چرا:** bash داخل تابعی که شرط `if` است `set -e` را خاموش میکند. خروجی گام همان خط آخرش است (`result <key> 1 …`) که تقریباً همیشه موفق است. فقط `return 1` صریح گام را شکست میدهد.
   - **سناریو (بازسازی‌شده):**
     - tarball دستکاری‌شده‌ی Node: `node-lts.sh:13` میگوید sha256 نخواند، ولی tarball باز میشود و `node` با root اجرا میشود؛ گام `ok`.
     - `ssh-hardening.sh:18`: `sshd -t` شکست میخورد و باز ssh reload میشود.
     - `work-user.sh:16`: `visudo -cqf` شکست میخورد و فایل خراب به `/etc/sudoers.d` میرود.
     - `work-user.sh:6`: `useradd` شکست میخورد، `ssh-hardening` کلیدهای root را پاک میکند و `AllowUsers` به کاربری که نیست؛ هیچ‌کس وارد نمیشود.
   - **اصلاح:** در `run_step`: `set +e; ( set -e; "$fn" ); rc=$?; set -e`. `system-upgrade` نیاز به ریبوت را با کد خروج اعلام کند، نه `exit 0`. در bench: sha256 غلط Node و `sshd -t` شکست‌خورده.
2. **لغو تأسیس چیزی را که باز کرده نمیبندد؛ تأسیس لغوشده هنوز شرکت یا سرور میسازد.** کد: `cancel()` در `domain/founding.py:1023-1053`؛ هیچ‌کدام از `seal()` (`:403-454`)، `next_run()` (`:1114-1149`)، `resume()` (`:1368-1385`) و `found_company()` (`:885-943`) لغو را نمیبینند.
   - **سناریوها:**
     - لغو در `proposed`: کارت `company_found` در کارتابل میماند؛ مالک تأیید میکند، شرکت ساخته میشود و تأسیس از `cancelled` به `sealed` برمیگردد.
     - لغو در `sealed`: کارت `server_plan` هنوز مُهرشدنی است، یا طرح مُهرشده وقتی provisioner بالا آمد ساخته میشود: **سرور پولی برای تأسیسی که هرگز تمام نمیشود.**
     - work itemهای ممیزی و پیشنهاد باز میمانند؛ جلسه‌های `stopped` کارگاه دور ریخته میشوند (`:1035`).
   - **اصلاح:**
     - `cancel()`: کارت‌های pending `company_found` و `server_plan` همان تأسیس withdraw شوند؛ طرح مُهرشده‌ی اجرانشده به `proposed` برگردد؛ کار ممیزی و پیشنهاد لغو شود؛ `service.stopped` صدا زده شود.
     - `found_company()`: فقط وقتی `f.state = 'proposed' AND f.decision_id = d.id`.
     - `seal`، `next_run` و `resume`: طرحی که تأسیسش `cancelled` است را رد کنند.
   - **تست:** هر سه سناریو؛ هیچ شرکت یا سروری بعد از لغو.
3. **JSON تأسیس هر دو اپ را میشکند.** جزئیات در §۳. بدترین‌ها: `GET /foundings` آرایه‌ی خالی است (وب فهرست خالی میبیند، اندروید decode نمیکند)؛ `Founding.plan` شیء است نه ref؛ `steps[].log_tail` فهرست است؛ `monthly_eur` گاهی null.

## ۲. «باید»ها
1. **مسیر SSH به کل اینترنت از دو راه باز میشود.** کد: `services/hq-common/src/hq_common/provisioning.py:128` فقط `port == "22"` با `/0` را میگیرد.
   - **رد میشوند ولی نباید:** `{tcp, "1-65535", ["0.0.0.0/0","::/0"]}` کنار یک قانون ۲۲ درست؛ `{tcp, "22", ["0.0.0.0/1","128.0.0.0/1"]}`.
   - **اصلاح:** هر بازه‌ی tcp که ۲۲ را شامل شود SSH است؛ منبع‌هایی که روی هم کل فضا را میپوشانند رد شوند (جز روی 80 و 443)؛ **منبع SSH باید زیرمجموعه‌ی `owner_settings.provision_ssh_sources` باشد.**
2. **`work_user` میتواند حساب سیستمی موجود باشد و `NOPASSWD:ALL` بگیرد و سرور را قفل کند.** کد: `provisioning.py:56,60` (فقط ۸ نام رزرو)، `domain/founding.py:797-798` (پیش‌فرض `code.lower()`)، `work-user.sh:6` (`id … || useradd`).
   - **سناریو:** شرکتی با کد `MAIL`، `PROXY`، `BACKUP`، `NEWS`، `LIST`، `IRC`، `GAMES`، `MAN`، `LP`، `UUCP`، `SYSLOG` یا `TSS`: کاربر موجود `mail` با shell `nologin` و home `/var/mail`؛ `AllowUsers mail` و پاک شدن کلیدهای root؛ سرور غیرقابل ورود ولی `ready_for_login`؛ و دیمون `mail` با `NOPASSWD:ALL`.
   - **اصلاح:** `useradd` کاربر را بسازد و اگر هست **شکست بخورد** (استفاده‌ی دوباره فقط در اجرای تکراری، با نشانه‌ای که خود قالب نوشته)؛ هر نامی که در `/etc/passwd` و `/etc/group` پایه‌ی Ubuntu 24.04 هست رد شود؛ پیش‌فرض `<code>-ops`.
3. **اجرای گیرکرده در `running` و تأسیس گیرکرده در `provisioning`.**
   - `runner.py:95-99` فقط `NotConfigured` را میگیرد؛ `OpenBaoError` (مثلاً OpenBao sealed بعد از ریبوت هاب) بیرون میزند؛ `hub.step` در `:105` بیرون `try` است؛ `_fail` خودش `HubError` میدهد؛ restart کانتینر وسط کار. نتیجه: اجرا برای همیشه `running`، `resume` فقط `failed` را میپذیرد (`founding.py:1371`).
   - callback فقط در `running` پذیرفته میشود (`founding.py:1431`): `boot` بعد از ۶۰۰ ثانیه `failed` میشود، گزارش بعدی سرور ۴۰۱ میگیرد، توکن پاک میشود، و `resume` بعد از ۶۰ دقیقه دوباره `callback_timeout`.
   - `finish()` (`:1328-1333`) فقط روی `done` جلو میرود و `cancel()` در `provisioning` رد میکند (`:1028-1029`).
   - **اصلاح:** `Exception` دور خواندن رمزها و اولین `hub.step` گرفته شود؛ یک reaper در API اجرای `running` بی‌فعالیت بعد از `callback_wait_s` + حاشیه را `failed` کند؛ callback در `failed` هم پذیرفته شود اگر توکن معتبر و استفاده‌نشده است؛ اجرای شکست‌خورده تأسیس را به `sealed` برگرداند یا لغو را اجازه دهد.
4. **مدیر فنی یک شرکت طرح سرور تأسیس هلدینگ را مینویسد.** کد: `routes/founding.py:447-465` با `infra/opa/policy/internal.rego:194-198`. `TY-TECH-MGR` با `server.plan {company: "TY", founding: "C-0001"}` طرح را با `company_id` هلدینگ میسازد و `proposed()` (`:816-833`) آن را برمیدارد؛ خطاهای ۴۰۹ و ۴۲۲ وضعیت تأسیس را لو میدهند. **اصلاح:** `provisioning.plan` با `founding` فقط برای خواننده‌های هلدینگ (OPA و route)؛ بدون `founding`، فقط دامنه‌ی خود صداکننده.

## ۳. شکل JSON (قرارداد §۱۸.۸ و §۱۸.۱۶؛ دو اپ همین را میخوانند)
| مسیر یا فیلد | الان | باید |
|---|---|---|
| `GET /foundings` | آرایه‌ی ساده، `LIMIT 200` | `Page<Founding>` با cursor |
| `Founding.plan` | شیء کامل `ServerPlan` | ref (`"PV-0001"\|null`)؛ اگر لازم است شیء در `plan_detail` |
| `Founding.source.repo` | برای `idea` نیست | `null` |
| `Founding.brand` | نیست | `{state, version}` (§۱۸.۱۴؛ تا ۹.۱، `{state: "missing", version: null}`) |
| `ProvisionRun.server.host_keys` | جمع میشود ولی برنمیگردد | fingerprintهای کلید میزبان سرور، تا مالک در اولین ورود بسنجد |
| `POST /provisioning/runs/{id}/resume` | هست | در قرارداد ثبت شد |
| فیلدهایی که nullable شدند (`name_fa`، `name_en`، `code` پیش از پیشنهاد، `audit.session_ref`، `audit.scores.*`، `firewall[].port` برای icmp، `server.ipv4/ipv6`، `monthly_eur` پیش از قیمت) | — | همان‌طور بماند؛ اپ‌ها را من هماهنگ میکنم |
| پول (`monthly_usd`، `monthly_eur`) | رشته | همان‌طور بماند (قرارداد §۱: پول رشته‌ی دهدهی است)؛ اپ‌ها را من هماهنگ میکنم |
| `steps[].log_tail` | فهرست خط | همان‌طور بماند؛ قرارداد §۱۸.۱۶ |
| `ProvisionRun.state` | `queued` هم دارد | همان‌طور بماند؛ قرارداد §۱۸.۱۶ |

## ۴. ریزها (اگر وقت شد)
- `GET /provisioning/plans/{ref}` قیمت را دوباره میگیرد، نسخه را بالا میبرد و Audit مینویسد (`routes/founding.py:253-274`)؛ `GET /infra/servers` هر بار ردیف `infra.inventory` میسازد و تا ۲۰ ثانیه HTTP با تراکنش باز (`:381`). GET نباید بنویسد: قیمت را در زمان‌بند یا روی دکمه‌ی «قیمت تازه» بگیر.
- فیلتر `kind` در `/decisions` (`routes/decisions.py:54-65`) `company_found` و `server_plan` را نمیپذیرد.
- `seal()` طرحی را که کارت `server_plan`ش رد، برگشتی یا منقضی است هم مُهر میکند (`founding.py:426-428`).
- `CompanyFoundPayload.plan` پذیرفته و نادیده گرفته میشود.
- توکن callback در argv کرل دیده میشود (`_footer.sh:29`): header از فایل `600` با `-H @file`.
- رد رمز root در resume دور زده میشود (`hetzner.py:196-198`، `runner.py:172-179`): رد ثبت شود و resume هم `refused` بدهد.
- کلیدهای سخت‌سازی اختیاری‌اند و `_login` (`runner.py:287`) خط ssh را حتی بی `work-user` میدهد: `ssh-hardening`، `unattended-upgrades` و `work-user` اجباری شوند.

## ۵. پاک‌ها (بازبین‌ها تأیید کردند)
- فقط منابع با برچسب `managed-by=coinepro-hq`؛ هیچ delete، rebuild یا power؛ شبکه‌ی خصوصی مال خود شرکت (`10.20.0.0/16`)، هرگز `10.10.1.0/24` هاب.
- digest یکی در API و provisioner؛ مُهر روی digest؛ بی قیمت مُهر نمیشود؛ تأیید `server_plan` از کارتابل ۴۰۹.
- توکن callback فقط sha256، یک‌بارمصرف، ۶۰ دقیقه، با rate limit؛ listener سوم egress فقط `api.hetzner.cloud:443`؛ AppRoleهای فقط‌خواندنی OpenBao؛ ورودی پنهان `make hetzner-token`؛ هیچ رمزی در لاگ یا پاسخ؛ هیچ دستی به SSH، ufw یا iptables هاب و همسایه‌ها.
- activation فقط مالک با step-up و فقط از `ready_for_login`؛ migration 0023 با RLS FORCE روی هر شش جدول؛ هیچ کد یا تعداد شرکت hard-code نشده.

## ۶. پایان
- §۱ تا §۳، تست برای هر بند، `make check` سبز.
- **deploy ۹** (migration 0023)، `make verify-live` سبز. `HQ_PROVISIONING` خاموش میماند تا مالک `make hetzner-token`، `make owner-ssh-key` و منبع‌های SSH را بدهد.
- گزارش «Review of 9» و push. بعد پرامپت ۹.۱.
