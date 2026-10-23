# پرامپت ۱۴.۱: اصلاح ورود بازیکن‌های ذخیره (ChatGPT، Gemini و DeepSeek)

> Claude سشن مشورت، ۲۰۲۶-۱۰-۲۳. مالک پشت کامپیوتر منتظر است؛ این‌ها را بی‌توقف و به همین ترتیب انجام بده.
> - **شاخه:** `server/p14-1-fixes` از سر `server/p14-archive`.
> - **قرارداد:** §۲۱.۱۳، با بند تازه‌ی ⟨1.7.2⟩.
> - **گزارش:** `docs/ops/reports/PROMPT_14_1.md`.
> - کلید توقف هلدینگ روشن میماند. `HQ_SUBSTITUTES` و `HQ_SUBSTITUTES_WEB` هم خاموش میمانند تا مالک خودش روشنشان کند.

## آنچه مالک دید (۲۰۲۶-۱۰-۲۳)

1. **ایمیج پنجره‌ی ورود ساخته نمیشود.**
   - `make chatgpt-web-login`، `gemini-web-login` و `deepseek-web-login` روی ماشینی که ایمیج را ندارد میافتند: `pull access denied for coinepro-hq/browser-login`.
   - علت: `web-login.sh` اول `up -d web-login-relay` را میزند و `web-login-relay` بخش `build:` ندارد.
2. **تنظیمات سیستمی Gemini خوانده نمیشود.** Gemini CLI این را نوشت: `Skipping system settings file '/etc/gemini-cli/settings.json' ... (mode: 100664)`.
   - یعنی `enforcedType`، `tools.exclude` و خاموشی MCP و extension اعمال نمیشد.
   - علت: umask گروه‌نویس روی checkout سرور، و `COPY` همان مود را به ایمیج برد.
   - مالک دستی `chmod 644` زد و ایمیج را دوباره ساخت؛ حالا خوانده میشود.
3. **Gemini CLI برای حساب شخصی تعطیل شده.** گوگل به «Sign in with Google» این را جواب داد:
   `This client is no longer supported for Gemini Code Assist for individuals ... migrate to the Antigravity suite`
4. **تب ChatGPT در پنجره‌ی ورود کرش میکند.** روی صفحه‌ی Cloudflare میافتد: «Aw, Snap!»، `SIGSEGV`.
5. **گوگل ورود را رد میکند.** در پنجره‌ی ورود اجازه‌ی ورود به حساب گوگل نمیدهد («This browser or app may not be secure»).
   - علت: کرومیوم با Playwright، CDP و `--enable-automation` باز شده و `navigator.webdriver=true` است.
6. **میزبان‌های صفحه‌ی ورود گوگل در فهرست نیستند.** صفحه‌ی ورود گوگل در `chatgpt-web` و `deepseek-web` به `www.gstatic.com`، `ssl.gstatic.com` و `fonts.gstatic.com` نیاز دارد که در `login_hosts` نیستند.

**وضعیت فعلی:**
- Codex CLI وصل است (`/auth/codex/auth.json` هست).
- اتصال API تازه‌ی `gemini-api` (provider `google`) را مالک ساخته و کلیدش را با `make connection-secret` داده.

## §۱. پنجره‌ی ورود (اول این؛ مانع اصلی)

1. **بدون اتوماسیون:**
   - در `services/egress/web-login.sh` به‌جای ورود با Playwright (`browser_web.login`)، **خود باینری کرومیوم همان ایمیج** را مستقیم اجرا کن، با این‌ها:
     - `--user-data-dir=/profiles/<account>`
     - `--proxy-server=http://egress:3133`
     - `--no-first-run`، `--disable-dev-shm-usage`
     - آدرس `LOGIN_PAGES[account]`
   - همان sandbox و seccomp، و همان مهلت حداکثر ۹۰۰ ثانیه. پروسه با بستن پنجره یا پایان مهلت تمام میشود.
   - **ممنوع:** CDP، `--remote-debugging-*` و `--enable-automation`.
   - تست: در پنجره‌ی ورود `navigator.webdriver` باید `false` باشد و هیچ پورت devtools باز نباشد.
