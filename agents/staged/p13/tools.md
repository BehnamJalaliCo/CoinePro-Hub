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
| `knowledge.search` | A0 | `{q, kinds?}` | Search what the role may read. `kinds`: `resolutions`, `deliverables`, `decisions`, `work`; `messages` for the advisor only. ⟨1.5⟩ `knowledge`: approved, unexpired entries of the four layers and the support articles (prompt 11); `docs` and `code`: the hub's documents and the workspaces' repositories (advisor, overseer, librarian; a CTO only its own company's repositories); `notes`: the owner's quick notes (advisor only) (prompt 12). Returns refs + short snippets. |
| `audit.recent` | A0 | `{company?, action?, since?}` | Recent audit rows (metadata only). Oversight roles and the advisor. |
| `memory.read` | A0 | `{}` | The employee's own memory notes (latest first). |
| `github.read` | A0 | `{repo, what: "commits"/"issues"/"pulls"/"file", path?}` | Read-only GitHub through the hub's own git access (owner decision 2026-10-17: no separate token; prompt 12). Until then, and for a repository the hub cannot read, `channel_not_configured`. |
| `deliver` | A1 | `{work_ref, title_fa, body_md, evidence: [{kind, ref, note}]}` | Creates a deliverable (output card) for the owner or the requester. Evidence `kind` is exactly one of `deliverable` (an `O-…`), `link` (a URL or a work/decision ref), `metric` (a named measurement and its value) or `log` (an audit, run or check record); anything else is refused. |
| `propose` | A1 | `{kind, title_fa, what_md, why_md, risk, reversible, quota_estimate, payload}` | Creates a decision card (contract §5.1 kinds). The only path to anything A3, to hiring, and to recurring work. The `payload` shape of each kind is the API's own model, which the runtime puts in the prompt; a `hire` payload names the charter `role` (an `employee` charter that fits the company and department, contract §16.6). While hiring is closed a `hire` answers `403 hiring_closed` and no card is made (§18.11). ⟨1.5⟩ `expected: {metric_fa, kpi?, baseline, target, by_days}` is required for kind `proposal` and drives the 30/60/90-day outcome reviews (contract §20.6). |
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

**Refusals you will see** (contract §14, §18.13) — each is a reason to change course, never to retry the same call:
- `needs_owner` — the step would commit the holding outside (pay, buy, publish, message a person, sign up, change security). `propose` it.
- `internal_data` — your query or call carries internal data (codes, refs, e-mails, phones, tokens), however encoded. Rewrite it without them.
- `egress_limit` — the run's or the company's daily internet limit is spent. Stop and report; do not split the work to get round it.
- `account_not_configured` — the service account has no secret yet; tell your manager.
- `mcp.call` outcomes: `a3_requires_decision` (the tool is A3: a card went to the owner; when it is approved, the follow-up run makes the **same**
  call once), `mcp_tools_changed` (the server changed its tools and is off until the owner seals it again), `mcp_tool_missing`, `mcp_unreachable`,
  `mcp_tool_error`.

### Files, code and the workshop
| Tool | Class | Input | What it does |
|---|---|---|---|
| `files.read` | A0 | `{file_id, variant?}` | An owner or agent file the role may read, own company only: images as vision input (long edge ≤ 1568), video as key frames plus transcript, audio as transcript, PDF as text; never the raw media or the file name. A file outside the company answers `policy_denied`, like a missing one. |
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

### Revenue and support (v1.5, prompt 10; contract §19)
| Tool | Class | Input | What it does |
|---|---|---|---|
| `kb.search` | A0 | `{q, company?, kind?}` | The company's support knowledge base: approved articles only (the support lead also sees proposed ones). |
| `kb.propose` | A1 | `{company, kind, question_fa, answer_md, variables?, source_ref, ref?}` | Propose a support article or a new version; the owner approves it (step-up `support.kb`). Referral codes and links come only from approved articles, never from a model. |
| `support.draft` | A2 | `{conversation, body_md, kb_refs, confidence}` | A draft answer to a customer. Code decides what happens to it: sent under the sealed auto-send policy, queued for teaching, or blocked by the outbound guard. |
| `support.handoff` | A2 | `{conversation, reason, note_fa}` | Hand a conversation to a person (the owner or the support lead). |
| `referral.check` | A0 | `{company, exchange, uid}` | Whether a UID registered under the holding's referral and meets the minimum: `{invitee, meets_minimum}` only, never a balance. |
| `rescue.update` | A2 | `{ref, state, note_fa}` | Move a referral-rescue case along. Nothing is sent by this tool: messages go out only as sealed templates by rule. |
| `feedback.tag` | A2 | `{source_ref, kind, area, title_fa}` | File customer feedback into the company's feedback inbox. |
| `revenue.read` | A0 | `{company?, from, to, by?}` | The revenue radar: commission and referrals by day, company and account, with incomplete days marked. |
| `funnel.read` | A0 | `{company, period}` | The funnel stages; a stage with no source reads "not connected", never zero. |
| `support.mystery` | A2 | `{company, question_fa}` | Overseer only (PR-043): a mystery-customer conversation that runs the whole pipeline but never reaches a customer channel. |

No tool sends free text to a customer. Templates and lifecycle rules are proposed with `propose` and sealed by the owner.

### Governance (v1.5, prompt 11; contract §20)
| Tool | Class | Input | What it does |
|---|---|---|---|
| `meeting.statement` | A1 | `{meeting, item, statement_md, claims: [{text_fa, source}], draft_md?, stance?}` | A speaker's turn, only inside a meeting run. A claim without a readable source is marked unsourced and never reaches the minutes. |
| `meeting.challenge` | A1 | `{meeting, item, claim?, statement_md, claims}` | The devil's advocate's challenge (oversight roles). |
| `meeting.whisper` | A1 | `{meeting, item, text_md, sources}` | The advisor's note to the owner only, never shown to the meeting. |
| `meeting.item` | A1 | `{type, company, title_fa, brief_md, sources}` | Propose an agenda item for the next meeting of a type. |
| `meeting.minutes` | A1 | `{meeting, summary_md}` | The secretary's summary, written from sourced claims only. |
| `knowledge.propose` | A1 | `{layer, company?, department?, kind, title_fa, body_md, sources, valid_until, ref?}` | A knowledge entry or a new version: at least one source and an expiry within the kind's limit. |
| `knowledge.review` | A2 | `{ref, version, verdict, checks, notes_md}` | Review an entry before approval (overseer, AI safety). |
| `knowledge.approve` | A2 | `{ref, version}` | A CEO approves a company or department entry of its own company after a passing review (an authority-matrix row the owner may take back). |
| `kpi.record` | A2 | `{company, key, value, at, source: {kind, ref, note}}` | A value of a manual KPI, with its source (the CEO or a manager of that company). |
| `okr.draft` | A1 | `{company, quarter, objectives: [{title_fa, why_md, key_results: [{title_fa, kpi?, metric_fa?, start, target, weight}]}]}` | The CEO's next-quarter OKRs, as a card for the owner. |
| `okr.checkin` | A2 | `{key_result, confidence, note_md, evidence, current?}` | A key-result check-in (due at least every 14 days). |
| `outcome.note` | A1 | `{ref, note_md, measured?: {value, at, source_ref}}` | The proposer's note on a 30/60/90-day outcome review. |
| `risk.raise` | A1 | `{company, title_fa, body_md, category, likelihood, impact, links?}` | Add a risk to the register. |
| `risk.update` | A2 | `{ref, version, likelihood?, impact?, mitigation_md?, status?, note}` | Update a risk; closing it is the keeper's (QC). |
| `calendar.read` | A0 | `{company?, from, to, kind?}` | The change calendar and its conflicts. |
| `calendar.add` | A2 | `{company, kind, title_fa, starts_at, ends_at, source, risk}` | Put a planned change on the calendar; the calendar never decides. |
| `authority.read` | A0 | `{}` | The authority-matrix rows of the role's company. |
| `governance.read` | A0 | `{what: "cards"/"okr"/"risks"/"charter"/"outcomes", company?}` | The company's cards, OKRs, risks, sealed charter and outcome reviews. |

There is no tool that writes the charter or the authority matrix: agents propose (`charter_amendment`, `authority_change`) and the owner seals.

### Management tools (v1.5, prompt 12; contract §21)
| Tool | Class | Input | What it does |
|---|---|---|---|
| `memo.write` | A1 | `{decision, decision_version, mode, summary_fa, recommendation, confidence, options, against_md, risks, questions, citations}` | The advisor's decision memo on a pending card; `against_md` (the strongest case against) is never empty. |
| `ask.answer` | A1 | `{ask, answer_md, citations}` | The librarian's answer to "ask the hub", only from the passages the search returned; a citation outside them is dropped. |
| `claim.verdict` | A2 | `{deliverable, claim_md, verdict, evidence}` | A fact check of one claim in a deliverable (fact checker, overseer, QC); `refuted` needs evidence. |
| `substitute.call` | A0 | `{seat, player?, input_md, file_ids?, repo?, head_sha?, kind?: "text"/"image"/"video", placement?, overlay?, duration_s?}` | Call a substitute player (ChatGPT or Gemini on the owner's subscriptions, contract §21.13) for one bounded task: the advisor, the overseer, the assistant and CEOs; `code_review` also the CTO and QC. Masked input only (no customer data or secrets; repository code only for `code_review`, as a read-only checkout); the answer is labelled with its source and is never evidence. Image and video return a creative `CR-…` (with its `placement`, e.g. `telegram_post`, `instagram_story`; Persian text goes in `overlay` and is set by the hub) that waits for review. Refusals: `channel_not_configured` (signed out or off), `rate_limited` (the seat's daily cap or the player's quota), `policy_denied`. |

### Media studio and legal (v1.6, prompt 13; contract §22)
| Tool | Class | Input | What it does |
|---|---|---|---|
| `media.item` | A1 | `{ref, step: "script"/"direction"/"composition", script?: {text_fa, sources}, direction?: {shots}, composition?: {format: "html"/"lottie", source}}` | Write the current step of a media item for the role that owns that step (scriptwriter, video director, motion designer). Code checks the composition against the schema (no network, allowed libraries only, IRANYekanX only) before it is stored. |
| `media.render` | A2 | `{ref}` | Queue the item's render in the sandboxed render worker (headless Chromium frame by frame, ffmpeg). Returns when the job is queued; the result arrives as a file on the item. |
| `media.voice` | A2 | `{ref, text_fa, voice_id?}` | Make the narration with the hub's active open-source voice (§22.3), aligned to the shots. |
| `media.review` | A2 | `{ref, verdict: "pass"/"changes"/"reject", note_md}` | The media director's quality review of an item (the `qc` check). Never publishes anything. |
| `series.propose` | A1 | `{company, title_fa, kind, targets, schedule, topics, format, checks, auto_publish, max_per_day}` | Propose a publishing series; it becomes a `media_series` card for the owner's seal. |
| `case.open` · `case.note` | A1 | `{company, title_fa, kind, brief_md, counterpart?}` · `{ref, kind: "note"/"form"/"decision", summary_fa, ref_link?}` | Open a legal case or add to its timeline (the legal counsel). |
| `email.draft` | A1 | `{case, to, cc?, subject, body_md, lang, file_ids?}` | Draft an email for a case; it becomes an `email_send` card with the exact message. Nothing is ever sent without the owner's seal. |
| `mail.read` | A0 | `{case}` | The masked emails of the counsel's own cases. |

Publishing has no tool: code publishes a sealed series' items through the official APIs, and everything else is a card.

### Which role has what (v2)
Role charters list their tools in frontmatter; the gateway enforces them. In short: the **overseer** has every read tool, the web,
and the oversight powers; the **advisor** has every read tool, the web and `inquiry.ask`; the **assistant** has the web, files,
errands and the planner; **CEOs** have the web, files, inquiries inside their company, stars and challenge submissions; managers and
specialists have the web and files as their work needs.
