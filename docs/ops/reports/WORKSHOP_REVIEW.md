# بررسی طرح «کارگاه با دست» (فقط خواندنی)

> Claude سرور هاب، ۲۰۲۶-۱۱-۰۹. طرح: `docs/WORKSHOP_HANDS.md` (`6644e318`).
> - هیچ کاربری ساخته نشد، چیزی نصب یا روشن نشد و کدی نوشته نشد.
> - **ردپای F-0014:** طبق دستور مالک لغو است (جلسه پاک شده است).
> - **مرجع کد:** شماره‌ی خط‌ها از شاخه‌ی اصلی `6644e318` است.

## خلاصه
| پرسش | جواب کوتاه |
|---|---|
| ۱. حافظه | **جا میشود.** کمترین حافظه‌ی قابل استفاده در ۷ روز گذشته **۸۰۴۸ MB** بود (حتی هنگام `make check`) و میانه حدود ۱۰.۴ GB. یک کار کارگاه در اوج حدود ۲ تا ۳ GB میگیرد. با سقف cgroup ‏`MemoryMax=4G` امن است. |
| ۲. جفت کردن روی هاب | **دو مانع در کد و یکی در OPA.** هیچ‌کدام سرور هلدینگ را برای نقش شرکت‌های دیگر باز نمیکند: (۱) pairing فقط شرکت `kind = company` را میپذیرد؛ (۲) `_authorize` و `_reachable` شرکت مقصد را `company` میخواهند و منشور باید `server.claude` داشته باشد؛ (۳) `servers.rego` راهی برای «کارگاه» ندارد. |
| ۳. فایل تا ۲۰۰MB | **نزدیک‌ترین راه، ماشین آپلود مالک است** (`POST /files`، بدنه‌ی خام، سنجش نوع و اندازه هنگام دریافت، ویدیو تا ۲۰۰MB، و Caddy تا 201MB). به‌علاوه‌ی `players.deliver` که فایل‌ها را پیوست خروجی کار میکند. لازم است: یک route تازه برای runner با همین ماشین، یک قاعده‌ی Caddy (حالا runnerها سقف **32MB** دارند)، و runner 0.3.2. |
| ۴. دستورها | پایین، بخش ۴. **پیش از هر چیز، دیوار شبکه:** هر کاربر محلی به پورت‌های `127.0.0.1` هاب میرسد، از جمله Temporal ‏(7233) که **احراز هویت ندارد**. |

## ۱. حافظه و CPU
**الان** (`free -m`، 15:14 UTC):
- **کل:** ۱۵۶۰۸ MB
- **در حال استفاده:** ۵۴۲۴ MB
- **قابل استفاده:** **۱۰۱۸۳ MB**
- **swap:** ۸ GB، ۷۳۳ MB پر

**CPU:** ۸ هسته، بار حدود ۰.۷.

**کانتینرها** (`docker stats --no-stream`): جمعاً حدود **۳۹۸۶ MiB** مصرف واقعی. بزرگ‌ترها:

| کانتینر | مصرف / سقف |
|---|---|
| postgres | 882 MiB / 1 GiB (**۸۶٪ سقفش**) |
| temporal | 785 MiB / 1 GiB (۷۷٪) |
| n8n | 283 / 512 MiB |
| prometheus | 268 / 512 MiB |
| api | 241 / 384 MiB |
| browser-web | 214 MiB / 1.04 GiB |
| grafana | 207 / 576 MiB |
| بقیه | هر کدام زیر 160 MiB |

**تاریخچه** (`sar`، ۳ تا ۹ نوامبر، هر ۱۰ دقیقه):

| روز | کمترین قابل استفاده | p10 | میانه |
|---|---|---|---|
| 11-03 | 8688 | 10102 | 10543 |
| 11-04 | 8656 | 9627 | 10579 |
| 11-05 | 8402 | 9413 | 10354 |
| 11-06 | 8351 | 9642 | 10404 |
| 11-07 | **8048** | 8972 | 10271 |
| 11-08 | 8175 | 9915 | 10560 |
| 11-09 | 9393 | 9751 | 10353 |

پایین‌ترین‌ها همزمان با `make check` و محیط تست بوده‌اند.

