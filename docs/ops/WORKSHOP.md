# کارگاه کد (Code Workshop) — راهنمای عملیات

قرارداد: `contracts/HQ_CORE_API_v1.md` §17.3، §17.4 و §17.7. پرامپت: `PROMPT_06` §4 و §5.

## وضعیت فعلی
- کنترل‌پلن کامل در هاب ساخته شده است: workspace، grant، session، event، approval، قفل کاری، بودجه و transcript.
- **محل اجرا هنوز انتخاب نشده است.** `WORKSHOP_RUNTIME` خالی است، `GET /meta` مقدار `workshop.runtime = null` برمیگرداند و `POST /workshop/sessions` جواب `503 runtime_not_configured` میدهد.
- workspaceها، grantها و تاریخچه بدون runtime هم کار میکنند.

## آنچه منتظر مالک است
1. **انتخاب محل اجرا** (`managed` یا `self_hosted`).
   - `managed` یعنی یک API key جدا با سقف ماهانه.
   - مالک این‌ها را خودش میسازد: agent (با ابزار bash و سیاست `always_ask`) و environment در Claude Managed Agents.
   - **همه‌ی ابزارهای فعال agent باید `always_ask` باشند** (پیش‌فرض agent toolset `always_allow` است؛ `auto` هم پذیرفته نیست؛ ابزار custom نباشد). هاب این را موقع ساختن runtime و پیش از شروع هر سشن با `GET /v1/agents/{id}` میخواند؛ اگر یک ابزار بی‌پرسش اجرا شود، runtime خاموش میماند یا سشن متوقف میشود (بازبینی ۶.۱ §۲).
   - مالک خودش در OpenBao میگذارد: `kv/hq-api/workshop/managed` با کلیدهای `api_key`، `agent_id` و `environment_id`. هیچ‌کس مقدارشان را نمیبیند.
2. **توکن GitHub هر workspace:** fine-grained، فقط برای همان یک ریپو، با دسترسی contents و pull requests، در `kv/hq-api/workshop/github/<WORKSPACE-CODE>` با کلید `token`.
3. سپس `WORKSHOP_RUNTIME=managed` در env سرویس api و ری‌استارت api. ری‌استارت هم با اجازه‌ی مالک است.

## adapterها (`apps/api/src/hq_api/workshop/runtime.py`)

| نام | وضعیت | خلاصه |
|---|---|---|
| `fake` | برای تست و CI | رویدادهای ساختگی، approval پیش از push، push ساختگی به `hq/<ref>`، آدرس PR ساختگی. در production انتخاب‌شدنی نیست. |
| `managed` | ساخته شده، روشن نیست | Claude Managed Agents با REST و هدر بتای `managed-agents-2026-04-01`. |
| `self_hosted` | فقط طراحی | پایین همین سند. |

**جزئیات `managed`:**
- ریپو به‌صورت منبع `github_repository` به سشن وصل میشود.
- توکن GitHub هنگام ساخت سشن یک بار از OpenBao خوانده میشود و به git proxy خود Anthropic میرسد. proxy آن را هنگام خروج جایگزین میکند. **توکن هیچ‌وقت داخل sandbox، مدل، رویداد، لاگ یا دیتابیس نیست.** تست خودکار این را اسکن میکند.
- سقف بودجه دو بار اعمال میشود: یک بار در خود سکو (`max_list_cost`) و یک بار در هاب.
- هر ابزار با `always_ask` میپرسد و هاب اول actionهای grant را اعمال میکند (`commands.needs`): grant فقط‌خواندنی هیچ ویرایش، اجرا، push یا PR نمیکند، و قفل کار هم نمیگیرد. بعد برای bash سه جور جواب میدهد (`workshop/commands.py`):
  - **خودکار اجازه میدهد:** خواندن، ویرایش، تست، lint، و commit روی شاخه‌ی خود سشن.
  - **رد میکند:** SSH، docker، cloud، دیتابیس، فایل‌های اعتبار و env، force push، push به هر شاخه‌ای جز `hq/<ref>`، و merge/release.
  - **از مالک میپرسد** (`approval_request`): push شاخه، باز کردن PR، و هر دستور بیرون از فهرست.
