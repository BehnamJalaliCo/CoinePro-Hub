# بررسی ریپوی Agency-Agents برای هاب (۲۰۲۶-۱۰-۲۲)

> خواسته‌ی مالک: «یکی از ریپوهای ناتمام قدیمی منو ببین… اگر به درد این پروژه میخوره بخش‌هایی ازش رو بردار، البته با ریز جزئیات بررسی بشه؛ نمیخوام پروژه‌ی قبلی که با شکست مواجه شده این پروژه رو خراب کنه.»
> - **ریپو:** `github.com/BehnamJalaliCo/Agency-Agents`، commit 9107cc5. فقط‌خواندنی و بیرون از هاب کلون شد. هیچ اسکریپتی از آن اجرا نشد.
> - **روش:** دو بازبین مستقل. یکی ۲۸۲ پرسونای ایجنت را خط‌به‌خط خواند؛ دیگری کد، اسکریپت‌ها، اپ دسکتاپ و ورک‌فلوها را.
> - **هیچ چیزی از آن وارد هاب نشده است.** این سند فقط گزارش و پیشنهاد است.

## ۱. خلاصه
- **ریپو مخرب نیست.** نه کد از راه دور اجرا میکند، نه تله‌متری دارد، نه رمز واقعی، نه دستور پنهان برای هوش مصنوعی. فرانت‌متر هر ۲۸۲ پرسونا سالم است و هیچ فایلی بریده یا تکراری نیست.
- **خطر واقعی نصب‌کننده‌هایش است.**
  - `scripts/install.sh` بدون پرسش ۲۸۲ پرسونا را در پوشه‌های سراسری `~/.claude/agents`، `~/.codex`، `~/.gemini` و چند ابزار دیگر میریزد و فایل هم‌نام را بی‌هشدار بازنویسی میکند (`:340`).
  - اگر روی سرور هاب اجرا شود، روی **همه‌ی سشن‌های Claude هاب** اثر میگذارد.
  - اپ دسکتاپ هم در `~/.claude/agents` مینویسد.
- **ناتمام است:** نسخه‌ی امضاشده منتشر نشده، ترجمه‌ای وجود ندارد، و چند سند با هم تناقض دارند.
- **محتوای پرسوناها، عین متن، با قوانین هاب نمیخواند:**
  - **عمل بدون تأیید:** انتشار، پیام مستقیم، زمان‌بندی خودکار و حتی پرداخت.
  - **عدد ساختگی:** ۲۴۴ پرسونا از ۲۸۲ هدف و سابقه‌ی ساختگی دارند، مثل «۳۰۰٪ افزایش».
  - **ترفندهای اسپم و فریب:** چند حساب، شمارش معکوس دروغ، decoy pricing.
  - **شل و نصب با npm.**
  - **هیچ پوششی برای کاربر فارسی‌زبان، تلگرام، کریپتو یا فارکس ندارند.**
- **ولی حدود ۳۰ پرسونا روش و چک‌لیست خوب دارند**، دقیقاً جایی که هاب کمبود دارد (بند ۲).

## ۲. چرا به درد هاب میخورد
هاب امروز فقط برای چند نقش منشور کارمند دارد: SRE، امنیت، راستی‌آزما، و در staged پشتیبانی و درآمد. ولی قالب شرکت دپارتمان‌های `TECH`، `GROWTH`، `SALES`، `PRODUCT`، `FIN`، `QUANT`، `AIOPS` و `HR` دارد. وقتی استخدام باز شود، مدیرعامل‌ها برای بیشتر این دپارتمان‌ها **منشوری برای استخدام پیدا نمیکنند**: `hire` بدون منشور مناسب `422` میگیرد.

این پرسوناها میتوانند **منبع** نوشتن آن منشورها باشند. نه کپی؛ بازنویسی کامل در قالب هاب.

