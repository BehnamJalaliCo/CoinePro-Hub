# infra/opa — سیاست‌های دسترسی (Open Policy Agent)

قاعده‌های «چه کسی چه کاری میتواند بکند» **کد نیستند، سیاست‌اند** (قرارداد `contracts/HQ_CORE_API_v1.md` §۵.۱ و §۱۲، و `docs/OPERATING_MODEL.md` §۱.۴ و §۱.۱۲). API هر درخواست حساس را از OPA میپرسد. اگر OPA در دسترس نباشد، API **fail-closed** است و درخواست را رد میکند (`503 policy_unavailable`).

- **ایمیج:** `openpolicyagent/opa:1.21.1-static` (distroless، کاربر `1000:1000`، بدون shell). نسخه فقط در `IMAGE` ثبت میشود. سلامت: `GET /health` روی پورت `8181`.
- **فایل‌ها:**
  - `policy/*.rego` (Rego v1) و تست‌ها در `policy/*_test.rego`.
  - `policy/authz.rego`: مجوز خود API ‏OPA.
  - `policy/data.json`: جدول‌هایی که داده‌اند، نه کد.
- **اجرا:** `opa run --server --authorization=basic --addr 0.0.0.0:8181 --log-level error --disable-telemetry /policy`. سیاست‌ها و داده **فقط از فایل** بار میشوند.

## مجوز API خود OPA (`system.authz`)
با `--authorization=basic` هر درخواست به OPA اول از `data.system.authz.allow` پرسیده میشود. فقط این‌ها مجازند:
- `POST /v1/data/hq/...`: ارزیابی سیاست‌ها
- `GET /health`

همه‌ی موارد زیر برای **هر کانتینری** با `401` رد میشوند:
- `PUT`، `PATCH` و `DELETE` روی `/v1/policies` و `/v1/data`
- `GET` داده
- API کوئری (`/v1/query`)

این را از یک کانتینر جدا روی شبکه‌ی تست آزموده‌ایم.

## داده (`policy/data.json` ← `data.hq.config`)
```json
{"hq": {"config": {
  "incident_categories": ["service_down", "security", "data_loss", "budget_hard_stop"],
  "propose_department": {"manager": {"evaluation": "HR", "dismissal": "HR"}},
  "a2_grants": {"ceo": ["work.delegate", "work.create", "kill_switch.set", "deploy_freeze.set", "decision.approve",
                        "work.request", "work.accept", "work.progress", "work.fail", "activity.set", "notify"],
                "manager": ["work.delegate", "work.create", "work.request", "work.accept", "work.progress",
                            "work.fail", "activity.set", "notify"],
                "inspector": ["work.delegate", "work.accept", "work.progress", "work.fail", "activity.set", "notify"],
                "employee": ["work.accept", "work.progress", "work.fail", "activity.set", "notify"]}
}}}
```
- `incident_categories`: دسته‌هایی که ایجنت با آن‌ها میتواند 🔴 بفرستد.
- `propose_department`: نوع‌هایی که هر نقش فقط از یک دپارتمان پیشنهاد میدهد (کد HR داده است).
- `a2_grants`: اقدام‌های A2 که هر نقش بدون پاکت اختیار مجاز است. نام‌ها همان نام ابزارهای `agents/tools.md` است (پرامپت ۵)، به‌علاوه‌ی opهای هسته.

اگر این فایل نباشد، هر چیزی که به آن وابسته است **رد** میشود.

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
| `hq.decisions` | `{principal, decision: {kind, company, action_class, payload, proposer: {kind, code}}, context: {within_quota, in_content_calendar}}` | تأیید یا رد یک تصمیم کارتابل. **مالک:** همه‌ی نوع‌ها. **مدیرعامل همان شرکت:** `recurring_approval` فقط با `within_quota`، و `a3_action` فقط وقتی `payload.action == "publish"` و پست در تقویم محتوای تأییدشده است (`in_content_calendar`). بقیه فقط مالک. سرویس‌ها هرگز تصمیم نمیگیرند. `A4` در تصمیم‌ها مجاز نیست. **هیچ‌کس پیشنهاد خودش را تأیید نمیکند** (`own_proposal`)، پس پیشنهاد خود مدیرعامل به مالک میرود. بدون `proposer` هیچ‌کس تصمیم نمیگیرد (`unknown_proposer`). |
| `hq.actions` | `{principal, action: {class, name, company}, context: {escrow_classes, company_locked, incident}}` | **دروازه‌ی هر نوشتن ایجنت.** **مالک:** همه، حتی وقتی شرکت قفل است. **ایجنت:** فقط شرکت خودش. A0 و A1 مجاز. A2 فقط اگر `name` در `a2_grants` نقش باشد یا A2 در پاکت اختیار باشد (`a2_needs_role_or_escrow`). A3 فقط از راه تصمیم (`a3_requires_decision`). **A4 همیشه رد** (`a4_forbidden_for_ai`). **سرویس:** A0 تا A2. قفل شرکت (کلید توقف یا deploy freeze) همه‌ی اقدام‌های غیرمالک از A1 به بالا را رد میکند، **جز** خود کنترل‌ها (`kill_switch.set`، `deploy_freeze.set`) و اعلان حادثه (`notification.raise` با `context.incident`)؛ API مقدار واقعی قفل (`company_locked`) را میفرستد. ایجنت متوقف یا برکنارشده فقط A0. |
| `hq.internal` | `{principal, op, target}` | عملیات `/internal/v1`. هر ایجنت فقط در شرکت، دپارتمان و نقش خودش (جدول پایین). ایجنت متوقف یا برکنارشده فقط `context.read`. |

