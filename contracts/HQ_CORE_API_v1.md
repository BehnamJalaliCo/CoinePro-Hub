# HQ Core API v1 — قرارداد هسته

> **مالک سند:** Claude سشن مشورت. **پیاده‌سازی:** `apps/api/` (پرامپت ۴).
> **مبنا:** `docs/OPERATING_MODEL.md` (§۰ تا §۱.۱۶) و طراحی D1. هر جا این سند با مدل عملیاتی نخواند، مدل عملیاتی درست است و تفاوت باید گزارش شود.
>
> بدنه‌ی فنی به انگلیسی است تا نام فیلدها و رفتارها دقیق و بی‌ابهام باشد.
>
> **v1.1 (۲۰۲۶-۱۰-۱۷):** «Contract notes» گزارش پرامپت ۴ و نتیجه‌ی بازبینی وارد شد. تغییرها با ⟨1.1⟩ علامت خورده‌اند؛ آن‌هایی که هنوز پیاده نشده‌اند در `docs/server-prompts/PROMPT_04_1_HARDENING.md` هستند.
>
> **v1.2 (۲۰۲۶-۱۰-۱۷):** ایجنت‌ها سر کار (§۱۶، پرامپت ۵). **v1.3 (۲۰۲۶-۱۰-۱۷):** عکس و فیلم و صوت در پیام‌ها، تبدیل دقیق صدای فارسی به متن، کارگاه کد و فرمان صوتی (§۱۷، پرامپت ۶). **v1.4 (۲۰۲۶-۱۰-۱۷):** تصمیم‌های دور دوم مالک: ناظر کل، مشاور نسخه‌ی ۲، دستیار شخصی، ستاره‌ها، مهارت‌ها، آکادمی، اینترنت کامل و MCP برای ایجنت‌ها، تأسیس شرکت و ساخت سرور، backup ساعتی (§۱۸، پرامپت‌های ۷ تا ۹). **v1.4.1 (۲۰۲۶-۱۰-۱۷):** آنچه پرامپت ۵ واقعاً ساخت و نتیجه‌ی بازبینی آن (§۱۶.۶)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_05_1_FIXES.md`. **v1.4.2 (۲۰۲۶-۱۰-۱۷):** استخدام با شروع خود مالک (§۱۸.۱۱). **v1.4.3 (۲۰۲۶-۱۰-۱۷):** مدیرعامل‌ها با اختیار کامل در پاکت بودجه‌ی ماهانه استخدام میکنند و مدل هر کار را خودشان انتخاب میکنند (§۱۸.۱۱)؛ استوری شرکت‌ها (§۱۸.۱۲)؛ ستاره برای مصرف درست بودجه (§۱۸.۴). **v1.4.4 (۲۰۲۶-۱۰-۱۷):** پروتکل‌هایی که قابلیتشان هنوز ساخته نشده `paused` میمانند و نظارت سهم توکن خودش را دارد (§۱۸.۱)؛ ممیزی دوم در `docs/GAP_ANALYSIS_v2.md`. **v1.4.5 (۲۰۲۶-۱۰-۱۸):** آنچه پرامپت ۷ واقعاً ساخت و نتیجه‌ی بازبینی آن (§۱۸.۱۳)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_07_1_FIXES.md`. **v1.4.6 (۲۰۲۶-۱۰-۱۹):** نشان و مُهر هر شرکت از PNG خود مالک ساخته میشود و داده است (§۱۸.۱۴، پرامپت ۹.۱). **v1.4.7 (۲۰۲۶-۱۰-۲۲):** آنچه پرامپت ۸ ساخت و نتیجه‌ی بازبینی آن (§۱۸.۱۵)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_08_1_FIXES.md`. **v1.6 (۲۰۲۶-۱۰-۲۲):** دپارتمان رسانه و طراحی در هر شرکت با برنامه‌ی انتشار مُهرشده، صدای متن‌باز روی هاب، و مشاور حقوقی هلدینگ با مکاتبه‌ی ایمیلی (§۲۲، پرامپت ۱۳). **v1.5 (۲۰۲۶-۱۰-۱۸):** درآمد و پشتیبانی: رادار درآمد، قیف و نجات رفرال، میز پشتیبانی با حالت آموزش و آزمون سایه، قالب‌ها و قاعده‌های چرخه‌ی عمر، NPS، صندوق بازخورد، نگهبان خروجی (§۱۹، پرامپت ۱۰)؛ حاکمیت: اتاق جلسه، اساسنامه، دانشنامه‌ی چهارلایه، سه کارت و کارت امتیاز، OKR، بازبینی نتیجه‌ی تصمیم، ماتریس اختیار، دفتر ریسک، تقویم تغییرات، مُهر گروهی (§۲۰، پرامپت ۱۱)؛ ابزار مدیریت: مشاور پریمیوم، «از هاب بپرس»، گزارش صوتی، ارزیابی ماهانه، هدررفت، ROI، پیش‌بینی مدیر کل دیجیتال، MCP کانتینری، و ChatGPT و Gemini به‌عنوان «بازیکن ذخیره» (§۲۱، پرامپت ۱۲).

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
| GET | `/work` | `?company&department&assignee&status&kind&priority&due_from&due_to&parent&q&overdue` |
| GET | `/work/{id}` | includes `chain`: the delegation path with time, assignee and usage of each step (§D-13 of the design list) |
| GET | `/work/{id}/events` | timeline |
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
| POST | `/control/deploy-freeze` | internal/owner: `{company, until, reason}` (§1.5 #5). ⟨1.1⟩ Freezes are lifted by authority too: the owner's only by the owner; the pipeline's by the pipeline or the owner; a CEO only its own. |

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
                 auto_send: "kb_verbatim"|"kb_grounded"|"off" }                  // what may leave without the owner
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
| POST | `/support/conversations/{ref}/teach` | owner: `{message_id?, answer_md, generalise: bool}` → sends the answer (if the conversation waits) and opens a `KbArticle` proposal from it · `Idempotency-Key` (required) |
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
  `support_go_live` (company, channel, `auto_send`, `verbatim_threshold`, `grounded_threshold`, the `ShadowReport`). All are sealed with step-up
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

## 22. v1.6 — the media studio and the legal counsel (prompt 13)

> **v1.6 (2026-10-22).** The owner's decisions of 2026-10-22: every company gets a **media department** that makes its posts, stories and
> reels every day by itself (scriptwriter, director, motion graphics written by Opus 5.5, a voice made on the hub, images from the
> substitute players), redesigns its sites' UI, and publishes **through series the owner seals once**; and the holding gets **one legal
> counsel** for all companies, who handles platform restrictions, appeals and correspondence by email. The owner no longer has to do this
> work by hand in Claude. Everything above still holds: A3 needs the owner's seal (here, once per series or per email), A4 never happens.

### 22.0 Principles ⟨1.6⟩
- **A department knows its own team.** A department in a template carries a **team blueprint**; its manager hires from it as the work needs
  (§18.11), and the owner never has to define the roles again.
- **Media is made by code where code can, and by models only where it must.** The schedule, the checks, the rendering, the captions, the
  Persian text on images and the publishing are code. Models write the script, the direction and the motion-graphics composition.
- **Publishing only through official APIs** (Telegram Bot API, Instagram Graph API for business accounts), never through a browser session
  or cookies. What an official API cannot publish (a Telegram channel story) becomes a card with the file for the owner to post.
- **The seal is on the series, not on every post.** A sealed series publishes an item automatically only when every check passed; anything
  outside the series, or any failed check, is a card.
- **Every outgoing email of the counsel is the owner's seal**, on the exact message.
- New **task classes**: `media_script`, `media_direction`, `media_motion`, `media_review`, `ui_design`, `legal_case`, `legal_email`.

### 22.1 Department blueprints ⟨1.6⟩
```
Department { …§3.2, team: [{role, title_fa, why_fa, first: bool}] }    // from the template; `first` = the first hires a new company makes
```
- `GET /templates` and `company.state` return each department's `team`. A manager proposes hires from it when the work needs them; the CEO
  decides inside the envelope (§18.11). A role in `team` is always an existing `employee` charter.
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

### 22.5 Kinds, stream, step-up, codes ⟨1.6⟩
- **Decision kinds:** `media_series`, `media_publish`, `email_send` (all sealed with step-up, §5.1).
- **Step-up targets:** `media.series` (series digest), `media.unpublish` (ref), and `decision.approve` on `email_send` bound to the message
  digest.
- **Stream topics:** `media` (`media.item`), `legal` (`legal.case`).
- **`Thread.kind`** gains `legal` (code `L`).
- **Error codes:** `series_not_sealed` (409, an item asked to auto-publish outside a sealed series), `platform_limit` (429 with
  `Retry-After`, the platform's own publishing limit).
