# گزارش پرامپت ۱۴.۱: ورود بازیکن‌های ذخیره (ChatGPT، Gemini، DeepSeek)

شاخه‌ی `server/p14-1-fixes` از سر `server/p14-archive`؛ قرارداد §21.13 با ⟨1.7.2⟩. کلید توقف هلدینگ روشن ماند؛ `HQ_SUBSTITUTES` و `HQ_SUBSTITUTES_WEB` خاموش‌اند.

## §1 پنجره‌ی ورود

- **§1.1 ok:** `services/egress/web-login.sh` خود باینری کرومیوم ایمیج را مستقیم اجرا میکند (`/ms-playwright/chromium-*/chrome-linux*/chrome`):
  - فلگ‌ها: `--user-data-dir=/profiles/<account>`، `--proxy-server=http://egress:3133`، `--no-first-run`، `--disable-dev-shm-usage`، و آدرس صفحه‌ی ورود همان حساب.
  - بدون Playwright، CDP، `--remote-debugging-*` و `--enable-automation`.
  - همان sandbox کرومیوم زیر seccomp کانتینر، و همان سقف ۹۰۰ ثانیه.
  - روی سرور: `navigator.webdriver` با فلگ‌های پنجره `false` است و با `--enable-automation` (مسیر قبلی Playwright) `true`. همین بود که گوگل را به «This browser or app may not be secure» میرساند.
  - تست: `test_the_window_runs_chromium_itself_without_automation` (فلگ ممنوع، پروکسی، پروفایل).
- **§1.2 ok (کرش):** هر سه سایت (chatgpt.com، chat.deepseek.com، gemini.google.com) با فلگ‌های تازه، headful روی Xvfb و از همان پروکسی ورود egress، هر کدام ۶۰ ثانیه باز ماندند.
  - هیچ خط کرش یا `Received signal 11` و هیچ خطای شبکه دیده نشد.
  - کرش با کرومیوم مستقیم، چه headless و چه headful، چه با heap ۱۹۲ و چه پیش‌فرض، روی سرور بازتولید نشد. پس علت، ترکیب راه‌اندازی Playwright (اتوماسیون و CDP) با heap ۱۹۲ مگ روی چالش سنگین Cloudflare بود؛ هر دو از مسیر پنجره حذف شدند.
  - heap پنجره‌ی ورود ۵۱۲ مگ است (`BROWSER_LOGIN_JS_HEAP_MB`؛ سقف حافظه ۱۰۲۴m). heap مرورگر پروفایل ۳۸۴ مگ است (`BROWSER_WEB_JS_HEAP_MB`؛ سقف ۷۶۸m). ابزار خواندن وب همان ۱۹۲ ماند.
- **§1.3 ok:** `make <x>-web-login` پیش از `up`، `--profile web-login build browser-web-login` میزند. ایمیج پنجره و relay هر دو همان است و دیگر هیچ pullی لازم نیست.
- **§1.4 ok:** `gstatic.com` به `login_hosts` در `chatgpt-web.yaml` و `deepseek-web.yaml` اضافه شد. تست: `test_google_sign_in_hosts_are_in_every_recipe` (accounts.google.com، www، ssl و fonts.gstatic.com در هر سه).
- **§1.5 ok:** jobهای پروفایل `ignore_default_args=["--enable-automation"]` و `--disable-blink-features=AutomationControlled` دارند؛ پوشه‌ی پروفایل همان است، پس کوکی‌های ورود مالک خوانده میشوند. تست: `test_profile_jobs_hide_the_automation_flag` (در `browser-test.sh`، با کرومیوم واقعی).

## §2 Gemini

- **§2.1 ok:** در `services/substitutes/Dockerfile` فایل‌های `settings.json` و `review.json` با `COPY --chmod=0644` کپی میشوند. پوشه پیش از آن با `install -d -m 0755` ساخته میشود، چون `--chmod` پوشه‌ای را که خودش بسازد هم 0644 میکرد و قابل ورود نبود.
  - gate: build ایمیج شکست میخورد اگر Gemini با هر کدام از دو فایل «Skipping system settings» چاپ کند. آزموده شد: با فایل 664 هشدار چاپ میشود و با فایل ایمیج نه.
  - علت ریشه: umask گروه‌نویس (0002) روی checkout سرور؛ فایل‌ها در گیت 664 بیرون میآیند.
  - lock fileهای tts، media-render، stt و ocr هم `--chmod=0644` گرفتند.
- **§2.2 ok (⟨1.7.2⟩):**
  - همه‌ی جایگاه‌های Gemini در seed `via: "web"` شدند و توان متنی بازیکن هم `web`.
  - migration `0029_1` (روی `0029`؛ هیچ CHECK نوعی را لمس نمیکند) جایگاه‌های `cli` بازیکن Gemini را به `web` میبرد، فقط وقتی مالک دستی تغییرشان نداده باشد. معیار: هیچ ردیف Audit با `substitute.seats` و هدف `gemini` نباشد، یعنی ردیفی که ویرایش جایگاه‌ها از اپ مینویسد. برای هر جایگاه منتقل‌شده یک ردیف Audit ثبت میشود.
  - runner بازیکن Gemini CLI را با `unavailable` و همین دلیل گزارش میکند. هیچ CLIای اجرا نمیشود و هیچ کلید API خواسته نمیشود. api این را میپذیرد و دلیل را روی بازیکن مینشاند.
  - `make gemini-login` فقط پیام را چاپ میکند. اپ برای Gemini به `make gemini-web-login` اشاره میکند.
  - تست‌ها: `test_the_gemini_cli_player_is_unavailable_and_never_asks_for_a_key`، `test_p141_gemini_web.py` (seed، پذیرش `unavailable`، و migration با و بدون ویرایش مالک).
- **§2.3 ok:** `code_review` با GPT (Codex CLI) میماند. جایگاه `code_review` بازیکن Gemini خاموش است (تست).

## Contract notes
- خطای تازه‌ی runner: `unavailable` (⟨1.7.2⟩)؛ بازیکن `status: off` با `status_reason` همان پیام.
- مسیرهای CLI بازیکن Gemini در کد ماندند و تست میشوند (`HQ_GEMINI_CLI_GONE=0` فقط در تست)، برای اتصال API پولی §21.9.