- هر «ask» دیگر (web_fetch، web_search، MCP، ابزار ناشناخته) هم `approval_request` میشود تا سشن بی‌پایان منتظر نماند.
- رویدادهای سشن هر ۵ ثانیه با poll خوانده میشوند (حلقه‌ی پس‌زمینه‌ی api).
- اگر cursor سکو گم شود، رویدادها دوباره خوانده میشوند، ولی approval یا تأیید تکراری ساخته نمیشود و توکن دو بار شمرده نمیشود.
- سشنِ در صف موقع کلید توقف یا توقف deploy شروع نمیشود (بعد از برداشتن قفل خودش شروع میشود) و بعد از انقضای grant با `grant_expired` متوقف میشود.

## قوانین ۱ تا ۷ در کد

| قانون | کجا اجرا میشود |
|---|---|
| ۱ | فقط شاخه‌ی `hq/<ref>` push میشود و PR باز میشود. merge و deploy با مُهر مالک میماند (`policy` ثابت `owner_seal`). |
| ۲ | اعتبار GitHub فقط در سمت managed است. |
| ۳ | هر سشن sandbox جدا و کلون تازه دارد (سمت runtime). |
| ۴ | سقف دلاری grant: با رسیدن به سقف، سشن `stopped` میشود، `held=budget` میگیرد و یک اعلان 🟡 برای مالک میرود. |
| ۵ | کلید توقف یا توقف deploy سشن‌های شرکت را `held=company_locked` میکند و سشن تازه `423` میگیرد. پس از برداشتن قفل، پیام بعدی مالک سشن را ادامه میدهد. |
| ۶ | یک سشن نوشتنی در هر بخش ریپو (`area`، پیشوند مسیر؛ خالی یعنی همه). بقیه با `held=work_lock` در صف میمانند و خودکار شروع میشوند. |
| ۷ | رویدادها فقط خلاصه و فراداده‌ی ماسک‌شده دارند. transcript کامل و ماسک‌شده در انبار فایل است: `GET /workshop/sessions/{ref}/transcript`. |

## طراحی `self_hosted` (ساخته نمیشود)
- **هاست:** یک هاست سازنده‌ی جدا (نه همین سرور).
  - هیچ مسیری به شبکه‌ی خصوصی هتزنر، هاب، یا production ندارد.
  - خروجی فقط به GitHub و رجیستری‌های بسته (allow-list در فایروال هتزنر).
- **کانتینر:** برای هر سشن یک کانتینر یک‌بارمصرف با این مشخصات:
  - Claude Agent SDK
  - کاربر غیر root، rootfs فقط‌خواندنی به‌جز `/workspace`
  - `cap_drop: ALL`، سقف CPU، حافظه و زمان
  - کلون تازه از شاخه‌ی پیش‌فرض
- **اعتبار:** توکن GitHub داخل کانتینر نیست.
  - یک git credential helper روی میزبان، از یک socket فقط‌نوشتنیِ push، فقط `hq/<ref>` را میپذیرد.
  - برای PR، کانتینر از هاب درخواست میدهد و هاب خودش PR را باز میکند.
- **پیوند با هاب:** یک worker کوچک روی هاست سازنده.
  - همان interface `Runtime` (start، send، answer، stop، poll، transcript) را با mTLS به api هاب عرضه میکند.
  - مجوز ابزارها همان `commands.classify` است.
- **هزینه:** اشتراک 20x مالک، با سهمیه‌ی مشترک با محصولات. یک هاست جدا هزینه‌ی تازه است و تصمیمش با مالک است.

## فرمان صوتی (§17.4)
- **مسیریابی سه مرحله دارد:**
  1. قاعده (`apps/api/seed/order_rules.yaml` به‌علاوه‌ی کد و نام هر شرکت)
  2. مدل سبک: کلاس کار `order_routing`، P1، `claude-haiku-5-5`، با json_schema، از طریق workflow `OrderRouting` روی worker
  3. مشاور کل (thread `A`)، فقط وقتی فرمان مبهم است
- **پاسخ مدل:** با فهرست شرکت‌ها و کارمندها چک میشود و هر کد ساختگی دور ریخته میشود.
- **مقصد هر نوع فرمان:**
  - `work`: مدیرعامل، یا مدیر بخش با میانبر (عمق ۱)
  - `code`: سشن جاری، یا سشن تازه زیر grant، یا تصمیم `code_session` (پیش‌فرض: سقف ۲۰ دلار، ۷ روز)
  - `question`: مشاور
  - `meeting`: کار برای مدیرعامل
- **ماسک:** متن پیش از هر مدل و هر ایجنت ماسک میشود.