| دپارتمان | منبع | نقش پیشنهادی در هاب |
|---|---|---|
| TECH | `engineering-database-reliability-engineer` (۵) | مهندس پایداری دیتابیس و backup |
| TECH | `engineering-minimal-change-engineer` (۴)، `engineering-mobile-release-engineer` (۴) | پیاده‌ساز کارگاه کد؛ مهندس انتشار اندروید |
| TECH/PRODUCT | `engineering-i18n-engineer` (۴) | مهندس فارسی‌سازی و RTL (با قاعده‌ی رقم و تک‌قلم هاب) |
| GROWTH | `marketing-seo-specialist` (۴)، `marketing-ai-citation-strategist` و `marketing-aeo-foundations` (۴) | متخصص سئو؛ دیده شدن در جواب موتورهای هوش مصنوعی |
| GROWTH | `marketing-developer-community-builder` (۴)، `marketing-x-twitter-intelligence-analyst` (۴) | مدیر جامعه‌ی تلگرام؛ پایش شبکه‌های اجتماعی |
| GROWTH | `marketing-email-strategist` (۴) | چرخه‌ی عمر و ایمیل (قوی در رضایت کاربر) |
| SALES | `sales-pipeline-analyst` (۳) | تحلیل‌گر قیف رفرال و درآمد |
| PRODUCT | `product-manager` (۴)، `specialized-pricing-analyst` (۳) | مدیر محصول؛ قیمت‌گذاری VIP (بدون ترفندهای فریب) |
| FIN | `finance-bookkeeper-controller` (۴)، `finance-fpa-analyst` (۴)، `engineering-finops-engineer` (۴) | دفترداری و بستن ماه؛ بودجه و پیش‌بینی؛ هزینه‌ی هتزنر و خزانه‌ی توکن |
| QUANT | `specialized-model-qa` (۵)، `academic-statistician` (۵)، `research-synthesist` (۵) | اعتبارسنج مدل سیگنال (calibration، drift)؛ آماردان بک‌تست؛ پژوهش بازار با شاهد |
| AIOPS | `automation-governance-architect` (۵)، `engineering-prompt-engineer` (۴) | دروازه‌بان اتوماسیون n8n («اول قاعده»)؛ مهندس منشور و prompt با تست |
| SECURITY | `security-ai-generated-code-auditor` (۵)، `security-secrets-credential-engineer` (۵)، `security-appsec-engineer` (۴) | بازبین امنیت کد؛ کشف نشت رمز (فقط کشف و پیشنهاد)؛ امنیت اپ |
| DESIGN | `design-ui-finish-gate-reviewer` (۴)، `testing-accessibility-auditor` (۴) | بازبین پایان UI؛ ممیز دسترس‌پذیری |
| HQ | `project-management-meeting-notes-specialist` (۴)، `specialized-codebase-archaeologist` (۴) | منشی جلسه؛ کمک به بازرس |

دو چیز غیر از پرسوناها هم ارزش دارد. هر دو از نو نوشته میشوند:
- **روش تشخیص متن تکراری** (`scripts/check-agent-originality.sh:59-147`، هم‌پوشانی ۸کلمه‌ای): یک چک قاعده‌ای برای مهارت، منشور و درس تازه، پیش از بازبینی ناظر. tokenizer آن فارسی را دور میریزد و باید از نو نوشته شود.
- **ساختار post-mortem** (`strategy/runbooks/scenario-incident-response.md:149-183`، `strategy/coordination/handoff-templates.md:299-343`): مهارت SRE و ارزیابی آکادمی. منشور `sre` امروز روشی برای آن ندارد.

## ۳. هرگز برداشته نمیشود
- `scripts/install.sh`، `scripts/convert.sh`، همه‌ی `integrations/*`، `apps/desktop`، `scripts/i18n/localize-agents-zh.ps1`، `scripts/publish-beta-owner.sh`، `scripts/translate-readme.mjs` (فراخوانی پولی OpenAI بیرون از LLM Router) و ورک‌فلوها.
- **پرسوناهایی که خودسرانه عمل میکنند یا پول جابه‌جا میکنند:**
  - `marketing-carousel-growth-engine` («Zero Confirmation»، انتشار با اعتبار محیط)
  - `agents-orchestrator`
  - `accounts-payable-agent` (پرداخت = A4)
  - `engineering-autonomous-optimization-architect`
  - هر هفت فایل `paid-media` (که به خودشان `Bash` میدهند)
- **پرسوناهای اسپم، فریب و ضعیف:** `marketing-growth-hacker`، `marketing-content-creator`، `marketing-reddit-community-builder`، `marketing-livestream-commerce-coach`، `product-behavioral-nudge-engine`، `sales-offer-lead-gen-strategist`.
- **حوزه‌های بی‌ربط:** حدود ۱۱۰ فایل، مثل بازی، GIS، پزشکی، حقوقی و بازارهای چین.

## ۴. چطور برداشته میشود (اگر مالک تأیید کند)
1. هر منشور تازه **از صفر** در قالب هاب نوشته میشود:
   - frontmatter `tools`، `limits` و `model`
   - مقدمه‌ی `_common.md`
   - هر کار بیرونی فقط با `propose` (A3)
   - شاهد برای هر ادعا
2. از منبع فقط **روش، چک‌لیست و قالب خروجی** گرفته میشود. **هیچ عدد هدف، سابقه‌ی ساختگی، لینک فروشنده، دستور شل یا بند خودمختاری نمیآید.**
3. قوانین هاب به هر منشور اضافه میشود: فارسی و لحن برند، رقم لاتین برای عدد بازار، هشدار ریسک، و چهار خط قرمز اساسنامه.
4. منشورها اول در `agents/staged/hiring/` میمانند و بارگذاری نمیشوند.
5. هر کدام از بازبینی ناظر (`skill.review` با متن کامل، §۱۸.۱۵) و ارزیابی آکادمی رد میشود، بعد با مُهر مالک فعال میشود.
6. حذف یا تغییر: فقط فایل‌های همان منشور. هیچ کد، اسکریپت یا ابزاری از این ریپو وارد هاب نمیشود.
