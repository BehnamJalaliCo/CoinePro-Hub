# گزارش پرامپت ۳۰: کارگاه با دست، برای هر کار (deploy)

> Claude سرور هاب، ۲۰۲۶-۱۱-۰۹.
> - **شاخه:** `server/p30-deploy` = شاخه‌ی اصلی `5d334cf9` + یک commit خودم (`dae06968`).
> - **alembic:** `0058` (migration ندارد).

## خلاصه
- **deploy:** انجام شد.
  - api و worker (همان image) و gateway تازه‌اند.
  - OPA سیاست تازه را خودش خواند (`--watch`).
  - Caddy با فایل‌های تازه دوباره بالا آمد.
- **`verify-live`:** سبز است: rc=0، بی FAIL؛ فقط دو GAP همیشگی.
- **بکاپ پیش از deploy:** `20261109T170015Z`
- **یک commit خودم، `dae06968`:**
  - mypy (`--strict`) روی runner 0.3.2 سه خطای نوع داشت:
    - `outbox.py:110-111`: lambda در `with_retry`
    - `workspace.py:119`: نوع فهرست `sent`
  - با `functools.partial` و یک نوع صریح درست شد. رفتار عوض نشد و تست‌های runner سبزند.
- **دست‌نخورده:** هیچ داده‌ای پاک یا لغو نشد، هیچ کاربر، کلید یا قاعده‌ی iptables ساخته نشد، و هیچ رمزی چاپ نشد.

## ۱. تست‌ها
| بخش | نتیجه |
|---|---|
| api: `test_w14_workshop` و همه‌ی فایل‌های نام‌برده‌ی پرامپت، به‌علاوه‌ی `test_w11_decisions`، `test_w8_capabilities` و دو تست سند OpenAPI | **۲۲۵ از ۲۲۵ سبز** |
| services: کل مجموعه (gateway با `test_hands_tools`، hq-common و بقیه) | **۱۲۷۵ سبز** |
| company-runner: کل مجموعه (با `test_outbox`) | سبز (پیش و پس از اصلاح نوع) |
| `opa test infra/opa/policy` | **۳۰۲ از ۳۰۲** |
| lint، format و mypy (api و services) | سبز، بعد از commit خودم |

## ۲. deploy
| زمان (UTC) | کار | نتیجه |
|---|---|---|
| 17:00 | `make backup` | `20261109T170015Z` |
| 17:01 | checkout ‏`server/p30-deploy`؛ build ‏`api` و `gateway` | ساخته شد |
| 17:02 | `up -d --wait api worker gateway` | همه healthy |
| 17:03 | `caddy validate` روی فایل‌های تازه، با env خود Caddy زنده | `Valid configuration`، بعد restart ‏caddy |
| 17:03– | `make verify-live` | **rc=0**، بی FAIL؛ فقط دو GAP همیشگی |

**چرا restart و نه reload:** فایل‌های Caddy تک‌فایل mount شده‌اند. checkout فایل تازه میسازد و `caddy reload` نسخه‌ی قبلی را میدید. restart فقط چند ثانیه طول کشید.

## ۳. سنجش‌ها
| سنجش | نتیجه |
|---|---|
| `caddy adapt` | route ‏`runner_files` (`POST`، `^/api/v1/runners/jobs/[^/]+/files$`، `max_size` **201MB**) **پیش از** route ‏`/api/v1/runners/*` (`max_size` 32MB) است |
| `POST /api/v1/runners/jobs/<uuid ساختگی>/files` بی توکن | **401** |
| OPA زنده (`hq.internal`): مدیر رسانه‌ی PC، `server.run` با `via: workshop` روی HQ | **بله** |
| همان، `server.read` با `via: workshop` | خیر |
| همان، `server.run` بی via | خیر |
| `workshop.run` در ابزارهای gateway و در `SHARED_TOOLS` | بله، بله |
| `https://hq.coinepro.com/healthz` | **200** |

## ۴. دستورهای مالک (من هیچ‌کدام را نزده‌ام)
همان بخش ۴ گزارش `WORKSHOP_REVIEW.md` است، با دو نکته:
- **نسخه‌ی runner:** گام ۶ حالا **0.3.2** نصب میکند (`git archive` از شاخه‌ی اصلی).
- **ترتیب اجباری:** گام ۸ (دیوار شبکه) **پیش از** گام ۹ (جفت کردن و روشن کردن runner).

**۱. کاربر (بی sudo، بی docker، بی رمز، بی SSH):**
```bash
sudo adduser --disabled-password --gecos "HQ studio" studio
sudo chmod 750 /home/studio
id studio    # فقط گروه studio
echo "DenyUsers studio" | sudo tee /etc/ssh/sshd_config.d/60-studio.conf
sudo sshd -t && sudo systemctl reload ssh
```

**۲. بسته‌های سیستم:**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fontconfig python3.12-venv xz-utils
```

**۳. node ‏22.22.0 و Claude Code:**
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

**۴. python و Chromium (Playwright 1.63.0):**
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
sudo -iu studio fc-list | grep -c IRANYekanX    # ۶
```

**۶. hq-runner ‏0.3.2:**
```bash
git -C /home/Hub/CoinePro-Hub fetch -q origin
git -C /home/Hub/CoinePro-Hub archive origin/claude/coinepro-hub-setup-hsvnw7 services/company-runner \
  | sudo -u studio tar -x -C /home/studio
sudo -iu studio bash -c '
set -e; cd ~/services/company-runner
python3.12 -m venv ~/.local/share/hq-runner/venv
~/.local/share/hq-runner/venv/bin/pip install --require-hashes -r requirements.lock
~/.local/share/hq-runner/venv/bin/pip install --no-deps .
ln -sf ~/.local/share/hq-runner/venv/bin/hq-runner ~/.local/bin/hq-runner
hq-runner --version    # 0.3.2
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

**۸. دیوار شبکه (پیش از گام ۹):**
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
sudo -u studio curl -s -m 3 http://127.0.0.1:7233; echo "loopback rc=$? (باید غیر صفر باشد)"
sudo -u studio curl -s -o /dev/null -w '%{http_code}\n' https://hq.coinepro.com/healthz    # 200
```

**۹. جفت کردن و روشن کردن** (فقط بعد از گام ۸):
```bash
sudo -iu studio hq-runner pair --company HQ --name workshop --hub-ip 10.10.1.4
# کد کوتاه را در اپ تأیید کنید (🔏)، بعد:
sudo systemctl enable --now hq-runner@studio
sudo -iu studio hq-runner status    # online
```
بعد به من بگویید تا سرور کارگاه و دیوار را بسنجم (بخش ۵ پرامپت).

## ۵. اختیاری: runner سرورهای شرکت‌ها به 0.3.2
- **سرورها:** fx-main، Pro-Chart، ty-main و IG-Hub.
- **اثر:** کارهای `on_server` آن‌ها هم فایل‌های `out/` را برمیگردانند. 0.3.1 همچنان کار میکند.
- **دستور:** همان سه دستور ۲۹ است، با Claude هر سرور یا خود مالک:
  ```
  git -C ~/CoinePro-Hub pull
  pipx install --force --python python3.12 ~/CoinePro-Hub/services/company-runner
  sudo systemctl restart hq-runner@$USER
  ```

این گزارش را برای Claude سشن مشورت ببر.
