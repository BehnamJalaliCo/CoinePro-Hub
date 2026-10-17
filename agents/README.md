# agents/ — منشور نقش‌ها (مال Claude سشن مشورت)

> هر نقش ایجنت یک **منشور نسخه‌دار** دارد: یک فایل Markdown با frontmatter YAML. موتور اجرای ایجنت‌ها (پرامپت ۵) این فایل‌ها را میخواند و system prompt هر اجرا را از آن‌ها میسازد. **کد سرور منشور نمینویسد؛ فقط میخواند.** تغییر منشور = commit تازه با `version` بالاتر، و هر اجرا نسخه‌ی منشوری را که با آن اجرا شده در ledger ثبت میکند.
>
> این پوشه طبق `CLAUDE.md` (قانون ۱۱، تصمیم مالک ۲۰۲۶-۱۰-۱۷) مال Claude سشن مشورت است. متن منشورها برای مدل به انگلیسی است تا دقیق باشد؛ هر چیزی که مالک میخواند فارسی است.

## ساختار
```
agents/
  roles/_common.md        قواعد مشترک همه‌ی نقش‌ها (اول هر system prompt): تقدم، پرسش رسمی، اینترنت
  roles/<role>.md         منشور هر نقش (از جمله overseer ناظر کل، advisor مشاور کل، assistant دستیار شخصی)
  tools.md                فهرست ابزارهای دروازه (نام، کلاس، ورودی)؛ مرجع منشورها. v2: اینترنت، MCP، نظارت، ستاره، آکادمی
  protocols/oversight.yaml دفتر پروتکل‌های ناظر کل (بذر جدول oversight.protocols)
  skills/SK-NNN-*/SKILL.md کتابخانه‌ی مهارت (بذر؛ نسخه‌های بعدی در اپ با مُهر مالک)
  academy/                 برنامه‌ی آموزشی نقش‌ها و آزمون‌های طلایی (EV-…)
```

## frontmatter هر منشور
| کلید | معنی |
|---|---|
| `role` | شناسه‌ی نقش (`ceo`، `cto`، `sre`، …). با `employees.role` یکی است. |
| `title_fa`, `title_en` | عنوان نمایشی |
| `kind` | `ceo` · `manager` · `employee` · `advisor` · `inspector` · `overseer` · `assistant` |
| `scope` | `company` (برای هر شرکت جدا) یا `holding` |
| `department` | کد دپارتمان یا `null` |
| `model`, `effort` | پیش‌فرض؛ تخصیص در `llm.assignments` (ارث‌بری §۱.۱۳) بر این غلبه میکند |
| `priority` | اولویت صف مدل برای کارهای عادی این نقش (`P0`..`P4`) |
| `tools` | ابزارهای مجاز از `tools.md`. هر چیز دیگری در دروازه رد میشود. |
| `limits` | `steps_per_run`، `tokens_per_step`، `tokens_per_run` |
| `version` | عدد صحیح؛ فقط بالا میرود |

## متغیرهای قالب
موتور این‌ها را پیش از ارسال جایگزین میکند: `{{employee_code}}`، `{{employee_title_fa}}`، `{{company_code}}`، `{{company_name_fa}}`، `{{company_name_en}}`، `{{holding_code}}`، `{{department_code}}`، `{{department_name_fa}}`، `{{manager_code}}`، `{{today_jalali}}`، `{{today_gregorian}}`، `{{owner_timezone}}`.
