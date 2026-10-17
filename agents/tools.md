# Tool catalog v2 (Tool Gateway)

Agents have **no shell and no direct network**; since v2 (owner decision 2026-10-17) the **internet is reached through tools** that run in the egress service. A run returns JSON; the agent runtime turns each requested action into a call to the **Tool Gateway**, which checks the role's allow-list, the action class (OPA `hq.actions`), the company's kill switch and deploy freeze, the run's budget, and writes one audit row per call. Results go back to the model **redacted**: no secrets, keys, tokens, customer personal data or raw message bodies of other threads.

Classes (OPERATING_MODEL §1.12): **A0** observe · **A1** propose/draft · **A2** internal & reversible (inside the authority envelope) · **A3** external — never executed by an agent; it becomes a decision for the owner · **A4** forbidden for AI — no such tool exists, and any unknown tool name is denied.

| Tool | Class | Input | What it does |
|---|---|---|---|
| `work.get` | A0 | `{ref}` | One work item with its delegation chain, brief, budget left, evidence and deliverables. Own company only. |
| `company.state` | A0 | `{}` (holding roles: `{company?}`) | Snapshot: departments, active employees, open work by status, pending decisions, kill switch, deploy freeze, budget use %, hiring (`closed`/`open`, contract §18.11). |
| `health.sites` | A0 | `{company?, since?}` | Latest results of the rule-based site checks (status, latency, TLS days left, consecutive failures) and open incidents. |
| `health.hub` | A0 | `{}` | The hub's own state: services up/down and restarts, disk, memory, certificate days left, last backup age and restore-test result. |
| `treasury.usage` | A0 | `{scope, period}` | Tokens and equivalent cost by company/department/role/model, budget use %, anomalies. |
| `knowledge.search` | A0 | `{q, kinds?}` | Search what the role may read. `kinds`: `resolutions`, `deliverables`, `decisions`, `work`; `messages` for the advisor only. Returns refs + short snippets. |
| `audit.recent` | A0 | `{company?, action?, since?}` | Recent audit rows (metadata only). Oversight roles and the advisor. |
| `memory.read` | A0 | `{}` | The employee's own memory notes (latest first). |
| `github.read` | A0 | `{repo, what: "commits"/"issues"/"pulls"/"file", path?}` | Read-only GitHub. **Off** until the owner provides a read-only token (`channel_not_configured`). |
| `deliver` | A1 | `{work_ref, title_fa, body_md, evidence: [{kind, ref, note}]}` | Creates a deliverable (output card) for the owner or the requester. Evidence `kind` is exactly one of `deliverable` (an `O-…`), `link` (a URL or a work/decision ref), `metric` (a named measurement and its value) or `log` (an audit, run or check record); anything else is refused. |
| `propose` | A1 | `{kind, title_fa, what_md, why_md, risk, reversible, quota_estimate, payload}` | Creates a decision card (contract §5.1 kinds). The only path to anything A3, to hiring, and to recurring work. The `payload` shape of each kind is the API's own model, which the runtime puts in the prompt; a `hire` payload names the charter `role` (an `employee` charter that fits the company and department, contract §16.6). While hiring is closed a `hire` answers `403 hiring_closed` and no card is made (§18.11). |
| `hire.decide` | A2 | `{ref, verdict: approve/reject/return, note}` | ⟨1.4.3⟩ CEO only, own company, only hire cards whose approver is this CEO (hiring `delegated`, contract §18.11). The system checks the charter, the model, the estimate and the envelope before an employee exists; a refusal (`envelope_exceeded`, `validation_failed`) is reported as refused. |
| `story.post` | A1 | `{kind: post/milestone, title_fa, body_fa, figures, file_id, links}` | ⟨1.4.3⟩ CEOs and holding heads: a story for the owner (contract §18.12), at most three a day per company; every figure with a source, an image only from the company's own files, a milestone links its evidence. |
| `message.owner` | A1 | `{body_md, links?}` | A message in the role's own thread with the owner. CEOs, managers and the advisor only. Subject to the CEO attention quota; non-urgent messages wait for the next digest. |
| `message.thread` | A1 | `{thread, body_md, links?}` | Reply in a thread the employee belongs to. |
| `memory.write` | A1 | `{note_md, tags?}` | Append one note to the employee's memory (append-only). |
| `work.accept` · `work.progress` · `work.fail` | A2 | `{ref, note?}` · `{ref, note, pct?}` · `{ref, reason, decline?}` | Own assigned work. |
| `work.delegate` | A2 | `{ref, to, title_fa, brief_md, budget}` | Delegate down one level (depth ≤ 2, child budget ≤ what is left). |
| `work.request` | A2 | `{to, title_fa, brief_md}` | Request to another department's manager, or (CEO only) another company's CEO. |
| `activity.set` | A2 | `{state, note?}` | Live-stream activity of the employee (`working`, `waiting`, `idle`). |
| `notify` | A2 | `{level, category?, title_fa, body_fa, link?}` | Raise a notification. `urgent` only with an incident `category` (service down, security, data loss, budget hard stop), max 5/hour/company. |

The runtime adds `done` (finish the run) implicitly; there is no other way to end a run.

## v2 tools (2026-10-17; contract §18)

