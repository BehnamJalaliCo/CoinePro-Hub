# HQ Core API v1 — قرارداد هسته

> **مالک سند:** Claude سشن مشورت. **پیاده‌سازی:** `apps/api/` (پرامپت ۴).
> **مبنا:** `docs/OPERATING_MODEL.md` (§۰ تا §۱.۱۶) و طراحی D1. هر جا این سند با مدل عملیاتی نخواند، مدل عملیاتی درست است و تفاوت باید گزارش شود.
>
> بدنه‌ی فنی به انگلیسی است تا نام فیلدها و رفتارها دقیق و بی‌ابهام باشد.

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
| Concurrency | Mutable resources carry `version` (int). PATCH requires `If-Match: <version>`; mismatch → `409 version_conflict`. |
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
| POST | `/auth/passkey/login/options` | — | WebAuthn request options |
| POST | `/auth/passkey/login/verify` | assertion | `{session}` (+ cookie on web) |
| POST | `/auth/step-up/options` | `{action, target}` | request options |
| POST | `/auth/step-up/verify` | assertion | `{step_up_token, expires_at}` |
| GET | `/auth/session` | — | `{principal, device, expires_at}` |
| POST | `/auth/logout` | — | 204 |
| GET | `/auth/devices` | — | list of passkeys and sessions |
| POST | `/auth/devices/{id}/revoke` 🔏 | — | 204 (revocation is a state, the row stays) |

`device`: `{id, name, kind: "passkey"|"session", created_at, last_used_at, revoked_at?}`.
WebAuthn relying party: `HQ_WEBAUTHN_RP_ID` (the domain) and `HQ_PUBLIC_ORIGIN`. **Without a domain and HTTPS, login is disabled** and the endpoints answer `503 origin_not_configured`.

---

## 3. Organisation