**برآورد یک کار کارگاه:**
- **Claude Code ‏(`claude` CLI):** ۲۶۰ تا ۳۲۰ MiB. این عدد اندازه‌گیری شده است: دو پروسه‌ی `claude` همین الان روی هاب.
- **Chromium headless برای رندر فریم‌ها:** حدود ۰.۵ تا ۱.۵ GiB.
- **ffmpeg** ‏(libx264، 1080p): حدود ۰.۳ تا ۰.۸ GiB، و همه‌ی هسته‌ها را میگیرد.
- **جمع در اوج:** حدود **۲ تا ۳ GiB**.

**نکته‌ها:**
- **ظرفیت runner:** آن را **۲ کار همزمان** میگیرد (`MAX_JOBS = 2`، `services/company-runner/src/hq_runner/runner.py:56`، در config قابل تنظیم نیست). پس در بدترین حالت حدود ۵ تا ۶ GiB.
- **پیشنهاد:** سقف cgroup روی سرویس `hq-runner@studio`: ‏`MemoryMax=4G`، `MemoryHigh=3500M`، `CPUQuota=600%` و `Nice=10`. دستورش در بخش ۴ آمده است. با آن، کارگاه هرگز بیش از ۴ GB نمیگیرد، ۲ هسته برای سرویس‌ها میماند، و دو کار همزمان به‌جای OOM کل سرور کند میشوند.
- **بودجه‌ی حافظه:** بودجه‌ی ۸۶٪ ‏`hq.sh` فقط سقف کانتینرها را میشمارد (الان دقیقاً پر: 13422 از 13422 MiB). کارگاه خارج از compose است، پس آن را نمیبیند. سقف cgroup جای آن را میگیرد.

## ۲. جفت کردن runner روی خود هاب، به‌عنوان سرور هلدینگ

**مانع ۱، pairing:**
- `routes/servers.py:278` (`runner_pair`) این را دارد:
  ```python
  if co is None or co.kind != "company": raise ApiError(422, … "unknown company")
  ```
- HQ از نوع `holding` است، پس `hq-runner pair --company HQ` با ۴۲۲ رد میشود.
- **تغییر لازم:** شرکت هلدینگ پذیرفته شود، ترجیحاً فقط با یک نشان کارگاه (مثلاً `role: workshop` روی `infra.servers`)، تا هر سرور دیگری هلدینگی نشود.

**از نظر شبکه مانعی نیست:**
- runner زیر کاربر جدا از همین هاب به `https://hq.coinepro.com` (91.107.169.208) یا `--hub-ip 10.10.1.4` وصل میشود. هر دو به Caddy روی ۴۴۳ میرسند.
- دیوار شبکه‌ی بخش ۴ همین دو را باز میگذارد.

**مانع ۲، اجازه در api** (`routes/servers.py`، `_authorize` حدود خط 1078 تا 1100). کار روی سرور شرکت دیگر فقط از این راه‌ها مجاز است:
- سرور خود شرکت ایجنت؛
- `_holding_power` (SRE پلتفرم و ناظر)؛
- نقش فنی (`_technical`: دپارتمان TECH، `scope: company`) و `_reachable`؛ اما `_reachable` (حدود خط 1025) شرکت مقصد را `kind == "company"` میخواهد، پس سرور هلدینگ هرگز در دسترس نیست؛
- درخواست بین‌شرکتی که CEO همان شرکت پذیرفته (`via_work`).

جلوتر از همه‌ی این‌ها، منشور ایجنت باید `server.claude` داشته باشد:
```python
if f"server.{kind}" not in lib.allowed(who.charter): raise 403
```
فقط **۷ منشور از ۳۴** آن را دارند (`agents/roles/*.md`).

**مانع ۳، OPA** (`infra/opa/policy/servers.rego`، سرور مقصد):
- `grant` فقط در این حالت‌ها هست:
  - `same_company`
  - `holding_reader` با منشور `hub_platform_sre` یا `overseer`
  - `via == "accepted_request"`
  - `via == "linked"`
- راهی برای «هر نقش، روی کارگاه هلدینگ» نیست.
- `data.json` ‏`a2_grants` برای ceo، manager، employee و overseer همین الان `server.claude` و `server.run` را دارد، پس طبقه‌ی اقدام مانع نیست.

**پیشنهاد کوچک‌ترین تغییر** (برای Claude سشن مشورت):
1. **ابزار تازه:** ابزار مشترک `workshop.run` در `SHARED_TOOLS` ‏(`services/hq-common/src/hq_common/charters.py:59`)، تا همه‌ی نقش‌ها داشته باشند بی دست زدن به ۳۴ منشور.
   - gateway آن را به `server.claude` روی سرور «کارگاه» هلدینگ ترجمه میکند.