### The internet and MCP (every request goes through the **egress** service and is logged in `/egress`)
| Tool | Class | Input | What it does |
|---|---|---|---|
| `web.search` | A0 | `{q, lang?, recency_days?, site?, n?}` | Web search through the holding's own SearXNG. Results: title, url, snippet, date. The query is checked for internal data first. |
| `web.read` | A0 | `{url, mode?: "text"/"pdf"/"html", max_chars?}` | Fetch one page or file and return readable text with its final URL and date. |
| `web.browse` | A0/A2 | `{steps: [{do: "goto"/"click"/"type"/"select"/"scroll"/"wait"/"read"/"screenshot"/"download", target?, text?, url?}], account?}` | A real headless browser session (Chromium, Playwright) in the egress service. Reading is A0; using a holding service `account` is A2. A step that submits a payment, a purchase, a publication, a message to a person, an account creation or a security change is refused with `needs_owner` → `propose`. Screenshots and downloads come back as files. |
| `http.request` | A0/A2 | `{method, url, headers?, json?, body?, account?}` | Any external API. `GET`/`HEAD` are A0; other methods are A2 and allowed only for hosts and paths the service account's policy lists as non-committing; committing calls are refused with `needs_owner`. |
| `mcp.call` | per tool | `{server, tool, args}` | A tool of an MCP server the owner enabled; its class comes from the server's registration. |
| `egress.recent` | A0 | `{company?, actor?, since?, blocked?}` | The egress log (overseer, security analyst, AI safety). |

**Egress guard:** loopback, link-local, RFC 1918 (the hub's private network and its production neighbours), cloud metadata, the hub's
internal names and `/internal` are unreachable. Service-account credentials are injected at egress; no model sees them.

### Files, code and the workshop
| Tool | Class | Input | What it does |
|---|---|---|---|
| `files.read` | A0 | `{file_id, variant?}` | An owner or agent file the role may read: images as vision input, video as key frames plus transcript, audio as transcript, PDF as text. |
| `workshop.read` | A0 | `{session_ref, after?}` | A Code Workshop session and its events. |
| `backups.status` | A0 | `{}` | The backup status (§18.9). |

### Oversight, inquiries and QC
| Tool | Class | Input | What it does |
|---|---|---|---|
| `inquiry.ask` | A1 | `{to, question_md, due_in_hours}` | A formal question with a due time (overseer, advisor; a CEO inside its company). |
| `inquiry.answer` | A1 | `{ref, answer_md, evidence}` | The answer, delivered to the asker's thread. |
| `finding.raise` | A1 | `{company, protocol?, severity, title_fa, body_md, evidence, answerable, due_in_hours}` | A finding (overseer, QC, fact-checker, AI safety, security). |
| `finding.update` | A2 | `{ref, status, note, evidence?}` | The answerable sets `acknowledged`, `fixing`, `fixed`, `disputed`; the overseer sets `verified`, `closed`. |
| `protocol.result` | A2 | `{protocol, result, findings, notes}` | The result of one scheduled protocol run (overseer). |
| `challenge.issue` | A2 | `{company, period, title_fa, brief_md, criteria, due_at, judge?}` | A challenge to a company (overseer). |
| `challenge.submit` | A1 | `{ref, work_ref, note}` | The company's submission (CEO). |
| `challenge.score` | A2 | `{ref, score, notes}` | The judge's score (overseer or QC). |
| `hold` | A2 | `{target: {kind, ref}, reason_md}` | Hold an action pending the owner (overseer, QC, security analyst). Only the owner releases. |
| `kill_switch.engage` | A2 | `{scope, reason}` | Engage a company's kill switch (overseer: any company; CEO: its own). Release is the owner's. |
| `deploy.freeze` | A2 | `{company, until, reason}` | Freeze deploys (overseer). |
| `skill.review` | A2 | `{ref, version, verdict, checks, notes_md}` | Review a skill before activation (overseer, AI safety). |
| `star.audit` | A2 | `{star_id, counted, note}` | Mark a star counted or not, with the reason (overseer). |
| `lesson.write` | A1 | `{source_company, period, title_fa, body_md, evidence}` | A lesson from the best company (overseer, AI Ops head). |

### Stars, errands, academy, provisioning
| Tool | Class | Input | What it does |
|---|---|---|---|
| `star.rubric` | A2 | `{criteria: [{key, name_fa, weight, description_md}], rules_md}` | The company's star rubric (CEO). |
| `star.give` | A2 | `{employee, week, stars, criteria, reason_md, evidence}` | Weekly stars for one employee of the CEO's company. No evidence → not counted. |
| `errand.step` · `errand.finish` | A2 | `{ref, kind, summary_fa, data}` · `{ref, result_md, file_ids?}` | The personal assistant's errand trail and result. |
| `planner.add` | A2 | `{title_fa, at, note?}` | An item in the owner's planner (assistant). |
| `eval.run` | A2 | `{suite, subject: {kind, ref, version}}` | Run a golden eval suite (AI Ops head). |
| `teach.draft` | A1 | `{ref, proposal: {kind, diff_md}}` | Turn the owner's teaching into a precise proposal (AI Ops head); the overseer reviews, an eval runs, the owner approves. |
| `server.plan` | A1 | `{founding?, company, name, type, location, private_network, firewall, software, work_user, repo?}` | A server plan with cost; the owner seals it, the provisioner (code, not an agent) builds it. |

### Which role has what (v2)
Role charters list their tools in frontmatter; the gateway enforces them. In short: the **overseer** has every read tool, the web,
and the oversight powers; the **advisor** has every read tool, the web and `inquiry.ask`; the **assistant** has the web, files,
errands and the planner; **CEOs** have the web, files, inquiries inside their company, stars and challenge submissions; managers and
specialists have the web and files as their work needs.
