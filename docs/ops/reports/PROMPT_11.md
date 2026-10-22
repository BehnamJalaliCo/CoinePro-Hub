PROMPT_11 REPORT (governance)

## §4-§10 (r11b: the three cards and the scorecard, OKR, decision outcomes, the authority matrix, risks, the change calendar, the batch seal)

- Branch **r11b** from `server/p11-governance` c58410c (prompt 10 live + main up to "Prompt 11 sent"); nothing else merged. **Not deployed.**
- **Migration:** `0026_1_governance_cards.py`, revision **0026_1**, down_revision **0025** (the parent chains it after the other half's 0026). `CREATE SCHEMA IF NOT EXISTS governance` (0026 makes it too). It rewrites `decisions_kind_check` from the kinds it holds plus the six of §20.11 (meeting_resolution, charter_amendment, okr, knowledge_entry, risk_acceptance, authority_change), **NOT VALID**; its downgrade keeps those kinds (cards of them outlive the tables; 0025's re-upgrade validates the constraint in test_hiring's 0009 round trip).
- Hub state kept: no model call anywhere (no router in any new code path), no outside call, no new service, port, container, profile or compose change (memory gate unchanged); `HQ_PROVISIONING` untouched; real-model tokens spent: **0**.

### §4 The three cards and the live scorecard (PR-090)
- §4.1 ok: `governance.kpis` (versioned definitions; the collector's last value is a cache, not a version), `kpi_values` (append-only series), `kpi_sets` (the If-Match version), `kpi_changes` (every definition change). Test: test_a_query_outside_the_registry_is_422 (If-Match, versions).
- §4.2 ok: sources only from the closed registry in code (`domain/gov_kpis.py` REGISTRY: health.*, treasury.*, work.*, oversight.*, stars.company_score; revenue.*, funnel.*, support.csat_30d from prompt 10; hub.* for the holding) or `manual`; a query outside it is 422; a manual KPI only by `kpi.record` with a `{kind, ref, note}` source (CEO or manager of that company). Tests: test_a_query_outside_the_registry_is_422, test_a_manual_kpi_without_a_source_is_422_and_a_query_kpi_is_codes.
- §4.3 ok: `hq-kpi-collect` every 15 min in the worker, by code; a value older than its freshness is `stale` («قدیمی», `kpi.stale` once per episode); no value is `no_source`, never zero; the holding card = its own KPIs + the companies' aggregated by each KPI's `aggregate`. Tests: test_a_health_kpi_is_measured_by_code_with_no_model, test_a_stale_value_is_stale_and_pr_090_raises_a_finding, test_the_holding_card_aggregates_one_more_company, test_revenue_without_a_source_is_no_source_never_zero.
- §4.4 ok: seed `apps/api/seed/kpis/standard.yaml` (registry queries only); a founding's `proposal.kpis` become manual growth KPIs; the owner changes targets with `PUT /kpis/{company}` (If-Match, audit, interaction). Test: test_a_query_outside_the_registry_is_422.
- §4.5 ok: `GET /scorecards` (one row per company, paged by code, `?q`), each cell value, time, source, target, 30-day trend (null on a day without a value) and state. Test: test_the_scorecard_is_paged_and_searchable.
- §4.6 ok: `gov_kpis.attainment` (one place): the active quarter's weighted key-result progress, else the share of scorecard KPIs with a value and a target at target; `stars.py` uses it for the 35% KPI part (left out when None). Tests: test_kpi_attainment_is_the_share_of_scorecard_kpis_at_target, test_a_late_checkin_is_a_finding_and_the_score_follows_the_krs.
- §4.7 ok: PR-090 paused → active by migration 0026_1 (an audit row `protocol.activate`) where only seeded versions exist; on a fresh database the seed does the same (`gov_checks.activate`). Its checker: a stale KPI is a finding (no_source is not). Tests: test_the_activated_protocols_are_active_and_scheduled, test_a_stale_value_is_stale_and_pr_090_raises_a_finding.
- §4.8 ok: `GET /cards`, `/scorecards`, `GET·PUT /kpis/{company}`, `/kpis/{company}/{key}/values`; topic `governance` (kpi.stale).

### §5 OKR per company
- §5.1 ok: `governance.objectives` (OB-0001), `key_results` (KR-0001), `okr_checkins` (append-only); Jalali quarters (`1405-Q3` = Mehr..Azar). A KR is a KPI (its value) or a manual metric (check-in with evidence).
- §5.2 ok: `okr.draft` (A1, the CEO; the current quarter without one or the next) → one `okr` card; amendments `key_result_changes`/`objective_changes`; only the owner's seal makes it active (and closes the quarter's earlier active ones); a returned, rejected or expired card leaves it draft. In a quarter's last month `hq-governance-daily` gives each CEO one «OKR فصل بعد» work item. Tests: test_an_okr_is_active_only_with_the_owners_seal, test_the_fx_ceo_drafts_no_okr_for_ty.
- §5.3 ok: `Work.key_result` from `POST /work` and `work.delegate` (a child inherits it); the planner shows it. Test: test_a_kpi_key_result_takes_the_kpis_value_and_work_serves_it.
- §5.4 ok: `okr.checkin` (A2) at least every 14 days; a late one is PR-116's finding (also: next quarter not proposed 30 days before it starts). Test: test_a_late_checkin_is_a_finding_and_the_score_follows_the_krs.
- §5.5 ok: the monthly progress is code (`GET /okr`, `/okr/{ref}`: progress per KR and objective); no new run.
- §5.6 ok: `GET /okr`, `/okr/{ref}`; `okr.updated` on topic governance.

### §6 Decision outcome reviews (30/60/90)
- §6.1 ok: `Decision.expected` (API, gateway `propose`); for a `proposal` made after the rollout (`governance.rollout`, the migration's time) a missing one is `warnings: ["expected_missing"]` for 7 days, then 422; earlier cards untouched (`expected`, `warnings` immutable); an unknown KPI is 422. Test: test_a_proposal_without_expected_warns_for_seven_days_then_is_422.
- §6.2 ok: the seal makes OR-… rows for day 30, 60, 90 up to by_days. Test: test_a_sealed_decision_has_reviews_at_30_60_90_and_a_met_kpi_is_met.
- §6.3 ok: on the due day by code (`met`/`partly`/`missed`, status verified, `outcome.due` once); without a KPI `unmeasurable`: `outcome.note` (A1, the proposer only) then the overseer's verdict in PR-006 (`protocol.result` `outcomes`); PR-006 now has a checker (code first) and writes into this table. Nothing to migrate: no PR-006 run ever recorded a verdict (the holding has been locked). Tests: test_a_sealed_decision_has_reviews_at_30_60_90_and_a_met_kpi_is_met, test_without_a_kpi_the_review_waits_for_the_note_and_the_overseer.
- §6.4 ok: prediction accuracy = (met + partly/2) / decided, `GET /outcomes/accuracy`. Test: test_prediction_accuracy_with_fixed_data.
- §6.5 ok: `GET /outcomes` (`?company&verdict&due&decision`, `due=true` = due now or overdue); `outcome.due` on topic governance.

### §7 The authority matrix
- §7.1 ok: `governance.authority` (holding config, no company), seeded from `apps/api/seed/authority.yaml`: hire.per_day 5, ceo.attention_per_day (= owner.settings.ceo_daily_attention), recurring approval by the CEO within quota, notify.urgent_per_hour 5, story.per_day 3, deploy.blackout_days (Friday), knowledge.approve.company (CEO), batch.max_usd $2, batch.max_items 20, batch.kinds. The api pushes the rows to OPA `data.hq.authority` (`PUT /v1/data/hq/authority`, the one data write system.authz now allows) at first use, after every change and whenever OPA's digest differs (≤ 60 s per process); `hq.limits` clamps every number into the files' bounds (`data.json`). hire.per_day is enforced by the row and OPA together; the story and urgent caps read their rows. Tests: test_after_the_hire_cap_changes_opa_enforces_it_at_once, test_the_bounds_of_the_files_agree, limits_test.rego.
- §7.2 ok: locked invariants (A4 never; A3 only the owner, the CEO content-calendar publish off; proposer ≠ approver; releasing a switch or a hold; no agent edits the matrix; never-batched kinds) are in hq.actions/hq.decisions/hq.internal and never read the data; sealed sends (a sealed lifecycle rule with its current sealed template, a live channel's auto_send) stay allowed, read from the seals. Tests: test_tampered_data_gives_no_agent_a3 (+ rego test_tampered_data_gives_no_agent_a3), test_sealed_sends_stay_allowed_and_an_unsealed_template_stops_its_rule.
- §7.3 ok: `PUT /authority` 🔏 `authority.update` (body SHA-256): unlocked rows only, inside bounds (422), row versions (409); `actor: "owner"` takes a row back (OPA then refuses the CEO's recurring approval); agents propose `authority_change` (🔏; `from` written by the api; 409 when the row moved). Tests: test_a_locked_row_or_a_number_outside_its_bounds_is_422, test_an_authority_change_card_is_sealed_with_step_up_and_applied.
- §7.4 ok: `GET /authority` (with locked rows and the digest); `authority.read` (A0) the rows of the agent's company; an agent on `PUT /authority` → 403. Test: test_an_agent_never_writes_the_matrix.

### §8 The risk register
- §8.1 ok: `governance.risks` (RK-0001, score = likelihood × impact, owner, mitigation, review_at, links, draft) and `risk_history`; keeper: the Inspector General.
- §8.2 ok: review_at at most 14/30/90 days by score; an overdue review → a work item for its owner (once per date), then PR-112's finding; 15+ without mitigation or acceptance → PR-112; acceptance only by a `risk_acceptance` card 🔏 (≤ 90 days; reopened when it lapses); closing only by the keeper (or the owner); a critical finding drafts a risk (`gov_risks.draft_risk`, also the post-mortem's entry point). Tests: test_a_20_risk_without_mitigation_after_its_date_is_a_finding, test_an_acceptance_needs_the_owners_step_up, test_the_owner_of_a_risk_cannot_close_it_and_the_keeper_can.
- §8.3 ok: `risk.raise` (A1: own company; holding-scope oversight roles any), `risk.update` (A2: the owner or the keeper). Test: test_the_fx_ceo_does_not_see_or_touch_a_ty_risk.
- §8.4 ok: `GET /risks`, `/risks/{ref}`, `/risks/matrix` (5×5), `POST /risks`, `PATCH /risks/{ref}` (If-Match); `risk.updated`.

### §9 The change and release calendar
- §9.1 ok: `governance.calendar_events` (CE-0001; deploy, campaign, event, maintenance, meeting, freeze, holiday; source decision/work/meeting/order).
- §9.2 ok: filled by code: a deploy card's `window` (before the card exists; `head_sha` required from now, 422 without), freezes (at a deploy's proposal and daily), the hub's nightly backup and weekly restore test, the 1405-1406 holidays (`apps/api/seed/calendar/holidays.yaml`, lunar days marked as tabular estimates); campaigns and events by `calendar.add` (CEO, GROWTH manager, holding managers) or the owner. Tests: test_a_deploy_in_a_freeze_conflicts_high_and_head_sha_is_required, test_the_holidays_are_seeded_and_a_deploy_on_one_is_medium.
- §9.3 ok: the conflict rules (freeze and same-company campaign/event high; two deploys of a company or a repo, a blackout day, a holiday, maintenance medium) in `payload.calendar_conflicts` and `risk_note`, `calendar.conflict` events; a rejected card's window is cancelled; PR-113 finds a deploy approved without a window or with a high conflict. Tests: test_a_campaign_at_the_same_time_is_seen_and_another_companys_is_refused, test_pr_113_finds_a_deploy_outside_the_calendar.
- §9.4 ok: the planner shows calendar events (`kind: "calendar"`), still a view.
- §9.5 ok: `GET /calendar` (events and conflicts), `POST /calendar`, `PATCH /calendar/{ref}` (If-Match); `calendar.read`, `calendar.add` (403 for another company).

### §10 The batch seal
- §10.1-§10.2 ok: eligibility by code and OPA together (`batch.kinds` ⊆ proposal, meeting_resolution, knowledge_entry; A1, low, reversible, pending, the owner's, no hold, no amendments, usd ≤ batch.max_usd); never batched: the locked list. Test: test_a_batch_with_a_hire_is_422_and_nothing_is_sealed.
- §10.3 ok: `GET /decisions/batchable`; `POST /decisions/batch/approve` 🔏 `decision.batch` on sha256 of the canonical sorted `[{ref, version}]`, Idempotency-Key; all or nothing (`422 batch_not_eligible`, `fields.items [{ref, reason}]`); each card its resolution, audit row (`batch: B-0001`) and interaction. Tests: test_a_card_that_changed_after_the_step_up_refuses_the_batch, test_a_token_for_one_card_less_or_more_is_refused, test_the_twenty_first_card_is_422, test_each_card_of_a_batch_has_its_resolution_audit_and_interaction.

### §11 Agent tools (the §4-§10 part)
- §11 ok: gateway `hq_gateway/governance.py`: kpi.record, okr.draft, okr.checkin, outcome.note, risk.raise, risk.update, calendar.read, calendar.add, authority.read, governance.read (classes as tools.md; texts redacted; Idempotency-Key per step); `propose` takes `expected` and the kinds authority_change and risk_acceptance (okr only from okr.draft); `work.delegate` takes `key_result`; OPA `governance.rego` + `ops` + A2 grants; GATEWAY_TOOLS. No tool writes the charter or the matrix. Tests: services test_governance_tools (13), governance_test.rego.

### §12 Oversight (the §4-§10 part)
- §12 ok: PR-090, PR-112, PR-113, PR-116 active (migration / seed) and scheduled (one Temporal schedule each, paused while `oversight_schedules` is off as today); their checkers and PR-006's by code (`domain/gov_checks.py`); like every protocol run they do nothing while the holding is locked. Tests: test_the_activated_protocols_are_active_and_scheduled, test_a_protocol_runs_nothing_while_the_holding_is_locked.

### The lock (every job of §4-§10)
- `hq-kpi-collect` (KpiCollect) and `hq-governance-daily` (GovernanceDaily) ask `gate.holding_lock` first and return `{"skipped": true, "reason": "holding_locked"}` with no row, no work item, no model and no outside call; neither calls a model at all. The protocols skip as before. Tests: test_no_collection_and_no_governance_job_while_the_holding_is_locked, test_a_protocol_runs_nothing_while_the_holding_is_locked, test_the_governance_schedules.

### Checks run (HQ_TEST_NAME p11b / p11bs, HQ_TEST_IMAGE_TAG p11b)
- api tests: the three p11b files (39 tests) and test_rls_all_tables (governance in SCHEMAS, `_fill_p11b`); the whole api suite once (see the final reply). services: gateway and hq-common tests. lint (ruff, mypy --strict) green; OpenAPI regenerated (31 operations added, none removed, no schema renamed); opa (100% coverage) green.

### Contract notes (§4-§10)
- AuthorityRule.limit also has `items` (batch.max_items, as §20.12) and `kinds` (batch.kinds, batch.never); `days` are weekday names (`sat`…`fri`); `bounds` is `{min, max}` for a number and `{allowed: [...]}` for a list. `GET /authority` → `{rules, digest}` (the digest OPA reports at `/v1/data/hq/limits/version`).
- The OPA push: system.authz allows `PUT /v1/data/hq/authority` to any caller on hq-agent (api, worker, gateway); the locked invariants never read it and hq.limits clamps every number into the files' bounds, so a forged push can only move a number within the owner's bounds.
- Kpi gains `target_max` (direction `range`); `PUT /kpis/{company}` may add a KPI (`source`, `card`, `name_fa`, `unit?`, `direction?`, `aggregate?`) beside §20.12's fields; a query KPI is keyed by its query; a source never changes. A scorecard row also has `name_fa`.
- The `okr` payload also carries `objectives: [OB-…]` (one card for a draft's objectives); its amendments are `objective_changes` and `key_result_changes`. Action classes: okr A1, risk_acceptance A2, authority_change A2 (the contract names none).
- `protocol.result` takes `outcomes: [{ref, verdict, note_md}]` for PR-006 (tools.md's row does not list it). `outcome.note` takes optional `evidence`. `GET /outcomes/accuracy` added.
- Risk also has `draft` and `origin`; the owner may close a risk as well as the keeper; risk.raise's owner is the raiser in its company, else the company's CEO.
- Batch: a card with a token estimate and no USD figure is not eligible (`over_max_usd`); a card a CEO decides gives `kind`. Problem.fields is `dict[str, Any]` (it carries `items`).
- CalendarEvent.company is null for a holiday; the deploy `window` is `{from, to}`; PlannerItem gains `kind: "calendar"`, `calendar_kind`, `key_result`.
- governance.read `charter` reads `governance.charters` (the other half) when its table is there, else `{state: "no_source"}`.

### Owner tasks (§4-§10)
1. KPI targets on each company's cards (in the app; `PUT /kpis/{company}`); manual KPIs (کاربر فعال) are recorded by the CEOs once the hub is launched.
2. Review the authority matrix (defaults above: 5 hires a day, 5 urgent an hour, 3 stories a day, attention 6, deploy blackout Friday, batch $2 / 20 cards / three kinds, knowledge approval with the CEO).
3. Seal next quarter's OKR when its card comes.
4. Check the lunar holidays of `apps/api/seed/calendar/holidays.yaml` against the official calendar (RUNBOOK §29.9).

### For the parent's merge with r11a
- Shared files changed additively: decisions.py (KINDS, ACTION_CLASS, STEP_UP_KINDS, PAYLOADS, DecisionIn kinds, `expected`, the deploy payload, decide's `hub=`), internal.py (OP_CLASS, delegate's key_result, the urgent cap row), errors.py (`batch_not_eligible`, Problem.fields), events.py (topic `governance` incl. `charter.`), app.py (governance router before decisions), OPA data.json / internal.rego ops / decisions.rego kinds, gateway tools.py (propose, delegate) and tool_status, seed.py, schedules/workflows/activities, RUNBOOK §29.4-§29.11 (append after §29's first lines), test_rls_all_tables (SCHEMAS `governance`, `_fill_p11b`: r11a's governance tables need their own fill).
- `gov_authority` has the row `knowledge.approve.company` (CEO; the owner may take it back) for r11a's knowledge approval, and `gov_risks.draft_risk(..., origin="postmortem")` for the post-mortem.