2. **مسیر تازه در `_authorize`:** وقتی سرور کارگاه هلدینگ است و نوع کار `claude`، حاصل `via = "workshop"` باشد، برای هر ایجنت.
   - exec و write روی کارگاه بسته بمانند.
3. **قاعده‌ی تازه در `servers.rego`:**
   ```rego
   grant if { op == "server.run"; agent; tv("via") == "workshop" }
   ```
   - با تستش در `servers_test.rego`.
   - api مطمئن میشود فقط `claude` باشد.
4. **pairing:** پذیرش هلدینگ (مانع ۱).
5. **آرگومان‌های کار کارگاه** در `workshop/server_sessions.py`:
   - `model: claude-opus-5-5`
   - `permission_mode` (مثلاً `acceptEdits`) و `allowed_tools` گسترده (Bash، Write، Edit، WebFetch)، چون نشست غیرتعاملی وگرنه Bash را رد میکند. hook دستورهای ویرانگر سر جایش است.
   - `workspace: <W-ref>` (پوشه‌ی کار)
   - بی `token_cap`
   - `TURN_TIMEOUT_S = 3600` همین الان ۶۰ دقیقه است.
   - **`effort: high`:** runner پرچمی برای آن ندارد (`claude_job.py` فقط `--model`، `--permission-mode`، `--max-turns` و `--allowedTools` را میسازد). یا با settings اضافه شود، یا پیش‌فرض بماند.
6. **اکانت:** هیچ تغییری لازم نیست. از ۲۹.۱، `runner_claude_account` توکن اکانتی را که هاب رویش است با کار میفرستد.

## ۳. نزدیک‌ترین راه برای فایل تا ۲۰۰MB، از runner به جلسه

**آنچه هست:**

| تکه | کجا | چه میکند |
|---|---|---|
| آپلود مالک | `routes/files.py:269` ‏`POST /files` | بدنه‌ی خام، `X-File-Name`. نوع از بایت‌های اول (`Upload.receive`) و اندازه هنگام دریافت سنجیده میشود. ویدیو mp4، webm و mov تا **۲۰۰MB** و **۱۰ دقیقه**؛ تصویر ۲۰MB؛ PDF ‏۳۰MB؛ متن و ZIP ‏۵۰MB. ویدیو بعد از ذخیره در workflow پردازش میشود (پوستر، فریم‌های کلیدی). **فقط مالک** (`owner_ctx`). `store_upload` (خط 176) شرکت را هلدینگ و سازنده را `owner` میگذارد. |
| Caddy | `infra/caddy/api-on.caddy` | `/api/v1/files*`: ‏`max_size 201MB`، read و write ‏600s. **`/api/v1/runners/*`: ‏`max_size 32MB`.** |
| نتیجه‌ی runner | `POST /runners/jobs/{id}/result` | JSON. خروجی بلند به‌شکل `output_overflow` (gzip تا ۶۴MB متن). برای فایل دودویی ۲۰۰MB مناسب نیست. |
| خروجی جلسه | `domain/players.py:346` ‏`deliver()` | ردیف `cartable.deliverables` با `attachments uuid[]`. اپ خروجی‌های فرمان را با «باز کن» و «دانلود» نشان میدهد (`GET /files/{id}` با Range). |
| قلاب کارگاه | `domain/workspace.py` ‏`after_job` (حدود خط 267، از `runner_result`) | همین الان جواب کار `claude` با `workspace` را خروجی کار میکند (`PL.deliver`). این جای طبیعی چسباندن فایل‌های `out/` است. |

**کوتاه‌ترین مسیر:**
1. **route تازه:** `POST /api/v1/runners/jobs/{id}/files`، با احراز runner و همان job.
   - بدنه‌ی خام با همان `Upload.receive` و `prepare_upload`، فقط نوع‌های ویدیو، تصویر، PDF و سند.
   - شرکت فایل = شرکت کار. سازنده = `agent` یا runner.
   - Audit با `file.upload`.
2. **Caddy:** یک matcher جدا پیش از `@runners`، مثل `path_regexp ^/api/v1/runners/jobs/[^/]+/files$`، با `max_size 201MB` و timeoutهای 600s، مثل `@media`.
3. **runner 0.3.2:** بعد از کار `claude`ی که `workspace` دارد، فایل‌های `~/hq-workspace/<W>/out/` را یکی‌یکی میفرستد و شناسه‌ها را در `data.files` نتیجه میگذارد.
4. **`workspace.after_job`:** این شناسه‌ها را به `PL.deliver(..., attachments=…)` میدهد (پارامتری که امروز نیست). خروجی با پیوست‌هایش در جلسه دیده میشود.