### عملیات `hq.internal`
| op | چه کسی | `target` |
|---|---|---|
| `context.read`، `activity.set` | خود کارمند؛ سرویس برای هر کارمند | `{employee}` |
| `work.accept`، `work.progress`، `work.deliver`، `work.fail` | فقط مسئول همان کار، در شرکت خودش | `{assignee, company}` |
| `work.delegate` | مسئول فعلی کار. مدیرعامل ← مدیر؛ مدیر ← کارمند **دپارتمان خودش** | `{assignee, company, to_role, to_department}` |
| `work.create` | مدیر ← مدیر **دپارتمان دیگر** همان شرکت، یا پیشنهاد کار **دائمی** در دپارتمان خودش (تا تأیید `recurring_approval` غیرفعال میماند)؛ مدیرعامل ← مدیر همان شرکت، یا ← **مدیرعامل شرکت دیگر** (تنها مسیر بین شرکت‌ها) | `{company, kind, to_role, to_department}` |
| `decision.propose` | ایجنت همان شرکت؛ نوع‌های مجاز هر نقش در `propose_kinds` (بازرس هم `hire` پیشنهاد میدهد). ارزیابی و برکناری فقط از دپارتمانی که `propose_department` میگوید. **`budget_change` فقط داخل شرکت خودش:** `company` همان شرکت؛ `department` با `<CO>-`؛ `role` و `task_class` با `<CO>:`؛ `holding` هرگز (`scope_outside_company`) | `{company, kind, scope: {scope_type, scope_ref}\|null}` |
| `decision.approve` | همان قاعده‌ی `hq.decisions` | `{decision, context}` |
| `message.post` | thread خودش؛ گروه دپارتمان خودش؛ مشاور در thread مشاور؛ مدیرعامل در threadهای `ceo` شرکت خودش | `{thread_code, thread_kind, thread_company, thread_department}` |
| `notification.raise` | ایجنت برای شرکت خودش؛ `urgent` فقط با `category` از `incident_categories` (`urgent_needs_incident`؛ API آن را به `decision` پایین میاورد و دوباره میپرسد). وقتی شرکت قفل است فقط حادثه‌ی `urgent` (`company_locked`؛ اگر `company_locked` نیاید، قفل حساب میشود). سطح نامعتبر ← `unknown_level`. سرویس: همه | `{company, level, category, company_locked}` |
| `kill_switch.set` | فقط مدیرعامل، فقط `company:<شرکت خودش>`. **روشن کردن** آزاد است. **آزاد کردن** فقط اگر یک ایجنت همان شرکت آن را زده باشد (`released_only_by_engager_authority`؛ کلیدی که مالک زده، یا مالک دوباره روشنش کرده و مالکیتش را گرفته، فقط مالک با 🔏 آزاد میکند). آزاد کردن چیزی که آزاد است idempotent است (۲۰۰). کلید هلدینگ برای ایجنت همیشه رد | `{scope, state, current: {state, changed_by_kind, changed_by_code, changed_by_company}}` |
| `deploy_freeze.set` | **گذاشتن:** سرویس برای هر شرکت، مدیرعامل برای شرکت خودش. **برداشتن** (`lift: true`): سرویس فقط توقفی که **همان سرویس** گذاشته (`created_by_code`)؛ مدیرعامل فقط توقفی که خودش گذاشته. توقف مالک فقط با مالک (`lifted_only_by_setter_authority`) | `{company, lift, freeze: {created_by_kind, created_by_code, created_by_company}\|null}` |
| `file.upload` | ایجنت برای شرکت خودش | `{company}` |
| `work.read`، `company.read`، `health.read`، `treasury.read`، `knowledge.read` (پرامپت ۵) | ایجنت در شرکت خودش. نقش‌های `scope: holding` (`principal.scope`: مشاور، بازرس، مدیر AIOPS و کارمندانشان) در هر شرکت. **جستجو در متن پیام‌ها** (`kinds` شامل `messages`) فقط برای مشاور | `{company, kinds?}` |
| `hub.read`، `audit.read` | فقط نقش‌های `scope: holding` | `{}` |
| `memory.read`، `memory.write` | فقط حافظه‌ی خود کارمند | `{employee}` |
| `run.reserve`، `run.record` | فقط اجرای خود کارمند (رزرو سقف ابزار و ردیف audit ‏`tool.call`) | `{employee}` |
| `thread.live` | همان قاعده‌ی `message.post` (پاسخ جریانی در thread خودش) | مثل `message.post` |

دلیل‌های رد (`deny_reasons`) پایدارند:
- عمومی: `unknown_op`، `unknown_principal`، `owner_uses_public_api`، `agent_inactive`، `other_company`، `not_assignee`
- هسته‌ی ۴.۱: `own_proposal`، `unknown_proposer`، `scope_outside_company`، `urgent_needs_incident`، `company_locked`، `unknown_level`، `released_only_by_engager_authority`، `lifted_only_by_setter_authority`، `a2_needs_role_or_escrow`
- بقیه: `<op>_not_permitted`

در `decision.approve` همان دلیل‌های `hq.decisions` برمیگردد (`owner_only`، `ceo_only`، `outside_quota`، `owner_only_action`، `not_in_content_calendar`، `services_never_decide`، `a4_never_in_decisions`، `own_proposal`، ...).

## تست
```bash
scripts/quality/opa.sh     # opa check --strict، opa fmt، opa test، پوشش ۱۰۰٪
```
همین گیت در `make check` و CI اجرا میشود. **پوشش زیر ۱۰۰٪ یعنی شکست**؛ هر قاعده‌ی جدید با تست خودش اضافه میشود.
