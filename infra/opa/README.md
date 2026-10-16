# infra/opa — سیاست‌های دسترسی (Open Policy Agent)

قاعده‌های «چه کسی چه کاری میتواند بکند» **کد نیستند، سیاست‌اند** (قرارداد `contracts/HQ_CORE_API_v1.md` §۵.۱ و §۱۲، و `docs/OPERATING_MODEL.md` §۱.۴ و §۱.۱۲). API هر درخواست حساس را از OPA میپرسد. اگر OPA در دسترس نباشد، API **fail-closed** است و درخواست رد میشود.

- **ایمیج:** `openpolicyagent/opa:1.21.1-static` (distroless، کاربر `1000:1000`، بدون shell). سلامت: `GET /health` روی پورت `8181`.
- **فایل‌ها:** `policy/*.rego` (Rego v1) و تست‌ها در `policy/*_test.rego`.

## قرارداد ورودی و خروجی
API درخواست `POST /v1/data/hq/<package>` را با بدنه‌ی `{"input": ...}` میفرستد و `result.allow` (bool، پیش‌فرض `false`) و `result.deny_reasons` (مجموعه‌ای از رشته‌ها) را میخواند.

**principal** در همه‌ی ورودی‌ها:
```json
{"kind": "owner|agent|service", "code": "owner|TY-CEO|TY-GROWTH-MGR|TY-GROWTH-01|HQ-ADV|<service>",
 "role": "owner|ceo|manager|employee|advisor|inspector|system|service",
 "company": "TY"|null, "department": "GROWTH"|null, "status": "active|paused|dismissed" (اختیاری)}
```
فیلدهای جاافتاده یا با نوع اشتباه همیشه به **رد** میرسند، نه قبول (`policy/lib.rego`).

| package | ورودی | تصمیم |
|---|---|---|
| `hq.decisions` | `{principal, decision: {kind, company, action_class, payload}, context: {within_quota, in_content_calendar}}` | تأیید یا رد یک تصمیم کارتابل. **مالک:** همه‌ی نوع‌ها. **مدیرعامل همان شرکت:** `recurring_approval` فقط با `within_quota`، و `a3_action` فقط وقتی `payload.action == "publish"` و پست در تقویم محتوای تأییدشده است (`in_content_calendar`). بقیه (deploy، تغییر قیمت، پیام گروهی) **فقط مالک**. سرویس‌ها هرگز تصمیم نمیگیرند. `A4` در تصمیم‌ها اصلاً مجاز نیست. |
| `hq.actions` | `{principal, action: {class, name, company}, context: {escrow_classes, company_locked}}` | کلاس‌های A0 تا A4. **مالک:** همه، حتی وقتی شرکت قفل است. **ایجنت:** فقط شرکت خودش؛ A0 و A1؛ A2 فقط داخل پاکت اختیار؛ A3 فقط از راه تصمیم (`a3_requires_decision`)؛ **A4 همیشه رد** (`a4_forbidden_for_ai`). **سرویس:** A0 تا A2. قفل شرکت (کلید توقف یا deploy freeze) همه‌ی اقدام‌های غیر مالک از A1 به بالا را رد میکند. ایجنت متوقف یا برکنارشده فقط A0. |
| `hq.internal` | `{principal, op, target}` | عملیات `/internal/v1`. هر ایجنت فقط در شرکت، دپارتمان و نقش خودش (جدول پایین). ایجنت متوقف یا برکنارشده فقط `context.read`. |

### عملیات `hq.internal`
| op | چه کسی | `target` |
|---|---|---|
| `context.read`، `activity.set` | خود کارمند؛ سرویس برای هر کارمند | `{employee}` |
| `work.accept`، `work.progress`، `work.deliver`، `work.fail` | فقط مسئول همان کار، در شرکت خودش | `{assignee, company}` |
| `work.delegate` | مسئول فعلی کار. مدیرعامل ← مدیر؛ مدیر ← کارمند **دپارتمان خودش** | `{assignee, company, to_role, to_department}` |
| `work.create` | مدیر ← مدیر **دپارتمان دیگر** همان شرکت؛ مدیرعامل ← مدیر همان شرکت، یا ← **مدیرعامل شرکت دیگر** (تنها مسیر بین شرکت‌ها) | `{company, to_role, to_department}` |
| `decision.propose` | ایجنت همان شرکت؛ نوع‌های مجاز هر نقش در `propose_kinds` (ارزیابی و برکناری فقط مدیر HR) | `{company, kind}` |
| `decision.approve` | همان قاعده‌ی `hq.decisions` | `{decision, context}` |
| `message.post` | thread خودش؛ گروه دپارتمان خودش؛ مشاور در thread مشاور؛ مدیرعامل در threadهای `ceo` شرکت خودش | `{thread_code, thread_kind, thread_company, thread_department}` |
| `notification.raise` | ایجنت برای شرکت خودش؛ سرویس برای همه | `{company}` |
| `kill_switch.set` | فقط مدیرعامل، فقط `company:<شرکت خودش>`؛ کلید هلدینگ برای ایجنت همیشه رد | `{scope}` |
| `deploy_freeze.set` | سرویس؛ یا مدیرعامل برای شرکت خودش | `{company}` |
| `file.upload` | ایجنت برای شرکت خودش | `{company}` |

دلیل‌های رد (`deny_reasons`) پایدارند: `unknown_op`، `unknown_principal`، `owner_uses_public_api`، `agent_inactive`، `other_company`، `not_assignee`، و برای بقیه `<op>_not_permitted`. در `decision.approve` همان دلیل‌های `hq.decisions` برمیگردد (`owner_only`، `ceo_only`، `outside_quota`، `owner_only_action`، `not_in_content_calendar`، `services_never_decide`، `a4_never_in_decisions`، ...).

## تست
```bash
scripts/quality/opa.sh     # opa check --strict، opa fmt، opa test، پوشش ۱۰۰٪
```
همین گیت در `make check` و CI اجرا میشود. **پوشش زیر ۱۰۰٪ یعنی شکست**؛ هر قاعده‌ی جدید با تست خودش اضافه میشود.
