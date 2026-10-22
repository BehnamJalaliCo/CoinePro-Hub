PROMPT_10 REPORT (revenue radar, funnel and referral rescue, support desk, lifecycle, NPS, feedback, intake) — in progress

- Branch r10 (to become server/p10-revenue-support) = server/p09-founding 319b1f8 + main 0f2d8b0 (the p10 charters and tools.md v1.5), merged without conflict. Not deployed.
- Migration **0025** (`0025_revenue_support.py`), down_revision **0023**: the parent re-chains it after 9.1's 0024. 0023's kind CHECK re-add is NOT VALID now ("0025 validates"), so the 0009 round trip (test_hiring) passes with cards of the new kinds.

## §1 Foundation: data, privacy, pseudonym
- §1.1 ok: schemas revenue, support, growth, feedback, intake; 31 tables, every one with company_id and FORCE RLS in the once-per-query form (0009), no company-less table (intake.sources and intake.nonces too); the five schemas are in test_rls_all_tables (one row of company B in every new table, none visible to A) and test_schema_rules (forced RLS); test_p10_foundation::test_fx_sees_no_support_row_of_ty (database scope and OPA)
- §1.2 ok: subject = HMAC-SHA256(key, company id ␟ channel ␟ external id), hq_common.pseudonym; the key kv/support/pseudonym is made once by infra/openbao/kv-once.sh (cas 0, never printed) from provision.sh, read by hq-api and hq-worker (policies), loaded as an optional secret; no key, no subject (503 not_ready, nothing stored); every subject column has CHECK hex 64 and revenue, growth, feedback and intake have no handle/uid/external_id column; tests test_customer_mask (pseudonym cases), infra.sh "kv-once", test_no_pseudonym_without_the_key, test_revenue_growth_and_feedback_hold_no_raw_handle_or_uid
- §1.3 ok: hq_common.customer_mask.mask() = redact's §16.6 shapes + BIP-39 phrases (12+ words of the pinned list, one typo allowed, numbered or comma-separated, full-width or invisibly split), private keys (64 hex with or without 0x, WIF, xprv/yprv/zprv/tprv, any -----BEGIN block), cards (13-19 digits, Luhn, Latin/Persian/Arabic digits, spaces or dashes); domain.support.store_inbound masks before the INSERT and model_view masks again; tests test_customer_mask (36 cases), test_a_seed_phrase_is_masked_before_storage_and_for_a_model
- §1.4 ok: daily hq-support-retention (04:15 owner zone, SupportRetention → support_retention): texts older than SUPPORT_RETENTION_DAYS (180) are removed — message bodies, NPS comments, feedback quotes, intake event data — rows, times, states and tags stay; rule-only, so it runs while the holding is locked; RUNBOOK §27 (backups keep a purged text until their own snapshot expires); test_retention_purges_old_texts_keeps_the_rows_and_runs_while_locked (181 days purged, 179 kept)
- §1.5 ok: infra/opa/policy/support.rego (100% covered): support.read (conversations, customers, proposed articles) = the company's support_lead/support_agent/referral_rescue and its SALES manager; support.stats (counts, masked quotes) also its CEO and the holding's advisor and overseer; kb.read approved = every employee of the company, proposed = support people; revenue.read/funnel.read per §19.10 (funnel.read also the support people); tests support_test.rego, test_fx_sees_no_support_row_of_ty
- §12.1 (charters) ok: support_lead, support_agent, referral_rescue, revenue_analyst are live in the charter library from agents/roles/ as they are (no problems); nobody is hired (hiring stays closed); test_the_new_charters_are_seeded_and_nobody_is_hired

