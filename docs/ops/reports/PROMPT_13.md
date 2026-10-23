PROMPT_13 REPORT (the media studio of every company and the holding's legal counsel)

## Branch and state
- Branch **r13j**: the media half **r13a** (§1, §1.1, §2; head 038fcd1) with the legal and voice half **r13b** (§3, §4; head a6b971c) merged into it. Both halves started from `dev/p13-base` 4f59c82 (prompt 10 + prompt 12's parts A and B joined + main up to "Prompt 13 sent"); nothing else is merged. Prompt 11 and prompt 12's final branch are laid under it later by the parent. **Not deployed.**
- **Migrations:** `0027_1` → **`0028`** (`0028_media_studio.py`, the media half) → **`0028_1`** (`0028_1_legal_voice.py`, the legal and voice half; the head).
  - Decision kinds: 0028 adds `media_series`, `media_publish` and `role_new`; 0028_1 adds `email_send` (one owner each). Both rewrite `decisions_kind_check` from the kinds it holds, **NOT VALID**.
  - 0028_1 is the last and **validates** `decisions_kind_check` and `threads_kind_check`. Every earlier re-add of them is NOT VALID (0014–0023 already were; 0018's thread CHECKs, 0025's and 0028's kind CHECKs now too), so test_hiring's down-and-up run keeps every later revision's rows.
  - The 0018 and 0025 edits do not touch deployed databases (those revisions already ran there).
- **Hub state kept:**
  - The holding kill switch and `HQ_MORNING_REPORT_LLM=off` are untouched; `HQ_PROVISIONING` is off.
  - No owner login, key, token or recording was used or asked for: Telegram, Instagram and the counsel's mailbox stay off until the owner sets them.
  - The opt-in profiles `media` and `tts` are built and **off**. No published port.
  - No real model, platform or outside call in CI (a fake model, a fake Telegram, a fake Graph API, a fake SMTP/IMAP). Real-model tokens spent: **0** (the §0.5 sample reel was not made, per the run sheet; its cost is estimated below).
- **What could wake a model or an outside call, and its gate** (each with a test that it does nothing while the holding is locked):
  - `hq-media-sweep` (every 5 min: the sealed series' schedules, due publishing, the rule re-check of published items) asks `gate.holding_lock` first and does nothing at all while the holding is locked. A locked company's series and items wait.
  - `hq-legal-mail-poll` (every 5 min): no mailbox call and no work while the holding is locked; without the `mail` account nothing either.
  - `hq-voice-bakeoff` (daily 03:40): nothing while the holding is locked.
  - The one-shots' claims answer 204 while the holding is locked: the render queue (`/internal/v1/media/render/claim`) and the TTS queues (`/internal/v1/tts/claim`, `/internal/v1/voices/jobs/claim`). An item's render and narration also wait while its own company is locked (kill switch or deploy freeze).
  - Publishing (the sweep's, and the one after a card's seal) stops for the holding lock, a company kill switch or deploy freeze, holds and watch mode. The sealed email's one send is the card's effect in the worker, which waits while the holding or the company is locked or the card is held.
  - Agent runs (the pipeline's steps, the counsel's cases and replies) are refused while locked; every agent write is 423 then. The steps' work items are records only.
  - The owner's own unpublish (sealed) runs when the owner asks; it only takes posts down.
  - Rule-only work: the re-check of published items touches no model and no outside service, and it still sits behind the holding gate inside the sweep. The TTS output's transcription skips the model punctuation pass (synthetic speech). Nothing rule-only runs while the holding is locked.
  - Tests: test_nothing_runs_while_the_holding_is_locked, test_the_company_kill_switch_holds_scheduled_publishing, test_the_poller_does_nothing_while_the_holding_is_locked, test_the_bakeoff_and_the_tts_job_do_nothing_while_the_holding_is_locked, test_a_narration_given_up_lets_the_item_go_on_silent (the company lock).

## Merged on 12 (r13f)
- **Merged on 12:** branch **r13f** = r12f d23b5c8 (prompt 11 deployed + prompt 12 parts A and B + §2, §3, §13) + r13j 5824aec + origin/server/p12-management-tools up to 5ea5f18 (ae878d4: 0027's `verified_at` IF NOT EXISTS; e6bec54: a deterministic revenue refusal test; 5ea5f18: the infra/mcp scripts executable). **Not deployed**; the parent runs `make check` and deploys.
- **Chain:** `0025` → `0026` → `0026_1` → `0027` → `0027_1` → `0027_2` → **`0028`** (down_revision now `0027_2`) → **`0028_1`** (the head).
  - `0028_1` is the only revision that validates `decisions_kind_check` and `threads_kind_check`, holding every kind of 11, 12 and 13. `0026_1` and `0027_2` no longer VALIDATE (each did while it was the head); every earlier re-add stays NOT VALID.
  - These edits do not touch a deployed database (0026_1 and 0027_2 already ran there); production upgrades from 0027_2 with 0028 and 0028_1.
  - test_hiring's round trip (down to 0009, up to the head, then r12f's re-seed) passes. test_p13f_join runs one more round trip, with a card of each of 11's and 13's kinds and thread L: all kept, both CHECKs validated.
- **Conflicts** resolved as unions: decision kinds, action classes and payloads, the GET /decisions kind filter (13's four kinds beside 11's), routers, error codes, stream topics (`ask`, `reviews`, `dceo`, `media`, `legal`), internal tool classes, the OPA lists and data.json, the fixed schedules (12's owner tools, then 13's media sweep, mail poll and bake-off), workflows, activities, gateway modules, tool_status, test fixtures (12's dceo token and 13's media token; the RLS and schema-rule lists; 11's, 12's and 13's fills). RUNBOOK: §29 is 11's, §30 is 12's, §31 is 13's; §30 and §31 now name the chain above.
- **The system prompt** keeps the contract's order: `_common` → the sealed holding charter and the company's addendum (§20.2; the four red lines until one is sealed) → the role's charter (a file, or the company's role draft, §22.5) → the department's identity (§22.1) → the skills. The runner uses one library for the run: the files plus the company's drafts, for the prompt, the charter section and a meeting turn's tools.
- **Fixed where 11, 12 and 13 meet:**
  - test_p12f_join's chain test now ends at `0028_1`.
  - The advisor's tools test (test_the_advisor_v2_has_its_read_tools) passes with 11's tools live. The charter-order test (test_agents_more) passes.
  - Template departments: 13's MEDIA and LEGAL mandates sit beside 11's `HQ-SEC` and 12's `HQ-LIB`. Every department's tool ceiling is a live gateway tool, 11's governance tools among them.
  - test_untrusted_files counted spawned children by the length of `untrusted._spawned`, which keeps only the newest 64; the joined suite spawns more before it runs. It now finds the one child after the last pid seen.
  - The import order in app.py.
- **New test:** test_p13f_join (5): one validating head; every kind there and validated; the round trip above; a MEDIA run's prompt order; the templates.
- **Gates on r13f** (test name p13b, image tag p13b):
  - api, full suite on a fresh database (fuzz 8, coverage), run on a02792b: 802 passed, 1 failed (the `_spawned` cap above, fixed in b183518). Coverage 84.5% overall (gate 80%); the domain files about 91% (gate 85%).
  - After the fix, targeted: 77 passed (test_files_media, test_p13a_media, test_p13b_voices and test_tools_mcp before test_untrusted_files, so the cap is reached; test_p10_revenue with e6bec54).
  - services (hq-common, gateway, egress, llm-router, tts, media-render): 987 passed.
  - lint clean (ruff, format, mypy --strict; services and api). OpenAPI regenerated: **494 operations** (12's 447 and 13's 416, none removed).
  - OPA 170/170 at 100% coverage; shellcheck (80 scripts); compose-config and compose-rules (lean, full); infra.sh (38 checks); gitleaks (history and working tree) all clean.
  - memory-budget ok: full 10896 MiB ≤ 11673; full+media 11920 ≤ 12288; full+tts 11216 ≤ 12288. Still over: full+stt by 784 MiB, lean+media by 700 MiB (both off).
- **Test-order note:** test_founding's auditor claim answers `busy` when the test runs after test_p11_charter_knowledge or test_p13a_roles in one session (`agent_headers` leaves HQ-AIOPS-MGR a running run). In the suite's own order it runs first and passes. This is not a defect of the join.

## Items
- §0 ok (before starting):
  - The p13 charters and `tools.md` are seeded from `agents/` as they are.
  - Every new table has company_id, FORCE RLS and an audit row per change, refuses DELETE, and is in test_rls_all_tables (filled) and test_schema_rules: schemas `media` and `legal`, and `people.role_drafts`.
  - No secret is printed (`make account-secret` only). §0.9's defaults hold (Owner tasks).
- §1 ok (mandate, identity, starting team):
  - `core.departments` gains `mandate` and `identity_md`, seeded from `standard.yaml` and `holding.yaml` where empty.
    - Every department has a Persian «مبدأ و مقصد», outputs, boundaries, a tool ceiling, a model ceiling (Sonnet; MEDIA Opus) and an identity.
    - MEDIA's is written from the owner's own words.
  - `team` is read from the template and shows only charters live in `agents/roles/` for that department.
  - `PUT /companies/{code}/departments/{dept}/mandate` takes 🔏 `department.mandate` on the body hash and `If-Match`. A ceiling with an unknown, A3/A4 or never-given tool is 422.
  - `GET /templates` gains `blueprint`; `company.state` carries every department's mandate and team, plus the caller's own identity.
  - The runner puts `identity_md` after the charter and before the skills, and records `agents.runs.identity_doc` (`TY-MEDIA@4`).
  - MEDIA («رسانه و طراحی», sort 25, head `media_director`, a team of six). Existing companies get it from migration 0028: the department, its asleep manager and two threads; no employee.
  - The holding has **one** LEGAL (`manager: false`: no manager, no manager or department thread) and **one** asleep `HQ-LGL` (kind employee, charter `legal_counsel`) with thread `L` (kind `legal`).
    - 0028 makes LEGAL and HQ-LGL; the seed (holding.yaml) makes thread L.
  - Tests: test_p13a_departments.py (7), test_org_work counts, test_the_holding_has_legal_and_hq_lgl_in_thread_l.
- §1.1 ok (roles written on demand):
  - `people.role_drafts` (RD-0001), with `GET`/`POST /roles/drafts`, `GET /roles/drafts/{ref}` and `POST …/retire`.
  - `role.draft` (A1, the department head): code checks the ceiling, 422 per field. `role.decide` (A2, the CEO): delegated hiring only.
  - The gates run in order:
    1. originality (8-word runs)
    2. the overseer's review on the sha256 (`skill.review` with RD-, a fifth check `ceiling`)
    3. the draft's own academy eval (70/100 = its baseline)
    4. the CEO, or a `role_new` card (always one for the holding)
  - Activation retires the superseded version and posts a role story.
  - The runner, the hire checks and the gateway read file charters plus the company's active drafts; `GET /roles` shows `source`.
  - Tests: test_p13a_roles.py (8), roles_test.rego, gateway test_role_tools.py (4).
- §2 ok (the media studio):
  - §2.1 data: `media.series` (SR-0001), `media.items` (MI-0001), `media.compositions` (append-only, numbered, sha256), `media.render_jobs` and `media.publish_log` (append-only). `media.voices` is §4's registry.
  - §2.2 series:
    - The owner creates one (`draft`), or the media director uses `series.propose` (`proposed` and a `media_series` card).
    - The seal is `POST …/seal {digest}` 🔏 `media.series`. Editing a sealed series takes it back to `proposed`.
    - The RRULE runs in the owner's zone: one item per occurrence with the pool's next topic, at most `max_per_day`, no backfill beyond 30 minutes.
    - Tests: test_an_unsealed_series_publishes_nothing_and_an_edit_takes_the_seal_away, test_a_series_card_is_sealed_on_its_page_and_the_limit_answers_429, test_a_series_must_fit_its_kind.
  - §2.3 pipeline:
    - Each step is a work item for the least busy holder of its role in the company's MEDIA department. Code moves the item on: script → direction → composition → voice → render → checks → review.
    - The composition schema (`hq_common/composition.py`) is checked in the api and again in the worker: no network, only anime.js and lottie-web by fixed `/lib` paths, the company's own assets, IRANYekanX only.
    - The seven checks run by code. A sealed auto series with every check `pass` is `scheduled`; anything else is `waiting_owner` and a `media_publish` card.
    - Tests: test_one_item_from_its_script_to_its_publishing, test_a_failed_check_makes_a_card_not_a_publish, test_a_composition_that_reaches_for_the_network_is_refused, test_review_changes_go_back_to_the_named_role_and_a_reject_ends_it, test_a_runtime_violation_sends_the_item_back_to_its_composer, test_captions_follow_the_shots_or_the_narration, hq-common test_composition.py.
  - §2.3 voice step (joined):
    - `media.voice` queues the item's narration in the voice registry's queue (`media.speech_jobs`, kind `narration`; §4) with the active voice.
    - `voices.ON_NARRATION` (`studio.on_narration`) brings the file to the item and moves it to its render.
    - A narration given up after three tries (`voices.ON_NARRATION_FAILED`) lets the item go on silent, with captions. With the `tts` profile off, the item goes on silent at once.
    - Tests: test_media_voice_queues_the_narration_with_the_active_voice (a real item through the pipeline), test_a_narration_given_up_lets_the_item_go_on_silent.
  - §2.3 render worker:
    - `services/media-render`, in the opt-in profile `media` (off).
    - `media-courier` runs on the internal `hq-media` network (172.30.23.0/24), which reaches only the api and OpenBao.
    - `media-render` sandbox: `network_mode: none`, a read-only root, uid 10001, `cap_drop ALL` plus `SYS_CHROOT`, Playwright's seccomp, no-new-privileges, 2 CPUs, 512 pids, 600 s, `MEM_MEDIA_RENDER=960m`.
    - It renders frame by frame on a virtual clock; ffmpeg makes H.264/AAC, a poster and WebVTT.
    - Tests: media-render tests, compose-rules, the bench's probe and "sneak" run, live.sh.
  - §2.3 publishing:
    - egress `POST /v1/media/publish`, official APIs only: the Telegram Bot API, and the Instagram Graph API with `is_ai_generated: true`.
    - The signed URL is one file for ≤ 15 minutes; any other URL is 404.
    - Instagram's 50 a day → 429 `platform_limit`. Unpublish is 🔏 `media.unpublish`.
    - Tests: egress test_media_out.py, test_a_signed_url_is_one_file_for_fifteen_minutes, test_a_one_off_ends_as_a_card_and_unpublishing_removes_what_it_can.
  - §2.4 UI redesign: a `design` item (ui_designer) renders phone and desktop screenshots and stays a deliverable for the CTO; it is never published. Test: test_a_design_is_rendered_to_pages_and_never_published.
  - §2.5 tools:
    - `media.item` (A1), `media.render` (A2; 503 channel_not_configured while `media` is off), `media.voice` (A2, the registry's), `media.review` (A2, the media director only), `series.propose` (A1).
    - They are in the gateway, in OPA (`media.rego`, `legal_voice.rego`), in the A2 grants and in OP_CLASS.
    - Tests: gateway test_media_tools.py, media_test.rego.
  - §2.6 overseer, by rule: the sweep re-checks published items (red lines, risk warning, facts, brand), at most 5 a company a day. A failure opens a `high` finding and pauses the series until the owner.
  - API and stream:
    - every route of §22.2 and §22.7
    - stream `media.item` and `media.series` on topic `media`; `role.updated` on `people`
    - codes `series_not_sealed` (409) and `platform_limit` (429)
- §3 ok (the legal counsel):
  - §3.1 cases:
    - `legal.cases` (LC-0001; company_id = the company the case is about), with its timeline in `legal.case_events`.
    - `GET /legal/cases`, `GET /legal/cases/{ref}`, `POST /legal/cases` (owner; a P2 work item, task_class `legal_case`), `POST …/close` (409 while an email waits). Stream `legal.case` on topic `legal`.
    - A CEO asks through `work.request {company: HQ, department: LEGAL}`.
    - Tests: test_the_counsel_reaches_only_its_own_cases, test_a_ceo_asks_the_holdings_counsel_through_a_work_item, test_the_owner_in_thread_l_wakes_the_counsel_and_only_it_answers_there.
  - §3.2 email:
    - `email.draft` → card `email_send` (A3) with the exact message and its `digest`. The seal is `decision.approve` step-up on the digest.
    - Amendments are 422, a changed or superseded email 409, no mailbox 409 `account_not_configured`.
    - The worker's effect sends it once, after the lock checks; it is never resent and never retried.
    - Replies: the poller reads through egress (IMAP, BODY.PEEK, a UID cursor) and keeps only replies naming a sent message. It masks them, passes attachments through §17.1 and wakes the counsel (P2, `legal_email`). Unrelated mail is not stored.
    - The mailbox is service account `mail`. Its secret is read from OpenBao for one call and goes only to egress.
    - Tests: test_an_email_leaves_only_by_the_seal_and_exactly_once, test_a_change_after_the_owner_saw_it_is_a_new_card, test_without_a_connected_mailbox_a_draft_stays_a_card, test_reject_reopens_the_case_and_closing_waits_for_the_seal, test_a_reply_reaches_its_case_and_wakes_the_counsel_unrelated_mail_does_not, test_the_mailbox_password_never_shows, egress test_mail_out.py (11).
  - §3.3 forms and portals: `propose` cards `a3_action` with `action: "form_submit"`; the owner submits them. Test: test_a_form_is_an_a3_card_the_owner_submits.
  - §3.4 tools: `case.open`, `case.note`, `email.draft` and `mail.read` (own cases only), in the gateway and the api (OPA `legal_voice.rego`). Tests: gateway test_legal_tools.py (6), legal_voice_test.rego (6).
- §4 ok (voice):
  - §4.1 one registry, `media.voices`:
    - The briefings of §21.4 speak with its active voice, and so does `media.voice`. A non-commercial voice the owner did not choose → 409 `licence_not_chosen`.
    - The TTS one-shot's second queue `/internal/v1/voices/jobs/{claim,done,fail}` speaks the bake-off samples and the media items' narrations, each with its own voice.
    - Tests: test_the_briefings_speak_with_the_registrys_active_voice, test_media_voice_queues_the_narration_with_the_active_voice, tts test_voice_jobs_speak_with_their_own_voice_and_send_their_numbers.
  - §4.2 bake-off:
    - Fixed Persian scripts: `numbers`, `latin`, `crypto`, `long`, `reel60`.
    - The daily schedule queues the missing samples. Each Ogg goes through §17.1 with its RTF and peak.
    - `GET /media/voices`, `POST /media/voices/{id}/score` 1–10, `make tts-bakeoff`.
    - Tests: test_the_bakeoff_queues_once_and_its_audio_goes_through_17_1, test_the_tts_images_scripts_are_the_hubs_spoken_scripts, tts test_bakeoff.py (8).
  - §4.3 candidates (table below) and the owner's voice:
    - `POST /media/voices/reference {file_id}`: owner only, the owner's own 60–180 s upload. It is never attached, never sent and never read by an agent. `GET /media/voices/reference` reads it.
    - Tests: test_the_registry_has_every_candidate_with_its_licence_and_numbers, test_the_owners_reference_is_the_owners_and_never_an_agents.
  - §4.4 activation:
    - `POST /media/voices/{id}/activate` 🔏 `voice.activate`. A non-commercial voice needs `accept_non_commercial: true` (else 422).
    - Not installed or unmeasured → 409 `not_ready` (ParsVoice-XTTS today). One voice is active.
    - `licence_commercial` is on every row and every narration result.
    - Test: test_a_non_commercial_voice_is_never_active_without_the_owner.
- §5 ok (charters and tools):
  - Seeded from `agents/` as they are; every tool of every charter is in the catalog.
  - `media.review` is the media director's alone; `email.draft` and `mail.read` are the legal counsel's alone; `media.voice` is the voice producer's. The motion designer runs on Opus 5.5.
  - Tests: test_the_media_charters_tools_are_all_in_the_catalog, test_the_media_tools_are_registered_and_media_review_is_the_directors_alone, test_every_charter_tool_is_in_the_catalog_and_the_exclusive_ones_stay_exclusive, test_agents_more.
- §6 ok (memory and cost): the numbers are below.
  - The email poller, the send, the checks and publishing run inside the existing worker.
  - The mailbox and publishing go through the existing egress.
  - No new long-running service and no port. The token estimate is below.
- §7 (owner tasks): listed below; nothing was done in the owner's place.
- §8 ok (the end):
  - OpenAPI regenerated on the joined branch: **416 operations**, no schema renamed.
    - r13a's 403 plus r13b's 17 new operations, less the studio's own TTS queue `/internal/v1/tts/media/*` (3) and the second `/internal/v1/media/voice`.
    - `NarrationJob` went with its route.
  - RUNBOOK §31: its first lines (the migration chain, the launch gate, the §0.9 defaults), then r13a's §31.1–§31.9, then r13b's §31.11–§31.14.
    - The command table rows: `make media-on|off|bench`, `make tts-bakeoff`, `make account-secret KEY=telegram-<co>|instagram-<co>|mail`.
  - live.sh: the render sandbox probe; a forged signed URL and every other `/public` path are 404 at the edge.
  - The full `make check` and `make verify-live` are the parent's.
- Join (r13j) ok:
  - Kept once:
    - LEGAL, HQ-LGL and thread L
    - `email_send` (0028_1)
    - `media.voice`: the registry's route and gateway tool, one OPA grant, one OP_CLASS entry
    - the worker's own OpenBao client (`hub.bao`, r13a's), which also serves the mail poller and the sealed send
  - The studio's own narration queue is gone, and so is the TTS service's second pass over it. The pipeline's voice step is the registry's:
    - `studio.request_voice` → `voices.narrate`
    - `studio.on_narration` and `on_narration_failed` hang on `voices.ON_NARRATION` and `ON_NARRATION_FAILED`
    - The registry's claim now also skips a narration whose own company is locked.
  - `hq-media` stays 172.30.23.0/24; r13b adds no network.
  - test_p10_foundation checks the kind CHECK validated again (0028_1 validates it).

### Memory (measured on this CPX42, 2026-10-23, offline)
| Part | How it runs | Measured | Limit | Profile |
|---|---|---|---|---|
| render worker (Chromium + ffmpeg), 30 s 1080×1920 reel, 900 frames | one-shot, one job at a time | 51.3 / 55.8 / 54.6 s; container peak 718 / 776 / 728 MiB (Chromium 284–291 MiB); reel 1.5–1.8 MB, H.264 High, AAC 48 kHz, 30.0 s | `MEM_MEDIA_RENDER=960m` | `media` |
| render worker, a Lottie still / a design page | same | 1.6 s, 259 MiB / 1.7 s, 280 MiB | same | `media` |
| media courier (claim/send) | one-shot | 17 MiB | `MEM_MEDIA_COURIER=64m` | `media` |
| TTS (briefings, narrations, bake-off; one engine) | the existing one-shot | one synthesis 236–271 MiB; container 264.8 MiB (lines of at most 8 words) | `MEM_TTS=320m` | `tts` |
| sweep, checks, publishing, signed URL, mail poller, sealed send | inside the worker / api | no new service | — | — |
- Memory gate on r13j (budget 12288 MiB full, 6196 lean):
  - Fits: full+media 11920; full+tts 11216; full+media+tts 12240; lean+tts 6192.
  - Over: lean+media by 700 (hq.sh refuses it, exit 3); full+stt by 784.
  - `media` does not fit together with mcp, the substitutes' runner or their web browser.
- Image size: the TTS image grows by ≈190 MB of disk (three more Piper voices).
- **media and tts stay off** until the owner orders the memory: `make install-systemd` once, then `make media-on` / `make tts-on`.

### Voice bake-off (2026-10-23 02:50 UTC, this CPX42, image coinepro-hq/tts:p13b, 320 MiB, 1 thread, no network, five scripts)
| Voice | Licence | Commercial | RTF | Peak of one synthesis | Speech |
|---|---|---|---|---|---|
| piper-amir (active) | MIT weights; dataset CC0-1.0 | yes | 0.177 | 236.3 MiB | 144.6 s |
| piper-ganji | MIT; CC0-1.0 | yes | 0.170 | 254.5 MiB | 158.5 s |
| piper-ganji-adabi | MIT; CC0-1.0 | yes | 0.187 | 270.5 MiB | 175.0 s |
| piper-reza-ibrahim | MIT; CC0-1.0 | yes | 0.185 | 269.8 MiB | 176.9 s |
| piper-gyro | MIT; dataset licence unstated | no | not shipped | | |
| manatts-piper | CC0-1.0 corpus; MIT | yes | not trained (GPU, owner) | | |
| parsvoice-xtts (+ owner's voice) | Coqui Public Model License (non-commercial) | no | not measured: gated, ≈2.5-3 GiB | | |
| chatterbox-fa (+ owner's voice) | CC BY-NC 4.0 | no | not measured: gated, over budget | | |
- RTF includes loading the model for every job. The reel text speaks 64-76 s.
- With 14-word lines the peaks were 293-337 MiB (the container at its 320 MiB limit); with 10, up to 307 MiB.
- No permissive multilingual model lists Persian on its card (Kokoro, Chatterbox multilingual; MMS-TTS fas is CC-BY-NC).

### Token cost per reel (estimated; no real call was made, per the run sheet)
- The fixed system prompt of each step, measured on r13j by test_p13a_prompt_sizes (\_common + charter + MEDIA's identity + the runtime's sections, at 4 characters a token):
  - scriptwriter 5,418; video director 5,239; motion designer 5,618; voice producer 4,895; media director 7,147
  - Each step resends it, plus the brief (1–4 K) and what its tools returned.
- Per 30 s narrated reel:
  - script (Sonnet): 18–28 K
  - direction (Sonnet): 12–20 K
  - composition (Opus 5.5; a document is 8–15 K output tokens each time): 80–200 K
  - voice (Haiku): 6–14 K
  - review (Sonnet, with key frames): 12–30 K
  - **Total ≈ 130–290 K tokens a reel**, 60–70% of it Opus. A still story without voice: ≈ 30–60 K. The TTS spends no token.
- The counsel's runs use the holding's envelope: ≤ 8 steps and 200 K tokens a run by its charter, task classes `legal_case` and `legal_email`, never on another provider.
- Reels are paid from the company's monthly envelope and show in its efficiency star. At one reel a day, a company spends about 4–9 M tokens a month on reels.
- **The agents' daily cap stays 600 K for the whole hub** (owner decision 2026-10-17): about 2–4 reels a day across every company. The cap is the owner's.

### Contract notes
1. §22.2 lists `POST /media/items/{ref}/publish`, while §22.7 says publishing outside a sealed series has one path, the card. Built as the card's approval: 🔏 `decision.approve` on the item's pending `media_publish` card. Without such a card it answers 409 `series_not_sealed` or `validation_failed`.
2. Publishing accounts: `tools.accounts.site` is a host, so the account's `policy.inject.username` holds the Telegram channel or the Instagram username (site `api.telegram.org` / `graph.instagram.com`). A series' target must be its own company's `telegram-<co>` or `instagram-<co>`. The Instagram username is checked against `me` before every publish.
3. A series' RRULE is its publishing time. All seven checks run on every item, and a series names all seven.
4. `GET /templates` keeps `departments` as codes and gains `blueprint`; `company.state` gives the identity of the caller's own department only.
5. MediaItem gains `publish_at`. `render` is the first output, and `pages` are a carousel's slides or a design's pages. A design item ends in `review` and is never published.
6. Captions come from the shots' voice lines; with a narration they are spread over its real length by the share of characters.
7. The narration (joined):
   - `media.voice` answers 202 with the registry's `Narration` (`job`, `voice` with its licence, `spoken_chars`).
   - `voice_id: "default"` in a series' format means the active voice.
   - With the `tts` profile off it answers `state: "off"` (no job, no voice, `note_fa`) and the item goes on silent.
   - The narration arrives later through `voices.ON_NARRATION`; one given up after three tries lets the item go on silent.
8. §2.6's daily overseer protocol is not in `agents/protocols/oversight.yaml` (the consultation session's file). Built as a rule re-check inside the sweep; a model-sampled PR-1xx is the consultation session's to add.
9. The render job's contract: a still's `at_s` (3 s; k−0.5 for slide k); a design's CSS viewport and `scale`; a video always has an audio track; a killed render arrives as `fail render_killed: …` and is retried.
10. Instagram: `is_ai_generated` and the Bearer header are confirmed only at the owner's first real publish. The API has no delete, so unpublishing there is `remove_by_hand`.
11. IRANYekanX is a licensed font (licence no. 136710), not open source. It is the hub's existing font and ships with its licence file in the render image.
12. A step stored with `media.item` closes its work item `done`, with the item as evidence (HQE01).
13. The signed URL's key is derived (HMAC, label `hq-media-public-url-v1`) from the agent token key; there is no new secret.
14. Role drafts: the overseer reviews them with `skill.review` and the RD- ref (a fifth check `ceiling`). A draft's eval passes at 70/100. A draft role reads only its own company, even in the holding. The charter text is capped at 7,000 characters.
15. The worker never held its OpenBao client (`hub.bao` was set in the api only). It now sets it to its own AppRole client, kept once. The publishing accounts, the counsel's mailbox, prompt 10's support channels and prompt 12's deploy diff read through it.
16. §22.7 email `state` gains `queued`, `sending` and `failed` (never retried), plus `Email.error`. A case's email cannot be sealed while the mailbox is not connected (409 `account_not_configured`).
17. §22.4: reply attachments are kept in the holding, because the counsel's `files.read` reads its own company only; the case's company is on the case. `a3_action.action` gains `form_submit`.
18. §22.2 `Voice` gains `installed`, `measured_on` and `version`. Its OpenAPI schema is `RegistryVoice`, because the briefing's `Voice` already had the name. `media.voices` ids are stable text keys, one per engine and speaker.
19. §22.3: the owner's reference must be the owner's own upload, not attached to a message, and 60–180 s long; else 422.
20. tests/test_hiring.py runs the migrations down to 0009 and up again. Every re-added kind CHECK below the head is NOT VALID, and 0028_1 validates at the head.

### Not done, and why
- ParsVoice-XTTS and Chatterbox are not measured: both downloads are gated behind a Hugging Face account (the owner's), and both are over the tts memory budget. They are in the registry with the reason.
- The ManaTTS voice is not trained: it needs a rented GPU (owner decision §0.9 #3). The plan and estimate are in RUNBOOK §31.13.
- No bake-off audio is in the production registry yet: the hub's queue runs only with `HQ_TTS=on` and the holding unlocked.
- The §0.5 real sample reel and story were not made: no real model call before launch, per the run sheet.
- The full api suite is the parent's, after prompt 12's final branch is laid under r13j (run once on r13f: see Merged on 12).

### Owner tasks
1. §0.9's six decisions. The defaults hold until you answer:
   - Opus 5.5 for motion graphics
   - ParsVoice-XTTS in your own voice (Piper until it is installed and you choose it)
   - no GPU rental, no music library
   - 2 reels / 3 stories / 2 posts a day per series
   - no counsel mailbox
2. The publishing accounts of each company. Nothing publishes until both steps are done for that account:
   - In the app: `telegram-<co>` (site `api.telegram.org`, the channel in `policy.inject.username`, the bot an admin with post and delete rights) and `instagram-<co>` (site `graph.instagram.com`, the page's username).
   - In your own terminal: `make account-secret KEY=telegram-<co>` and `KEY=instagram-<co>`.
   - Instagram also needs the domain over HTTPS: `HQ_SITE_ADDRESS`, and egress's `EGRESS_PUBLIC_HOST`.
3. The legal mailbox (Gmail, Workspace or the domain's mail): service account `mail` in the app (site, address, ports 465 and 993), then `make account-secret KEY=mail` (an app password).
4. The memory order between the opt-ins: `media` fits the full profile with TTS, but not with MCP, the substitutes' runner or their web browser. Switch on with `make install-systemd`, then `make media-on` / `make tts-on`.
5. Each company's active brand (mark and palette): the `brand` check needs it.
6. Opening hiring for the MEDIA teams (hiring is closed).
7. Sealing each company's first series. A new series starts with `auto_publish: false`, so every item is then a card.
8. The agents' daily token cap (600 K) against the per-reel cost above.
9. To try ParsVoice-XTTS: accept its terms with your own Hugging Face account and decide on the memory (it does not fit the tts budget); its licence is non-commercial. A rented GPU for the ManaTTS voice (≈ $15-70), or not.
10. Record your reference voice in the app (1-3 minutes of clean speech) when a cloning engine is wanted. After launch, turn the voice on so the bake-off makes the samples, then listen blind, score, and choose the active voice (🔏).

### Gates (r13j; test name p13a, image tag p13a)
- python lint: ruff, format and mypy --strict, clean for the api (189 files) and the services (136 files).
- OpenAPI regenerated: 416 operations.
- OPA 137/137 at 100% coverage; shellcheck (80 scripts); yamllint (46 files); compose-config and compose-rules (lean, full); memory-budget (numbers above); infra.sh (38 checks); gitleaks (history and working tree) all clean.
- services: gateway, hq-common, egress, tts and llm-router, 914 passed.
- api, targeted, on a fresh database:
  - 82 passed: test_p13a_media, test_p13b_voices, test_p13b_legal, test_p13a_departments, test_p13a_roles, test_p13a_prompt_sizes, test_schema_rules, test_rls_all_tables, test_p10_foundation.
  - test_hiring (migrations 0009 → 0028_1 and back up), test_agents_more (the charter-order test passes here) and test_org_work pass. test_inquiries_errands has one known base failure: test_the_advisor_v2_has_its_read_tools needs prompt 11's tools, which are not on this base.
  - 107 passed: test_openapi (schemathesis, 8 examples), test_worker, test_stream_topics, test_decisions_messages, test_p12b_briefings, test_agents, test_precedence, test_egress, test_p12b_cards, test_files_media.
- The full api suite was not run: the parent runs it once prompt 12's final branch is under r13j. Known base failures that may remain: the advisor's p11 tools above, and the prompt-12 substitutes tests that need the substitutes' seed and fail when they run after test_hiring's down-and-up cycle in the same session.
