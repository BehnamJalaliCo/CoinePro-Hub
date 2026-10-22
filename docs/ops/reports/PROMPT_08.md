PROMPT_08 REPORT (Chief Overseer, advisor v2, assistant, stars, hiring, stories, skills, academy) — code only

- **Not deployed and no migration on the live database** (owner, 2026-10-18: the shared weekly limit). Branch server/p08-organisation = prompt 7 (server/p07-platform as of 3a468a3 + fixes) + prompt 8; migrations 0018-0022 exist only in code
- §1 kinds overseer/assistant, HQ-OVR (thread N, dept OVS) and HQ-PA (thread P) seeded from the holding template, HQ-OVS-MGR reports to HQ-OVR, Employee.rank, /meta precedence; N and P wake their agent at P2; only that agent posts there
- §2 oversight (0019): protocols seeded from agents/protocols/oversight.yaml (52 in 11 areas), one Temporal schedule each (paused with HQ_OVERSIGHT_SCHEDULES=off), 23 rule/reconcile protocols as code; model-backed ones as work for the overseer or QC, capped (HQ_OVERSIGHT_MODEL_RUNS_PER_DAY=3, 60K tokens a run: at most ~180K/day + ~60K/week of challenges); findings + history, challenges, standing orders (owner's seal), holds enforced on approvals, effects, the gateway, workshop sessions and stories; watch mode (Khalvat, 6 h away, or the owner) holds high-risk cards, never approves; compliance daily; PR-070 from the backup hook
- §3/§5 (0020): inquiries (Q-…; the asked one is woken at P1, the answer lands in the asker's thread, late → notification and compliance), advisor v2 read tools; errands (E-…) from thread P, errand.step/finish, planner.add (PL-…), errand_action (A3) → the owner; nothing commits without the seal
- §4/§8/§9 (0021): star rubrics (efficiency ≥ 15%), stars (no reason/evidence = not counted), weekly/monthly roll-ups, company score = 35 KPI + 20 challenges + 15 compliance + 15 people + 15 efficiency (pure function, ledger only; KPI null until a KPI store exists), inflation → PR-080 finding, lessons and adoption; delegated hiring (envelopes, approver = the CEO, hire.decide, hard checks, probation, hire story, report notification, PR-098 review); stories (system + story.post 3/day, redacted, own images, held ones hidden)
- §6/§7 (0022): skills (SK-001..003 seeded in review), code pre-check then overseer review then eval then the owner's seal; active skills and sealed addenda after the charter, versions on the run and in llm.calls.meta; academy suites from agents/academy, eval runs with a judge, gate ≥ baseline − 1, teaching → addendum/skill, training records, monthly academy cap
- Tests: api 331 passed (fresh env), services 435, OPA 98/98 (100%); acceptance tests of §1-§9 present and passing (fake model only). Merge fixes found by the suites: duplicate propose_kinds keys (OPA), PR-034 against the skills schema, PR-080 one finding not two, held story release
- Real-model spend: 0 tokens (no live run: not deployed)
- Contract notes: in each fork's notes (kept in the commit messages); main ones: new codes held 423, envelope_required 422, envelope_exceeded 409, story_limit 429, academy_budget 409; inquiry.late and academy.teaching events; planner items PL-…; errand_action payload; an approved charter_rule becomes a server-side addendum (agents/ never edited); hold target kinds decision/session/work/employee/tool/story
- Merged with server/p07-platform ea193ac (the review of 6 and 7) on 2026-10-22: make check (HQ_TEST_IMAGE_TAG=m8) all 16 gates green (services 539 passed + 1 skipped, api 400 passed, coverage 89% / 87%, OPA 99/99 at 100%; live PASS on the running prompt-7 stack with only 7.1's by-IP GAP lines); 0018 now follows 0017_6, the kind CHECKs of 0019-0021 carry tool_enable; still not deployed (waits for the consultation session's review). New prompt-8 items (§2.2-§2.3, contract §18.1 v1.4.4): (a) `status: paused` protocols are seeded paused with no schedule (a stale one is removed), no run, no finding, and leave compliance (test_paused_protocols_have_no_schedule_run_or_finding_and_do_not_count); (b) OVERSIGHT_DAILY_SHARE (default 0.2, .env.example, RUNBOOK §21): llm-router stops the holding's overseer and QC at that share of AGENT_DAILY_TOKEN_CAP (429 budget_exhausted, ledger oversight_share) except a critical protocol's run; protocol_run records `deferred` for the rest, the next UTC day's first tick runs them first, compliance never counts them; a code check that passes never wakes the overseer, a failure or an undecided result wakes it once a day with only the evidence the code collected (test_with_the_share_spent_a_high_protocol_is_deferred_and_a_critical_one_runs, test_the_oversight_share_stops_overseer_and_qc_but_not_critical, test_a_code_check_that_cannot_decide_wakes_the_overseer_with_its_evidence, test_oversight_share.py); (c) every protocol/challenge work budget is min(HQ_OVERSIGHT_RUN_TOKENS, the assignee's charter) and a run's cap never exceeds its charter, so no overseer or advisor run passes 200000 tokens (test_the_overseer_and_the_advisor_are_capped_by_their_charters; the critical run above is claimed at 200000 with HQ_OVERSIGHT_RUN_TOKENS=900000)
- For the owner when 8 is deployed: the overseer's daily model-run cap (3) and tokens per run (60K); watch_after_hours (6); activating the seeded skills; the academy cap; envelopes in /budgets before delegated hiring

## Review of 8 (prompt 8.1, contract §18.15)

Branch `r81` (stage A1 of RUN_2026-10-22_A_TO_D), not deployed. Migrations: none added. 0019, 0021 and 0022 were edited in place, which is allowed because prompt 8 is not deployed.

- **Merges ok:** base origin/server/p08-organisation 500932c. Main merged exactly up to 19dda76 and no further, so main's prompt-10 charters stay out. Then origin/server/p07-platform 8661551. Both merges were clean. The live backup fixes are kept as they are: the Drive folder «CoinePro HQ Backup», restic's TMPDIR on the repository's disk, and gdrive-auth's link-and-code flow with own=1 (infra/backup and scripts/quality/backup.sh are identical to p07). OpenAPI was regenerated after the fixes.
- **§1.1 ok:** `cancel` now cancels the action itself, so nothing held ever runs afterwards:
  - a pending card is rejected by the owner («لغو از hold»);
  - a queued effect becomes `effect_status = cancelled`, and an approved card's open follow-up work is cancelled;
  - a workshop session is stopped (`hold_cancelled`);
  - a work item is cancelled with its children.
  Only `release` lets the action go on. Test: test_a_cancelled_hold_cancels_the_action_and_nothing_held_ever_runs; test_oversight's hold test now expects `cancelled`.
- **§1.2 ok:** the overseer's engage takes the switch over unless the owner or the overseer already holds it. A CEO that engaged first gets 403 when it tries to release. Test: test_the_overseer_takes_over_a_switch_a_ceo_engaged_first.
- **§1.3 ok:** a hold on a session marks it held `hold` and interrupts it at once on its runtime. While it is held:
  - nothing it reports is taken (no step, no approval, no push); only its spend is counted;
  - messages and approval allows get 423.
  A release lets it go on, or start, or wait in line if it never started. Test: test_a_hold_interrupts_a_running_session_and_a_release_lets_it_go_on.
- **§1.4 ok:** every hire approval of a company runs under one advisory lock. `committed` counts approved hires whose employee is active or not made yet. The estimate comes only from payload.quota_estimate_month. The five-a-day guard runs under the same lock. Tests: test_two_approvals_over_the_envelope_one_is_refused, test_the_sixth_hire_of_the_day_is_refused_under_the_lock (both concurrent).
- **§1.5 ok:** `name_fa`, `summary_fa` and `scope` belong to each version. A PUT leaves every prompt unchanged until the new version is activated. Test: test_a_put_on_an_active_skill_changes_no_prompt_until_the_new_version_is_activated.
- **§1.6 ok:** the reviewer sees the exact masked text, fenced as data, with its sha256. A `pass` needs all four checks true and the same sha, otherwise 422. Teachings work the same way (`proposal_sha256`). The pre-check refuses the five sentences and their likes in Persian and English. Tests:
  - test_the_precheck_refuses_the_five_sentences_and_their_likes
  - test_the_reviewer_sees_the_fenced_text_and_a_pass_needs_its_sha_and_all_four_checks
  - test_a_teaching_review_sees_the_proposal_and_changes_send_it_back
- **§2.1 ok:** the gateway's ProposeIn, decisions.rego and the `GET /decisions` kind filter already had `protocol` and `errand_action` from the merge (5428dc4). Tests added: test_the_overseer_proposes_a_protocol_and_the_owner_seals_it, OPA test_a_protocol_card_is_the_owners_alone.
- **§2.2 ok:** `skipped` is gone:
  - it is out of 0019's CHECK, and `last_run.result` is typed;
  - past HQ_OVERSIGHT_MODEL_RUNS_PER_DAY a run is `deferred` and goes first the next day; a `critical` one is never stopped;
  - the count is taken under an advisory lock, and the token share on the ledger is as built in e6538cd.
  Test: test_the_count_cap_never_stops_a_critical_protocol_and_nothing_is_skipped.
- **§2.3 ok:** watch mode now holds the cards a CEO decides as well. A card the owner released or cancelled in the same watch is not held again (`oversight.watch_since()`). Release and cancel write owner.interactions. Test: test_watch_mode_holds_a_ceos_card_and_not_again_what_the_owner_released.
- **§2.4 ok:** a held or company-locked effect sleeps `retry_in_s` between attempts. Test: test_an_effect_held_or_under_a_company_switch_waits_without_spinning.
- **§2.5 ok:** `protocol.result` records pass or fail for every company the protocol covers. Test: test_a_model_protocols_result_records_pass_for_every_company_it_covered.
- **§2.6 ok:** only the answerable or its chain of command sets acknowledged, fixing, fixed or disputed. `verified` comes only after a `fixed` whose fix carried evidence; the verifier's own evidence does not count. Test: test_only_the_answerable_or_its_chain_moves_a_finding.
- **§2.7 ok:** a paused protocol is refused on every path:
  - `protocol.result` and `finding.raise` answer 409;
  - PR-070, PR-080 and PR-098 skip it;
  - it has no schedule.
  Tests: test_a_paused_protocol_is_refused_on_every_path, test_pr098_review_only_while_the_protocol_is_active.
- **§2.8 ok:** `hire.decide` works only in mode delegated. Switching to proposals gives the pending cards back to the owner and closes the CEOs' decide items. `after_hire` keys on decided_by_kind, so an owner-first hire gets no probation line. Tests: test_proposals_mode_returns_cards_to_the_owner_and_stops_hire_decide, test_a_card_the_owner_approves_first_is_the_owners_hire.
- **§2.9 ok:** an active skill stays in every prompt while a new version is in review (filter on active_version and the version's status). PR-034 follows the same rule. Test: the §1.5 test.
- **§2.10 ok:** a run with a failed call is `failed` with passed=false. A first good run only sets the baseline. Activation and approval re-check the current baseline. Test: test_a_run_whose_call_fails_is_failed_and_a_first_run_only_sets_the_baseline.
- **§2.11 ok:** queued and running runs reserve an estimate under a lock (409 academy_budget). Tokens are written after each case, and a crash or timeout fails the run (`academy_eval_failed`). Test: test_queued_runs_hold_the_cap_and_a_crashed_run_is_failed.
  - Bug found and fixed: the internal routes computed the cap inside the agent's own RLS scope, so the cap was never really enforced.
- **§2.12 ok:** `prompt_section` returns only what it really included. A skill body over 6,000 characters is refused when it is written. Tests: test_the_prompt_section_says_what_it_really_holds, test_a_skill_over_the_limit_is_refused_when_written.
- **§2.13 ok:** at most 30 skills and 30 addenda are named on a call. New route `POST /academy/addenda/{id}/retire` 🔏 academy.approve, target = its teaching ref. Test: in the §2.14 test.
- **§2.14 ok:** a teaching aimed at one employee becomes that employee's addendum only. Test: test_a_teaching_of_one_employee_is_its_addendum_and_an_addendum_can_be_retired.
- **§2.15 ok:** each new weekly or monthly roll-up gives the overseer one work item «درس از …، …». No item is made while the holding is locked. Test: test_a_roll_up_wakes_the_overseer_for_its_lessons_but_not_under_the_kill_switch.
- **§2.16 ok:** `lesson_adoption` is sealed with step-up. A returned, expired or withdrawn card frees the lesson to be proposed again. Test: test_lesson_adoption_needs_the_seal_and_reopens_after_return_or_expiry.
- **§2.17 ok:**
  - `links.period` must match `^(week|month):…$`;
  - outside links are refused with or without a scheme (`t.me/x`, `evil.com/promo`);
  - a milestone must link work, a deliverable or a metric.
  Tests: test_outside_links_with_or_without_a_scheme, test_story_period_metric_and_milestone_evidence.
- **§2.18 ok:** the owner's welcome adds +0.2 to the employee score in that month (`owner_welcome`). Test: in test_a_card_the_owner_approves_first_is_the_owners_hire.
- **§2.19 ok:** rubric weights are stored and served as numbers. Test: test_rubric_weights_are_numbers_and_stars_are_whole_or_half.
- **§2.20 ok:** `Run` gains `skills: ["SK-001@3"]` and `addenda`, taken from what was really in the prompt. Test: in test_skills_academy.
- **§3 a–j ok:** built exactly as the table of §18.15:
  - `GET /academy/runs` and `recent`;
  - `baseline {subject, score}|null`;
  - EvalRun `state`, `tokens {input, output}` and `equiv_cost_usd`;
  - the runs of a suite are a Page, newest first;
  - `trend` is the last 12 scores;
  - `resources` are FileRefs;
  - `Skill.eval` and `Teaching.eval_run`;
  - the `POST /skills` body.
  Test: test_academy_shapes.
- **§3 k ok:** `Protocol.last_run.result` is one of `pass|fail|partial|deferred`. Test: in the §2.2 test.
- **Daily cap ok** (run sheet): AGENT_DAILY_TOKEN_CAP=0 now means nothing, not "no cap".
  - Every run is refused with `daily_cap`, at claim and before every model call.
  - The oversight share of 0 is 0, in the api and in llm-router.
  - AGENTS.md and RUNBOOK are updated.
  Tests: test_a_daily_token_cap_of_zero_means_nothing_runs, hq-common test_limit_and_spent, llm-router test_integration_ledger.
- **Holding lock ok** (run sheet): while the holding kill switch is engaged, none of prompt 8's own jobs does anything:
  - a protocol schedule's run makes no run row, no work and no model call;
  - the tick resumes no deferred run;
  - the weekly challenge item, the lesson item and the stars reminder are not made;
  - late inquiries are not marked;
  - an eval run fails `holding_locked` before any model call.
  The rest of the tick (watch mode, missed challenges, compliance) is rule-only: no model and no outside call. Tests: test_oversight_runs_nothing_on_its_own_while_the_holding_is_locked, test_no_eval_runs_while_the_holding_kill_switch_is_engaged, the §2.15 test.
- **§4 done:**
  - a hold on an approved card also stops its follow-up work;
  - a challenge is scored only by its judge or the overseer;
  - watch holds name the holding's own overseer;
  - `protocol.result` takes only findings of that protocol or of the caller;
  - half stars are validated (422 with the field), and criteria are refused without a rubric;
  - an errand's cancel withdraws its pending errand_action card;
  - «تصمیم D-…» items close on withdraw;
  - the envelope month starts at the owner's midnight;
  - a held or cancelled story never shows in the rings or the archive;
  - OPA gives `skill.review` only to the oversight roles, and `academy.eval`/`academy.teach` only to the holding's AIOPS;
  - a `changes` verdict sends a teaching back to drafting;
  - a memory proposal with a role target is refused at the draft.
- **§4 not done** (left for after deploy):
  - `star.give` filling `efficiency` from the ledger;
  - the errand cost index;
  - `/inquiries` and `/errands` cursors;
  - a late inquiry counted again in PR-051 after its answer;
  - seeded skills' review items (they would wake HQ-OVR at bootstrap);
  - `academy.approve` bound to the proposal digest;
  - the `accepted` challenge state.
- **Migrations, in place:**
  - 0019: `protocol_runs.result` without `skipped`, `effect_status` gains `cancelled`, `workshop.sessions.held` gains `hold`, and `oversight.watch_since()`.
  - 0021: hq_api may update decisions' approver_kind and approver_code.
  - 0022: versions' name/summary/scope and sha; eval tokens, cost and reservation; teaching sha; employee addenda and their retirement; `runs.addenda`.
- **Contract notes:**
  - `CodeSession.held` gains `hold` (the overseer's hold).
  - `Decision.effect_status` gains `cancelled`.
  - `Story.links.metric`.
  - The `owner_welcome` score component.
  - `EvalRun.error`, and `Budget.reserved_tokens` in academy.
  - `skill.review` may pass `sha256`; when it is missing, the version's own sha is recorded.
  - A skill body or a teaching proposal is at most 6,000 characters.
  - POST/PUT `/skills` require `scope.roles` and `scope.companies`.
  - The `protocol.result` of a holding-scope protocol counts for the holding only.
- **Tests:**
  - api: 437 passed on a fresh database
  - services (hq-common, gateway, llm-router): 383 passed
  - OPA: 100/100 at 100%
  - lint and mypy clean; OpenAPI regenerated
- **Real-model spend:** 0 tokens; nothing was deployed.
- **Deploy (2026-10-22, one deploy of 8 + 8.1 + 9 + 9.2 at `server/p09-founding` 62fbe77):** backup first (snapshot a559d46e, local + Google Drive ok); `make up` ran migrations 0017_6 → 0018 → 0019 → 0020 → 0021 → 0022 → 0023; 22 services healthy; `make verify-live` passed (only the known GAP lines: egress and SearXNG reach the neighbours and metadata by IP, the owner's DOCKER-USER rule). Full `make check` green before it (services 623, api 449, OPA 104/104, provisioning bench incl. bad Node sha256 and failing `sshd -t`, backup, live; gitleaks needed three identifier keys in the apps' demo fixtures allow-listed). The holding kill switch stays engaged and HQ_MORNING_REPORT_LLM=off: zero model calls since the deploy, no run, no protocol woke; HQ_PROVISIONING off (no provisioner container, no Hetzner token read). Memory after deploy: 2.65 GiB in use; the highest is Temporal at 71% of its cap.

این گزارش را برای Claude سشن مشورت ببر.