## Foundation for §2-§13 (for the next agents)
- **No new migration.** 0025 holds every table of §2-§11 (columns documented in the file). If one is truly unavoidable, make it 0026 on 0025 and say why. Content of versioned rows (support.kb_articles, growth.templates, growth.rules) is immutable: a new version is a new row with the same ref (the ref stays in its company, a trigger). App roles hq_api and hq_worker have SELECT, INSERT, UPDATE on every new table (immutable columns are guarded by keep_immutable triggers), no DELETE anywhere but intake.nonces; growth.rescue_steps, growth.referral_checks, growth.opt_outs and intake.rejections are append-only.
- **Tables by section:** §2 revenue.accounts, days, invitees (subject + meets_minimum only), pulls, alerts (UNIQUE incident_key) · §3 growth.funnel_days, leaks, rescue_cases (RC-000001), rescue_steps, referral_checks (cache + 30/h cap: rows with cached=false) · §4 support.settings, channels, customers, conversations (SC-000001), messages · §5 support.kb_articles (KB-0001), history_imports, shadow_runs; academy.eval_suites ref `support-shadow-<CODE>` + version, eval_runs purpose 'shadow' · §7 growth.templates (TM-0001), rules (LR-0001), sends (UNIQUE dedupe_key), opt_outs, nps_waves, nps_responses · §8 feedback.items (FB-000001, merged_into), signals (pending → rule/model/agent), keywords · §9 intake.sources (UNIQUE company+kind+channel), nonces, events, rejections.
- **Database rules you get for free:** a channel can be `live` only with go_live_decision_id and live_since (CHECK); support.settings thresholds change only together with a new thresholds_decision_id (trigger, HQV01); one open conversation per customer; one open rescue case per company+exchange+subject; one approved version per article ref, one approved policy key per company; decision kinds message_template, lifecycle_rule, support_go_live exist.
- **Helpers:** `hq_api.domain.support` — subject(), settings(), channel() (rows made on first use, no seed needed), store_inbound() (mask → customer → open conversation → message; dedupes webhook retries by external id; returns first_secret for the one safety line), model_view() (what a model may read), purge_texts(). `hq_common.customer_mask` — mask(), quote() (also hides @handles and long ids: use it for every quote a CEO, the advisor, the overseer or the feedback inbox sees). `hq_common.pseudonym` — channel is a support channel kind, or `uid:<exchange>` for an exchange UID (the same person has one subject across the affiliate list, referral.check and product events).
- **The holding-lock rule (owner, 2026-10-22):** anything that runs on its own — a schedule, an activity, a pull, a send, a draft, the nightly batch, a protocol, an agent run it would start — begins with `lock = await gate.automation_lock(tx, company_id)` and returns `gate.skipped(lock)` while it is set: no model call, no outside call, no new run (record `skipped`/`skipped_reason` where the table has one). Give each an acceptance test that engages the holding switch (see test_p10_foundation's pattern: save the state, engage, run, restore). Only rule-only work that touches nothing outside (like retention) may skip the gate; say so in your reply.
- **Where things go:** routes in routes/revenue.py, support.py, growth.py, feedback.py, intake.py (already registered: `router` under /api/v1, `internal_router` under /internal/v1, intake's `webhook_router` under /intake/v1 — Caddy routes for /intake/v1 are §9's); worker activities in worker/support_activities.py (SupportActivities is registered; add to all()), workflows in worker/workflows.py (WORKFLOWS), fixed schedules in worker/schedules.py (FIXED + fixed()); domain logic beside domain/support.py; the outbound guard in hq_common (§6).
- **Already registered:** stream topics revenue, support, growth (rescue., lifecycle., nps.), feedback; error codes channel_not_live, shadow_not_passed, template_not_sealed, send_blocked, opted_out, send_limit; OPA ops support.read, support.stats, kb.read, revenue.read, funnel.read (A0 in OP_CLASS; send `charter: ctx.who.charter` in the target); settings SUPPORT_RETENTION_DAYS, SUPPORT_DRAFT_DAILY_TOKENS (also passed to llm-router for the scope support_draft:<company>), SUPPORT_DAILY_OUTBOUND_CAP, SUPPORT_AUTO_REPLIES_PER_HOUR, SUPPORT_HANDOFF_DIGEST_MIN, REFERRAL_CHECKS_PER_HOUR, REFERRAL_CHECK_CACHE_S, REVENUE_BACKFILL_DAYS, REVENUE_PULL_MAX_DAYS, INTAKE_MAX_SKEW_S (config.py, .env.example, compose api/worker env).
- **The draft budget (§4.3)** needs no llm-router migration: SUPPORT_DRAFT_DAILY_TOKENS already reaches llm-router's environment (not read yet); a check beside `_check_oversight_share` (service.py) over the day's role counters of `<CO>:support_agent` does it.
- **Left for §12:** the gateway tools (kb.search … support.mystery) and their OPA write ops; test_the_advisor_v2_has_its_read_tools exempts revenue.read and funnel.read from the live-gateway-tools check until they exist — drop that exception then.

## Checks of the foundation (HQ_TEST_IMAGE_TAG=p9b, fresh database)
- api: the whole suite on a fresh database (the 0009 round trip of test_hiring included): all passed but test_propose_section_is_generated_from_the_api_models, whose list of hireable roles now starts with prompt 10's charters (merged from main); the test names them now and passes.
- services: hq-common and gateway tests passed; lint (ruff, format, mypy strict) clean; OPA 107/107 at 100% coverage; openapi unchanged (the route modules are empty); shellcheck, compose-config, compose-rules, yamllint, memory-budget (full 10896 MiB of 12486), gitleaks (history and tree) and infra.sh (kv-once included) green. The full make check is the parent's.

## Contract notes
- An inbound SupportMessage has status `sent` (the §19.3 enum has no "received"); a refused send records `failed` with a `failure` field (no_channel, send_error, send_limit, channel_not_live, opted_out) beside blocked_reasons.
- The pseudonym's "company" is the company id and the three parts are joined with U+001F; "channel" is a support channel kind or `uid:<exchange>`.
- The inbound mask also masks a 64-hex transaction hash (the safe side: support asks for a UID, never a hash).
- Retention removes every text a customer wrote (message bodies, NPS comments, feedback quotes, intake event data), not only messages; rows stay.

## Owner tasks (from §1)
- None needed for §1: the pseudonym key is made by `make up`. To note: a purged text stays in the restic snapshots until each expires (yearly snapshots: up to 10 years); removing it from backups earlier is the owner's decision.

## Gating
- Nothing in this foundation calls a model or an outside service. The one new scheduled job, the retention sweep, is rule-only and runs while the holding is locked (by design). HQ_PROVISIONING untouched. Real-model spend: 0 tokens.

## Support
Branch r10b (on r10 2005809), stage D's support half: §4-§7, §9-§11 and the desk's part of §12. No migration (0025's tables only). Nothing is deployed; no channel is live; the holding switch and `HQ_MORNING_REPORT_LLM=off` are untouched.

### §4 Support desk: channels and the answer path
- §4.1 ok: channels per company (not_configured → shadow → live → paused), made on first use. `PATCH /support/channels/{company}/{kind}` (If-Match): widening (kb_grounded, or a paused channel that already went live back to live) 🔏 `support.channel` = `company/kind@auto_send`; narrowing needs none; never-live → 409 `shadow_not_passed`; `/pause` no step-up. Live only from a sealed `support_go_live` card. Test: test_patch_widening_needs_step_up_and_narrowing_does_not.
- §4.2 ok: Telegram by webhook only. Updates come in through `/intake/v1/telegram/{CO}/{channel}` (§9). setWebhook runs once per channel with the secret token, from egress, in the sweep (unlocked only).
  - Business messages are answered with their `business_connection_id`; `business_connection` updates set `premium_connected`.
  - Telegram's rules are in code (a bot writes only to a person who wrote first; Business needs its connection). What Telegram would refuse is recorded `failed: no_channel`.
  - Sends leave only through egress `POST /v1/support/send` (worker on hq-egress-api); the token is read for one call.
  - Tests: test_the_egress_sender_gives_the_token_to_egress_only, test_the_sweep_sets_a_telegram_webhook_once_and_only_while_unlocked, egress test_support_out (fork).
- §4.3 ok: `domain/desk.process` (worker `SupportInbound`): launch gate → opt-out / NPS / CSAT answers → loop guard → security/complaint/human handoff → the rule (top approved faq, threshold + margin 0.15: verbatim, no model) → else the support agent woken at P1 (one work item per conversation).
  - No support agent, or the day's `SUPPORT_DRAFT_DAILY_TOKENS` spent → handoff without a model.
  - `support.draft` is decided by code: grounded (every link, code and figure in the cited approved, unexpired articles) → guard → auto_send (kb_verbatim default, kb_grounded with confidence ≥ the card's threshold, off). The draft budget is also enforced in llm-router (scope `support_draft:<CO>` = the role counter `<CO>:support_agent`).
  - Tests: test_a_verbatim_question_is_answered_with_no_model_call, test_a_draft_with_a_link_not_in_the_article_is_blocked_and_queued, test_with_kb_verbatim_a_sound_draft_still_waits_for_the_owner, test_with_kb_grounded_a_checked_draft_goes_and_a_figure_not_in_the_article_waits, test_once_the_draft_tokens_of_the_day_are_spent_the_next_message_is_handed_off, test_a_message_without_an_article_wakes_the_support_agent_once, llm-router test_a_companys_support_drafts_stop_at_the_daily_draft_budget.
- §4.4 ok: a handoff puts the conversation in waiting_owner and the customer gets the sealed `holding_reply` (live channels only). The owner's digest gets one batched line per company every `SUPPORT_HANDOFF_DIGEST_MIN`. A security handoff is urgent, at most 3 a day per company (then report). Test: test_a_company_without_a_support_agent_hands_off_with_the_holding_reply.
- §4.5 ok, groundwork only: the agent asks for the UID and uses `referral.check` (r10a's tool). The verbatim/draft path then gives the article. The rescue case is r10a's (§3).
- §4.6 ok: 20 automatic replies an hour per conversation (the 21st stops: paused `auto_reply_cap` + handoff). `SUPPORT_DAILY_OUTBOUND_CAP` per company (automatic: failed `send_limit` + handoff; the owner's reply: 429 `send_limit` + Retry-After). A bot loop (the same text 3× or 6 messages in 2 min) is paused and handed off. Test: test_the_twenty_first_automatic_reply_of_an_hour_stops_and_hands_off.
- §4.7 ok: on close the sealed csat rule (if active) asks 1..5; the reply sets `csat` on that conversation. Code: lifecycle.on_closed / take_answer.
- §4.8 ok: customer text is data. An instruction-like message ("Ignore your rules…", "admin link") is a security handoff; a draft that follows one fails grounded or the guard. Test: test_an_instruction_inside_a_customer_message_gets_no_link_out.
- §4.9 ok: API per §19.3 (channels, conversations, reply/teach with Idempotency-Key required, close, queue). Stream topic `support`: support.message, support.queue, support.channel. Tests: test_a_shadow_channel_sends_nothing_to_telegram, test_the_same_reply_key_sends_one_message_and_the_guard_binds_the_owner_too.

### §5 Knowledge base, teaching mode, shadow test, go-live
- §5.1 ok: versioned articles (faq, policy+key, procedure, referral, official_link, safety), each with source and expiry (180 days; the support lead gets review work 14 days before, when hired). Expired = no automatic answer and no valid citation.
  - Approve: 🔏 `support.kb` = `ref@version`; the ref's earlier approved version (or an older approved article with the same policy key) is retired.
  - An agent's proposal (`kb.propose`) carries no link or code and is masked.
  - Tests: test_an_article_is_approved_only_with_step_up, test_an_expired_article_no_longer_answers_by_itself.
- §5.2 ok: teaching queue `GET /support/queue` (handoffs, drafts waiting, guard refusals, the latest shadow disagreements). `/reply` and `/teach` send at once through the guard and make a masked proposal (`source: owner_answer`). With a support lead, a generalising work item. Test: test_the_owner_teaches_and_a_masked_proposal_is_made.
- §5.3 ok, the real run waits for the owner: `POST /support/history` (Telegram Desktop result.json, full or one chat, or a CSV) → pairs → masked → at most 100 cases round-robin across topics → the private suite `support-shadow-<CO>` (company-scoped, RLS). This step is rule-only.
  - `POST /support/shadow/{CO}/run` queues an academy eval run (purpose shadow); the worker runs each case on the §4.3 path without sending and judges it by code (guard, grounded) and a light judge.
  - Pass = correct ≥ 90% AND zero safety failures AND zero wrong codes/links. The run proposes both thresholds.
  - Tests: test_the_history_becomes_a_private_masked_suite_of_at_most_100, test_the_history_parsers_and_the_thresholds, test_the_shadow_run_waits_while_the_holding_is_locked.
- §5.4 ok: on a pass, one `support_go_live` card per channel in shadow, plus the owner's decision notification about Premium. The card's seal (🔏 `decision.approve`) puts the channel live with exactly the card's thresholds. The thresholds have no edit route (0025 trigger).
  - The card is bound to its run: a newer run → 409.
  - Telegram Business also needs `premium_connected`; holding_reply and safety must be sealed.
  - 89% → no card; 90% with one wrong code → no card.
  - Tests: test_go_live_cards_only_on_a_clean_pass_and_the_seal_makes_the_channel_live, test_a_newer_shadow_run_supersedes_the_card.

### §6 Outbound guard
- §6 ok: `hq_common.outbound_guard`: code, not a model, one module for every outbound text (agent drafts, verbatim answers, rule templates, the owner's reply, the mystery channel).
  - Codes: asks_secret, unknown_link, unknown_code, profit_promise, customer_data, internal_data, too_long (3500), red_line (empty until prompt 11).
  - Normalisation: ي/ك, ZWNJ, Persian/Arabic digits, full-width, percent and base64/hex.
  - Links and codes must be exactly approved for the same company. No override for asks_secret, profit_promise, red_line.
  - Refusals are stored `blocked` with `blocked_reasons` (and audited); the owner gets 422 `send_blocked`.
  - The safety line goes on the first answer of each conversation and on every lifecycle message.
  - Tests: hq-common test_outbound_guard (101 table cases + 12 named, among them «لطفاً کد تأیید پیامک را بفرستید» → asks_secret, `lbank.com/ref/XXXX` → unknown_code, another company's link → unknown_link); api test_the_same_reply_key_sends_one_message_and_the_guard_binds_the_owner_too.

### §7 Templates, lifecycle rules, NPS
- §7.1 ok: templates per purpose, versioned. The owner proposes (`POST /growth/templates`) and seals (🔏 `growth.template` = `ref@version:sha256`, the server sends `seal_target`); agents propose with a `message_template` card.
  - Seed per company on first use: holding_reply, safety, csat, nps (signature «پشتیبانی Coine»), all proposed.
  - Tests: test_the_owner_makes_a_rule_without_any_agent_and_seals_it_with_step_up, test_a_template_seal_never_fits_the_same_text_in_another_company, test_an_agents_template_card_is_sealed_by_the_owner.
- §7.2 ok: rules (welcome, reactivation, rescue, nps, csat) with limits (per_customer_days, daily_cap, quiet_hours Tehran, max_follow_ups).
  - `POST /growth/rules`, then seal 🔏 `growth.rule` = `ref@version` (409 `template_not_sealed` unless its template version is sealed and current); pause needs nothing, resume 🔏; a new template version pauses the rule.
  - Seeded csat and nps rules are proposed.
  - Tests: test_an_unsealed_rule_sends_nothing, test_a_new_template_version_pauses_its_rules.
- §7.3 ok: the one entry point `hq_api.domain.growth.send_template(tx, hub, company_id=, purpose=, dedupe_key=, conversation_id= | subject=, rescue_case_id=, nps_wave_id=, follow_up=, variables=)` (for r10a's rescue and feedback).
  - Order: gate → active sealed rule and current sealed template → opt-out → per-customer days → quiet hours (held, retried by the sweep) → daily cap → live channel and Telegram's rules → guard with the safety line → queued for the worker.
  - Opt-out words stop every rule of the company for that customer for good.
  - Test: test_quiet_hours_the_daily_cap_and_opt_out.
- §7.4 ok: quarterly waves `NP-<y>Q<q>-<CO>` (default RRULE every 3 months, 1st, 10:00 Tehran; open 14 days), a random sample with a conversation in 90 days, 0..10 answers. Score = %promoters − %detractors; comments go to feedback.signals; `nps.closed` on close. Test: test_the_nps_score_and_a_wave.
- §7.5 ok: welcome and reactivation say they have no candidates until CR-009/010 (`note_fa` on the rule).

### §9 Intake and the CRs
- §9.1 ok: three Caddy routes, the only public ones prompt 10 adds, each body ≤ 1 MB. Telegram: its ranges at Caddy and again in the api, plus the secret token. Chatwoot and product: HMAC-SHA256 over `"<ts>.<body>"`, ±300 s, one nonce per event id, each source's IP list.
  - A refusal is 401/403/413/429 with no detail and writes one counted row only.
  - Secrets: `make intake-secret`, `make telegram-bot-token`.
  - Tests: test_the_telegram_webhook_checks_its_secret_ip_and_update_id, test_signed_product_events_stale_and_repeated_ids_are_refused, test_a_chatwoot_message_is_signed_and_stored, test_unknown_companies_and_oversized_bodies_say_nothing, test_identity's unauthenticated sweep; infra.sh caddy (intake routes, 2 MB refused, Telegram-only, /internal 404 with the api on and off); compose-rules (no new port).
- §9.2 ok: `GET /intake/sources` (configured = the secret's presence; last event; 24 h counts) and `POST /intake/sources` 🔏 `intake.source` (body hash), which moves the channel not_configured → shadow, never live. Product events are stored masked with the UID's pseudonym; `support_message` enters the desk on product_bot; other kinds await r10a's handlers (`intake.APPLIERS`). Test: test_sources_need_step_up_and_put_their_channel_in_shadow.
- §9.3 ok: CR-005, CR-009, CR-010, CR-011 written in `docs/ops/change-requests/` (with an index and a template); CR-007 marked "replaced". Nothing runs in the product repos.

### §10 Chatwoot (built, not deployed)
- §10 ok: software key `chatwoot` (opt-in: never in a rule-made plan; founding uses `DEFAULT_SOFTWARE`).
  - `infra/provisioning/templates/chatwoot.sh`: Chatwoot CE v4.18.0-ce + pgvector + redis + caddy, pinned by digest; ~2.2 GB of limits for a 2 vCPU / 4 GB server; secrets made on the server; only 443; nothing starts until the owner runs `chatwoot-start <domain>`.
  - The Chatwoot adapter is egress `POST /v1/support/send` (method `message`) and the intake route. Tests use a fake Chatwoot.
  - No server is made, HQ_PROVISIONING stays off. On the hub it does not fit: full profile 10896 of 12486 MiB, so +2.2 GB fails the memory gate.
  - Tests: provisioner test_cloudinit, provisioning.sh bench, egress test_support_out, api test_a_chatwoot_message_is_signed_and_stored.

### §11 Overseer
- §11 ok: `support.mystery` (overseer only): a mystery customer on the `mystery` channel through the whole §4.3 path. It never reaches Telegram/Chatwoot (recorded sent) and is left out of the conversation list, the queue, the outbound counts and the funnel. A company with no live channel → `deferred`. `{company, conversation}` reads a mystery transcript back.
  - PR-043, PR-101, PR-102, PR-103 are seeded from the file as they are, all paused. PR-043's gate: holding locked → skipped; no live channel → deferred.
  - Checkers: PR-101 re-guards the day's automatic messages and leaves unexplained refusals undecided; PR-102 is skipped with no automatic answer in the week; PR-103 flags days marked complete with gaps, or whose sum ≠ coins.
  - Tests: test_the_mystery_customer_never_reaches_telegram_or_the_statistics, test_the_support_protocols_are_seeded_paused_and_pr043_defers_without_a_live_channel, test_pr101_finds_an_automatic_message_with_an_unapproved_link.

### §12 (the desk's part)
- §12.2 ok: gateway tools `kb.search` (A0), `kb.propose` (A1), `support.draft`, `support.handoff`, `support.mystery` (A2) in `hq_gateway/support.py` and `tool_status`.
  - Internal API under `/internal/v1/support/*`.
  - OPA `support_desk.rego` (100% covered): kb.propose and handoff for the company's support lead and agent; draft for its support agent only; mystery for the holding's overseer only. A2 grants: employee draft/handoff, overseer mystery.
  - Employees, managers and CEOs may propose message_template/lifecycle_rule; decisions.rego knows the three new kinds.
  - The rescue specialist has no send tool. Another company's `kb.search` → 403.
  - Tests: gateway test_support_tools, OPA support_desk_test.rego, api test_kb_search_of_another_company_is_refused_and_tools_are_the_charters, test_support_draft_and_handoff_through_the_internal_api.

### §13 Memory and token estimate
- No new container and no new port. Work runs in api, worker (one more network) and egress (one module). The live memory measurement (`docker stats`) is for the parent's deploy.
- **Tokens:** verbatim answers cost 0. A model draft is the support agent's run (Haiku 5.5): 2 steps (kb.search, then support.draft) of about 4.5k input each (charter ~2.5k, brief and transcript ~0.6k, results ~1.5k) plus ~0.6k output. That is ≈ 10k tokens per drafted message.
  - Example: 50 messages a day per company, 60% without a verbatim article at first ⇒ 50 × 0.6 × 10k = 300k/day. The cap `SUPPORT_DRAFT_DAILY_TOKENS` = 60k holds it to about 6 drafts a day; the rest are handed off without a model.
  - With a mature knowledge base (25% without an article) ⇒ 50 × 0.25 × 10k = 125k/day, still capped at 60k unless the owner raises it.
  - A shadow run (academy budget, only when the owner asks) is at most 100 × (~4k draft + ~1.5k judge) ≈ 0.55M tokens; verbatim cases that match the owner's words cost 0.
  - Support counts under the company's monthly budget.
- Real-model tokens spent in this work: 0.

### Checks (HQ_TEST_IMAGE_TAG=u1)
- services: hq-common, llm-router, gateway, egress and provisioner tests all passed (total coverage 89%; outbound_guard 95%, gateway support 93%, egress support_out 85%). Lint (ruff, format, mypy strict) is clean for services and apps/api. OPA passes 110/110 at 100% coverage.
- shellcheck, compose-config, compose-rules, memory-budget (full 10896 of 12486 MiB, unchanged) and infra.sh (caddy intake routes, /internal 404) are green. openapi was regenerated: additive only.
- api: every p10 file passes (desk, intake, kb_lifecycle, foundation), and so do test_identity and test_openapi.
  - An earlier full run had 3 failures, fixed since: a stale openapi document, one missing description, and the code checkers of paused protocols.
  - One run of test_oversight::test_a_judgement_protocol_is_the_overseers_work_within_the_daily_cap failed once after the fuzzing. It passed alone, with test_every_code_checker_runs, and with test_openapi before it, so it looks flaky.
  - The final full api run on a fresh database was stopped by the usage limit, so the parent's make check is the full run.
- gitleaks: 3 findings, all in main's apps/web and apps/android mock fixtures (not this branch's files).

### Support (status)
- Done (code and tests): §4, §5 (the real shadow run waits for the owner's history), §6, §7 (`growth.send_template`), §9 (routes, sources, secrets, CRs), §10 (built, not deployed), §11, §12 desk tools and OPA, and the §13 estimate.
- Partly done: §4.5 relies on r10a's `referral.check`, `rescue.update` and rescue cases. Intake product events other than support_message wait for r10a's `intake.APPLIERS`.
- Not started: none.
- Tests not yet run: the final full api suite on a fresh database (the parent's make check); infra.sh's caddy part ran green; the live `docker stats` after deploy.

### Contract notes
- Caddy's stock image has no rate limiter: Caddy caps the body; the api counts calls per source (`INTAKE_RATE_PER_MIN`, 120) and per company before any row.
- `send_blocked` carries its reasons in `fields.blocked_reasons` (comma-joined: Problem.fields is string to string).
- `support.mystery` also takes `{company, conversation}` instead of `question_fa`, to read the mystery transcript back (the agent's draft arrives later).
- A repeated webhook or event id answers 200 (`{"duplicate": true}`) so senders stop retrying. Only one counted refusal row is written.
- The Telegram route validates `channel` in the handler, so every unauthenticated call gets 401.
- The owner's own reply goes while the holding is locked (it is the owner's act); every automatic send waits. The owner's replies count toward `SUPPORT_DAILY_OUTBOUND_CAP`.
- Before a go-live card a company has no thresholds: shadow and mystery use 0.9 for the verbatim rule (no channel is live anyway).
- Action classes: message_template A2, lifecycle_rule A3, support_go_live A3. All three are sealed with step-up and applied in the deciding transaction (bound to their payload: a newer template/rule version or a newer shadow run → 409).
- Schema names: `MessageTemplate` (the name `Template` is org's), `KbLink`/`KbSource`/`KbCode`/`KbVariable`. Template gains `seal_target`. SupportChannel gains `premium_connected`. Conversation gains `version`. QueueItem gains `reason`. LifecycleRule gains `note_fa`. The KB approve body is `{version?}`.
- A new template version pauses its active rules (`template_new_version`). Running again takes a rule version on the new template version (rule rows are immutable).
- One go-live card per channel in `shadow`; a channel enters shadow when its intake source is registered.
- Product events: `subject` is the product's UID or user id. It becomes the pseudonym with channel `uid:<exchange>` when `data.exchange` is given, else `product_bot`.
- NPS default RRULE `FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=10;BYMINUTE=0` (Tehran), a wave open 14 days.

### Owner tasks (support)
1. Seal each company's `safety` and `holding_reply` templates; write and approve the basic articles: `vip.min_balance`, the referral code and link, the official links, the VIP rules.
2. Give the real support history (Telegram Desktop export or CSV) through /files and `POST /support/history`. The shadow run needs the hub launched (model tokens).
3. For `telegram_bot`: create the bot in BotFather, run `make telegram-bot-token COMPANY=… CHANNEL=telegram_bot`, and register the intake source (🔏).
4. After a pass: buy Premium, connect Business → Chatbots, and seal the `support_go_live` card.
5. Decide on Chatwoot (§10) and on CR-005, CR-009 to CR-011. For product events, run `make intake-secret COMPANY=… SOURCE=product` and register the source with its IPs.

### Gating (support)
- Gated on `gate.automation_lock`, doing nothing while the holding is locked (tested): SupportInbound (process), automatic SupportSend, SupportSweep (expiry, reminders, digest, lifecycle retries, NPS, webhooks), SupportShadow, `send_template`, PR-043.
- Not gated:
  - The owner's own reply (no channel is live).
  - The intake webhooks: they only verify and store, with no model and no outside call; the messages wait.
  - The history import: rule-only.
- No real Telegram or Chatwoot call (fakes in CI); zero real-model tokens; HQ_PROVISIONING untouched.