**حد:** ویدیو بیش از ۱۰ دقیقه رد میشود. این حد همان است که برای آپلود مالک هست.

## ۴. دستورها (فقط برای مالک؛ من هیچ‌کدام را نزده‌ام)

**پیش از هر چیز، چرا دیوار شبکه لازم است:** این پورت‌ها روی `127.0.0.1` باز هستند و هر کاربر محلی، از جمله `studio`، به آن‌ها میرسد:

| پورت | سرویس | احراز هویت |
|---|---|---|
| 7233 | Temporal | **ندارد**. کسی که به آن برسد workflowها را میبیند و میتواند متوقف کند. |
| 8233 | Temporal UI | — |
| 5432 | Postgres | رمز میخواهد |
| 8200 | OpenBao | توکن میخواهد |
| 6379 | Valkey | رمز میخواهد |
| 4222 و 8222 | NATS | — |
| 9090 | Prometheus | — |
| 3100 | Loki | لاگ‌ها |
| 3000 | Grafana | — |
| 5678 | n8n | — |

پس دیوار (قدم ۸) پیش از روشن کردن runner لازم است.

**وضع فعلی دیگر:**
- `/home/Hub` ‏`750` و `.secrets` ‏`700` هستند و `/tmp/claude-1000` ‏`700`. کاربر تازه آن‌ها را نمیخواند.
- ufw خاموش است و زنجیره‌ی OUTPUT خالی است.
- ffmpeg، fontconfig، python3.12-venv و pipx نصب نیستند.
- python3.12 هست.

**۱. کاربر (بی sudo، بی docker، بی رمز، بی SSH):**
```bash
sudo adduser --disabled-password --gecos "HQ studio" studio
sudo chmod 750 /home/studio
id studio    # فقط گروه studio
echo "DenyUsers studio" | sudo tee /etc/ssh/sshd_config.d/60-studio.conf
sudo sshd -t && sudo systemctl reload ssh
```
`sshd` این سرور `PasswordAuthentication yes` دارد. کاربر بی‌رمز با آن وارد نمیشود، ولی `DenyUsers` آن را قطعی میکند.

**۲. بسته‌های سیستم:**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fontconfig python3.12-venv xz-utils
```

**۳. node ‏22.22.0 (همان نسخه‌ی ریپو) و Claude Code، در خانه‌ی خود کاربر:**
```bash
sudo -iu studio bash -c '
set -e; export PATH=$HOME/.local/bin:$PATH; V=v22.22.0; cd /tmp
curl -fsSLO https://nodejs.org/dist/$V/node-$V-linux-x64.tar.xz
curl -fsSL https://nodejs.org/dist/$V/SHASUMS256.txt | grep " node-$V-linux-x64.tar.xz$" | sha256sum -c -
mkdir -p ~/.local/node ~/.local/bin
tar -xJf node-$V-linux-x64.tar.xz -C ~/.local/node --strip-components=1 && rm node-$V-linux-x64.tar.xz
for b in node npm npx; do ln -sf ~/.local/node/bin/$b ~/.local/bin/$b; done
npm config set prefix ~/.local
npm install -g @anthropic-ai/claude-code
claude --version
'
```
لاگین Claude لازم نیست. runner 0.3.1 توکن اکانت هاب را با هر کار فقط به همان پروسه میدهد.

**۴. python و Chromium (Playwright 1.63.0، همان نسخه‌ی ریپو):**
```bash
sudo -iu studio bash -c '
set -e; python3.12 -m venv ~/.local/share/studio-py
~/.local/share/studio-py/bin/pip install playwright==1.63.0
~/.local/share/studio-py/bin/python -m playwright install chromium
'
sudo /home/studio/.local/share/studio-py/bin/python -m playwright install-deps chromium
```

**۵. فونت IRANYekanX:**
```bash
sudo install -d -o studio -g studio -m 755 /home/studio/.local/share/fonts
sudo install -o studio -g studio -m 644 /home/Hub/CoinePro-Hub/design/fonts/static/IRANYekanX-*.ttf /home/studio/.local/share/fonts/
sudo -iu studio fc-cache -f
sudo -iu studio fc-list | grep -c IRANYekanX    # باید ۶ باشد
```

**۶. hq-runner ‏0.3.1:** کد از ریپوی هاب کپی میشود، چون studio به `/home/Hub` دسترسی ندارد.
```bash
git -C /home/Hub/CoinePro-Hub archive origin/claude/coinepro-hub-setup-hsvnw7 services/company-runner \
  | sudo -u studio tar -x -C /home/studio