### 3.1 Company
```
Company {
  id, code: "TY", kind: "holding"|"company",
  name_fa, name_en, color_index: 1..10 (D1 company palette; wraps for >10),
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
| GET | `/companies` | `?status&q` — holding first, then by code. Designed for 40+ rows. |
| GET | `/companies/{code}` | |
| POST | `/companies` 🔏 | `{code, name_fa, name_en, color_index?, template}` → creates departments and leadership positions **from the template file**, all in one transaction. |
| PATCH | `/companies/{code}` | `name_*`, `color_index`, `status` (`archived` only with 🔏). Code never changes. |
| GET | `/templates` | available company templates (from `seed/templates/*.yaml`). |

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
- Recurring work needs an escrow. Created by the owner → active immediately. Created by an agent → a decision `recurring_approval` that the owner **or that company's CEO** may approve, within the company's quota (§1.4).
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

**Authority is policy, not code:** the "who may approve" column lives in OPA (`policy/decisions.rego`) and is tested.

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

`GET /stream` — Server-Sent Events. `?topics=work,decisions,deliverables,messages,notifications,activity,llm,control&company=TY` (repeatable).
- Envelope: `event: <type>` and `data: {id, type, at, company, ref, data}`; `id:` is the JetStream sequence so `Last-Event-ID` resumes without loss.
- Types: `work.created|updated|delegated|completed`, `decision.created|decided`, `deliverable.created|rated`, `message.created`, `notification.created`, `presence.changed`, `control.changed`, `employee.updated`, `activity.changed` (runtime), `llm.call.started|finished` (from llm-router, metadata only), `budget.alert`.
- Backed by NATS JetStream subjects `hq.core.<company>.<type>`; the API is a filtered, tenant-checked bridge. Heartbeat comment every 15 s.
- Scales to 40+ companies: the client subscribes to the holding summary (`company=*` returns only counters and `activity.changed`, never full payloads).

---

## 8. Audit

```
AuditEntry { seq: bigint, at, actor: Actor, principal_kind, company|null,
             action: "decision.approve"|..., action_class: "A0".."A4",
             target: {kind, ref}, request_id, ip_hash|null, step_up: bool,
             summary, prev_hash, hash }
```
- **Append-only:** the API role has INSERT and SELECT only; a trigger rejects UPDATE and DELETE for everyone.
- **Hash chain:** `hash = sha256(prev_hash || canonical_json(entry_without_hash))`. A nightly job verifies the chain and raises `urgent` if broken.
- Bodies of messages and secrets are never copied into audit; only references.

| GET `/audit` `?company&actor&action&action_class&from&to` | GET `/audit/verify` → `{ok, checked, first_bad_seq|null, verified_at}` |
|---|---|

---

## 9. Control

| Method | Path | Notes |
|---|---|---|
| GET | `/control/state` | kill switches and deploy freezes for the holding and every company |
| POST | `/control/kill-switch` | `{scope: "holding"\|"company:TY", state: "engaged"\|"released", reason}`. **Engage needs no step-up** (speed matters); **release is 🔏**. A CEO (agent) may engage or release only its own company (internal API). |
| POST | `/control/deploy-freeze` | internal/owner: `{company, until, reason}` (§1.5 #5) |

Engaged holding kill switch: the router refuses every call except P0, the worker pauses every agent workflow, and the stream shows it everywhere.

---

## 10. Token Treasury (read side of `llm.*`)

| Method | Path | Notes |
|---|---|---|
| GET | `/treasury/summary` | `?period=day\|month&company` → totals (input, output, cache read/write, thinking tokens; `cost_usd`, `equiv_cost_usd`), budget use % with 70/90/100 thresholds, top 5 consumers |
| GET | `/treasury/breakdown` | `?by=company\|department\|actor\|model\|connection\|task_class\|priority&from&to&company` |
| GET | `/treasury/calls` | metadata only, paged; never prompt or response text |
| GET | `/treasury/what-if` | `?from&to&company&model=` → "what would this have cost on model X" from our price table (design list #22) |
| GET | `/connections` | registry without secrets |
| PATCH | `/connections/{id}` 🔏 | `status`, `display_name`, price table (each price with `source_url` and `as_of`) |
| POST | `/connections/{id}/secret` 🔏 | `{secret}` **write-only** → stored in OpenBao; response never contains it; audit records only that it changed |
| GET/PUT | `/assignments` (PUT 🔏) | holding → company → department → role → task class, with inheritance shown resolved |
| GET/PUT | `/budgets` (PUT 🔏) | per scope and period |

**Cost source:** `equiv_cost_usd` and `cost_usd` come **from our price table** in `llm.connections`. The SDK's own figure is stored in `meta.sdk_cost_usd` for comparison only.

---

## 11. Health and meta
`GET /health` (no auth; `{status}` only) · `GET /meta` (auth; versions, enabled channels, whether login is configured).

---

## 12. Internal API for the agent runtime (`/internal/v1`, not public)

Used by the agent runtime in prompt 5 and by tests now (with a fake agent principal). Every call is checked against the agent's company, department and role, and against OPA.

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

---

## 13. Events on NATS (for other services)
`hq.core.<company>.<type>` with the same envelope as §7. Metadata only, no message bodies, no secrets. JetStream stream `HQ_CORE`, retention 30 days.

---

## 14. Error codes (stable)
`unauthenticated`, `forbidden`, `csrf_rejected`, `step_up_required`, `step_up_invalid`, `origin_not_configured`,
`not_found`, `version_conflict`, `idempotency_conflict`, `validation_failed`, `evidence_required`,
`delegation_depth_exceeded`, `budget_exceeded`, `company_locked`, `decision_not_pending`, `policy_denied`,
`rate_limited`, `channel_not_configured`, `internal_error`.

---

## 15. Seeds (data files, not code)
- `seed/templates/standard.yaml` — the 8 departments with codes, Persian and English names and manager titles; leadership positions (CEO, 8 managers).
- `seed/templates/holding.yaml` — `OVS`, `AIOPS`, the advisor `HQ-ADV`.
- `seed/companies.yaml` already exists in llm-router; v1 extends rows (`name_fa`, `color_index`, `template`) without changing codes.
- Seeds are idempotent and never overwrite rows edited later.
