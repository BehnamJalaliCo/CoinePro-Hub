# Tool catalog v1 (Tool Gateway)

Agents have **no network and no shell**. A run returns JSON; the agent runtime turns each requested action into a call to the **Tool Gateway**, which checks the role's allow-list, the action class (OPA `hq.actions`), the company's kill switch and deploy freeze, the run's budget, and writes one audit row per call. Results go back to the model **redacted**: no secrets, keys, tokens, customer personal data or raw message bodies of other threads.

Classes (OPERATING_MODEL §1.12): **A0** observe · **A1** propose/draft · **A2** internal & reversible (inside the authority envelope) · **A3** external — never executed by an agent; it becomes a decision for the owner · **A4** forbidden for AI — no such tool exists, and any unknown tool name is denied.

| Tool | Class | Input | What it does |
|---|---|---|---|
| `work.get` | A0 | `{ref}` | One work item with its delegation chain, brief, budget left, evidence and deliverables. Own company only. |
| `company.state` | A0 | `{}` (holding roles: `{company?}`) | Snapshot: departments, active employees, open work by status, pending decisions, kill switch, deploy freeze, budget use %. |
| `health.sites` | A0 | `{company?, since?}` | Latest results of the rule-based site checks (status, latency, TLS days left, consecutive failures) and open incidents. |
| `health.hub` | A0 | `{}` | The hub's own state: services up/down and restarts, disk, memory, certificate days left, last backup age and restore-test result. |
| `treasury.usage` | A0 | `{scope, period}` | Tokens and equivalent cost by company/department/role/model, budget use %, anomalies. |
| `knowledge.search` | A0 | `{q, kinds?}` | Search resolutions, deliverables, decisions and (advisor only) messages the role may read. Returns refs + short snippets. |
| `audit.recent` | A0 | `{company?, action?, since?}` | Recent audit rows (metadata only). Oversight roles and the advisor. |
| `memory.read` | A0 | `{}` | The employee's own memory notes (latest first). |
| `github.read` | A0 | `{repo, what: "commits"\|"issues"\|"pulls"\|"file", path?}` | Read-only GitHub. **Off** until the owner provides a read-only token (`channel_not_configured`). |
| `deliver` | A1 | `{work_ref, title_fa, body_md, evidence: [{kind, ref, note}]}` | Creates a deliverable (output card) for the owner or the requester. |
| `propose` | A1 | `{kind, title_fa, what_md, why_md, risk, reversible, quota_estimate, payload}` | Creates a decision card (contract §5.1 kinds). The only path to anything A3, to hiring, and to recurring work. |
| `message.owner` | A1 | `{body_md, links?}` | A message in the role's own thread with the owner. CEOs, managers and the advisor only. Subject to the CEO attention quota; non-urgent messages wait for the next digest. |
| `message.thread` | A1 | `{thread, body_md, links?}` | Reply in a thread the employee belongs to. |
| `memory.write` | A1 | `{note_md, tags?}` | Append one note to the employee's memory (append-only). |
| `work.accept` · `work.progress` · `work.fail` | A2 | `{ref, note?}` · `{ref, note, pct?}` · `{ref, reason, decline?}` | Own assigned work. |
| `work.delegate` | A2 | `{ref, to, title_fa, brief_md, budget}` | Delegate down one level (depth ≤ 2, child budget ≤ what is left). |
| `work.request` | A2 | `{to, title_fa, brief_md}` | Request to another department's manager, or (CEO only) another company's CEO. |
| `activity.set` | A2 | `{state, note?}` | Live-stream activity of the employee (`working`, `waiting`, `idle`). |
| `notify` | A2 | `{level, category?, title_fa, body_fa, link?}` | Raise a notification. `urgent` only with an incident `category` (service down, security, data loss, budget hard stop), max 5/hour/company. |

The runtime adds `done` (finish the run) implicitly; there is no other way to end a run.
