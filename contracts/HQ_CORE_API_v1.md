# HQ Core API v1 — قرارداد هسته

> **مالک سند:** Claude سشن مشورت. **پیاده‌سازی:** `apps/api/` (پرامپت ۴).
> **مبنا:** `docs/OPERATING_MODEL.md` (§۰ تا §۱.۱۶) و طراحی D1. هر جا این سند با مدل عملیاتی نخواند، مدل عملیاتی درست است و تفاوت باید گزارش شود.
>
> بدنه‌ی فنی به انگلیسی است تا نام فیلدها و رفتارها دقیق و بی‌ابهام باشد.
>
> **v1.1 (۲۰۲۶-۱۰-۱۷):** «Contract notes» گزارش پرامپت ۴ و نتیجه‌ی بازبینی وارد شد. تغییرها با ⟨1.1⟩ علامت خورده‌اند؛ آن‌هایی که هنوز پیاده نشده‌اند در `docs/server-prompts/PROMPT_04_1_HARDENING.md` هستند.
>
> **v1.2 (۲۰۲۶-۱۰-۱۷):** ایجنت‌ها سر کار (§۱۶، پرامپت ۵). **v1.3 (۲۰۲۶-۱۰-۱۷):** عکس و فیلم و صوت در پیام‌ها، تبدیل دقیق صدای فارسی به متن، کارگاه کد و فرمان صوتی (§۱۷، پرامپت ۶). **v1.4 (۲۰۲۶-۱۰-۱۷):** تصمیم‌های دور دوم مالک: ناظر کل، مشاور نسخه‌ی ۲، دستیار شخصی، ستاره‌ها، مهارت‌ها، آکادمی، اینترنت کامل و MCP برای ایجنت‌ها، تأسیس شرکت و ساخت سرور، backup ساعتی (§۱۸، پرامپت‌های ۷ تا ۹). **v1.4.1 (۲۰۲۶-۱۰-۱۷):** آنچه پرامپت ۵ واقعاً ساخت و نتیجه‌ی بازبینی آن (§۱۶.۶)؛ اصلاح‌ها در `docs/server-prompts/PROMPT_05_1_FIXES.md`. **v1.4.2 (۲۰۲۶-۱۰-۱۷):** استخدام با شروع خود مالک (§۱۸.۱۱).

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
  hired_at, dismissed_at|null, hired_by_decision: "D-000123"|null,
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
  digital_ceo_prediction: { verdict: "approve"|"reject", confidence }|null,   // shown only when §1.8 enables it
  version, created_at
}
```
| kind | payload | who may approve |
|---|---|---|
| `hire` | `{company, department, title_fa, title_en, reason, duties[], model, effort, permissions[], quota_estimate_month}` | owner |
| `dismissal` | `{employee, reason, transfer_to?}` | owner |
| `recurring_approval` | `{work_id, escrow, schedule}` | owner, or the company's CEO within quota |
| `deploy` | `{repo, pr_url, diff_stat, ci: {status, url}, tests: {passed, failed}, rollout}` | owner only (A3) |
| `a3_action` | `{action, target, preview}` (publish, customer message, restart, price change) | owner; a post already in the approved content calendar may be approved by the CEO (§1.12) |
| `proposal` | `{okr, cost, risk, expected_impact, options[]}` (CEO growth proposals, batched) | owner |
| `budget_change` | `{scope, period, token_limit?, usd_limit?}` | owner |
| `evaluation` | `{employee, recommendation: "promote"\|"demote"\|"dismiss", evidence}` (monthly HR) | owner |

**Authority is policy, not code:** the "who may approve" column lives in OPA (`policy/decisions.rego`) and is tested. ⟨1.1⟩ The proposer is part of the policy input; **proposer = approver is always denied.** `budget_change.scope` must lie inside the proposer's company (owner proposals excepted).

⟨1.1⟩ **A decided decision is sealed:** `status`, `decided_*`, `seal`, `note` and `amendments` are written once, in the decision's own transaction, and never change afterwards. **Owner amendments are applied:** the effect uses the amended payload, and the response returns `amendments` next to the original `payload`.

⟨1.1⟩ `a3_action` of kind publish can be approved by a CEO only once the content calendar exists (a later version); until then it is owner only.

| Method | Path | Notes |
|---|---|---|
| GET | `/decisions` | `?status&company&kind&risk&q` — default `status=pending`, oldest first |
| GET | `/decisions/{ref}` | |
| POST | `/decisions/{ref}/approve` | 🔏 for `A3`, `hire`, `dismissal`, `budget_change`; `{note?, amendments?}` → resolution created |
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

`GET /stream` — Server-Sent Events. `?topics=work,decisions,deliverables,messages,notifications,activity,llm,control,runs&company=TY` (repeatable; ⟨1.4.1⟩ `runs` carries `run.*`).
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
| POST | `/transcribe` | Owner only. Raw audio body (types and limits as §17.1 audio). `?purpose=message\|order\|note`. → `{ text, language: "fa", duration_s, confidence: 0..1, segments: [{start_s, end_s, text}], file_id, engine: {name, model, version} }` |

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
              runtime: "managed"|"self_hosted", model, effort,
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
2. **Credentials never enter the sandbox.** The GitHub credential is per workspace, fine-grained (contents and pull requests on that one
   repository), kept by the hub (or the managed runtime's vault, substituted at egress), never printed, never shown to a model.
3. Each session runs in **its own sandbox** with a fresh clone, no access to the hub's network or other sessions, outbound limited to GitHub and
   package registries. A session's CLAUDE.md is the repository's own; the repository's rules bind the session.
4. **Budget:** every session has a USD cap from its grant; at the cap it stops and asks. Usage enters the Token Treasury like every call.
5. **Kill switch and deploy freeze:** engaging either for the workspace's company pauses its sessions.
6. **Work lock** (OPERATING_MODEL §1.5): one writing session per repository area at a time; others queue.
7. **Everything is recorded:** events carry summaries and metadata; the full session transcript is stored in object storage, owner-readable,
   retained with the audit set.

**Runtime.** `managed` = Claude Managed Agents (Anthropic hosts the loop and a per-session container; its permission policy `always_ask` for
pushes and PRs maps to `approval_request`; the GitHub credential lives in its vault). `self_hosted` = the Claude Agent SDK in disposable
containers on a separate builder host. The contract is the same for both; the choice is an owner decision recorded in prompt 6.

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
- `GET /meta` gains `workshop: { runtime: "managed"|"self_hosted"|null }` — `null` until the owner chooses (then `POST /workshop/sessions`
  answers `503 runtime_not_configured`), so the apps can say so before the owner tries.

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
             version, sealed_at|null, last_run: { at, result: "pass"|"fail"|"partial", findings: int }|null }
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
             companies: [{company, stars: 0..5, score: 0..100, parts: {kpi, challenges, compliance, people}, rank, trend: [0..100]}],
             employees: [{code, company, title_fa, stars: 0..5, count, rank_company, rank_holding, trend: [0..5]}],
             lessons: [L-…] }
Lesson     { id, ref: "L-0001", source_company, period, title_fa, body_md, evidence, adoption: [{company, status: "proposed"|"adopted"|"rejected", decision_ref}] }
```
| GET | `/stars/rubrics` · `/stars/rubrics/{company}` | CEOs write them (internal `star.rubric`); the owner reads |
| GET | `/stars` | `?company&week&employee` |
| GET | `/stars/rollup` | `?period=week\|month&key` (default: the last closed period) |
| GET | `/lessons` | `?company&period` |
- Week = Saturday to Friday, owner TZ; the roll-up runs **Saturday 08:00 Tehran**, the month on the 1st (Jalali month).
- **Company score** = 40% KPI attainment + 25% overseer challenges + 20% compliance + 15% people (employees' stars); **company stars** = score ÷ 20.
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
EvalSuite  { ref: "EV-001", role, title_fa, cases: [{id, input_md, rubric_md, weight}], baseline: {subject, version, score} }
EvalRun    { id, suite, subject: {kind: "charter"|"skill"|"model", ref, version}, score: 0..100, passed: bool, cases: [{id, score, notes}], at }
Teaching   { id, ref: "TE-0001", target: {kind: "role"|"employee", ref}, source: "voice"|"text", text_md, file_id|null,
             proposal: {kind: "charter_rule"|"skill"|"memory"|"playbook", diff_md}|null, eval_run|null,
             status: "drafting"|"proposed"|"approved"|"rejected", created_at }
TrainingRecord { employee, charter_version, curriculum_version, skills: [ref@version], evals: [{suite, score, at}], lessons: [L-…], trend: [0..100] }
```
| GET | `/academy/curricula` · `/academy/curricula/{role}` | |
| GET | `/academy/evals` · `/academy/evals/{ref}/runs` | |
| GET · POST | `/academy/teach` | POST `{target, text, source, file_id?}`; the AI Ops head drafts, the overseer reviews, an eval runs |
| POST | `/academy/teach/{ref}/approve` 🔏 · `/reject` | target = ref |
| GET | `/academy/records/{employee}` | |
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
             decision_ref|null, plan|null, company|null, created_at, updated_at }
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
- **Decision kinds** added: `protocol`, `tool_enable`, `errand_action`, `company_found`, `server_plan`, `lesson_adoption`.
- **Stream types** (topics): `oversight.finding`, `oversight.hold`, `oversight.watch` (`oversight`) · `inquiry.answered` (`inquiries`) ·
  `errand.updated` (`errands`) · `stars.rollup` (`stars`) · `skill.updated` (`skills`) · `academy.eval` (`academy`) ·
  `founding.updated`, `provision.step` (`founding`) · `backup.done`, `backup.failed` (`backups`).
- **Step-up targets:** `oversight.protocol` (body hash), `oversight.order` (ref), `oversight.release` (ref), `skill.activate` (`ref@version`),
  `academy.approve` (ref), `mcp.add` (body hash), `mcp.enable` (key), `provision.seal` (the plan's `digest`), `founding.activate` (ref).

### 18.11 Hiring starts with the owner ⟨1.4.2⟩
Owner decision, 2026-10-17: no hire now. When the owner brings the hub up for real work, the owner either hires from zero personally or asks the CEOs to propose their teams at that moment. Until then nobody proposes a hire.
```
Hiring { state: "closed"|"open", mode: "self"|"proposals"|null, changed_at|null, changed_by: Actor|null,
         withdrawn: ["D-000001", …] }     // hire cards the system withdrew when hiring closed
```
| Method | Path | Notes |
|---|---|---|
| GET | `/owner/hiring` | the state above; `closed` by default |
| POST | `/owner/hiring/start` 🔏 | `{mode: "proposals"|"self"}` · step-up `hiring.start`, target `holding`. `proposals`: hiring opens to agents and each CEO (and each holding head with a hiring duty) gets **one** work item, "propose your first month's team", at its normal priority. `self`: hiring stays closed to agents; the owner hires directly |
| POST | `/owner/hiring/close` | no step-up (closing is always safe); pending agent hire cards are withdrawn |
| POST | `/org/hires` 🔏 | owner only · `{company, department, role, title_fa, title_en?, model?, effort?, reports_to?, quota_estimate_month?}` · step-up `hire.direct`, target = SHA-256 of the exact body. Writes a `hire` decision proposed **and sealed by the owner** in one transaction (status `approved`, resolution `M-…`), then the employee; the same checks as §16.6 (the charter `role` must fit the company and department). `model`/`effort` default to the charter's. → `201 {employee, decision}` |
- While `closed`, an agent's `propose` of kind `hire` is refused before any card exists: `403 hiring_closed` (new stable code, §14). Dismissal, budget and every other kind are unaffected.
- Closing hiring (and the decision itself, 2026-10-17) **withdraws** pending agent hire cards: status `withdrawn`, `decided_by` system, note «مالک: استخدام با شروع خود مالک». Nothing is deleted; the cards stay in history and in `withdrawn`.
- The daily agent token cap stays at 600K until the owner sets it from the first week's outputs (owner decision, 2026-10-17).
- Stream: `hiring.changed` on topic `control`. Step-up targets: `hiring.start` (`holding`), `hire.direct` (body hash).