sudo -iu studio bash -c '
set -e; cd ~/services/company-runner
python3.12 -m venv ~/.local/share/hq-runner/venv
~/.local/share/hq-runner/venv/bin/pip install --require-hashes -r requirements.lock
~/.local/share/hq-runner/venv/bin/pip install --no-deps .
ln -sf ~/.local/share/hq-runner/venv/bin/hq-runner ~/.local/bin/hq-runner
hq-runner --version    # 0.3.1
'
```

**۷. سرویس و سقف منابع** (هنوز روشن نکنید):
```bash
sudo cp /home/Hub/CoinePro-Hub/services/company-runner/systemd/hq-runner@.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/hq-runner@studio.service.d
printf '[Service]\nMemoryMax=4G\nMemoryHigh=3500M\nCPUQuota=600%%\nNice=10\nTasksMax=512\nNoNewPrivileges=yes\n' \
  | sudo tee /etc/systemd/system/hq-runner@studio.service.d/limits.conf
sudo systemctl daemon-reload
```

**۸. دیوار شبکه:** studio فقط به اینترنت، DNS و HTTPS خود هاب میرسد.
```bash
sudo tee /usr/local/sbin/studio-firewall.sh >/dev/null <<'EOF'
#!/bin/sh
set -e
U=$(id -u studio)
iptables -N STUDIO_OUT 2>/dev/null || iptables -F STUDIO_OUT
iptables -A STUDIO_OUT -d 127.0.0.53 -p udp --dport 53 -j RETURN
iptables -A STUDIO_OUT -d 127.0.0.53 -p tcp --dport 53 -j RETURN
iptables -A STUDIO_OUT -d 10.10.1.4 -p tcp --dport 443 -j RETURN
for n in 127.0.0.0/8 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10; do
  iptables -A STUDIO_OUT -d "$n" -j REJECT
done
iptables -C OUTPUT -m owner --uid-owner "$U" -j STUDIO_OUT 2>/dev/null || iptables -I OUTPUT -m owner --uid-owner "$U" -j STUDIO_OUT
ip6tables -N STUDIO_OUT6 2>/dev/null || ip6tables -F STUDIO_OUT6
for n in ::1/128 fc00::/7 fe80::/10; do ip6tables -A STUDIO_OUT6 -d "$n" -j REJECT; done
ip6tables -C OUTPUT -m owner --uid-owner "$U" -j STUDIO_OUT6 2>/dev/null || ip6tables -I OUTPUT -m owner --uid-owner "$U" -j STUDIO_OUT6
EOF
sudo chmod 755 /usr/local/sbin/studio-firewall.sh
sudo /usr/local/sbin/studio-firewall.sh
printf '[Unit]\nDescription=studio user outbound fence\nAfter=network-pre.target\nBefore=hq-runner@studio.service\n\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/studio-firewall.sh\nRemainAfterExit=yes\n\n[Install]\nWantedBy=multi-user.target\n' \
  | sudo tee /etc/systemd/system/studio-firewall.service
sudo systemctl daemon-reload && sudo systemctl enable studio-firewall.service
# سنجش:
sudo -u studio curl -s -m 3 http://127.0.0.1:7233; echo "loopback rc=$? (باید غیر صفر باشد)"
sudo -u studio curl -s -o /dev/null -w '%{http_code}\n' https://hq.coinepro.com/healthz    # باید 200 باشد
```
**اثر روی بقیه:** این دیوار فقط بسته‌های کاربر studio را میگیرد (`--uid-owner`). داکر، کاربر Hub و قانون DOCKER-USER مالک دست نمیخورند.

**۹. جفت کردن و روشن کردن** (فقط بعد از تغییر کد بخش ۲؛ امروز ۴۲۲ میدهد):
```bash
sudo -iu studio hq-runner pair --company HQ --name workshop --hub-ip 10.10.1.4
# کد را در اپ تأیید کنید (🔏)، بعد:
sudo systemctl enable --now hq-runner@studio
sudo -iu studio hq-runner status    # online
```

این گزارش را برای Claude سشن مشورت ببر.