2. **کرش SIGSEGV:**
   - روی خود سرور، بی‌هیچ ورودی، `https://chatgpt.com/` و `https://chat.deepseek.com/` را با همان ایمیج باز کن و علت را از لاگ کرومیوم و `dmesg` پیدا کن.
   - مظنون‌ها: `--js-flags=--max-old-space-size=192` در `browser.py` (برای اپ سنگین ChatGPT کم است)، seccomp روی JIT یا WebAssembly چالش Cloudflare، و `/tmp` 256m.
   - اصلاح کمینه را بزن، در بودجه‌ی حافظه. مثلاً `BROWSER_JS_HEAP_MB` بزرگ‌تر فقط برای `browser-web-login` و `browser-web`؛ ابزار خواندن وب همان ۱۹۲ بماند.
   - تست: صفحه‌ی اول هر سه سایت بدون کرش بالا بیاید.
3. **ساخت ایمیج:** `web-login.sh` پیش از `up`، اگر ایمیج نیست، `"$HQ" --profile web-login build browser-web-login` را بزند. یا `web-login-relay` هم `build:` با همان context بگیرد.
4. **میزبان‌های گوگل:** `gstatic.com` را به `login_hosts` در `chatgpt-web.yaml` و `deepseek-web.yaml` اضافه کن.
   - `policies.google.com` و `support.google.com` لازم نیستند.
   - تست bench: میزبان‌های لازم ورود گوگل در هر سه دستور باشند.
5. **jobها:** برای jobهای پروفایل (`launch_persistent_context`)، `ignore_default_args=["--enable-automation"]` و `--disable-blink-features=AutomationControlled` را اضافه کن، اگر با recipeها جور است. کوکی‌های ورود مالک باید با همان پوشه‌ی پروفایل خوانده شوند.

## §۲. Gemini CLI

1. **مود فایل‌ها:** در `services/substitutes/Dockerfile`: `COPY --chmod=0644 substitutes/etc/gemini-cli/ /etc/gemini-cli/` (شامل `review.json`).
   - بقیه‌ی Dockerfileها را هم برای فایل‌های تنظیم و policy همین‌طور ببین.
   - gate: ایمیج ساخته‌شده هرگز «Skipping system settings» چاپ نکند.
2. **قرارداد ⟨1.7.2⟩:**
   - همه‌ی جایگاه‌های Gemini پیش‌فرض `via: "web"` شوند. در seed و یک migration، جایگاه‌هایی را هم عوض کن که مالک دستی تغییرشان نداده.
   - runner بازیکن Gemini CLI را `unavailable` با همین دلیل گزارش کند و هرگز کلید API نخواهد.
   - `make gemini-login` فقط این را چاپ کند: «Gemini CLI for individuals is discontinued by Google; Gemini runs through make gemini-web-login».
3. `code_review` با GPT (Codex) میماند.

## §۳. پایان

1. `make check` کامل.
2. deploy: backup ← migration ← `verify-live`.
   - برای egress فقط `make up` همان سرویس.
   - ایمیج‌های `browser-login`، `browser-web` و `substitutes` را دوباره build کن.
3. به مالک، **در همین نشست**، کوتاه و فارسی بگو که آماده است و ترتیب کار با خودش این است:
   1. `make gemini-web-login`
   2. `make chatgpt-web-login`
   3. `make deepseek-web-login`
   4. بعد `HQ_SUBSTITUTES=on` و `HQ_SUBSTITUTES_WEB=on`، `make up` و `make install-systemd`
4. قوانین همیشگی سر جایش است:
   - رمز و کوکی چاپ نشود.
   - به SSH، فایروال، کاربرها و کلیدها دست نزن.
   - ورود به حساب‌ها فقط با خود مالک.
