# HQ Core API v1 — قرارداد هسته

> **مالک سند:** Claude سشن مشورت. **پیاده‌سازی:** `apps/api/` (پرامپت ۴).
> **مبنا:** `docs/OPERATING_MODEL.md` (§۰ تا §۱.۱۶) و طراحی D1. هر جا این سند با مدل عملیاتی نخواند، مدل عملیاتی درست است و تفاوت باید گزارش شود.
>
> بدنه‌ی فنی به انگلیسی است تا نام فیلدها و رفتارها دقیق و بی‌ابهام باشد.
>
> **v1.1 (۲۰۲۶-۱۰-۱۷):** «Contract notes» گزارش پرامپت ۴ و نتیجه‌ی بازبینی وارد شد. تغییرها با ⟨1.1⟩ علامت خورده‌اند؛ آن‌هایی که هنوز پیاده نشده‌اند در `docs/server-prompts/PROMPT_04_1_HARDENING.md` هستند.
>
> **v1.2 (۲۰۲۶-۱۰-۱۷):** ایجنت‌ها سر کار (§۱۶، پرامپت ۵). **v1.3 (۲۰۲۶-۱۰-۱۷):** عکس و فیلم و صوت در پیام‌ها، تبدیل دقیق صدای فارسی به متن، کارگاه کد و فرمان صوتی (§۱۷، پرامپت ۶). **v1.4 (۲۰۲۶-۱۰-۱۷):** تصمیم‌های دور دوم مالک: ناظر کل، مشاور نسخه‌ی ۲، دستیار شخصی، ستاره‌ها، مهارت‌ها، آکادمی، اینترنت کامل و MCP برای ایجنت‌ها، تأسیس شرکت و ساخت سرور، backup ساعتی (§۱۸، پرامپت‌های ۷ تا ۹). **v1.4.1 (۲۰۲۶-۱۰-۱۷):** آنچه پرامپت ۵ واقعاً ساخت و نتیجه‌ی بازبینی آن (§۱۶.۶)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_05_1_FIXES.md`. **v1.4.2 (۲۰۲۶-۱۰-۱۷):** استخدام با شروع خود مالک (§۱۸.۱۱). **v1.4.3 (۲۰۲۶-۱۰-۱۷):** مدیرعامل‌ها با اختیار کامل در پاکت بودجه‌ی ماهانه استخدام میکنند و مدل هر کار را خودشان انتخاب میکنند (§۱۸.۱۱)؛ استوری شرکت‌ها (§۱۸.۱۲)؛ ستاره برای مصرف درست بودجه (§۱۸.۴). **v1.4.4 (۲۰۲۶-۱۰-۱۷):** پروتکل‌هایی که قابلیتشان هنوز ساخته نشده `paused` میمانند و نظارت سهم توکن خودش را دارد (§۱۸.۱)؛ ممیزی دوم در `docs/GAP_ANALYSIS_v2.md`. **v1.4.5 (۲۰۲۶-۱۰-۱۸):** آنچه پرامپت ۷ واقعاً ساخت و نتیجه‌ی بازبینی آن (§۱۸.۱۳)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_07_1_FIXES.md`. **v1.4.6 (۲۰۲۶-۱۰-۱۹):** نشان و مُهر هر شرکت از PNG خود مالک ساخته میشود و داده است (§۱۸.۱۴، پرامپت ۹.۱). **v1.4.7 (۲۰۲۶-۱۰-۲۲):** آنچه پرامپت ۸ ساخت و نتیجه‌ی بازبینی آن (§۱۸.۱۵)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_08_1_FIXES.md`. **v1.4.8 (۲۰۲۶-۱۰-۲۲):** آنچه پرامپت ۹ ساخت و نتیجه‌ی بازبینی آن (§۱۸.۱۶)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_09_2_FIXES.md`. **v1.6 (۲۰۲۶-۱۰-۲۲):** دپارتمان رسانه و طراحی در هر شرکت با برنامه‌ی انتشار مُهرشده، صدای متن‌باز روی هاب، و مشاور حقوقی هلدینگ با مکاتبه‌ی ایمیلی (§۲۲، پرامپت ۱۳). **v1.5 (۲۰۲۶-۱۰-۱۸):** درآمد و پشتیبانی: رادار درآمد، قیف و نجات رفرال، میز پشتیبانی با حالت آموزش و آزمون سایه، قالب‌ها و قاعده‌های چرخه‌ی عمر، NPS، صندوق بازخورد، نگهبان خروجی (§۱۹، پرامپت ۱۰)؛ حاکمیت: اتاق جلسه، اساسنامه، دانشنامه‌ی چهارلایه، سه کارت و کارت امتیاز، OKR، بازبینی نتیجه‌ی تصمیم، ماتریس اختیار، دفتر ریسک، تقویم تغییرات، مُهر گروهی (§۲۰، پرامپت ۱۱)؛ ابزار مدیریت: مشاور پریمیوم، «از هاب بپرس»، گزارش صوتی، ارزیابی ماهانه، هدررفت، ROI، پیش‌بینی مدیر کل دیجیتال، MCP کانتینری، و ChatGPT و Gemini به‌عنوان «بازیکن ذخیره» (§۲۱، پرامپت ۱۲).

> **v1.24 (۲۰۲۶-۱۱-۰۸):** هلدینگ زنده: یک جریان رویداد برای همه‌ی برنامه، نقشه‌ی شبکه، نبض دفتر، کنتور توکن و حال هر کارمند (§۴۲، W12).
>
> **v1.25 (۲۰۲۶-۱۱-۰۹):** کارگاه با دست: هر نقش هر شرکت هر کاری را که ابزارش را ندارد به Claude Code روی سرور هاب میدهد (`workshop.run`)، و فایل‌های `out/` با لینک در جلسه برمیگردند (§۴۳).
>
> **v1.26 (۲۰۲۶-۱۱-۱۰):** «با من» واقعاً قدم‌به‌قدم (§۳۴.۱، §۴۱.۲): گام‌های شماره‌دار مالک خودِ برنامه‌اند و به ترتیب خودش؛ کارگاه در «با من» فقط کار بعدی برنامه را شروع میکند؛ مسئول میتواند نوبت کارگاه خودش را متوقف کند (`workshop.stop`)؛ و اصلاح‌های بازبینی عمیق (§۴۳.۶، §۴۳.۷).
>
> **v1.27 (۲۰۲۶-۱۱-۱۰):** جلسه‌ی مستقیم، قدم اول (§۴۴، پرامپت ۳۲): گوینده‌ی محتوا روشن است (آنچه مالک خاموش کرد گفتگوی صوتی خودش بود)؛ استخدامی که مالک در جلسه‌ی خودش خواسته همان‌جا با کد انجام میشود، بی کارت و بی اثر انگشت؛ مسئول جلسه کار را خودش با کارگاه انجام میدهد؛ و نوبت کارگاه فایل‌های ستاد را با خودش میبرد (`workshop.run {files}`، §۴۳.۸)؛ و دیوار کارگاه بین شرکت‌ها که هیچ‌وقت جلوی کار را نمیگیرد (§۴۳.۹، runner 0.3.4).
>
> **v1.32 (۲۰۲۶-۱۱-۱۰، به‌روزرسانی ۱.۰.۱):** جلسه‌ی مستقیم، قدم سوم (§۵۴، پرامپت ۳۵؛ مالک: «مثل همین سشنی که من با تو صحبت میکنم»): مسئول جلسه یک نشست Claude Code روی کارگاه است، با ابزارهای ستاد. هر ابزار از همان درگاه ابزار رد میشود، هر توکن در خزانه ثبت میشود، و اگر کارگاه نتواند، مسئول مثل قبل کار میکند.
>
> **v1.31 (۲۰۲۶-۱۱-۱۰، به‌روزرسانی ۱.۰.۱):** کمبودهای فرمان ریلز (§۴۷ تا §۵۳، پرامپت ۳۵؛ مالک: «هیچ روزی تکراری نباشد»، «گوینده یک بار برای همیشه»، «در ساعت‌های پربازدید»): دفتر موضوع‌های گفته‌شده که کد جلوی تکرار را میگیرد؛ گوینده‌ی ثابت هر شرکت؛ «بهترین ساعت» از روی آمار IG-Hub؛ روال دائمی («کارمند ۲۴ ساعته») با یک جمله، بی کارت و بی اثر انگشت؛ لغو پست زمان‌بندی‌شده از اپ؛ تبدیل خودکار عکس و کاور به JPEG؛ و «بیشترین effort» برای کارگاه.
>
> **v1.30 (۲۰۲۶-۱۱-۱۰):** ساعت، کامنت و اسلاید در انتشار (§۴۶؛ مالک: «هر بار شاید یک کامنت باشد … ساعت را باید هاب تنظیم بکند»): هاب ساعت انتشار را میدهد و IG-Hub تا آن ساعت نگهش میدارد؛ کلمه‌ی کامنت و لینکِ همان پست همراهش میرود و در IG-Hub قانونِ همان یک پست میشود؛ اسلاید (چند فایل)؛ ساعت ثابت برای انتشار خودکار هر کارگروه. کاور ریلز و دستور انتشار در خود IG-Hub نوشته شد (شاخه‌ی `claude/coinepro-hub-setup-hsvnw7` آن ریپو).
> **v1.29 (۲۰۲۶-۱۱-۱۰):** اجازه‌ی دائمی انتشار (§۴۵، پرامپت ۳۴؛ مالک: «به صورت خودکار از روز دوم انجام بشه … نه اینکه هر بار من تایید کنم»): مالک یک بار برای هر شرکت در یک کارگروه میگوید «خودکار»؛ از نوبت بعد، هاب بسته‌ی هر روال (ویدیو، کاور، `caption.txt`) را خودش از همان مسیر IG-Hub منتشر میکند. بدون آن، هر خروجی مثل قبل منتظر لمس اوست، حالا بیرون از جلسه هم. مُهر و بازنشستگی کارگروه دیگر اثر انگشت نمیخواهد.
> **v1.28 (۲۰۲۶-۱۱-۱۰):** «تأیید و انتشار» (§۴۴.۴، §۴۴.۵، پرامپت ۳۳): مالک روی فایل خروجی جلسه یک بار میزند و همان فایل از راه runner سرور IG-Hub منتشر میشود، بی کارت و بی اثر انگشت؛ کارت `media_publish` هم دیگر اثر انگشت نمیخواهد. اثر انگشت فقط برای پول، حذف برای همیشه، کلید و دسترسی، و دستور ویرانگر سرور.

> **v1.12 (۲۰۲۶-۱۱-۰۴):** «خط تولید» (§۳۰، پرامپت ۲۲): موتور عمومی تولید و انتشار محتوا برای هر شرکت و هر پلتفرم، از روی قالب، با مرحله‌های قابل ویرایش، کتابخانه، تقویم، n8n برای مرحله‌های قاعده‌ای، و حالت پیش‌نویس تا خودکار.
>
> **v1.13 (۲۰۲۶-۱۱-۰۴):** رشد (§۳۱، پرامپت ۲۲): حلقه‌ی یادگیری خط تولید، شرکت آماده با یک فرمان، خبرنامه‌ی ایمیلی، رصد رتبه‌ی سئو و رقبا، تقویم یکپارچه‌ی کمپین، بودجه‌ی تبلیغات با توقف خودکار، و قاعده‌ی اتوماسیون از یک جمله‌ی مالک.
>
> **v1.14 (۲۰۲۶-۱۱-۰۴):** «گفتگو» (§۳۲، پرامپت ۲۳): گفتگوی صوتی و متنی مالک با منشی هلدینگ، ناظر کل، دستیار شخصی و هر مدیر هر شرکت؛ هر کدام با صدای خودش، حالت مشورت یا جلسه‌ی کاری، کارت به‌جای کار خودسر، کلید صدا در خود چت با چراغ وضعیت، و کنتور زنده‌ی هزینه با سقف مالک.
>
> **v1.18 (۲۰۲۶-۱۱-۰۶):** فایل در جلسه (§۳۶، پرامپت ۲۶): فونت و سند در بارگذاری، فایل در هر نوبت گفتگو، و فایل‌های جلسه برای همه‌ی کارهای همان فرمان.
>
> **v1.19 (۲۰۲۶-۱۱-۰۶):** پاک کردن برای همیشه (§۳۷، پرامپت ۲۶): جلسه، سند بایگانی و خروجی با مُهر مالک؛ پیشنهاد پاک کردن از ایجنت‌ها؛ لغو فرمان و حرف تازه بعد از تحویل.
>
> **v1.20 (۲۰۲۶-۱۱-۰۶):** هاب از داخل اپ (§۳۸، پرامپت ۲۶): کاتالوگ ثابت عملیات هاب برای تیم فنی هلدینگ با مُهر مالک برای کارهای حساس، و هیچ‌کس نمیگوید «دسترسی ندارم».
>
> **v1.22 (۲۰۲۶-۱۱-۰۷):** جلسه به کارگروه تبدیل میشود (§۴۰): حافظه‌ی جلسه، کارگروهِ قابل‌تکرار از نتیجه‌ی جلسه، و دادنش به شرکت یا پلتفرم دیگر.
>
> **v1.23 (۲۰۲۶-۱۱-۰۸):** جلسه کارش را زنده نشان میدهد و هیچ‌وقت بی‌صدا نمیماند (§۴۱): فعالیت زنده، مرحله‌های مالک برنامه‌ی جلسه، بیدار شدن مسئول، «ادامه بده».
>
> **v1.23 (۲۰۲۶-۱۱-۰۸، آن‌طور که ساخته شد، W11):** حرف مالک در جلسه‌ی کاری حرفِ فرمان است؛ هیچ سقف توکنی فرمان مالک را نمیخواباند؛ یک قاعده برای رسیدن شرکت‌ها به هم (کار، سرور، اتصال)؛ `connection.set`؛ حساب اینستاگرام روی IG-Hub است (§۴۱، یادداشت‌های as built).
>
> **v1.21 (۲۰۲۶-۱۱-۰۷):** جلسه کار را همان‌جا تمام میکند (§۳۹، W9): نقش در خودکارسازی هرگز رد نمیشود، هیچ کارتی از داخل جلسه فرمان تازه نمیسازد، مسئول کارت خراب خودش را درست میکند، داستان فرمان بی‌رسید و بی‌تکرار، و هر اجرا فقط آنچه لازم دارد را حمل میکند.
>
> **v1.17 (۲۰۲۶-۱۱-۰۶):** هر فرمان یک جلسه (§۳۵، پرامپت ۲۵): جلسه‌ی همیشه‌صاحب‌دار با حاضران و بازیکن‌ها، فهرست کارها، کارها در همان‌جا، بستن و بایگانی و باز کردن دوباره؛ دفتر مدیر کل؛ پیوند شرکت‌ها و بوم.
>
> **v1.16 (۲۰۲۶-۱۱-۰۶):** فرمان با جواب زنده (§۳۴، پرامپت ۲۵): ابزار گزارش و پرسش برای مسئول هر فرمان، «نوبت شما» و پاسخ مالک روی همان کار، گفتگوی زنده‌ی هر فرمان با مسئولش، و هیچ موضوع فنی برای مالک.
>
> **v1.15 (۲۰۲۶-۱۱-۰۵):** پول و شیوه‌ی کار Grok (§۳۳، پرامپت ۲۴): گزارش مصرف به زبان مشاور، خواندن و تطبیق پرداخت‌های کریپتویی شرکت‌ها (دفتر خود شرکت از راه runner و زنجیره‌ی عمومی)، تحلیل درآمد، CRM کوچک، پیگیری افیلیت، اثر پولی تصمیم‌ها، ایجنت‌های موازی، سفر شرکت، پرسونا و تست پیام، و محیط کاری روی سرور هر شرکت.
>
> **v1.11 (۲۰۲۶-۱۱-۰۲):** مالک فقط کسب‌وکار میبیند (§۲۹، پرامپت ۲۱): مسیر بر پایه‌ی حوزه، ضمانت جواب هر فرمان با «گزارش فرمان»، قانون‌گذاری مالک از اپ، منشی هلدینگ، صدای بلند، بودجه‌ی ارجاع، زبان فارسی و بازنویسی برای مدیر کل، شورای v2، آمادگی، استخدام خودکار، کارگروه‌ها، اتصال‌ها، خانه‌ی سه‌کارتی، وضعیت کارمند و مرز تأیید.

> **v1.10.2 (۲۰۲۶-۱۱-۰۲):** هزینه‌ی هلدینگ (§۲۸.۷، پرامپت ۲۰.۱): کاتالوگ فقط با دستور مالک و با سقف توکن، دیده‌بان اول با قاعده، سقف روزانه‌ی هر شرکت، سهم هر حوزه در گزارش، و متن GPT از چت وب ChatGPT.

> **v1.7 (۲۰۲۶-۱۰-۲۲):** بایگانی رسمی هلدینگ و هر شرکت (§۲۳، پرامپت ۱۴): سند، نسخه و مُهر، طرح بایگانی، سطح محرمانگی و مجوز دیدن، نگهداری و امحا با مُهر مالک، توقیف قانونی، یادآور سررسید، OCR فارسی روی هاب؛ «لایه‌ی باز»: نوع سند، فیلد، پوشه، سطح، قاعده، یادآور و اتوماسیون، همه داده و از اپ قابل گسترش.

---

## 0. Scope

v1 covers the **core of the holding**: identity, organisation, work and delegation, the three inboxes
(decisions, deliverables, messages), notifications and Khalvat, the resolutions ledger, audit, control
(kill switch, deploy freeze), read access to the Token Treasury, the live stream, and the **internal
API the agent runtime will use** (prompt 5). Meetings, charter, knowledge, support and the digital
CEO's model are later versions; their tables are not part of v1 unless listed here.

**Hard rules that every endpoint obeys**
1. **Companies are data** (§0). No company code, department code or role is hard-coded. Seeds are YAML files.
2. **Tenant isolation in the database:** every tenant row has `company_id`; Row-Level Security is **FORCE**d; the API sets `app.company_ids` (uuid[]) with `SET LOCAL` per transaction, exactly like `llm.*`.
3. **Nothing is deleted.** Messages, decisions, resolutions, deliverables, ratings and audit rows are append-only or soft-state. There is **no DELETE endpoint for business data** in v1. (A4: deleting data is forbidden for AI; for the owner, removal is archival.)
4. **Every mutation writes one audit row** in the same transaction (§8).
5. **Every owner action also writes one `owner.interactions` row** (decision, rating, edit, message, setting) — the raw material of the digital CEO (§1.8).
6. **Delegation is a database record, never an agent calling an agent** (§1.4). Maximum depth **2**, enforced in the database.
7. **No secret ever leaves the server** in a response, a log line or an event. Connection keys are write-only.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Base path | Public: `/api/v1/...` behind Caddy. Internal (agents, services): `/internal/v1/...` on `hq-internal` only, **never routed by Caddy**. |
| Format | JSON, UTF-8. Field names `snake_case`. |
| IDs | `id`: UUIDv7 string. Human references are separate, immutable, never reused: employee `TY-TECH-01`, decision `D-000123`, deliverable `O-000456`, resolution `M-0001`, message `A-0142` (§5.3). |
| Time | RFC 3339 UTC (`2026-10-17T05:42:00Z`). Clients render Jalali and Gregorian in the owner's time zone (`owner.settings.timezone`, default `Asia/Tehran`). |
| Money | Decimal **string** in USD, 6 decimals max (`"2.410000"`). Tokens are integers. |
| Enums | Lower-case strings. Unknown values from the server must be tolerated by clients (forward compatible). |
| Lists | Cursor pagination: `?limit=50&cursor=<opaque>` → `{ "items": [...], "next_cursor": "..." \| null }`. `limit` max 200. Default sort is newest first unless stated. |
| Filtering | Query parameters as listed per endpoint; `company` takes a code (`TY`) and may repeat. |
| Concurrency | Mutable resources carry `version` (int). **Every** PATCH requires `If-Match: <version>`; missing → `428 precondition_required` ⟨1.1⟩; mismatch → `409 version_conflict`. |
| Idempotency | Every POST that changes state accepts `Idempotency-Key` (UUID). **Required** for: decision actions, ratings, messages, work creation, kill switch. Same key + same body within 24 h returns the first result. |
| Errors | RFC 9457 `application/problem+json`: `{ "type", "title", "status", "code", "detail", "message_fa", "fields"? }`. `code` is stable and machine-readable (list in §14). `message_fa` is a short Persian sentence for the UI. |
| Rate limits | `429` with `Retry-After`. Auth endpoints are limited per IP and per credential. |
| Localisation | Data carries both `name_fa` and `name_en` where a human name exists. UI strings live in the clients. |
| Digits | The API returns numbers as numbers. Choice of Persian or Latin digits is the client's (D1: Latin for money, tokens, IDs and model names; Persian for prose counts). |

---

## 2. Identity and sessions

**Principals**
| kind | who | how it authenticates |
|---|---|---|
| `owner` | the general manager (one human) | Passkey (WebAuthn, user verification **required**) |
| `service` | internal services (llm-router, n8n, worker) | service token from OpenBao, `Authorization: Bearer` on `/internal` |
| `agent` | an employee, CEO, manager or the advisor when the agent runtime runs it (prompt 5) | short-lived token minted by the agent runtime per run, bound to one `employee_code` and its company |

**Owner sessions**
- Web: session cookie `hq_session` — `HttpOnly; Secure; SameSite=Strict; Path=/api`. Android: `Authorization: Bearer <opaque>`.
- Tokens are **opaque**, stored hashed server-side (`auth.sessions`), revocable, sliding expiry 30 days, absolute 90 days, bound to the device record.
- Mutations from the web must send `X-HQ-Client: web` and a same-origin `Origin`; otherwise `403 csrf_rejected`.
- **Step-up:** sensitive actions need a fresh passkey assertion (biometric on the phone). The client calls step-up, receives a `step_up_token` (single use, 120 s, bound to `action` and `target`), and sends it as `X-Step-Up`. Actions that require it are marked **🔏** below.

**First enrolment and recovery** (no password exists anywhere):
- The owner runs `make owner-enroll` **in their own terminal on the server**. It prints a one-time enrolment link valid 15 minutes. It is never logged and never shown to Claude.
- The same command is the recovery path if every device is lost.
- At least two passkeys (phone and computer) are recommended; the UI nags until there are two.

| Method | Path | Body / query | Result |
|---|---|---|---|
| POST | `/auth/passkey/register/options` | `{enrolment_token?}` (or an existing session + 🔏) | WebAuthn creation options |
| POST | `/auth/passkey/register/verify` | attestation, `{device_name}` | `{device}` |
| POST | `/auth/passkey/login/options` | — | WebAuthn request options; ⟨1.1⟩ discoverable credentials, `allowCredentials` empty, so no passkey id is revealed before login |
| POST | `/auth/passkey/login/verify` | assertion | `{session}` (+ cookie on web) |
| POST | `/auth/step-up/options` | `{action, target}` | request options |
| POST | `/auth/step-up/verify` | assertion | `{step_up_token, expires_at}` |
| GET | `/auth/session` | — | `{principal, device, expires_at}` |
| POST | `/auth/logout` | — | 204 |
| GET | `/auth/devices` | — | list of passkeys and sessions |
| POST | `/auth/devices/{id}/revoke` 🔏 | — | 204 (revocation is a state, the row stays) |

`device`: `{id, name, kind: "passkey"|"session", created_at, last_used_at, revoked_at?}`.
WebAuthn relying party: `HQ_WEBAUTHN_RP_ID` (the domain) and `HQ_PUBLIC_ORIGIN`. **Without a domain and HTTPS, login is disabled** and the endpoints answer `503 origin_not_configured`. ⟨1.1⟩ Owner decision 2026-10-17: the domain is **`hq.coinepro.com`** (RP ID = that host). A sign-count regression flags the passkey, writes an audit row and raises `urgent`. The Android app's origin (`android:apk-key-hash:…`) is an allow-list setting, empty until the app ships.

---

## 3. Organisation

### 3.1 Company
```
Company {
  id, code: "TY", kind: "holding"|"company",
  name_fa, name_en,
  color_index: 1..8|null,         // ⟨1.1⟩ slot in the categorical chart palette v2 (design/tokens). Given at creation,
                                  // kept forever, never by rank, never cycled. Companies without a slot appear
                                  // inside "Other" in charts. Companies are identified by their own mark, not a colour.
  status: "active"|"paused"|"archived",
  brand_version: int|null,         // ⟨1.4.6⟩ the active CompanyBrand (§18.14); marks and seals are drawn from GET /brands
  template: "standard",            // the template it was created from
  kill_switch: "released"|"engaged",
  deploy_freeze_until: datetime|null,
  counts: { employees_active, work_open, decisions_pending },
  version, created_at
}
```
| Method | Path | Notes |
|---|---|---|
| GET | `/companies` | `?status&q` — holding first, then by code. No fixed company count: always paginated and searchable. |
| GET | `/companies/{code}` | |
| POST | `/companies` 🔏 | `{code, name_fa, name_en, color_index?, template}` → creates departments and leadership positions **from the template file**, all in one transaction. |
| PATCH | `/companies/{code}` | `name_*`, `color_index`, `status` (`archived` only with 🔏). Code never changes. |
| GET | `/templates` | available company templates (from `seed/templates/*.yaml`). |

⟨1.1⟩ **The holding is a company row** (`kind: "holding"`, code from the seed, today `HQ`). Holding-level rows (advisor, OVS, AIOPS, holding-wide work and decisions) carry the holding's `company_id`, so `company` is **never null** in any response. Code never hard-codes the holding's code; it reads the `kind: "holding"` row.

### 3.2 Department
```
Department { id, company: "TY", code: "TECH", name_fa, name_en, manager_title_fa, manager_title_en,
             manager: EmployeeRef|null, status, sort, version }
```
Standard template: `TECH`, `GROWTH`, `SALES`, `PRODUCT`, `FIN`, `QUANT`, `AIOPS`, `HR`. The holding (`HQ`) has `OVS` (oversight, veto) and `AIOPS`, plus the advisor.

| Method | Path |
|---|---|
| GET | `/companies/{code}/departments` |
| POST | `/companies/{code}/departments` 🔏 |
| PATCH | `/departments/{company}/{dept}` |

### 3.3 Employee (every agent, including CEOs, managers and the advisor)
```
Employee {
  id, code: "TY-TECH-01" | "TY-TECH-MGR" | "TY-CEO" | "HQ-ADV",
  company: "TY", department: "TECH"|null,
  kind: "ceo"|"manager"|"employee"|"advisor"|"inspector"|"system",
  title_fa, title_en, display_name: string|null,
  reports_to: EmployeeRef|null,
  status: "active"|"paused"|"dismissed",
  activity: "sleeping"|"working"|"waiting"|"error",     // live, written by the runtime
  activity_note: string|null, activity_at: datetime|null,
  model: { connection, model, effort } ,                // resolved from llm.assignments, read-only here
  score: { value: 0..10|null, owner_avg: number|null, rank_in_department: int|null, trend: [..12 monthly] },
  hired_at, dismissed_at|null, hired_by_decision: "D-000123"|null, probation_until|null,   // ⟨1.4.3⟩ +7 days after a delegated hire
  version
}
EmployeeRef { code, title_fa, kind, company, department }
```
**Codes** (§1.2): `<COMPANY>-<DEPT>-<NN>` for employees (two digits, three when needed), `<COMPANY>-<DEPT>-MGR` for a manager, `<COMPANY>-CEO`, `HQ-ADV` for the advisor. **A code is issued once and never reused**, even after dismissal (a sequence per company+department that only moves forward).

**Score** (§1.16): `0.40·owner_rating + 0.25·success_with_evidence + 0.20·cost_per_accepted_output + 0.15·on_time`, each normalised to 0..10 over the last 90 days. Computed by a job, stored, never edited by hand.

| Method | Path | Notes |
|---|---|---|
| GET | `/employees` | `?company&department&kind&status&activity&q` |
| GET | `/employees/{code}` | includes the last 20 work items and ratings |
| PATCH | `/employees/{code}` | `display_name` only |
| POST | `/employees/{code}/pause` | stops new work being routed; open work stays |
| POST | `/employees/{code}/resume` | |
| POST | `/employees/{code}/dismiss` 🔏 | `{reason, transfer_to?: code}` → status `dismissed`, open work returns to the manager, a knowledge-transfer work item is created for the runtime (§1.3) |
| GET | `/org/{company}/chart` | tree: CEO → managers → employees, with `activity` |

Hiring never happens through this resource: it is a **decision** of kind `hire` (§5.1).

---

## 4. Work and delegation

```
Work {
  id, ref: "W-000789", company, department|null,
  kind: "one_off"|"recurring"|"event"|"project",
  title, brief (markdown), priority: "P0".."P4",
  status: "queued"|"in_progress"|"waiting"|"delivered"|"done"|"cancelled"|"failed",
  created_by: Actor, assignee: EmployeeRef|null,
  parent_id|null, root_id, depth: 0|1|2,
  requested_by_work_id|null,         // cross-department / cross-company request (§1.4)
  due_at|null, overdue: bool, escalation_level: 0..3,
  budget: { tokens|null, usd|null, tokens_used, usd_used },
  escrow: Escrow|null,               // recurring only
  schedule: { rrule, timezone, next_at }|null,
  deliverable_ids: [], evidence: [Evidence],
  key_result: "KR-…"|null,           // ⟨1.5⟩ the OKR key result it serves (§20.5)
  version, created_at, updated_at
}
Actor { kind: "owner"|"agent"|"service", code: "owner"|"TY-CEO"|..., display_fa }
Escrow { allowed_action_classes: ["A0","A1","A2"], token_cap_per_run, usd_cap_per_month, expires_at, approved_by: Actor, decision: "D-..."|null }
Evidence { kind: "deliverable"|"link"|"metric"|"log", ref, note }
```

**Rules (database-enforced where marked ⛓)**
- ⛓ `depth ≤ 2`. Owner → CEO is depth 0; CEO → manager 1; manager → employee 2. A shortcut straight to a manager starts at depth 1. A delegation beyond 2 → `409 delegation_depth_exceeded`.
- ⛓ A child budget can never exceed what remains of its parent; the sum of children ≤ parent.
- ⛓ `done` only with at least one deliverable or evidence (§1.9 #4); otherwise `422 evidence_required`.
- Cross-department: a manager creates a new root work in the other department with `requested_by_work_id`; the receiving manager accepts (assigns) or declines. Cross-company: only from CEO to CEO.
- Recurring work needs an escrow. Created by the owner → active immediately. Created by an agent (a CEO, or ⟨1.1⟩ a manager for its own department) → a decision `recurring_approval` that the owner **or that company's CEO** may approve, within the company's monthly quota (§1.4). ⟨1.1⟩ **Nobody approves their own proposal:** a CEO's own proposal goes to the owner.
- ⟨1.1⟩ `schedule.rrule` accepts only the subset that maps exactly onto a Temporal calendar spec: `HOURLY` with an `INTERVAL` that divides 24, and `DAILY`, `WEEKLY` (`BYDAY`), `MONTHLY` (`BYMONTHDAY`) with `BYHOUR` and `BYMINUTE`. Anything else → `422 validation_failed`.
- ⟨1.1⟩ `delivered → done` happens when the owner rates the deliverable or completes the work. An agent may decline work through `/internal/v1/work/{id}/fail` with `{decline: true, reason}`.
- Overdue work escalates one level at a time: manager → CEO → owner (§1.9 #5), each step a notification.
- Kill switch engaged or deploy freeze on a company → state-changing work for agents in that company is refused (`423 company_locked`); the owner is never locked out.

| Method | Path | Notes |
|---|---|---|
| GET | `/work` | `?company&department&assignee&status&kind&priority&due_from&due_to&parent&q&overdue` ⟨1.7.4⟩ `&created_by=owner\|<code>`. |
| GET | `/work/{id}` | includes `chain`: the delegation path with time, assignee and usage of each step (§D-13 of the design list). ⟨1.7.4⟩ Each of `children` carries `ref, title, status, assignee, updated_at, progress (0..1\|null, the latest `/progress` report), deliverable_refs`, two levels down. `Work` adds `deliverable_refs` beside `deliverable_ids`; `GET /deliverables` takes `?work=`. Stream `work.*` and `deliverable.created` payloads carry `root_id, root_ref`. |
| GET | `/work/{id}/events` | timeline |
| GET | `/work/{id}/tree-events` | ⟨1.7.4⟩ the work's and all its sub-works' events (depth ≤ 2), time order, `Page`; run steps as summaries only (§16). |
| POST | `/work` | owner order: `{company, department?, assignee?, title, brief, kind, priority, due_at?, budget?, escrow?, schedule?}`. Without `assignee` it goes to the CEO, or straight to a department manager when `department` is given. |
| PATCH | `/work/{id}` | `title, brief, priority, due_at` |
| POST | `/work/{id}/cancel` | `{reason}` |
| POST | `/work/{id}/complete` | `{evidence[]}` — owner may close with evidence |
| GET | `/planner` | `?scope=owner\|company:TY\|department:TY-TECH&from&to` → days with work due, recurring occurrences and (later) meetings. **A view over work, not separate data** (§1.9). |

---

## 5. The three inboxes

### 5.1 Decisions (کارتابل تصمیم)
```
Decision {
  id, ref: "D-000123", company, kind, action_class: "A1"|"A2"|"A3",
  title, what (markdown), why (markdown),
  proposer: Actor, work_id|null,
  quota_estimate: { tokens, usd }, risk: "low"|"medium"|"high", risk_note, reversible: bool,
  payload: <typed by kind, below>,
  status: "pending"|"approved"|"rejected"|"returned"|"expired"|"withdrawn",
  expires_at|null, decided_at|null, decided_by: Actor|null,
  seal: { sealed_at, method: "passkey_uv", step_up_id }|null,
  note|null, resolution: "M-0001"|null, thread: "TY-CEO"|null,
  approver: Actor|null,   // ⟨1.4.3⟩ who decides it: null = the owner; a company's CEO for delegated hires (§18.11)
  digital_ceo_prediction: { verdict: "approve"|"reject", confidence }|null,   // shown only when §1.8 enables it; ⟨1.5⟩ shape and reveal rule in §21.10
  version, created_at
}
```
| kind | payload | who may approve |
|---|---|---|
| `hire` | `{company, department, title_fa, title_en, reason, duties[], model, effort, permissions[], quota_estimate_month}` | owner |
| `dismissal` | `{employee, reason, transfer_to?}` | owner |
| `recurring_approval` | `{work_id, escrow, schedule}` | owner, or the company's CEO within quota |
| `deploy` | `{repo, pr_url, diff_stat, ci: {status, url}, tests: {passed, failed}, rollout}`; ⟨1.5⟩ one definition in §21.6, adding `head_sha` (required, the card is bound to it), `window`, `calendar_conflicts`, `diff`, `diff_unavailable` | owner only (A3) |
| `a3_action` | `{action, target, preview}` (publish, customer message, restart, price change) | owner; a post already in the approved content calendar may be approved by the CEO (§1.12) |
| `proposal` | `{okr, cost, risk, expected_impact, options[]}` (CEO growth proposals, batched) | owner |
| `budget_change` | `{scope, period, token_limit?, usd_limit?}` | owner |
| `evaluation` | `{employee, recommendation: "promote"\|"demote"\|"dismiss", evidence}` (monthly HR); ⟨1.5⟩ payload v2 in §21.5 | owner |
| ⟨1.5⟩ `message_template` · `lifecycle_rule` · `support_go_live` | §19.9 | owner |
| ⟨1.5⟩ `meeting_resolution` · `charter_amendment` · `okr` · `knowledge_entry` · `risk_acceptance` · `authority_change` | §20.11 | owner |

**Authority is policy, not code:** the "who may approve" column lives in OPA (`policy/decisions.rego`) and is tested. ⟨1.1⟩ The proposer is part of the policy input; **proposer = approver is always denied.** `budget_change.scope` must lie inside the proposer's company (owner proposals excepted).

⟨1.1⟩ **A decided decision is sealed:** `status`, `decided_*`, `seal`, `note` and `amendments` are written once, in the decision's own transaction, and never change afterwards. **Owner amendments are applied:** the effect uses the amended payload, and the response returns `amendments` next to the original `payload`.

⟨1.1⟩ `a3_action` of kind publish can be approved by a CEO only once the content calendar exists (a later version); until then it is owner only.

| Method | Path | Notes |
|---|---|---|
| GET | `/decisions` | `?status&company&kind&risk&q` — default `status=pending`, oldest first |
| GET | `/decisions/{ref}` | |
| POST | `/decisions/{ref}/approve` | 🔏 for `A3`, `hire`, `dismissal`, `budget_change`, ⟨1.4.3⟩ `code_session` (its seal creates a workshop grant), ⟨1.4.5⟩ `protocol`, `tool_enable`, `errand_action`, `company_found`, `lesson_adoption` (target = ref; a card is bound to what it proposes, so when that changes the card is superseded: `409 decision_not_pending`, and a new card comes). A `server_plan` card is sealed only on its own route against the plan's `digest` (§18.8); here it answers `409 validation_failed`. ⟨1.5⟩ Also 🔏 (target = ref, bound to the payload the same way): `message_template`, `lifecycle_rule`, `support_go_live` (§19.9), `charter_amendment`, `risk_acceptance`, `authority_change` (§20.11), `evaluation` (§21.5); several low-risk A1 cards may be sealed together (§20.10); `{note?, amendments?}` → resolution created |
| POST | `/decisions/{ref}/reject` | `{reason?, reason_code?: "cost"\|"risk"\|"timing"\|"quality"\|"other"}` |
| POST | `/decisions/{ref}/return` | «برگشت با یادداشت»: `{note}` (required) → back to the proposer |
| POST | `/decisions/{ref}/ask` | «توی چت بپرس»: opens or reuses the proposer's thread and posts a linked message; returns `{thread, message_ref}` |
| POST | `/decisions/{ref}/review-with-advisor` | «با مشاور بررسی کن»: posts the decision into the advisor thread (§1.7) |

### 5.2 Deliverables (کارتابل خروجی)
```
Deliverable {
  id, ref: "O-000456", company, work_id, producer: EmployeeRef,
  title, summary, body (markdown)|null, attachments: [FileRef],
  produced_with: { connection, provider, model, effort, label_fa: "انجام‌شده با Sonnet 5.5" },
  usage: { input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, equiv_cost_usd, cost_usd },
  evidence: [Evidence],
  rating: { score: 1..10, comment|null, rated_at, history_count }|null,
  created_at
}
FileRef { id, name, mime, size, sha256 }       // content via GET /files/{id}
```
| Method | Path | Notes |
|---|---|---|
| GET | `/deliverables` | `?company&producer&unrated&q` |
| GET | `/deliverables/{ref}` | |
| POST | `/deliverables/{ref}/rating` | `{score: 1..10, comment?}`. Re-rating within 7 days adds a new version; history is kept. |
| GET | `/files/{id}` | streams the file; tenant-checked |

⟨1.7.3⟩ **Seen and filed** (owner, 2026-10-29: «بعد از خواندن… برود توی خوانده‌شده، با دسته‌بندی درست… بعداً بشه بهش استناد کرد»):
```
Deliverable { …, category: "report"|"work",        // report: written by the hub's own reporting (HQ-SYS: morning report, letters); work: an agent's output for a work item
              seen_at|null,                         // the owner opened it and marked it seen; never deleted, so agents and the digital chief keep learning from it
              filed_as: "AR-…"|null }               // the archive record it was filed as (§23), if any
```
| Method | Path | Notes |
|---|---|---|
| GET | `/deliverables` | adds `?seen=true\|false&category=report\|work&from&to` (dates, owner's zone) to the filters above; newest first, a `Page` |
| POST | `/deliverables/seen` | owner · `{refs: [ref], seen: bool}` (one or many; swipe and "mark all seen") → `{updated}`; idempotent |
| POST | `/deliverables/{ref}/file` | owner · files it in the archive (§23): an archive draft of class `report` (or the rules' choice) with the body as a PDF and a link `about` to the deliverable; → `{record: "AR-…"}`; a second call answers the same record |
- `GET /inbox/summary` adds `deliverables_unseen`. Rating stays separate: an unrated deliverable may be seen, and the unrated filter still works.
- Nothing is deleted. A seen deliverable leaves the "new" list only; search, filters and the archive still find it.

### 5.3 Messages (پیام‌ها)
```
Thread { id, code, kind: "advisor"|"ceo"|"manager"|"department"|"employee",
         company|null, title_fa, participants: [Actor], last_message_at, unread: int }
Message { id, ref: "<thread.code>-<seq 4+ digits>", thread, author: Actor,
          body (markdown), attachments: [FileRef], links: { decision?, work?, resolution? },
          kind: "text"|"voice_transcript"|"system", created_at }
```
Thread codes: advisor `A`; a CEO `TY-CEO`; a manager `TY-TECH-MGR`; a department group `TY-TECH`; an employee `TY-TECH-01`.
So the advisor's 142nd message is **`A-0142`** — the reference the owner and the advisor cite (§1.1).

- **Messages are immutable.** No edit, no delete. A correction is a new message with `links.corrects`.
- Full-text search across threads the principal may read (Postgres FTS + `pg_trgm`; Persian-safe normalisation of ی/ي and ک/ك and ZWNJ).
- Agent replies are written by the runtime through the internal API (§12). v1 stores and serves; it does not generate.

| Method | Path |
|---|---|
| GET | `/threads` `?kind&company` |
| POST | `/threads` `{kind: "employee", employee}` (opens a direct thread) |
| GET | `/threads/{code}/messages` `?cursor` (oldest→newest page from the cursor) |
| POST | `/threads/{code}/messages` `{body, links?}` |
| POST | `/threads/{code}/read` `{up_to_ref}` |
| GET | `/search/messages` `?q&thread&company&from&to` |
| POST | `/resolutions` `{title, body, source_message?}` — the owner records a resolution from a conversation |

### 5.4 Resolutions (دفتر مصوبات)
```
Resolution { ref: "M-0001", company|null, title, body, source: { decision?: "D-..", message?: "A-0142" },
             sealed_by: Actor, sealed_at, sent_to: [EmployeeRef], follow_up_work_id|null }
```
Append-only, numbered for the holding in one sequence. Created automatically when a decision is approved, or by the owner from a message. Approval notifies the proposer and, if needed, creates the follow-up work (§1.7 cycle).

| GET `/resolutions` `?company&q` | GET `/resolutions/{ref}` |
|---|---|

### 5.5 Inbox summary
`GET /inbox/summary` → `{ decisions_pending, decisions_by_risk, deliverables_unrated, messages_unread, notifications: {urgent, decision, report, info, learning}, khalvat }` — for badges; cheap (< 20 ms).

---

## 6. Notifications and Khalvat

```
Notification { id, level: "urgent"|"decision"|"report"|"info"|"learning", company|null,
               title_fa, body_fa, link: { kind, ref }, created_at, read_at|null,
               choices: [{id, label_fa}]|null, answer: choice_id|null,
               delivered: { in_app, web_push, fcm, telegram } }
```
Behaviour (§1.7):
| level | delivery |
|---|---|
| `urgent` | always, even in Khalvat; sound; push |
| `decision` | batched (digest window, default 30 min); push once per batch |
| `report` | on the fixed rhythm (morning 08:00, weekly) |
| `info` | in-app only, silent |
| `learning` | in-app, rare, one-tap answers; capped per day |

- **Per-company, per-level settings:** `GET/PUT /notification-settings` → matrix `{company|*: {level: {in_app, push, sound, muted_until}}}`.
- **CEO attention quota** (§1.7 #4): non-urgent items from one CEO beyond `n/day` (setting, default 6) wait for the next digest.
- **Channels:** in-app (stream), Web Push (VAPID), FCM (Android), Telegram bot **as backup only — no approval is ever possible from Telegram**. Channels without credentials are simply off and reported.
- ⟨1.1⟩ **Agents and `urgent`:** the level is part of the policy input. An agent may raise `urgent` only with a `category` the policy lists (service down, security, data loss, budget hard stop), at most **5 per hour per company**; anything else is downgraded to `decision`. An agent of a locked company cannot raise notifications except `urgent` incidents.

| Method | Path |
|---|---|
| GET | `/notifications` `?level&company&unread` |
| POST | `/notifications/{id}/read` · POST `/notifications/read-all` `{before?, level?}` |
| POST | `/notifications/{id}/answer` `{choice_id}` (learning questions; recorded as an owner interaction) |
| GET/PUT | `/notification-settings` |
| GET | `/push/vapid-public-key` · POST `/push/web-subscriptions` · POST `/push/web-subscriptions/{id}/revoke` |
| POST | `/push/fcm-tokens` `{token, device_name}` · POST `/push/fcm-tokens/{id}/revoke` |

**Khalvat (owner presence)**
| Method | Path | Notes |
|---|---|---|
| GET | `/owner/presence` | `{khalvat: bool, since, until|null}` |
| PUT | `/owner/presence` | `{khalvat: true, until?}` or `{khalvat: false}`. Turning it on publishes `presence.changed`; every CEO sees "owner in Khalvat — urgent only". |
| GET | `/owner/away-summary` | `?since` (defaults to the last Khalvat start) → «در نبودت چه گذشت»: counts and the top items per box and per company, deterministic, no LLM in v1 |
| GET/PUT | `/owner/settings` | `{timezone, morning_report_at: "08:00", digest_minutes: 30, ceo_daily_attention: 6, calendars: ["jalali","gregorian"]}` |
| GET | `/owner/interactions` | the owner can always see what the system records about them (§1.8) |

---

## 7. Live stream

`GET /stream` — Server-Sent Events. `?topics=work,decisions,deliverables,messages,notifications,activity,llm,control,runs,stories&company=TY` (repeatable; ⟨1.4.1⟩ `runs` carries `run.*`).
- ⟨1.5⟩ Topics added by §19–§21: `revenue`, `support`, `growth`, `feedback` · `meetings`, `governance`, `knowledge` · `advisor`, `ask`, `reviews`, `briefings`, `people`, `notes`, `quality`, `dceo`, `treasury`, `creatives`. ⟨1.4.6⟩ `companies` (§18.14). ⟨1.6⟩ `media`, `legal` (§22).
- ⟨1.4.2⟩ **Unknown topics are ignored**, not refused: a client may name topics a newer server adds (`files`, `workshop`, `orders`, the §18 topics). The first SSE comment lists the topics actually served (`: topics work,decisions,…`). Only a malformed `topics` (pattern, length) is `422`.
- Envelope: `event: <type>` and `data: {id, type, at, company, ref, data}`; `id:` is the JetStream sequence so `Last-Event-ID` resumes without loss.
- Types: `work.created|updated|delegated|completed`, `decision.created|decided`, `deliverable.created|rated`, `message.created`, `notification.created`, `presence.changed`, `control.changed`, `employee.updated`, `activity.changed` (runtime), `llm.call.started|finished` (from llm-router, metadata only), `budget.alert`.
- Backed by NATS JetStream subjects `hq.core.<company>.<type>`; the API is a filtered, tenant-checked bridge. Heartbeat comment every 15 s.
- Scales to any number of companies: the client subscribes to the holding summary (`company=*` returns only counters and `activity.changed`, never full payloads).
- ⟨1.1⟩ Events from llm-router: NATS subject `hq.core.<CO>.llm.call_started` / `...llm.call_finished`; the envelope `type` keeps the dotted form `llm.call.started` / `llm.call.finished`.

---

## 8. Audit

```
AuditEntry { seq: bigint, at, actor: Actor, principal_kind, company|null,
             action: "decision.approve"|..., action_class: "A0".."A4",
             target: {kind, ref}, request_id, ip_hash|null, step_up: bool,
             summary, prev_hash, hash }
```
- **Append-only:** the API role has INSERT and SELECT only; a trigger rejects UPDATE and DELETE for everyone.
- **Hash chain:** `hash = sha256(prev_hash || canonical_json(entry_without_hash))`. A nightly job verifies the chain and raises `urgent` if broken. ⟨1.1⟩ `at` is always the database clock. The nightly job also **anchors the chain head outside Postgres** (seq + hash, append-only file in the backup set), and `verify` compares against the last anchor, so a rewrite that also rewrites the head is still caught.
- Bodies of messages and secrets are never copied into audit; only references.

| GET `/audit` `?company&actor&action&action_class&from&to` | GET `/audit/verify` → `{ok, checked, first_bad_seq|null, verified_at, anchor: {seq, hash, at, matches}|null}` ⟨1.1⟩ |
|---|---|

---

## 9. Control

| Method | Path | Notes |
|---|---|---|
| GET | `/control/state` | kill switches and deploy freezes for the holding and every company |
| POST | `/control/kill-switch` | `{scope: "holding"\|"company:TY", state: "engaged"\|"released", reason}`. **Engage needs no step-up** (speed matters); **release is 🔏**. A CEO (agent) may engage its own company's switch (internal API). ⟨1.1⟩ **Release follows authority:** a switch the owner engaged is released only by the owner with 🔏; a CEO may release only a switch that an agent of its own company engaged. |
| POST | `/control/deploy-freeze` | internal/owner: `{company, until, reason}` (§1.5 #5). ⟨1.1⟩ Freezes are lifted by authority too: the owner's only by the owner; the pipeline's by the pipeline or the owner; a CEO only its own. ⟨1.7.3⟩ The owner lifting (an `until` in the past) is 🔏 `deploy_freeze.lift` on `company:<CODE>`, like `kill_switch.release`; closing stays without step-up. The audit `summary` of `kill_switch.engage`, `kill_switch.release` and `deploy_freeze.set` carries the reason (`<summary>: <reason>`), so the control history (`GET /audit?company=&action=`) shows why. |

Engaged holding kill switch: the router refuses every call except P0, the worker pauses every agent workflow, and the stream shows it everywhere.

---

## 10. Token Treasury (read side of `llm.*`)

| Method | Path | Notes |
|---|---|---|
| GET | `/treasury/summary` | `?period=day\|month&company` → totals (input, output, cache read/write, thinking tokens; `cost_usd`, `equiv_cost_usd`), budget use % with 70/90/100 thresholds, top 5 consumers |
| GET | `/treasury/breakdown` | `?by=company\|department\|actor\|model\|connection\|task_class\|priority\|day&from&to&company` — ⟨1.3⟩ `day`: one row per calendar day **in the owner's time zone**, `key` = ISO date, ascending, days without calls included with zeros, inside `[from, to]` |
| GET | `/treasury/calls` | metadata only, paged; never prompt or response text |
| GET | `/treasury/what-if` | `?from&to&company&model=` → "what would this have cost on model X" from our price table (design list #22) |
| GET | `/connections` | registry without secrets |
| PATCH | `/connections/{id}` 🔏 | `status`, `display_name`, price table (each price with `source_url` and `as_of`); `Connection.version` and `If-Match` like every PATCH ⟨1.1⟩ |
| POST | `/connections/{id}/secret` 🔏 | `{secret}` **write-only** → stored in OpenBao; response never contains it; audit records only that it changed |
| POST | `/connections` 🔏 | ⟨1.5⟩ a new connection, `connection.create` on the body hash; it starts `pending_secret` (§21.7) |
| GET/PUT | `/assignments` (PUT 🔏) | holding → company → department → role → task class, with inheritance shown resolved. ⟨1.1⟩ The step-up is bound to a hash of the request body, not to `*`. |
| GET/PUT | `/budgets` (PUT 🔏) | per scope and period; step-up bound to the body hash ⟨1.1⟩ |

**Cost source:** `equiv_cost_usd` and `cost_usd` come **from our price table** in `llm.connections`. The SDK's own figure is stored in `meta.sdk_cost_usd` for comparison only.

---

## 11. Health and meta
`GET /health` (no auth; `{status}` only) · `GET /meta` (auth; versions, enabled channels, whether login is configured).

---

## 12. Internal API for the agent runtime (`/internal/v1`, not public)

Used by the agent runtime in prompt 5 and by tests now (with a fake agent principal). Every call is checked against the agent's company, department and role, and against OPA — ⟨1.1⟩ **before** anything outside the agent's company is looked up, so a refusal never reveals whether a code exists elsewhere.

⟨1.1⟩ **Agent principal:** `Authorization: Bearer hqa1.<…>`, an HMAC token (key in OpenBao `kv/hq-api/config`) for one employee and one run, lifetime ≤ 1 h, with a `jti` the API accepts once per request id window (replay refused). The company always comes from the employee row, never from the token. Every agent write also passes the action-class policy (`hq.actions`: A0–A3 by role and escrow; **A4 always denied**).

| Method | Path | Notes |
|---|---|---|
| POST | `/internal/v1/work/{id}/accept` · `/progress` · `/delegate` · `/deliver` · `/fail` | `deliver` creates a Deliverable; `delegate` enforces depth and budget |
| POST | `/internal/v1/work` | an agent opens work: a request to another department, or (CEO only) to another company's CEO |
| POST | `/internal/v1/decisions` | an agent proposes (hire, recurring approval, deploy, A3 action, proposal, evaluation) |
| POST | `/internal/v1/threads/{code}/messages` | an agent replies |
| POST | `/internal/v1/activity` | `{employee, activity, note}` → `activity.changed` |
| POST | `/internal/v1/notifications` | services and agents raise a notification (level rules and attention quota apply) |
| POST | `/internal/v1/control/kill-switch` | CEO for its own company only |
| GET | `/internal/v1/context/{employee}` | what the runtime needs to run one step: employee, work, budget left, escrow, company state |
| POST | `/internal/v1/decisions/{ref}/approve` · `/reject` ⟨1.1⟩ | a CEO decides what the policy lets it decide in its own company (e.g. `recurring_approval` within quota); never its own proposal |
| POST | `/internal/v1/files` ⟨1.1⟩ | raw-body upload (size limit enforced while streaming) → file id for evidence and deliverables |

---

## 13. Events on NATS (for other services)
`hq.core.<company>.<type>` with the same envelope as §7. Metadata only, no message bodies, no secrets. JetStream stream `HQ_CORE`, retention 30 days.

---

## 14. Error codes (stable)
`unauthenticated`, `forbidden`, `csrf_rejected`, `step_up_required`, `step_up_invalid`, `origin_not_configured`,
`not_found`, `version_conflict`, `idempotency_conflict`, `validation_failed`, `evidence_required`,
`delegation_depth_exceeded`, `budget_exceeded`, `company_locked`, `decision_not_pending`, `policy_denied`,
`rate_limited`, `channel_not_configured`, `internal_error`,
⟨1.1⟩ `precondition_required` (428, PATCH without `If-Match`), `policy_unavailable` (503, OPA did not answer; the API is fail-closed — distinct from `policy_denied` 403 so clients say "try again" instead of "not allowed").
⟨1.4.1⟩ `live_unavailable` (503, live replies are switched off; the stored reply still arrives in the thread).
⟨1.4.2⟩ `hiring_closed` (403, an agent proposed a hire while hiring is closed, §18.11).
⟨1.3⟩ `runtime_not_configured` (503, the Code Workshop has no runtime yet, §17.7).
⟨1.4.3⟩ `envelope_required` (422, delegated hiring needs a monthly envelope for every operating company), `envelope_exceeded` (409, the hire's monthly estimate does not fit the company's envelope), `story_limit` (429, a company's three stories a day). `not_ready` (409, a feature the contract names that this server build does not serve yet, e.g. `delegated` before prompt 8).
⟨1.4.5⟩ `needs_owner` (403, a web step or call that would commit the holding outside: the agent proposes it instead), `internal_data` (403, an outgoing query or call carries internal data), `egress_limit` (429 with `Retry-After`, a run's or a company-day's internet limit), `account_not_configured` (409, a service account has no secret yet). The MCP outcomes are not Problem codes: they are step outcomes (§18.13).
⟨1.4.7⟩ `held` (423, the target is held by the overseer, §18.15), `academy_budget` (409, the academy's monthly cap).
⟨1.6⟩ `series_not_sealed` (409), `platform_limit` (429 with `Retry-After`) — §22.
⟨1.5⟩ `channel_not_live` (409), `shadow_not_passed` (409), `template_not_sealed` (409), `send_blocked` (422, with `blocked_reasons`), `opted_out` (409), `send_limit` (429 with `Retry-After`) — §19; `meeting_not_live` (409), `knowledge_expired` (422), `batch_not_eligible` (422, `fields.items`) — §20.

---

## 15. Seeds (data files, not code)
- `seed/templates/standard.yaml` — the 8 departments with codes, Persian and English names and manager titles; leadership positions (CEO, 8 managers).
- `seed/templates/holding.yaml` — `OVS`, `AIOPS`, the advisor `HQ-ADV`.
- `seed/companies.yaml` already exists in llm-router; v1 extends rows (`name_fa`, `color_index`, `template`) without changing codes. ⟨1.1⟩ Today's slots: PC 1, FX 2, TY 3 (chart palette v2); the holding has none (charts draw it in neutral silver); a new company takes the next free slot, or none.
- Seeds are idempotent and never overwrite rows edited later.

---

## 16. v1.2 — agents at work (prompt 5)

> **v1.2 (2026-10-17).** Agents now run. Everything above still holds; this section adds what the agent runtime, the advisor and the rule-based checks expose. Role charters live in `agents/` (owned by the consultation Claude) and are read, never written, by the server.

### 16.1 Employee charter
`Employee` gains `charter: { role, version }` — the charter file (`agents/roles/<role>.md`) and version the employee runs with. `GET /roles` lists charters (role, titles, kind, scope, default model and effort, tools, limits, version); read-only. A run records the charter version it used.

### 16.2 Agent runs and steps (the "agent screen")
```
Run  { id, employee, work_ref|null, thread|null, trigger: "work"|"message"|"schedule"|"alert",
       state: "queued"|"running"|"done"|"failed"|"refused", started_at, finished_at|null,
       steps: int, tokens: {input, output, cache_read, cache_write}, equiv_cost_usd, charter_version }
Step { run_id, n, at, summary_fa, actions: [{tool, class, outcome: "ok"|"denied"|"error", ref?}] }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/runs` | `?company&employee&state&from&to` |
| GET | `/runs/{id}` | with `steps` |
| GET | `/work/{id}/runs` | runs for one work item |

Steps carry **summaries and tool metadata only** — never the prompt, the model's raw output or tool payloads. Stream types added: `run.started`, `run.step`, `run.finished`.

### 16.3 Conversations with agents and the advisor
- `POST /threads/{code}/messages` on a thread whose counterpart is an agent (the advisor `A`, a CEO, a manager, an employee) returns `{ message, reply: { state: "queued" } }` and wakes that agent (advisor at **P2**, others at their charter priority, CEO attention quota respected for *their* messages, not for the owner's).
- `GET /threads/{code}/live` — **owner only**, SSE. Events: `reply.started {run_id}`, `reply.delta {text}` (Persian text chunks of the reply being written), `reply.done {message_ref}`, `reply.failed {code}`. The final text is the stored message; deltas are not stored.
- `Message` gains `citations: [{ kind: "decision"|"resolution"|"deliverable"|"work"|"message"|"audit", ref }]`, validated server-side: a citation to a ref that does not exist or that the author may not read is dropped and counted in `meta.citations_dropped`.
- The advisor is **read-only**: it can only write in thread `A` and to its own memory.

### 16.4 Rule-based site checks and incidents
```
Site      { id, company, url, kind: "web"|"api"|"bot", expect: {status, contains?}, interval_s, enabled }
Check     { site_id, at, ok, status|null, latency_ms|null, tls_days_left|null, error_code|null }
Incident  { id, ref: "I-0001", company, site_id, opened_at, closed_at|null, severity: "sev1"|"sev2"|"sev3",
            work_ref|null, checks_failed }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/ops/sites` | `?company` — sites with their latest check and 24 h uptime |
| PUT | `/ops/sites` 🔏 | replace the list for one company (owner edits URLs; data, not code) |
| GET | `/ops/incidents` | `?company&open` |

No model runs for a healthy check. N consecutive failures open an incident and **one** work item for the company's CTO (or its SRE once hired); recovery closes it.

### 16.5 Quota
`GET /treasury/quota` → `{ subscription: { status: "ok"|"warning"|"limited", window, resets_at|null, source }, throttle: { paused_priorities: ["P4", …] } }`. The Quota Controller is code (no model): at `warning` it pauses P4, at `limited` it lets only P0–P2 through, and it says so on the stream (`budget.alert`).

### 16.6 As built in prompt 5 ⟨1.4.1⟩
Recorded from the server's report and the review of `server/p05-agents` (2026-10-17). Where the build differs from §16.1–16.5, this list is the contract.
- **Messages.** `POST /threads/{code}/messages` → `201 { message, reply: { state: "queued"|"running", run_id } | null }` on **every** thread; `reply` is null when no agent was woken. `Message.citations[{kind, ref}]` and `meta.citations_dropped` as in §16.3; an agent's message carries at most 50 citations, checked against what its author may read. An agent's `links` refs must exist in the thread's company (prompt 5.1).
- **Charters.** `Employee.charter` is `{role, version|null} | null`. `GET /roles` is a plain list and adds `department` and `priority`. A charter with `scope: holding` (in the holding company) reads every company.
- **Hiring.** The `hire` payload carries `role`: required when an agent proposes and checked again at approval, before the step-up is consumed. It must be an `employee` charter whose scope fits the company (company ← `company`, holding ← `holding`) and the department; otherwise `422 validation_failed`.
- **Runs.** `Run` adds `company, reason, priority, model, effort, queued_at, tool_calls, cost_usd, charter, partial, error_code`. `steps` stays a count; `GET /runs/{id}` and `GET /work/{id}/runs` carry `steps_detail[Step]`. `/work/{id}/runs` is an unpaged list, oldest first. A step action's class is serialised as `"class"`.
- **Usage.** What an agent reports as usage on `deliver` is ignored; a deliverable's `usage` and `produced_with` come from its run's ledger rows (prompt 5.1).
- **Locks.** A holding or company kill switch **and a deploy freeze** refuse a run before its next step (prompt 5.1); a freeze no longer lets model calls continue with read-only writes.
- **Caps.** Tool-call caps per step and per run answer `429 rate_limited` with `Retry-After`. The daily agent token cap counts input, output and cache tokens and is checked before **every** model call, not only at the start of a run.
- **Site checks.** `Site` adds `method, canary, consecutive_failures, last{…}, uptime_24h, version`. `PUT /ops/sites` takes `{company, sites[≤50]}` and is sealed with step-up action `sites.update` bound to the SHA-256 of the exact body; sites left out are switched off, never deleted; canaries are untouched; URLs on private or internal addresses are refused. `Incident` carries `url` (not `site_id`), `last_status`, `last_error`.
- **Unpaged lists.** `/roles`, `/ops/sites` and `/ops/incidents` (`limit` ≤ 500) are plain lists, an accepted exception to §1's paging rule: each is small by nature.
- **Quota.** `subscription` adds `connection, utilization, changed_at`; `window` and `resets_at` are null while `ok`. A `limited` state whose reset time is unknown expires after the router's retry time or five hours, never "for good" (prompt 5.1). Each status change is published as `budget.alert {kind: "quota", …}` on the holding's subject with one 🔵 report.
- **Live replies.** `GET /threads/{code}/live`: every event carries `run_id`; when live replies are off it answers `503 live_unavailable` (new stable code, §14).
- **Stream.** Topic **`runs`** carries `run.started`, `run.step`, `run.finished` (§7's topic list gains `runs`).
- **Step-up.** `/auth/step-up/verify` rotates the web session cookie (`Set-Cookie`); bearer sessions (Android) are not rotated.
- **Internal API for the runtime (§12).** `GET /internal/v1/work/ref/{ref}`, `/company/state`, `/health/sites`, `/health/hub`, `/treasury/usage`, `/knowledge/search` (kinds: `resolutions, deliverables, decisions, work`; `messages` for the advisor only), `/audit/recent`, `GET|POST /memory` (POST honours `Idempotency-Key`), `POST /runs/self/reserve`, `POST /runs/self/tool-calls`, `POST /threads/{code}/live` (NDJSON). Policy is decided before any lookup in another company, so a missing and a forbidden code answer the same 403.
- **Redaction.** Keys, tokens, passwords, e-mails, phone and card numbers are masked in everything a model reads (run context, tool results, decision payloads, memory) and in everything an agent writes or streams (prompt 5.1); outgoing text is masked but never shortened.

---

## 17. v1.3 — media, voice, the Code Workshop and voice orders (prompt 6)

> **v1.3 (2026-10-17).** Owner requests of 2026-10-17: send photos and videos to managers and employees; voice turned into
> exact Persian text; a Claude Code workspace inside the app, driven by managers and the advisor under the owner's grant;
> and orders given by voice that reach the right place. Everything above still holds.

### 17.1 Owner uploads and attachments
```
FileRef ⟨1.3⟩ { id, name, mime, size, sha256,
                kind: "image"|"video"|"audio"|"document",
                status: "processing"|"ready"|"failed",
                width?, height?, duration_s?,
                variants: { thumb?: file_id, poster?: file_id },
                transcript?: string }            // audio, and the sound of a video, when ready
```
| Method | Path | Notes |
|---|---|---|
| POST | `/files` | Owner only. **Raw body** (no multipart), `Content-Type` = the file's type, `X-File-Name` = UTF-8 name, percent-encoded; `Idempotency-Key` as every POST. Allowed: images `jpeg`, `png`, `webp`, `heic` (≤ 20 MB); video `mp4`, `webm`, `quicktime` (≤ 200 MB, ≤ 10 min); audio `m4a/aac`, `ogg/opus`, `webm`, `wav`, `mpeg` (≤ 25 MB, ≤ 15 min); `pdf` (≤ 30 MB). The size limit is enforced **while streaming**, the type is checked by content (magic bytes), not by the header. → `201 FileRef` (`status: "processing"` for video and audio). |
| GET | `/files/{id}` | `?variant=original\|thumb\|poster` (default original); supports `Range`; tenant-checked. |
| GET | `/files/{id}/meta` | the `FileRef` (poll while `processing`; the stream also sends `file.ready`). |

- **Processing** (a worker, no model): images lose EXIF and GPS, get a 512 px WebP `thumb`; videos get a `poster` frame, up to 12 key frames (scene change, at most one per 5 s) for agents, and their sound track transcribed (§17.2); audio is transcribed.
- `MessageIn` ⟨1.3⟩ `{ body, links?, attachments?: [file_id] }` — up to 10 owner files. `body` may be empty when there is an attachment. Agents
  receive **images as vision input** (long edge ≤ 1568 px), **video as its key frames plus transcript**, **audio as transcript** — never raw
  video or audio. A model never sees EXIF, file names it did not need, or another company's files.
- Files are company-scoped like everything else: a file attached in an `FX-…` thread is readable by FX agents only (and the owner).

### 17.2 Voice to exact Persian text
| Method | Path | Notes |
|---|---|---|
| POST | `/transcribe` | Owner only. Raw audio body (types and limits as §17.1 audio). `?purpose=message\|order\|note` (⟨1.5⟩ `&save=true` with `note` also files the quick note, §21.8). → `{ text, language: "fa", duration_s, confidence: 0..1, segments: [{start_s, end_s, text}], file_id, engine: {name, model, version} }` |

- Engine: **self-hosted Whisper** (`faster-whisper`, model `large-v3-turbo`, int8 on CPU; MIT licence) with `language="fa"`, beam 5, VAD.
  Nothing leaves the hub for speech recognition.
- Then a **deterministic Persian normaliser**: Arabic ي/ك → ی/ک, ZWNJ for «می»/«نمی» prefixes and «ها»/«های»/«تر»/«ترین»/«ام»/«ای» suffixes,
  Persian punctuation (، ؛ ؟), numbers kept as spoken, no translation, no paraphrase.
- Then an optional **punctuation pass** with the light model (A0, owner-zone budget): it may add punctuation and paragraph breaks and fix
  obvious ASR splits only; the server rejects its output when the word-level edit distance from the normalised text exceeds 8% and keeps
  the normalised text instead. Both texts are kept for the quality log.
- **Quality protocol (roadmap month 3, pulled forward):** a 100-sample Persian test set of the owner's own voice (with exact transcripts the owner
  confirms) measures word error rate per engine version; target ≥ 95% word accuracy. Results in `docs/ops/reports/`.
- A message sent from voice is stored as `kind: "voice_transcript"` with the audio as an attachment, so the owner can always replay what was said.

### 17.3 The Code Workshop (کارگاه کد)
A place inside the app where Claude Code works on the companies' repositories: sessions are opened under an owner **grant**, driven by an
agent (a CTO, Lead Developer, the hub's own platform SRE) or by the owner directly, watched live, and stopped at any time.
```
Workspace { id, code: "FX-APP", company, repo: "<owner>/<name>", default_branch, title_fa,
            policy: { branch_prefix: "hq/", may_open_pr: true, merge: "owner_seal", deploy: "owner_seal" }, status: "active"|"paused" }
Grant     { id, ref: "G-0001", workspace, actions: ["read","edit","run","push_branch","open_pr"], driver: Actor|null,
            budget_usd, expires_at, granted_by: Actor, decision_ref|null, revoked_at|null }
CodeSession { id, ref: "S-0001", workspace, grant, title, brief, opened_by: Actor, driver: Actor,
              runtime: "subscription"|"managed"|"self_hosted", model, effort,
              state: "starting"|"working"|"waiting_approval"|"idle"|"done"|"failed"|"stopped",
              branch|null, pr_url|null, usage: { usd, input_tokens, output_tokens }, created_at, updated_at }
SessionEvent { seq, at, type: "message"|"progress"|"command"|"file_change"|"approval_request"|"approval_result"|"state"|"error",
               actor: Actor, summary_fa, data }   // data: {cmd, exit_code} | {path, added, removed} | {approval_id, action, detail} …
```
| Method | Path | Notes |
|---|---|---|
| GET | `/workshop/workspaces` | `?company` |
| PUT | `/workshop/workspaces` 🔏 | owner edits the list (data, not code) |
| GET | `/workshop/grants` | `?workspace&active` |
| POST | `/workshop/grants` 🔏 | owner grants `{workspace, actions, driver?, budget_usd, expires_at}`; agents ask through a decision of kind `code_session` (A1), whose seal creates the grant |
| POST | `/workshop/grants/{ref}/revoke` | immediate; running sessions under it stop |
| GET | `/workshop/sessions` | `?workspace&state&driver` |
| POST | `/workshop/sessions` | `{grant, title, brief, attachments?, model?, effort?}` — owner, or the grant's driver through the internal API |
| GET | `/workshop/sessions/{ref}` | |
| GET | `/workshop/sessions/{ref}/events` | `?after` (seq) |
| GET | `/workshop/sessions/{ref}/live` | SSE of `SessionEvent` (`event:` = its `type`); resumes with `Last-Event-ID` = seq |
| POST | `/workshop/sessions/{ref}/messages` | `{body, attachments?}` — the owner steers a session in words or voice |
| POST | `/workshop/sessions/{ref}/approvals/{id}` 🔏 | `{allow, note?}` — answers an `approval_request` (push, opening a PR, any command outside the allow-list) |
| POST | `/workshop/sessions/{ref}/stop` | immediate; the branch stays |

**Rules (non-negotiable):**
1. The workshop **never touches production**: no SSH, no deploy keys, no server credentials, no database URLs. Its only write is a git push to
   `hq/<session-ref>` branches and opening a PR. Merge and deploy stay decisions with the owner's seal (§5.1, OPERATING_MODEL §1.1).
2. **Credentials never enter the sandbox.** ⟨1.4.3⟩ The hub clones into the sandbox and **the hub itself pushes** the session's `hq/<session-ref>`
   branch (a fixed refspec, never another ref) and opens the PR, with the git access the owner already gave the hub (owner, 2026-10-17: no new
   tokens). The credential stays in the hub, is never printed and never shown to a model; a workspace the hub cannot reach shows `no_access`.
3. Each session runs in **its own sandbox** with a fresh clone, no access to the hub's network or other sessions, outbound limited to GitHub and
   package registries. A session's CLAUDE.md is the repository's own; the repository's rules bind the session.
4. **Budget:** every session has a USD cap from its grant; at the cap it stops and asks. Usage enters the Token Treasury like every call.
5. **Kill switch and deploy freeze:** engaging either for the workspace's company pauses its sessions.
6. **Work lock** (OPERATING_MODEL §1.5): one writing session per repository area at a time; others queue.
7. **Everything is recorded:** events carry summaries and metadata; the full session transcript is stored in object storage, owner-readable,
   retained with the audit set.

**Runtime.** ⟨1.4.3⟩ **None is chosen; the in-hub runtime is shelved** (owner, 2026-10-17). The owner wants to see their own Claude Code sessions,
and those live in claude.ai/code and the Claude app, which no official API exposes to a third-party app; building a look-alike would spend credit
without giving that. The control plane (workspaces, grants, history) stays and stays dormant: `workshop.runtime` is `null` and
`POST /workshop/sessions` answers `503 runtime_not_configured`; the apps open claude.ai/code instead. `subscription` (Claude Code under the
holding's subscription in a sandbox on the hub, the hub pushing), `managed` and `self_hosted` remain designs, not builds.

### 17.4 Voice orders (فرمان صوتی)
| Method | Path | Notes |
|---|---|---|
| POST | `/orders` | `{text, source: "voice"\|"text", file_id?, company?}` → `{ ref: "F-0001", routes: [{company, to, kind: "work"\|"code"\|"meeting"\|"question", work_ref?, session_ref?, decision_ref?}], summary_fa }` |
| GET | `/orders` | `?from&to` — the owner's orders and where each went |

- Routing is **rules first** (named company, named role, known keywords), then the light model, then the advisor only when the order is
  ambiguous; the depth-2 rule of §4 still holds.
- `code` orders go to the workshop: into a running session the order fits, else a new session under an existing grant, else a
  `code_session` decision for the owner's seal. `question` orders go to the advisor (thread `A`).
- The order, its audio and its routes are kept; the order appears in the owner's planner.

### 17.5 Not in the API
The owner's own claude.ai / Claude Code sessions stay in the owner's Claude account. The apps open them (`https://claude.ai/code`) with the
owner's own sign-in; the hub never stores, proxies or reads them.

### 17.6 Stream types added
`file.ready`, `file.failed`, `workshop.session` (state changes), `workshop.approval` (a new approval request), `order.routed`.
Their `/stream` topics: `files`, `workshop`, `orders` (added to the `topics` list of §7).

### 17.7 Step-up targets and discovery
- Step-up actions (🔏 above): `workshop.grant` and `workshop.workspaces` are bound to the SHA-256 of the request body (like
  `/budgets`); `workshop.approval` is bound to `"{session_ref}/{approval_id}"` (e.g. `S-0004/AP-0007`) and is needed only to
  **allow** — a denial (`allow: false`) needs no step-up, like engaging a kill switch.
- `GET /meta` gains `workshop: { runtime: "subscription"|"managed"|"self_hosted"|null }` — `null` until the owner chooses (then `POST /workshop/sessions`
  answers `503 runtime_not_configured`), so the apps can say so before the owner tries.

### 17.8 As built in prompt 6 ⟨1.4.3⟩
- **FileRef** carries `kind`, `status`, `width?`, `height?`, `duration_s?`, `variants {thumb?, poster?}`, `transcript?`; a variant is fetched as
  `GET /files/{id}?variant=thumb|poster` on the original's id. The agents' `GET /internal/v1/files/{id}/meta` adds `frames: [{id, at_s}]`; a missing and
  a forbidden file are both `403 policy_denied` (no existence oracle).
- **Ownership:** an owner upload sits in the holding until its first attachment, then belongs to that thread's company for good; attaching it in
  another operating company is `422` (upload again). Files are never shared across companies.
- **`/transcribe`** keeps the audio as a file (`purpose: message|order|note`); attaching a `message` audio makes the message `voice_transcript`. The
  punctuation pass is skipped when the text holds anything the masker would hide (no model reads a spoken secret). While the `stt` service is off
  (memory, owner's decision): `503 channel_not_configured`.
- **Workshop:** `CodeSession` gains `area`, `held: "budget"|"company_locked"|"work_lock"|null` and `transcript_file`; owner-only
  `GET /workshop/sessions/{ref}/transcript`; the events list is a `Page`; `PUT /workshop/workspaces` takes the whole list and a workspace left out is
  paused, never deleted; a grant's driver must belong to the workspace's company; an owner-ordered `code_session` defaults to `$20`, 7 days.
  New stable code `runtime_not_configured` (503, §14).
- **Orders:** `Order` gains `routed_by: "rule"|"model"|"advisor"`; each route gains `message_ref?` and `note_fa?`.
- **The agents' file tool** is `files.read` (`agents/tools.md`); prompt 6 built it as `file.view` — the name follows `tools.md` (review of 6).
- Gaps left open (safest behaviour): session attachments are recorded but not yet sent to the runtime; workshop usage sits on the session row, not
  yet in the Token Treasury ledger (a managed runtime bills its own API key).

## 18. v1.4 — the owner's decisions of 2026-10-17, round two (prompts 7–9)

> Owner decisions (`docs/OWNER_REQUESTS_2026-10-17.md`, `OPERATING_MODEL.md` §1.17): a **Chief Overseer** above QC; the advisor at rank two
> with read access to everything; a **personal assistant**; **full internet** for agents; **MCP** and a **skill library**; the **holding academy**;
> **stars** given by CEOs; **company founding with server provisioning** that ends with Claude Code ready for the owner's own login; **hourly
> encrypted backups** to the owner's Google Drive. Everything above still holds: A3 needs the owner's seal, A4 never happens, no secret leaves the server.

### 18.0 Kinds, precedence and threads
- `Employee.kind` gains `"overseer"` and `"assistant"`; `Thread.kind` gains `"overseer"` and `"assistant"`.
- Seeds (data): `HQ-OVR` overseer (thread **`N`**, messages `N-0001`), `HQ-PA` personal assistant (thread **`P`**, messages `P-0001`).
  The inspector `HQ-OVS-MGR` `reports_to` the overseer and leads **QC**.
- `Employee.rank` (computed, read-only): **1** owner · **2** overseer, advisor · **3** CEO, inspector, AI Ops head · **4** manager · **5** employee.
  `GET /meta` gains `precedence: [{rank, kinds, note_fa}]`. An inquiry from rank 2 must be answered (§18.2).

### 18.1 Oversight (the Chief Overseer)
```
Protocol   { id, ref: "PR-001", title_fa, area: "truth"|"authority"|"money"|"safety"|"quality"|"delivery"|"security"|"data"|"people"|"product"|"owner",
             check_md, method: "rule"|"sample"|"llm"|"reconcile"|"blind_test"|"mystery"|"drill",
             schedule: RRULE (owner TZ), scope: "holding"|"company"|"department", evidence_md,
             severity: "info"|"low"|"medium"|"high"|"critical", answerable: role, status: "active"|"paused"|"draft",
             version, sealed_at|null, last_run: { at, result: "pass"|"fail"|"partial"|"deferred", findings: int }|null }
Finding    { id, ref: "FI-0001", company, protocol|null, severity, title_fa, body_md, evidence: [{kind, ref, note}],
             status: "open"|"acknowledged"|"fixing"|"fixed"|"verified"|"disputed"|"closed", answerable: Actor, due_at,
             opened_at, closed_at|null, history: [{at, by: Actor, status, note}] }
Challenge  { id, ref: "CH-0001", company, period: "week"|"month", title_fa, brief_md, criteria: [{name_fa, weight}], due_at,
             status: "issued"|"accepted"|"submitted"|"scored"|"missed", score: 0..100|null, judge: Actor, work_ref|null }
StandingOrder { id, ref: "SO-001", text_md, source: "voice"|"text", file_id|null, applies_to: "overseer"|"all",
             status: "proposed"|"sealed"|"retired", version, sealed_at|null }
Hold       { id, ref: "H-0001", company, action: { kind, summary_fa, payload_digest }, reason_md, held_by: Actor, held_at,
             state: "held"|"released"|"cancelled", decided_by|null, decided_at|null }
Compliance { company, score: 0..100, by_area: {area: 0..100}, findings_open: {critical, high, medium, low}, protocols: {passed, failed}, trend: [0..100] }
WatchReport { on: bool, since, until|null, summary_md, held: [H-…], urgent: [notification id], findings: [FI-…] }
```
⟨1.4.4⟩ **A protocol that checks a feature not built yet is `paused`:** no schedule, no run, no finding, not counted in compliance.
The prompt that builds the feature makes it `active`. **Oversight token share:** the overseer and QC together use at most
`OVERSIGHT_DAILY_SHARE` (default 0.2) of the agents' daily token cap; once it is spent only `critical` protocols run and the rest
record `deferred` (not a failure) and run first the next day. One overseer run is capped at 200 000 tokens (charter v2).
| Method | Path | Notes |
|---|---|---|
| GET | `/oversight/summary` | compliance per company, open findings by severity, holds waiting, this week's challenges, watch mode |
| GET | `/oversight/protocols` | `?area&status` |
| POST | `/oversight/protocols` 🔏 | owner adds (body hash); agents propose through a decision of kind `protocol` |
| PUT | `/oversight/protocols/{ref}` 🔏 | edit, pause or resume = a new version (body hash) |
| GET | `/oversight/protocols/{ref}/runs` | results with findings |
| GET | `/oversight/findings` · `/oversight/findings/{ref}` | `?company&status&severity` |
| POST | `/oversight/findings/{ref}/status` | owner: `verified`, `closed`, `disputed` with a note |
| GET | `/oversight/challenges` | `?company&period&status` |
| GET · POST | `/oversight/orders` | owner's standing orders (text or voice); POST creates `proposed` |
| POST | `/oversight/orders/{ref}/seal` 🔏 · `/retire` | seal target = ref |
| GET | `/oversight/holds` | `?state=held` |
| POST | `/oversight/holds/{ref}/release` 🔏 · `/cancel` | release target = ref; cancel needs none |
| GET | `/oversight/watch` | the current or last watch report |
| GET | `/oversight/compliance` | per company, with trend |

- **Watch mode** is on while Khalvat is on, after `owner_settings.watch_after_hours` (default 6) without owner activity, or when the owner says so.
  In watch mode the overseer holds and stops; it never approves (owner decision).
- **Powers through the internal API** (agents/tools.md): `hold`, `kill_switch.engage` (company scope), `deploy.freeze`, `finding.raise`,
  `challenge.issue`, `inquiry.ask`, `notify` urgent. **Releasing** a kill switch, a freeze or a hold is the owner's alone.

### 18.2 Inquiries (advisor and overseer ask; everyone answers)
```
Inquiry { id, ref: "Q-0001", from: Actor, to: Actor, company, question_md, due_at, status: "open"|"answered"|"late"|"withdrawn",
          answer_md|null, evidence: [{kind, ref, note}], answered_at|null, thread_ref }
```
| GET | `/inquiries` | `?from&to&status` (owner sees all) |
- The answer appears in the asker's thread (`A-…` or `N-…`) with `links.inquiry`. A late inquiry notifies the owner and counts against compliance.

### 18.3 The personal assistant: errands
```
Errand { id, ref: "E-0001", title_fa, brief_md, source: "voice"|"text", file_ids: [id], due_at|null,
         status: "queued"|"working"|"waiting_owner"|"done"|"failed"|"cancelled",
         steps: [{at, kind: "search"|"read"|"browse"|"request"|"draft"|"note"|"proposal", summary_fa, data}],
         result_md|null, attachments: [FileRef], decision_ref|null, usage: {usd, input_tokens, output_tokens}, created_at, updated_at }
```
| GET · POST | `/errands` | POST `{brief_md, source, file_ids?, due_at?, title_fa?}` |
| GET | `/errands/{ref}` | |
| POST | `/errands/{ref}/cancel` | |
- Thread **`P`** is the conversation; a message can open an errand (`links.errand`). An external commitment becomes a decision of kind `errand_action` (A3).

### 18.4 Stars
```
StarRubric { company, version, criteria: [{key, name_fa, weight, description_md}], rules_md, by: Actor (CEO), status: "draft"|"active", updated_at }
Star       { id, employee, company, week (Saturday, YYYY-MM-DD, owner TZ), stars: 0..5, by: Actor (CEO), reason_md, evidence: [{kind, ref, note}],
             criteria: {key: 0..5}, counted: bool, overseer_note|null, created_at }
StarRollup { period: "week"|"month", key, best_company,
             companies: [{company, stars: 0..5, score: 0..100, parts: {kpi, challenges, compliance, people, efficiency}, rank, trend: [0..100]}],
             employees: [{code, company, title_fa, stars: 0..5, count, rank_company, rank_holding, trend: [0..5], efficiency: 0..100|null}],
             lessons: [L-…] }
Lesson     { id, ref: "L-0001", source_company, period, title_fa, body_md, evidence, adoption: [{company, status: "proposed"|"adopted"|"rejected", decision_ref}] }
```
| GET | `/stars/rubrics` · `/stars/rubrics/{company}` | CEOs write them (internal `star.rubric`); the owner reads |
| GET | `/stars` | `?company&week&employee` |
| GET | `/stars/rollup` | `?period=week\|month&key` (default: the last closed period) |
| GET | `/lessons` | `?company&period` |
- Week = Saturday to Friday, owner TZ; the roll-up runs **Saturday 08:00 Tehran**, the month on the 1st (Jalali month).
- **Company score** ⟨1.4.3⟩ = 35% KPI attainment + 20% overseer challenges + 15% compliance + 15% people (employees' stars) + **15% efficiency**; **company stars** = score ÷ 20.
- **Efficiency** ⟨1.4.3⟩ (owner, 2026-10-17: stars for spending the budget well and reaching the result, without waste), 0–100, computed by the system from the ledger, never self-reported:
  - company: 40% envelope discipline (month use ≤ envelope; above 100% scores 0) + 30% waste (tokens of failed, cancelled or abandoned runs and of work that never delivered, as a share of the month; lower is better) + 30% cost per accepted deliverable against the holding's median;
  - employee: 50% tokens per accepted deliverable against its department's median + 25% failed-run share + 25% estimate accuracy (actual month use within ±25% of its hire estimate scores full);
  - every CEO's rubric carries an **efficiency** criterion of at least 15% weight, scored from these figures; picking a stronger model than the job needs shows up here.
- A star without a reason or evidence is not counted; the overseer flags inflation (e.g. more than 70% fives in a company).
- The owner gives no stars. The owner's 1–10 rating stays a separate part of the employee score (§1.16).

### 18.5 Skills
```
Skill { id, ref: "SK-001", name_fa, summary_fa, body_md, resources: [FileRef], scope: {roles: [role], companies: "all"|[code], departments: [code]},
        version, status: "draft"|"in_review"|"approved"|"active"|"retired",
        review: {by: Actor, at, verdict: "pass"|"changes"|"reject", notes_md, checks: {injection, secrets, conflicts, policy}}|null,
        eval: {suite, score, baseline}|null, created_by: Actor, created_at, activated_at|null }
```
| GET · POST | `/skills` | POST from text, a voice transcript or files; starts as `in_review` |
| GET | `/skills/{ref}` · `/skills/{ref}/versions` | |
| PUT | `/skills/{ref}` | new version → `in_review` |
| POST | `/skills/{ref}/activate` 🔏 · `/retire` | target `ref@version`; only after review `pass` and eval ≥ baseline |
- The runtime puts active skills after the charter in the system prompt; every run records `skills: ["SK-001@3", …]`.

### 18.6 The holding academy
```
Curriculum { role, version, modules: [{key, title_fa, skills: [ref], playbooks: [ref], examples: {good: [O-…], bad: [O-…]}}], updated_at }
EvalSuite  { ref: "EV-001", role, title_fa, cases: [{id, input_md, rubric_md, weight}], baseline: {subject, version, score},
             recent: [EvalRun] }                                                        // ⟨1.4.5⟩ in GET /academy/evals: the last 10 runs, oldest first
EvalRun    { id, suite, subject: {kind: "charter"|"skill"|"model", ref, version}, score: 0..100, passed: bool, cases: [{id, score, notes}], at,
             tokens: {input, output}, equiv_cost_usd }                                  // ⟨1.4.5⟩ what the run cost, for comparing models
Teaching   { id, ref: "TE-0001", target: {kind: "role"|"employee", ref}, source: "voice"|"text", text_md, file_id|null,
             proposal: {kind: "charter_rule"|"skill"|"memory"|"playbook", diff_md}|null, eval_run|null,
             status: "drafting"|"proposed"|"approved"|"rejected", created_at }
TrainingRecord { employee, charter_version, curriculum_version, skills: [ref@version], evals: [{suite, score, at}], lessons: [L-…], trend: [0..100] }
```
| GET | `/academy/curricula` · `/academy/curricula/{role}` | |
| GET | `/academy/evals` · `/academy/evals/{ref}/runs` | ⟨1.4.5⟩ runs are a `Page`, newest first |
| GET | `/academy/runs` | ⟨1.4.5⟩ `?role&suite&subject_kind&subject_ref&latest&cursor` — runs across suites, a `Page`, newest first; `latest=true` keeps only the newest run per (suite, subject). `?subject_kind=model&latest=true` is the model comparison: which model does each suite's work best, and at what cost |
| GET · POST | `/academy/teach` | POST `{target, text, source, file_id?}`; the AI Ops head drafts, the overseer reviews, an eval runs |
| POST | `/academy/teach/{ref}/approve` 🔏 · `/reject` | target = ref |
| GET | `/academy/records/{employee}` | ⟨1.4.5⟩ the employee card's training history: `evals` newest first, `trend` the last 12 eval scores oldest first |
- **Gate:** a new charter, skill or model assignment goes live only when its eval score ≥ baseline − 1; otherwise it is rejected with the report.

### 18.7 Internet and MCP for agents
- **Tools** (agents/tools.md v2): `web.search`, `web.read`, `web.browse` (a real browser: navigate, click, type, download), `http.request`
  (any method to an external host), `mcp.call`. All run in the **egress** service, never in the agent runtime.
- **Egress guard:** loopback, link-local, RFC 1918 (including `10.10.1.0/24` and its production neighbours), cloud metadata, the hub's own
  internal names and `/internal` are blocked; per-run and per-company limits; every request is logged.
- **Credentials** for holding service accounts live in OpenBao and are injected at egress; a model never sees them.
- **A3 on the web:** an external commitment in the holding's name — paying, publishing, messaging a person outside, creating an account, changing an
  account's security — becomes a decision. Research, reading and working in tools is A0–A2.
```
EgressEntry { id, at, company, actor, run_id, tool, method, host, status, bytes_in, bytes_out, ms, blocked_reason|null, class }
McpServer   { id, key, title_fa, transport: "http"|"container", url|image, tools: [{name, class: "A0"|"A1"|"A2"|"A3", enabled}],
              companies: "all"|[code], status: "pending"|"enabled"|"disabled", has_secret: bool, added_at }
ServiceAccount { id, key, site, title_fa, companies: "all"|[code], has_secret: bool, last_used_at|null }
```
| GET | `/egress` · `/egress/summary` | `?company&since&blocked`; `?period=day` |
| GET | `/tools/catalog` | every tool: class, roles, status |
| GET · POST | `/tools/mcp` | POST 🔏 adds a server (body hash) |
| POST | `/tools/mcp/{key}/enable` 🔏 · `/disable` | target = key |
| GET · POST | `/tools/accounts` | metadata only; the owner writes the secret on the server (`make account-secret`), never through the API |

### 18.8 Company founding and server provisioning
```
Founding   { id, ref: "C-0001", name_fa, name_en, code, source: {kind: "repo"|"idea", repo|null, brief_md},
             state: "auditing"|"proposed"|"sealed"|"provisioning"|"ready_for_login"|"active"|"cancelled",
             audit: {session_ref, report_md, scores: {architecture, quality, security, tests, debt}}|null,
             proposal: {departments: [code], kpis: [{name_fa, target}], team: [{role, model, monthly_usd}], roadmap_md, monthly_usd}|null,
             decision_ref|null, plan|null, company|null,
             brand: {state: "missing"|"proposed"|"active", version|null},          // ⟨1.4.6⟩ the step «مُهر شرکت» (§18.14)
             created_at, updated_at }
ServerPlan { id, ref: "PV-0001", founding|null, company, name, type, location, image: "ubuntu-24.04", private_network: bool,
             firewall: [{direction: "in", protocol, port, sources: [cidr], note_fa}], software: [key], work_user, repo|null,
             monthly_eur, digest, state: "proposed"|"sealed"|"running"|"done"|"failed", decision_ref|null, run|null }
             // digest = sha256 of the plan's canonical JSON (sorted keys, no spaces) without digest, state, decision_ref and run
ProvisionRun { id, plan, state: "running"|"done"|"failed",
             steps: [{key, title_fa, state: "pending"|"running"|"done"|"failed", started_at|null, finished_at|null, log_tail}],
             server: {name, ipv4, ipv6, private_ip}|null, login: {ssh, then: [cmd]}|null }
```
| GET · POST | `/foundings` | POST `{source}` opens a read-only workshop audit |
| GET | `/foundings/{ref}` | |
| POST | `/foundings/{ref}/cancel` · `/activate` 🔏 | activate after the owner has logged in on the new server (target = ref) |
| GET | `/provisioning/plans` · `/provisioning/plans/{ref}` | |
| POST | `/provisioning/plans/{ref}/seal` 🔏 | target = the plan's `digest`; the server recomputes it, so any change after the owner saw it voids the seal. The A3 seal that spends money |
| GET | `/provisioning/runs/{id}` · `/provisioning/runs/{id}/live` (SSE) | |
| GET | `/infra/servers` | servers the provisioner made; **no delete** (owner, Hetzner console) |
- **Software keys** (fixed list, reviewed templates): `system-upgrade`, `unattended-upgrades`, `work-user`, `ssh-hardening` (keys only, no root login),
  `docker`, `git`, `node-lts`, `claude-code`, `repo-clone`, `private-network`, `hetzner-firewall`, `node-exporter`.
- No root password is created; the owner's SSH public key is installed. The owner runs `login.ssh`, then `claude` and logs into their own account;
  the provisioner never sees it.

### 18.9 Backups
```
BackupStatus { hourly: {last_at, next_at, ok, snapshot, size_bytes}, wal: {last_archived_at, lag_s},
               destinations: [{key: "gdrive"|"hetzner"|"local", configured, last_ok_at, used_bytes, quota_bytes|null}],
               retention: {hourly, daily, weekly, monthly, yearly}, restore_test: {last_at, ok, duration_s, notes},
               openbao_snapshot: {last_at, ok}, encryption: "restic (AES-256)" }
```
| GET | `/backups/status` · `/backups/snapshots` | owner, overseer, platform SRE |
- Restore never goes through the API: the owner runs it in their own terminal.

### 18.10 Decision kinds, stream types, step-up targets
- **Decision kinds** added: `protocol`, `tool_enable`, `errand_action`, `company_found`, `server_plan`, `lesson_adoption`. ⟨1.4.5⟩ All are sealed with step-up; how, and the one exception (`server_plan`), is in the approve row of §5.1.
- **Stream types** (topics): `oversight.finding`, `oversight.hold`, `oversight.watch` (`oversight`) · `inquiry.answered` (`inquiries`) ·
  `errand.updated` (`errands`) · `stars.rollup` (`stars`) · `skill.updated` (`skills`) · `academy.eval` (`academy`) ·
  `founding.updated`, `provision.step` (`founding`) · `backup.done`, `backup.failed` (`backups`) · ⟨1.4.6⟩ `brand.updated` (`companies`).
- **Step-up targets:** `oversight.protocol` (body hash), `oversight.order` (ref), `oversight.release` (ref), `skill.activate` (`ref@version`),
  `academy.approve` (ref), `mcp.add` (body hash), `mcp.enable` (key),
  `provision.seal` (the plan's `digest`), `founding.activate` (ref), ⟨1.4.5⟩ `account.put` (body hash), ⟨1.4.6⟩ `company.brand` (the brand version's `digest`). ⟨1.5⟩ `revenue.account`, `support.kb`, `support.channel`, `growth.template`, `growth.rule`, `intake.source` (§19.9) · `charter.seal`, `authority.update`, `meetings.settings`, `decision.batch` (§20.11) · `connection.create` (§21.12).

### 18.11 Hiring: the owner opens it, the CEOs hire ⟨1.4.2⟩ ⟨1.4.3⟩
Owner decisions, 2026-10-17: no hire now; hiring opens when the owner brings the hub up for real work. From then on **each company's CEO hires with full authority inside the company's monthly token envelope**: departments ask for the people they need, the CEO decides, and **the CEO chooses the model each job needs** (not every role on Opus). The owner is kept informed through stories (§18.12) and the digest, and can undo any hire. Spending the envelope well, with results and without waste, earns stars (§18.4).
```
Hiring { state: "closed"|"open", mode: "delegated"|"proposals"|null, changed_at|null, changed_by: Actor|null,
         withdrawn: ["D-000001", …],                    // hire cards the system withdrew (never deleted)
         envelopes: [{company, tokens_month|null,         // the company's monthly budget (§9 /budgets, scope company, period month)
                      committed_month,                   // monthly estimates of its active employees (from their hire decisions)
                      used_month,                        // tokens used this (Jalali) month
                      hires_month}] }                    // hires approved this month
```
| Method | Path | Notes |
|---|---|---|
| GET | `/owner/hiring` | the state above; `closed` by default |
| POST | `/owner/hiring/start` 🔏 | `{mode: "delegated"\|"proposals"}` · step-up `hiring.start`, target `holding`. Each operating company's CEO (and each holding head with a hiring duty) gets **one** work item, "build your first month's team", at its normal priority (idempotent). `delegated` needs a monthly envelope for every active operating company: otherwise `422 envelope_required` with `fields: {envelopes: "TY, FX"}`. ⟨1.4.3⟩ |
| POST | `/owner/hiring/close` | no step-up (closing is always safe); pending agent hire cards are withdrawn |
| POST | `/org/hires` 🔏 | owner only, in any state · `{company, department, role, title_fa, title_en?, model?, effort?, reason?, duties?, reports_to?, quota_estimate_month?}` · step-up `hire.direct`, target = SHA-256 of the exact body. Writes a `hire` decision proposed **and sealed by the owner** in one transaction (status `approved`, resolution `M-…`), then the employee; the same checks as §16.6 (the charter `role` must fit the company and department). `model`/`effort`/`title_en` default to the charter's; `reason` defaults to «استخدام مستقیم مالک». → `201 {employee, decision}` |
| GET | `/budgets` · PUT 🔏 | the envelopes are company budgets: `{company, scope_type: "company", scope_ref: <code>, period: "month", token_limit}` (§9, step-up bound to the body hash) |

**Who decides a hire card** — `Decision` gains `approver: Actor|null` (null = the owner) ⟨1.4.3⟩:
| State | An operating company's card | A holding card (HQ) |
|---|---|---|
| `closed` | refused before any card exists: `403 hiring_closed` | same |
| `open`, `proposals` | the owner (as every A2 hire before) | the owner |
| `open`, `delegated` | **its CEO** (`approver` = that CEO); the owner may still decide it first | the owner (the holding has no CEO) |

- **The CEO decides** with the tool `hire.decide` `{ref, verdict: "approve"|"reject"|"return", note}` (A2, own company only, only cards whose `approver` is this CEO; also for the CEO's own proposals). A manager asks by `propose` kind `hire`; the CEO is woken by a work item for the card.
- **Hard checks on every approval** (whoever approves, in one transaction; a refusal is a stable code and no employee is made):
  the charter fits (§16.6) · the model is offered by an enabled connection · `quota_estimate_month` is present and at least the charter's `limits.tokens_per_run` · `committed_month + estimate ≤ tokens_month` else **`409 envelope_exceeded`** · the company's kill switch is released · at most **5 hires per company per day** (a loop guard, `429 rate_limited`).
- **After a delegated hire:** the employee starts at once with `probation_until` = +7 days; a `hire` story is posted (§18.12); the owner gets one `report`-level notification in the digest (never an urgent push); the Chief Overseer gets a review item (protocol "hire review", 24 h) and may hold it or open a finding.
- **The owner undoes** a hire from its story or the employee page: `POST /employees/{code}/dismiss` 🔏 (§4) with reason «مالک: از استوری».
- `GET /decisions` for the owner's cartable shows by default only cards the owner decides (`approver` null); `?approver=all` shows the CEOs' too. `/inbox/summary.decisions_pending` counts the owner's only.
- While `closed`, an agent's `propose` of kind `hire` is refused: `403 hiring_closed` (§14). Dismissal, budget and every other kind are unaffected.
- Closing hiring (and the decision itself, 2026-10-17) **withdraws** pending agent hire cards: status `withdrawn`, `decided_by` system, note «مالک: استخدام با شروع خود مالک».
- The daily agent token cap stays at 600K until the owner sets it from the first week's outputs (owner decision, 2026-10-17).
- Stream: `hiring.changed` on topic `control`. Step-up targets: `hiring.start` (`holding`), `hire.direct` (body hash).
- **As built in prompt 5.1** ⟨1.4.3⟩: `start` and `/org/hires` without a step-up answer `403 step_up_required` (no session: 401; an agent token on the owner API: 403). A withdrawn card's `decided_by` is `{kind: "service", code: "system"}`. `start` answers the `Hiring` plus `work: [ref…]` (the items it created). The `hire` payload accepts an optional `reports_to`. Agent tool results may carry `hint_fa` (a Persian hint for the model, e.g. after `hiring_closed`). Gateway codes `api_bad_answer`, `repo_not_allowed`, `body_too_large`. A refused site URL is `422` with `fields: {"sites.N.url": …}`. A body over the API's size is `413 validation_failed` (API-wide). Still to land (review of 5.1): the `delegated` enum with `409 not_ready`, `envelopes`, `approver`, `probation_until`.

### 18.12 Stories ⟨1.4.3⟩
Owner decision, 2026-10-17: the owner follows the companies the way one follows accounts on Instagram — a row of circles at the top of «فرمان», one per company, ringed in gold while something is unseen. A story is a designed card in the company's colours (no generated imagery): the system posts one for each notable event, and each CEO may post up to three a day in its own words. Stories are pulled, never pushed.
```
Story     { id, ref: "ST-000123", company, kind: "hire"|"deliverable"|"stars"|"milestone"|"post",
            author: Actor,                                  // system, or the company's CEO
            title_fa (≤ 60), body_fa (≤ 280), figures: [{label_fa, value}] (≤ 3; value is a short figure: "1.6M", "$4.20", "86"),
            media: MediaRef|null,                           // an image from the company's own files (§17), images only
            links: {employee?, deliverable?, decision?, work?, period?},
            created_at, expires_at (= created_at + 24 h), seen: bool, welcomed: bool }
StoryRing { company, unseen, latest_at, items: [Story] }    // items oldest first, as they play
```
| Method | Path | Notes |
|---|---|---|
| GET | `/stories` | live stories (not expired), one ring per company with any; rings with unseen first, then by `latest_at` |
| GET | `/stories/archive` | `?company&cursor` — expired stories, newest first (the company's highlights) |
| POST | `/stories/seen` | `{refs: ["ST-…"]}` → marks them seen; no step-up |
| POST | `/stories/{ref}/welcome` | a `hire` story only: the owner's welcome; the new employee's manager and CEO see it (a positive signal in the employee score); no step-up |
- **System stories:** `hire` (every approved hire, with role, model, effort and monthly estimate as figures, and the CEO's reason as the body); `deliverable` (a deliverable the owner rated 9–10); `stars` (Saturday's roll-up: the best company and its best employee); `milestone` (a KPI target reached, with the figure).
- **CEO stories:** the tool `story.post` `{kind: "post"|"milestone", title_fa, body_fa, figures?, file_id?, links?}` (A1; CEOs and holding heads): at most **3 per company per day** (`429 story_limit`), redacted like every agent output, an image only from the company's own files, no outside links; a `milestone` must link the evidence (work, deliverable or metric).
- The owner never gets a push for a story; a `hire` story also appears in the digest (above).
- Stream: `story.created` on topic `stories`.

### 18.13 As built in prompt 7 ⟨1.4.5⟩
**Backups (§18.9).** `BackupStatus` as served:
```
BackupStatus { hourly: {last_at, last_ok_at, next_at, ok, error|null, stale: bool, snapshot, size_bytes},
               wal: {last_archived_at, lag_s, failed_count, failing: bool, ready_count},          // failing, ready_count: 7.1
               base_backup: {last_at, count}|null, check: {last_at, ok}|null,
               destinations: [{key, configured, ok|null, error|null, last_ok_at, used_bytes, quota_bytes|null}],
               retention, restore_test: {last_at, ok, duration_s, notes, pitr_target|null, source|null},
               openbao_snapshot: {configured, last_at, ok}, encryption }
Snapshot     { id, time, destination: "local"|"gdrive"|"hetzner", size_bytes|null, tags }
```
- `GET /backups/snapshots` is a `Page` (`?destination&limit&cursor`).
- **WAL archiving that fails is a data-loss alarm, not a statistic:** `wal.failing` is true when the last failure is newer than the last success,
  or more than 5 segments wait (`ready_count`). Then `hourly.ok` is false and the owner gets an urgent alert at once (7.1).

**Internet (§18.7).**
```
EgressEntry    { …§18.7, kind: "request"|"connect"|"search"|"browse" }
EgressDay      { company, day, requests, blocked, bytes, browser_s, hosts }       // GET /egress/summary?period=day|week|month
ServiceAccount { id, key, site, title_fa, companies, has_secret, last_used_at|null,
                 policy: { inject: {kind: "bearer"|"header"|"basic"|"cookie", name?, username?},
                           browse: {kind: "cookie"|"header"|"form", name?, login_url?, username?, user_selector?, pass_selector?, submit_selector?}|null,
                           allow: [{methods: ["POST"|"PUT"|"PATCH"|"DELETE"|"OPTIONS"], path_prefix, note_fa?}],   // the non-committing calls
                           ports: [int] } }                                  // extra ports, for the account's own site only (7.1)
```
- `POST /tools/accounts` adds or changes an account by `key`. **🔏 `account.put`, target = sha256 of the body** (7.1): a new site, allow rule or
  port widens what a stored secret can do, so it is a seal like `mcp.add`. Takes `Idempotency-Key`.
- `web.browse` is capped at 15 s per call. The data guard refuses every e-mail address and phone number in an outgoing query (safe default),
  after decoding (percent-encoding, full-width forms, Persian digits; 7.1).
- An agent's internet call that is refused for policy is a step with `outcome: "denied"` and one of the four codes of §14.

**MCP (§18.7).**
```
McpServer { …§18.7, status_reason|null, auth_header|null, listed_tools: [{name, description}]|null, listed_at|null, enabled_at|null, version }
CatalogTool { name, source: "internal"|"web"|"mcp", server|null, class, per_call: bool, roles, status: "live"|"off"|"channel_not_configured"|"pending",
              description, input }
```
- **Step outcomes** of `mcp.call` (in `Step.actions[].ref`, never Problem codes): `mcp_tools_changed` (the server's listing no longer matches the
  sealed one; the server is switched off), `mcp_tool_missing`, `mcp_unreachable`, `mcp_tool_error`, `a3_requires_decision` (an A3 tool became a card).
- **A3 tool → card:** the `a3_action` card's payload gains `action: "mcp_call"`, `server`, `tool`, `args_sha256` and the arguments **with secrets
  masked but recipients and amounts shown** (the owner must see what they approve). **Approving runs the call exactly once** (7.1): the follow-up
  run's identical call (same company, server, tool, `args_sha256` and registration) consumes the approved card; a changed argument needs a new
  card; a rejected card answers `denied` with no new card.
- **A changed listing** switches the server off and raises a `tool_enable` decision card (§18.10) with `{key, listing_sha256, diff: {added, removed,
  changed}}`. Approving it is the usual 🔏 decision seal (`decision.approve`, target = ref) and re-enables the server with **exactly that listing**;
  a listing that changes again before the seal supersedes the card (`409 decision_not_pending`) and a new card comes.
- The three MCP POSTs take `Idempotency-Key` (§1).
- **Agents' files:** `GET /internal/v1/files/{id}/meta` adds `agent` (the variant id for vision) and `text` (a PDF's extracted text, or null).

### 18.14 The company's brand and seal ⟨1.4.6⟩
> Owner, 2026-10-19: once a company is fully defined, the owner gives its **PNG logo** and the company's **seal** is made from it. Companies are
> data: the mark and seal of every company, new or old, come from its record, never from a client build. The seal's geometry is
> `design/brand/SEAL.md`; the holding's own seal is fixed and is not data.
```
CompanyBrand { company, version, state: "processing"|"proposed"|"active"|"failed"|"retired",
               source: {kind: "upload"|"seed", file_id|null, path|null, sha256, width, height, has_alpha},
               mark: {vb, layers: [{role: "ink"|"accent", color, d}]},             // the shape the clients already draw (CompanyMark)
               wordmark: {vb, layers: [{role, color, d}]}|null,
               ink, accent|null,                                                   // hex; accent = the company's signature colour; null = a one-colour mark
               accent_night|null, accent_day|null,                                 // set only when the accent fails 3:1 on that theme's page surface
               palette: [{hex, share}],                                            // ≤ 6, by area, for briefs and stories
               options: {colors: 1..4, detail: 1..5},
               checks: {paths_bytes, min_feature_px_16, iou, contrast_night|null, contrast_day|null, warnings: [string]},
               digest,                                                             // sha256 of the canonical JSON of mark, wordmark, ink, accent, accent_night, accent_day
               status_reason|null, created_at, activated_at|null }
Brands       { etag, companies: {CODE: {version, mark, wordmark|null, ink, accent|null, accent_night|null, accent_day|null}} }   // active versions only
```
| Method | Path | Notes |
|---|---|---|
| POST | `/companies/{code}/brand` | owner · `{file_id, part: "mark"\|"wordmark", options?}` → `202 CompanyBrand` (`processing`) · a new version that carries the other part over from the active one · `Idempotency-Key` |
| GET | `/companies/{code}/brand` | the active version and, if any, the newest `proposed` one · `/brand/versions` lists all |
| POST | `/companies/{code}/brand/{version}/retrace` | `{options}` → a new `processing` version from the same file |
| POST | `/companies/{code}/brand/{version}/activate` 🔏 | `company.brand`, target = the version's `digest`; the server recomputes it. The previous active version becomes `retired` |
| GET | `/brands` | every active brand in one response, `ETag` (clients cache it; `304` when unchanged). Every brand route is the owner's; an agent token → 403 |
- `Company` gains `brand_version: int|null` (§3.1). The clients draw a company's mark and seal from `/brands`, then from their built-in marks,
  then from the code.
- **Processing is code, no model,** in the sandboxed media worker of §17.1 (no network, memory and time limits, the decompression-bomb guard):
  1. **Input:** PNG (best with transparency); WebP and JPEG are accepted with the warning «بدون شفافیت». At most 4096 × 4096 px.
  2. **Background:** transparent pixels; with no alpha, the colour of the four corners when they agree (ΔE ≤ 5); otherwise `failed`
     `no_background` («لوگو را با زمینه‌ی شفاف یا یکدست بدهید»).
  3. **Trim** to the content with 4% padding.
  4. **Colours:** the foreground is quantised in OKLab into `options.colors` (default: as many as the logo has, at most 4); anti-aliased edges do
     not vote. The largest low-chroma cluster is `ink`; the others are `accent` layers with their own colour. One colour → a single `ink` layer
     and `accent: null`.
  5. **Trace** each layer to paths with **VTracer** (MIT), `detail` 1–5 setting speckle filter and corner threshold; holes are even-odd.
  6. **Budget:** all `d` together ≤ 48 KB. Over it → lower detail automatically down to 1; still over → `failed` `too_complex`.
  7. **Only our own paths are kept:** every `d` must match the SVG path grammar; nothing else of any uploaded markup exists in the output.
  8. **Checks:** the trace is rasterised again and compared with the original mask (`iou`; below 0.9 → warning); the thinnest feature at 16 px
     (`min_feature_px_16`; below 1 → warning «در اندازه‌ی کوچک جزئیات گم میشود»); the accent's contrast on both themes' page surfaces; below 3:1
     → the nearest passing lightness in OKLCH (hue and chroma kept) becomes `accent_night` or `accent_day`, with a warning.
  9. → `proposed`, stream `brand.updated`.
- **The owner looks before sealing:** the app shows the original beside the trace, the mark at 16, 24, 48 and 160 px, the seal in `ready` and
  `sealed`, at night and by day, and the warnings; the owner retraces with other options or activates.
- **Founding** (§18.8): the company exists once `company_found` is sealed; the founding then shows the step «مُهر شرکت». `Founding` gains
  `brand: {state: "missing"|"proposed"|"active", version|null}`. `POST /foundings/{ref}/activate` without an active brand → `409 not_ready`
  with `missing: ["brand"]`, unless the body says `{skip_brand: true}` (the company then shows its code until a brand is sealed).
- **Existing companies:** the server seeds an `active` version 1 for each folder in `design/brand/companies/<code>/` from its flat SVGs
  (`*-mark-flat.svg`, `*-wordmark*-flat.svg`; layers by `--logo-ink` / `--logo-accent`), `source.kind: "seed"`. A new upload replaces it like
  any version.
- Stream: `brand.updated` on topic `companies`. Step-up target: `company.brand` (digest).

### 18.15 As built in prompt 8 ⟨1.4.7⟩
Recorded from the server's report and the review of `server/p08-organisation` (2026-10-22); the fixes are `docs/server-prompts/PROMPT_08_1_FIXES.md`.
Where the build differs from §18.0–18.6 and §18.11–18.12, this list is the contract.
- **Holds.** `Hold.target.kind`: `decision`, `session`, `work`, `employee`, `tool`, `story`. A held target answers `423 held` (new stable
  code). **`release`** 🔏 lets the action go on; **`cancel`** (no step-up) **cancels the action itself**: a pending card is rejected (by the
  owner, note «لغو از hold»), a queued effect is cancelled, a workshop session is stopped, a work item is cancelled. Nothing held ever runs
  after a cancel. A hold on a running workshop session interrupts it at once; a release resumes it.
- **Kill switch.** An engage by the overseer, like the owner's, takes the switch over; only the owner releases a switch the owner or the
  overseer engaged. A CEO releases only a switch it engaged itself and nobody took over.
- **Protocol runs.** `last_run.result`: `pass`, `fail`, `partial`, `deferred` — never `skipped`. The oversight token share
  (`OVERSIGHT_DAILY_SHARE`, §18.1) is enforced on the ledger; once spent only `critical` protocols run and the rest are `deferred` and run
  first the next day. A count cap on model runs (`HQ_OVERSIGHT_MODEL_RUNS_PER_DAY`) may exist on top but never stops a `critical` protocol.
  A `paused` protocol has no schedule at all and every path refuses it: `protocol.result`, `finding.raise`, and the event-driven checks.
- **Findings.** Only the answerable (or its chain of command) sets `acknowledged`, `fixing`, `fixed`, `disputed`; the overseer sets
  `verified` only after a `fixed` that carried evidence, and `closed`.
- **Hiring.** `hire.decide` works only while hiring is `open` in mode `delegated`; switching to `proposals` clears `approver` on pending
  cards (they return to the owner's cartable). The envelope check and the five-a-day guard run under a per-company lock, and
  `committed_month` counts approved hires whose employee is active **or not created yet**. The estimate is `payload.quota_estimate_month`
  only. A hire the owner approved first is the owner's (no probation line «… استخدام کرد»).
- **Watch mode** holds cards a CEO decides as well; a target the owner released or decided during the same watch period is not held again;
  release and cancel count as owner activity.
- **Skills.** `POST /skills` `{name_fa, summary_fa?, body_md, scope: {roles: [role], companies: "all"|[code], departments?: [code]},
  file_ids?}` (`summary_fa` defaults to the first 200 characters of `body_md`). `name_fa`, `summary_fa` and `scope` belong to a **version**;
  a `PUT` makes a new version and the active one stays in every prompt until the new one is activated. `Skill.resources: [FileRef]`.
  `Skill.eval: {suite, score, baseline|null}|null`. A review shows the reviewer the exact masked text fenced as data, records its sha256, and
  a `pass` needs all four checks true and the same sha. `Run` gains `skills: ["SK-001@3"]` and `addenda: [id]` — what was really in the
  prompt.
- **Academy.**
  ```
  EvalSuite { …§18.6, baseline: {subject: {kind, ref, version}, score}|null, recent: [EvalRun] }
  EvalRun   { id, suite, subject: {kind, ref, version}, state: "queued"|"running"|"done"|"failed",
              score: 0..100|null, passed: bool|null, cases: [{id, score, notes}], at, tokens: {input, output}, equiv_cost_usd }
  Teaching  { …§18.6, eval_run: {id, score, baseline|null, passed}|null }
  ```
  A run in which any model call failed is `failed`, never a pass. A suite's first successful run sets its baseline but is not itself a pass
  for activation. Activation checks the eval against the baseline as it is at that moment. The monthly academy cap reserves an estimate for
  queued and running runs (`409 academy_budget`). A teaching aimed at one employee becomes an addendum for that employee only; an addendum can
  be retired (`POST /academy/addenda/{id}/retire` 🔏 `academy.approve`, target = its teaching ref). `GET /academy/runs` as in §18.6.
- **Stories.** `links.period` matches `^(week|month):…$`; a link to outside the hub, with or without `http`, is refused; a `milestone`
  links work, a deliverable or a metric. The owner's welcome is a small positive part of the employee score.
- **Stars.** Rubric weights are numbers. Stars are whole or half (`0, 0.5, … 5`); anything else is `422 validation_failed` with the field.
- **Decisions.** `protocol` and `errand_action` are valid in `GET /decisions?kind=`; `lesson_adoption` is sealed with step-up (§18.10); a
  returned or expired `lesson_adoption` card frees the lesson to be proposed again.
- **Other contract notes from the build:** planner items `PL-…`; stream types `inquiry.late` (`inquiries`) and `academy.teaching`
  (`academy`); `academy_budget` (409) and `held` (423) join §14; an approved `charter_rule` is an addendum row on the server, never a change
  to `agents/`.

### 18.16 As built in prompt 9 ⟨1.4.8⟩
Recorded from the server's report and the review of `server/p09-founding` (2026-10-22); the fixes are `docs/server-prompts/PROMPT_09_2_FIXES.md`.
Where the build differs from §18.8, this list is the contract.
```
Founding   { …§18.8, name_fa|null, name_en|null, code|null,                      // null until the proposal
             source: {kind: "repo"|"idea", repo|null, brief_md},
             audit: {session_ref|null, report_md, scores: {architecture|null, quality|null, security|null, tests|null, debt|null}}|null,   // each 0..10
             plan: "PV-…"|null, plan_detail: ServerPlan|null, brand: {state, version|null} }
ServerPlan { …§18.8, firewall: [{direction: "in", protocol, port|null, sources, note_fa}],     // port null for icmp
             monthly_eur: decimal string|null,                                        // null until Hetzner's price is known; no price, no seal
             price: {server, ipv4, network, source, at}|null, problems: [string], sealed_at|null, version }
ProvisionRun { …§18.8, state: "queued"|"running"|"done"|"failed",
             steps: [{key, title_fa, state, started_at|null, finished_at|null, log_tail: [string]}],
             server: {name, ipv4|null, ipv6|null, private_ip|null, host_keys: [{type, fingerprint_sha256}]}|null }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/foundings` | a `Page`, newest first |
| POST | `/provisioning/runs/{id}/resume` | owner · a `failed` run of a still-sealed plan continues from its failed step on the same seal |
- **Money** stays a decimal string (§1): `proposal.monthly_usd`, `team[].monthly_usd`, `monthly_eur`.
- **Cancel closes everything:** cancelling a founding withdraws its pending `company_found` and `server_plan` cards, returns a sealed but
  unrun plan to `proposed`, cancels its audit and proposal work and stops its workshop session. Nothing of a cancelled founding is ever
  sealed, created or built. A failed run returns the founding to `sealed` (resume or cancel).
- **SSH is never open to the world:** any tcp range that contains 22 is SSH, and its sources must lie inside
  `owner_settings.provision_ssh_sources`; a source set that covers the whole address space is refused except on 80 and 443 (ICMP to the
  whole internet is refused too).
- **`price.network`** is `"0.00"` while the private network is free at Hetzner; it stays in the shape so a priced network needs no change.
- **The reaper** fails a run that stopped answering: its error code is `callback_timeout` when the server never called back from cloud-init,
  otherwise `error`.
- **The work user** is created by the build and never reuses an existing account; a name of Ubuntu's base system is refused; the default is
  `<code>-ops`. `ssh-hardening`, `unattended-upgrades` and `work-user` are always in a plan.
- **A step fails when any command in it fails**; a failed step stops the run and is resumable.
- **Plans of a founding** are written only by holding roles; a company's CTO writes plans for its own company only.
- The owner sees the new server's host-key fingerprints before the first login.
- Codes as served: `seal_mismatch`, `plan_invalid`, `price_unknown`, `not_configured` (Problem codes; statuses in the OpenAPI);
  `refused`, `server_gone`, `callback_timeout`, `verify_failed` (run and step outcomes, never Problem codes).
- The provisioner is the opt-in compose profile `provisioning`; `HQ_PROVISIONING` stays off until the owner has given the Hetzner token,
  the SSH public keys and the SSH sources.

## 19. v1.5 — revenue and support (prompt 10)

> **v1.5 (2026-10-18).** The holding's money comes from exchange referral commission (VIP is free for users who sign up with our referral and
> keep a minimum balance). This section makes that money visible every day and protects it: the revenue radar, the funnel, referral rescue, a
> support desk the owner teaches, lifecycle messages, NPS, a feedback inbox and one anti-fraud rule over every word sent to a customer.
> Everything above still holds. **Rules first, AI last:** pulls, triggers, checks and limits are code; a model writes only what a rule cannot.

### 19.0 Principles ⟨1.5⟩
- **Nothing the AI writes reaches a customer unchecked.** Every outbound message (support, rescue, lifecycle, NPS, the owner's own reply) passes
  the **outbound guard** (§19.6) in code; a message it refuses is never sent and is stored as `blocked` with its reasons.
- **Referral codes, referral links and official links come only from approved knowledge** (`KbArticle.kind` `referral` / `official_link`).
  The guard refuses any referral-looking code or any link that is not an exact approved one. A model never makes one up.
- **Support never asks for** a password, a private key, a seed phrase, a 2FA/SMS code, an API secret or a card number, and **never promises profit**.
- **Auto-send** (OPERATING_MODEL §1.12 exception) covers only answers built from **approved** articles of the conversation's company, on a channel
  the owner put `live`, after the **shadow test** passed (§19.4). Anything else goes to the owner's teaching queue.
- **Rule-sent messages** (rescue follow-ups, lifecycle, NPS) use a **sealed template** under a **sealed rule** with limits; sealing the rule is the
  owner's A3 approval in advance. Free-text outbound by an agent does not exist.
- **Customer data stays in its company** (RLS) and is masked everywhere but the support screens of the owner and that company's support roles.
  Analytics use a keyed pseudonym (HMAC, key in OpenBao), never the handle or the exchange UID.
- **No fixed number of companies, channels or exchanges** anywhere: each is data.

### 19.1 Revenue radar (G1)
```
RevenueAccount { id, company, exchange: "lbank"|…, adapter: "lbank-affiliate-v2"|…, service_account: key,   // a §18.13 service account
                 title_fa, status: "not_configured"|"ok"|"error", last_pull_at|null, last_error|null, version }
RevenueDay     { company, account, day,                                   // the exchange's settlement day (lbank: T+1, UTC+8)
                 commission_usdt, by_coin: [{coin, amount, usdt, price_source}], fees_usdt|null, volume_usdt|null,
                 new_invitees, active_traders|null, deposits_usdt|null,
                 complete: bool, pulled_at, source: {adapter, endpoints: [path]} }
RevenueSummary { period: "day"|"week"|"month", from, to, total_usdt, prev_total_usdt|null,
                 by_company: [{company, usdt, token_cost_usd, net_usd, share}],
                 by_account: [{account, company, usdt}], trend: [{day, usdt}],
                 alerts: [{kind: "drop"|"pull_failed"|"incomplete", company, account|null, note_fa}] }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/revenue/summary` | `?period=day\|week\|month&company` — owner, CEOs (own company), advisor, overseer, FIN and SALES managers |
| GET | `/revenue/days` | `?company&account&from&to` — unpaged, ≤ 400 rows |
| GET · POST | `/revenue/accounts` | POST 🔏 `revenue.account` (body hash) adds or changes one by `exchange` + `company`; the secret is never in the API (`make account-secret`) |
| POST | `/revenue/accounts/{id}/pull` | owner: pull now (`?from&to`, ≤ 31 days), rate-limited like the schedule · `Idempotency-Key` (required) |
- The pull is **code** (a worker schedule after the exchange's settlement time), through egress with the account's signed connector; the key never
  leaves egress.
- **Signed requests** ⟨1.5⟩: §18.13 `ServiceAccount.policy.inject.kind` gains `"signer"` with `signer: "lbank-v2"` (a fixed list in code, never user
  input). An account with a signer is refused for `http.request` and `web.browse` (`policy_denied`) and is used only by
  `POST /internal/v1/egress/connectors/{adapter}/pull` (worker only); `referral.check` goes through the same connector, never through an agent's request. A day is `complete` only when every page of every endpoint answered. `token_cost_usd` comes from the Token Treasury, never from an agent.
- Alerts (one per incident, `report` level, to the company's CEO and the owner's digest): commission below 60% of the trailing 28-day median of the same
  weekday; a pull that failed twice in a row; a day still incomplete after 36 h.

### 19.2 Funnel and referral rescue (G2, G3)
```
Funnel     { company, period: "week"|"month", from, to,
             stages: [{key: "visit"|"signup"|"referral_verified"|"min_balance"|"vip_active", label_fa,
                       count|null, connected: bool, source: "affiliate"|"product_events"|"support"|"analytics"|null}],
             conversions: [{from, to, rate|null}], leaks: [{stage, note_fa, rate, median_rate}] }
RescueCase { id, ref: "RC-000123", company, source: "support"|"product", conversation|null, exchange,
             subject: pseudonym, state: "open"|"contacted"|"rescued"|"lost"|"opted_out",
             steps: [{at, kind: "check"|"message"|"follow_up"|"note", template|null, result_fa}],
             opened_at, rescued_at|null, closed_at|null }
```
| GET | `/growth/funnel` | `?company&period` — a stage with no source is `connected: false, count: null`; a rate is never estimated |
| GET | `/growth/rescue` · `/growth/rescue/{ref}` | `?company&state&cursor` — the rescue rate is `rescued / (rescued + lost)` per period |
- `referral_verified` and `min_balance` come from the affiliate data (§19.1); `signup` and `vip_active` from product events (§19.8), until then
  `connected: false`. The **minimum balance** is the company's approved knowledge (`KbArticle` kind `policy`, key `vip.min_balance`), one number.
- A rescue case opens when a UID check says "not our invitee" (support) or a product sends `referral_failed`; follow-ups run under a sealed
  `rescue` rule (§19.5); a later check that says "our invitee" closes it `rescued`.

### 19.3 Support desk (G22, G23, item 25)
```
SupportChannel { company, kind: "telegram_business"|"telegram_bot"|"chatwoot"|"product_bot"|"mystery",
                 state: "not_configured"|"shadow"|"live"|"paused", live_since|null, paused_reason|null,
                 auto_send: "kb_verbatim"|"kb_grounded"|"off",                   // what may leave without the owner
                 version }                                                       // ⟨1.5.1⟩ for If-Match; "already went live" = live_since != null
Conversation   { id, ref: "SC-000123", company, channel, customer: {display_name|null, handle_masked, lang},
                 state: "open"|"waiting_owner"|"answered"|"closed", opened_at, last_message_at,
                 handoff: {reason: "no_kb"|"low_confidence"|"blocked"|"asked_for_human"|"complaint"|"security", at}|null,
                 tags: [string], rescue|null, csat: 1..5|null, mystery: bool }
SupportMessage { id, conversation, at, direction: "in"|"out", author: "customer"|"agent"|"owner"|"rule",
                 body,                                                       // masked: secrets, cards, seed phrases never stored raw
                 status: "draft"|"queued"|"sent"|"blocked"|"failed",
                 kb_refs: ["KB-0042@3"], confidence: 0..1|null,
                 checks: {guard: "pass"|"fail", grounded: "pass"|"fail"|null}, blocked_reasons: [code] }
QueueItem      { conversation, kind: "handoff"|"low_confidence"|"blocked"|"shadow_disagreement", since, draft|null, company }
```
| GET | `/support/channels` | `?company` |
| POST | `/support/channels/{company}/{kind}/pause` | owner, no step-up (stopping is always safe). Going live the first time is a `support_go_live` decision (§19.9) |
| PATCH | `/support/channels/{company}/{kind}` | owner, `If-Match` · `{auto_send?, state?: "live"}`. Widening (to `kb_grounded`, or a paused channel that already went live back to `live`) is 🔏 `support.channel`, target = `company/kind@auto_send`; narrowing (`kb_verbatim`, `off`) needs none. A channel that never went live → `409 shadow_not_passed` |
| GET | `/support/conversations` | `?company&state&channel&q&cursor` |
| GET | `/support/conversations/{ref}` | with messages, oldest first |
| POST | `/support/conversations/{ref}/reply` | owner: `{body}` → sent as the owner, through the outbound guard; `422 send_blocked` with reasons · `Idempotency-Key` (required) |
| POST | `/support/conversations/{ref}/teach` | owner: `{message_id?, answer_md, generalise: bool}` → sends the answer (if the conversation waits) and opens a `KbArticle` proposal from it → `{message: SupportMessage\|null, article: KbArticle}` · `Idempotency-Key` (required) |
| POST | `/support/conversations/{ref}/close` | owner or support lead |
| GET | `/support/queue` | the teaching queue: what waits for the owner, oldest first |
- **Answering:** a customer message first meets the **rules**: an exact or near-exact match (Persian-normalised full-text, score above the company's
  threshold) to one approved `faq` article answers **verbatim** with no model. Otherwise the company's support agent drafts from approved articles
  only, citing them; code checks every link, code, number and figure in the draft against the cited articles (`grounded`), then the guard.
  `auto_send` decides what leaves alone: `kb_verbatim` (default after go-live) = verbatim answers only; `kb_grounded` = also drafts that pass both
  checks with confidence ≥ the company's threshold (the owner turns it on per channel with the `PATCH` above); `off` = everything waits.
- **Draft budget:** the model drafts of one company use at most `SUPPORT_DRAFT_DAILY_TOKENS` a day (default 60 000; the router enforces it as the
  scope `support_draft:<company>`). When it is spent, the rest of that day's messages are handed off without a model call (`low_confidence`).
- **Handoff:** no article, low confidence, a refusal, a complaint, a security report or "I want a human" → the conversation waits for the owner,
  the customer gets the sealed `holding_reply` template, and the owner's digest gets one line (batched every 30 min; `urgent` only for a
  `security` handoff such as an impersonation report, within the urgent limit).
- **Teaching (حالت آموزش):** whatever the owner answers or corrects becomes a `KbArticle` proposal written by the support lead (generalised,
  variables marked, no customer data), approved by the owner (§19.4). The owner's answer is sent at once; the article helps the next customer.

### 19.4 Knowledge base, shadow test, go-live
```
KbArticle   { id, ref: "KB-0042", company, version, kind: "faq"|"policy"|"procedure"|"referral"|"official_link"|"safety",
              key|null,                                       // policy keys, e.g. "vip.min_balance"
              question_fa, variants: [string], answer_md, variables: [{name, source: "customer"|"policy"}],
              links: [{url, label_fa}], codes: [{exchange, code}],            // referral / official_link only
              status: "proposed"|"approved"|"expired"|"retired", source: {kind: "owner_answer"|"owner"|"doc"|"agent", ref},
              approved_at|null, expires_at, uses_30d, sha256 }
ShadowReport { company, suite: "support-shadow-<company>@<version>", run_id, at, total, correct, partial, wrong,
               safety_failures, wrong_codes, pass: bool, threshold: 0.9, disagreements: [{case, verdict, note_fa}] }
```
| GET | `/support/kb` | `?company&kind&status&q` |
| POST | `/support/kb` | owner or agent proposal `{company, kind, question_fa, answer_md, …}` → `proposed` (a new version of `ref` when given) |
| POST | `/support/kb/{ref}/approve` 🔏 | target `support.kb` = `ref@version`; an approved article changes what may be sent without the owner |
| POST | `/support/kb/{ref}/retire` | owner; also automatic at `expires_at` (default 180 days; the support lead is reminded 14 days before) |
| POST | `/support/history` | owner: `{company, file_id}` — a chat export (Telegram Desktop JSON or a CSV of question and answer) → builds the private shadow suite |
| GET | `/support/shadow` · POST `/support/shadow/{company}/run` | the latest report; run = an academy eval run of the support charter on the suite (§18.6) |
- The suite holds up to 100 real past questions with the owner's real answers as truth, masked, stratified by topic; it never leaves the company.
- **Pass** = correct ≥ 90% **and** zero safety failures **and** zero wrong codes or links. Only then can a `support_go_live` card exist for that
  company; otherwise `409 shadow_not_passed`. Telegram Business additionally needs the owner's Premium account connected (Business → Chatbots).

### 19.5 Templates, lifecycle rules, NPS (G24, G25)
```
Template      { id, ref: "TM-0007", company, version, purpose: "welcome"|"reactivation"|"rescue"|"nps"|"holding_reply"|"safety"|"csat",
                body_fa, variables: [name], status: "proposed"|"sealed"|"retired", sealed_at|null, sha256 }
LifecycleRule { id, ref: "LR-0003", company, version, kind: "welcome"|"reactivation"|"rescue"|"nps"|"csat",
                trigger: {event?: "signup"|"referral_failed"|"conversation_closed", after_hours?, inactive_days?, rrule?},
                template: "TM-0007@2", channel: kind,
                limits: {per_customer_days, daily_cap, quiet_hours: ["22:00", "09:00"], max_follow_ups},
                status: "proposed"|"active"|"paused", decision_ref|null, sent_30d, opt_outs_30d }
NpsWave       { ref: "NP-2026Q4-TY", company, quarter, sample: int, sent, responses, score: -100..100|null,
                promoters, passives, detractors, opens_at, closes_at, comments_to_feedback: int }
```
| GET | `/growth/templates` · `/growth/rules` · `/growth/nps` | `?company` |
| POST | `/growth/templates` | propose; the owner may seal directly: `POST /growth/templates/{ref}/seal` 🔏 `growth.template` = `ref@version:sha256` of the body |
| POST | `/growth/rules` | owner: a new rule (or a new version of `ref`) → `proposed`; no agent is needed |
| POST | `/growth/rules/{ref}/seal` 🔏 | owner: `growth.rule` = `ref@version` → `active`; its template version must be sealed, else `409 template_not_sealed` |
| POST | `/growth/rules/{ref}/pause` · `/resume` 🔏 | pausing needs nothing; resuming `growth.rule` = `ref@version` |
- An agent proposes a template or a rule with `propose` → decision `message_template` / `lifecycle_rule` (§19.9). A rule runs only while its
  template version is sealed; a new template version pauses the rule until it is sealed too.
- **Opt-out:** «لغو»، «stop»، «نمیخواهم» and their variants stop every rule for that customer in that company for good (`opted_out`).
- **Telegram's own rules** (a bot writes only to people who wrote first; business-chat limits) are checked in code; a message Telegram would not
  allow is recorded `no_channel`, never forced.
- **NPS** is one rule of kind `nps` (quarterly, a random sample of customers with a conversation in the last 90 days); answers 0–10 with an
  optional comment; comments go to the feedback inbox.

### 19.6 The outbound guard (G26)
Code, not a model, over every outbound message of every channel (also the owner's own reply and the mystery channel). Refusal codes:
`asks_secret` (password, private key, seed phrase, 2FA/SMS code, API secret, card number — Persian and English patterns), `unknown_link` (a URL not
in the company's approved `official_link`/`referral` articles), `unknown_code` (a referral-looking code not exactly approved), `profit_promise`
(«سود تضمینی»، «بدون ضرر»، «حتماً سود» …), `customer_data` (another customer's handle, UID or contact), `internal_data` (§18.13), `too_long`,
`red_line` (a `rule` red line of the sealed charter, §20.2; the message is held for review, never sent).
- The **safety line** (a sealed `safety` template: «پشتیبانی ما هرگز رمز، کلید خصوصی، کد تأیید یا عبارت بازیابی شما را نمیخواهد…») is added to
  the first answer of every conversation and to every lifecycle message.
- **Inbound:** a customer message holding a secret (seed phrase, private key, card) is masked before it is stored or shown to a model, and the
  customer gets the safety line once. An impersonation report is a `security` handoff.
- The owner may edit and resend a blocked message; the guard runs again. There is no override for `asks_secret`, `profit_promise` or `red_line`.

### 19.7 Feedback inbox (G15)
```
FeedbackItem { id, ref: "FB-000123", company, kind: "bug"|"feature"|"confusion"|"complaint"|"praise",
               area: string, title_fa, count, first_seen, last_seen, quotes: [masked, ≤ 3], sources: [SC-…|NP-…],
               state: "new"|"triaged"|"in_backlog"|"done"|"wont_do", work_ref|null, version }
```
| GET | `/feedback` | `?company&kind&state&cursor` — most frequent first |
| PATCH | `/feedback/{ref}` | `state`, `work_ref`, `If-Match` (owner, the company's CEO and PRODUCT manager) |
- Tagging is rules first (keywords per company), then a light model in a nightly batch; similar items merge (same kind and area, Persian
  full-text similarity). An item reaching the company's threshold (default 5 in 7 days) becomes one work item for the PRODUCT manager.

### 19.8 Intake from outside (Telegram, Chatwoot, products)
| POST | `/intake/v1/telegram/{company}/{channel}` | Telegram webhook; the `X-Telegram-Bot-Api-Secret-Token` must match; Telegram's published IP ranges only |
| POST | `/intake/v1/chatwoot/{company}` | Chatwoot agent-bot webhook, HMAC-SHA256 of the body with the source's secret |
| POST | `/intake/v1/product/{company}` | product events `{events: [{id, kind, at, subject, data}]}` (`signup`, `uid_submitted`, `referral_verified`, `referral_failed`, `vip_activated`, `support_message`), HMAC-SHA256 over `timestamp.body`, ±300 s, `id` idempotent |
- These are the only public routes added; they are served by Caddy on `hq.coinepro.com` (never `/internal`), rate-limited, and answer `401
  unauthenticated` on a bad signature with no detail. Secrets: `make intake-secret COMPANY=… SOURCE=…` (the owner's terminal), never the API.
- `IntakeSource { company, kind: "telegram"|"chatwoot"|"product", configured: bool, last_event_at|null, events_24h, rejected_24h }` —
  `GET /intake/sources`; `POST /intake/sources` 🔏 `intake.source` (body hash) registers one (allowed IPs, kinds).

### 19.9 Decision kinds, step-up targets, stream, codes ⟨1.5⟩
- **Decision kinds:** `message_template` (payload: the template and its sha256), `lifecycle_rule` (the rule, its template version and limits),
  `support_go_live` (company, channel, `auto_send`, `verbatim_threshold`, `grounded_threshold`, the `ShadowReport`).
  ⟨1.5.1⟩ Payload shapes as the apps read them: `message_template` `{template: Template, sha256}` · `lifecycle_rule` `{rule: LifecycleRule,
  template: "TM-…@v", limits}` · `support_go_live` `{company, channel, auto_send, verbatim_threshold, grounded_threshold, shadow_report: ShadowReport}`.
  Rates and shares in §19 (`share`, `conversions[].rate`, `leaks[].rate`) are 0..1; the rescue rate is the client's `rescued / (rescued + lost)`.
  `POST /intake/sources` body: `{company, kind, allowed_ips: [cidr], kinds: [event kind]}`. All are sealed with step-up
  (`decision.approve`, target = ref; §5.1 ⟨1.4.5⟩) and bound to their payload: a template, rule or shadow report that changes before the seal
  supersedes the card. The thresholds have no edit route: changing them takes a new shadow run and a new card.
- **Step-up targets:** `revenue.account` (body hash), `support.kb` (`ref@version`), `support.channel` (`company/kind@auto_send`),
  `growth.template` (`ref@version:sha256`), `growth.rule` (`ref@version`), `intake.source` (body hash).
- **Stream topics:** `revenue` (`revenue.day`, `revenue.alert`) · `support` (`support.message`, `support.queue`, `support.channel`) ·
  `growth` (`rescue.updated`, `lifecycle.sent`, `nps.closed`) · `feedback` (`feedback.item`).
- **Stable codes (§14):** `channel_not_live` (409), `shadow_not_passed` (409), `template_not_sealed` (409), `send_blocked` (422, with
  `blocked_reasons`), `opted_out` (409), `send_limit` (429 with `Retry-After`).
- **Oversight:** `PR-043` (mystery customer) becomes `active` with this section: the overseer opens a conversation on the `mystery` channel with
  the owner's standing permission; it runs the whole pipeline but never reaches Telegram or Chatwoot and is left out of every statistic.

### 19.10 Agent tools (agents/tools.md, v1.5)
| Tool | Class | Who |
|---|---|---|
| `kb.search` `{q, company?, kind?}` | A0 | support roles (approved only), support lead (also proposed) |
| `kb.propose` `{company, kind, question_fa, answer_md, variables?, source_ref, ref?}` | A1 | support lead, support agent |
| `support.draft` `{conversation, body_md, kb_refs, confidence}` | A2 | support agent — code decides: send (auto-send policy), queue or block |
| `support.handoff` `{conversation, reason, note_fa}` | A2 | support roles |
| `referral.check` `{company, exchange, uid}` | A0 | support agent, rescue specialist — answers `{invitee: bool, meets_minimum: bool\|null}`, never a balance |
| `rescue.update` `{ref, state, note_fa}` | A2 | rescue specialist |
| `feedback.tag` `{source_ref, kind, area, title_fa}` | A2 | support lead, PRODUCT manager |
| `revenue.read` `{company?, from, to, by?}` · `funnel.read` `{company, period}` | A0 | CEOs, FIN and SALES managers, revenue analyst, advisor, overseer |
| `support.mystery` `{company, question_fa}` | A2 | overseer only (PR-043) |
Templates and rules are proposed with `propose` (kinds above); there is no tool that sends free text to a customer.

## 20. v1.5 — governance (prompt 11)

> Owner decisions (`OPERATING_MODEL.md` §1.14–§1.16; `docs/GAP_ANALYSIS_v2.md` §5ج): **meetings** run by code under a token budget the owner sees
> beforehand, every claim with a source, a devil's advocate from oversight, the advisor whispering only to the owner, and resolutions only by the
> owner's seal; a versioned **charter** with company addenda that only the owner seals and every agent reads; a **four-layer knowledge base**
> with sources and expiry; the **three cards** and a live **scorecard**; **OKRs**; **decision outcome reviews** at 30/60/90 days; an editable
> **authority matrix** with locked invariants; a **risk register**; a **change calendar** with conflict detection; and a **batch seal** for
> low-risk cards. Everything above still holds: no fixed company count, `company_id` with forced RLS, A3 is the owner's, A4 never happens.
> ⟨1.5⟩ No new long-running service: meetings are workflows in the existing worker, KPIs are collected by a worker schedule, the authority
> matrix is data for the existing OPA, search is Postgres FTS.

### 20.1 Meetings
```
MeetingType { key: "board"|"company"|"standup"|"war_room"|"postmortem"|"strategy", title_fa,
              schedule: RRULE (owner TZ)|null,               // null = opened by an event (war_room, postmortem)
              members: { roles: [role], companies: "all"|"concerned" },
              max_rounds: 1..3 (default 2), max_speakers: 2..8 (default 6, per agenda item),
              budget_tokens: int|null (null = no meeting cap: war_room only), turn_cap_tokens (default 6000),
              owner_presence: "live"|"summary"|"audio", enabled, version }
Meeting     { id, ref: "MT-0001", type, company,                  // the holding's company for board and strategy
              title_fa, starts_at, state: "scheduled"|"prep"|"live"|"closing"|"ended"|"cancelled",
              mode: "discussion"|"written",                        // written: not enough of the daily cap left; statements only
              budget: { cap, estimate, reserved, used }, trimmed_fa|null,
              items: [MeetingItem], participants: [{actor: Actor, role_fa, speaker: bool, devil: bool}],
              owner_presence, minutes: { deliverable: "O-…", summary_md }|null, incident|null, version, created_at }
MeetingItem { id, n, title_fa, brief_md, sources: [{kind, ref, note}], time_box_min, speakers: [Actor], round: 0..3,
              state: "waiting"|"round_1"|"round_2"|"done"|"skipped" }
Turn        { id, meeting, item, n, round, speaker: Actor, kind: "statement"|"challenge"|"vote"|"owner",
              statement_md, claims: [Claim], draft_md|null, stance: {draft, vote: "support"|"oppose"|"abstain", reason_fa}|null,
              run_id|null, tokens, at }
Claim       { id, text_fa, source: {kind, ref}|null, status: "sourced"|"unsourced"|"challenged"|"withdrawn" }
Whisper     { id, meeting, item, text_md, sources, at }      // the advisor's; visible to the owner only
Draft       { id, meeting, item, text_md, proposer: Actor, votes: {support, oppose, abstain}, decision: "D-…"|null }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/meetings` | `?type&company&state&from&to` |
| POST | `/meetings` | owner: an ad-hoc meeting `{type, company?, starts_at, items?}`; same speaker rule, budget and daily share · `Idempotency-Key` |
| GET | `/meetings/{ref}` | with items, budget estimate and `trimmed_fa`; before `live` this is what the owner sees and edits |
| PATCH | `/meetings/{ref}` | owner: reorder or skip items, lower the budget, presence (`If-Match`) |
| GET | `/meetings/{ref}/turns` | `?item&after` (Page); whispers are included for the owner only |
| POST | `/meetings/{ref}/speak` | owner: `{text?, file_id?}` (a voice file goes through §17.2); jumps the queue. `409 meeting_not_live` otherwise · `Idempotency-Key` (required) |
| POST | `/meetings/{ref}/control` | owner: `{action: "next_round"|"skip_item"|"end"|"raise_budget", tokens?}`; only the owner raises a budget |
| GET · PUT | `/meetings/settings` | the `MeetingType` list; PUT 🔏 `meetings.settings`, target = body hash |
- **Run by code.** Agenda, speakers, turn order, budget estimate and trimming, claim checks and the minutes are code. One turn is one agent
  run with `Run.trigger: "meeting"` and the tool `meeting.statement`; its context is the item, its sources, the claims made so far on that
  item and the speaker's own company data. Speakers per item ≤ `max_speakers`, chosen by rule (the concerned companies' CEOs or managers,
  the relevant holding head, the devil's advocate last); other companies give written statements, so a meeting's size never depends on
  the number of companies.
- **Budget.** The router enforces the cap as the scope `meeting:<ref>`; it is reserved from the agents' daily cap at the start. A turn
  that does not fit is not run and the meeting moves to `closing`. Not enough daily cap left → `mode: "written"`. `war_room` has no
  meeting cap but stays inside the daily cap and the holding kill switch.
- **Daily share** ⟨1.5⟩: all meeting reservations of one day together use at most `MEETINGS_DAILY_SHARE` of the agents' daily cap (default 0.15,
  enforced by the router like the oversight share of §18.1); a meeting that does not fit what is left is `written`. `war_room` is outside the share.
  The weekly `company` meetings are spread over the working days by rule (companies in code order, Saturday to Wednesday; a new company goes
  to the lightest day), so one day never holds them all.
- **Claims** are checked like message citations (§16.3): the ref must exist and the speaker must be able to read it, else `unsourced`;
  an expired knowledge entry is refused (`knowledge_expired`). Unsourced and challenged claims never enter the minutes or a resolution.
- **Resolutions.** Each draft becomes a decision of kind `meeting_resolution` (A1, owner) carrying the votes and the sourced claims; only
  the owner's seal creates `M-…` and the follow-up work. Managers' votes never replace the seal.
- **Minutes** are assembled by code; the system role `secretary` (`HQ-SEC`, Haiku) writes `summary_md` from sourced claims only.
- **Standup** is code only by default (yesterday's work records per department, nothing sent when nothing changed). **War room** opens on
  a `sev1` incident or an `urgent` `service_down`, P0; it closes with the incident and schedules a `postmortem` for 10:00 the next day.
- `owner_presence: "audio"` behaves as `summary` until text-to-speech exists (prompt 12).
- `GET /planner` includes meetings (§4).

### 20.2 Charter and addenda
```
Charter { scope: "holding"|"<company code>", version, status: "proposed"|"sealed"|"superseded",
          body_md (holding ≤ 6000 chars, addendum ≤ 3000), red_lines: [{key, text_fa, check: "rule"|"sample", patterns: [regex]|null}],
          body_sha256, created_by: Actor, created_at, sealed_by: Actor|null, sealed_at|null }
          // body_sha256 = sha256 of the canonical JSON {body_md, red_lines} (sorted keys, no spaces): the seal binds the red lines too
```
| Method | Path | Notes |
|---|---|---|
| GET | `/charter` | the sealed holding charter and every addendum the principal may read, with versions |
| GET | `/charter/{scope}/versions` · `/charter/{scope}/versions/{v}` | |
| GET | `/charter/{scope}/versions/{v}/diff` | `?against=<v>` → unified diff, computed on the server |
| PUT | `/charter/{scope}` | owner: a new `proposed` version |
| POST | `/charter/{scope}/versions/{v}/seal` 🔏 | `charter.seal`, target = `body_sha256` (recomputed by the server) |
- **Agents read, never write.** The runtime puts the sealed holding charter and the company's sealed addendum after `_common` and before the
  role charter (cached prefix); every run records `charter_docs: ["holding@3", "TY@1"]`. Until a version is sealed only the four red lines
  of `OPERATING_MODEL.md` §1.15 apply. There is no agent tool that writes a charter.
- Agents propose amendments with `propose` kind `charter_amendment` `{scope, base_version, body_md, red_lines, diff_md, body_sha256}` (a CEO for its
  own addendum; the overseer and the advisor for the holding). Sealing the card is 🔏; a card whose `base_version` is no longer current is
  superseded (`409 decision_not_pending`).
- **Red lines** with `check: "rule"` are matched by code on deliverables, messages to the owner and stories (→ a finding), and are added
  to the support output guard of §19 for text to customers with the refusal code `red_line` (§19.6: held for review, never sent, no override).

### 20.3 Knowledge (four layers)
```
KnowledgeEntry { id, ref: "K-0001", layer: "holding"|"company"|"department"|"employee", company, department|null,
                 kind: "principle"|"policy"|"fact"|"faq"|"playbook"|"support", title_fa, body_md,
                 sources: [{kind, ref, note}] (≥ 1), valid_until: date,
                 status: "draft"|"in_review"|"approved"|"expired"|"retired",
                 review: {by: Actor, at, verdict: "pass"|"changes"|"reject", checks: {injection, secrets, conflicts, policy}, notes_md}|null,
                 approved_by: Actor|null, version, created_by: Actor, created_at, updated_at }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/knowledge` | `?layer&company&department&kind&status&q&include_expired` (owner and overseer only for expired) |
| GET | `/knowledge/{ref}` · `/knowledge/{ref}/versions` | |
| POST · PUT | `/knowledge` · `/knowledge/{ref}` | owner: an entry or a new version; what the owner writes is approved by that act |
| POST | `/knowledge/{ref}/retire` | owner |
- **No second store.** The employee layer is the employee's memory (§16.6), shown read-only here, not copied. The support knowledge base
  (§19, `/support/kb`) keeps its own table, its owner seal (`support.kb`) and its own expiry: it appears in the company layer as kind
  `support`, read-only through a view (`GET /knowledge?kind=support`, `knowledge.search`), and is edited only at `/support/kb`. Skills (§18.5) stay the role instructions in the system prompt; a playbook is a
  department's approved method, found by search; curricula point to playbooks by `K-…`; an adopted lesson drafts a playbook.
- **Sources and expiry are required.** Longest `valid_until` by kind: fact 90 days, faq 180, playbook and policy 365, principle 730
  (support articles follow §19). Fourteen days before expiry a review work item goes to the layer's keeper; at expiry the entry is `expired`, is not
  returned to agents, and cannot be cited (`422 knowledge_expired`).
- **Approval.** Review by the overseer or AI safety; then the company's CEO approves company and department entries (`knowledge.approve`,
  an authority-matrix row the owner may take back); holding entries are cards of kind `knowledge_entry` for the owner.
- **No leaks.** RLS: holding entries for all; company entries for that company and the holding; department entries for that department,
  its CEO and the holding. Moving knowledge between companies is a CEO-to-CEO `work.request`; the receiver writes its own entry.
- Search: Postgres FTS and `pg_trgm` with the Persian normalisation of §5.3; `knowledge.search` gains kind `knowledge`.

### 20.4 The three cards and the scorecard
```
Kpi      { id, company, key, card: "stability"|"growth"|"safety_cost", name_fa, unit, direction: "up"|"down",
           source: {kind: "query", query: "<registry key>"}|{kind: "manual"}, freshness_hours, target|null,
           scorecard: bool, aggregate: "sum"|"avg"|"min"|"max", status: "active"|"paused", version }
KpiValue { kpi, at, value, source_ref: {kind, ref, note} }
Card     { company, card, kpis: [{key, name_fa, unit, value|null, at|null, source_ref|null, target|null, trend: [30 values],
           state: "ok"|"stale"|"no_source"}] }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/cards` | `?company` (default: the holding) → the three cards |
| GET | `/scorecards` | one row per company with its `scorecard` KPIs; paged and searchable (§1) |
| GET · PUT | `/kpis/{company}` | definitions and targets; PUT owner, `If-Match` |
| GET | `/kpis/{company}/{key}/values` | `?from&to` |
- **Sources come from a closed registry** of reviewed queries (health, treasury, work, oversight, stars; revenue, funnel and support once
  prompt 10 serves them). A query whose source does not exist is not in the registry and its KPI shows `no_source`, never zero. A manual
  KPI is written only with `kpi.record` and a source.
- Values older than `freshness_hours` are `stale` («قدیمی»). The holding card aggregates the companies with each KPI's `aggregate`, plus
  the holding's own KPIs.
- **KPI attainment** in the company score (§18.4, 35%) = the weighted progress of the active quarter's key results when an OKR is active,
  else the share of scorecard KPIs at or beyond their target.
- Protocol `PR-090` is `active` from this version.

### 20.5 OKR
```
Objective { id, ref: "OB-0001", company, quarter: "1405-Q3" (Jalali), title_fa, why_md, owner: Actor (the CEO),
            status: "draft"|"proposed"|"active"|"closed", decision: "D-…"|null, key_results: [KeyResult] }
KeyResult { id, ref: "KR-0001", objective, title_fa, kpi: key|null, metric_fa|null, start, target, current|null,
            progress: 0..1, confidence: 0..1, weight, checkins: [{at, by: Actor, confidence, note_md, evidence}] }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/okr` | `?company&quarter&status` |
| GET | `/okr/{ref}` | an objective with its key results |
- A CEO drafts the next quarter in its last month (`okr.draft`) → a decision of kind `okr` (owner; amendments allowed); only the seal makes
  it `active`. A key result linked to a KPI takes `current` from it. A check-in is due at least every 14 days.
- `Work` gains `key_result: "KR-…"|null` (set by `POST /work` and `work.delegate`); the planner shows it.

### 20.6 Decision outcomes (30/60/90 days)
```
Decision      { …§5.1, expected: {metric_fa, kpi|null, baseline, target, by_days: 30|60|90}|null,
                warnings: ["expected_missing"] }   // expected is required for kind proposal created after prompt 11 is deployed (see below)
OutcomeReview { id, ref: "OR-0001", decision: "D-…", company, day: 30|60|90, due_at, expected,
                measured: {value, at, source_ref}|null, verdict: "pending"|"met"|"partly"|"missed"|"unmeasurable",
                proposer: Actor, proposer_note_md|null, overseer_note_md|null, status: "due"|"answered"|"verified" }
```
| GET | `/outcomes` | `?company&verdict&due&decision` |
|---|---|---|
- **`expected` on proposals:** required only for `proposal` cards created after prompt 11 is deployed; earlier cards are untouched. For the first
  7 days a missing `expected` is a warning on the card (`warnings: ["expected_missing"]`), not a 422; after that it is `422 validation_failed`.
  The CEO charter and the `propose` row of `agents/tools.md` already ask for it.
- Created when a decision with `expected` is sealed: day 30, 60 and 90, up to `by_days`. With a KPI the verdict is code (`met` at target,
  `partly` at half the distance or more, else `missed`); without one the proposer writes `outcome.note` and the overseer decides (`PR-006`).
- Managers' and CEOs' **prediction accuracy** (§1.16) comes from these verdicts.

### 20.7 Authority matrix
```
AuthorityRule { key, title_fa, action, actor: role|kind, scope: "own_company"|"holding",
                limit: {tokens_month?, usd?, count_day?, count_hour?, days?: [weekday]}|null, bounds: {min, max}|null,
                step_up: bool, class: "A0".."A4", locked: bool, note_fa, version }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/authority` | the whole matrix with `locked` rows |
| PUT | `/authority` 🔏 | `authority.update`, target = body hash; unlocked rows only, inside `bounds` (`422` otherwise) |
- The rows are data that OPA reads (`data.hq.authority`); the API pushes them at start and on every change. The policy keeps the **locked
  invariants independent of the data**: A4 never; A3 only the owner (the CEO's content-calendar publish exception of §1.12 stays off until a
  content calendar exists); proposer ≠ approver; releasing a kill switch or a hold is the owner's; no agent edits the matrix.
- **Sends the owner sealed in advance are the owner's A3 approval and stay allowed:** messages of a sealed `lifecycle_rule` with its sealed
  template, and the `auto_send` of a channel that went live by a sealed `support_go_live` (§19). The locked invariant blocks only A3 execution
  without such a seal; the policy reads the seals themselves (the sealed card and the rule's or channel's version), never the matrix data.
- Agents read their company's rows with `authority.read`; they propose changes with `propose` kind `authority_change` (🔏 on approval).

### 20.8 Risk register
```
Risk { id, ref: "RK-0001", company, title_fa, body_md,
       category: "product"|"security"|"data"|"money"|"people"|"vendor"|"ops"|"reputation",
       likelihood: 1..5, impact: 1..5, score (= likelihood × impact), owner: Actor, mitigation_md|null,
       status: "open"|"mitigating"|"accepted"|"closed", review_at, accepted: {decision: "D-…", until}|null,
       links: {finding?, incident?, decision?, work?}, history: [{at, by: Actor, change, note}], version }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/risks` | `?company&status&category&min_score` |
| GET | `/risks/{ref}` · `/risks/matrix` | the matrix: 5 × 5 counts, `?company` |
| POST · PATCH | `/risks` · `/risks/{ref}` | owner (`If-Match` on PATCH) |
- Keeper: the Inspector General (QC). Longest review interval: score ≥ 15 → 14 days, ≥ 8 → 30, else 90. A risk of 15 or more has a
  mitigation or the owner's acceptance: a decision of kind `risk_acceptance` (🔏, at most 90 days). Closing needs the keeper. A `critical`
  finding and a post-mortem draft a risk.

### 20.9 Change calendar
```
CalendarEvent { id, ref: "CE-0001", company|null, kind: "deploy"|"campaign"|"event"|"maintenance"|"meeting"|"freeze"|"holiday",
                title_fa, starts_at, ends_at, source: {decision?, work?, meeting?, order?}, status: "planned"|"done"|"cancelled",
                risk: "low"|"medium"|"high", created_by: Actor }
Conflict      { a: "CE-…", b: "CE-…", rule, severity: "medium"|"high", note_fa }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/calendar` | `?company&from&to&kind` → events and their conflicts |
| POST · PATCH | `/calendar` · `/calendar/{ref}` | owner (`If-Match` on PATCH); agents use `calendar.add` |
- Filled by code from deploy cards, freezes, meetings, backup and restore windows, and the official Jalali holidays (seed). The `deploy`
  payload gains `window: {from, to}` and `calendar_conflicts`; it has **one definition** in §5.1, shown in full in §21.6, in which `head_sha`
  is required from this version (given by the proposer; checking it against the PR is §21.6). Rules: a deploy inside a freeze or during the same company's campaign or event is `high`; two
  deploys of one company or of a shared service, a deploy on a blackout day of the authority matrix or a holiday, and maintenance during a
  deploy are `medium`. Conflicts go into the deploy card's `payload.calendar_conflicts` and `risk_note`. The calendar never decides.
- `GET /planner` includes calendar events; the planner stays a view.

### 20.10 Batch seal
| Method | Path | Notes |
|---|---|---|
| GET | `/decisions/batchable` | the pending cards that may be sealed together, with title, cost and proposer |
| POST | `/decisions/batch/approve` 🔏 | `{items: [{ref, version}]}`; `decision.batch`, target = sha256 of the canonical JSON of `items` sorted by `ref` · `Idempotency-Key` (required) |
- **Eligible** only when all hold: kind `proposal`, `meeting_resolution` or `knowledge_entry`; `action_class: "A1"`; `risk: "low"`;
  `reversible`; `pending`; the owner is the approver; no hold; no amendments; `quota_estimate.usd ≤ batch.max_usd`; at most
  `batch.max_items` items (both authority-matrix rows; defaults $2 and 20). **Never batched (locked):** any A3, `hire`, `dismissal`,
  `budget_change`, `code_session`, `server_plan`, `deploy`, `company_found`, `tool_enable`, `protocol`, `errand_action`, `evaluation`,
  `charter_amendment`, `authority_change`, `risk_acceptance`, `okr`, `recurring_approval`, `lesson_adoption`, `message_template`, `lifecycle_rule`,
  `support_go_live`, or anything irreversible. The
  owner may only shorten the allowed list.
- **All or nothing:** if any card changed or is no longer eligible, the whole call is `422 batch_not_eligible` with
  `fields.items: [{ref, reason}]` and nothing is sealed. Each sealed card has its own resolution, its own audit row (with `batch: "B-0001"`)
  and its own owner interaction.

### 20.11 Kinds, stream types, step-up targets, codes
- **Decision kinds** added: `meeting_resolution` (A1), `charter_amendment` (🔏), `okr`, `knowledge_entry`, `risk_acceptance` (🔏),
  `authority_change` (🔏). 🔏 kinds are sealed with `decision.approve`, target = ref, like §5.1.
- **`Run.trigger`** gains `"meeting"`.
- **Stream topics:** `meetings`: `meeting.scheduled`, `meeting.started`, `meeting.turn`, `meeting.claim`, `meeting.whisper` (owner only),
  `meeting.ended` · `governance`: `charter.sealed`, `kpi.stale`, `okr.updated`, `outcome.due`, `risk.updated`, `calendar.conflict` ·
  `knowledge`: `knowledge.updated`, `knowledge.expiring`.
- **Step-up targets:** `charter.seal` (`body_sha256` = sha256 of the canonical `{body_md, red_lines}`), `authority.update` (body hash),
  `meetings.settings` (body hash), `decision.batch` (sha256 of the sorted `[{ref, version}]`).
- **Settings:** `MEETINGS_DAILY_SHARE` (default 0.15, the owner's to change).
- **Stable codes (§14):** `meeting_not_live` (409), `knowledge_expired` (422), `batch_not_eligible` (422, `fields.items`).
- **Agent tools** (agents/tools.md): `meeting.statement`, `meeting.challenge`, `meeting.whisper`, `meeting.item`, `meeting.minutes`,
  `knowledge.propose`, `knowledge.review`, `knowledge.approve`, `kpi.record`, `okr.draft`, `okr.checkin`, `outcome.note`, `risk.raise`,
  `risk.update`, `calendar.read`, `calendar.add`, `authority.read`, `governance.read`; `knowledge.search` gains kind `knowledge`;
  `propose` accepts `expected`.

### 20.12 Shapes as the apps read them ⟨1.5.1⟩
Written with the web and Android screens (2026-10-22). Where §20.1–§20.11 leave a shape open, this is the contract.
- **Meetings:**
  - `GET /meetings/{ref}/turns` → `{items: [Turn], whispers?: [Whisper], next_cursor}`. `GET /meetings/{ref}` carries `drafts?: [Draft]`.
  - `budget.cap` is `number|null` (null for a war room); `incident` is an `I-…` ref.
  - `PATCH /meetings/{ref}` (If-Match) `{items?: [{id, n, skip?}], budget_cap?, owner_presence?}`. `POST …/speak` → `Turn`; `POST …/control` and `POST /meetings` → `Meeting`.
  - `GET /meetings/settings` → `[MeetingType]`; `PUT` `{types}` without If-Match; each row carries its own `version`.
- **Charter:**
  - `GET /charter` → `[{scope, sealed, proposed, versions: [{version, status, created_by, created_at, sealed_at}]}]`; `GET …/diff` → `{scope, version, against, diff}`.
  - `PUT /charter/{scope}` `{body_md, red_lines}`.
  - The seal's target is the `body_sha256` the server sends: SHA-256 of the UTF-8 body as stored (no JSON wrapping, no escaping). Clients never recompute it.
- **Knowledge:**
  - Create and update body `{layer, company, department?, kind, title_fa, body_md, sources, valid_until}`.
  - `review.checks` values: true = passed. Support articles keep their `KB-` refs in the knowledge view.
- **Cards:**
  - `trend: [number|null]` (a day with no value is null, never zero).
  - `Card` gains `direction: "up"|"down"|"range"`.
  - A scorecard row is `{company, kpis: [CardKpi + {card, direction}]}`.
  - `GET /kpis/{company}` → `{company, version, kpis}`; `PUT` (If-Match on that version) `{kpis: [{key, target, scorecard, status, freshness_hours}]}`.
- **OKR, outcomes:** an OKR check-in's `evidence` is `[Source]`; `GET /outcomes?due=true` = due now or overdue.
- **Authority:**
  - `PUT /authority` (🔏 body hash) `{rules: [{key, actor?, limit, version}]}`; `actor: "owner"` takes a row back.
  - The batch-seal item limit is the rule key `batch.max_items` with `limit.items`.
- **Risks:** `GET /risks/matrix` → `{company, counts: [[int ×5] ×5]}` indexed `[likelihood−1][impact−1]`; the create body has `owner?`, `mitigation_md?`, `review_at?`.
- **Calendar:**
  - `GET /calendar` → `{events, conflicts}`. `CalendarEvent` gains `version` (for If-Match).
  - A single-event rule (a deploy on a blackout day) has `a = b`.
- **Batch seal:**
  - `GET /decisions/batchable` items `{ref, version, kind, company, title, quota_estimate, proposer, risk?, created_at?, expires_at?}`.
  - The approve response is `{batch, items: [{ref, resolution}]}`.
  - Refusal reasons in `fields.items`: `changed`, `not_pending`, `kind`, `action_class`, `risk`, `irreversible`, `amended`, `over_max_usd`, `over_max_items`, `held`.
- **Decision payloads:**
  - `meeting_resolution` `{meeting, item, text_md, votes, claims}`
  - `okr` `{objective: "OB-…"|Objective, quarter}`
  - `knowledge_entry` `{entry}`
  - `risk_acceptance` `{risk, until, score?}`
  - `authority_change` `{changes: [{key, from, to}]}`

## 21. v1.5 — management tools (prompt 12)

> **v1.5 (2026-10-18).** The owner's everyday tools (`docs/GAP_ANALYSIS_v2.md` §5د): the premium advisor (decision memo, devil's advocate,
> proactive notes, the weekly review), "ask the hub", spoken briefings and the CEOs' weekly letters, department ranking, the monthly HR
> evaluation, the real diff on a deploy card, the daily waste report, ROI, adding a connection, quick notes, cartable reminders, refuted claims on
> the agent health board, the **digital CEO in prediction-only mode**, and MCP servers in containers. Everything above still holds.
> **Rules first, AI last:** every figure, trigger, flag, rank and reminder here is code; a model writes only prose a rule cannot write.

### 21.0 Principles ⟨1.5⟩
- **The owner zone has its own token share.** The *automatic* runs of the advisor (auto memo, proactive notes, weekly review brief), the librarian
  and the digital CEO (model predictions, principles) together use at most `OWNER_ZONE_DAILY_SHARE` (default 0.25, pending the owner's decision) of the agents' daily cap,
  enforced by the LLM Router like the oversight share (§18.1). When it is spent, automatic runs wait for the next day and predictions fall back to
  the baseline. **What the owner asks for directly** (an ask, a memo on request, a message) always runs, inside the overall cap.
- New **task classes** (in `/assignments`, defaults from the charters): `advisor_memo`, `advisor_proactive`, `advisor_review`, `ask_hub`,
  `ceo_letter`, `hr_eval`, `dceo_predict`, `dceo_principles`.
- **Nothing here acts in the world.** No new A3 path exists; the digital CEO cannot write anything but its own predictions.
- Every new table carries `company_id` (owner and holding rows: the holding's) under forced RLS, and every change writes one audit row.

### 21.1 The premium advisor: memo, devil's advocate, proactive notes (OPERATING_MODEL §1.11)
```
DecisionMemo { id, ref: "DM-0001", decision: "D-…", decision_version, mode: "standard"|"devil",
               state: "writing"|"ready"|"failed"|"stale", trigger: "owner"|"auto",
               summary_fa, recommendation: "approve"|"reject"|"return"|"ask", confidence: 0..1,
               options: [{title_fa, pros_md, cons_md}], against_md,           // the strongest case against; never empty
               risks: [{title_fa, likelihood: "low"|"medium"|"high", impact: "low"|"medium"|"high", mitigation_fa}],
               questions: [string],                                           // what the owner should ask the proposer
               citations: [{kind, ref}], usage: {tokens, usd},
               second_opinion: {player, model, recommendation, confidence, summary_fa, differences: [string], agrees: bool}|null,   // §21.13
               created_at }
AdvisorTrigger { id, key, kind: "budget"|"quota"|"compliance"|"incident"|"revenue"|"waiting_decisions"|"finding"|"okr",
               company|null, fired_at, facts: {…}, message_ref: "A-…"|null, state: "sent"|"deferred"|"capped" }
```
| Method | Path | Notes |
|---|---|---|
| POST | `/decisions/{ref}/memo` | `{mode}` → `202 DecisionMemo`; idempotent per decision, mode and decision `version`; a decided card → `409 decision_not_pending` |
| GET | `/decisions/{ref}/memo` | `?mode` (default `standard`) → the latest memo, or 404 |
| GET | `/advisor/memos` | `?decision&cursor` |
| GET | `/advisor/triggers` | `?since&kind` |
- `Decision` gains `memos: [{ref, mode, state}]`.
- **Automatic memo** when a card for the owner is created with `risk: high` or kind `deploy`, `company_found` or `server_plan`; at most
  `owner_settings.advisor.auto_memo.max_per_day` (default 3). The cap is not carried over.
- A memo is bound to the card's `version`: a changed card makes it `stale`.
- **Devil's advocate:** `MessageIn` gains `mode?: "devil"`, valid only in thread `A` (elsewhere `422 validation_failed`). The advisor's reply carries
  `meta.mode: "devil"`. A `devil` memo argues why not.
- **Proactive notes:** rules fire triggers with a `key` unique per day; the advisor is woken once per key with the facts gathered beforehand and
  writes one short message in `A` with `meta.proactive: {kind, key}` and a `report`-level notification, **never `urgent`**. At most
  `owner_settings.advisor.proactive_per_day` (default 3); the rest are recorded `capped`.
- Agent tool: `memo.write` (A1, advisor only, `pending` cards only).
- Stream: `memo.ready`, `advisor.proactive` on topic `advisor`.

### 21.2 Ask the hub (F7)
```
Ask       { id, ref: "AK-0001", q, scope: {companies?: [code], kinds?: [kind]}|null,
            state: "queued"|"searching"|"answering"|"done"|"failed", found: int,
            answer_md|null, citations: [{kind: "resolution"|"decision"|"deliverable"|"work"|"message"|"doc"|"code",
                                         ref?, repo?, path?, lines?: [from, to], commit?, snippet}],
            not_indexed: [repo], usage: {tokens, usd}, created_at, finished_at|null }
```
| Method | Path | Notes |
|---|---|---|
| POST | `/ask` | owner only · `{q (≤ 500), scope?}` → `202 Ask` · `Idempotency-Key` |
| GET | `/ask/{ref}` · `/ask` | `?cursor` (history, newest first) |
- **Retrieval is code:** Postgres full-text search with `pg_trgm` and the Persian normalisation of §5.3, over a nightly corpus: resolutions,
  decisions, deliverables, work, messages (the owner's asks only), the hub's own documents (`docs/`, `contracts/`, `agents/`, RUNBOOK), and the
  code of the hub repository and of every Code Workshop workspace repository (read-only, fetched with the hub's existing git access — the owner's
  decision: no new GitHub token; a repository the hub cannot read is listed in `not_indexed`). A file in which the secret scan finds anything is
  left out entirely. No embeddings.
- **Nothing found → no model call**, `found: 0`, `answer_md` says so. Otherwise the librarian `HQ-LIB` answers only from the retrieved passages;
  a citation outside them is dropped and counted; an answer with no valid citation is `failed`.
- Agents: `knowledge.search` gains kinds `docs` and `code` (advisor, overseer, librarian; a CTO only its own company's repositories) and `notes`
  (advisor only, §21.8).
- Stream: `ask.answered` on topic `ask`.

### 21.3 The weekly review with the advisor (M15)
```
WeeklyReview { id, ref: "WR-0001", week (Saturday, YYYY-MM-DD, owner TZ), state: "ready"|"in_progress"|"done"|"skipped",
               agenda: [{n, kind: "decision"|"risk"|"okr"|"finding"|"budget"|"revenue"|"outcome_review"|"note",
                         ref, company|null, title_fa, why_fa, status: "open"|"done"|"deferred", owner_note|null}],   // ≤ 12, in this kind order
               brief_message_ref: "A-…"|null, minutes_ref: "O-…"|null,
               started_at|null, finished_at|null, duration_s|null, version }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/reviews/weekly` · `/reviews/weekly/current` | owner only |
| POST | `/reviews/weekly/{ref}/start` · `/finish` | `finish` writes the minutes as a deliverable `O-…` by `HQ-ADV` |
| PATCH | `/reviews/weekly/{ref}/items/{n}` | `{status, owner_note?}` · `If-Match` |
- `owner_settings.weekly_review: {enabled, day: "sa", at: "10:00"}`. The agenda is built by code 30 minutes before; the advisor writes a one-page
  brief in `A` (`meta.review`). A review not done by the next one is `skipped` (one line in the morning report; no urgent nag).
- Stream: `review.updated` on topic `reviews`.

### 21.4 Spoken briefings and the CEOs' weekly letters (F8)
```
Briefing { id, ref: "BR-0001", kind: "morning"|"ceo_letter", company, period: {from, to},
           deliverable_ref: "O-…", text_md,
           audio: FileRef|null, audio_state: "pending"|"ready"|"off"|"failed",
           voice: {engine: "piper", version, voice, license}|null, created_at }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/briefings` | `?kind&company&cursor` |
| GET | `/briefings/latest` | `?kind=morning\|ceo_letter&company` |
| GET | `/briefings/{ref}` | |
- **Speech is made on the hub** (Piper, a Persian `fa_IR` voice whose licence is recorded in `voice.license` and in `/meta`; nothing leaves the
  hub). The spoken script is built by code from the text: no markdown, refs read as their titles, every number, amount, percentage and Jalali
  date read as Persian words, no Latin digit left. Audio is Ogg/Opus. TTS off or failed → `audio_state` says so and the text is unchanged.
- **Morning:** the written morning report of prompt 5 (no new number) gets its audio; `owner_settings.audio_briefings.morning` (default on).
- **CEO weekly letter:** Saturday 09:00 owner TZ (after the stars roll-up), one per active operating company, ≤ 600 words to the owner, from a facts
  pack built by code (KPIs, stars and score, spend against the envelope, deliverables and the owner's ratings, incidents, findings, challenge,
  the company's revenue §19, next week's plan). A figure not in the facts pack sends the letter back once; the second time it is published
  marked «عدد بی‌منبع» and opens a `PR-001` finding. `owner_settings.ceo_weekly_letter: {enabled, day, at}` (default on);
  `owner_settings.audio_briefings.ceo_letters` (default on). Deliverable kind `ceo_letter`.
- Stream: `briefing.ready` on topic `briefings`.

### 21.5 Department ranking and the monthly HR evaluation (§1.16)
```
DepartmentRank { period: "week"|"month", key, company, department, score: 0..100,
                 parts: {people, delivery, efficiency, owner|null}, employees: int,
                 rank_company, rank_holding|null, trend: [0..100], computed_at }
HrRound        { id, ref: "HR-0001", company, month (Jalali, "1405-08"), state: "drafting"|"proposed"|"done",
                 evaluator: Actor, due_at,
                 employees: [{code, title_fa, score, score_prev|null, stars|null, efficiency|null, owner_avg|null,
                              failed_share, findings_open, refuted_claims, probation_until|null,
                              flags: ["promote_candidate"|"coach"|"demote_candidate"|"dismiss_candidate"|"probation_end"]}],
                 deliverable_ref: "O-…"|null, decisions: ["D-…"], teachings: ["TE-…"] }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/rankings/departments` | `?period=week\|month&key&company` |
| GET | `/hr/rounds` · `/hr/rounds/{ref}` | `?company&month` — owner, overseer, the company's CEO |
- **Department score** = 35% people (employees' scores × 10, weighted by active days) + 30% delivery (work done with evidence on time ÷ work due)
  + 20% efficiency (§18.4) + 15% owner (owner's ratings of the department's deliverables × 10; when there are none its weight is spread over the
  rest). A department without active employees is not ranked. `rank_holding` ranks departments with the same code across companies; null when
  only one exists. Computed with the stars roll-up. Stream: `rankings.updated` on topic `stars`.
- **HR round:** the 1st of each Jalali month, 10:00 owner TZ, per active operating company and the holding. Flags are rules:
  `promote_candidate` score ≥ 8.5 two months running, stars ≥ 4, no open `high` finding · `coach` a drop ≥ 1.5 or a score in [5, 6) ·
  `demote_candidate` score < 5 two months running · `dismiss_candidate` score < 3.5 two months running, or probation ended with score < 5 ·
  `probation_end`. The evaluator is the company's HR manager, else its CEO; the holding's is the AI Ops head. It delivers the monthly HR
  report (`hr_monthly`) and proposes `evaluation` cards **only for flagged employees**; an unflagged one needs evidence and `override_reason` and
  is marked `unflagged: true`. `coach` makes no card: an academy teaching draft (§18.6) for the AI Ops head.
- **`evaluation` payload v2** ⟨1.5⟩: `{employee, recommendation: "promote"|"demote"|"dismiss"|"confirm", change: {model?, effort?, title_fa?,
  quota_estimate_month?}|null, transfer_to?, round: "HR-…", evidence[], unflagged?, override_reason?}`. The owner decides; approval is 🔏
  (`decision.approve`, target = ref). Effects: `promote`/`demote` apply `change` under the hire checks of §18.11 (an enabled connection offers
  the model; the envelope still fits, else `409 envelope_exceeded` and nothing changes); `dismiss` is the dismissal of §3.3 with `transfer_to`;
  `confirm` clears `probation_until`.
- Stream: `hr.round` on topic `people`.

### 21.6 The deploy card shows the diff
**One definition** of the `deploy` payload ⟨1.5⟩; §5.1 changes to it (it includes prompt 11's `window` and `calendar_conflicts`, §20.9):
```
deploy { repo, pr_url, head_sha,                          // required from prompt 11; the card is bound to it, diff or not
         diff_stat, ci: {status, url}, tests: {passed, failed}, rollout,
         window: {from, to}|null, calendar_conflicts: [Conflict]|null,                     // §20.9
         diff: { base_sha, head_sha, total_files, total_additions, total_deletions, truncated: bool, fetched_at,
                 files: [{path, status: "added"|"modified"|"removed"|"renamed", additions, deletions, binary: bool,
                          patch|null, truncated: bool, secret_masked: bool}] } | null,
         diff_unavailable: "no_access"|"too_large"|"fetch_failed"|null }
```
| GET | `/decisions/{ref}/diff` | owner only · `?file=<path>` — one file's full patch, ≤ 2000 lines, masked the same way |
- Built by the API (a service, not a model) when the card is created, with the hub's existing git access (`git fetch`, `git diff base…head_sha`;
  the owner's decision: no new GitHub token); ≤ 300 files, ≤ 400 patch lines per file, ≤ 256 KB in all. Lines where the secret scan finds
  anything are masked. A repository the hub cannot read → `diff: null`, `diff_unavailable: "no_access"`; a `head_sha` not in the repository → 422.
- The card is bound to the top-level `head_sha`: a new push to the PR's branch supersedes it (`409 decision_not_pending` on approve; checked every
  15 minutes for pending cards and once more before the seal), the proposer is told, and a new card with the new diff is needed.

### 21.7 Treasury: waste, ROI, a new connection (F2, M10, #29)
```
WasteDay { day, company|null,                           // null = the holding total
           total_tokens, total_usd, waste_tokens, waste_usd, share: 0..1, vs_7d: number,
           items: [{category: "failed_runs"|"cancelled_work"|"no_progress_runs"|"retry_loops"|"router_errors"|"duplicate_calls"|"cache_miss"|"over_model",
                    tokens, usd, count, top: [{employee?, run_id?, work_ref?, tokens}]}] }
RoiRow   { by: "employee"|"department"|"company", key, company, period: "week"|"month", period_key,
           cost_usd, accepted, avg_rating|null, value_points, cost_per_accepted_usd|null,
           attributed: {rescued?: int, resolved_conversations?: int},
           revenue_usd|null, net_usd|null, roi|null, trend: [number] }      // revenue, net and roi: companies only (§19.1)
```
| Method | Path | Notes |
|---|---|---|
| GET | `/treasury/waste` | `?day&company` → `WasteDay`; `?from&to` → a list |
| GET | `/treasury/roi` | `?by=employee\|department\|company&period=week\|month&key&company` |
| POST | `/connections` 🔏 | `connection.create`, target = SHA-256 of the body · `{key, provider, kind: "subscription"\|"api_key", display_name, base_url?, models[], default_model?, pricing, limits, fallback_priority?}` → `201 Connection` with `status: "pending_secret"` · `Idempotency-Key` (required) |
- **Waste** is computed by code at 07:45 owner TZ for the day before, from the ledger and the runs; it never stores prompt or response text
  (`duplicate_calls` and `cache_miss` use hashes the router keeps). Efficiency stars (§18.4) read the same table, so one day has one waste figure.
  The morning report carries one line; a share above 15% raises a `report` notification.
- **ROI:** revenue is attributed to companies only (§19.1); an employee's or a department's `revenue_usd` and `roi` are always null (commission
  cannot be traced to one agent, and no figure is invented). `value_points` = Σ (owner rating ÷ 10) over accepted deliverables.
- **A new connection's secret** is set either through the existing write-only `POST /connections/{id}/secret` 🔏 `connection.secret` (§10),
  which also moves a `pending_secret` connection to verification, or by the owner's `make connection-secret KEY=<key>` in their own terminal
  (hidden input, straight to OpenBao). Both stay open until the owner decides (default: the API route; with "terminal only" the route answers
  `409 validation_failed` for `pending_secret`). The router then verifies it with a call that costs no tokens (e.g. listing models, through
  egress) → `ready`, or `error` with `status_reason`. No response, log or audit row ever carries the secret. `provider` must be one the router supports; `base_url` only for `openai_compatible`, `https`, and through the egress
  guard (no private address). A duplicate `key` is `409 version_conflict`. It is used only through `PUT /assignments` 🔏.

- ⟨1.5⟩ **Other subscriptions** (owner, 2026-10-19): `chatgpt-plus` (provider `openai`) and `gemini-pro` (provider `google`) are connections of kind
  `subscription`, run through their official CLIs as model-only one-shot processes. How they are used — the substitute players — is §21.13.

### 21.8 Quick notes and cartable reminders (M9, M8)
```
OwnerNote { id, ref: "NT-0001", text_md, source: "text"|"voice", file_id|null, tags: [string],
            status: "open"|"promoted"|"archived", promoted_to: {kind: "work"|"order"|"errand", ref}|null,
            created_at, updated_at, version }
```
| Method | Path | Notes |
|---|---|---|
| GET · POST | `/notes` | owner only · `?status&q&cursor` · POST `{text_md, source, file_id?, tags?}` with `Idempotency-Key` |
| PATCH | `/notes/{ref}` | `text_md`, `tags`, `status: "archived"` · `If-Match`; no delete |
| POST | `/notes/{ref}/promote` | `{to: "work"\|"order"\|"errand", …}` → creates through §4, §17.4 or §18.3 and links it |
- `/transcribe?purpose=note&save=true` ⟨1.5⟩ also creates the note and returns `note_ref`. No model runs on notes; the advisor reads open
  notes only for the weekly review.
- **Reminders** (code, every 15 minutes), for cards the owner decides: at 50% of the time to expiry and 6 h before it; for cards without expiry at
  24 h, 72 h and 7 days. Each threshold once, a `decision`-level notification in the digest, held through Khalvat. `Decision` gains `waiting_h`
  and `reminders: [{at, kind: "half"|"before_expiry"|"age_24h"|"age_72h"|"age_7d"}]`.
  `owner_settings.reminders: {enabled, fraction: 0.5, before_expiry_h: 6, ages_h: [24, 72, 168]}`.
- Stream: `note.created` on topic `notes`; `decision.reminded` on topic `decisions`.

### 21.9 The agent health board and refuted claims (M16)
```
Claim       { id, ref: "CL-0001", company, deliverable: "O-…", employee, claim_md (≤ 300, masked),
              verdict: "confirmed"|"refuted"|"unverifiable", checked_by: Actor, protocol: "PR-…"|null, evidence: [{kind, ref, note}], at }
AgentHealth { employee, company, period: "7d"|"30d", runs, failed_share, refused_share, retry_loops,
              owner_returns, claims_checked, refuted, refuted_share|null, cost_usd,
              flags: ["truth"|"reliability"|"loops"] }
```
| GET | `/claims` | `?company&employee&verdict&cursor` |
| GET | `/runs/health` | `?company&period=7d\|30d&cursor` — one row per employee |
- Agent tool `claim.verdict` (A2: fact checker, overseer, QC); `refuted` without evidence → `422`. Flags are rules: `truth` refuted share ≥ 20% with
  at least 5 checked · `reliability` failed share ≥ 25% · `loops` two or more retry loops in the period. Refuted claims feed the HR facts (§21.5).
- Stream: `claim.verdict` on topic `quality`.

### 21.10 The digital CEO: prediction only (OPERATING_MODEL §1.8)
```
Prediction { decision: "D-…", made_at, method: "baseline"|"model", verdict: "approve"|"reject"|"return", confidence: 0..1,
             rationale_fa|null, principles: ["DP-…"], sealed_hash, seen_before: bool,
             actual: "approve"|"reject"|"return"|null, correct: bool|null }
Principle  { id, ref: "DP-001", text_fa, sources: [{kind, ref}], status: "proposed"|"active"|"retired",
             edited_by_owner: bool, version, updated_at }
DceoStats  { window: "30d"|"90d"|"all", n, accuracy|null, baseline_accuracy|null, model_accuracy|null, brier|null,
             by_kind: {kind: {n, accuracy}}, calibration: [{bucket: "0.5-0.6", n, hit_rate}] }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/digital-ceo` | stats for the three windows and `owner_settings.digital_ceo` |
| GET | `/digital-ceo/predictions` | `?correct&kind&cursor` — decided cards only (or all while `reveal: "before"`) |
| GET · POST | `/digital-ceo/principles` | POST: the owner adds one (`active`) |
| PUT | `/digital-ceo/principles/{ref}` | edit or retire = a new version · `If-Match` |
| POST | `/digital-ceo/principles/{ref}/accept` | a `proposed` principle becomes `active` |
- **It never acts.** It is a service (`service:dceo`), not an agent: no Gateway tool, no thread, no notification; policy refuses every write but
  its own `dceo.*` rows. It never approves, rejects, messages or notifies, at any accuracy. Its label in every client is «مدیر کل دیجیتال».
- **Every card the owner decides** gets a prediction **before** the decision: a baseline (the owner's past approval rate by kind, risk and proposer
  kind, Laplace-smoothed; no model) and, for medium- and high-risk cards, a model prediction (`dceo_predict`, light model, ≤ 8 000 tokens, at most
  `owner_settings.digital_ceo.max_model_per_day`, default 20). Each is sealed (`sealed_hash` of its canonical JSON, one audit row); a prediction
  written after `decided_at` is discarded.
- **Hidden until the owner decides** by default (`owner_settings.digital_ceo.reveal: "after"`): `Decision.digital_ceo_prediction` is null while
  the card is pending, then `{verdict, confidence, method, correct}`. **§5.1 changes to this shape** ⟨1.5⟩:
  `digital_ceo_prediction: { verdict: "approve"|"reject"|"return", confidence: 0..1, method: "baseline"|"model", correct: bool|null }|null`
  (it was `{verdict: "approve"|"reject", confidence}`). With `reveal: "before"` the owner sees it at once and those predictions are
  `seen_before: true`, outside the clean accuracy figure; the setting warns while fewer than 30 hidden predictions exist.
- **Principles:** each Saturday 11:00 a model run (`dceo_principles`, ≤ 120 000 tokens) reads the week's owner interactions (masked) and the
  missed predictions and proposes up to 5 new or changed principles with their sources; the owner accepts, edits or retires them. The owner
  always sees what is recorded about them (§2, `/owner/interactions`).
- Stream: `dceo.scored` on topic `dceo` (after the decision only).

### 21.11 MCP servers in containers (completes §18.13)
- `McpServer.transport: "container"` is accepted when its `key` and `image` (pinned **digest**) match the reviewed allow-list on the hub
  (`infra/mcp/servers.yaml`: image, command, licence, source, expected tools, memory limit); otherwise `422 validation_failed`. A server that
  needs the internet or a secret is `409 not_ready` (a later version).
- Each one runs as its own service on the internal network `hq-mcp` (no route out; the gateway is the only other member), non-root, read-only,
  no capabilities, never the Docker socket; a stdio server is served over Streamable HTTP by `mcp-proxy` (MIT) inside the same image.
- Everything of §18.13 holds unchanged: the two owner seals, the sealed class per tool, the listing pin and `tool_enable` card, A3 to a card,
  redaction, `mcp_calls`.
- The reference server `time` (`mcp-server-time`, MIT; `get_current_time`, `convert_time`, A0) is proposed `pending` for the owner's seal.
- Adding another container server is a reviewed change to the allow-list on the server, then the owner's seals in the app.

### 21.12 Kinds, stream, step-up, settings ⟨1.5⟩
- **Decision kinds:** none new. `evaluation` payload v2 (§21.5) and the one `deploy` payload definition (§21.6). `evaluation` joins the 🔏 list of
  §5.1 (target = ref). `Decision.digital_ceo_prediction` takes the shape of §21.10.
- **Step-up targets:** `connection.create` (body hash); `connection.login` (id), `substitute.seats` (body hash), `substitute.web_logout` (§21.13).
- **Stream topics:** `advisor` (`memo.ready`, `advisor.proactive`) · `ask` (`ask.answered`) · `reviews` (`review.updated`) · `briefings`
  (`briefing.ready`) · `stars` (`rankings.updated`) · `people` (`hr.round`) · `notes` (`note.created`) · `decisions` (`decision.reminded`) ·
  `quality` (`claim.verdict`) · `dceo` (`dceo.scored`) · `treasury` (`substitute.updated`) · `creatives` (`creative.updated`).
- **`/owner/settings` gains:** `advisor: {auto_memo: {enabled, max_per_day}, proactive_per_day}`, `weekly_review: {enabled, day, at}`,
  `audio_briefings: {morning, ceo_letters}`, `ceo_weekly_letter: {enabled, day, at}`, `reminders: {enabled, fraction, before_expiry_h, ages_h}`,
  `digital_ceo: {enabled, reveal: "after"|"before", model_predictions, max_model_per_day}`, `substitutes: {behind_ratio, creative_default_image}`.
- **Agent tools** (agents/tools.md): `memo.write` (A1, advisor), `ask.answer` (A1, librarian), `claim.verdict` (A2, fact checker, overseer, QC),
  `substitute.call` (A0, advisor, overseer, assistant, CEOs; `code_review` also CTOs and QC; §21.13); `knowledge.search` kinds `docs`, `code`, `notes` as in §21.2.
- **Task classes** (§21.13): `sub_code_review`, `sub_second_opinion`, `sub_cross_check`, `sub_errand`, `sub_draft`, `sub_long_read`, `sub_creative`.
- **Error codes:** none new (`rate_limited`, `not_ready`, `decision_not_pending`, `envelope_exceeded`, `channel_not_configured` cover every case).
- **Protocols:** `PR-082` (monthly HR evaluation) becomes `active`, scheduled on the 3rd of each **Jalali** month: the protocol registry gains an
  optional `calendar: "gregorian"|"jalali"` (default `gregorian`); with `jalali`, `BYMONTHDAY` is a day of the Jalali month. The key enters
  `agents/protocols/oversight.yaml` only with prompt 12, together with PR-082's new check ("…an `evaluation` card for every flagged employee");
  the loader ignores an unknown key with a warning, never an error.
- **Repositories:** nothing here asks the owner for a GitHub token; the hub's existing git access is used, and what it cannot read is `not_indexed`
  or `no_access`.

### 21.13 Substitute players: ChatGPT and Gemini (owner, 2026-10-19) ⟨1.5⟩
> The owner's words: **Claude Code holds the whole project, comprehensive and integrated; Gemini and GPT are substitute players
> (بازیکن ذخیره), called onto the pitch for one task at a time.** The owner pays for ChatGPT Plus and Google AI Pro (18 months, about $20 a
> month each), so both are used through the month, in two ways (owner, the same day):
> - **their coding models** (GPT 5.5 and 5.3 through Codex, Gemini 3.8 through Gemini CLI) for reviews, second opinions, errands, drafts and
>   long reads, called by code and by agents;
> - **ChatGPT's own chat and image generation, and Gemini's images and videos**, on the owner's unlimited plans, for the companies' ad
>   creatives (a Telegram channel post, an Instagram story) that an agent asks for with a precise brief — **through a signed-in browser on
>   the hub (Playwright), the way the owner already ran it on their own server** (owner's decision: this path, no other).
> - **DeepSeek's free chat** (owner, 2026-10-22), a third player on the same signed-in browser path, with its web search: quick searches
>   that would otherwise spend Claude tokens, and a third opinion when models consult each other.

**The rules of the bench**
- **Claude holds the project.** Code, decisions, verdicts, findings, customer-facing text, every A2+ act and every final deliverable stay with
  the Claude agent in charge. A substitute answers one bounded question: no thread, no memory, no write path; it never speaks to a customer and
  never publishes. Its own tools are off, except that a code review reads a read-only checkout (seat `code_review`).
- **What it receives** is masked (redaction §16.6) and passes the egress data guard (§18.7): never customer data or conversations, secrets, or
  another company's files. **Repository code** only in `code_review`: a read-only checkout of a repository the hub already reads, without the
  files the secret scan flags (the rule of §21.2).
- **What it returns is labelled and is never evidence.** Every output carries `source: {player, model, connection, at}` and is shown with the
  provider's logo. No finding is raised, closed or disputed, and no claim confirmed or refuted, on a substitute's word alone.
- **Who calls them:** code, at the fixed seats below, or a Claude agent with `substitute.call`. The caller stays answerable for what it does
  with the answer.

```
Substitute { player: "gpt"|"gemini"|"deepseek", connection: "chatgpt-plus"|"gemini-pro"|"deepseek-free",
             runner: "codex_cli"|"gemini_cli"|null,                               // DeepSeek has no CLI: web only
             login: {state: "signed_out"|"signing_in"|"signed_in"|"expired", plan_fa, since|null, last_ok_at|null},
             status: "ready"|"limited"|"off"|"error", limited_until|null, status_reason|null,
             models: [{id, label, tier: "strong"|"light", available: bool}],      // checked against what the CLI offers under the subscription
             capabilities: {text: Cap, image: Cap, video: Cap},                   // Cap = "cli"|"web"|"api"|"off"
             web: {account: "chatgpt-web"|"gemini-web"|"deepseek-web", state: "signed_in"|"expired"|"signed_out", last_ok_at|null,
                   recipe_version, last_failure|null},                             // the signed-in browser profile (below)
             seats: [{seat, via: "cli"|"web", model, enabled, per_day, used_today}],
             month: {key (Jalali, "1405-08"), calls, skipped, input_tokens, output_tokens, estimated: bool,
                     equiv_usd, price_usd, value_ratio|null}, version }          // value_ratio = equiv_usd ÷ price_usd; null for a free account
SubstituteLogin { id, connection, method: "device_code"|"auth_code", verification_url, user_code|null, expires_at,
             state: "waiting"|"done"|"expired"|"failed", status_reason|null }
Creative   { id, ref: "CR-0001", company, kind: "image"|"video", brief_md, prompt_md,
             placement: "telegram_post"|"telegram_story"|"instagram_post"|"instagram_story"|"banner"|"other",   // sets aspect and safe zones
             aspect: "1:1"|"4:5"|"9:16"|"16:9", duration_s|null,                     // video only, ≤ 10
             overlay: {title_fa, body_fa|null, cta_fa|null, mark: bool}|null,         // Persian text set by the hub, never generated
             composed: FileRef|null,                                                  // the generated file with the overlay, by code
             player: "gpt"|"gemini", model, path: "web"|"cli"|"api",
             state: "queued"|"generating"|"review"|"accepted"|"rejected"|"failed",
             requested_by: Actor, work_ref|null, errand_ref|null, files: [FileRef], review_md|null,
             source: {player, model, at}|null, ai_generated: true, created_at, updated_at, version }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/substitutes` | owner · both players |
| PUT | `/substitutes/{player}/seats` 🔏 | `substitute.seats`, target = SHA-256 of the body · `[{seat, via, model, enabled, per_day}]` · `If-Match` |
| POST | `/substitutes/{player}/web/logout` 🔏 | `substitute.web_logout`, target = player · wipes the signed-in browser profile |
| POST | `/connections/{id}/login` 🔏 | `connection.login`, target = id · a subscription connection run by a CLI → `201 SubstituteLogin`; the CLI offers no headless sign-in → `409 not_ready` (the app shows the terminal command) |
| GET | `/connections/{id}/login/{login_id}` | poll while `waiting` |
| POST | `/connections/{id}/login/{login_id}/code` | `{code}` **write-only**, `auth_code` logins only, while `waiting` (covered by the start's step-up; at most 10 minutes) |
| POST | `/connections/{id}/logout` 🔏 | target = id · removes the stored sign-in |
| GET · POST | `/creatives` | `?company&state&kind&cursor` · POST (owner) `{company, kind, brief_md, placement, overlay?, duration_s?, player?}` · `Idempotency-Key` |
| GET | `/creatives/{ref}` | |
| POST | `/creatives/{ref}/accept` · `/reject` | owner · `{note?}` |

**Seats** (defaults; the owner changes them in the app). `strong` = GPT 5.5, `light` = GPT 5.3 (fewer credits), Gemini = 3.8 (the owner's
choice; less trusted for accuracy, so by default it gets drafts, long reads and creative work, and a check only as an extra signal). A seat
may be held by either player; the table gives the default holder. A text seat runs `via: "cli"` by default (the coding models, measured and
fast); the owner may switch it to `via: "web"` to use the unlimited chat in the browser instead. Model ids are data in the connection's
`models[]`: one the CLI does not offer is `available: false`, the seat falls to the nearest available model of the same tier, and the morning
report says so.
⟨1.7.2⟩ **Gemini CLI for individuals is gone** (2026-10-23: Google answers the CLI's "Sign in with Google" with «This client is no longer
supported for Gemini Code Assist for individuals», pointing to Antigravity). So every Gemini seat runs `via: "web"` (the signed-in browser
profile, below); the Gemini CLI runner reports the player `unavailable` with that reason and never asks for an API key. `code_review` stays
with GPT (Codex CLI). An API-key Gemini connection (paid) remains possible through §21.9.
| Seat | Player · model | What it does | Per day |
|---|---|---|---|
| `advisor_second_opinion` | gpt · strong | An independent opinion on the same masked facts pack as a decision memo (§21.1), **without** the advisor's memo. `DecisionMemo.second_opinion: {player, model, recommendation, confidence, summary_fa (≤ 600), differences: [string], agrees: bool}\|null`; `agrees` is code (same `recommendation`). A disagreement shows on the card and in the weekly review. | 3 |
| `code_review` | gpt · strong (gemini: off until the owner turns it on) | A second review of a change: a deploy card's PR (§21.6), a founding's repository audit (§18.8), a Code Workshop session's diff. The CLI reads a read-only checkout at `head_sha` with the diff (Codex in its read-only sandbox; Gemini CLI with read-only file tools only) and returns `findings: [{path, line, severity, title_fa, detail_md}]`. The CTO or QC verifies each; the verified ones go into the card's `risk_note`. `deploy` gains `second_review: {player, model, findings, verified}\|null`. It never approves or blocks. | 10 |
| `overseer_cross_check` | gpt · strong | A second check of the claims a `sample` protocol picked (`PR-001`, the fact checker's sample) before the verdict. Disagreement sends the claim back to the overseer; it never decides it. | 20 claims |
| `assistant_errand` | gpt · light | The assistant's drafting steps: summary, translation, rewrite, a draft email or post. The assistant checks and finishes the errand. | 30 |
| `content_draft` | gemini | First drafts of company content (captions, titles, meta descriptions, variations) for the agent in charge to edit. | 30 |
| `long_read` | gemini | A summary of a long masked document or log, with page or line anchors the caller verifies. | 10 |
| `quick_search` | deepseek · `via: "web"`, thinking and search on | A fast answer, with its sources, to a quick public question an agent would otherwise spend Claude tokens searching for. The query passes the same data guard as `web.search` (nothing internal). The caller reads each cited source itself (`web.read`) before a fact or a figure is used; the answer alone is never evidence. | 60 |
| `third_opinion` | deepseek · `via: "web"` | A third independent opinion beside the advisor's memo and GPT's second opinion (the same masked facts pack, no other opinion shown), and an extra voice whenever a seat or an agent consults several models. `DecisionMemo` gains `third_opinion`, the shape of `second_opinion`. | 5 |
| `creative` | gpt or gemini · `via: "web"` | Images (ChatGPT, Gemini), and videos of at most 10 s (Gemini), for ads and teasers (below). | 20 images · 3 videos |
- **Task classes:** `sub_code_review`, `sub_second_opinion`, `sub_cross_check`, `sub_errand`, `sub_draft`, `sub_long_read`, `sub_creative` (in `/assignments`, on
  the two subscription connections only).
- **Nothing falls back silently.** A player that is `limited`, signed out or `off` makes its seat `skipped` (counted in `month.skipped`); the
  caller carries on with its own model. A Claude run is never moved to a substitute, and a substitute seat is never moved to Claude.
- **Their own limits.** Substitute calls count neither against the agents' daily token cap nor against the oversight or owner-zone shares; they
  are bounded by the subscription's quota and each seat's `per_day`. The ledger records them at their equivalent cost.
- **Use through the month:** `month` comes from the CLI's own usage report (`estimated: true` when it gives none); `equiv_usd` from the price
  table (§10). The morning report carries one line per player; when `value_ratio` is under `owner_settings.substitutes.behind_ratio` (default
  0.4) on the 15th of the Jalali month, a `report` notification suggests seats to widen. Nothing widens by itself.

**Images and videos** (`creative`)
1. The owner (`POST /creatives`) or an agent (`substitute.call` with `seat: "creative"`) asks, e.g. «تصویر تبلیغ کانال تلگرام FX برای
   آموزش رایگان» with `placement: "telegram_post"`. **The Claude agent in charge writes `prompt_md`** from the brief, the placement and the
   company's brand (§18.14); the substitute only renders. The prompt asks for **no text inside the image**.
2. **Persian text is set by the hub, never generated:** `overlay` (title, body, call to action, the company's mark) is composed over the result
   by code (IRANYekanX, the brand palette, the placement's safe zones; resvg) → `composed`.
3. **The path is the web** (`path: "web"`): the image or video is made in ChatGPT or Gemini themselves, in the signed-in browser profile on
   the hub (below), on the owner's unlimited plan. `cli` is used only if the official CLI can make it under the subscription; `api` only if the
   owner adds an API-key connection (paid). Nothing waits on the owner to make a file.
4. `review`: the agent in charge checks the composed result against the brief (vision; a video's key frames) and writes `review_md`; the owner
   accepts or rejects. Every creative is `ai_generated: true`. Publishing one anywhere (the channel, the story) is an external act: a decision
   (A3), as always.

**The web path: a signed-in browser on the hub** (the owner's own method, from their server)
- **Where:** the egress service's real browser (Playwright, Chromium; §18.7), with a **persistent profile per player**: two holding service
  accounts, `chatgpt-web` (chatgpt.com), `gemini-web` (gemini.google.com) and `deepseek-web` (chat.deepseek.com).
  `ServiceAccount.policy.browse.kind` gains `"profile"`. The
  profile lives in a volume only the egress browser mounts for that account (files `600`, not in backups); browsing with it is limited to
  that site's own hosts; no model ever sees its cookies.
- **Sign-in, once, by the owner:** `make chatgpt-web-login`, `make gemini-web-login` or `make deepseek-web-login` in their own terminal opens that profile in a visible
  browser for at most 15 minutes, shown through noVNC (MPL-2.0) bound to `127.0.0.1` only, which the owner reaches through their own SSH tunnel
  (`ssh -L`). The owner signs in and closes it; the hub never sees the password. A signed-out or expired profile → `web.state: "expired"`,
  the seats that use it are `skipped`, and one `report` notification asks the owner to sign in again.
- **Rules first, AI last:** each job runs a reviewed **recipe** (`infra/egress/recipes/chatgpt-web.yaml`, `gemini-web.yaml`, `deepseek-web.yaml`;
  in DeepSeek **both its deep-thinking and its web search are always on** (owner, 2026-10-22) and nothing else of the site is used): open a new chat
  (a temporary one when the site offers it), paste the prompt, wait for the result (image ≤ 3 min, video ≤ 10 min), download the original,
  close. When a recipe fails because the site changed, **one Claude run** finishes the same job with `web.browse` on that account
  (screenshots; never a secret) and writes the recipe fix as a reviewed change; until it is merged, jobs use that fallback.
- **Pace:** one browser job per player at a time, at least 60 s apart, inside the seat's daily cap.
- **What goes in:** only the prompt the Claude agent wrote, masked like every substitute input; never customer data.
- **What comes out:** every download goes through §17.1's processing (type by content, EXIF stripped, size limits) before anything uses it.
- **Text on the web:** a text seat switched to `via: "web"` sends its masked question to the chat the same way and reads the answer from the
  page.

**Sign-in for the CLIs, from the app or the terminal.** From the app: step-up → the runner starts the CLI's own headless sign-in (a device code, or a
browserless auth code) and returns `verification_url` (and `user_code`); the owner signs in on their phone and, for `auth_code`, pastes the
code back. From the terminal: `make chatgpt-login`, `make gemini-login`. The credential lives only in a volume the runner mounts (files `600`,
not in backups; if lost, the owner signs in again). No response, log or audit row carries it; neither the API nor any Claude reads it.

**The runner.** One image with both CLIs, run one-shot per call (input on stdin, never in argv), one call at a time for both players together,
with an empty tmpfs working directory, a read-only root, no hub network, and egress only to the hosts the CLI needs (pinned in the egress
allow-list). The CLIs' own tools are off: Gemini with no core tools, Codex in its read-only sandbox. For `code_review` only, the repository's
checkout is mounted read-only as the working directory and the CLI may read it (Gemini: its read-only file tools; no shell, no write, no web).
Its memory limit is measured and passes the memory gate, or it stays off.

- **Agent tool** `substitute.call` (A0; advisor, overseer, assistant, CEOs; `code_review` also the CTO and QC; ⟨1.6⟩ `creative` also the media
  director, motion designer, visual designer and UI designer, §22): `{seat, player?, input_md,
  file_ids?, repo?, head_sha?, kind?: "text"|"image"|"video", placement?, overlay?, duration_s?}` → `{text_md, source}`, `{findings, source}`
  or `{creative: "CR-…", state}`. Refusals: `channel_not_configured` (signed out or `off`),
  `rate_limited` (the seat's daily cap, or the player is `limited`), `policy_denied` (a seat the role may not use, or input the data guard refuses).
- **Step-up targets:** `connection.login` (id), `substitute.seats` (body hash), `substitute.web_logout` (player). **Stream:** `substitute.updated` on topic `treasury`,
  `creative.updated` on topic `creatives`. **Settings:** `owner_settings.substitutes: {behind_ratio, creative_default_image: "gpt"|"gemini"}`.

### 21.14 Shapes as the apps read them ⟨1.5.1⟩
Written with the web and Android screens (2026-10-22). Where §21.1–§21.13 leave a shape open, this is the contract.
- **Empty states:** when there is nothing yet, these answer `404 not_found`: a decision with no memo, no current weekly review, no briefing yet.
- **Memos and messages:**
  - `DecisionMemo.third_opinion` is optional.
  - Advisor messages carry `meta: {mode?: "devil", proactive?: {kind, key}, review?}`; the owner's own devil-mode message stores `meta.mode` too.
- **Weekly review:** `POST …/start`, `…/finish` and `PATCH …/items/{n}` each return the whole `WeeklyReview`.
- **Deploy card:**
  - `GET /decisions/{ref}/diff?file=` returns one `files[]` row with its whole patch and `truncated: false`.
  - `deploy.second_review.verified` is `bool|int`; each finding may carry `verified: true|false|null`.
- **Waste and ROI:**
  - `WasteDay.vs_7d` is the relative change against the 7-day average.
  - `RoiRow.trend` is ROI for companies, and cost per accepted deliverable for departments and employees.
- **New connection:**
  - Providers: `anthropic`, `openai`, `google`, `deepseek`, `mistral`, `openai_compatible`.
  - `pricing` is `{<model>: {input_per_mtok, output_per_mtok}}`; `limits` is `{rpm?, tpm?, daily_usd?}`.
  - `status` gains `verifying` between created and ready.
  - The substitute accounts (`chatgpt-plus`, `gemini-pro`, `deepseek-free`) are listed in `/connections` with `kind: "subscription"`; sign-in goes by connection id.
- **Notes:** `POST /notes/{ref}/promote` `{to, company?, title?}` (`company` required when `to` is `work`).
- **Digital chief:**
  - `Prediction` also carries the card's `kind` and `title`.
  - `GET /digital-ceo` → `{stats: [3 windows], settings, hidden}`.
  - Editing or retiring a principle sends `{text_fa, status}`.
- **Creative:**
  - Seats show `per_day_video` and `used_today_video` beside the image cap.
  - A failed creative carries its reason in `review_md`.
  - Aspect hints by placement: `telegram_post` 16:9, `telegram_story` 9:16, `instagram_post` 4:5, `instagram_story` 9:16, `banner` 16:9, other 1:1.
- **CLI sign-out:** 🔏 action `connection.logout`, target = the connection id.
- **HR:** `HrRound.month` is the Jalali month the round runs in; the round shows `due_at`.
- **Owner settings:** `PUT /owner/settings` (If-Match) sends each changed §21.12 block whole.

## 22. v1.6 — the media studio and the legal counsel (prompt 13)

> **v1.6 (2026-10-22).** The owner's decisions of 2026-10-22: every company gets a **media department** that makes its posts, stories and
> reels every day by itself (scriptwriter, director, motion graphics written by Opus 5.5, a voice made on the hub, images from the
> substitute players), redesigns its sites' UI, and publishes **through series the owner seals once**; and the holding gets **one legal
> counsel** for all companies, who handles platform restrictions, appeals and correspondence by email. The owner no longer has to do this
> work by hand in Claude. Everything above still holds: A3 needs the owner's seal (here, once per series or per email), A4 never happens.

### 22.0 Principles ⟨1.6⟩
- **A department is defined by its mandate, not by a fixed list of roles** (owner, 2026-10-22: «نباید محدود کنیم به یه سری نقش‌ها؛ فقط
  مبدأ و مقصد مشخص باشه و شخصیت دپارتمان و مدیر بخشش»). Each department has a **mandate** (where it starts, where it must arrive, what it
  delivers, its limits) and an **identity**; its manager writes **any role the work needs** (§22.5). The team blueprint is only where it
  starts.
- **Media is made by code where code can, and by models only where it must.** The schedule, the checks, the rendering, the captions, the
  Persian text on images and the publishing are code. Models write the script, the direction and the motion-graphics composition.
- **Publishing only through official APIs** (Telegram Bot API, Instagram Graph API for business accounts), never through a browser session
  or cookies. What an official API cannot publish (a Telegram channel story) becomes a card with the file for the owner to post.
- **The seal is on the series, not on every post.** A sealed series publishes an item automatically only when every check passed; anything
  outside the series, or any failed check, is a card.
- **Every outgoing email of the counsel is the owner's seal**, on the exact message.
- New **task classes**: `media_script`, `media_direction`, `media_motion`, `media_review`, `ui_design`, `legal_case`, `legal_email`.

### 22.1 Department mandate, identity and starting team ⟨1.6⟩
```
Department { …§3.2,
             mandate: { from_fa, to_fa, outputs_fa: [string], boundaries_fa: [string],      // «مبدأ و مقصد»: what it starts from, what it must reach
                        tool_ceiling: [tool], model_ceiling: "claude-haiku-5-5"|"claude-sonnet-5-5"|"claude-opus-5-5" },
             identity_md,                                                            // the department's character, tone and taste; every member reads it
             team: [{role, title_fa, why_fa, first: bool}],                          // a starting suggestion, never a limit
             version }
```
| Method | Path | Notes |
|---|---|---|
| PUT | `/companies/{code}/departments/{dept}/mandate` 🔏 | owner · `department.mandate`, target = SHA-256 of the body · `{mandate, identity_md}` · `If-Match` |
- Seeded from the template; the owner changes them in the app. `GET /templates` and `company.state` return them.
- The runtime puts the department's `identity_md` after the charter (and before skills) in the system prompt of the manager and every
  employee of that department, and records its version on the run.
- `team` lists existing charters the manager may start with; a role the work needs and the list lacks is written by the manager (§22.5).
- **The standard template gains `MEDIA`** («رسانه و طراحی», head role `media_director`, sort 25) with the team `scriptwriter`,
  `video_director`, `motion_designer`, `voice_producer`, `visual_designer`, `ui_designer`. Existing companies get the department (and its
  asleep manager) by migration; no employee is created.
- **The holding template gains `LEGAL`** («حقوقی») with the seeded holding employee **`HQ-LGL`** («مشاور حقوقی», charter `legal_counsel`),
  asleep until work arrives, like `HQ-PA`.

### 22.2 The media studio ⟨1.6⟩
```
Series    { id, ref: "SR-0001", company, title_fa, kind: "reel"|"story"|"post"|"carousel",
            targets: [{channel: "telegram"|"instagram", account: <service account key>,
                       placement: "telegram_post"|"telegram_story"|"instagram_reel"|"instagram_story"|"instagram_post"}],
            schedule: RRULE (owner TZ), topics: {pool: [string], rule_fa}|null,
            format: {aspect: "9:16"|"4:5"|"1:1"|"16:9", duration_s|null, voice: {voice_id}|null, captions: bool, music: "none"|"library",
                     overlay: {cta_fa|null, mark: bool}},
            checks: ["brand", "red_lines", "risk_warning", "facts", "rights", "platform", "qc"],
            auto_publish: bool, max_per_day, status: "draft"|"proposed"|"sealed"|"paused"|"retired",
            digest, version, sealed_at|null }
MediaItem { id, ref: "MI-0001", company, series: "SR-…"|null, kind: "reel"|"story"|"post"|"carousel"|"design", title_fa,     // `design`: UI mockups, never published
            state: "scripting"|"directing"|"composing"|"voicing"|"rendering"|"checking"|"review"|"scheduled"|"published"|"waiting_owner"|"held"|"failed"|"rejected",
            script: {text_fa, sources: [{kind, ref|url, note}], by: Actor}|null,
            direction: {shots: [{n, duration_s, visual_fa, text_on_screen_fa|null, voice_fa|null}], by: Actor}|null,
            composition: {format: "html"|"lottie", sha256, by: Actor}|null,
            assets: [FileRef], voice: FileRef|null, render: FileRef|null, captions: FileRef|null,
            checks: [{key, result: "pass"|"fail"|"n/a", note_fa|null}], qc: {by: Actor, verdict: "pass"|"changes"|"reject", note_md}|null,
            publish: [{channel, placement, at|null, external_id|null, url|null, error|null}],
            decision_ref: "D-…"|null, ai_generated: true, cost: {tokens, usd}, created_at, updated_at, version }
Voice     { id, engine, name_fa, licence, licence_commercial: bool, rtf, mem_mb, owner_score|null, status: "candidate"|"active"|"retired" }
```
| Method | Path | Notes |
|---|---|---|
| GET · POST | `/media/series` | `?company&status` · POST (owner or the media director's proposal) creates a `draft` |
| PUT | `/media/series/{ref}` | `If-Match`; a sealed series edited goes back to `proposed` (its seal no longer covers it) |
| POST | `/media/series/{ref}/seal` 🔏 | `media.series`, target = the series `digest`; `/pause` and `/retire` need none |
| GET | `/media/items` · `/media/items/{ref}` | `?company&series&state&cursor` |
| POST | `/media/items` | owner · `{company, kind, brief_md, series?}` — a one-off item; one-offs always end as a card |
| POST | `/media/items/{ref}/publish` | owner · publishes a `waiting_owner` item now (its card's approval does the same) |
| POST | `/media/items/{ref}/unpublish` 🔏 | `media.unpublish`, target = ref · deletes the post through the same API where the platform allows it |
| GET | `/media/voices` · POST `/media/voices/{id}/score` | the voice registry; the owner's blind listening score 1–10 |
- **The pipeline** (each step a work item to the role, woken in order; code moves the item on):
  1. A sealed series' schedule creates the item (code) with the next topic from its pool (or the rule).
  2. **Script** (`scriptwriter`): Persian, with a source for every claim and figure; trading content carries the risk warning.
  3. **Direction** (`video_director`): shot list, timing, what is on screen and what is said.
  4. **Composition** (`motion_designer`, Opus 5.5 by default): the motion graphics **as code**: one HTML document (CSS animations, SVG, the
     Web Animations API, `anime.js` MIT) or a Lottie JSON (`lottie-web` MIT), from a constrained schema: no network, no script outside the
     allowed libraries, IRANYekanX the only font, the company's palette and mark (§18.14). Images come from the company's files or
     `substitute.call` `creative` (§21.13).
  5. **Voice** (`voice_producer`): the narration with the hub's TTS (§22.3); timing aligned to the shots.
  6. **Render** (code, sandboxed render worker): headless Chromium renders the composition frame by frame; `ffmpeg` muxes voice, music from
     the owner's licensed library (if any) and burned-in Persian captions; output per `placement` (size, codec, length).
  7. **Checks** (code): `brand` (font, palette, mark), `red_lines` (the charter's patterns, §20.2, on script and captions), `risk_warning`
     (present on trading content), `facts` (every figure in the script has a source), `rights` (only own, generated or licensed assets),
     `platform` (aspect, length, size, the platform's own limits), `qc` (the media director's review, `media.review`).
  8. **Publish** (code): a sealed series with `auto_publish` and every check `pass` → at the scheduled time through the official API with the
     company's service account. Otherwise `waiting_owner` and a `media_publish` card (A3). Instagram media are created with
     `is_ai_generated: true`; Instagram fetches the file from a **signed URL valid for that one file for ≤ 15 minutes**. A Telegram channel
     story has no Bot API: it is always a card with the file.
- **Limits:** `max_per_day` per series and the platform's own limits (Instagram: 50 API posts a day per account); the company's kill switch,
  deploy freeze, holds and watch mode stop publishing like any other act; the company's monthly token envelope pays for the models.
- **UI redesign** (`ui_designer`): a design deliverable — the redesigned pages as HTML mockups rendered to screenshots by the same render
  worker, images from the substitutes, the brand of §18.14 — handed to the CTO; building it is Code Workshop work and its deploy a card.
- A `design` item (the UI designer's) has the steps brief and composition only, renders screenshots, never reaches the checks for
  publishing, and ends as a deliverable.
- Agent tools: `media.item` (A1, the item's current step for its role; `design` items: the UI designer), `media.render` (A2, queue the item's render), `media.voice` (A2,
  TTS for the item), `media.review` (A2, the media director only), `series.propose` (A1, a series card for the owner).
- Stream: `media.item` on topic `media`. Decision kinds: `media_series` (🔏 on the series digest), `media_publish` (A3).

### 22.3 Voice: open source, on the hub, chosen by ear ⟨1.6⟩
- **No paid voice service** (owner, 2026-10-22: «پولی به ElevenLabs ندیم»). Speech is made on the hub by an open-source model, shared with
  the spoken briefings of §21.4.
- **Chosen by a measured bake-off:** each candidate speaks the same Persian test scripts (numbers, Latin terms, crypto words, a long
  sentence); the server records RTF and peak RAM on the hub's CPU; the owner listens blind in the app and scores (`owner_score`). The best
  commercially usable voice becomes `active`.
- **Candidates** (licences as their cards state them; the owner decides on any non-commercial one):
  - Piper `fa_IR` voices (MIT; fast, plain);
  - a voice the server trains on the **ManaTTS** corpus (CC0, 86 h, one female speaker) with a permissive architecture (Piper/VITS or
    Matcha-TTS, MIT); training needs a GPU for some hours — a rented one is a cost and the owner's decision;
  - permissive multilingual models (Apache-2.0 or MIT) if their own card lists Persian;
  - ParsVoice-XTTS (Coqui Public Model License) and the Persian Chatterbox fine-tune (CC BY-NC) are labelled non-commercial on their cards:
    measured, never activated without the owner's explicit choice.
  - **The owner's own voice** (owner, 2026-10-22): the candidates that clone from a short sample (ParsVoice-XTTS, Chatterbox) also speak the
    test scripts in the owner's voice, from a reference the owner records in the app (`POST /media/voices/reference` `{file_id}`, owner only,
    1–3 minutes of clean speech; stored like any owner file and never sent anywhere). The owner hears both and picks.
  - **The owner's choice (2026-10-22): ParsVoice-XTTS**, in the owner's own voice when a reference exists; the blind listening confirms it.
- Every `Voice` records its licence; `licence_commercial: false` is shown on every use.

### 22.4 The legal counsel ⟨1.6⟩
```
LegalCase { id, ref: "LC-0001", company, title_fa,
            kind: "platform_restriction"|"account_appeal"|"takedown"|"partner_dispute"|"policy_review"|"contract_review"|"compliance"|"other",
            counterpart: {name, channel: "email"|"form"|"portal"|"other", address|null},
            status: "open"|"waiting_reply"|"waiting_owner"|"resolved"|"closed",
            timeline: [{at, kind: "note"|"email_out"|"email_in"|"form"|"decision", ref|null, summary_fa}],
            deadlines: [{at, what_fa}], opened_by: Actor, created_at, updated_at, version }
EmailDraft { case: "LC-…", from, to: [addr], cc: [addr], subject, body_md, attachments: [FileRef], lang: "fa"|"en", digest }
```
| Method | Path | Notes |
|---|---|---|
| GET · POST | `/legal/cases` | `?company&status&cursor` · POST (owner, or a CEO through work) `{company, title_fa, kind, brief_md, file_ids?}` |
| GET | `/legal/cases/{ref}` | with the full timeline and the emails |
| POST | `/legal/cases/{ref}/close` | owner |
- **Thread `L`** («حقوقی», messages `L-0001`) is the owner's conversation with `HQ-LGL`; a CEO asks through a work item to the holding.
- **Email:** one holding mailbox (service account `mail`, IMAP and SMTP or the provider's official API; the owner enters it with
  `make account-secret`). `email.draft` (A1) makes a card of kind `email_send` with the **exact** message (from, to, cc, subject, body,
  attachment hashes); approving it (🔏, the card bound to the message `digest`) sends exactly that once. Incoming replies to a case's
  messages (by `Message-ID`/`References`) are read by code, masked, added to the timeline, and wake the counsel; **nothing is ever sent
  automatically**. Attachments go through §17.1.
- **Forms and portals** (an appeal form, a help-centre ticket): the counsel prepares the exact field values in a card of kind `a3_action`
  with `action: "form_submit"`, the form's page as `target` and the field values as `preview`; the owner submits it (it usually needs the
  account's own sign-in) and the counsel records the outcome.
- The counsel works only through official channels and published policies (each cited with its date), never pretends to be the owner or
  anyone else, never threatens, and says plainly when a matter needs a human lawyer.
- Agent tools: `case.open`, `case.note` (A1; `deadline?: {at, what_fa}` adds to `deadlines`), `email.draft` (A1 → card), `mail.read` (A0,
  the counsel's own cases only).
- Stream: `legal.case` on topic `legal`. Decision kind: `email_send` (A3, 🔏 on the message digest).

### 22.5 Roles written on demand ⟨1.6⟩
Any department can grow a role nobody listed: the owner says «یه تدوینگر پادکست میخوام» or the work shows the gap, and the department's
manager writes the role's charter. It goes through the same gates as every charter, and it can never give more than the department has.
```
RoleDraft { id, ref: "RD-0001", company, department, role (snake_case, unique in the company), title_fa, title_en, why_md,
            charter_md,                                                // the body, in the hub's charter format (§16.1)
            tools: [tool], model, effort, limits: {steps_per_run, tokens_per_step, tokens_per_run},
            eval: {suite: "EV-…", cases: [{id, input_md, rubric_md, weight}]},     // at least 3 cases written with the draft
            state: "drafting"|"in_review"|"eval"|"proposed"|"active"|"rejected"|"retired",
            review: {by: Actor, verdict, checks: {injection, secrets, conflicts, policy, ceiling}, sha256}|null, eval_run: EvalRun|null,
            approver: Actor|null, decision_ref|null, version, created_at, activated_at|null }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/roles/drafts` · `/roles/drafts/{ref}` | `?company&department&state` |
| POST | `/roles/drafts` | owner · `{company, department, brief_md}` — the owner asks; the manager is woken to write it |
| POST | `/roles/drafts/{ref}/retire` | owner · stops new hires on it; employees on it keep running until moved or dismissed |
- **Who writes:** the department's manager, with `role.draft` (A1), from the department's mandate and identity, after checking that no
  existing charter fits (it says which it compared). It writes the body, the tools, the model and the eval cases.
- **The ceiling is hard:** `tools` ⊆ the department's `tool_ceiling`, and never an oversight power, `hire.decide`, `role.decide`,
  `kill_switch.*`, `message.owner` or anything A4; `model` ≤ `model_ceiling`; `limits` ≤ the manager's own. Anything outside → `422`.
  `_common.md` always comes first at runtime, so A3 stays `propose` and A4 stays impossible whatever the body says.
- **Gates, in order:** the originality check (rule; staged hiring README) → the overseer's review with the full masked text and its sha256
  (§18.15; `ceiling` is a fifth check) → the eval run of its own cases (must pass; it also becomes the role's baseline) → approval.
- **Approval:** the company's CEO with `role.decide` (A2) when hiring is `delegated` and the draft is inside the ceiling; otherwise, and
  always for the holding, a `role_new` card for the owner (🔏). The owner sees every new role as a story («نقش تازه در …») and can retire it.
- **Where it lives:** an active draft is a charter **on the server** (a database row), scoped to its company and department; files in
  `agents/` are never written. The charter loader merges file charters and active drafts; `GET /roles` lists both (`source:
  "file"|"draft"`). A hire may name either (§16.6).
- **Changing it:** a new version is a new draft through the same gates; teachings and addenda work on it as on any charter (§18.6).
- Agent tools: `role.draft` (A1, department managers), `role.decide` (A2, CEOs). Stream: `role.updated` on topic `people`. Decision kind:
  `role_new` (🔏, target = ref). Step-up target: `department.mandate` (body hash).

### 22.6 Kinds, stream, step-up, codes ⟨1.6⟩
- **Decision kinds:** `media_series`, `media_publish`, `email_send`, `role_new` (all sealed with step-up, §5.1).
- **Step-up targets:** `media.series` (series digest), `media.unpublish` (ref), and `decision.approve` on `email_send` bound to the message
  digest.
- **Stream topics:** `media` (`media.item`), `legal` (`legal.case`).
- **`Thread.kind`** gains `legal` (code `L`).
- **Error codes:** `series_not_sealed` (409, an item asked to auto-publish outside a sealed series), `platform_limit` (429 with
  `Retry-After`, the platform's own publishing limit).

### 22.7 Shapes as the apps read them ⟨1.6.1⟩
Written with the web and Android screens (2026-10-22). Where §22.0–§22.6 leave a shape open, this is the contract.
- **Departments:**
  - `PUT /companies/{code}/departments/{dept}/mandate` (🔏 body hash) uses `Department.version` for If-Match and returns the Department.
- **Role drafts:**
  - `RoleDraft` gains `brief_md`, `requested_by`, `written_by`, `compared[]`, `originality {ok, closest, note_fa}`, `hires`, `retired_at`
    and `state_note_fa`.
  - `GET /roles` rows gain `source`, `company` and `draft`.
  - The `role_new` payload is `{draft, company, department, role, title_fa, model, effort, limits, tools_count, review, eval_score, sha256}`.
  - The role story is `Story.kind: "role"` with `links.role_draft`; retiring from the story needs no step-up.
- **Series:**
  - `MediaSeries` gains `proposed_by`, `decision_ref`, `next_at[]` (computed by the server from the RRULE in the owner's time zone),
    `today {made, published}`, `items_total`, `created_at`, `updated_at` and `status_note_fa`.
  - `POST …/seal` takes `{digest}`; a changed series answers `409 version_conflict`.
  - Sealing a paused series resumes it and decides any pending `media_series` card. A `media_series` card is sealed on the series page,
    never by the cartable's approve (`409 validation_failed`, like `server_plan`).
- **Media items:**
  - `MediaItem` gains `brief_md`, `topic_fa`, `deliverable_ref`, `state_note_fa` and `pages[]`. `FileRef` carries `width`, `height` and
    `duration_s`; a video's poster is `?variant=poster` (§17.1). A `design` item is never published.
  - **Publishing outside a sealed series has one path:** its `media_publish` card (🔏 `decision.approve`). There is no publish route an
    app calls.
  - `media_publish` payload: `{item, series, kind, title_fa, why, placements: [{channel, placement, account, via: "api"|"manual", blocked}],
    render, checks}`. `PublishRow.error` ∈ `no_api`, `account_not_configured`, `removed`, `remove_by_hand`, `platform_limit`.
    `external_id: "manual"` means the owner posted it from the card. After an unpublish the item becomes `rejected` with a note.
- **Platform limits:** `GET /media/limits` → `[{account, channel, company, per_24h|null, used_24h, resets_at, note_fa}]`. Publishing
  accounts are `/tools/accounts` keys `telegram-<co>`, `instagram-<co>` and `mail`.
- **Voice:**
  - `Voice` gains `speaker` (`model`|`owner`), `clones`, `samples: [{script, title_fa, text_fa, file}]`, `note_fa` and `measured_at`; each
    engine-and-speaker pair is its own row.
  - `GET /media/voices/reference` → 404 when none, else `{file, duration_s, created_at, state, reason_fa}`.
  - `POST /media/voices/{id}/activate` 🔏 `voice.activate` (target = id); a non-commercial voice needs `{accept_non_commercial: true}`
    (422 without it); an unmeasured voice answers `409 not_ready`.
- **Legal:**
  - `LegalCase` gains `brief_md`; `GET` one adds `emails[]` (an `EmailDraft` plus `{id, direction, state:
    "waiting_seal"|"sent"|"received"|"superseded"|"rejected", decision_ref, message_id, at}`).
  - An email's `digest` is SHA-256 of the canonical `{from, to, cc, subject, body_md, attachment sha256s, lang}`.
  - Rejecting or returning an email reopens the case; closing a case while an email waits for its seal answers 409.
  - Messages may link `case`, `media_item` or `series`.

## 23. v1.7 — the archive (prompt 14)

> **v1.7 (2026-10-22).** The owner's decision: the holding and every company get an **archive of record** («بایگانی»), "فوق تخصصی و لایه‌باز":
> what the hub needs today is built in properly, and **everything that describes the archive is data the owner can extend from the app**
> (classes of record, their fields, the file plan, levels, retention, reminders, parties, link kinds, automations) without a deploy.
> Everything above still holds. Rules first, models last: filing, OCR, search, retention, reminders and integrity are code; a model only
> *suggests* a class and metadata, and a person confirms.

### 23.0 Principles ⟨1.7⟩
- **A record is evidence.** It is filed once, versioned, and, once sealed, never changed: a correction is a new version that supersedes.
  Every file carries its SHA-256; a daily fixity job re-hashes what is stored.
- **The schema is data (the open layer).** Classes, fields, folders, levels, retention and reminder rules, party kinds, link kinds,
  automations and system sources are versioned rows. The owner changes them in the app with step-up; an agent may only propose a change
  (`archive_schema` card). What needs code is only the **closed vocabulary** they are built from: field types (§23.2), automation events
  and actions (§23.7), and system sources (§23.8). Adding to those lists is a prompt; using them is not.
- **Clearance decides who sees what.** Every record has a level; every reader has a clearance per scope. Metadata of a record above a
  reader's clearance is never returned, not even its title; search counts never leak it. Secret material is encrypted at rest and every
  view is logged.
- **No secret ever enters the archive.** Passwords, private keys, seed phrases, API keys and 2FA codes are refused at upload by the same
  patterns as gitleaks and the outbound guard (§19.6). Customer personal data stays in the support desk (§19.3), never in the archive.
- **Nothing is deleted except by the owner's seal at the end of retention** (rule 3 of §0 has this one exception): a `archive_disposal`
  card lists the records; sealed by the owner, their files are destroyed and a tombstone stays (ref, class, title, dates, hashes, the
  decision). A record under a legal hold can never be disposed.
- **Scopes are data:** the holding (`HQ`) and every company; no fixed number of companies.

### 23.1 Records, versions, files ⟨1.7⟩
```
Record   { id, ref: "AR-000123", scope: "HQ"|<company code>, class: "contract", class_version, title_fa,
           folder: "FP-…"|null, level: <level key>, state: "draft"|"filed"|"sealed"|"superseded"|"disposed",
           metadata: {<field key>: value},                       // validated against the class version's fields (§23.2)
           parties: [{party: "PT-…", role_fa}], links: [{kind: <link kind>, to: {kind, ref}}],
           holds: ["LH-…"], retention: {rule: "RR-…", trigger_at|null, review_at|null, disposable: bool},
           reminders: [{field, at, lead_days, state: "pending"|"sent"|"done"}],
           current_version, versions: [RecordVersion], source: {kind: "owner"|"agent"|"system", ref|null},
           created_by: Actor, created_at, filed_at|null, sealed_at|null, version }      // `version` is the row version for If-Match
RecordVersion { n, files: [{file_id, name, mime, size_bytes, sha256, pages|null, text_state: "none"|"text_layer"|"ocr"|"failed",
                ocr_confidence|null}], manifest_sha256,                   // SHA-256 of the sorted "sha256  name" lines
                note_fa|null, created_by, created_at, sealed: bool }
```
| Method | Path | Notes |
|---|---|---|
| GET | `/archive/records` | `?scope&class&folder&level&state&party&q&from&to&expiring_within_days&held&cursor` — only what the reader's clearance allows |
| GET | `/archive/records/{ref}` | the record with its versions, links, holds and reminders |
| POST | `/archive/records` | `{scope, class, title_fa, metadata, level?, folder?, file_ids, parties?, links?, file: bool}` · `Idempotency-Key` (required). The owner may file at once (`file: true` → `filed`); an agent's call makes a `draft` |
| PATCH | `/archive/records/{ref}` | `If-Match` · `title_fa`, `metadata`, `folder`, `parties`, `level` (raise only; lowering is §23.4). A sealed record answers `409 sealed_record`, except a PATCH whose only field is `level`: the level is access metadata outside the sealed manifest, so it can be raised, or lowered with `archive.declassify`, without touching the seal ⟨1.7.1⟩ |
| POST | `/archive/records/{ref}/versions` | `{file_ids, note_fa}` → a new version; on a sealed record the old one becomes `superseded`, the record goes back to `filed` |
| POST | `/archive/records/{ref}/seal` 🔏 | target = the current version's `manifest_sha256` |
| POST · DELETE | `/archive/records/{ref}/links` | add or remove one link (not on a sealed version's links) |
| GET | `/archive/records/{ref}/files/{file_id}` | the file; levels with `watermark` are served watermarked (viewer, time, ref); levels with `step_up_to_view` need 🔏 `archive.view` (target = ref). Every call is an access-log row |
| GET | `/archive/records/{ref}/access` | owner only · who viewed or downloaded what, when |
| POST | `/archive/import` | owner · `{scope, file_ids, class?}` → one `draft` per file for the archivist to classify |

### 23.2 Classes and fields (the open layer) ⟨1.7⟩
```
RecordClass { key, title_fa, parent: key|null, scopes: "all"|[scope], icon, default_level, default_folder: "FP-…"|null,
              fields: [Field], required_files: int, allowed_mime: [mime], ocr: bool, retention: "RR-…"|null,
              reminder_fields: [field key], auto_link: [{field, link_kind}], version, status: "active"|"retired" }
Field       { key, title_fa, type, required: bool, searchable: bool, sensitive: bool,        // sensitive → masked below `confidential`
              options?: [{key, title_fa}],                                                    // enum, multi_enum
              ref_kinds?: [kind], currency?: "USD"|"USDT"|"EUR"|"IRR"|…, help_fa?, status: "active"|"retired" }
```
- **Field types (closed vocabulary, v1):** `text`, `long_text`, `number`, `money` (decimal string + currency), `percent`, `date`
  (stored ISO, shown Jalali), `date_range`, `enum`, `multi_enum`, `boolean`, `party`, `company`, `ref` (`decision`, `resolution`, `case`,
  `work`, `record`, `employee`, `revenue_account`), `url` (http/https), `email`, `phone`, `id_code` (masked to the last 4), `iban`
  (masked to the last 4).
- **Changing a class** makes a new class version. Records keep the version they were filed under; the app shows how many records would
  miss a new required field before the seal, and the archivist gets one work item to fill them. **A field is never deleted**, only
  `retired`: its values stay on old records and in search.
- **Seed classes** (the owner edits or retires any of them): `company_registration` (ثبت شرکت), `contract` (قرارداد), `affiliate_agreement`
  (توافق افیلیت), `license` (مجوز), `invoice` (فاکتور و رسید), `domain` (دامنه), `legal_correspondence` (مکاتبه‌ی حقوقی), `sealed_policy`
  (اساسنامه و سیاست مُهرشده), `brand_asset` (نشان و مُهر), `resolution_bundle` (مصوبه‌های ماه), `other` (سایر). Their fields and defaults
  are in `infra/seed/archive/*.yaml` on the server, not in code.

### 23.3 File plan, parties, link kinds ⟨1.7⟩
```
FolderNode { ref: "FP-…", scope, parent: "FP-…"|null, title_fa, classes: [class key], default_level|null, order, status }
Party      { ref: "PT-…", kind: <party kind>, name_fa, name_en|null, identifiers: {<key>: value}, scopes: [scope], status }
PartyKind  { key, title_fa, identifier_fields: [Field] }               // seeds: exchange, provider, government, bank, person, other
LinkKind   { key, title_fa, inverse_fa, to_kinds: [kind] }             // seeds: supersedes, amends, renews, evidence_for, attached_to, about
```

### 23.4 Levels and clearance ⟨1.7⟩
```
Level     { key, title_fa, rank: int, color_index, watermark: bool, encrypt: bool, step_up_to_view: bool, agents_max: bool }
Clearance { subject: {kind: "role"|"employee", ref}, scope: <scope>|"all", level: <level key> }
```
- **Seeds:** `public` (عمومی, 0), `internal` (داخلی, 10, default), `confidential` (محرمانه, 20, watermark), `secret` (سری, 30, watermark,
  encrypt, step-up to view, never above `agents_max`). The owner may add levels between them; a level's rank never changes once used.
- **Clearance seeds:** every agent role `internal` in its own company's scope; the legal counsel `confidential` in `all`; the archivist
  `confidential` for content and every level for **metadata it files**; the owner everything. The owner changes clearance with 🔏
  `archive.clearance` (body hash).
- **Lowering a record's level** (declassification) is the owner's alone: 🔏 `archive.declassify`, target `ref@version:level`.
- `secret` files are encrypted with the OpenBao transit key `archive-secret` before they reach the file store; the key never leaves OpenBao.

### 23.5 Retention, disposal, legal holds ⟨1.7⟩
```
RetentionRule { ref: "RR-…", title_fa, trigger: "filed"|"field:<key>"|"case_closed"|"superseded", keep: {years?, months?}|"permanent",
                then: "review"|"dispose_card", version, status }
LegalHold     { ref: "LH-…", title_fa, case: "LC-…"|null, reason_md, scope: {records?, folders?, classes?, parties?, from?, to?},
                state: "active"|"released", placed_by: Actor, placed_at, released_at|null }
```
- When a record's retention ends, `then: review` makes one work item for the archivist; `dispose_card` makes (weekly, batched) one
  `archive_disposal` card for the owner listing the records. Nothing is destroyed without that card's seal. A held record is skipped.
- **Seed rules** (defaults the owner edits; not legal advice): contracts and agreements 7 years after `field:end`; invoices 7 years
  after `field:date`; licenses and domains 2 years after `field:expires_at`; legal correspondence 10 years after `case_closed`; registration,
  sealed policy, brand and resolutions `permanent`; other `review` after 3 years.
- **Holds:** the legal counsel places one with `archive.hold` (A2, with its case); the owner too. Releasing is the owner's: 🔏
  `archive.hold.release` (target = ref). A held record answers `423 held` to any change except a new version.

### 23.6 Reminders ⟨1.7⟩
```
ReminderRule { ref: "RM-…", class, field, lead_days: [int], to: "owner"|{role}|{company_ceo: true}, channel: "cartable"|"digest",
               version, status }
```
- Seeds: contract `end` 60/30/7 days, license and domain `expires_at` 90/30/7, affiliate agreement `review_at` 30/7. A due reminder is a
  cartable reminder (§21.8) or a digest line; marking the underlying action done closes it.

### 23.7 Automations (the open layer, closed vocabulary) ⟨1.7⟩
```
Automation { ref: "AU-…", title_fa, on: "filed"|"sealed"|"reminder_due"|"retention_due"|"hold_set"|"version_added",
             when: {class?, scope?, level_min?, field?: {key, op: "eq"|"lt"|"gt"|"contains", value}},
             do: [{action: "notify"|"work_item"|"link"|"move_to_folder"|"raise_level"|"add_reminder", args}], version, status }
```
- Rules only, never a model. A new automation is the owner's (🔏 `archive.schema`). `work_item` names a role, never a person outside the
  hub; `notify` follows §6 (never `urgent` except the fixity alarm).

### 23.8 System sources: what the hub files by itself ⟨1.7⟩
`GET · PUT /archive/sources` (owner) switches each on or off: `charter_sealed` (§20.2, every sealed version), `resolution_month`
(the month's sealed resolutions as one PDF), `brand_sealed` (§18.14), `founding_registration` (§18.8, the sealed proposal), `legal_email`
(§22.4, every sent email and its case), `case_closed`, `server_plan_sealed` (§18.8), `backup_restore_test` (§18.9, the monthly result).
Each lands as a `filed` record of its seed class with `source.kind: "system"`.

### 23.9 Search, OCR, "ask the hub" ⟨1.7⟩
- **Text:** a PDF's own text layer first; scanned PDFs and images go to **OCR on the hub** (Tesseract 5, `fas` + `eng`, Apache-2.0; pinned
  traineddata with SHA-256; a sandboxed service with no network), then the deterministic Persian normaliser (`hq_common.persian`).
- **Search:** Persian-normalised full text over title, searchable fields and file text, plus metadata filters; `GET /archive/search`
  `?q&scope&class&level&from&to&cursor` → `{items: [{ref, title_fa, class, snippet_fa, score}], next_cursor}`, clearance-filtered before
  ranking.
- **Ask the hub** (§21.2) includes records within the asker's clearance; `knowledge.search` gains kind `records` for agents, within theirs.
- **Suggestions:** rules first (dates, amounts, IBAN/ID patterns, known parties from the registry); while the kill switch is released, the
  archivist may also suggest a class and metadata. A suggestion is never filed by itself.

### 23.10 Schema API (the open layer) ⟨1.7⟩
| Method | Path | Notes |
|---|---|---|
| GET | `/archive/schema` | everything that describes the archive: classes, field types (closed list), folders, levels, clearance, retention, reminders, parties and kinds, link kinds, automations, sources |
| PUT | `/archive/schema/{part}/{key}` 🔏 | owner · `part` ∈ `classes`, `folders`, `levels`, `clearance`, `retention`, `reminders`, `party_kinds`, `link_kinds`, `automations` · `If-Match` · target `archive.schema` (body hash). Validates against the closed vocabulary (`422 schema_invalid` with `fields`); answers the new version and `impact: {records, missing_required}` |
| POST | `/archive/schema/{part}/{key}/retire` 🔏 | the same target; nothing that uses it is deleted |
| GET · POST | `/archive/parties` | the parties registry; `PATCH /archive/parties/{ref}` with `If-Match` |
| GET · POST | `/archive/holds` | `POST /archive/holds/{ref}/release` 🔏 |
| GET | `/archive/reminders` · `/archive/retention/due` · `/archive/fixity` | due reminders; records whose retention ended; the last fixity run `{at, checked, failed: [ref]}` |

### 23.11 Kinds, tools, stream, step-up, codes ⟨1.7⟩
- **Decision kinds:** `archive_schema` (an agent's proposed schema change; payload = the exact `PUT` body), `archive_disposal` (payload
  `{records: [{ref, class, title_fa, retention_rule, trigger_at}]}`), both sealed with step-up (§5.1).
- **Step-up targets:** `archive.seal` (manifest sha256), `archive.view` (ref), `archive.declassify` (`ref@version:level`), `archive.schema`
  (body hash), `archive.clearance` (body hash), `archive.hold.release` (ref).
- **Agent tools:** `archive.search` (A0) and `archive.read` (A0; metadata and text within clearance), `archive.file` (A1; a `draft` from
  file ids with a proposed class and metadata), `archive.link` (A1), `archive.hold` (A2; the legal counsel, with a case).
- **Roles:** the **archivist** (`HQ-ARC`, «بایگان», a system role of the holding): classifies drafts, completes metadata, links, reports gaps
  weekly; never seals, declassifies, releases a hold or disposes.
- **Stream topic** `archive`: `record.filed`, `record.updated`, `record.sealed`, `reminder.due`, `hold.changed`, `fixity.failed`,
  `schema.changed`.
- **Codes (§14):** `clearance` (403, the record is above the reader's clearance; returned only where the reader already knows the ref),
  `sealed_record` (409), `schema_invalid` (422 with `fields`), `secret_in_document` (422, a secret pattern was found; the file is not
  stored), `held` (423, §18.15). A fixity failure is a data-loss alarm (`urgent`, category data loss), not a Problem code.

### 23.12 Shapes both apps read ⟨1.7.1⟩
Recorded from the web client's data layer (`apps/web/src/lib/api/v20.ts`, 2026-10-22), so the server builds to what the apps already read.
Where §23.1–§23.11 is silent, this list is the contract.
```
Level        { key, title_fa, rank, … }                    // seeded 0, 10, 20, 30: a new level fits between two; a used level's rank is fixed (422 schema_invalid, fields.rank)
             owner_settings: agents_max = the highest level any agent may be cleared for (seeded on "confidential")
Clearance    { subject: "role:<role>"|"employee:<code>", grants: [{scope: "own"|<company code>|"holding", level}], metadata_level, version }
             // saved one subject at a time: PUT /archive/schema/clearance/<subject>; "own" = the subject's own company;
             // metadata_level lets the archivist see the metadata of what it files at every level
Schema rows  carry usage counts: records (classes, folders, levels, retention, link kinds), parties (party kinds)
GET /archive/schema  also returns vocab: {events, actions, ops, ref_kinds, currencies, mimes} and parties
Values       money {amount: decimal string, currency} · date "YYYY-MM-DD" · date_range {from, to} · enum key · multi_enum [key]
             party "PT-…" · company <code> · ref {kind, ref}
Record       { …§23.1, doc_date|null,                     // what from/to filter on
               masked: [field key], class|null,            // null on a draft from import
               suggestion: {class, title_fa, metadata, parties, by: "rules"|"archivist", note_fa}|null,   // drafts only
               tombstone: {decision, at, hashes}|null }    // after disposal
Version      { …§23.1, state: "current"|"superseded" }
Link         { kind, to_kind, to_ref, title_fa, at, by, sealed, inverse }          // a sealed link is never removed
AccessRow    { at, actor, action: "view"|"download"|"metadata"|"level", file_id, version, step_up, watermarked, level_from?, level_to? }   // "level": a raise or declassification
DueReminder  { id, record, title_fa, scope, class, field, at, lead_days, days_left, state, rule, to, channel }
RetentionDue { ref, title_fa, scope, class, rule, trigger_at, due_at, then, holds, decision_ref|null }
Fixity       { at, checked, failed: [ref], next_at }
Hold         { …§23.5, records: n, record_refs: [ref] }   // scope: records is an explicit list; the other facets (folders, classes, parties, from/to) must all match
Source       { key, title_fa, class, enabled, filed, last_at, note_fa }
Automation   { …§23.7, runs_30d, last_run_at|null }
             action args: notify {to, level: "info"|"report"|"decision", text_fa} · work_item {role, title_fa} · link {kind, to}
                          move_to_folder {folder} · raise_level {level} · add_reminder {field, lead_days}
```
| Method | Path | Notes |
|---|---|---|
| PUT | `/archive/schema/{part}/{key}?dry_run=1` | the impact only, nothing applied, no passkey; answers `{part, key, version, impact, row, dry_run: true}` |
| PUT | `/archive/schema/{part}/{key}` 🔏 | answers `{part, key, version, impact, row}`. A new key sends `If-None-Match: *`; parts keyed by ref (folders, retention, reminders, automations) are created with key `new` and the server assigns the ref |
| POST | `/archive/schema/{part}/{key}/retire` 🔏 | body `{part, key, version}`; its hash is the step-up target |
| PUT | `/archive/sources` | owner · `{<key>: on}` for the switches that change |
| POST | `/archive/intake` | `{file_ids}` → `{files, suggestion}`: the secret scan, hashes and text extraction run here (`422 secret_in_document`) |
| POST | `/archive/records/{ref}/file` | `If-Match` · a completed draft becomes `filed` |
| DELETE | `/archive/records/{ref}/links?kind&to_kind&to_ref` | removes an unsealed link |
| POST | `/archive/reminders/{id}/done` | closes a reminder |
- **Declassify** is the record's `PATCH` with a lower `level` and `X-Step-Up` target `archive.declassify`. **Seal** posts
  `{manifest_sha256}`; the server recomputes it and refuses a mismatch.
- **A class's default folder:** the first folder in the record's scope whose `classes` include the class; otherwise the class's
  `default_folder` if it lies in that scope.
- **Cards:** the `archive_schema` payload is `{part, key, base_version, body, impact}`; the card is void if that schema row changed since.
  Both archive cards are approved with the usual `decision.approve` step-up, target the card's ref.
  A card with `base_version: null` (a new key) is void once that key exists.
- **A draft** takes `class` in its `PATCH` (an imported draft has none); a filed record does not. Intake fills the form from the
  `suggestion`, and the draft is created with `POST /archive/records` (`file: false`).
- **`tombstone.hashes`** is `[{name, sha256}]`, one per destroyed file. **`notify.to`** is `owner` or a role key.
- **Clearance rows** may be served one per grant or grouped per subject as above; both apps read either.
- **Files:** images show inline; a PDF opens in a new tab or downloads (the page's security policy does not frame `blob:` URLs). Date
  inputs take the Gregorian date and show the Jalali one beside it.

## 24. As served, checked by the Android 0.3.0 audit ⟨1.7.3⟩
Recorded 2026-10-29 from a field-by-field check of every Android model against the server's `openapi/hq-api.v1.json`. Where these differ
from the sections above, the server is right and this list is the contract; both apps read these shapes.
- **Numbers that are floats:** `Decision.waiting_h`; `RegistryVoice.mem_mb`.
- **May be null or missing:**
  - `RegistryVoice.samples[].file`
  - `StarRollup.companies[].stars`, `score`, `rank` and `parts`
  - `Story.author`
  - `HrEmployee.score`
  - teaching and skill eval `score` and `passed`
  - `CompanyRevenue.share`
  - `CoinAmount.usdt`
  - `KbVariable.source`
  - `handle_masked`
  - `MeetingMinutes.deliverable`
  - `StandingOrder.created_at`
- **Shapes:**
  - `Risk.history[].change` is an object.
  - `RoleDraft.written_by` is an employee code string.
  - A legal email's attachments are `{file_id, name, mime?, sha256}`, not FileRefs.
  - `GET /support/conversations/{ref}` returns `{conversation, messages}`.
  - `GET /egress/summary` is a list of `EgressDay`.
- **Being aligned in prompt 15:**
  - `GET /lessons` becomes a `Page`.
  - `GET /stars/rollup` answers 200 with empty lists before the first roll-up.
  - `/transcribe` answers `503 channel_not_configured` at once while speech-to-text is off, and `/meta.speech.enabled` says so.
- **Clients are tolerant:** an unknown enum value falls back, and a field the server omits takes its default. A decode failure is logged with its field path (the Android «خطاخوان»), never with the body.

## 25. Companies, founding, notifications and the stream ⟨1.7.5⟩ (2026-10-30, prompt 15.2)
- `DELETE /companies/{code}` 🔏 `company.delete` on `{code}`, `Idempotency-Key`: `204`; `409 company_has_history` when any work was done or any deliverable, archive record, revenue or non-zero treasury row exists (archive it instead with `PATCH /companies/{code} {status: "archived"}` 🔏 `company.archive`); `422` for the holding; `404`. An Audit row summarises what was removed first; a provisioned server is deleted only on the owner's separate approval.
- `FoundingIn { source: {kind: "idea"|"repo"|"blank", repo?, brief_md?}, name_fa?, code?, tagline?, color_index?, logo_file_id? }`. `blank` registers a `draft` company without audit or proposal. `code` is unique across companies and open foundings (`409 code_taken`). The proposer keeps the owner's name and code. At `sealed`, a given logo and colour become the company's brand.
- `POST /notifications/read {ids: [...]}` marks several read. An open overseer finding with the same key is updated, not raised again; a new notification only when its severity rises or it reopens.
- `GET /stream`: `topics` up to 1000 characters, and `topics=all`. Until then clients split topics into groups of at most 200 characters, one connection each.


## 26. Company server runners ⟨1.8⟩ (2026-10-30, prompt 17, revised)
Owner, 2026-10-30: the holding's agents work on the companies' own servers (inspect them, write code, commit, push, deploy, build media) on
the owner's orders, under the holding's control. The owner owns every server involved. This replaces §17.3 rule 1 ("never touches production")
for company servers that the owner has paired; the hub's own server keeps its rules.

### 26.1 Design: a pull runner on each company server (like a self-hosted CI runner)
- **Runner:** each company server runs **`hq-runner`**, a small open-source program kept in this repository (`services/company-runner/`).
  - It runs as a systemd service under the server's existing work user (`forex` on FX, …).
  - That user already holds the server's logged-in Claude Code, Docker and git.
- **Who connects to whom:**
  - The runner opens **outbound HTTPS** to `https://hq.coinepro.com/api/v1/runners/*`. It long-polls for jobs, streams their events and posts results.
  - **The hub never connects into a company server:** no inbound port, no SSH key held by the hub, no private-network rule, no DOCKER-USER change.
  - It needs no new hub container; the routes live in `apps/api`.
- **Pairing (device-authorisation flow, nothing secret is shown):**
  1. On the server, `hq-runner pair --company <CODE> --name <name>` calls `POST /runners/pair`. The hub answers with a short `user_code` (`ABCD-1234`), shown on the server.
  2. The owner approves it in the app with the passkey: `POST /runners/approve {user_code}` 🔏 `server.attach`, target `company:<CODE>`.
  3. The runner's poll then receives its own credential (`runner_token`, rotated every 24 h through `POST /runners/rotate`). It stores it with mode `600` under the work user's home.
  - The hub stores only a hash of the token.
- **Detach:** `DELETE /infra/servers/{id}` 🔏 revokes the token at once. The runner stops on its next poll.

### 26.1a Over the holding's private network (owner, 2026-10-30: «باید همه چی به هم متصل باشه از طریق شبکه ما»)
- **Route:** the runner reaches the hub over the **Hetzner private network**, not the internet.
  - On each company server, `hq.coinepro.com` resolves to `10.10.1.4` (the runner's `--hub-ip 10.10.1.4`, or one `/etc/hosts` line).
  - Caddy already listens on 443 on every interface, so the TLS certificate stays valid and the traffic stays inside the network.
  - The private network is unencrypted; TLS covers it.
- **Fallback:** if the private address does not answer, the runner falls back to the public address and says so in its state (`via: "private"|"public"`).
- **A server outside the network** (for example IG-Hub) joins it from the Hetzner console. That is the owner's action, and its next free address is `10.10.1.5`.
  - Until it joins, it works over the public address.

### 26.1b Companies working together through their servers
- **How servers work together:** each company's Claude-run server talks to the others **through the hub**, never directly:
  - a cross-company work request (CEO to CEO, §4)
  - a job on the other company's runner
- **Media published through a company's own product API** (for example IG-Hub's Instagram API):
  - **What the series names:** a §22 series target may name `channel: "runner"` with `{server, command}`.
  - **The publish job:** at publish time the hub queues a `publish` job on that server's runner. The runner fetches the rendered files from the hub, runs the configured local command (which calls the product's own API on that server), and returns `{external_id, url}`.
  - **No new egress:** no hub egress to private addresses is needed.
  - **Setting up the publish command:** the owner seals it once with the series. The `command` is set up by that server's own Claude.
- **Job kinds:** the job kinds of §26.2 add `publish`.

### 26.2 Jobs and what agents can do
A **job** is one unit of work for one server: `{id, server, kind, actor: Actor, args, state: "queued"|"running"|"awaiting_seal"|"done"|"failed"|"cancelled", created_at, started_at|null, finished_at|null, exit_code|null, summary_fa|null, transcript_url|null}`.

Agent tools (Tool Gateway, recorded like every tool call) create jobs and wait for them:

| Tool | Job kind | What the runner does |
|---|---|---|
| `server.map` | `map` | collects the inventory (§26.5) with fixed read-only commands |
| `server.exec` | `exec` | runs `{cmd, cwd?, timeout_s ≤ 3600, sudo?}` as the work user (sudo only if the user has it), streams stdout/stderr, returns `exit_code` |
| `server.read` / `server.write` | `read` / `write` | a file (≤ 20 MB); `write` keeps `<file>.hq-bak` |
| `server.claude` | `claude` | runs the server's own Claude Code on a brief (`claude -p … --output-format stream-json`), in the repository folder named in `args.cwd`, under that repository's CLAUDE.md; events stream as `SessionEvent` into a `CodeSession` with `runtime: "company_server"`; owner messages resume it (`--resume`) |

⟨2026-11-09⟩ **The account a `claude` job runs on (owner: the companies have no Claude subscription of their own).** When the hub holds the
owner's second subscription (`kv/claude-runtime/oauth-2`, `make claude-token SLOT=2`), `GET /runners/jobs/next` gives a `claude` job one
more top-level field, `claude_oauth` (that account's token). It is added at pickup only: never in the job's stored `args`, its events, the
hub's logs or its database. A runner of 0.3.1 sets it as `CLAUDE_CODE_OAUTH_TOKEN` for that one Claude Code process (and masks it in every
event); an older runner ignores it and runs on the server's own login. No other kind ever carries it.
⟨2026-11-09⟩ **Which account:** the one the hub itself is on, read from `llm.quota_status` with the router's `near_full` rule — the main
subscription (`kv/claude-runtime/oauth`) while it has room, the second once the main is at 99% or refused, the main again as soon as its
window resets. Both full: a queued `claude` job is not handed out (it waits, as the hub's own calls wait) while the server's other jobs go on.

**Charter defaults:**
- **Each company's CEO, CTO / Lead Developer, DevOps and SRE:** all tools on that company's servers.
- **SEO, content and analysts:** `map`, `read` and `exec`.
- **The holding's platform SRE and the overseer:** every paired server.

### 26.3 Control
- **Free:** jobs run without a card.
- **Seal-required:** a decision card `server_destructive` (🔏 `server.destructive`, target `<CODE>:<server>`) first, for the categories in `/control/server-policy`:
  - `db_drop`
  - `volume_delete`
  - `backup_delete`
  - `disk_wipe`
  - `access_change` (that server's SSH, users or firewall)
  - `server_delete`

  How each job kind is checked:
  - **`exec`:** the hub classifies the command before queueing.
  - **`claude`:** the runner installs a Claude Code `PreToolUse` hook for the session that asks the hub to classify each Bash command.
  - **On a match:** the job, or that tool call, waits in `awaiting_seal`.
- **Kill switch and deploy freeze:**
  - **Kill switch:** the company's kill switch cancels its queued and running jobs; the runner kills the process group.
  - **New jobs while locked:** `423 company_locked`.
  - **Deploy freeze:** refuses jobs the hub classes as deploys.
- **Audit:** every job, plus every command inside a `claude` job, is an Audit row:
  - fields: actor, server, masked command, exit code, duration, digest
  - the full transcript goes to object storage, readable by the owner
  - secrets are masked by name and pattern before storing
- **Budget:** `claude` jobs run on the server's own Claude login; the runner reports usage from stream-json into the Token Treasury.

### 26.4 API
| Method | Path | Notes |
|---|---|---|
| POST | `/runners/pair` | runner, unauthenticated, rate-limited: `{company, name, hostname, private_ip, os, runner_version}` → `{device_code, user_code, expires_in: 900, interval: 5}` |
| POST | `/runners/token` | runner: `{device_code}` → `428 authorization_pending` until approved, then `{runner_token, server_id}` once |
| POST | `/runners/approve` 🔏 | owner: `{user_code}` · `server.attach`, target `company:<CODE>` → `{server}` |
| POST | `/runners/rotate` | runner (bearer) → `{runner_token}` |
| GET | `/runners/jobs/next` | runner (bearer), long-poll ≤ 30 s → `{job}` or `204`; also carries cancels |
| POST | `/runners/jobs/{id}/events` | runner: a batch of `{seq, type: "stdout"\|"stderr"\|"session_event"\|"progress", data}` |
| POST | `/runners/jobs/{id}/result` | runner: `{exit_code, summary_fa?, usage?}` |
| POST | `/runners/classify` | runner (bearer): `{cmd}` → `{category\|null}` (for the Claude hook) |
| GET | `/infra/servers` | also paired servers: `{id, company, name, origin: "provisioned"\|"attached", private_ip, user, hostname, runner_version, via: "private"\|"public"\|null, state: "pending"\|"online"\|"offline"\|"revoked", last_seen_at, map_at}` |
| DELETE | `/infra/servers/{id}` 🔏 | `server.detach`, target `<CODE>:<server>` · revokes the runner |
| GET / POST | `/infra/servers/{id}/map` | the latest map / queue a `map` job |
| GET | `/infra/servers/{id}/activity` | `?actor&from&to`, `Page` of jobs and their commands |
| POST | `/infra/servers/{id}/exec` 🔏 | the owner's own `exec` job, `server.exec`, target = SHA-256 of the body; SSE of its events |
| GET / PUT | `/control/server-policy` | `{seal_required: [...]}`; PUT 🔏 `server.policy`, target = SHA-256 of the body |

**Stream:** topic `servers` carries `server.state`, `server.call` (one per job start and end) and `server.awaiting_seal`.
**Database:** `infra.servers.plan_id` becomes nullable for `origin = "attached"`.

### 26.5 Shapes the Android app is built on (binding)
- **`Server.map`** (`GET …/map` → `{at, map}`):
  ```
  {user, os, kernel, uptime_s, cpu: {cores, load1}, memory: {total_mb, used_mb, swap_total_mb, swap_used_mb},
   disks: [{mount, total_gb, used_gb}], containers: [{name, image, state, health|null, project|null}],
   compose: [{project, path, services: [..]}], systemd: [{unit, state, timer: bool, next_at|null}],
   cron: [{user, schedule, cmd_masked}], ports: [{port, proto, bind, process, public: bool}],
   repos: [{path, remote, branch, dirty: bool, last_commit_at}],
   automations: [{kind: "n8n"|"cron"|"systemd"|"other", name, active: bool, detail}], sites: [{host, upstream}]}
  ```
- **The owner's terminal:** body `{cmd, cwd?, timeout_s, sudo}`. The SSE events:
  - `stdout` / `stderr`: `{text}`
  - `exit`: `{code, duration_ms}`
  - `error`: `{code, message}`
  - `awaiting_seal`: `{decision_ref}`
- **An owner-started session:** `POST /workshop/sessions {runtime: "company_server", server, company, driver: "<agent code>"|null, title, brief, cwd?}`.
  - `CodeSession` adds `server|null, company`.
- **Stream `server.call`:** `{server, company, actor: Actor, tool, summary_fa, cmd_masked, exit_code|null, duration_ms|null, session_ref|null, state: "running"|"done"|"failed"}`.
- **`transcript_url`:** a hub path read with the owner's session.

### 26.6 The holding's network map ⟨1.8⟩ (owner, 2026-10-30: «عمیقاً بررسی بکن… که همه‌ی سرورها به هم دسترسی داشته باشند یا همه به هاب»)
- **Job kind `netcheck` (read-only):** `args: {targets: [{to, host, port}]}`, one row per port (the runner also accepts `{name, ip, ports}`); results echo `to`.
  - The runner TCP-connects each port (3 s timeout) and pings each target where it can.
  - It returns `{from, via, results: [{to, host, port, ok, ms, error}]}`; a ping row has `port: null`.
- **What every poll carries:** each runner reports `via` and `hub_rtt_ms`, stored on its server row.
- **`GET /infra/network`:**
  ```
  {at, nodes: [{id, company, name, private_ip, via, state, hub_rtt_ms}], links: [{from, to, port, ok, ms, error, at}]}
  ```
  - The hub is node `hub` at `10.10.1.4`.
- **`POST /infra/network/check`** (owner): queues a `netcheck` on every online runner. Its targets are the hub (443) and every other attached server's private IP (80, 443). ⟨2026-11-08⟩ Not 22: SSH between two companies' servers is closed by their firewalls on purpose and is no path of the work (every request goes over HTTPS through the hub); a port-22 link stored before is left out of `GET /infra/network` and of `server.state` reasons.
- **A daily protocol runs it:** the overseer raises a finding when a link that worked now fails.
- **Cross-company work:** a `server.*` tool on another company's server is allowed in only two cases:
  - **Holding-wide roles:** for the holding's platform SRE and the overseer.
  - **Cross-company request:** through a cross-company work request (§4) that the other company's CEO accepted. The job then runs as that company's actor.

  Servers never call each other directly; the hub carries every cross-server task.


## 27. Choosing the player, the council of models, and speech on the hub ⟨1.9⟩ (2026-10-31, prompt 18)
Owner, 2026-10-23 (request #13), brought forward on 2026-10-31: «بگیم بده جی‌پی‌تی انجام بده یا فلان کارو جمنای بکنه یا دستور بدم با هم
مشارکت کنن… عکس و ویدیو با هم بسازن». And request #14: speech to text on the hub.

### 27.1 The player of an order
- **Fields:** `POST /work` and `PATCH /work/{id}` take `player: "auto"|"claude"|"gpt"|"gemini"|"deepseek"` (default `auto`) and `mode: "single"|"council"` (default `single`).
- **Where they appear:** `Work` carries both, and every child work inherits them unless its assignee's charter forbids it.
- **`auto`:** the LLM Router picks, as today.
- **A named player:** every model call of the work's runs goes to that player.
  - **`claude`:** the Claude models through the router.
  - **The others:** a substitute seat (§21.13), within its daily cap, with the same data masking.
  - **Unavailable player** (signed out, limited or off): the run waits up to 30 minutes and then falls back to `auto`. A notification says so, and the work's events record it.
- **Voice orders:** they recognise «با جی‌پی‌تی / با جمنای / با دیپ‌سیک / شورا» and set the fields.

### 27.2 The council of models
- **How it runs:** `mode: "council"` runs the same brief independently on every available player (Claude plus every substitute that is `ready`).
  - Each player's work is a council member run.
  - Claude then writes the synthesis.
- **Synthesis contents:** where the players agree, where they differ and why, the recommendation, and each answer in full.
- **Record shape:**
  ```
  Council { work_ref, members: [{player, model, state: "queued"|"working"|"done"|"failed"|"skipped", run_id|null, deliverable_ref|null, reason|null}],
            synthesis_ref|null, state: "running"|"synthesising"|"done"|"failed" }
  ```
  - `GET /work/{id}/council` returns it.
  - Stream `work.council` carries every change to it.
- **Media work** (images, video):
  - Each player that can make the kind makes its own version as a Creative (§21.13).
  - The owner picks one (`POST /creatives/{ref}/pick`). For video, `POST /creatives/{ref}/animate` makes a video from the picked image.
- **Budget:** one envelope covers the whole council. A member that would pass a cap is `skipped` with the reason.

### 27.3 Speech to text on the hub
- **Model and memory:** the `stt` service runs the pinned **`small`** faster-whisper model (MIT) so it fits the memory budget, and `/meta.speech.enabled` becomes `true`.
- **When the hub transcribes:**
  - voice messages and voice notes
  - the owner's voice orders when the phone's recogniser is unavailable or fails
  - audio files attached anywhere
- **Results:** a transcript is stored on the file (`transcript_fa`), and stream `file.transcribed` announces it.
- **Privacy:** audio never leaves the hub.
- **The phone first:** the apps still prefer the phone's recogniser for live dictation. The hub's transcript also replaces a voice message's text when the owner asks.

## 28. Owner's clean-up, deep company catalogue, the watch, and council robustness ⟨1.10⟩ (2026-10-31, prompt 19)
Owner, 2026-10-31: outputs must not pile up (select several → archive or delete for good); a search field showed a stray "O-…"; an
intelligence beyond the CEOs must watch the app and the holding (bugs, security holes, growth, advice); the council's answer to "go
through the TradeYar server and extract everything" was shallow, and three of four players failed.

### 28.1 Outputs: several at once, archive or delete
- **Bulk archive:** `POST /deliverables/file {refs: [..]}` files each one as §5.2 `/{ref}/file` does → `{records: [{ref, record}]}`, idempotent per ref.
- **Delete for good:** `DELETE /deliverables {refs: [..]}`, 🔏 `deliverables.delete` on the SHA-256 of the sorted refs.
  - **What is deleted:** the rows, their files and their ratings, removed from the database and storage.
  - **What stays:** only an Audit row with `{ref, title, company, deleted_by, at}`. The Audit chain cannot lose rows.
  - **A filed output:** archive records it was filed into stay. The archive is the owner's record.
  - **Response:** `{deleted: n}`.
- §5.2's "never deleted" now means: never deleted by anyone but the owner.

### 28.2 Company catalogue (a deep extraction, not a summary)
- **What it is:** `Catalogue { company, at, state: "running"|"done"|"failed", record: "AR-…"|null, sections: [...] }`.
- **How it is built:** by a `claude` job on every paired server of the company (§26). The brief is fixed and exhaustive; the job reads, it does not change anything:
  - **Products and services:** every container, compose project, systemd unit, process, port, domain and site, and what each one does.
  - **Automations and schedules:** every n8n workflow (name, trigger, nodes, schedule, last run, errors), cron entry and timer.
  - **Data:** databases, schemas, tables with row counts (no row contents), queues and buckets.
  - **Interfaces:** APIs and their routes, bots and their commands, webhooks, and integrations with third parties (names only, never secrets).
  - **Code:** repositories, branches and last commits; outputs and reports produced; logs with recurring errors.
  - **Risks:** expiring certificates, failing services, public ports, outdated packages with CVEs.
- **Output:** a structured catalogue (sections with tables), filed in the archive as a `report` record, plus a deliverable to the owner.
- **Section shape** (stored and served; older catalogues converted on read):
  ```
  {key, title_fa, summary_fa: str|null, tables: [{title_fa: str|null, columns: [str], rows: [[str]]}], notes_fa: [str], count: int|null}
  ```
  - **Cells:** every cell is a string.
  - **Rows:** each row is exactly as wide as its columns.
  - **Prose fields** are plain sentences, never JSON.
  - **What the job returns:** one fenced JSON object per section.
  - **A section that does not parse:** retried once. As a last resort its prose goes to `notes_fa`, with tables empty.
- **`uptime_24h`** on `/ops/sites` and `/internal/v1/health/sites` is a fraction 0..1. The governance KPI `health.uptime_24h` stays a percent (unit `%`).
- **Routes:**
  - `POST /companies/{code}/catalogue` (owner) starts a run.
  - `GET /companies/{code}/catalogue` returns the latest.
  - A weekly protocol refreshes it and sends the diff to the CEO and the owner.
- **The CEO's duty:** when an order asks to "go through / extract everything", the CEO starts the catalogue instead of writing a summary of its own.

### 28.3 The watch (دیده‌بان): continuous checks over the app, the hub and every company
- **Who runs it:** the overseer (§18) runs these as protocols, each producing findings and, where useful, a proposed fix as a work item or a Code Workshop session for the owner's seal.
  - **Daily security sweep (every paired server and the hub):**
    - public ports against the expected list
    - CVEs in installed packages and lock files
    - TLS expiry
    - failed logins summary
    - secrets committed to repositories
    - backup freshness
  - **Daily app health:** the apps report their own errors (`POST /client/errors`, below), and the overseer groups them, finds the cause in code (`github.read`), and proposes the fix.
  - **Weekly code review per repository:** a read-only `claude` job looks for bugs, dead code, missing tests and risky patterns, and returns a ranked list.
- **Who else contributes:**
  - **Weekly growth memo from the advisor:** per company, the three highest-value moves from the catalogue, revenue, funnel and support data, each with expected impact.
  - **Monthly «پیشنهاد هلدینگ» from the digital CEO:** cross-company opportunities.
- **App error reports:** `POST /client/errors {app: "android"|"web", version, entries: [ErrorEntry]}`.
  - The entries are the app's own error log (already masked on the device), sent in batches.
  - `GET /client/errors?app&version&from` is for the owner and the overseer.

### 28.4 Council robustness
- **An unsupported model:** a substitute seat whose model is refused by the provider (e.g. Codex with a ChatGPT login refusing a model id) retries once with the seat's default model.
  - The seat's model list is re-checked against what the CLI reports.
  - The member's `reason` is written in Persian («مدل gpt-5.3 با اشتراک ChatGPT پشتیبانی نمیشود؛ با مدل پیش‌فرض دوباره امتحان شد»).
- **Web recipe failure** (`recipe_failed`): one retry after reloading the signed-in profile.
  - Then the member is `failed`, with a Persian reason and a screenshot attached to the failure for the overseer.
  - The substitute's state becomes `error`, so the next council skips it with that reason up front.
- **Synthesis:** never waits for members that ended. With one answer it says so plainly and does not pretend there was a council.
- **The app:** shows each failure in plain Persian, never raw JSON.

### 28.5 Notifications: several at once, delete for good ⟨1.10.1⟩ (owner, 2026-11-01)
- **Delete:** `DELETE /notifications {ids: [..]}` (owner only) deletes those notifications from the database → `{deleted: n}`.
  - **Scope:** any notification may be deleted, read or unread. The apps offer it on the «خوانده‌شده» tab.
  - **«همه» selected:** `{all_read: true}` deletes every read notification up to the newest one shown, and must be sent with `{before: <ts>}` from the screen.
  - **What stays:** no Audit tombstone is needed (notifications are copies of events that stay in their own records).
- **Selection:** both apps add long-press / checkbox selection with «انتخاب همه» to both tabs.
  - **«خوانده‌نشده» tab:** the actions are «خوانده‌شده» and «حذف».
  - **«خوانده‌شده» tab:** the action is «حذف».

### 28.6 Catalogue jobs read everything they are asked to, and never carry a secret
- **Permissions:** the read-only `claude` catalogue job runs with an allow-list of read commands, so a non-interactive session is not refused. The list includes:
  - `crontab -l`
  - `systemctl list-*` and `status`
  - `docker ps`, `docker compose ls`, `ps`, `config` and `docker inspect`
  - read-only `docker exec … cat|ls`
  - `ls`, `cat`, `head` and `find` under `/etc`, `/opt`, `/srv` and `/home`
  - `n8n export:workflow --all` to stdout
  - `ss` and `journalctl --since`

  Everything else stays under the existing destructive-command hook.
- **Missing access:** what the job still cannot read is listed in the section's `notes_fa`, with the exact command that was refused.
- **No secrets:** every catalogue answer passes the hub's secret masker before it is stored or shown.
  - The overseer's «الگوی رمز در خروجی ایجنت» finding on a catalogue therefore closes once the catalogue is re-rendered masked.

### 28.7 What the holding spends ⟨1.10.2⟩ (2026-11-02, prompt 20.1)
Prompt 20's diagnosis: 97.6% of the week's tokens went to one catalogue run (24 Claude Code jobs, 50M tokens in an hour, started
by the watch after the owner's clean-up cleared the week's claim); the owner's clip order got 0.5%. Every rule below is code.
- **The catalogue (§28.2) runs only on the owner's order.**
  - `POST /companies/{code}/catalogue` (the owner) is unchanged.
  - `company.catalogue {start: true}` starts a run only when the agent's run works on a work item created by the owner, or one
    requested or split from it (up the `parent_id` / `requested_by_work_id` chain). Otherwise it answers the latest catalogue, or
    `409 owner_order_required` when there is none.
  - The watch no longer refreshes it weekly; it only ends runs left waiting on a server that is off.
- **A token cap per run:** `HQ_CATALOGUE_RUN_TOKENS` (default 1 500 000) for every server and section of one run together.
  - Each `claude` job gets its share as `token_cap` (at least 60 000) and `max_turns: 25`.
  - A second try of a section is asked only while the run's spent tokens plus that share fit the cap.
  - **Runner 0.2.2:** adds up every assistant message's usage (input + output + cache reads and writes, a message once) and stops
    the session the moment it passes `token_cap`: exit code `125`, `output.token_cap_reached: true`, the usage it reached.
    An older runner keeps to `max_turns` only.
  - The jobs run on the company's own server and its own Claude Code login: their `llm.calls` rows carry
    `meta.quota = "company_server"` and `meta.via = "catalogue" | "server_claude"`, and never count against the hub's daily cap.
- **The watch, rule first (§28.3):**
  - The daily security sweep (PR-140) reads every paired server's map (a port bound publicly other than 22, 80, 443; a disk at 80%
    or more) and the sites' certificates (fewer than 21 days) by code. Nothing found: the run passes with no model. Something found:
    the model's brief starts with what the rules found.
  - The daily app health (PR-141) calls a model only on a day an app reported an `error`.
  - The code review of every repository (PR-142) runs on the 1st of the Jalali month, not weekly.
- **A daily cap per company:** `core.companies.daily_token_cap` (`NULL` = `AGENT_COMPANY_DAILY_TOKEN_CAP`, default 400 000; `0` =
  only the hub's cap). A company's agent runs of the UTC day (input + output + cache tokens) stop at it, checked when a run is
  claimed and before every model call (`daily_cap`), next to the hub's own `AGENT_DAILY_TOKEN_CAP`.
- **Spend by domain:** every `llm.calls` row falls in one domain, by rule: `catalogue`, `server`, `oversight`, `advisor`, `council`,
  `meetings`, `media`, `work`. The morning report shows yesterday's share and, on the owner's Saturday, the past week's; a
  warning line when `catalogue`, `oversight` or `server` leads.
- **`treasury.usage`** (finding 7): `{scope?: company|holding|<CODE>, period?: day|week|month, company?, department?, role?}`, any
  case; the answer adds `by_domain` and `by_department`.
- **GPT's text on ChatGPT's web chat** (the owner, 2026-11-02), not Codex:
  - `DEFAULT_PLAYERS.gpt.capabilities.text = "web"`. Its text seats (`advisor_second_opinion`, `overseer_cross_check`,
    `assistant_errand`) run `via: "web"` on the signed-in `chatgpt-web` profile.
  - Codex (`via: "cli"`) keeps only `code_review`, off until the owner turns it on.
  - GPT is ready once its web profile is signed in. A Codex limit never stops the web chat; the web chat's own limit is a hold on
    the web path (`web_error_until`, reason `limited`).
  - Migration `0036` moves the seeded seats only (not seats the owner edited by hand), one Audit row per seat.
  - **The recipe stands on the page's structure** (the lesson of 19.3, the profile is fa-IR): Enter sends; testids first; the answer
    is the last rendered answer block. A label is only a fallback beside a structural selector, in Persian and English. A recipe's
    `read` step may name `alt` selectors, tried in turn when the first matches nothing.

## 29. The owner sees the business: routing by domain, every order answered, working groups, connections, the home ⟨1.11⟩ (2026-11-02, prompt 21)
The owner (2026-11-02): «فرمان کلیپ دادم … هیچ خروجی نداشت؛ نمیدونم با کی حرف میزنم. کل اپ شده مسائل فنی سرورها … میخوام به سئو،
محصولات، پیشرفت و درآمد فکر کنم.» Plan: `docs/PLAN_2026-11-02_OWNER_FOCUS.md` (the one-glance table, rows 1–16 and 18);
management review: `docs/MANAGEMENT_REVIEW_2026-11.md`. Principles: **upgrade, not rebuild** (nothing that works is thrown away);
**companies are data** (no fixed number of companies anywhere); **rules first, AI last**; every shape keeps §28.2's table-section
rule and the fractional `uptime` of §28.
Every route below is under `/api/v1` (owner) or `/internal/v1` (agents, through the gateway), as §1 says.

### 29.1 Routing by domain (owner's decisions 1–3, 2026-11-02)
- **Every finding, notification and decision card carries a `domain`:** `business` · `media` · `revenue` · `product` · `tech` · `security` · `infra`.
  - Set by the code that raises it (a protocol's area maps to a domain; `server_*`, `deploy`, `backup`, `incident`, `catalogue` → `tech`/`infra`;
    `security`, `secret`, `egress` → `security`; `media_*` → `media`; `revenue`, `funnel`, `referral` → `revenue`; `feedback`, `app_health` → `product`).
    No domain given: `business`.
- **Who handles it** (`routed_to`, an employee code):
  | domain | company's own | the holding's (the hub itself) |
  |---|---|---|
  | `tech`, `infra` | the company's CTO (its SRE as second) | `hub_platform_sre` |
  | `security` | the company's CTO, and the holding's `security_analyst` | `security_analyst` |
  | `business`, `media`, `revenue`, `product` | the company's CEO (media: its media director) | the owner's home cards (§29.13) |
- **What reaches the owner** (`owner_visible: true`):
  - every `business`, `media`, `revenue`, `product` item, written for the owner (§29.7);
  - a technical item **only** when it is critical by the fixed list `critical_reason`: `data_leak` · `product_down` (a product unreachable
    more than 15 minutes) · `money` · `legal`;
  - the **weekly technical summary**, Saturday 09:00 owner's time (Tehran): one rule-based `report` deliverable of the holding's system
    employee, a few lines per company: open technical findings by severity and age, incidents and their downtime, uptime, the
    week's spend by domain (§28.7), hires made (§29.10). Nothing else technical is pushed.
- **Owner routes, filtered by default:** `GET /notifications`, `GET /oversight/findings`, `GET /decisions` answer only `owner_visible` rows
  unless `?scope=all` (the app's «شرکت ← فنی» uses `?scope=all&domain=tech|infra|security&company=X`). Each row carries `domain`,
  `owner_visible`, `routed_to`, `critical_reason|null`.
- **Destructive cards:** a `server_destructive` card's approver is the company's CTO (`approver: {kind: "agent", code}`), who decides with
  `hire.decide`'s sibling tool `card.decide` `{ref, verdict, note}`. Only the categories in `owner.settings.destructive_owner_categories`
  (default `["server_delete", "db_drop"]`, on a production target) stay the owner's. The owner may change the list (🔏 `settings.destructive`).
- **Data already there:** open technical findings and notifications move to their handler's queue (`owner_visible: false`, `routed_to` set);
  nothing is deleted. Migration `0037` does it once, with one Audit row per kind moved.

### 29.2 Every order is answered (owner's ask 2)
```
OrderReport { ref: "F-0001", text_fa, at, state: "received"|"planned"|"in_progress"|"waiting"|"blocked"|"delivered"|"failed"|"cancelled",
              ack: {at, by: Actor, plan_fa, assigned: [{company, code, title_fa}], due_at}|null,
              route: {companies: [code], department, collaborators: [code], output_kind, budget_tokens, mode, player},
              steps: [{at, who_fa, what_fa}],            # plain Persian, newest last, at most 30
              blockers: [Blocker], outputs: [{ref, title_fa, kind}],
              summary: {done_fa, left_fa, need_fa}|null, updated_at }
Blocker { kind: "no_employee"|"hiring_closed"|"locked"|"series_unsealed"|"budget"|"player_down"|"connection_missing"|"no_progress"|"talk_loop",
          title_fa, detail_fa, since, fix: {action, label_fa, target}|null }
```
- `GET /orders/{ref}/report` (owner) and stream `order.report` on every change; `GET /orders` items carry `state` and `summary`.
- **Acknowledgement within 10 minutes:** the dispatcher (§29.4) writes the receipt at once («دریافت شد؛ به … سپرده شد»); the assignee's
  first run must store its plan (`order.ack {ref, plan_fa, assigned, due_at}`, A1); 10 minutes without one is a `no_progress` blocker and
  the CEO is woken with a small work item.
- **No progress:** 2 hours without a step → the CEO must report (`order.progress`); 6 hours → the overseer tells the owner why
  (one `decision`-level notification, `domain: business`, written for the owner).
- **Talk without output:** more than `ORDER_TALK_LIMIT` (default 12) agent runs on one order without a deliverable stops the order's
  open runs and adds a `talk_loop` blocker with «گیر کرد چون …».
- **The right state:** the root work of an owner's order is never `delivered` while one of its children is open, its progress is below
  100, or its last deliverable is a partial one («خروجی ناقص»); it stays `in_progress` (or `waiting`). A partial deliverable never closes
  any work (finding 3 of prompt 20).
- **Blockers are detected by code** on every change and every 15 minutes, each with its one-tap fix:
  | kind | detected when | fix action (`POST /orders/{ref}/fix {action, target}`) |
  |---|---|---|
  | `no_employee` | the target department has no active employee for the seat the work needs | `hire` (the group seat's charter, auto-hire §29.10) |
  | `hiring_closed` | an agent's hire was refused | `hiring.open` (🔏) |
  | `locked` | a kill switch, a deploy freeze or a hold on the work's company | `lock.open` (the owner's existing release routes) |
  | `series_unsealed` | a media item waits for a `media_series` card | `series.seal` (🔏, the card) |
  | `budget` | the work's envelope, the company's daily cap or the hub's cap stopped a run | `budget.add` `{tokens}` (+X, §29.6) |
  | `player_down` | the work's named player is signed out, limited or off | `player.auto` (switch to `auto`) |
  | `connection_missing` | the work needs a connection that is not connected | `connection.guide` (§29.12) |
- **End report:** when the order ends (`delivered`, `failed`, `cancelled`) `summary` is filled: «چه شد», «چه ماند», «از شما چه لازم است»
  (with the fix button), and one `report` notification links it.

### 29.3 The owner makes a rule from the app (owner's ask 3)
- `POST /rules {text, source: "text"|"voice", file_id?}` → a `StandingOrder` (§18.1) `proposed`, `applies_to` widened to
  `"all"|"overseer"|{roles: [role]}|{companies: [code]}` and a precise `text_md` written from the owner's words (rule-based clean-up; the
  light model only to make it one clear imperative). The owner seals it with one tap (🔏 the existing `/oversight/orders/{ref}/seal`).
- Sealed rules are injected into the system prompt of every role they apply to (the existing «Owner's standing orders» block).
- The overseer watches them (PR-095, now daily and rule-first: a violation found by a rule is a finding; a model only samples), and the
  **first enforcement report** comes 24 hours after the seal (a `report` notification: how many runs it applied to, violations, fixed).
- `GET /rules` (= standing orders, newest first, with their counts), `PUT /rules/{ref}` (a new version, 🔏), `POST /rules/{ref}/retire`.
- **As built (prompt 21):**
  ```
  Rule { id, ref, text_md, owner_text|null, source, file_id|null, applies_to, status: "proposed"|"sealed"|"retired", version,
         sealed_at|null, created_at, counts: {runs, violations, fixed}, report_at|null, history: [{version, text_md, applies_to,
         applies_codes, status, sealed_at}] }
  ```
  `owner_text` keeps the owner's own words. `PUT /rules/{ref} {text_md?, applies_to?}`: the 🔏 is the new version's seal (step-up
  `rule.seal` or `oversight.order`, target = ref; the seal route takes either too); the previous version goes to `history`, the first
  report comes 24 hours after this seal; a retired rule answers 409. `counts.violations` = findings that name the rule (its ref in
  their evidence or text); `fixed` = those fixed, verified or closed. The report is stream `rule.report` (topic `oversight`) and one
  `report` notification (`link_kind: "rule"`). `StandingOrder.applies_to` (§18.1) is the same union.

### 29.4 The holding's secretary (dispatcher, chief of staff)
- `POST /orders/preview {text, source}` (owner) → a `Route` and one line:
  ```
  Route { companies: [code], department, collaborators: [code], output_kind: "post"|"reel"|"story"|"article"|"report"|"plan"|"code"|"answer"|"other",
          count: int|null, budget_tokens, mode: "single"|"council", player, preview_fa, confidence: 0..1, why_fa }
  ```
  `preview_fa` e.g. «→ تریدیار/رسانه + IG-Hub/انتشار؛ خروجی: ۳ ریلز؛ بودجه: ۴۰۰ هزار توکن».
- **How:** rules first (`apps/api/seed/order_rules.yaml`, which now names `MEDIA` and output words: «کلیپ، ریلز، ویدیو، پست، استوری،
  اینستاگرام، تلگرام، انتشار، محتوا»), then one light-model call only when the rules leave the company or the department open.
  The secretary remembers the owner's corrections and every «نه» reason (`owner.dispatch_memory`), and reads them first.
- **Defaults:** `mode: "single"`; `council` only when the owner says so («شورا») or the order is an outside question (§29.8).
  `budget_tokens` from the output kind's table (data) and never below the department's floor (§29.6).
- `POST /orders {text, source, file_id?, route?}`: with `route` (the preview, possibly edited) it is followed exactly; without, the
  secretary decides as above. A production order goes to the department that owns the output (a media order to the company's media
  director, never to AI operations; finding 1 of prompt 20).
- **Several companies:** one root work in the first company, one child work per collaborator (on that company's CEO or department; its
  server's Claude through the runner when the work is on the server, §26), and one `OrderReport` over all of them.
- **As built (prompt 21, additive):**
  - `Route` adds `kind: "work"|"code"|"meeting"|"question"|"server"`: how it is carried out (`question` single = the advisor,
    `question` council = the council v2 on the company's CEO, `server` = an inside question to the company's own Claude on its
    server). `companies[0]` holds the root work; every other company in `companies` or `collaborators` gets one requested work
    (`requested_by_work_id` = the root; its department when it has one, else its CEO) with the output kind's base budget.
  - `POST /orders` answers its `route` too (`OrderOut.route`, also on `GET /orders` items); the order keeps it.
  - An edited route that changes what the rules were sure of (company, collaborators, department, output kind, mode, player, kind)
    is remembered (`correction`, {from, to}); a like order (≥ 60% of its words shared) then follows the correction. An unknown
    company or department in a sent route answers 422; `kind: "server"` without an online server too.
  - The «نه» reasons of the home's cards are written with `dispatch.remember(tx, "no", text_fa, data)` and read with
    `dispatch.recall(tx, "no", text)`.

### 29.5 Long voice
- **On the phone:** continuous recognition that restarts itself at every pause until the owner stops; the text grows on screen.
- **Over one minute,** or when the phone's recogniser fails: the audio goes to the hub's STT in chunks:
  `POST /transcribe/sessions {purpose: "order"|"rule"|"message"|"note"}` → `{id}` (speech off on the hub: `409 channel_not_configured`,
  the app keeps the phone's text); `PUT /transcribe/sessions/{id}/chunks/{n}` (raw audio,
  ≤ 90 s each, in order, idempotent per n); `POST /transcribe/sessions/{id}/finish` → `{text, duration_s, chunks, segments}`. Up to
  `STT_SESSION_MAX_S` (default 1 200 s, 20 minutes); STT starts on demand (§27.3). A session unused for 30 minutes expires.
- **Before sending,** the whole text is shown and editable.
- **As built (prompt 21):** `POST /transcribe/sessions` → `201 {id, purpose, state: "open"|"finished"|"expired", chunks, seconds,
  max_s, chunk_max_s, expires_at}` (owner, `Idempotency-Key`; 503 while speech is off). Chunk numbers start at 0 or 1 and follow in
  order (a gap: 422); a chunk sent again with the same bytes changes nothing, with other bytes replaces it; answer
  `{n, file_id, duration_s, chunks, seconds}`; a chunk over 90 s or a session over `STT_SESSION_MAX_S`: 413. `finish` adds
  `engine`; a finished session answers its text again; a chunk after it: 409. An expired session answers **410 `session_expired`**.
  `GET /transcribe/sessions/{id}` (additive) shows a session to resume after a dropped connection.

### 29.6 The delegation budget
- **A floor:** a work request's token budget is never below the target role's floor: `3 × tokens_per_step` of its charter, or the median
  real input of that role's last 20 steps (`llm.calls`) × 3 when larger. A request below it is raised to it (finding 2 of prompt 20).
- **Cache apart:** a run's cap counts `input + output + cache_write`; `cache_read` counts at 10% (it is the same context read again).
  The full figures stay in the Token Treasury.
- **Short of budget:** a run that would pass its cap stops cleanly, its work goes `waiting` with a `budget` blocker, and its CEO gets
  «بودجه کم است، +X بدهم؟» (`work.budget {ref, add_tokens}`, A2, within the company's month envelope). The same button is in the order report.

### 29.7 Language: Persian only, and plain for the owner
- **Every player answers in Persian.** An answer whose letters are less than 60% Persian, or holding CJK characters, is refused and asked
  again once with the instruction repeated; a second failure ends that member `failed` («پاسخ فارسی نبود»). A web player's page residue
  (a trailing offer such as «مایلید …؟», buttons' text) is cut before the answer is kept.
  - **As built (prompt 21):** checked on every answer of a work's or a council's seat call (what reaches the owner); a code review,
    a cross-check's JSON verdict and an agent's own errand keep the language their task asks for. The member's reason code is
    `not_persian_retry` while asked again, `not_persian` when it failed. The residue patterns are data: `apps/api/seed/web_residue.yaml`.
- **Rewrite for the owner** («بازنویسی برای مدیر کل»): every text that reaches the owner (notification, card, order report, summary,
  council plan, home card) passes `humanize`: code first, the light model only when the code cannot fix it.
  - **Forbidden:** refs (`W-…`, `O-…`, `D-…`, `FI-…`, `H-…`, `RK-…`, `AR-…`, ids, uuids), table, service and tool names, error codes
    (`snake_case`), English technical terms, raw English or Chinese sentences. The list is data: `apps/api/seed/plain_language.yaml`
    (`forbidden` patterns and `replace` pairs such as `delivered → تحویل شد`, `runner → دستیار سرور`, `token → واحد مصرف`).
  - **Format:** «چه شد» · «چرا مهم است» · «از شما چه لازم است» (only when something is). Short sentences, Latin digits.
  - **Details:** the original stays under `details_md`, behind «جزئیات».
  - **Test:** `humanize.check(text) → [violations]` runs on a sample of every notification and card kind; a text with a violation is
    rewritten again before it is shown.

### 29.8 The council v2: outside advisors with a fact pack
- **Only for outside questions** (market, competitors, trends, content ideas, keywords and SEO, ad copy, new markets, pricing) or when
  the owner asks. An inside question (server, database, code, real figures) is answered by the company's own Claude on its server
  (a capped `claude` job, §26, §28.7), never by the council.
- **Fact pack** (`FactPack {company, at, figures: [{key, title_fa, value, source, at}], recent_posts: [...], notes_fa}`): built before the
  council from the hub's own data and the connections (§29.12), with no secret and no personal data.
- **Roles** (`owner.settings.council_roles`, default): captain Claude (splits the work, writes the plan), researcher Gemini (web, with
  sources), numbers DeepSeek (costs, returns, checks the researcher), devil's advocate GPT (another angle, critique).
- **Three rounds:** proposals (each with steps, cost and risk) → critique of the others' proposals → the captain's plan as a table
  «چه کسی · چه کاری · تا کی». Persian only (§29.7).
- **Output to the owner:** the plan in 5–10 lines with «اجرا کن», which makes an order (§29.4) from it. Each member's answer stays under
  «جزئیات». `Council` (§27.2) adds `round: 1|2|3`, `roles: {player: role}`, `fact_pack_ref`, `plan_md`.
- **As built (prompt 21, additive):** each member adds `role`; `Council` adds `rounds: [{round, members}]` (the rounds before the
  current one, each answer under «جزئیات») and `order_ref` (the order «اجرا کن» made). In round 2 each substitute that proposed reads
  the others' proposals; the captain reads every proposal and critique in round 3 (a child work of the council's assignee); with one
  answer the council says so plainly (§28.4). `POST /work/{id}/council/run` (owner, `Idempotency-Key`) is «اجرا کن»: `201 OrderOut`,
  the plan as an order of the council's company (its CEO), single mode, the output's budget; 409 before the plan or once it ran.
  `GET /fact-packs/{ref}` (owner) → `{ref, work_ref, company, at, figures, recent_posts, notes_fa}`; `fact_pack_ref` is `FP-` and
  the council work's number. `owner.settings.council_roles` is in `GET/PUT /owner/settings` (a player left out has no seat). A media
  council (images, video) keeps §27.2. An inside question's server job is read-only (the catalogue's allow-list), `max_turns` 15,
  `token_cap` the route's budget (at least 60 000); its answer is the work's deliverable (`produced_with.via: "server"`).

### 29.9 Readiness of each company for each working group
```
Readiness { company, group, ready: bool, checks: [{key, ok, title_fa, detail_fa, fix: {action, label_fa, target}|null}] }
```
- `GET /companies/{code}/readiness?group=content` checks: each seat filled by an active employee; hiring automatic; the month's envelope
  set; at least one sealed series per channel; the publishing channels connected (IG-Hub, Telegram); the media tools available (render
  and voice on the hub, started on demand like STT); the players; the runner online.
- Every failed check has a fix button (`hire`, `series.propose`, `connection.guide`, `media.on`, …).
- `POST /companies/{code}/readiness/fix {group, action, target}` (owner) runs a fix on the hub and answers the readiness again:
  `hire` (automatic hiring, §29.10), `hiring.open` 🔏, `lock.open` 🔏, `group.resume`, `series.propose` (a work item for the company's
  media director). A fix the app does itself (`connection.guide`, `envelope.set`, `media.on`, `runner.check`) answers it unchanged.
- **A sealed fix** (here and in `POST /orders/{ref}/fix`) accepts the step-up of the hub's own action (`hiring.start` on `holding`,
  `media.series` on the series digest) or of the fix itself (`hiring.open` / `series.seal` on the fix's target).
- ⟨1.11.1, as built⟩ check keys: `group`, `seat:<seat>` (required seats only), `hiring`, `envelope`, `channels`,
  `connection:<kind>` and `series:<kind>` per publishing channel, `media_tools`, `players`, `runner`. Fix actions:
  `group.resume` (target `<group>:<CODE>`), `hire` (`<CODE>:<role>`), `hiring.open` (`holding`), `envelope.set` (`<CODE>`),
  `connection.guide` (`<kind>`), `series.propose` (`<CODE>:<kind>`), `media.on` (`media`), `lock.open` (`holding`),
  `runner.check` (`<CODE>:<server>`). An ok check has `fix: null`. Render and voice are the opt-in profiles `media` and
  `tts`; the hub does not start them on demand yet (STT's host starter is not reused), so `media.on` is the owner's.

### 29.10 Automatic hiring (owner's decision, 2026-11-02)
- Hiring is `open` with `mode: "auto"` for every company: a CEO's `hire` within the company's month envelope is approved by code, and a
  working group's empty seat is filled by code (the seat's charter, its default model) when the group is on for the company.
- No card for the owner; each hire is a story and one line in the weekly summary (§29.1). Over the envelope: refused, a `budget` blocker.

### 29.11 Working groups (growth groups) as data
```
Group   { key, title_fa, purpose_fa, seats: [{seat, role, title_fa, count}], routines: [Routine], kpis: [{key, title_fa, unit, source}],
          connections: [kind], eligible: "has_channel"|"all", state: "on"|"off" }
Routine { key, title_fa, seat, schedule (RRULE, owner's zone), brief_md, max_tokens, state: "on"|"paused" }
Membership { group, company, state: "on"|"paused", joined_at, seats: [{seat, employee: code|null}] }
RoutineRun { id, group, company, routine, at, work_ref|null, state: "queued"|"done"|"failed"|"skipped", note_fa }
Experiment { id, group, company, week, hypothesis_fa, metric, target, result|null, kept: bool|null }
```
- **Defined in data:** `apps/api/seed/groups/*.yaml`; the first is `content` («تولید محتوا و انتشار», seats of the management review §4.1).
  A new group is a new file, no new code.
- **Members:** every active company that is `eligible` (`has_channel`: it has at least one publishing channel, §29.12) joins by itself,
  a new company too. The owner may pause a company's membership.
- **Routines** run on their schedule as small work items for the seat's employee (code makes the item; the model runs only in the
  employee's run, within `max_tokens`). Each run is in the history; a routine can be paused.
- **KPIs:** read daily from the connections into `growth.metrics_daily`; each group's KPI series per company feeds the home (§29.13).
- **Experiments:** one a week per company, written by the analyst, closed with its figure.
- Routes: `GET /groups`, `GET /groups/{key}`, `GET /groups/{key}/members`, `PUT /groups/{key}/members/{code} {state}`, `GET /groups/{key}/runs`,
  `PUT /groups/{key}/routines/{routine} {state}`, `GET /groups/{key}/kpis?company&days`, `GET /groups/{key}/experiments?company`.
- Seeded data (owner's answers, 2026-11-02): **the signal channel belongs to TradeYar**; **every Instagram account is on IG-Hub**.
- ⟨1.11.1, as built⟩ additive fields: `Group.version`, `Group.lead`; `Seat.optional` (`video_director`, `voice_producer`:
  no readiness gap); `Routine.task_class|null`, `Routine.needs|null` (`sealed_series`: the publishing routine runs only
  when the company has a sealed series, else a `skipped` run says why); `Kpi.seat`; `Membership.name_fa`, `.plan`,
  `.plan_at` (the content lead's `group.plan`), `MemberSeat {seat, role, title_fa, employee, optional}`;
  `RoutineRun.occurrence_at`, `.employee` (runs are listed newest period first). A routine's occurrence that the tick
  reaches more than 2 hours late is left (no backlog). `GET /groups/{key}/kpis` answers
  `{group, days, companies: [{code, name_fa, kpis: [{key, title_fa, unit, source, series: [{day, value}]}]}]}`.
  Experiment additive: `baseline`, `note_fa`, `closed_at`. Agent tools: `group.plan` (A1: the content lead or the CEO),
  `experiment.write` (A1: the analyst or the lead), `connection.read` (A0: own company; holding readers any).

### 29.12 Connections: what can be measured and managed
```
Connection { company, kind: "search_console"|"ga4"|"instagram"|"telegram"|"youtube"|"x"|"pagespeed"|"trends"|"bing"|"play_console",
             label_fa, state: "not_connected"|"connected"|"error", config: {...non-secret...}, secret: "set"|"missing",
             last_read_at|null, last_error_fa|null, daily: [{day, key, value}] }
```
- Order of work: Search Console, GA4, Instagram (through IG-Hub), Telegram, YouTube and X, PageSpeed, Trends, Bing, Play Console.
- **Secrets only in OpenBao** (`hq/growth/<company>/<kind>`); never shown, only `set`/`missing`. The owner puts one in with
  `PUT /companies/{code}/connections/{kind}/secret` (write-only, 🔏) or `make growth-secret`.
- `GET /companies/{code}/connections`, `PUT /companies/{code}/connections/{kind} {config}` (🔏 when it widens what is read),
  `POST /companies/{code}/connections/{kind}/test`, `GET /connections/guides/{kind}` (a one-page Persian guide, data in
  `apps/api/seed/connection_guides/`).
- **Daily read** by code (no model): each connected kind's free API into `growth.metrics_daily (company, kind, day, key, value, source)`.
  Instagram is read through IG-Hub's own runner (a fixed read-only job of its config), never with a token on the hub.
- No model guesses a figure a connection gives.
- ⟨1.11.1, as built⟩ `Connection` adds `missing_fa: [str]` (what it still needs), `reader: bool` (the hub reads it by
  itself), `secret_needed: true|false|null` (null: optional); `Daily` adds `subject` (the channel, site, property or
  account). `PUT …/{kind}` takes `{config, label_fa?}` (a secret-like key is refused); 🔏 `connection.config` targets the
  SHA-256 of the body; 🔏 `connection.secret` targets `<CODE>:<kind>`; its answer is `{company, kind, secret: "set"}`.
  `GET /connections/guides/{kind}` → `{kind, title_fa, body_md}`. `growth.metrics_daily` holds
  `(company, kind, day, key, subject, value, source)`; kind `hub` is the hub's own count (items published, cost per
  published item, experiments closed). Readers built: telegram (members per channel; a bot sees no post views),
  pagespeed, search_console, ga4, youtube, instagram (IG-Hub's read-only `exec` job; its command must read only);
  x, trends, bing, play_console: «خواندن خودکار این اتصال هنوز ساخته نشده». Every read leaves through egress
  (`POST /v1/http`, the call's own account) and is in the egress log.

### 29.13 The owner's home
```
Home { cards: {effective: Suggestion|null, good: Suggestion|null, progress: Progress|null},
       morning: [str × ≤5], groups: [{key, title_fa, companies: [{code, name_fa, kpi: {key, title_fa, unit, series: [{day, value}]}}]}],
       orders: [{ref, text_fa, state, summary_fa}], critical: [Notification] }
Suggestion { id, kind: "effective"|"good", company, title_fa, why_fa, impact_fa, cost_fa, source: "council"|"group"|"advisor",
             state: "new"|"run"|"later"|"no", reason_fa|null, order_ref|null, created_at }
Progress   { id, company, title_fa, before: {value, at}, after: {value, at}, kpi, source, work_ref|null }
```
- `GET /home` (owner). One effective and one good suggestion are chosen across all companies (highest impact per cost; never one the
  owner said «نه» to, by the secretary's memory). `Progress` comes only from a real connection's figures, before and after.
- `POST /home/suggestions/{id} {action: "run"|"later"|"no", reason_fa?}`: `run` makes an order (§29.4); `no` keeps the reason.
- **Morning** (5 lines, 08:00 Tehran, rule-based, §29.7 applied): yesterday's outputs, the best KPI move, what waits for the owner.
- Nothing technical is on the home but `critical` (§29.1). Stream `home.updated`.
- ⟨1.11.1, as built⟩ `Suggestion.name_fa`, `Progress.name_fa` additive; `HomeKpi.source` additive. `critical` holds
  the unread urgent notifications of the last 7 days (owner-visible only once §29.1's columns exist). `run` needs an
  `Idempotency-Key` (the order is made through `POST /orders` with it, once); `later` hides it 3 days. A suggestion
  whose text is not plain Persian after `humanize` is never stored or shown. Progress: a series' latest point (the
  last 3 days) against the point about a week before; `position`, `lcp_ms`, `cls` are better when they fall.

### 29.14 Employee state (as Grok Bot shows it)
- Each employee in `GET /companies/{code}/employees` and `GET /employees/{code}` adds
  `state: "idle"|"thinking"|"working"|"waiting"|"stuck"|"done"` and `stuck: {reason_fa, fix}|null`:
  `thinking` a model call is in flight; `working` a tool call or a server job runs; `waiting` its work waits on someone else or a
  card; `stuck` a blocker (§29.2) stops it; `done` it delivered today and has nothing open; else `idle`.

### 29.15 The approval boundary (as Claude Duet draws it)
| action | approval |
|---|---|
| read, draft, prepare, measure | free |
| publish in a sealed series | free (the seal was the approval) |
| publish outside a series, send an email, sign | the owner (A3, as today) |
| spend within the month envelope, hire (§29.10) | free, reported weekly |
| destructive on a server | the company's CTO; `server_delete` and production `db_drop`: the owner (§29.1) |

### 29.16 Stream types, decision kinds and step-up targets added
- Stream: `order.report`, `home.updated`, `group.run`, `connection.updated`, `suggestion.updated`, `rule.report`.
  ⟨1.11.1⟩ SSE topics: `home` (`home.`, `suggestion.`) and `groups` (`group.`, `connection.`).
- Agent tools: `order.ack`, `order.progress`, `work.budget`, `card.decide`, `group.plan`, `connection.read`, `experiment.write`.
- Step-up: `settings.destructive`, `connection.secret`, `connection.config`, `rule.seal` (= the standing order's seal).

## 30. Production lines: one engine for every company and every platform ⟨1.12⟩ (2026-11-04, prompt 22)

The owner's model (2026-11-04): content is made by a line of steps the owner sets once and edits freely; the line then runs and
publishes by itself. Nothing is written for one company: a **template** is the plan of steps, a **line** is a template set for one
company, one platform and one channel. A new company or platform is a new line (or a new template file), not new code.
"First rule (n8n), last AI": the rule steps run in n8n or plain code; only the steps that need a model use one.

### 30.1 Data
```
Template { key, title_fa, platform, version, steps: [StepDef], defaults: {...}, outputs_fa }
StepDef  { key, kind, title_fa, prompt_fa|null (with {{vars}}), settings: {...}, inputs: [step key], gate: "auto"|"owner"|"ceo",
           optional: bool, enabled: bool, max_attempts: 1..3, timeout_s }
Line     { ref "LN-0001", company, template, template_version, platform, channel: {kind, subject}, title_fa,
           schedule (RRULE, owner's zone)|null, state: "draft"|"on"|"paused", mode: "draft"|"auto",
           good_runs, auto_after: int (default 7), caps: {runs_per_day, tokens_per_run, opus_per_day},
           version, steps: [StepDef as overridden for this line], library: [asset id], created_at, updated_at }
LineVersion { line, version, body (the whole line), by, at, note_fa }
Run      { ref "RN-000001" (`LR-` is the growth page's), line, line_version, trigger: "schedule"|"owner"|"test"|"n8n"|"group", dry: bool,
           state: "queued"|"running"|"waiting"|"done"|"failed"|"skipped"|"cancelled", at, ended_at,
           steps: [StepRun], cost: {tokens, usd_equiv}, published: [{platform, kind, external_id|null, at, url|null}],
           metrics: {h24: {...}|null, d7: {...}|null}, note_fa }
StepRun  { key, kind, state: "pending"|"running"|"waiting"|"done"|"failed"|"skipped", attempt, started_at, ended_at,
           output: {text|null, file_id|null, files: [file_id], data: {...}}, via, tokens, usd_equiv, error_fa|null }
Asset    { id, company|null (null: the holding's, for every company), kind: "cover_folder"|"voice"|"prompt"|"pattern"|"music"|"brand",
           title_fa, config: {...}, files: [file_id], created_at }
```
- **Platforms:** `instagram_reel`, `instagram_post`, `instagram_story`, `youtube_short`, `youtube_long`, `telegram_post`,
  `site_article`. A platform is a string in data; adding one is a template plus, when it publishes somewhere new, an adapter.
- **Templates are data** in `apps/api/seed/lines/*.yaml` (loaded at start, versioned by their `version`); they name no company.
- **Versions:** every `PUT /lines/{ref}` makes a new `LineVersion`; a run records the version it ran; revert makes a new version
  with the old body.

### 30.2 Step kinds (each one adapter)
| kind | what it does | model / tool |
|---|---|---|
| `gpt_text` | the prompt (with the inputs filled in) to ChatGPT; text back | ChatGPT web (§21.13 seat call), never Codex |
| `dedupe` | the text against this line's past outputs (and the company's); too alike → the previous step again (≤ `max_attempts`) | code (pgvector or shingles) |
| `tts` | text to speech with the speaker and style the owner chose | Gemini TTS in Google AI Studio, **the owner's account** signed in in the hub's browser (egress recipe `aistudio-web`) |
| `pattern_search` | the best patterns for a query (images, links) | Pinterest read in the hub's browser (egress recipe `pinterest-web`), read only |
| `council_pick` | the council chooses one of the candidates, with its reasons | council v2 (§29.8) |
| `opus_build` | the build: script, audio, direction and editing plan, pattern → a render spec, the caption and the hashtags | Opus 5.5, effort `high`, through the router (task class `line_build`), within `caps.opus_per_day` |
| `render` | the spec to a video (or an image) | the media studio's renderer (§22, profile `media`), or the company's server through its runner (`settings.where`) |
| `cover` | the cover from the page's cover folder (an `Asset`) and the content | ChatGPT web with the folder's files |
| `quality` | the checks before publishing: not a repeat, every figure has its source (the owner's rules, §29.3), length, Persian, banned words | code |
| `publish` | the platform's API: IG-Hub (post or reel, caption, cover, time; then the story the same day), YouTube Data API, Telegram Bot API, the site | code, through egress |
| `deliver` | a file to the owner: his Telegram and a card in the app (e.g. a cover the platform could not set) | code |
| `n8n` | a named n8n workflow; waits for its signed callback | n8n |
| `seal` | waits for the owner's (or the CEO's) approval | — |

- Every step leaves through the Tool Gateway or egress, is in the Audit log, and every model call is in the ledger (`llm.calls`,
  caller `lines`). A step's output is kept (text in the row, files in the file store) and shown in the app.
- **Fallbacks are explicit:** a platform that cannot set a cover → `deliver` to the owner; a player that is signed out or limited →
  the step `failed` with a plain reason (never a silent switch to another model).

### 30.3 Running
- One Temporal workflow per run (`LineRun`); its steps in order; each its own timeout and attempts. A `seal` step (or a step with
  `gate: owner|ceo`) waits and raises a `line_publish` card (A3). `POST /line-runs/{ref}/rerun {from_step}` runs again from one step.
- **Draft and auto:** a new line is `draft`: its `publish` waits for the owner's seal. Each sealed run that published counts a good run;
  at `auto_after` the app offers «خودکار کن» (🔏 `line.auto`). `mode: auto` publishes without a seal.
- **Caps:** `runs_per_day`, `tokens_per_run`, `opus_per_day` per line; the company's daily token cap (§28.7) and the holding's lock and
  kill switch stop a run before its next step (`skipped` with the reason).
- **Dry run:** `dry: true` runs every step but `publish` and `deliver` (the app's «آزمایش کامل»).
- **Learning:** 24 hours and 7 days after a publish, code reads the post's figures from its connection into `Run.metrics`.

### 30.4 n8n (rule automations)
- Self-hosted n8n (Sustainable Use License, D-16) in the opt-in compose profile `automations`, port on `127.0.0.1` only, its own
  Postgres database. Its workflows are files in `automations/n8n/*.json`, imported by `make n8n-import`.
- Hub → n8n: a webhook with an HMAC-SHA256 signature (secret in OpenBao `kv/hq/n8n`); n8n → hub:
  `POST /internal/v1/lines/callback` signed the same way. n8n holds no model key and calls no model.

### 30.5 Routes
- Templates: `GET /line-templates`, `GET /line-templates/{key}`.
- Lines: `GET /companies/{code}/lines`, `POST /companies/{code}/lines {template, platform, channel, title_fa}` (a `draft`),
  `GET /lines/{ref}`, `PUT /lines/{ref} {title_fa?, schedule?, steps?, caps?, library?, note_fa?}` (🔏 `line.caps` when a cap rises),
  `POST /lines/{ref}/state {state: on|paused}`, `POST /lines/{ref}/mode {mode}` (🔏 `line.auto` for `auto`),
  `GET /lines/{ref}/versions`, `POST /lines/{ref}/revert {version}`, `POST /lines/{ref}/copy {company}` (a `draft` for another company).
- Runs: `POST /lines/{ref}/runs {dry?, from_step?}`, `POST /lines/{ref}/steps/{key}/test {inputs?}` (that step alone, nothing kept
  beyond the answer), `GET /lines/{ref}/runs`, `GET /line-runs/{ref}`, `POST /line-runs/{ref}/rerun {from_step}`,
  `POST /line-runs/{ref}/seal {approve: bool, note_fa?}`, `POST /line-runs/{ref}/cancel`.
- Calendar: `GET /calendar/lines?from&to&company?` → `{days: [{day, items: [{line, company, platform, at, state, run|null}]}]}`.
- Library: `GET /library?company&kind`, `POST /library` (multipart: `meta` JSON and files), `PUT /library/{id}`, `DELETE /library/{id}`.
- Voices: `GET /tts/voices` → `[{name, title_fa, gender, sample_file|null}]` (the speakers AI Studio offers, cached a day).
- Internal: `POST /internal/v1/lines/callback` (n8n, signed).
- Owner only (every route above but the internal one). Stream topic `lines` (`line.`, `line_run.`). Decision kind `line_publish`.
  Step-up targets `line.auto` (`<ref>`), `line.caps` (`<ref>`).

### 30.6 Templates seeded (prompt 22)
`instagram_reel` (script → dedupe → voice → direction → patterns → council pick → Opus build → render → cover → quality →
publish reel → story the same day), `instagram_story`, `youtube_short`, `youtube_long`, `telegram_post`, `site_article` (keyword →
outline → article → quality → publish → Search Console feedback). Each prompt is a starting text in Persian the owner edits.

### 30.7 Acceptance
A line made from `instagram_reel` for one company runs end to end (every adapter faked in tests; dry on the hub until the owner
connects AI Studio and IG-Hub), its outputs shown step by step in both apps; the same line copied to a second company runs with
only its settings changed.

## 31. Growth: learning, ready companies, owned channels, ads, automations from a sentence ⟨1.13⟩ (2026-11-04, prompt 22)

The owner's priorities after the gap review (`docs/GAP_REVIEW_2026-11-04.md`). Same rules as §30: data, not code per company;
rule first, model last; every call through the gateway or egress, in the Audit and the ledger; owner-only routes.

### 31.1 The learning loop of a line
```
RunFeatures { run, hook (first line), length_s|words, voice, pattern, publish_hour, caption_len, platform }   -- by code at publish
Insights    { line, metric (template defaults.insights.metric, e.g. "views"|"reach"|"clicks"|"watch_s"), window_runs,
              best: {hour, length_bucket, voice, pattern_source}, top_hooks: [text], lessons_fa: [str], updated_at }
```
- After the 24h and 7d reads (§30.3), code ranks the line's published runs by its metric and writes `Insights` (no model).
- Prompts may use `{{insights.lessons}}` and `{{insights.top_hooks}}`; a clear winner raises a home suggestion (§29.13).
- The `quality` step also checks the platform rules in data (`apps/api/seed/lines/rules.yaml`: links, financial claims, banned
  phrases per platform) before publish.
- Routes: `GET /lines/{ref}/insights`.

### 31.2 A ready company with one order (company kit)
```
Kit { key, title_fa, purpose_fa, team_template (seed/templates), groups: [group key], lines: [{template, platform, title_fa}],
      kpis: [key], connections: [kind], defaults: {...} }
```
- Kits are data in `apps/api/seed/kits/*.yaml`; none names a company.
- `GET /kits`, `POST /companies/from-kit {kit, code, name_fa, name_en, color_index?}` (🔏 `company.create`): the company with its
  team (the existing templates), its group memberships, its lines as **drafts** (`hq_api.lines.store.create_line`), its KPIs and its
  connections as `not_connected`; the answer lists what the owner still has to connect. A server is not created here (founding §).
- The secretary (§29.4) routes an order like «یک شرکت تازه برای … بساز» to a preview of this call; nothing is created before the seal.

### 31.3 Newsletter (owned channel)
- Listmonk (AGPL-3.0, self-hosted) in the opt-in compose profile `newsletter`, `127.0.0.1` only, its own Postgres database.
- A company's list(s), subscribers' consent kept by Listmonk (one-click unsubscribe is Listmonk's), campaigns made by a line of
  platform `newsletter` (new template) or by hand, A/B subject, scheduled send; open and click figures read daily into
  `growth.metrics_daily` (kind `newsletter`).
- Routes: `GET /companies/{code}/newsletter` (lists, counts, last campaigns), `POST /companies/{code}/newsletter/campaigns`,
  `POST /newsletter/campaigns/{id}/schedule {at}` (🔏 `newsletter.send` for a list over its size limit), `GET /newsletter/campaigns/{id}`.

### 31.4 SEO rank and competitors
```
Keyword    { company, phrase, site, target_url|null, state: on|paused }
RankDaily  { keyword, day, source: "search_console"|"searxng", position|null, url|null }
Competitor { company, name_fa, site|null, instagram|null, youtube|null, telegram|null, state }
CompetitorDaily { competitor, day, key, value, source }   -- new pages (sitemap), followers, subscribers, posts
```
- Our positions from Search Console (free, already connected); a small daily SERP check through the hub's SearXNG for our keywords
  and the competitors' sites (positions marked approximate); competitors' public figures through free APIs (YouTube Data API) and
  sitemaps through egress. No model reads a figure.
- A competitor's jump (new pages, a big follower move) raises an item for the company's growth lead, not the owner.
- Routes: `GET/POST/PUT/DELETE /companies/{code}/keywords[/{id}]`, `GET /companies/{code}/ranks?days`,
  `GET/POST/PUT/DELETE /companies/{code}/competitors[/{id}]`, `GET /companies/{code}/competitors/daily?days`.

### 31.5 One campaign calendar
```
CalendarItem { day, at|null, company, kind: "line"|"newsletter"|"ad"|"campaign"|"manual", ref, title_fa, platform|null,
               state, conflict_fa|null }
Campaign     { id, company, title_fa, goal_fa, starts, ends, channels: [platform], budget|null, state }
```
- `GET /campaign-calendar?from&to&company?` (`/calendar` is the change calendar of §20) merges line runs (§30), newsletters, ad campaigns and campaigns; conflicts (two posts on one
  channel within its spacing, an Iranian holiday from the calendar data) are marked. `GET/POST/PUT/DELETE /campaigns[/{id}]`.
- §30's `GET /calendar/lines` stays as it is.

### 31.6 Ad budgets that stop by themselves
```
AdAccount { company, platform: "google_ads"|"meta_ads", account_id, state }          -- a connection kind (§29.12), secret in OpenBao
AdRule    { company, scope (account|campaign id), daily_cap, window_days, min_roas, min_spend_before_judging, action: "pause"|"notify",
            state: on|off }
AdDaily   { company, platform, campaign_id, day, spend, clicks, conversions, revenue, roas }
```
- Daily read by code (the platforms' free APIs, through egress); revenue from the revenue module (§19) where attributed.
- A rule that trips **pauses** the campaign through the API (reversible), writes the Audit and tells the company's growth lead and
  the owner's weekly summary; it never raises a budget. Raising a cap is 🔏 `ads.cap`.
- Routes: `GET /companies/{code}/ads` (accounts, campaigns, last 30 days), `GET/POST/PUT/DELETE /companies/{code}/ad-rules[/{id}]`,
  `POST /ads/campaigns/{platform}/{id}/resume` (🔏 `ads.resume`).

### 31.7 An automation from one sentence
```
Automation { ref "AT-0001" (`AU-` is the archive's), company|null, sentence_fa, rule: {trigger, conditions, actions}, state: "proposed"|"on"|"off",
             runs: int, last_run_at|null, n8n_workflow|null }
trigger    { kind: "schedule" (RRULE) | "event" (stream type) | "metric" (connection key, op, value, window) }
actions    [ {kind: "work.create"|"line.run"|"line.pause"|"notify.owner"|"notify.lead"|"ad.pause"|"n8n.run", args} ]  -- allow-list only
```
- The owner writes one Persian sentence; one router call (task class `automation_compile`, a mid model) turns it into the JSON above
  against a strict schema; the app shows it back in plain Persian (`preview_fa`) with what it will and will not do; nothing runs
  before the owner's seal (🔏 `automation.seal`). Running is code (a tick and the stream), never a model; an action outside the
  allow-list is refused at compile time. `n8n.run` and rules that need n8n are exported as an n8n workflow (§30.4).
- Routes: `POST /automations/compile {sentence_fa, company?}` → `{rule, preview_fa, refused_fa: [..]}`, `POST /automations {rule,
  sentence_fa, company?}` (proposed), `POST /automations/{ref}/seal`, `POST /automations/{ref}/state {on|off}`, `GET /automations`,
  `GET /automations/{ref}` (with its runs).

### 31.8 Stream, decisions, step-up
- Stream: `insights.updated`, `rank.daily`, `competitor.jump`, `ad.paused`, `automation.run`, `campaign.updated` (topic `growth`).
- Step-up: `company.create`, `newsletter.send`, `ads.cap`, `ads.resume`, `automation.seal`.


## 32. Talk: the owner's conversation with the holding, by voice or text ⟨1.14⟩ (2026-11-04, prompt 23)

The owner's request (2026-11-04): one place, apart from the yellow order button, where the owner talks (holds a button, types, or
speaks hands-free) with the **holding secretary**, the **overseer**, the **personal assistant**, or any manager of any company. Each
persona answers in its own voice, reads everything it is allowed to read, and turns talk into work **only when the owner wants**.
The voice engine's API key is given inside the chat, checked at once, shown as a light, and every cent spent is on a live meter.

Principles (on top of §0):
- **One engine, personas are data.** A persona is a charter + a voice + a brain setting + a tool allow-list. A new persona, a new
  voice engine or a new provider is data and one adapter file, never a new screen or a new engine.
- **Talking is A0.** A turn reads; it never writes business data. Work comes out of talk only through a **card** the owner taps,
  and the card runs the existing route (§29.4 orders, §18.11 hiring, §20 decisions, §29 owner rules, §31.7 automations) with that
  route's own confirmation and step-up.
- **Consult is the default.** Minutes and tasks are made only when the owner asks (§32.3).
- **One filter for the companies.** The holding secretary is the only secretary; what the owner tells a company to do becomes an order
  through the dispatcher (§29.4), so every company's work keeps one path and one Audit.
- **Voice never stops.** An engine that fails or reaches the owner's cap hands the sentence to the next engine in the chain; the
  local engine (§22.3) is always last; text always works.
- **The key never enters a conversation, a log, the Audit body or a model prompt.**

### 32.1 Personas and conversations
```
Persona      { key: "secretary"|"overseer"|"assistant"|"advisor"|"manager", role (charter key), title_fa, company|null,
               voice: {engine, voice, rate: 0.8..1.25}, brain: {task_class: "talk_turn", effort}, tools: [tool], face (avatar file),
               consult_only: bool }
Conversation { ref "CV-0001", title_fa, persona (current key or role@CODE), present: [persona], mode: "consult"|"work",
               started_at, last_turn_at, turns: int, summary_fa|null, cost: {tokens, usd_equiv, voice_usd}, open_cards: int }
Turn         { id, conversation, n, by: "owner"|persona, source: "typed"|"hold"|"handsfree", text, say_fa|null, show_md|null,
               cards: [Card], audio: [{seq, file_id, seconds, engine}], tokens: {input, output, cache_read, cache_write},
               voice: {engine, seconds, audio_tokens, usd}|null, state: "streaming"|"done"|"stopped"|"failed", reason_fa|null, at }
Card         { id, turn, kind: "order"|"ask"|"hire"|"decision"|"planner"|"rule"|"automation"|"minutes"|"invite",
               title_fa, body_fa, payload, state: "offered"|"done"|"dismissed"|"failed", made: [ref], reason_fa|null }
```
- Personas come from `apps/api/seed/talk/personas.yaml` (the fixed three, `advisor`, and `manager`, a template filled by role and
  company). The owner changes voice, engine and effort in the app (`PUT /talk/personas/{key}`); the charter is not editable here.
- **The holding secretary** (`secretary`, title «منشی هلدینگ») is a new conversational charter `agents/roles/holding_secretary.md`;
  the meeting secretary (`secretary.md`, §20.1) and the dispatcher code (§29.4) stay as they are, and the dispatcher is her "hand"
  for orders. The overseer and the assistant use their charters (`overseer.md`, `assistant.md`).
- Default voices (owner's request; the owner picks the exact voice by ear): secretary a woman's voice, overseer a man's voice,
  assistant a young man's voice; managers from a pool (`seed/talk/voices.yaml`), each role@company keeps its voice once given.
- The faces sit at the top of the talk screen. The app opens the talk screen from a **separate button** (not the yellow order button,
  which stays the quick order of §29.4/§29.5).

### 32.2 A turn: the brain
- `POST /talk/conversations/{ref}/turns {text, source, client_id}` (owner, `Idempotency-Key`) → `202 {turn, events}`; the answer
  streams on `GET /talk/turns/{id}/events` (SSE): `text` (delta of `show_md`), `say` (a finished spoken sentence), `audio`
  `{seq, file_id, seconds, engine}`, `card`, `invite`, `meter`, `done`, `error {code, reason_fa}`.
- **Context, built by code:** the persona's charter (cached 1 h), the owner's memory, the conversation's summary, the last 12 turns,
  and a small **now pack** (open critical items, waiting decisions, today's orders and their state; for a manager, its company only).
- **One router call** per step, task class `talk_turn` (effort from the persona), streaming. Tools: read-only (A0) from the persona's
  charter allow-list, executed through the Tool Gateway as in runs (§16), at most `TALK_TOOL_STEPS` (default 4) per turn and
  `TALK_TOKENS_PER_TURN` (default 60 000) tokens; tool outputs are untrusted data (`hq_common.untrusted`).
- **The answer is a strict schema:** `{say_fa (≤ 400 characters, what is spoken), show_md (the full answer on screen),
  cards: [≤ 3], invite: {role, company}|null}`; code validates it; a card of a kind the persona may not offer is dropped.
- **Deep questions** ("analyse the last month of TY's sales") are not answered by guessing: the persona offers an `ask` card; tapped,
  it becomes a work of the right role (as §29.4 with `output_kind: "answer"`); the result comes back into the **same conversation** as a
  turn of that persona («جواب آمد») with a notification.
- **Brain unavailable** (the router has no capacity, e.g. the subscription's window is spent): if the owner enabled the optional
  `gemini-text` connection (off by default; the same Google key), the turn uses it and says so in `show_md`; otherwise one plain line
  «الان به مغزم دسترسی ندارم؛ تا … صبر کنید یا متن را بفرستم برای …» and nothing is lost. Never a 5xx to the app.
- Every call is in the Token Treasury under domain `talk` (input, output, cache, thinking).

### 32.3 Consult and work
- **`consult` (default):** the conversation is stored; nothing else is made. A card appears only when the owner says something
  imperative (the rules of `seed/order_rules.yaml` and `seed/talk/intents.yaml`, code first) — at most one unsolicited card per
  `TALK_CARD_EVERY` (default 5) turns. A persona never turns advice into minutes by itself.
- **`work`:** by the toggle, or the owner's words («جلسه‌ی کاری»، «صورت‌جلسه کن»، «تسک‌بندی کن»). At «پایان جلسه» (or the words),
  one `minutes` card: a 5–10 line summary, decisions, and tasks (each with company, department and due date the owner can edit);
  «اجرا کن» makes one order per task through the dispatcher (§29.4), linked to `CV-…`; the minutes are kept with the conversation.
- «صورت‌جلسه کن» in any mode makes one `minutes` card from the conversation so far (`POST /talk/conversations/{ref}/minutes`).
- `consult_only` personas (the overseer) never offer order cards; they offer `decision` or `ask` only.

### 32.4 Calling a manager in, and the company filter
- From the `+` face (company → role) or by voice («مدیرعامل تریدیار را بیاور»، «مدیر رسانه‌ی … توضیح بده»; rules first, then the
  turn's `invite`): `POST /talk/conversations/{ref}/invite {role, company}` → the persona `manager` with that role@company joins
  `present` and answers next. Its tools are scoped to its company (RLS, as its runs); its charter and voice are its own.
- The secretary moderates: code writes the one-line notice («مدیرعامل تریدیار آمد»); the owner returns to her by her face or «منشی».
- **Everything the owner tells a manager to do** becomes a card: `order` (dispatcher route preset to that company/department),
  `hire` (that manager's hiring proposal, §18.11, sealed as usual), `decision`. A manager in talk never acts directly; the work runs
  in the company's normal runs and appears in the order report (§29.4) and the conversation.
- No secretary per company (the app stays simple); the persona table allows one later without a new engine.

### 32.5 Voice engines, the key in the chat, the light
```
VoiceEngine { key, title_fa, provider: "google"|"local", model, languages: int, rank_fa, key_pattern|null, state: "missing"|"checking"|"ok"|
              "failing"|"capped", reason_fa|null, checked_at|null,
              price: {text_in_per_m, audio_out_per_m, audio_tokens_per_s, valid_until|null, next: {from, text_in_per_m,
                      audio_out_per_m}|null, source_url, as_of}, voices: [{name, gender_fa, sample_file|null}] }
```
- `key_pattern` is the provider's key shape (a regex) the app uses to keep a pasted key out of the composer.
- Registry `apps/api/seed/voice/engines.yaml`, adapters `apps/api/src/hq_api/voice/engines/*.py` (one interface, like §30's steps):
  - `gemini-3.8-flash-tts` (the best quality, 130 languages);
  - `gemini-3.8-flash-lite-tts` (about one third cheaper, 101 languages; Persian checked by the owner's ear before use);
  - `piper` (local, free, §22.3; always the chain's last).
- Google calls go through **egress** (channel `gemini-tts`, host `generativelanguage.googleapis.com` only); egress reads the key from
  OpenBao `kv/hq/voice/google`. The audio is encoded on the hub (Opus) and stored as files of the conversation, one per sentence.
- **The key in the chat:** the talk composer has a 🔑 button that opens a secure sheet (masked, no suggestions). A key-shaped string
  typed or pasted into the composer (patterns per provider in `engines.yaml`, e.g. `AIza[0-9A-Za-z_-]{35}`) is **not sent**; the app
  moves it into the sheet. `PUT /voice/providers/{provider}/secret {secret}` 🔏 `voice.secret` (target = provider) → `202
  {state: "checking"}`; the hub writes OpenBao, then checks: (1) a free metadata call (`models.get`) for each model of the provider;
  (2) a one-word speech («سلام»), its cost on the meter. The result arrives as `voice.engine` on the stream: `ok`, or `failing` with
  a plain reason mapped from Google's answer («کلید درست نیست»، «این کلید به مدل صدا دسترسی ندارد»، «صورتحساب این پروژه فعال نیست»،
  «سهمیه تمام شده است»). `DELETE /voice/providers/{provider}/secret` 🔏 removes it.
- **Server defence:** every turn's text is scanned before storage and before any model call; a key-shaped string is replaced by
  «[کلید حذف شد]» and the persona answers «کلید را با دکمه‌ی 🔑 بدهید». The Audit says only «voice.secret set».
- **The light** (app header of the talk screen, one dot per engine in use): green `ok`, yellow `checking`, red `missing`/`failing`
  (tap: the reason and the fix), amber `capped`. Rechecked by code every 6 h and after any failure (metadata call only, free).

### 32.6 The meter and the cap
```
VoiceMeter { period: "today"|"month", voice_usd, cap_usd|null, projected_usd, by_engine: [{engine, usd, seconds, audio_tokens}],
             by_persona: [{persona, usd, seconds}], talk_tokens, talk_usd_equiv, price_note_fa|null, updated_at }
```
- Every speech call writes one usage row with **Google's own token counts** (`usageMetadata`) and the price in force at that moment;
  the local engine writes seconds at 0 USD. LLM tokens of talk come from the router's ledger (domain `talk`).
- `GET /voice/meter?period=today|month` → `VoiceMeter`; the stream sends `voice.meter` after every turn, so the counter moves live.
  `projected_usd` = month to date ÷ days elapsed × days in the month (code).
- Honest label under «جزئیات»: the meter is Google's tokens × the price table; Google's bill (tax, currency) can differ slightly.
- Prices are data with `valid_until` and `next`, so a scheduled change applies by itself; the owner edits them in the app
  (`PUT /voice/engines/{key}/price`) and the app warns 14 days before a `next` price («از ۱ ژانویه قیمت دو برابر میشود»).
- **The cap is the owner's:** `owner.settings.voice {month_cap_usd|null, warn_at: 0.8, chain: [engine]}` (`GET/PUT /owner/settings`).
  On first key, the app asks for the cap (no default is set by anyone else). At `warn_at`: one notification. At the cap, or when an
  engine fails: the next sentence uses the next engine in the chain, the light turns amber/red, one line in the chat; Piper is last,
  so the voice never stops. Nothing raises the cap but the owner.

### 32.7 Speaking, hands-free, interrupting
- **In:** typed; **hold** (the talk screen's own button: hold, speak, release); **hands-free** (tap once: the app listens, a turn
  ends after `TALK_SILENCE_MS` of silence, default 1 200, and listening resumes after the answer). The phone's recogniser first;
  long speech goes to the hub's STT (§29.5, `purpose: "talk"`, additive).
- **Out:** the first sentence is spoken as soon as it is ready (sentence streaming); a short local sound while tools run (no cost).
  Target p50 time to first audio ≤ 3 s, measured on deploy (a target, not a promise).
- **Barge-in:** when the owner starts speaking, playback stops and `POST /talk/turns/{id}/stop` ends generation; sentences not yet
  spoken are not synthesised, so not billed.

### 32.8 Memory and records
- Every turn is stored forever (§0). A summary every 10 turns (task class `talk_summary`, a light model) feeds the context.
- The owner's facts go to memory only when the owner says so («یادت باشه»، rule) or taps «به خاطر بسپار» on a turn.
- `GET /talk/conversations?persona&q&cursor` with full-text search (as §5.3); `GET /talk/conversations/{ref}` with its turns page.
- Retention of audio files follows the files' policy; text is never deleted.

### 32.9 Routes, stream, step-up, policy
| Method | Path |
|---|---|
| GET | `/talk/personas` |
| PUT | `/talk/personas/{key}` `{voice?, engine?, effort?}` |
| GET / POST | `/talk/conversations` (`POST {persona, role?, company?, mode?}` → 201 `Conversation`) |
| GET / PATCH | `/talk/conversations/{ref}` (`PATCH {mode?, title_fa?}`) |
| POST | `/talk/conversations/{ref}/turns`, `/invite`, `/minutes` |
| GET | `/talk/turns/{id}/events` (SSE) |
| POST | `/talk/turns/{id}/stop` |
| POST | `/talk/cards/{id}/run` `{payload?}` (the owner's edits) → `{made: [ref]}`, `/talk/cards/{id}/dismiss` |
| GET | `/voice/engines`, `/voice/engines/{key}/voices`, `/voice/meter` |
| PUT / DELETE | `/voice/providers/{provider}/secret` 🔏 `voice.secret` |
| POST | `/voice/engines/{key}/check`, `/voice/sample {engine, voice, text?}` (a short sample; its cost on the meter) |
| PUT | `/voice/engines/{key}/price` |
- All owner-only (OPA `talk.rego`, 100% coverage like every policy). Errors in Persian (`message_fa`); a provider's refusal is `502`
  only for a sample or a check the owner asked for; a turn never answers 5xx (it falls back, §32.5–32.6).
- Stream topic `talk`: `talk.turn` (done/failed), `talk.card`, `voice.engine`, `voice.meter`.
- Step-up: `voice.secret`. Cards keep the step-ups of the routes they run.
- Data: migrations `0043` (schema `talk`: `conversations`, `turns`, `cards`) and `0044` (`talk.voice_usage`, `talk.engine_state`), RLS as the rest
  (manager turns carry `company_id`). Router task classes `talk_turn` and `talk_summary` (migration and router seed, as §31.7).

## 33. Money and the Grok-like working style: usage in the advisor's words, crypto payments, revenue, CRM, parallel agents, the company journey, personas, workspaces ⟨1.15⟩ (2026-11-05, prompt 24)

The owner's request (2026-11-05): the usage report comes from the holding to the advisor, who delivers it in plain human words; the open items
of the Grok gap review (`docs/GAP_REVIEW_2026-11-04.md`) are built, with a mid model (a "Sonnet class" router assignment) wherever a model
is needed; the companies' payment gateways are crypto on chain, and they are reviewed and read.

Principles (on top of §0, §30, §31):
- **Numbers by code, words by a model.** Every figure, rate, forecast and match is computed by code from stored rows; a model only phrases,
  drafts or estimates, and an estimate is always labelled «تخمین» with its basis.
- **Money is read, never moved.** The hub never holds a private key, never signs a transaction, never approves or rejects a company's payment.
  It reads the companies' own records (through their runner, §26) and the public chain (through egress), and reconciles the two.
- **Companies are data.** Every adapter, plan, stage and persona is a row or a seed file; nothing names a company in code.
- **Every model call** has its own task class, goes through the LLM Router and is in the Token Treasury.

### 33.1 Usage in the advisor's words
- **The pack (code):** `UsagePack { period: "day"|"week", from, to, by_domain: [{domain, tokens, usd_equiv, share}], by_company: [...],
  top_runs: [{ref, role, tokens}], voice_usd, lines: {runs, tokens}, ads_spend_usd, vs_prev: {tokens_pct, usd_pct}, anomalies: [{kind,
  note}] }` from the Token Treasury (§20.1 query), the voice meter (§32.6), lines (§30) and ads (§31.6).
- **The words (model):** one router call, task class `usage_report` (mid model, low effort, ≤ 4 000 output tokens), the advisor's charter
  voice: what happened, where it was high and why (from the pack only), one concrete saving. Strict schema `{lines_fa: [3..8], saving_fa}`.
- **Delivery:** daily at 07:55 Tehran, 3 lines inside the morning summary (§29.13); weekly (Saturday 09:00 Tehran) the full text as a message
  of the advisor's thread `A` with the pack under «جزئیات»; in Talk (§32) the advisor reads the latest one aloud when the owner asks
  («گزارش مصرف»), from the stored text (no new model call).
- `GET /usage/reports?period&cursor` → `UsageReport { ref "UR-0001", period, from, to, pack, text: {lines_fa, saving_fa}, at }`;
  `POST /usage/reports {period}` (owner) makes one now.

### 33.2 Crypto payments, read and reconciled
What the companies do today (review of 2026-11-05): users pay USDT on chain (BEP20 on BSC and TRC20 on TRON) to the company's public
wallet and submit the transaction hash; there is no third-party processor and no webhook. The hub therefore reads two independent sources:
```
PaymentSource { id, company, kind: "ledger"|"chain", adapter, network: "bsc_usdt"|"trc20_usdt"|null, address|null (public),
                state: "not_configured"|"ok"|"error", last_read_at|null, last_error_fa|null }
Payment       { id, company, source, ext_id, customer: pseudonym, plan, amount_usdt, network|null, tx_hash|null, paid_at,
                period_start|null, period_end|null, status: "matched"|"ledger_only"|"chain_only"|"amount_mismatch"|"pending_chain",
                checked_at }
Reconcile     { company, day, ledger_count, chain_count, matched, ledger_only, chain_only, amount_mismatch, note_fa }
```
- **Ledger (the company's own records):** a runner job kind `ledger` (§26, runner 0.3.0) runs the company's installed read-only ledger
  query on the company server against a SELECT-only database role the company creates (its DSN lives only on the company server, in the
  runner's config, never on the hub). **The query itself lives on the company server** (`~/.config/hq-runner/ledger.sql`, written by
  that server's own Claude): this repository is public and never holds a company's schema. The hub keeps only the **output contract**
  (`apps/api/seed/payments/ledger_v1.yaml`: the columns `ext_id, customer, plan, amount_usdt, network, tx_hash, paid_at, period_start,
  period_end, kind` with their types and rules), sends `{contract: "ledger_v1", since_cursor}` and validates every row it gets back. Customer ids are hashed on the company
  server (HMAC with a per-company salt kept there) before they leave it. Rows of a store's in-app billing carry `amount_usdt: null` and are
  counted, not summed.
- **Chain (public):** egress channel `chain-read` reads USDT transfers **to** the configured public addresses: BSC through a public JSON-RPC
  (`eth_getLogs` on the USDT contract, Transfer topic, `to` = address) and TRON through TronGrid's public API; confirmations counted by
  code (BSC 15, TRON 20, data). No key is needed; an API key, if the owner adds one for rate limits, is an egress secret like any other.
- **Reconcile (code, daily and on demand):** a ledger row with a tx hash that is on chain to our address with amount ≥ the plan's price is
  `matched`; a ledger row not found on chain is `ledger_only` (an approved payment without money: an alert); an on-chain transfer with no
  ledger row is `chain_only` (money without a customer: shown for the company to claim); a lower amount is `amount_mismatch`.
  Alerts go to the company's CEO and FIN manager; the owner sees only a weekly line unless a `ledger_only` exceeds 100 USDT (critical).
- **Never:** approve, reject, refund or extend anything in a company system; call a mutating admin endpoint; store a wallet's private key.
- Routes (owner; CEOs and FIN of their company read): `GET/POST /companies/{code}/payment-sources` (POST adds or changes one; a ledger
  source needs the runner paired), `POST /payment-sources/{id}/read` (`Idempotency-Key`), `GET /companies/{code}/payments?status&from&to&cursor`,
  `GET /companies/{code}/reconcile?from&to`.

### 33.3 Revenue analytics (code only)
```
RevenueBoard { company|null, period: "month", months: [{month, mrr_usdt, new_customers, churned, active, arpu_usdt}],
               churn_rate, ltv_usdt, cac_usdt|null, payback_months|null,
               cohorts: [{start_month, size, retained: [pct by month]}],
               forecast: [{month, mrr_usdt, low, high}], forecast_basis_fa,
               roi: {revenue_usdt, cost_usd: {tokens, voice, ads, servers|null}, ratio},
               cost_per_output: [{kind: "line_run"|"deliverable"|"order", count, usd_each}] }
```
- **MRR:** the paid amount spread over its period; **churned:** a customer whose last period ended > 7 days ago without a renewal; **LTV** =
  ARPU ÷ monthly churn (null when churn is 0 or fewer than 3 months exist); **CAC** = (ads spend + tokens of the growth domain) ÷ new paying
  customers of the month; **forecast:** Holt's linear trend on monthly MRR with a ±1.28σ band of its residuals, only with ≥ 4 months, and
  `forecast_basis_fa` says so in one line.
- **Revenue joins the radar:** §19.1's affiliate commission and §33.2's payments are summed per company in `GET /revenue/summary`
  (additive field `by_source`).
- `GET /revenue/board?company` (owner, the advisor, CEOs and FIN of their company).

### 33.4 Sales: a small CRM per company
```
Lead { ref "LD-000001", company, source: "support"|"telegram"|"site"|"payment"|"referral"|"manual", name_fa|null, contact: pseudonym,
       stage: key, value_usdt|null, next_at|null, next_fa|null, assignee: Actor|null, lost_reason_fa|null, events: [{at, kind, note_fa}],
       created_at, updated_at }
```
- Stages are data per company (default `new → contacted → qualified → trial → paid | lost`, from the kit, §31.2). A lead is made by code from
  the support desk (§19.3), Telegram intake (§19.8), a `chain_only` payment (§33.2) or by hand; `paid` is set by code when a payment of the
  same pseudonym arrives.
- **Follow-up:** code reminds the assignee at `next_at`; a mid-model call (task class `sales_followup`) drafts the message in the company's
  voice; sending goes only through the existing outbound guard and approval rules (§19.6, A2/A3 as today). Contact details stay in the
  company's own systems; the hub keeps a pseudonym and the company's display name only.
- Routes: `GET/POST /companies/{code}/leads`, `GET/PATCH /leads/{ref}`, `POST /leads/{ref}/draft` (the draft, not sent), `GET /companies/{code}/pipeline`
  (counts and value by stage, win rate, median days per stage).

### 33.5 Affiliate follow-up
- From §19.1's daily rows code computes **due vs received** commission per account and month; a gap over 5% after the exchange's
  settlement window opens a follow-up (a planner item for the FIN manager, with the figures and a drafted message, task class
  `sales_followup`); a paid gap closes it. `GET /revenue/affiliate-gaps?company`.

### 33.6 Decisions with their money impact
- `Decision` gains `impact: {revenue_usdt|null, cost_usd|null, horizon_days, basis_fa, kind: "measured"|"estimate"}|null` (additive).
- **Measured** by code where the inputs exist: `budget_change` (the delta), `hire` (model × charter tokens × the role's median use, priced by
  the router's table), ads (`ads.cap`, from the campaign's 14-day ROAS), a line's caps (its last 14 days per run).
- **Estimate** (task class `decision_impact`, mid model, one call per card, strict schema) only for `proposal` and `a3_action` cards, labelled
  «تخمین» with its basis; never for a card the owner has already decided.
- The owner's decision list can be sorted by impact (`GET /decisions?sort=impact`).

### 33.7 Agents in parallel
- A work may be split into up to `PARALLEL_MAX` (data, default 3) **independent** child works that run at the same time (the depth limit of
  2 stays). The parent's assignee proposes the split (`work.split {parts: [{title_fa, role, brief}]}`, A1); code refuses parts that depend
  on each other (a part naming another part's output).
- Each part is an ordinary work with its own run and budget share; the router's concurrency (per connection) still applies, so parts
  queue rather than overload.
- **The short meeting:** when every part is done, code gathers the deliverables and the parent's assignee writes one merge (its own run);
  a failed part is reported as such, never hidden. The order report (§29.2) shows the parts side by side.

### 33.8 The company journey
```
Journey { company, stages: [{key, title_fa, reached_at|null, evidence: {kind, ref}|null}], current, next_fa, days_in_stage }
```
- Stages are data (from the kit, default: `founded`, `server_ready`, `first_content`, `first_visitor`, `first_lead`, `first_payment`,
  `ten_paying`, `break_even`); each is reached by code from existing rows (company, servers, lines' first publish, analytics, leads,
  payments, revenue board). `next_fa` is one line from a mid-model call (task class `journey_next`) only when a stage changes.
- `GET /companies/{code}/journey`, `GET /journeys` (all companies on one timeline).

### 33.9 Personas and the message test
```
Persona { id, company, name_fa, summary_fa, pains_fa: [str], objections_fa: [str], channel_fa, source: "owner"|"kb_suggested", version }
PersonaTest { text, results: [{persona, score: 0..100, would_act: bool, objection_fa|null, fix_fa|null}], at }
```
- Personas are the company's data; the owner edits them; `POST /companies/{code}/personas/suggest` proposes up to 4 from the company's
  knowledge base (one mid-model call), saved only when the owner keeps them.
- `POST /companies/{code}/personas/test {text}` → `PersonaTest` (task class `persona_test`, one call for all personas, strict schema).
- A line step kind `persona_test` (§30.2, additive) gates a run: below the step's `min_score` (data) the run waits for the owner with the
  objections shown.

### 33.10 The company workspace (a working computer per company)
- A work can be done **on its company's own server** (`mode: "on_server"`): the server's Claude Code (§26.2 `server.claude`) works in a
  persistent folder `~/hq-workspace/<work-ref>` (runner 0.3.0 makes it; it survives across resumes) until the deliverable is ready or an
  approval is needed; A3 steps stop as `awaiting_seal` exactly as today. One workspace per work, never shared; it is removed 30 days after
  the work closes (runner, logged).
- The owner sees the workspace's progress in the order report and can stop it (`POST /work/{id}/stop`, existing).
- Only works of companies whose server is paired and on runner ≥ 0.3.0; otherwise the work runs on the hub as today.

### 33.11 Routes, stream, policy, data
- Stream topic `money`: `payment.read`, `payment.alert`, `lead.updated`, `usage.report`, `journey.stage`; topic `work`: `work.split`.
- Step-up: `payment.source` (adding or changing a payment source).
- OPA: `money.rego` and `grok.rego` with tests (100%). Errors in Persian; a company system or chain answering badly is `502` only on an
  owner's explicit read; scheduled reads record the error on the source.
- Data: migrations `0047` (payments, reconcile, revenue board caches), `0048` (usage reports, leads, decision impact, affiliate gaps),
  `0049` (journey, personas, the `persona_test` step), `0050` (work split and workspaces). Router task classes `usage_report`,
  `sales_followup`, `decision_impact`, `journey_next`, `persona_test`.
- Runner **0.3.0**: job kinds `ledger` (§33.2) and the `claude` job's `workspace` (§33.10). A company server on 0.2.x keeps working; the two
  features wait for 0.3.0.

## 34. The order answered live, and nothing technical to the owner ⟨1.16⟩ (2026-11-06, prompt 25)
The owner, 2026-11-06: «به محض فرمان باید اون مسئول … با من حرف بزنه و مرحله به مرحله با من پیش بره یا یه فرمان کلی بدم خودش بره همه
کارهارو بکنه» and «موارد فنی رو به من ارجاع ندید». Order W-000153 («مرحله به مرحله با فرمان من») sat «در انتظار فرمان مرحله اول» with
nowhere to answer: `order.ack` and `order.progress` existed in the api and the policy, but no gateway tool reached them, and no route let
the owner reply. This section is the base of §35 (every order a session).

### 34.1 The pace
- `owner.orders.pace`: `"step"` when the order says so (rules, data `orders.STEP_WORDS`: «مرحله به مرحله»، «قدم به قدم»، «گام به گام»،
  «با فرمان من»، «با من جلو» …), else `"auto"`. `OrderOut.pace`, `OrderRecord.pace`, `OrderReport.pace` (additive).
- ⟨2026-11-09⟩ `OrderIn.pace` (`"step"` · `"auto"`, optional, additive): the owner's own answer to «با من یا خودکار؟», which the apps
  ask before a new session is sent (the office, the order sheet, a council's «اجرا کن»); given, it **wins over the words** for the
  order's row and every brief its route writes. Absent (a talk card, a playbook, an older app), the words decide as above. A hub
  before it answers `422 validation_failed` with `fields.pace`; the apps then send the order without it and set the pace at once
  (`POST /orders/{ref}/pace`).
- The holder's work brief says how: **step** — record the steps (`order.ack`), do the next one, report it (`order.progress`), ask the owner
  (`order.ask`) and finish the run; **auto** — record the plan, split or delegate, report real steps, deliver; never wait for the owner
  (only an outside commitment is a `propose`).

- ⟨2026-11-09⟩ **A step order holds while it waits for the owner** (the owner: «دکمه با من رو زدم و شروع کرده برای خودش کار
  رو جلو بردن»). While a `step` order's turn is open (§34.3, the session not ended), nothing of the order runs: a `work` run of any
  of its works (the holder's or a colleague's it handed a part to) is refused at its claim with `owner_turn`, and a run already
  under way stops before its next step (the asker itself ends `done`; anyone else `refused`, `owner_turn`). A run the owner's own
  word started (`owner_reply:`, `nudge:`, `pace:`, `owner_turn_over:`, `session_reopened:`) and a `talk` run are never held.
  The held runs come back (reason `owner_turn_over:<ref>`) the moment he answers (`reply`), says «ادامه بده» (`nudge`, which now
  clears the open question too) or makes the order `auto`; the requeue sweep is the net. The activity line of a held run reads
  «منتظر جواب شما ماند؛ با جواب شما ادامه میدهد.»; its comeback «شما جواب دادید؛ کارش را ادامه میدهد». An `auto` order is
  never held. The holder's plan instruction says it: in a step order a part handed to a colleague is waited for (its output wakes
  the holder) before the step is reported and the owner asked.
- ⟨2026-11-10⟩ **The hold, tightened (the owner's recording of 2026-11-09 and the audit):**
  - A run his word started is exempt only when it was **queued after the question** it waits on (`queued_at >= ` the latest ask):
    «ادامه بده» a moment before a colleague asks does not answer that question.
  - «ادامه بده» (`nudge`) while a question is open is his answer to **whoever asked**: every asker's work runs again (reason
    `nudge:<ref>`), not only the holder's, and a talk-loop stop is lifted as a reply lifts it.
  - The asker's run that ends on its own question is `done` (it was reported as a cut, «خروجی ناقص»).
  - A session the owner **closed** takes no plan, step or question from a run that was still going (`order.ack`,
    `order.progress`, `order.ask` answer `409 work_closed`), and a run whose work was cancelled stops before its next step
    (`refused`, `work_closed`). Reopening brings back the plan tasks the close dropped.
  - **The step rule is said by code** in the holder's brief (`order.step_rule`, only in a `step` order): the plan's next open task
    by number and title; only that task in this run, and only when the owner's last word clearly says to start it; a word that
    asks for something else (to see or seal the cards, a question, a correction) is done as asked and starts no task.

### 34.2 The order's live talk
- `POST /orders/{ref}/talk` (owner) → `{conversation_ref}`: the order's conversation (§32), made once: work mode, the persona of the order's
  holder (`role@CODE` in an operating company; the holding's fixed persona of its role; else the secretary), its first turn the holder's
  hello. A step order opens it at once: `OrderOut.talk_ref`. `OrderReport.conversation_ref`, `TalkConversation.order_ref` (additive).
- In that conversation the persona sees «## The order you hold» (the order, its pace, the owner's open turn, the last 12 steps, blockers,
  outputs). An `order` card there is the owner's next word **on that order** (§34.3 reply), never a new order; any persona may offer it,
  on any instruction, without the unsolicited-card spacing.
- What the holder reports (`order.progress`) and asks (`order.ask`) comes into the conversation as the persona's turns; what the owner
  answers on the order's page comes in as the owner's turn.

### 34.3 The owner's turn
- **Agent tools (A1, every role but a system one; only someone working on the order):** `order.ack {ref, plan_fa, assigned?, due_at?}`,
  `order.progress {ref, step_fa}`, `order.ask {ref, question_fa}` → `/internal/v1/orders/{ref}/ack|progress|ask`.
- `order.ask`: `OrderReport.turn = {question_fa, at, by: Actor, who_fa}`, the order `waiting`, a step «سؤال از شما: …», one `decision`
  notification to the owner at once (link: the order's talk when it has one), the talk's turn. No «no progress» nudge while it is open.
- `POST /orders/{ref}/reply {text}` (owner, `Idempotency-Key`) → `OrderReport`: a step «مدیر کل: …», the turn cleared, and the asker's open
  work (else the holder's) runs again at once (`work.wake_assignee`, one queued run per work) with the dialogue in its brief
  (`order`: the order, its pace, the owner's open turn, the last 12 steps). An ended order: 409; an unknown one: 404.
  ⟨2026-11-09⟩ `text` is 1 to 10000 letters, as long as a talk turn (`TalkTurnIn.text`), and the step keeps all of it (it was 2000:
  the owner's long replies in F-0013 and F-0014 got `422`, `fields.text`).

### 34.4 Nothing technical to the owner
- The weekly review's agenda: a card or a finding of a technical domain only when critical (§29.1); a risk only of category `product`,
  `money`, `people` or `reputation`. Its brief: at most 8 plain lines, no refs, no technical matter, no inquiries; capped at 30 000 tokens;
  task class `advisor_review` on the mid model (router assignment by task class).
- The weekly technical summary (§29.1) goes to the technical team (its handler), not the owner.
- The advisor's charter (v8): plain for the owner (citations in `links`), nothing technical to the owner (to the AI operations head or the
  company's CTO by `inquiry.ask`), unless critical by §29.1.
- Data: migration `0051` (`owner.orders.pace`, `owner.order_reports.turn` and `conversation_ref`, `talk.conversations.order_ref`,
  `work.wake_assignee`). OPA: `order.ask` beside `order.ack`/`order.progress` (`routing.rego`).

## 35. Every order a session; the owner's office; company links ⟨1.17⟩ (2026-11-06, prompt 25)
The owner, 2026-11-06: «هر فرمان من باید یک سشن خودش رو داشته باشه تا بتونیم به نتیجه برسونیم و کار رو که اوکی کردیم و همه چی تموم شد
سشن بایگانی بشه یا پاک بشه» · «مدل مثلا چت جیپی تی رو به سشن فرمان اضافه بکنیم» · «همونجا … میگفتم برو اینو استخدام کن اینو بهش بسپر
اینکارو بکن … در انتها خط تولید و کار گروه رو راه اندازی میکردیم و بعد سشن رو میبستیم تا فرمان های منم بی صاحب نمیموندند» · «اون صفحه
خانه دفتر مدیر کله … شرکت ها به هم دیگه ارتباط داشته باشند و همه به هاب و بتونم این ارتباط هارو شکل بدم». Plan:
`docs/PLAN_2026-11-06_ORDER_SESSIONS.md`. §34 is its base. Any subject, not only content.

### 35.1 The session is the order
- **Every routed order has a holder and a session at once.** Every route makes a root work (a `question` single: the advisor's work, its
  answer the deliverable; `code`: the company's technical manager's work beside the workshop session; a kit: the secretary until sealed).
  The order's talk (§34.2) is opened on routing for every order (not only `step`); `OrderOut.talk_ref` is always set. A holder missing
  (no active employee): the secretary holds it and its first turn proposes the hire (a `hire` card) — never ownerless.
- **The order no longer ends by itself.** When its root works are delivered the session is `ready` and waits for the owner's OK
  (`POST /orders/{ref}/close`). Only `close` sets `ended_at`; the report still refreshes while open. A council's «اجرا کن» (§29.8) and a
  home suggestion's «اجرا کن» continue the same order (a reply), never a new F-ref, when they come from a session.
- `summary_fa` and every owner-facing text are humanized (§29.7); every owner-facing ApiError carries `message_fa`.

### 35.2 Shapes
```
SessionCard { ref,                       # F-… (the app's key; never shown)
              conversation_ref,          # CV-… the session's talk
              title_fa,                  # the order's words, plain, ≤ 80 chars
              holder: {code, title_fa, company, company_fa} | null,
              badge: "your_turn"|"ready"|"stuck"|"moving"|"closed",
              reason_fa,                 # one plain line: why this badge («مدیرعامل میپرسد: …»)
              brief: {done_fa, now_fa, need_fa},   # «چه شد · حالا چه · از تو چه», always filled
              pace: "auto"|"step",
              participants: [Participant],
              tasks: {done, total},
              opened_at, last_at, closed_at|null, hidden: bool }
Participant { key,                        # persona key: role@CODE | advisor | overseer | assistant | secretary | player:gpt …
              kind: "holder"|"person"|"player", title_fa, company|null }
SessionTask { id, n, title_fa, state: "todo"|"doing"|"done"|"dropped", by: "owner"|"agent", who_fa|null, work_ref|null }
```
- `OrderReport` (additive): `session: {state: "open"|"closed", badge, reason_fa, closed_at|null, hidden}`, `brief`, `tasks: [SessionTask]`,
  `participants: [Participant]`.
- **Badge by code:** `closed` — closed. `your_turn` — an open `turn` (§34.3), a blocker whose fix is the owner's, or a pending
  owner-visible decision of one of the order's works. `ready` — every root work delivered (or the holder reported done) and not closed.
  `stuck` — a blocker without an owner fix, `talk_loop`, or no step for `order_progress_hours`. `moving` — otherwise.

### 35.3 Routes (owner)
- `GET /sessions?state=open|closed|all&limit&cursor` → `Page[SessionCard]`; open: `your_turn`, `ready`, `stuck`, `moving`, each newest
  `last_at` first; hidden ones only with `state=all`.
- `POST /orders/{ref}/participants {kind: "person"|"player", key}` → `OrderReport`. A person: any persona key (managers of any company, the
  advisor, the overseer, the assistant). A player: `gpt`, `gemini`, `deepseek` (the substitutes §21.13; one signed out answers 409 with
  `message_fa`). `DELETE /orders/{ref}/participants/{key}` (never the holder).
- `POST /orders/{ref}/tasks {title_fa}` → `SessionTask`; `PATCH /orders/{ref}/tasks/{id} {title_fa?, state?, n?}` → `SessionTask`.
- `POST /orders/{ref}/close {verdict: "ok"|"cancel", note?}` (`Idempotency-Key`) → `OrderReport`: `ok` — the order `delivered`
  (`cancelled` when it has no final output), its open works cancelled except the permanent structures it set up (groups, lines,
  automations, rules); the session closed and archived (its talk read-only). `cancel` — the same, `cancelled`.
- `POST /orders/{ref}/reopen` → `OrderReport`: `ended_at` cleared, the session open, the holder woken.
- `POST /orders/{ref}/hide` · `POST /orders/{ref}/unhide` → `OrderReport` (nothing is deleted; a hidden session leaves every list).
- `POST /orders/{ref}/pace {pace: "auto"|"step"}` → `OrderReport`: the owner switches «با من / خودکار» at any time; a step
  «از این به بعد …» and the holder woken with the new instruction.
- Existing: `GET /orders/{ref}/report`, `POST /orders/{ref}/reply`, `POST /orders/{ref}/talk`, `POST /orders/{ref}/fix`.

### 35.4 Talking in a session
- `POST /talk/conversations/{ref}/turns` (§32) adds `to?: key|"all"`: `key` — that participant answers; `"all"` (also «نظر همه» in the
  owner's words) — each present participant answers once (at most 5, players included), then the holder sums up. Default: the holder.
- A **player** participant (persona key `player:gpt|gemini|deepseek`) answers through its substitute seat (§21.13) from the masked
  conversation; its turn is labelled with its model; it reads nothing of the hub but the conversation and «## The order you hold».
- Fixed personas join too (`invite` accepts `advisor`, `overseer`, `assistant`).
- **Cards in a session** (each runs the existing route with its own checks; what it makes is a step of the order):
  `order` (→ reply §34.3), `ask`, `hire` (any persona; `company` explicit), `delegate {to: code|role|department, text}` (a child work of the
  order's root for that employee/department), `budget {tokens}` (the order's budget fix), `group {company, group}` (the company joins the
  working group §29.11), `line {company, template}` (a production line from a template §30, its own seal), `decision`, `planner`, `rule`,
  `automation`, `invite`.
- Agent tools: `order.ack` takes `steps?: [str]` (→ agent tasks); `order.progress` takes `done?: [n]` (ticks tasks). A second `order.ask`
  while a turn is open joins the same turn (both questions; the reply wakes both askers). An open turn reminds the owner once after
  `order_owner_hours`.

### 35.5 The owner's office (the home)
```
Office { sessions: [SessionCard],          # open, as GET /sessions (≤ 30)
         approvals: [Decision], approvals_total,   # owner-visible pending only (≤ 10)
         money: {revenue_month_usd|null, spend_month_usd, budget_month_usd|null, line_fa},
         critical: [Notification],         # owner-visible critical only (§29.1)
         suggestions: [Suggestion],        # §29.13, any subject; «اجرا کن» opens a session
         canvas: Canvas }
```
- `GET /office` (owner). `GET /home` stays for older apps. Nothing on the office is fixed to one subject (no per-group KPI block).

### 35.6 Company links and the canvas
```
Canvas { nodes: [{code, name_fa, kind: "holding"|"company", x|null, y|null, line_fa, open_sessions}],
         links: [CompanyLink] }
CompanyLink { id, from, to, kind: "serves"|"publishes"|"feeds"|"sells"|"supports", purpose_fa, state: "on"|"off", open_works, updated_at }
```
- `GET /links` → `Canvas`; `POST /links {from, to, kind, purpose_fa}` → `CompanyLink`; `PATCH /links/{id} {kind?, purpose_fa?, state?}`;
  `PUT /canvas/nodes/{code} {x, y}`. Every company is linked to the hub (the holding node) implicitly. Every write audited (A1). Nothing
  deleted: a link is turned `off`.
- **Honoured:** the secretary's preview suggests collaborators along `on` links that fit the order (publishing → `publishes`, data →
  `feeds`…); a cross-company work request along an `on` link is accepted at once (`owner.settings.links_enforced`, default false: until
  the owner turns it on, requests stay open as today); `company.state` (agent tool) lists the company's links; in a session, people of
  linked companies are suggested first.

### 35.7 Stream, data, policy
- Stream topic `orders`: `session.updated {ref, badge}`; topic `holding`: `links.updated`.
- Data: migration `0052` (sessions: `owner.order_reports.closed_at`, `hidden_at`, `turn` asks, `owner.session_tasks`, talk persona keys
  `player:…`, card kinds `delegate|budget|group|line`, `talk.conversations.closed_at`, `work.wake_assignee` honours the locks),
  `0053` (`core.company_links`, `owner.canvas_nodes`, `owner.settings.links_enforced`).
- OPA: `sessions.rego` (owner routes), `links` in `internal.rego` (`work_create_ok` with `linked`), tests 100%.

## 36. Files in a session ⟨1.18⟩ (2026-11-06, prompt 26)
The owner, 2026-11-06: «میخوام اینجا فایل بفرستم برای سشن نمیتونم» — e.g. a font for the title of Pro-Chart's covers («تایتل بذاره
با فونتی که ما میدیم»).

### 36.1 Upload
- `POST /files` (§17.1) also accepts **fonts** (TrueType, OpenType, WOFF, WOFF2, by their first bytes → `kind: "font"`, ≤ 20 MB) and
  plain text / Markdown and ZIP archives (`kind: "document"`, ≤ 50 MB; a ZIP is stored, never unpacked by the hub). `FileRef.kind`
  gains `font` and `document`; a font's `FileRef.meta.family` is its family name (read in the untrusted child process).

### 36.2 A turn with files
- `POST /talk/conversations/{ref}/turns` adds `file_ids?: [uuid]` (≤ 10; the owner's own uploads). `TalkTurn.files: [FileRef]` on the
  owner's turn. The persona's model sees each file: an image as an image (when the brain takes images; else its description), a PDF's
  or a text's first pages as text, a font's family, a video's poster and transcript, an audio's transcript.

### 36.3 Files go with the order
- In a session (a talk bound to an order): every file of the owner's turns belongs to the order: a step «فایل از مدیر کل: <name>»,
  `OrderReport.files: [FileRef]` (newest first), and every run of the order's works sees them (`order.files` in its brief) and may read
  them with `files.read` (whatever its company). A font of the order is used by the creative overlay and the media studio when the work
  names it (`overlay.font_file_id`, `media.item` style `font_file_id`); IRANYekanX stays the default.
- Data: migration `0054` (`talk.turns.files`, the order's files, the file kinds).

## 37. Erasing for good, and cancel that works ⟨1.19⟩ (2026-11-06, prompt 26)
The owner, 2026-11-06: «روی لغو این فرمان میزنم اجرا نمیکنه و باید یه گزینه حذف هم داشته باشه که اصلا شاید یه سشن رو من میخوام پاک
کنم اصلا نباشه و قابلیت پاک کردن از بایگانی هم بذار … یا به کمک ایجنت ها یه چیزایی رو بگم پاک کنند». Hiding (§35) stays; erasing is
for good. Every erase is the owner's alone and sealed (🔏): an agent only proposes one.

### 37.1 A session erased
- `GET /orders/{ref}/erase/preview` → `ErasePreview {ref, kind: "session", title_fa, counts: {turns, files, outputs, works,
  notifications}, keeps_fa: [str]}`: nothing changes. `keeps_fa` names in plain Persian what stays (a working group or production line
  the session set up; one line in the audit book; the token and money figures, which the treasury must still add up).
- `POST /orders/{ref}/erase` 🔏 (action `session.erase`, target = ref; `Idempotency-Key`), open or closed, hidden or not. In one
  transaction: the order's open works are cancelled as `close {verdict: cancel}` does; then gone for good are the session (its report,
  steps, tasks, participants), its talk (conversation, turns, their voice and attached files), the order's files, the order's outputs
  (deliverables) and their files, its pending decisions (withdrawn), the notifications that point at the order or its works, the run
  transcripts of its works, and the works themselves. A stored file is destroyed only when no record that stays uses it. A guarded
  ledger row the hub cannot delete (the token ledger, the audit chain, a work event) keeps no text of the order: its words are
  replaced with «پاک‌شده» and it leaves every list and search. One audit entry `session.erase` (A3) holds the ref and the counts.
  → `{ref, erased: {turns, files, outputs, works, notifications}}`. Afterwards the order and its session answer `404`, and no list,
  search, office card, canvas, digest, brief or agent context shows it.
- A permanent structure the session set up (a working group, a production line) is never erased with it; erase it on its own page.

### 37.2 From the archive, and one output
- `GET /archive/records/{ref}/erase/preview` and `POST /archive/records/{ref}/erase` 🔏 (`archive.erase`, target = ref): the archive's
  own disposal (§23) run now instead of on its schedule: the record's files destroyed and the record removed; a tombstone keeps only
  the ref, the date and «به دستور مدیر کل». A record under a legal hold answers `409` with `message_fa` naming the hold.
- `GET /deliverables/{ref}/erase/preview` and `POST /deliverables/{ref}/erase` 🔏 (`output.erase`): one output and its files, its
  pending decision withdrawn; the work it belongs to stays (its step says «خروجی پاک شد»).
- A closed session in the sessions archive is erased with 37.1.

### 37.3 «پاکش کن» in words: an agent proposes
- Agent tool `erase.propose {kind: "session"|"archive_record"|"output", ref, why_fa}` (A1, every working role; the policy lets a role
  propose only what it can read): a decision card `erase` to the owner with the preview's counts. Approving it (🔏, target = the card's
  ref, bound to the preview) runs 37.1/37.2; rejecting it changes nothing. In a session the owner may say «این سه خروجی را پاک کن»:
  the holder proposes one card per item (or one card for a session); several erase cards may be sealed together (§20.10).
- An agent never erases anything itself.

### 37.4 Cancel that works, and a word after delivery
- `POST /orders/{ref}/close` accepts `verdict: "cancel"` with its own `Idempotency-Key` (a UUID; a client never derives one key from
  another). The Android 0.15.0 «لغو این فرمان» sent a non-UUID key and got `422`: fixed in the app (0.16.0).
- The owner's word in a session whose works are all delivered (`ready`) is not refused any more (`409 no open work on the order`):
  the holder's delivered root work goes back to `in_progress` with the word as its next step and the holder is woken — a revision,
  as in any working session. Only an ended session (closed) asks to be reopened first.
- Data: migration `0055` (erase markers, the `erase` decision kind).

## 38. The hub run from the app ⟨1.20⟩ (2026-11-06, prompt 26)
The owner, 2026-11-06: «نمیشه که یبار توی آپ من بگم یبارم بیام به تو بگم یبار تو به سرور بگی … به داکر یا خیلی از چیزا api دسترسی
نداشته باشه … امشب این آپ باید اون چیزی که من میخوام بشه». What the owner says in the app is done by the holding's own people: a company
server through its runner (§26, as today), **the hub itself through a fixed catalogue of hub operations**, and nobody answers «دسترسی ندارم».

### 38.1 Hub operations (`hub.ops`)
- Agent tool `hub.ops {op, args?}` · `{job}`: one operation from a fixed catalogue, queued on the hub and run on the hub host by the
  **hub-ops dispatcher** (`infra/hubops/dispatch.sh`, systemd timer every 10 s as user Hub, like the substitutes dispatcher: a token of
  its own, the api reached on the internal network; no listening port; no shell from the hub — only the catalogue's fixed commands with
  validated arguments). The first answer is `queued` with a `job`; call again with `{job}` until `done` (output, masked, ≤ 64 KB) or
  `failed`. Every op is audited.
- **Catalogue** (class; what it runs):
  - A0 read: `status` (`hq.sh ps`, health of each service), `logs {service, lines ≤ 500, since?}` (masked), `stats` (memory and CPU per
    container, the memory budget), `verify` (`make verify-live`), `inventory` (the §25.2 connection table: players, sign-ins, voice key
    present yes/no, n8n, growth connections, runners, backups — names and states only), `n8n.list` (workflows, active or not),
    `n8n.executions {workflow?, limit ≤ 50}` (state and time only).
  - A2 operate: `restart {service}` (an application service of the stack; never `openbao`, `postgres`, `caddy`), `profile {name: media
    | tts | ocr | newsletter | automations | mcp | tracing, on: bool}` (the memory budget still refuses what does not fit; the answer says
    what to turn off), `n8n.import` (the repository's workflows), `n8n.activate {workflow, on: bool}`, `backup` (`make backup-hourly`),
    `catalogue.refresh`.
  - A3 with the owner's seal (a decision card `hub_op`, 🔏, bound to the op and its args): `n8n.create {name, workflow_json}` (a new n8n
    workflow, imported inactive; activating it is `n8n.activate`), `profile` when it needs another profile off to fit, `deploy {ref}`
    (pull and rebuild the named services of an approved branch — only when the owner seals it).
  - Never in the catalogue: SSH, users, sudoers, firewall (ufw, iptables, DOCKER-USER), fail2ban, OpenBao (unseal, root token, policies),
    any file under `~/.secrets` or `infra/compose/.env`, the `*-login`, `*-secret`, `gdrive-auth`, `owner-*` owner targets, reboot,
    volume or database deletion. Asking for one answers `policy_denied` with the owner's step in plain Persian.
- **Who:** the holding's technical people (the AI operations head, the platform SRE, the holding CTO when hired; `kind` from the
  charters); every other role asks them (`work.request` to the holding's AIOPS, or its own company's CTO for its company's servers).
- **Owner steps from the app:** an op that needs the owner (a sign-in, a key) answers with the exact step; the owner's sign-ins in the
  hub browser stay his (noVNC through his tunnel) until a later prompt brings them into the app.

### 38.2 Nobody says «دسترسی ندارم»
- The capability brief (every run, every talk persona) gains `technical`: for this role, which servers it may work on (`server.*` through
  the runner) and whether it holds `hub.ops`; for a role that holds neither, the one way: `work.request` to its company's CTO (or the
  holding's AIOPS for the hub) with what to do. `_common.md`: «never say a capability is missing: do it, or hand it to who can, and tell
  the owner who has it».
- Data: migration `0056` (`ops.hub_jobs`, the `hub_op` decision kind).

### 38.3 The owner's «سرویس‌ها» page
The hub server's proposal (2026-11-06), adopted: a page in the app with an on/off switch for each optional service and the free memory;
the owner's word is recorded (audit) and the same hub-ops dispatcher (38.1) runs it, the memory budget checked; the answer comes back.
- `GET /hub/services` (owner) → `HubServices {memory: {total_mb, budget_mb, caps_mb, free_mb}, services: [HubService], at}`; `HubService
  {key, title_fa, what_fa (one plain line: what it is for), state: "on"|"off"|"starting"|"failed", optional: bool, mem_cap_mb,
  mem_used_mb|null, can_toggle: bool, note_fa|null}`. Optional (toggleable): `media` (ساخت ویدیو و کاور), `tts` (صدای ساده‌ی هاب),
  `stt` (تبدیل گفتار به متن), `ocr` (خواندن اسکن بایگانی), `newsletter` (خبرنامه), `automations` (n8n), `mcp`, `tracing`; core services
  are listed with `optional: false, can_toggle: false`. The figures are the dispatcher's latest snapshot (≤ 60 s old; `at`); while the
  dispatcher has never reported, `memory` is null and the page says the hub part is not installed yet.
- `POST /hub/services/{key}` {on: bool, turn_off?: [key]} (owner; `Idempotency-Key`; no passkey: optional services only) → `202
  HubJob {ref, state, result_fa|null, blocking: [{key, title_fa, mem_cap_mb}]}`; `turn_off` switches those off first, in the same job.
  `GET /hub/jobs/{ref}` → `HubJob` (the app polls, or the stream's `hub.job` event); done: `result_fa` «روشن شد» / «خاموش شد»;
  refused by the memory budget: `state: "refused"`, `result_fa` «جا نیست؛ این‌ها جا را گرفته‌اند» and `blocking` = the optional
  services that are on, largest first, so the app offers one tap: «<x> را خاموش کن و <y> را روشن کن» (`turn_off`).
- Every switch is audited (A2) and is an interaction; the agents' `hub.ops profile` is the same job.

## 39. The session gets the work done in one place ⟨1.21⟩ (2026-11-07, W9)
The owner, 2026-11-07, in the session of his Pro-Chart content order: the media director's `automation` card («یافتن موضوع روزانه
ساعت ۰۸:۰۰») answered «نقش کارمند درست نیست.» three times (the compiler's `role` was a free string the model wrote as a word, and
code refused anything outside `^[a-z][a-z_]{1,30}$`); «go find why» became two NEW orders to the advisor, each with its receipt, plan
and «سامانه: خروجی رسید» lines. «همش اینور و اونور … این بروکراسی اداری چیه … مگه نگفتم توی سشن‌ها به همه چیز دسترسی باشه».

### 39.1 A role never refuses an automation (§31.7)
- `POST /automations/compile` and the `automation` card carry the company's real roles to the model (`roles` in the prompt: the
  charters its active employees hold and its departments' teams, key → title) and normalise what comes back by code: an employee code
  is that employee's role, `role@CODE` is the role, a Persian or English title (`سناریست`, `Scriptwriter`, `script-writer`) is its
  charter; a role nobody in the company holds goes to the charter's department manager, else the proposer's department manager, else the
  CEO, and `preview_fa` says so («کسی با نقش «نویسنده» در این شرکت نیست؛ این کار به مدیر رسانه و طراحی داده میشود.»). Never a 422 for
  a role. The preview and the stored automation name a role by its charter's title.
- Every other refusal names the field and what is allowed, in one line (««اولویت» (priority) باید یکی از P0 تا P4 باشد.»); the talk
  card's `reason_fa` is that line, and so is the session's step «خودکارسازی انجام نشد: …».

### 39.2 Nothing leaves the session (§35.4)
In a talk bound to an order no card makes a new `F-` ref:
- `ask {text, to?: code | department | charter role | "advisor", company?}`: the asked person joins THIS session (the participant path,
  «… آمد.») and the question is a work of this order assigned to them: a child of the root in the holder's company, a work requested
  by the root in another company or the holding (the order's tree follows both); a plan task names it; nobody named: the holding's
  advisor. Its deliverable comes back as that person's own turn here («جواب آمد») and the card is answered.
- `minutes`: each task a work of this order (a department named: its manager; another company: its CEO, requested by the root), the
  rest plan tasks of the session («صورت‌جلسه: 3 کار به همین فرمان اضافه شد.»).
- `order` stays the reply on the same order; `hire`, `group`, `line`, `automation`, `delegate`, `budget`, `planner`, `rule`, `decision`
  keep their effect and leave one short line in the session (a step and the holder's turn, by code).
- ⟨2026-11-07⟩ Whoever is hired from inside a session joins THAT session («<title> استخدام شد و به همین جلسه آمد.», a step and
  a turn): a seat filled at once at the card's run, a manager's hire card when its decision is applied (found by the card's `made`).
  Never a new order for the new employee.
- A talk not bound to an order keeps §32's behaviour (an order per ask or task, through the dispatcher).

### 39.3 The holder fixes its own failures
- «## The order you hold» (the talk) and the holder's run brief (`order`) carry `failed_cards`: the session's last three failed cards
  (kind, title, the exact `reason_fa`, the payload fields). The persona section of a session and `_common.md` (v8; `manager.md` v9,
  `ceo.md` v13): read the reason, fix the card and offer it again; someone else needed joins this session (`ask`) or works under this
  order (`work.delegate`, `work.request`); never the owner's question to another order; never «this is someone else's job».

### 39.4 Less noise for the owner (§29.7, §35.2)
- The order's story writes no «به … سپرده شد» per hand-over and no «سامانه: خروجی رسید» per output (the outputs are listed as
  themselves; the cards' lines and the holder's plan say who got what); a new work or output still moves `last_step_at`. The order's
  own receipt stays its first line.
- `brief.done_fa`, `now_fa`, `need_fa`: each one plain line of at most 90 characters (cut at a word, «…»).

### 39.5 What a run carries
- The capability brief (§38.2) is `lean` for a run that is not work for a person — an `alert` (an event work a service made: an ops
  alert, a watcher's protocol run, the weekly review, a digest, a technical summary), a `schedule` (a recurring occurrence, the CEO's
  daily report) and any run of a system role: `technical` and whom to hand things to (~750 characters), never the players, the
  company profile or the holding map. A consult-only persona's talk turn (the overseer, the advisor) carries the brief without the
  holding map. A person's work run, a message run and a working persona's talk turn keep the full brief (≤ `CAPS_CHARS` 12 000).
- Measured per run (characters of context): a work run 24 000 + 12 000 (unchanged); a watcher's run 24 000 + ~750 (was + 12 000);
  a meeting turn 24 000 (unchanged, no brief); the overseer's talk head ~9 700 (was ~16 000), the secretary's unchanged.

## 40. A session becomes a working group the owner can give to any company ⟨1.22⟩ (2026-11-07, W10)
The owner, 2026-11-07: «همون لحظه که داریم برای موضوع یه نفر رو استخدام میکنیم اون توی اون جلسه حضور داشته باشه تا بهش محول بشه و آخر
جلسه که صورت جلسه شد … ۲-۳ هزار خط چت کردیم و به یه نتیجه رسیدیم. میخوام اون نتیجه به یه اسکیل تبدیل بشه، به یه فرمان قابل اجرا … که
بتونم اونو به شرکت‌های دیگه هم بدم … همون مدل رو برای یوتیوب … برای تلگرام … باید همه اتفاقها توی همون جلسه بیفته … جلسه‌ها به
همدیگه ارتباطی ندارن، کار گم میشه». §39 keeps everything inside the session (a hire joins it at once); this section makes a long
session remember, and turns its result into a reusable working group.

### 40.1 The session remembers
- Every session keeps a **memory** (≤ 6 000 chars, Persian, plain): what was decided, who does what (the people in the session and
  their tasks), the tools and helpers chosen (e.g. «موضوع روزانه را نویسنده با ChatGPT پیدا میکند»), open points. Code appends each
  card done and each person joining; a small model pass (the cheapest model that does it well) folds the last turns in every 20
  turns and at close. The holder's and every participant's context carries the memory plus the last turns, so a session of thousands
  of lines never loses its thread. `OrderReport.memory_md` (read-only for the clients; the details sheet shows it as «تا اینجا»).
- The holder's context also names the company's last three sessions (title, one outcome line, their playbook if any): sessions are
  not islands.

### 40.2 From the session: a playbook (a working group as data)
- `POST /orders/{ref}/playbook` (owner; `Idempotency-Key`; open or closed session) → `Playbook` in `draft`, drafted by the holder
  from the memory, the plan, the session's hires, automations, lines and cards done:
  ```
  Playbook { ref: "PB-0001", title_fa, purpose_fa, state: "draft"|"sealed"|"retired", version,
             platform: "instagram"|"youtube"|"telegram"|"site"|"any",
             seats: [{seat, role, title_fa, duties_fa, helpers: ["gpt"|"gemini"|"deepseek"|"aistudio"], model?}],
             routines: [{key, title_fa, seat, schedule (RRULE, the owner's time zone), brief_md}],
             kpis: [{key, title_fa, source}], connections: [kind], rules_fa: [str],
             source: {order, company, conversation}, members: [{company, name_fa, state, order?}], parent?: PB-ref,
             created_at, sealed_at? }
  ```
  It appears in the session as a card «کارگروه از این جلسه» (open, edit, seal). The owner changes it in words in the session (the
  holder rewrites the draft) or directly: `PATCH /playbooks/{ref}` (draft only; any field above but `ref`, `state`, `source`).
- `POST /playbooks/{ref}/seal` 🔏 (`playbook.seal`, target = ref) → a working group (§29.11, stored in the database, eligibility
  `chosen`: only companies the owner gives it to) and the session's company its first member: seats resolved to the employees the
  session hired, empty seats filled by §29.10 inside the envelope; its routines start at their next time. A playbook's routines are
  ordinary group routines (one small work per occurrence for the seat's employee).

### 40.3 Give it to another company or another platform
- `GET /playbooks?state=` (the library) · `GET /playbooks/{ref}`.
- `POST /playbooks/{ref}/apply {company, platform?, note_fa?}` (owner; `Idempotency-Key`) → a **new session** for that company,
  held by its CEO (or the manager of the matching department), whose first turn carries the playbook and the owner's note
  («این کارگروه را برای <نام شرکت> روی <پلتفرم> پیاده کن»). The holder adapts it there (its accounts, tone, platform specifics);
  sealing the adapted draft from that session makes a version (`parent` = the source) and that company its member. Applying with
  no change: the company joins the sealed group directly (`apply {…, as_is: true}`), no session. `SessionCard.source` names the
  playbook a session came from.
- `POST /playbooks/{ref}/retire` 🔏: its routines stop for every member; nothing is deleted.
- Nothing runs before the owner's seal. Every write is audited.
- Data: migration `0057` (owner.playbooks, the sessions' memory, group eligibility `chosen`, the source of a session).
- ⟨1.22, as built (W10)⟩ additive: `Playbook.retired_at`, `.group` (the growth.groups key `pb_<n>`), `.note_fa` (what the
  drafter dropped and why: a role nobody has a charter for, an RRULE the calendar cannot hold, a routine on no seat, a KPI
  without a source, an unknown connection; or «مدل پیش‌نویس نداد …» when the holder's model gave nothing and code built the
  skeleton from the session's hires and scheduled automations); `PlaybookRoutine.max_tokens` (default 40 000), `PlaybookKpi.unit`;
  `PlaybookMember.order` is the session the playbook came from for its own company. A seat's role may be an employee's, a
  manager's or the CEO's charter (never a system role). `POST /orders/{ref}/playbook` answers 201. `PATCH` takes any of
  `title_fa, purpose_fa, platform, seats, routines, kpis, connections, rules_fa` (one at least; `version` counts up). `apply`
  answers `PlaybookApplied {playbook, member?, order?, conversation?}`: `as_is` the membership, else the new session (its
  `OrderReport.session.source` and `SessionCard.source` = the playbook; the owner's first turn in its talk is the playbook as
  Markdown; `apply` on a retired playbook: 409). The holder rewrites the draft in words with a `playbook` card
  `{playbook, draft}` (talk.cards kind `playbook`; the card the draft posts carries `{playbook}` only and running it just
  points at it); the holder's context names the session's playbooks (`playbooks`), its memory (`memory_md`), the playbook it
  was opened from (`source_playbook`) and the company's last three sessions (`related_sessions`). `Group.eligible` adds
  `chosen` and `Group.playbook`; a seat once resolved keeps its employee while they hold the role. Step-up actions
  `playbook.seal` and `playbook.retire` are routine (no fingerprint, `stepup.LIGHT`). The memory is folded by task class
  `session_memory` (Haiku-class, every 20 turns in the talk worker and once more after `close`, in the background); the draft
  by `playbook_draft` (Sonnet-class), through the same awaited worker call as the order's routing. Stream: `group.playbook
  {state, version?, group?}` (topic `groups`), the card as `talk.card`.

## 41. The session shows its work live and never stalls ⟨1.23⟩ (2026-11-08, W11)
The owner, 2026-11-08, on his Pro-Chart reels session (F-0011): he gave a numbered 9-step working group; the media director
answered with notes and a «test reel» order, the CEO approved two hires, then nothing moved and the session still read «در جریان».
«جاهایی که کار انجام دادن و ول کردند رفتند نه استریم زنده ای … مراحل کاری که از ۱ شروع شده و هر جای ۱ گیر کردند از من سوالی بپرسند …
گزینه‌های با من و خودکار برداشته شده … مثل خودت که کلود کدی از کار کردنت آدم میفهمه کار میکنی». Not a redesign: the execution loop
of a session, made visible and continuous.

### 41.1 Live activity
- `GET /orders/{ref}/activity` (owner) → `SessionActivity {working: [Worker], last: [ActivityLine] (≤ 30, newest last), idle_since?,
  waiting_fa?, stuck_fa?}`; `Worker {who_fa, company_fa, work_title_fa, started_at, step: n, doing_fa}`; `ActivityLine {at, who_fa,
  text_fa}` — each a run's step in plain Persian (§29.7: the step's own summary humanized, or the tools it used in words: «سایت
  pro-chart.com را خواند»، «از ChatGPT پرسید»، «صدا ساخت»، «خروجی تحویل داد»; never a tool key, ref or code).
- Stream event `session.activity` {order, line: ActivityLine, working: n} on every run start, step and end of a work of the order
  (its tree), so the clients show it as it happens.

### 41.2 The owner's steps are the plan
- When the owner's word in a session holds a numbered list (Persian or Latin digits, «۱ -», «1.», «۱)» …), each item becomes a plan
  task of the session in that order (code, no model), unless the holder's `order.ack` already wrote those steps; the holder's brief
  says: work the plan task by task, tick each with `order.progress done`, and ask the owner (`order.ask`) the moment one cannot go on.
- ⟨2026-11-10⟩ **His steps ARE the plan, in his order** (the owner's recording of 2026-11-09: his nine steps had been appended
  after the holder's five, so the holder's «ساخت اولین ریلز» (4) ran before his «متن گفتار» and «صدا», which had become 7 and 8).
  When his word holds a numbered list, the holder's own tasks that are still open are dropped (`state: dropped`), his items are
  added in his order, and the plan is numbered again from 1 (done tasks first, then the open ones, then the dropped): a task's
  `n` is its place in the plan. One step says it: «برنامه: N کار از حرف مدیر کل؛ برنامه همین گام‌های شماست و به ترتیب خودتان،
  برنامه‌ی قبلی مسئول کنار رفت». The holder may add steps of its own afterwards (`order.ack steps`): they go after his.
- The holder's pace («با من» / «خودکار») is shown and switched in the session's header again (§34 `POST /orders/{ref}/pace`).

### 41.3 Never a silent stall
- The holder is woken (once per cause) when someone joins the session by a hire (§39.2), when a hire card of the session is decided,
  when a child work of the order is delivered or fails, and when the owner answers an `order.ask`.
- The sweep (every few minutes): a session not ended, not waiting on the owner, with no queued or running run of its works for
  `SESSION_IDLE_MINUTES` (10) → the holder is woken once with «continue the plan from task N»; still idle `SESSION_IDLE_MINUTES`
  later → the badge is `stuck`, a step and one owner notification say why in plain words (the last refusal, a blocker, an empty
  seat, a sign-in or key the work needs) and what fixes it. `moving` means a run is queued or running now.
- `POST /orders/{ref}/nudge` (owner; Idempotency-Key) → «ادامه بده»: the holder is woken now with the plan's next task.
- ⟨1.23, as built (W11, 2026-11-08)⟩ additive:
  - `SessionActivity.last` holds, beside each step, a run's start («شروع کرد: …») and how it ended («این دور کارش را تمام کرد»،
    «کار متوقف شد: …»); a run of no consequence (`work_closed`) leaves no line. `Worker.started_at` is the queue time of a run not
    yet started (`doing_fa` «در صف اجرا»). A step's `actions` carry a readable `hint` (a site's name, a player's name, a company
    or an employee code resolved to a title) so the owner reads «سایت pro-chart را خواند», never a key. Stream topic `orders`
    carries `session.*` (the apps missed `session.updated` before); the holding-wide stream (`company=*`) passes
    `session.activity` and `session.updated` in full.
  - The badge: `moving` only while a run of the order's works is queued or running («در حال کار: …»); idle for less than two
    thresholds it stays `moving` and says since when («از N دقیقه پیش کسی کار نمیکند؛ مسئول بیدار میشود»); idle for two thresholds
    (`SESSION_IDLE_MINUTES`, default 10) it is `stuck` with the cause in `reason_fa` and `stuck_fa` (the last refused or failed
    run, a blocker, a tool's missing sign-in or key, an empty seat, else «نمیدانیم چرا؛ «ادامه بده» را بزنید»). Nothing is stored
    for it: the wake is the run it queued (reason `session_idle:<ref>`), the stuck line its step and one notification.
  - The holder's brief (`order` in a run, «The order you hold» in the talk) carries `plan: [{n, title, state}]`, `plan_next`,
    `plan_instruction` and `owner_said` (the owner's last three turns in the session, verbatim). In a working session every owner
    turn that is not a question is the order's word by code (`reply`: the step «مدیر کل: …», the holder woken) — no card to tap;
    a question or a consult-mode turn feeds the plan only. The wakes (a hire that joined, a hire card decided, a child delivered or
    failed, the owner's reply, the idle sweep, «ادامه بده», a lifted cap) never count toward the talk-without-output stop, which
    counts only runs that produced nothing, starts again at every step and is at least 3 per plan task; a wake that returns
    nothing writes a step saying why («مسئول بیدار نشد: …»).
  - `POST /orders/{ref}/nudge` answers `SessionActivity` (200), 409 on a closed session; the step «مدیر کل گفت ادامه بده» and the
    owner's line in the talk.
  - Budgets (the owner, 2026-11-08: «کلا بودجه رو سقفشو بردار»): a work of an owner's order, its collaborators' works and the children
    delegated or requested under it carry no `budget_tokens` (the preview's `budget_tokens` is the secretary's estimate, never a cap);
    no `budget` blocker for a token stop; `POST /orders/{ref}/fix {action: budget.add}` without `tokens` lifts the work's cap for good
    (200, the step «سقف مصرف این کار برداشته شد؛ کار ادامه دارد», the work woken); the «تصمیم درباره‌ی D-…» items carry no budget.
    The `budget` blocker stays for a hire the month envelope refuses (`envelope_required`, `envelope_exceeded`), now with the fix
    `envelope.set` (target the company code); `FixIn.action` adds `envelope.set` and `media.on` (the app's own pages). A tool's
    missing account names the tool in words with a real fix or none (`speech.make`, `media.render` → `media.on`,
    `substitute.call`); an Instagram one reads «حساب روی IG-Hub است؛ تیم فنی آن را به هاب معرفی میکند» (never «not connected»).
  - Reach across companies, one rule (the owner: «همه شرکت‌ها به هم راه داشته باشند»): while `links_enforced` is off any active
    company counts as linked; while on, an `on` link or a company present in the session of the order the work serves. It governs
    `work.request` (a manager to another company's CEO; any role to the holding's AIOPS or LEGAL manager), `server.*` for a
    technical role (the TECH department's charters: `via: linked`, `server.map` lists those servers, the job audited on both
    companies, destructive commands still sealed) and `connection.set`.
  - Agent tool `connection.set {company?, kind, accounts?, via?: "ig_hub", server?, read_command?, channels?, site_url?,
    channel_id?, handle?, property_id?}` (A2; the company's CEO, media director and technical roles; a technical role for another
    company within reach) → `/internal/v1/connections/set` → `Connection`: a connection's non-secret settings, the state recomputed,
    audited on both companies, a step in the order's session; a secret-looking value or a command that is not read-only is refused
    (422 with the field). The capability brief says of an Instagram connection not connected here that the account lives on IG-Hub
    (the `ig_hub` setting of `seed/channels.yaml`: company and server) and who registers it.
  - ⟨1.24⟩ §42.2, the line's additive shape (`ActivityLine`, on `GET /orders/{ref}/activity` and in `session.activity` alike):
    `id` (`<run>:<n>`, 0 the start, `<run>:end` the end; `task:<ref>:<n>` a ticked plan task; `join:<code>` a hire that joined),
    `company` (the actor's code), `kind: start|step|end|wake|ask|join|task`, `state: running|done|failed`, `task_n`. The
    stream also carries the wakes (`wake`, id `<run>:0` of the run queued), the asks («سؤال از شما: …»), the joins and the ticked
    tasks («کار N انجام شد: …»); `GET /activity` merges by `id` (the later line wins) and keeps the last 30.
  - The delegate card of the talk takes `company` (the asked person's company; a full employee code resolves both); a named company
    or server in the owner's words («از تریدیار», «سرور CoineProFx») picks that company; a server of the session's memory alone
    counts for servers, never for a person of another company (M3).
  - **The owner's three decisions (2026-11-08)**, as built:
    1. *Voice is off.* `OwnerSettings.voice` gains `enabled` (additive, default `false`; `PUT /owner/settings {voice: {enabled}}`): the
       talk answers in text alone (no `say`, no `audio` event), no «صدا در دسترس نیست» line ever, no `voice` block and no `voice` entry
       in the capability brief, no sign-in as a blocker, readiness item or owner's step. The voice code stays and runs only while
       `enabled` is on.
    2. *Instagram = IG-Hub, for every company.* The `connection_missing` blocker for Instagram is gone: a run that meets it makes the
       holding's technical work by code, once per company (IG-Hub's company's CTO, else the holding's AIOPS manager; `run_meta.ig_setup`
       = the company code; under the order's work so the session sees it and its delivery wakes the holder), and the session reads one
       step «تیم فنی حساب‌های اینستاگرام را از راه IG-Hub به هاب معرفی میکند». The daily read (`read_due`, result `ig_setup`) makes the
       same work for a company whose read path is not registered. Readiness: `channels` is always ok (Instagram through IG-Hub, the
       accounts the technical team's), `connection:instagram` is always ok with «از راه IG-Hub خوانده و منتشر میشود (N حساب)» or the
       technical team's line, never a `connection.guide` fix for it; a `group` check that fails for want of membership carries no fix
       (a failed check may carry no fix when the step is the technical team's). The brief's `how.instagram` and the charters say
       plainly: Instagram, for all companies, is read and published through IG-Hub.
    3. *No video tool.* Readiness has no `media_tools` check; a refusal of `speech.make`, `media.render`, `media.item` or `media.on` is
       never a blocker (`FixIn` still accepts `media.on`). The brief's `how.cover_image` (image only) and `how.video` and the holder's
       plan instruction say: the video step of a plan is done when the media team delivers the «بسته‌ی ساخت ویدیو» (script, shot list,
       on-screen text, voice text, caption, hashtags, cover prompt); the owner makes the video and drops the file into the session (§36);
       publishing goes on through IG-Hub. Charters: `_common` v10, `media_director` v8, `scriptwriter` v5, `video_director` v3,
       `motion_designer` v4 (the «A voice from Google AI Studio» sections gone, `speech.make` only the voice producer's).

## 42. The holding live: one stream the whole app moves with ⟨1.24⟩ (2026-11-08, W12)
The owner, 2026-11-08: «بهترین و حرفه ای ترین و تخصصی ترین انیمیشنا و استریم هارو … نقشه نشون بده کدوم شرکت به کدوم وصل شد قطع شد
… همه جای آپ باشه». He approved the 12 P0 views of `design/LIVE_VIEWS.md` (D4-Live). This section is their data; the views, the
motion grammar (M1–M13) and the map are in that document (§2, §4, §5). Every event follows §7: metadata and plain Persian labels
only, never a message body, prompt, tool payload, secret, hostname or address; emitted inside the writer's transaction through the
outbox (`events.emit`). Company codes are data; nothing assumes a number of companies (owner rule 9).

### 42.1 Topics
- `events.TOPICS`: `orders` = `("order.", "session.")` (`session.updated` of §35.7 and `session.activity` of §41.1 reach the apps);
  `holding` = `("links.", "holding.")`; `servers` = `("server.", "network.")`. `employee.state` and `llm.tick` route under their
  existing prefixes (`activity`, `llm`).
- The holding view (`company=*`) passes in full, besides `activity.changed`: `server.state`, `network.link`, `holding.flow`,
  `employee.state`, `llm.tick`, `session.updated`, `session.activity`, `control.changed`, `links.updated`. Everything else stays
  reduced to `{id, type, at, company}`.

### 42.2 New events
| Event | Topic | `data` | Emitted when |
|---|---|---|---|
| `session.activity` (additive to §41.1) | `orders` | `{order, working: n, line: {id, at, who_fa, company, text_fa, kind: start\|step\|end\|wake\|ask\|join\|task\|memory, state: running\|done\|failed, task_n\|null}}`; `line.id` = run id + step n, so a step's end updates its line | each run start, step and end of a work of the order's tree; the holder woken (`wake`); someone joins (`join`); a plan task ticked (`task`) |
| `holding.flow` | `holding` | `{from, to, kind: order\|request\|accept\|deliver\|read\|playbook\|publish, via: "hub", ref, root_ref\|null, label_fa\|null (≤ 60)}`; `from`/`to` = `"hub"`, a company code, or `"outside"` | an owner order is routed (hub → the holder's company); a cross-company work is created / accepted / delivered back (A → hub → B); an agent reads another company's data for a work; a playbook is given to another company; a line publishes |
| `network.link` | `servers` | `{from: server, to: "hub"\|server, port\|null, ok, ms\|null, error_fa\|null, since, last_ok_at\|null}` | a measured link (`netcheck`, §26.6) changes `ok` or crosses the slow threshold; at most once per link per minute; every result during an owner's check |
| `employee.state` | `activity` | `{employee, company, department, state: idle\|thinking\|working\|waiting\|stuck\|done, since, work_ref\|null, root_ref\|null, stuck_fa\|null}` | the §29.14 state changes; at most one per employee per 2 s (`stuck` and `done` at once) |
| `llm.tick` | `llm` | `{company, window_s: 5, calls, in_flight, tokens: {input, output, cache_read, cache_write, thinking}, equiv_usd, day: {tokens, effective_tokens, equiv_usd, budget_usd\|null, pct\|null}}` | every 5 s for each company that had a call in the window (nothing when idle), built in the worker bridge that already reads the router's call events |

`server.state` (additive): `{prev_state, since, reason: no_poll\|runner_stopped\|server_unreachable\|revoked\|fallback_public\|slow\|null,
reason_fa, hub_rtt_ms\|null, open_jobs}`; also emitted when `via` changes and when the round-trip tier changes. `reason` is inferred
by the hub: the runner is silent but another server still reaches that server's ports → `runner_stopped`; nobody reaches it →
`server_unreachable`; otherwise `no_poll`. A client never infers offline from silence.

### 42.3 `GET /live/summary` (owner)
→ `LiveSummary {seq, at, people: {working, thinking, waiting, stuck, total}, sessions: {moving, your_turn, stuck, ready},
approvals, urgent_unread, servers: {online, offline, total}, tokens: {today, effective_today, per_min, equiv_usd_today,
budget_usd|null}, control: {holding: bool, companies_locked: [code]}, companies: [{code, name_fa, working, total, sessions_open,
servers_online, servers_total, spend_today_usd, last_event_at|null, state: ok|busy|stuck|locked}]}`. `seq` is the stream's last
sequence when read, so the client seeds from the summary and resumes the stream exactly after it (`Last-Event-ID`). Missing data is
`null` (shown «—»), never zero.

### 42.4 Clients (the 12 P0 views)
Live heartbeat on every screen (live / reconnecting / stale; a frozen view must never look calm) · the network map (hub, companies
and servers from data; spokes, runner links, company links) with particles per event and a table view · disconnects red with the
time, the reason and the fix · the session's live work (§41) · the session badge and stall watch · the office pulse · the token meter
(70/90/100 marks, four token kinds) · the live company card · each employee's state by shape and word · the urgent banner and the
decision toast · the kill-switch band. Reduced motion turns every motion into an instant change; a hidden app draws nothing and,
on return, applies the state at once («n رویداد در نبودت» past 20).

### 42.5 As built (W12, hub)
Where the build is more precise than §42.1–§42.3, this list is the contract. Migration 0058.
- **Money** stays a decimal string of 6 places (§1): `llm.tick` `equiv_usd`, `day.equiv_usd`, `day.budget_usd`; `LiveSummary`
  `tokens.equiv_usd_today`, `tokens.budget_usd`, `companies[].spend_today_usd`. `pct` is a number (1 decimal).
- **`holding.flow`:** the envelope's `company` is the holding's code (the map is the holding's); the ends are in `data`, the holding
  itself is `"hub"`. Labels are built from company names only, never a title or a brief.
  - `order`: one flow, hub → the holder's company (the first route's); `ref` the F-ref, `root_ref` its root work.
  - `request` (A → B), `accept` and `deliver` (B → A): `ref` B's work, `root_ref` the root of A's asking work; `accept` on the first
    acceptance only, `deliver` only when the work is delivered (not a partial output).
  - `read` (data owner → reader): `linked.read` of another company (any `what`), `knowledge.search` of a named other company, and
    `files.read` of a file the owner gave the order (from `"hub"`); `ref` the reader's work, its employee code when the run has none.
  - `playbook`: from the company whose session made it (`"hub"` when none) to the receiver; `root_ref` the work of the session that
    adapts it, null for `as_is`. `publish`: the line's company → `"outside"`, `ref` the line run.
- **`network.link`:** `ref` `<server>:<to>:<port>`, envelope company the measuring server's; `error_fa` is mapped from the runner's
  error (its own words never go out); slow = 300 ms or more (the same line is the hub round trip's tier). A ping row has no port and
  is not stored, so `port` is never null today.
- **`employee.state`:** derived in the same transaction after `run.started`, `run.finished`, `activity.changed` and an agent's
  `server.call` (no writer calls it); what no event says (a card decided, a lock, the day turning) the worker's reconcile finds every
  30 s. A change inside the 2 s window goes out at its end (the worker's flush, every second) with the latest state. `work_ref` is the
  work of its running run, else its newest open work; null when `idle` or `done`; `root_ref` is the root work's ref (as `work.*`).
- **`llm.tick`:** windows aligned to the clock; `calls` counts the calls that finished in the window (they carry the tokens), so a
  window with only a start ticks with `calls: 0`; `in_flight` and `day` are read from the ledger; the day is the Token Treasury's UTC
  day (as the router's budgets count it); `day.budget_usd` is the company's daily dollar budget, else null.
- **`server.state`:** `reason_fa` is null when `reason` is; `prev_state` is the same state when only `via` or the tier changed; an
  offline server's `since` is its last contact, and its reason counts only links measured since; a netcheck that changes an offline
  server's reason sends `server.state` again.
- **`LiveSummary`:** `seq` is null only while the event bus is down. `companies[]` are the operating companies (active or paused),
  the holding being the hub; `working` = thinking + working; `sessions_open` = open sessions whose first route was that company;
  `last_event_at` = its newest event among the last 20 000, else null. `servers` counts servers with a runner, not revoked.
  `tokens.budget_usd` is the holding's daily dollar budget, else null; `urgent_unread` counts the owner-visible urgent notices of the
  last 7 days not read (as the home's critical list). Eight queries whatever the number of companies.

## 43. The workshop: hands for any task ⟨1.25⟩ (2026-11-09)
The owner, 2026-11-09: «اپ یه شاه‌راهه، یه انتقال‌دهنده‌ست و همه‌ی اتفاق‌ها توی سرور رخ میده … قراره صدها کار مختلف اتفاق
بیفته». The app is only the line to the owner; the hub is a computer and Claude Code on it has hands. Any task no tool of a role
covers (a reel or a motion graphic, a YouTube video, an X post with images, a site page, an SEO crawl, a PDF report, a scraper,
a data file, anything) goes to the holding's **workshop**. Nothing below is about one kind of task: no task gets a path of its own.
Design: `docs/WORKSHOP_HANDS.md`; the review: `docs/ops/reports/WORKSHOP_REVIEW.md`.

### 43.1 The workshop server
- A locked-down Linux user on the hub host (`studio`: no sudo, no docker group, no access to `/home/Hub` or the secrets, outbound
  only to the internet, DNS and the hub's own HTTPS) runs its own `hq-runner` (≥ 0.3.2), paired to the **holding** like any server
  (§26.1): `POST /runners/pair` now takes the holding's code as well as a company's; the owner's seal on `runners/approve`
  (`server.attach`, `company:<HOLDING>`) is the gate. Every server of the holding is the workshop. Resources: a systemd drop-in caps
  it (4 GB, 6 of 8 cores); the runner runs at most two jobs at once.
- Its tools are installed once in the user's home (ffmpeg, Chromium through Playwright, node, python, the IRANYekanX font); anything
  else a task needs, the session installs in the work's folder.

### 43.2 `workshop.run` (agent tool, A2; `POST /internal/v1/workshop/runs`)
- Held by **every working role of every company** (`hq_common.charters.SHARED_TOOLS`; `a2_grants` of every role kind, the advisor
  included); never a system role.
- Body: `{brief (1..20000), title? (≤ 300), work? (W-ref)}`. The turn is for the run's work item, or `work` when the caller is its
  assignee (else `403`); a run without a work item and no `work`: `422 fields.work`; a closed work: `409 work_closed`.
- Policy: `hq.internal` op `server.run` with `via: workshop` and the holding's code (servers.rego): any working agent. Only a `claude`
  job: `server.exec`, `server.write` and `server.read` on the workshop stay closed to the companies' roles (`403`).
- The turn is a **workspace turn** (§33.10) of that work on the workshop server: the folder `~/hq-workspace/<W-ref>` and the same
  Claude session on every later call for the work (the owner's fix is the next call: `--resume`); a session that failed gives way to
  a fresh one in the same folder. Job args: `{brief, title, cwd, workspace, hands: true, model: "claude-opus-5-5",
  permission_mode: "acceptEdits", allowed_tools: [Bash, Read, Write, Edit, MultiEdit, NotebookEdit, Glob, Grep, WebFetch,
  WebSearch, TodoWrite, Task, Agent], timeout_s: 3420}`, **no `token_cap`**; the job's timeout is 3600 s: the session has 57
  minutes, the last 3 are for sending `out/`, and the hub fails a job 120 s past its timeout if no result came. The PreToolUse hook (§26.3) still classifies every Bash command: a destructive one waits for the owner's seal.
  The Claude account is the hub's own of the moment (§26.2, prompt 29.1).
- The brief the workshop reads: the ground rules (a whole computer, install what you need in the folder, **every file to deliver in
  `out/`**, the deliverable types and sizes, 60 minutes, never publish, pay, message anyone or print a secret, a short Persian
  answer naming each file), then the agent's ask as written.
- Answers: `201 WorkshopRun {job, work_ref, state: "starting", turn, path, server}`; `200` with `state: "working"` while a turn of
  the work still runs (nothing new starts). `409 workshop_unavailable` (no holding server on runner ≥ 0.3.2), `409 workshop_stopped`
  (the owner stopped the work's workspace: `POST /work/{id}/stop`), `409 workspace_elsewhere` (the work runs on its company's own
  server, `mode: on_server`). Requires `Idempotency-Key`. Audit `workshop.run` (A2) on the work's company and the holding.
- The gateway answers the model at once with a hint to finish its run; the output comes back by itself.

### 43.3 Files back: `POST /runners/jobs/{id}/files` (runner, bearer)
- Any workspace turn (a `claude` job with `args.workspace`, on the holding's workshop or a company's own server) may send the files
  it left in `out/` of the work's folder, while the job runs (before its result): a raw body as an owner upload (§17.1;
  `Content-Type`, `X-File-Name` percent-encoded), the type checked by its bytes and the size while it streams: video (mp4, webm,
  mov ≤ 200 MB and 10 minutes), image (jpeg, png, webp, heic ≤ 20 MB), PDF (30 MB), text, Markdown and ZIP (50 MB), audio (25 MB);
  a font is not a deliverable (`415`). `201 FileRef`.
- The file belongs to **the work's company**, made by the job's agent (`created_by_kind: agent`), `meta: {job, workspace}`; a video
  or audio is processed as an owner upload (poster, key frames, transcript); a PDF or text gets its text for `files.read`. The same
  bytes twice for one job answer the same file; at most 20 files a job (`429`). `409` once the job ended; `422` for a job that is
  not a workspace turn of this server; `404` for a job of another server. Audit `file.upload` (A1) on the work's company.
- Caddy: its own matcher before `/api/v1/runners/*` with the media limits (201 MB, 600 s); every other runner route keeps 32 MB.
- The runner (0.3.2) sends only a turn that ended well, only regular files under `out/` (no link, nothing hidden), and a file only
  when its bytes changed since it was last sent for that work (`workspaces.json` keeps `sent`); its result's `data` carries
  `files: [file ids]` and `files_skipped: [{name, why}]` (the hub keeps both in the job's result).

### 43.4 The output in the session
- When a workspace turn ends well (`workspace.after_job`), its answer and its files (the result's `files`, checked: originals of
  this job in the work's company; anything else dropped) become a deliverable of the work with the files as `attachments`
  (`produced_with.runtime: "workshop"` on the workshop, `"company_server"` on a company's server). The app shows them with
  «باز کن» and «دانلود» (§36). A turn with files and no answer still delivers (its body says the files are attached).
- A workshop turn of a **child** work delivers it (the work `delivered`; its parent's holder is woken as for any child). A workshop
  turn of a **root** work (the order itself) leaves it open: the deliverable is made (`work_events` kind `output`) and its holder is
  woken at once (`work.wake_assignee`, reason `workshop_done:<W-ref>`) to show the owner what is ready and ask «تأیید یا اصلاح؟»
  (`order.ask`). After the owner approves, publishing goes the usual way (Instagram through IG-Hub; A3 stays a decision). ⟨2026-11-10⟩ The
  usual way is now his own tap on the file: «تأیید و انتشار» (§44.5).
- A workshop turn that fails (its 60 minutes, an error) marks the workspace `failed` with the reason (`note_fa`, and the work event
  `workspace_failed` carries it) and wakes the holder at once (reason `workspace_failed:<W-ref>`): the session never stalls
  silently. The activity line of such a run says why it started (§41: «کارگاه کارش را تحویل داد؛ نگاهش میکند», «کار کارگاه به نتیجه
  نرسید؛ دلیلش را میگوید»); a step that calls the tool reads «کار را به کارگاه داد تا بسازد».
- `WorkspaceProgress.where_fa` of a workshop turn is «کارگاه هلدینگ».

### 43.5 Error codes (additive)
`workshop_unavailable` 409 · `workshop_stopped` 409 · `workspace_elsewhere` 409 · `work_closed` 409 · ⟨2026-11-10⟩
`not_next_step` 409.

### 43.6 ⟨2026-11-10⟩ The workshop after its first week (the audit and the owner's recording)
- **`workshop.run {…, task?}`.** In a `step` order («با من») that has a plan, `task` is required and must be the number of the
  plan's next open task: any other answers `409 not_next_step` with `fields.task` naming the next one (a later step never starts
  before an earlier one). A general order, a work of no order and an empty plan are not gated.
- **`workshop.stop {work?, reason?}`** (agent tool, **A1**, every working role; `POST /internal/v1/workshop/stop`): the caller
  stops the running turn of its own work (its run's work, or `work`, assigned to it). The job is cancelled
  (`error_code: workshop_stopped`; the runner kills its process group on its next poll), nothing of it is delivered, the
  workspace goes `idle` and stays usable (a later `workshop.run` opens a fresh session in the same folder). Answers
  `{work_ref, stopped, job}`; `stopped: false` when nothing was running. Audit `workshop.stop` on both companies; work event
  `workspace_stopped`. (The owner's own stop, `POST /work/{ref}/stop`, still holds the work until he speaks: a
  `workshop.run` of a run his word started after the stop starts it again; any other answers `409 workshop_stopped`.)
- **Who may:** the route asks `hq.internal` as before (`server.run`, `via: workshop`) and `hq.actions` by the tool's own name
  (`workshop.run`): the advisor, the assistant and QC, who have that grant and not `server.run`, are no longer refused.
- **A turn is someone working.** A workspace turn whose job is `queued`, `running` or `awaiting_seal` counts as live work of its
  order: `SessionActivity.working` carries a row for it (`who_fa`: «کارگاه هلدینگ», or «Claude روی سرور شرکت» on a company's
  server; `doing_fa`: «دارد میسازد؛ هر نوبت تا ۶۰ دقیقه» / «در صف کارگاه»), `session.activity.working` counts it, and the idle
  sweep neither wakes the holder nor says «گیر کرد» while it runs.
- **Never a silent end.** The api's job sweep runs `workspace.after_job` for a workspace turn it failed (`timed_out`), and fails
  a workshop turn still `queued` after 15 minutes while its server is not online (`error_code: not_started`). `409
  workshop_unavailable` is answered at once when the workshop is paired but not online. When the holder cannot be woken for what a
  turn left (a lock, nobody assigned), the session gets a step saying so.
- **What an unfinished turn made is kept.** A turn stopped at its time limit sends its `out/` files (runner ≥ 0.3.3) and the
  failed turn's files become an output of the work titled «خروجی ناتمام کارگاه: …» (`produced_with.unfinished: true`), the work
  left open, before the holder is woken with the reason.
- **Its hands stay.** Every later turn of a workshop session carries the first one's `hands`, `model`, `permission_mode`,
  `allowed_tools` and time limit, the owner's own message in that session included (it ran without them).
- **Its tokens are not the work's budget.** A workshop turn's tokens are shown on the work (`tokens_used`) and the work's
  `budget_tokens`, when it has one, grows by the same amount: the workshop has no token cap, and a long turn does not leave the
  assignee's next run a cap of zero.
- **The company's kill switch covers its workshop turn.** `workshop.run` is refused (`423 company_locked`) while the work's own
  company is locked; engaging a company's switch cancels its running workshop turns; a queued one is not dispatched. The holding's
  runner polls in every company's view, so a closed work's folder of any company is closed and removed as §33.10 says.
- **Runner 0.3.3** (compatible with 0.3.2; only the workshop's runner needs it now): `sent` is recorded after the hub took the
  turn's result (a result that never arrived leaves its files to be sent again); `out/` is sent on a time-limit stop too;
  `workspaces.json` is written under a lock.

### 43.7 ⟨2026-11-10⟩ Tools and policy found by the audit (no new surface)
- The gateway waits for a held call longer than the api holds it (`server.*` with `wait_s`, `hub.ops {job}`): its 10 s client
  timeout gave up first and the model read `api_unreachable` for a job that was running, then sent the command again.
- A tool result is cut only when it does not fit (`GATEWAY_MAX_RESULT_CHARS`): a string was always cut to its first 4,000
  characters. A command's `stdout`/`stderr`, when cut, keep their **end**. `truncated` is true whenever a string was cut. A UUID is
  never read as a phone number.
- `mail.read` answers `messages` (the key `emails` was masked whole); `connection.read` answers `secret_state: set | missing`
  (the key `secret` was masked).
- `propose` takes kind `archive_schema` (the archivist's one card). A `system` role has `work.accept`, `work.progress`,
  `work.fail`, `activity.set` (`a2_grants.system`). An employee whose charter has `kpi.record` may record a KPI of its own company.
  `kill_switch.engage` and `deploy.freeze` are exempt from the lock by their tool names too. `server.map` has no `fresh`.
- llm-router: a subscription out of quota stays a fallback candidate (its breaker decides); `near_full` reads every window that
  holds and ignores an `ok` reading older than six hours. A `claude` job waits when every stored account is refused (it was sent
  out with no token).

### 43.8 ⟨2026-11-10⟩ A turn takes hub files with it (`workshop.run {…, files?}`)
The reel of the owner's recording came back silent because the narration the hub can make had no way into the workshop's folder.
- **`workshop.run {brief, title?, work?, task?, files?}`**: `files` is up to 10 file ids. Each must be an **original** of the
  work's own company, of the caller's company, or one of the owner's uploads of the work's order (`owner.order_files`); any other
  answers `422 fields.files`. The job's args carry `inputs: [{file_id, name, mime, size}]`; `name` is the name the file has on
  the disk (no folder, nothing hidden, never empty; a second file of the same name gets its number in front).
- The workshop's brief lists them («فایل‌های ورودی این نوبت در پوشه‌ی in/ هستند») as `in/<name> (<mime>)`.
- **`GET /runners/jobs/{id}/inputs/{file_id}`** (runner, bearer): the bytes of one input, as stored, for the runner of that job's
  server while the job runs. Only a file the job's own `args.inputs` names (checked when the turn was made); `404` for any other
  file or a job that is not a `claude` job, `409` once the job ended. `runners/next` gives each input its `url` (this route).
- A workshop whose runner is older than 0.3.3 cannot take them: `files` then answers `409 workshop_unavailable` at once
  (`fields.files` and `message_fa` say why), in place of a turn that would start without them.
- The runner (≥ 0.3.3) downloads them into `in/` of the work's folder before the session starts (≤ 200 MB each; `in/` a symbolic
  link is refused). One that cannot be fetched fails the turn before it starts («یک فایل ورودی این نوبت از ستاد دریافت نشد؛ نوبت
  شروع نشد.»): a turn never starts half-fed, and the holder is woken with the reason as for any failed turn (§43.4).

### 43.9 ⟨2026-11-10⟩ The wall between the companies' turns (`args.sandbox`, runner 0.3.4)
The owner, 2026-11-10: «نکته امنیتی هم اجرا بشه و کار راه بیفته نه اینکه گیر بکنه». Every turn of the workshop runs as the same
Linux user, so a turn of one company could read another company's work folder, its Claude transcripts and the runner's token.
- **The hub asks:** every workshop turn's args carry `sandbox: "auto"` (carried to the owner's own messages in that session, as
  `hands` is). A company's own server (`mode: on_server`) is never walled: its Claude works on that server itself.
- **The runner (≥ 0.3.4) puts the wall up when its server can:** Landlock, in the kernel (used from Linux 5.19; Ubuntu 24.04 has
  it): no root, no package. For the turn's whole process tree:
  - **closed:** every other work's folder (`~/hq-workspace/*`), the runner's own folder (its token, `workspaces.json`), this
    server's own `~/.claude` and `~/.claude.json` (other turns' transcripts, a login);
  - **open:** everything else as before, the work's own folder, and its private area `~/hq-workspace/.hq/<W-ref>/`: `home/` (the
    turn's `HOME`: a link to every entry of the real home that is not closed; a small file is copied, so a tool that rewrites its
    dotfile does it in the work's own home; anything new lands here), `tmp/` (`TMPDIR`), `job/` (settings, the hook's log and
    socket; `tmp/` and `job/` are emptied after the turn). The private area goes with the work's folder (30 days after its close).
  - The brief goes in on stdin (a process's command line is readable by every process of the user). The PreToolUse hook asks the
    runner over the job's own unix socket and the runner asks the hub (`POST /runners/classify`): the runner's token never goes in.
  - Claude's sessions live in the work's own home; a session begun on one side of the wall is carried to the other for `--resume`.
- **Never in the way of the work (`auto`):** the turn runs **without** the wall, and says why, when the server is switched off
  (`HQ_RUNNER_SANDBOX=off`), the kernel has no Landlock, the hub sent no Claude account for the turn (the server's own login is
  behind the wall), the probe failed (a walled process must work in its folder, fail to list what is closed, start the hook and
  the CLI; remembered for an hour), or the walled session did not start (no assistant message and an error: the same turn is
  started once more without the wall, and when that one starts the wall stays down on the server for an hour).
- **The result says which:** `data.sandbox: {state: "on", kind: "landlock"} | {state: "off", why}` (absent from a runner < 0.3.4).
  The hub keeps it on the output (`produced_with.sandbox: on | off`) and, when off, writes one audit entry on the holding
  (`workshop.sandbox_off`, A1, the work's ref, the server and the reason). It is never a blocker, a readiness item, a line of the
  session or a step of the owner's.
- **What it does not close:** the network, `/tmp` (shared; the workshop's brief says to keep temporary files in the work's folder or `$TMPDIR`), the tool folders the turns share
  in the real home (`~/.cache`, `~/.npm`, `~/.local`), and, before Linux 6.12, a signal to a process outside. `hq-runner
  sandbox-check` prints whether the wall works on a server, and why not.

## 44. Sessions are direct, and nothing sends the owner elsewhere ⟨1.27⟩ (2026-11-10, prompt 32)
The owner, 2026-11-10: «این برو بیا و هی مهر بکن و اینو مجوز بده و بروکراسی اداری بازی توی شرکت آزار و اذیت میده منو … مثل همین
سشنی که من با تو صحبت میکنم.» His decisions (`docs/SIMPLIFY_2026-11-10_DIRECT_SESSIONS.md`): his «تأیید» in the session is the
seal for what goes out and can be taken back; sessions are direct by default; hiring stays, without paperwork; the workshop's
isolation never blocks work (§43.9). This section is the first step; the publish wire follows (prompt 33).

### 44.1 The narrator of content is on
- The owner made it clear (2026-11-10): what he switched off on 2026-11-08 is **his own voice talk with the app** (§32:
  `voice.enabled`, default false, never a blocker or a readiness item). The **narrator of a reel or a video** is wanted.
- `speech.make` (A1, Google AI Studio's web page on the owner's account, §27/§38) is held by `media_director`, `voice_producer`,
  `video_director`, `motion_designer` and `scriptwriter`.
- The holder's brief (`capabilities.brief`) carries `narration: {state: signed_in | signed_out | unknown, tool: "speech.make"}`
  and `how.narration` (make the voice, deliver it so the owner hears it, give it to the workshop with `files`, never a silent
  video in place of a narrated one). `how.video` no longer says the voice is off.
- `speech.make` left `SILENT_TOOLS`: a refusal of it (`signed_out`, `expired`, a connection code) is a blocker of the session
  **only while AI Studio is signed out now** («گوینده وارد حسابش نیست»: the owner's one sign-in, `make aistudio-web-login`), and
  it is gone once a voice was made. The activity line of such a run says the same in one sentence. `media.render`, `media.item`
  and `media.on` stay silent.

### 44.2 A hire the owner asked for in his session
- `POST /internal/v1/decisions` with `kind: hire`: when the proposer's work (the card's `work_id`, else its run's work) belongs to
  an **open order**, and the owner's own words in that session ask for a hire (the order's text, his words in the session, the
  plan steps he wrote; a hire word left once every «استخدام نکن» phrase is taken out), the hire is **his decision already**:
  - hiring `closed` does not refuse it (`403 hiring_closed` stays for every other hire), and the hiring mode is not read;
  - no approver: no CEO card, no owner card, no passkey. The card is approved by code in the same request (`note_fa`:
    «استخدام به خواست مدیر کل در جلسه‌ی O-…») and the employee is made at once;
  - the hard checks of every approval still hold (an enabled connection offers the model, the monthly estimate, the company's
    month envelope when it has one, the kill switch, the hires a day); a month envelope is not required;
  - when a hard check refuses it, nothing is made and the card stays **the owner's own**, shown in that session (§34.1 `cards`);
  - the newcomer joins that session (one line; the holder is woken, reason `joined:`), as a hire from a talk card does (§39).
- The words are the owner's, stored by code: an agent cannot write them. A hire nobody asked for goes the usual way (§18.11).
- «کارمند ۲۴ ساعته» is, by the owner's decision, a standing routine made from one sentence (§31, automations), not a hire; this
  step adds no surface for it.

### 44.3 The holder works directly
- `talk_brief` (the holder's run for the owner's word, §34) carries `direct: true` and `direct_rule`: the holder is the one who
  does the order, with its own tools and the workshop; it does not delegate or split a step, raise a card for an internal thing,
  or send a part to the CEO, the CTO or another team when a tool of its own or the workshop does it. It hands a part over only
  when the owner names who should do it, or the step needs a right it does not have (said in one line). A hire happens only when
  the owner's own words ask for one (§44.2). His «تأیید» in the session is his approval of what he was shown; the holder never
  tells him to go and seal something elsewhere for an internal step.
- The common rules (`agents/roles/_common.md` v13) say the same to every role.

### 44.4 Three levels of approval
The owner, 2026-11-10: «اثر انگشت فقط برای پول، حذف برای همیشه، کلید و دسترسی، و دستور ویرانگر سرور».
- **Level 0, free:** everything inside and undoable (writing, making, reading, a draft, a file, a plan).
- **Level 1, one tap:** what goes out and can be taken back. The `media_publish` card is approved without a passkey
  (`decisions.TAP_KINDS`; `POST /media/items/{ref}/publish` and `POST /decisions/{ref}/approve` take no `X-Step-Up` for it; a
  token sent anyway is ignored), and `OrderCard.seal` reads `tap` for it. The owner's «تأیید و انتشار» on a file of his session
  (§44.5) needs no card at all.
- **Level 2, the passkey:** as before for every other A3 card and every kind of `STEP_UP_KINDS` (a hire outside a session, a
  budget, a tool, a series, an erase, a destructive command on a server, a line's gated step: `line_publish` may gate a
  newsletter or an ad, which cannot be taken back).

### 44.5 «تأیید و انتشار»: the owner publishes a file of his session (`POST /orders/{ref}/publish`)
Nothing here is a new way out of the hub: Instagram, for every company, lives on IG-Hub, and a server publishes through its own
runner (§26.1b). The tap makes one `publish` job on IG-Hub's server; the job is the record.
- **`POST /api/v1/orders/{ref}/publish`** (the owner's bearer; **no step-up, no card**; requires `Idempotency-Key`). Body:
  `{output: "O-…", file_id, kind?: reel | post | story, caption? (≤ 2200), account?: "@handle", cover_file_id?}`. `output` is an output of one
  of the order's works and `file_id` one of its attachments (an original video or image of that company): `404` / `422
  fields.file_id` otherwise. `kind` defaults to `reel` for a video and `post` for an image (`422 fields.kind` for a reel that
  is not a video). `423 company_locked` while the file's company is locked.
- **A reel's cover** (`cover_file_id`): an image of the same output; it goes as the job's second file (`files[1].role:
  "cover"`, `HQ_PUBLISH_FILE_2`, `meta.cover: true`). `422 fields.cover_file_id` for another kind or a file that is not an
  image of this output. `SessionPublish.cover_name` names it.
- **The company's Instagram connection** (`growth.connections`, kind `instagram`) gives the accounts, IG-Hub's server and the
  **`publish_command`**: a non-secret setting registered with `connection.set {…, publish_command}` (a secret-looking command
  and one the hub's classifier calls destructive are refused, `422 fields.publish_command`). With several accounts and none
  named: `422 fields.account` lists them.
- **`202 SessionPublish`** `{job, output, file_id, file_name, channel: "instagram", kind, account, state, url, note_fa, at,
  published_at}`; `state`: `publishing` (the job is queued or running) · `published` · `failed` (`note_fa` says why) ·
  `waiting_seal` (the hub's classifier held the command for the owner's seal) · `waiting_setup` (below; `job: null`).
  The same file to the same account in the same kind is **never sent twice**: a tap while its job is live, or after it was
  published, answers that publish; after a failure a tap is a new try.
- **The job** (`infra.server_jobs`, kind `publish`, on IG-Hub's server, actor the owner): `args = {session: {order, output,
  work, company, file_id}, kind, placement: "instagram_<kind>", account, command, caption, title_fa, meta: {channel, kind,
  account, company, cover}, files: [{file_id, name, mime, kind, role?}]}`. Its runner fetches each file with its own token from
  `GET /runners/jobs/{id}/inputs/{file_id}` (only the files the job names; a studio item's publish keeps its signed URLs) and
  runs the command with `HQ_PUBLISH_FILE_1`, `HQ_PUBLISH_CAPTION_FILE` and `HQ_PUBLISH_META`; the command prints
  `{"external_id", "url"}` (§26.1b). No runner change.
- **The session hears it:** a step «مدیر کل: «تأیید و انتشار»: ریلز «…» به @… میرود» at the tap; when the job ends, «منتشر شد:
  ریلز در @… · <link>» or «انتشار … انجام نشد: <why>» (the handle and the link are written as they are). `OrderReport.publishes`
  lists the session's publishes, newest first. Audit: `publish.session` (A3, the owner, on the file's company and on IG-Hub's)
  at the tap; `publish.session_done` / `publish.session_failed` on the file's company when it ends.
- **Never the owner's step:** a company with no accounts or no `publish_command` registered answers `202` with `state:
  waiting_setup` and a `note_fa`; the hub makes the technical work once per company (`run_meta.ig_publish`, P1: IG-Hub's CTO,
  else the holding's AIOPS; under the order's work, so its holder is woken when it is delivered) and the session says so. The
  work's brief names what the command gets and must print. The owner taps again when the session says it is connected.
- **From the output's own page** (where its files are; apps 0.19.8): `GET /api/v1/deliverables/{ref}/publish` answers
  `PublishPanel {order, channel, accounts, ready, publishes}` (`order: null` for an output of no session: the apps show no
  button; `ready`: the accounts and the publish command are registered; `publishes`: this output's, newest first), and
  `POST /api/v1/deliverables/{ref}/publish {file_id, kind?, caption?, account?, cover_file_id?}` is the same tap for the session the output
  belongs to (`409 fields.output` for an output of no session).
- **Taking it back:** Instagram's API deletes no post; a published post is removed in Instagram itself. (A Telegram message is
  still unpublished by the hub, §22.7.)
- The common rules (v14) tell every role: a ready file is shown with its caption and «تأیید و انتشار؟»; no card for it; never
  «منتشر شد» before the session says so.

## 45. The owner's standing permission to publish ⟨1.29⟩ (2026-11-10, prompt 34)

The owner, the same day as §44: «پرامپتی که من برای کار گروه فرستاده بودم … نوشته بودم به صورت خودکار از روز دوم انجام بشه و
به اتوماسیون تبدیل بشه نه اینکه هر بار من تایید کنم. ۱۰۰ تا کارگروه راه بندازم اونوقت باید روزی صد بار تایید بدم. پس جوری آپ
رو باید طراحی بکنید که همه جور بشه باهاش کار کرد.» §44.5 made his word one tap on each output. Here that word can be given
**once for a working group** instead: the same publish job, the same route through IG-Hub, no new way out of the hub.
Nothing a model says can give this permission; only the owner's own routes below set it.

### 45.1 The word: a membership's `publish`

`growth.memberships.publish` (migration 0059), one per company in a working group (§29.11, §40.2):
`{mode: "auto" | "ask", account?, story?, since, by}`. Absent or `ask` is the behaviour of §44.5: each output waits for his
tap. `auto`: from the next run on, the hub publishes the package of each routine's delivered work by itself.

- **`PUT /api/v1/groups/{key}/members/{code}/publish {mode, account?, story?}`** (owner; his tap, **no step-up**; audit
  `group.publish`, A3) → `Membership`. `account`: one of the company's registered Instagram accounts (`422 fields.account`
  names them); left out for a company with one account, and for a company whose path is not registered yet (checked when
  it goes out). `story: true`: the same video also goes out as a story.
- **With the seal:** `POST /api/v1/playbooks/{ref}/seal {publish?: {mode, account?, story?}}` sets it for the session's
  company (the group's first member). **With the gift:** `POST /api/v1/playbooks/{ref}/apply {company, as_is: true,
  publish?}` sets it for that company.
- `Membership.publish` and `PlaybookMember.publish` answer `{mode, account, story, since}` (`ask` when he has not said
  `auto`).
- **Sealing and retiring a working group are his tap** (`POST /playbooks/{ref}/seal`, `/retire`: no step-up since v1.29;
  audit A3 as before). The passkey is for money, deleting for good, keys and access, and a destructive command on a server
  (§44.4); a seal hires inside the month's envelope and a retire deletes nothing. A client that still sends a step-up
  assertion is answered the same.

### 45.2 The package

> **IG-Hub as it is (its repository, read 2026-11-10):** a publishing API for other servers (`/api/v1/media`,
> `/api/v1/publish` with `kind: image | reel | carousel | story`, `caption`, `first_comment`, `scheduled_at`, cancel and
> status with the permalink); **JPEG pictures only**; **no cover field for a reel yet**; comment rules (keywords, on all
> posts / the next post / chosen posts, public replies, one private reply with a link button, hours, cooldown) and the
> statistics (likes and comments of each post) only in its own panel, not through a key. So a package's picture is a
> `.jpg`, a reel's cover is carried by the hub and used once IG-Hub takes it, and scheduling and the comment rules are
> IG-Hub's own to wire next.

What a routine's work made to go out is **one output** of that work (or of a work under it): its newest finished output
that carries **`caption.txt`** (or `caption.md`) and a video; the cover is an image of the same output (one named `cover…`
first); without a video, an image with `caption.txt` goes out as a post. A workshop turn leaves these in `out/` (§43.3
already accepts `.mp4`, images and `.txt`). `caption.txt` is the mark of a package: an output without it is never sent on
a standing word.

- The routine's work is **told** by code: on `auto`, its brief ends with a «Publishing: the owner gave this working group
  his standing permission …» block (where it goes, the package, «never ask the owner to approve it»). The common rules
  (v15) tell every role the same and that the package is one output.
- `PublishPanel` (the output's page, §44.5) gains **`tap`** (true for every output: one of no session is tapped in
  «خروجی‌ها» too; `POST /deliverables/{ref}/publish` no longer answers `409` for it), **`caption`** (the text of its
  `caption.txt`, so the sheet opens with it), **`group`**, **`group_fa`** and **`mode`** (the working group whose routine
  made it and his standing word). `SessionPublish` gains **`auto`** (true: sent on the standing word).

### 45.3 Going out by itself

- **When:** the routine's own work is delivered (`POST /internal/v1/work/{id}/deliver`, after its commit), and again on the
  groups' tick for every run of the last 3 days with `auto` that has not gone out (a path that was not registered yet, a
  lost hook). A run is sent **once**: its jobs carry `args.standing = {run, group, routine, occurrence, since}`.
- **What:** one `publish` job as in §44.5 (`args.session.order: null`, actor the service `groups`): the video as a reel
  with its cover and the caption, and with `story` a second job, the same video as a story. Audit `publish.standing` (A3,
  on the company and on IG-Hub's, naming the day he gave his word), then `publish.standing_done` / `_failed`.
- **Only what comes after his word:** a work delivered before `since` is never sent by it (an output that was already
  waiting for his tap stays his to tap). **Never twice:** a file he already tapped himself (the same account, the same
  kind) is not sent again. A paused member, a group that is off, the kill switch or a freeze (the launch gate): nothing
  is sent.
- **Never silent, never his chore:** the run's `note_fa` says where it stands («انتشار خودکار: ریلز به @… میرود»,
  «خودکار منتشر شد: … · link»). A video without its caption is not sent: the run says so and the owner gets **one**
  notification with the output («… منتظر شماست»), where one tap sends it. A company whose publish path is not registered
  gets the technical work of §44.5 once, and the run goes out on a later tick. A publish Instagram refused is told to him
  once, with the output and «دوباره». A work that made nothing to publish (a report) is no fault and tells nobody.
- **Taking the word back:** `PUT … {mode: "ask"}`; pausing the member or retiring the group stops it as well.

## 46. The time, the comment rule and the carousel of a publish ⟨1.30⟩ (2026-11-10, prompt 34)

The owner, after IG-Hub's repository was read with him: «هر بار شاید یک کامنت باشد. شماره دو ساعت را باید هاب تنظیم
بکند ولی باز هم از داخل خود سرور ig هاب نگاه کنی تنظیم پست با ساعت دارد … قابلیت گذاشتن کاور هم دارد باید کدش در آی جی هاب
نوشته شود چون من api کامل از فیس بوک دریافت کردم.» So the hub decides and IG-Hub does: nothing here is a second scheduler
or a second rule engine.

### 46.1 What IG-Hub gained (its own repository, branch `claude/coinepro-hub-setup-hsvnw7`)

- Publishing takes **`cover`** for a reel (one JPEG, sent to Meta as `cover_url`) and **`comment_rule`** (`keywords`,
  `reply_text`, `link`, `button`, `public_replies`): kept with the publication and made a rule **for the post it became and
  no other**, when it is published (ahead of the account's general rules).
- `GET /api/v1/posts`: an account's last posts with likes and comments, and how they did by the Tehran hour they went out.
- **`deploy/hq_publish.py`**: the command the hub's runner runs there for one `publish` job (the standard library only).
  It reads `HQ_PUBLISH_FILE_n`, the caption file and `HQ_PUBLISH_META`, uploads, publishes or schedules through IG-Hub's
  key API, and prints `{"external_id", "url"}`: the post's id and link, or **`"pub:<id>"` with a null url** while IG-Hub
  holds it for its time or Meta is still preparing it. A refusal is one plain Persian line and exit code 1. The key is
  made on that server into a file (`python -m ighub.admin api-key hq FILE`) and never printed.
- So a company's `publish_command` is `python3 <IG-Hub's folder>/deploy/hq_publish.py`; the technical team's work (§44.5)
  names it.

### 46.2 The tap (`POST /orders/{ref}/publish`, `POST /deliverables/{ref}/publish`), additive

- **`scheduled_at`** (a time with its zone, at most a year ahead; one nearer than 2 minutes is now): the job's
  `meta.scheduled_at`. IG-Hub holds the post till then (it shows in IG-Hub's own calendar, where it can be cancelled).
- **`comment`** `{keywords: [..], reply, link?, button?, public_replies?}` (not for a story; a word and a reply are both
  needed, `422 fields.comment`; a link that is not https is left out): `meta.comment`.
- **`first_comment`**: `meta.first_comment`.
- **`kind: "carousel"`** with **`file_ids`** (1 to 9 more videos or images of the same output, in order): the job's files
  are `file_id` then those. `422 fields.file_ids` otherwise.
- `SessionPublish` gains `scheduled_at`, `comment` (the first word), `files`, and the state **`scheduled`**.
  `PublishPanel` gains `comment` (the rule the package carries).
- **The package** (§45.2) may carry **`comment.txt`**: `keyword: …`, `reply: …`, `link: https://…`, `public: …`, one a
  line, in English or Persian labels («کلمه», «پاسخ», «لینک»). The sheet opens with it, and a standing publish sends it.

### 46.3 Held, then asked about

- The command's `pub:<id>` answer ends the job `done` but the publication is **not out**: its state is `scheduled`
  (its time is ahead) or `publishing`. The session says once «زمان‌بندی شد: ریلز در @…، ساعت …»; nothing says «منتشر شد».
  The same file to the same account in the same kind is still one publication: a second tap answers it.
- **`follow_up`** (the api's 30-second sweep): 90 seconds after its time, and then every 3 minutes for 6 hours, the hub
  queues one `publish` job with `meta.check: "pub:<id>"` and no file. Its answer is the publication's record from then
  on: the post's link («منتشر شد … + link», the run's note, the audit), the same `pub:<id>` (asked again), or Instagram's
  refusal (said plainly; a tap is then a new try). A question the runner never answered (`timed_out`, `not_started`)
  changes nothing and is asked again.

### 46.4 The standing word's hour

`publish.at` («HH:MM», the owner's zone; `PUT /groups/{key}/members/{code}/publish {…, at?}`, the seal and the as-is gift
take it too; `422 fields.at` for anything else): each day's package goes out at that hour **today when it is still
ahead**, at once when the work is delivered after it (it is never kept for tomorrow, when the next one comes). The
routine's brief names the hour and `comment.txt`.

## 47. The ledger of what was said: a topic is never made twice ⟨1.31⟩ (2026-11-10, prompt 35)

The owner's order (`docs/ORDER_PROCHART_REELS_2026-11-10.md`): «هیچ روزی تکراری نباشد: ۳۶۵ روز، ۳۶۵ مطلب و ویدیوی
متفاوت», and for each day's Pinterest sample «هر بار متفاوت». Until now that rested on what a model remembered of a
session. From here it is a table and a comparison made by code.

### 47.1 The ledger (`growth.topics`, migration 0060)

One row for each topic and each reference (an outside sample) a company used in a working group:
`TopicEntry {id, kind: "topic" | "reference", title_fa, url?, at, by, source: "claim" | "package" | "owner",
work_ref?, output?}`.

- **The same topic, by code:** letters unified (Arabic and Persian forms, digits), marks, half-spaces and punctuation
  dropped, a plural's «ها/های» cut, filler words («آموزش», «معرفی», «ویدیو», «چیست», …) and the company's own name
  left out; two titles are one topic when their words are the same in any order, when they read the same once the
  spaces are out («پرو چارت», «پروچارت»), or when they share at least 0.8 of their words. Another indicator, another
  product compared, or a part of a topic («واگرایی در RSI» after «اندیکاتور RSI») is another topic.
- **The same reference:** its address without `www.`, the country prefix, the query and the trailing slash; a
  Pinterest pin is its number.
- **Whose ledger:** the working group of the routine run the work belongs to (the work itself, or up its parents and
  requests). A work of a session that is not a working group yet writes in that session's own list; sealing the
  session's playbook (§40.2) moves those lines to the group, so day one counts.
- A day's run names **one** topic and **one** reference: the same one again answers the same line, another one
  replaces it. A freed line (below) is kept as `freed`; nothing is deleted.

### 47.2 `topic.claim` (agent tool, A1; `POST /internal/v1/topics/claim`)

Held by every working role (`SHARED_TOOLS`). Body `{title_fa?, kind?, url?, work?}`: the caller's run's work, or
`work` assigned to it (`403` otherwise). `201 {entry, new, group}` (`new: false`: this run had named the same one);
**`409 topic_taken`** when the ledger already says it: `fields.title_fa` names the earlier line and its day,
`fields.recent` the last ones, and the model chooses another. `422 fields.url` for a reference without an address.
Policy `hq.internal` op `topic.claim` (groups.rego: a working agent, for a work the api says is its own). Audit
`topic.claim` (A1) on the work's company.

- **The routine is told by code:** the brief of every routine of a working group that publishes (a playbook's group,
  or one with a publishing connection) ends with a «Ledger: …» block: claim before writing, the last 40 topics and 10
  references («Already said, newest first: …»), and `topic.txt` in the package. The common rules (v16) say the same.

### 47.3 What goes out is in the ledger, and a twin is not sent by itself

- **On the standing word (§45.3):** before a package goes out, its topic is the run's own claim; a run that named
  none is read by the hub (`topic.txt` of the output, else the first line of its caption without its hashtags; `source:
  package`). When that says what an earlier line of the ledger says (`topic.txt`: the rule of §47.1; a caption line:
  the same words only), the package is **not sent by itself**: the run's note says «موضوع این نوبت پیش‌تر گفته شده
  («…»، روز) …» and the owner gets one notification with the output, where one tap sends it anyway. A package he
  already tapped himself is no twin to hold.
- **On his own tap (§44.5):** an output of a routine's work he publishes himself is noted in the ledger the same way
  (never refused: it is his choice).

### 47.4 The owner's page of the ledger

- `GET /api/v1/groups/{key}/members/{code}/topics?kind=&q=&limit=&cursor=` → `TopicLedger {items, topics,
  references, next_cursor}`, newest first.
- `POST …/topics {kind?, title_fa?, url?}` (the owner adds one himself, «این را قبلاً گفته‌ایم») → `201 TopicEntry`
  or `409 topic_taken`. `DELETE …/topics/{id}` frees a line (it may be said again). Audit `topic.add` (A1),
  `topic.free` (A2).

## 48. A company's narrator, set once ⟨1.31⟩ (2026-11-10, prompt 35)

The owner's order: «گوینده یک بار برای همیشه تنظیم شود». The voice and its style were words in a working group's
instructions that a model passed along each time.

- **`media.narrators`** (migration 0060): one row per company, `{voice, style_fa}`. `voice` is one of AI Studio's
  prebuilt speakers (`422 fields.voice` otherwise).
- **`GET /api/v1/companies/{code}/narrator`** → `Narrator {company, set, voice, style_fa, by, updated_at, voices:
  [{name, gender, trait_fa}], aistudio: signed_in | signed_out | unknown}` (`set: false`: none yet; `voice` is then
  AI Studio's default). **`PUT /api/v1/companies/{code}/narrator {voice, style_fa?}`** (owner; his tap, no step-up;
  audit `narrator.set`, A2).
- **`speech.make` takes it by code:** the voice is for the company of the caller's run's work (a holding role
  working on a company's order speaks with that company's narrator), else the caller's own. When that company has a
  narrator, its voice and style are used **whatever `voice` and `style` were passed**; `SpeechMakeAnswer` gains
  `narrator: true`. A company without one speaks as before.
- **`narrator.set` (agent tool, A1; `POST /internal/v1/narrator {voice, style_fa?, work?}`):** the agent that works
  on an open order of the owner sets the narrator of that work's company, as he asked in the session. `403` for a
  work of no order. Policy `hq.internal` op `narrator.set` (groups.rego). The holder's brief
  (`capabilities.brief.narration`) names the company's narrator when it has one (`narrator: {voice, style, fixed}`).

## 49. The best hour, by itself ⟨1.31⟩ (2026-11-10, prompt 35)

The owner's order: «بعد از یک ماه صفحه را تحلیل کند و در ساعت‌های پربازدید طبق زمان‌بندی منتشر کند».

> **What IG-Hub has (its server's report, 2026-11-10; its repository read again):** each post's likes and comments
> for an account's last 50 posts, overwritten every 15 minutes, no history; **no views, reach, saves or shares**
> (its code asks Meta for no insights and has no permission for them). So «پربازدید» is, until IG-Hub reads insights,
> **the hour whose posts drew the most likes and comments**, and the hub says so wherever it shows the hour.

### 49.1 The read

- Once a day for each registered Instagram account of a company whose `publish_command` is registered: one
  read-only `exec` job on IG-Hub's server (actor the service `best-hour`), `<publish_command> posts <account> 100`
  (IG-Hub's `deploy/hq_publish.py` prints its own `GET /api/v1/posts`: `{items: [{id, media_type, permalink,
  posted_at, like_count, comments_count}], hours}`). The hourly connections read asks it and collects it on a later
  tick. The command must pass the hub's read-only check; nothing else is ever run this way.
- The hub keeps each post (`growth.ig_posts`, upsert by its id) and the state of each account's read
  (`growth.ig_post_reads`). An IG-Hub whose command does not know `posts` yet answers nothing readable: noted, tried
  again the next day, never a blocker.

### 49.2 The rule (code, never a model)

The posts of the last 90 days that are at least 48 hours old; at least **12 posts over at least 28 days**; each hour
of the owner's day scored by its posts' mean likes + comments, pulled toward the account's own mean by a prior of 2
posts; an hour needs 2 posts; the best one, a tie to the hour with more posts.

- **`GET /api/v1/companies/{code}/best-hour?account=`** → `BestHour {account, hour: "HH:00" | null, at, enough,
  posts, days, basis: "likes_comments", note_fa, read_at}`. `enough: false`: too little data yet, and `note_fa` says
  how much there is.
- **The standing word (§45, §46.4) gains `best`:** `PUT /groups/{key}/members/{code}/publish {…, best?: bool}` (the
  seal and the as-is gift take it too); `MemberPublish.best`. With `best` and enough data, each day's package goes out
  at that hour **today while it is still ahead**, else at once; without enough data, at the fixed `at` when there is
  one, else at once. The routine's brief says the hub chooses the hour.
- **The tap's sheet:** `PublishPanel.best` (the `BestHour` of the account, only when `enough`), so «بهترین ساعت» is
  one of its times (`scheduled_at = best.at`).

## 50. A standing routine from one sentence («کارمند ۲۴ ساعته») ⟨1.31⟩ (2026-11-10, prompt 35)

The owner's decision (2026-11-10, §44.2): «کارمند ۲۴ ساعته» is not a hire; it is a standing routine made from one
sentence, in the session, **without a card, without a passkey, and without going through «کارگروه از این جلسه»**.

- **A routine** is an automation (§31.7) of the plainest kind: its trigger is a **schedule** and every action is
  `work.create`, `notify.owner` or `notify.lead`. It only makes work for a role of the company (inside its month
  envelope) or tells someone, and one tap switches it off, so the owner's sentence is the seal. Anything more (an
  event or a number as the trigger, a line, an ad, an n8n flow) stays an automation he seals (🔏 `automation.seal`).
- **`POST /api/v1/routines {sentence_fa, company?, order?}`** (owner; no step-up; `Idempotency-Key`) → `201
  SessionRoutine {ref, company, sentence_fa, when_fa, preview_fa, state: "on", next_at, last_run_at, runs, order,
  note_fa}`: one compile (§31.7), checked by code, then **`on` at once** (`sealed_at` now, no step-up id,
  `growth.automations.source = {order, by, routine: true}`). `company` left out with `order`: the session's
  company; left out without: the holding's. `422` (nothing made) when the sentence does not compile or is more than a
  routine (`message_fa` says which). Audit `automation.routine` (A2). The session says «روال دائمی ساخته شد: …».
- **`GET /api/v1/routines?company=&order=`**; `OrderReport.routines` lists a session's own, newest first.
  `Automation` gains `routine` and `order`. Switching: `POST /automations/{ref}/state {on | off}` (no step-up, as
  before).
- **The holder's way in (`automation.propose`, A1):** when the compiled rule is a routine and **the owner's own
  words in that open session ask for something standing** (the order's text, his words there, the plan steps he
  wrote; a word of repetition: «هر روز», «هفتگی», «۲۴ ساعته», «دائمی», «هر N ساعت», …), the automation is made `on` in
  that request (`state: "on"`, `routine: true`; the session says «روال دائمی به خواست مدیر کل ساخته شد: …»; no
  notification to seal). Otherwise it is `proposed` as before. The words are his, stored by code.

## 51. A scheduled post taken back from the app ⟨1.31⟩ (2026-11-10, prompt 35)

- **`POST /api/v1/publishes/{job}/cancel`** (owner; his tap, no step-up) → `SessionPublish`. `job`: the
  publication's job (`SessionPublish.job`). For a publication that is `scheduled` or `publishing` (not out yet):
  - one whose first job no runner has taken is cancelled here (`state: cancelled` at once);
  - one IG-Hub holds (`pub:<id>`) is cancelled there: one `publish` job with `meta.cancel = "pub:<id>"` and no file.
    Its command answers **`{"external_id": "cancelled:pub:<id>", "url": null}`** (cancelled), the post's id and link
    (it went out first: the publication is `published` and the session says so), or exits non-zero (IG-Hub refused:
    the publication **stands**, `note_fa` says «لغو انجام نشد (…)», and the follow-up of §46.3 goes on). While the
    cancel is on its way the answer keeps its state with `note_fa` «در حال لغو»; a second tap answers the same job.
  - `409 not_cancellable` for one that is out, failed or cancelled already, and for one whose file is still on its
    way to IG-Hub (a moment later it is cancellable).
- `SessionPublish.state` gains **`cancelled`**. After it a tap on the same file is a new publication. The session
  says «لغو انتشار: …» at the tap and «لغو شد: … منتشر نمیشود» or «لغو … انجام نشد: …» when IG-Hub answers. Audit
  `publish.cancel` (A2).
- **IG-Hub's side** (its prompt 2): `hq_publish.py` takes `meta.cancel` (its own `DELETE /api/v1/publish/{id}`). An
  older command there fails the cancel job with a plain line and changes nothing.
- Every `publish` job's meta also carries **`key`** (the publication's own key, the same on every try), for IG-Hub to
  refuse a twin once it reads it.

## 52. A picture goes out as a JPEG ⟨1.31⟩ (2026-11-10, prompt 35)

Instagram publishes JPEG pictures only (IG-Hub refuses any other: `publish_jpeg_only`). In every `publish` job
(the tap, the standing word, a reel's cover, a carousel's pictures, a story's picture) a picture that is not a JPEG
is sent as one the hub makes from it: turned the way it is seen (EXIF), on white where it was see-through, RGB, its
longer side at most 4096 px, quality 92. The JPEG is a file of the same company (`meta.jpeg_of` names the picture it
came from), made once and used again; the publication keeps the name and the id of the file the owner tapped
(`SessionPublish.file_name`, `file_id`, `cover_name`). A picture the hub cannot read: `422 fields.file_id` on a tap.
PNG, WebP and HEIC are read; a video is never touched.

## 53. The workshop on its highest effort ⟨1.31⟩ (2026-11-10, prompt 35)

The owner's order: the motion graphic is made by «Opus 5.5 با بیشترین effort».

- Every workshop turn's args carry **`effort`** (`low | medium | high | xhigh | max`): **`max`** unless the caller
  asks for less (`workshop.run {…, effort?}`); carried to the owner's own messages in that session as `model` is.
- **Runner 0.3.5** passes it to Claude Code (`--effort`), reading once from the CLI's own `--help` which levels it
  takes: the level asked for, else the highest it has below it, else none (the turn runs as before). The result's
  `data.effort` says what was passed; the hub keeps it on the output (`produced_with.effort`, with
  `produced_with.model`). A runner older than 0.3.5 ignores the argument.
- Error codes (additive, §47 and §51): `topic_taken` 409 · `not_cancellable` 409.

## 54. The direct session, step three: the holder is one session with the hub's tools ⟨1.32⟩ (2026-11-10, prompt 35)

The owner (`docs/SIMPLIFY_2026-11-10_DIRECT_SESSIONS.md` §4.1, §7.3): «مثل همین سشنی که من با تو صحبت میکنم … توی
شرکت هم همین اشتراک کلود هست و همین مدل‌ها، پس نباید انقدر پیچیده باشه». Until now a session's holder was a short run
of a model that could only name a tool, six steps at a time, read the session again on every wake, and handed
anything with hands to the workshop and waited. From here the holder's run **is** a turn on the workshop: one
brain, one thread, the same Claude session and the same folder on every word of the owner's, up to 60 minutes.

### 54.1 What does not change

- **Everything of the hub goes through the Tool Gateway.** The session reaches the hub's data and actions only by
  its role's own tools. Each call is relayed by the workshop's runner to the api, handed by the worker to the
  gateway with a token minted for the turn's own run, and decided by the gateway as for any agent: the role's
  tools, the policy, the class (A0 to A4: an A3 is still a card, an A4 never an AI's), the kill switch, the hold of
  the overseer, the audit row. The runner's own token never goes behind the workshop's wall (§43.9).
- **The Treasury sees every token:** the turn's usage comes with its result (§26.2), on the hub's Claude account of
  the moment, which the hub chooses.
- The companies' data stay apart (the wall of §43.9; every tool's own company check). A turn has its hour and is
  never silent (§43.6). The passkey is for money, deleting for good, keys and access, and a destructive command
  (the PreToolUse hook classifies every command of the session as before).
- What the workshop itself may reach (the internet, its own folder) is what §43 already gave it; nothing of the hub
  is reachable from there but the tools.

### 54.2 The hand-over (worker, `Runner.execute`)

A claimed run is handed over when all of these hold; otherwise it runs as before (nothing ever waits for the
workshop):
- it is a `work` run of the **assignee of an order's own root work** (the session's holder), the session open;
- its reason is not one that only tells of a failed turn (`workspace_failed:`): that stays the quick classic run;
- the holding's workshop is **online on runner ≥ 0.3.5**, and the work's workspace, if it has one, is on it and
  not stopped by the owner (his own later word starts it again);
- `HQ_DIRECT_SESSIONS` is not `off` (a switch of the deploy; sessions are direct by default, his decision).

The hand-over makes one **workspace turn** of that work (§43.2: the same folder `~/hq-workspace/<W-ref>`, the same
Claude session resumed) with `args = {…hands, direct: true, tools: "hub", run: <its run>, order: <F-ref>, model:
"claude-opus-5-5", effort: "max", sandbox: "auto", inputs?}` and the classic run ends `done` at once (note `direct
turn <job>`; it called no model). Audit `session.turn` (A2) on the work's company and the holding.

- **Its brief** (code, Persian): on a session's first turn who it is (the holder's title and company), the rules
  (its final answer is its word to the owner: short, plain Persian; deliverables in `out/`; never publish, pay or
  message outside; hand a part over only when the owner says who; the hub only through its tools), its tools, its
  role's own guide, the session's memory and the order; on every turn the session's state (plan, steps, blockers,
  outputs, files, the owner's open turn), why it was woken, and the owner's last words. A later turn of the same
  Claude session carries only what is new.
- **The owner's files** of the session that no turn carried yet go with it (`in/`, §43.8).
- **One brain, one thread:** while a turn of the work is live (a direct one, or the holder's own classic
  `workshop.run`), a new run of the holder for it ends at once (`direct turn waits`) and, when the owner's word
  caused it, the session says once «مسئول هنوز روی نوبت قبلی است؛ حرف شما بعد از آن خوانده میشود …». When the turn
  ends, a word of his that came after it began starts the next turn (`owner_reply:`).

### 54.3 The turn's own run (`agents.runs.trigger = 'direct'`, migration 0061)

The gateway acts for a run, so a direct turn opens one (`agents.open_direct_run`): the holder's, for the order's
work, `running` at once, 500 tool calls (50 a step; the api counts the steps), its token good for the turn's hour.
- It never counts against the one-running-run rule (as a `talk` run does not): a holder whose turn builds for an
  hour still answers its other work. One live direct run per work.
- It ends with the turn (`agents.close_direct_run`): `done` with the turn's tokens, or `failed` (the job's code).
  One left open past its token is failed when the next is opened.
- A direct run is not a line of the session's activity, a «talk without output» or a busy employee: the turn's own
  row is (`SessionActivity.working`: the **holder's** name, «دارد روی فرمان شما کار میکند؛ هر نوبت تا ۶۰ دقیقه»).

### 54.4 The hub's tools in the session (runner 0.3.5)

A turn with `args.tools: "hub"` gets one MCP server, the runner's own (`hq-runner mcp-tools`, stdio; no other MCP
server is loaded): its tools are `mcp__hq__<name>` and are allowed without asking. The server holds no secret: each
request is one line to the job's own unix socket, and the runner asks the hub.

- **`GET /api/v1/runners/jobs/{id}/tools`** (runner, bearer; a live direct turn of its own server) → `{tools:
  [{name, description, input_schema}]}`: the tools of the holder's charter (a drafted role: its draft's), without
  `workshop.run` / `workshop.stop` (the session is the workshop) and without any A3 or A4 tool. `name` is the tool's
  name with its dot as an underscore (`order.ask` → `order_ask`); `input_schema` is the gateway's own input model
  (`POST /v1/tools/catalog` on the gateway, asked through the worker; when it cannot be asked, an open object and the
  catalog's description). Two more that the api answers itself: **`skill_list`** and **`skill_read {role}`**.
- **`POST /api/v1/runners/jobs/{id}/tools/call {name, args}`** → the gateway's outcome `{outcome: ok | denied |
  error, class, code, ref, result?, hint_fa?, fields?}`, always `200` (a refusal is an outcome the session reads). The
  api maps `name` back to a tool the holder holds (any other: `unknown_tool`, nothing is called), finds the turn's
  run and hands `{employee, run, step, index, tool, args}` to the worker (workflow `DirectTool`), which mints the
  agent token for that run and calls the gateway's `POST /v1/tools/call`. `422` for a job that is not a direct turn,
  `404` for another server's job, `409` once the turn ended.
- **Roles are skills, not seats:** `skill_list` names every working role with its Persian title; `skill_read`
  returns that role's guide (its charter's body). The session reads the scriptwriter's or the motion designer's
  guide and does that work itself: nobody is hired to make a reel (a hire happens only on the owner's own word,
  §44.2). Audit `skill.read` (A0).
- The runner's result says how many hub tools the session called (`data.tool_calls`).

### 54.5 The turn's end in the session

- **Done:** what the session answered is **the holder's own word**: a line of the session's talk and a step by the
  holder's name (never «کارگاه هلدینگ»). What it left in `out/` is one output of the order's work (`produced_with:
  {runtime: "workshop", direct: true, model, effort, …}`), with «تأیید و انتشار» on its files (§44.5). The work stays
  open (it is his session), and **no second run is woken to repeat it**. A question the turn asked with `order.ask`
  is already the session's open turn. An answer of nothing, with no file and no question, is said («این نوبت بی‌جواب
  تمام شد …»), never left silent.
- **Failed or timed out:** the run ends `failed`, what the turn had made is kept as an unfinished output, and the
  holder is told at once by the quick classic run (`workspace_failed:`), as for any workshop turn (§43.4, §43.6).
- **Stopped by the owner** (`POST /work/{ref}/stop`): the run ends; only his own later word starts a new turn.
- `OrderReport.direct` (bool): the workshop can take this session's turns directly now.

### 54.6 What stays classic

A working group's routine, a colleague's child work, a message, a meeting, a talk persona's read, and every run
while the workshop cannot take a turn: all as before (a routine's work still hands its build to the workshop with
`workshop.run`). Step three is the session's own holder; nothing else changes its path.
