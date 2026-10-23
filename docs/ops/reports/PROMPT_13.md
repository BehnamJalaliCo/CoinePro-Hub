PROMPT_13 REPORT (the media studio of every company and the holding's legal counsel)

## Media (branch r13a: §1, §1.1, §2, §5 and §6 of the prompt; stage G of the run sheet)
- Branch **r13a** from `dev/p13-base` 4f59c82 (prompt 10 + prompt 12's two parts joined, TTS off, + main up to "Prompt 13 sent"); nothing else merged. Prompt 11 and the rest of 12 are laid under it later by the parent. Three forks of this agent built parts in parallel and are merged into it: **r13a-roles** (§1.1), **r13a-egress** (the egress side of publishing) and **r13a-render** (the render worker and its infrastructure). **Not deployed.**
- **Migration:** `apps/api/migrations/versions/0028_media_studio.py`, revision **0028**, down_revision **0027_1**. The other half's is 0028_1 (down_revision 0028).
  - Decision kinds `media_series`, `media_publish`, `role_new` and `email_send` are added to `decisions_kind_check`, rebuilt from the kinds it already holds and added **NOT VALID**. A sibling migration doing the same composes with it. Fork D fixed the helper: an empty drop list is `ARRAY[]::text[]`, which the merge must keep.
- **Hub state kept:**
  - The holding kill switch and `HQ_MORNING_REPORT_LLM=off` are untouched, and `HQ_PROVISIONING` is off.
  - No owner login, key or token was used or asked for: Telegram and Instagram stay off until the owner sets them.
  - The opt-in `media` profile is built and **off**.
  - No real model, platform or outside call in CI (a fake model, a fake Telegram, a fake Graph API). Real-model tokens spent: **0**. Per the run sheet, the §0.5 real sample reel was **not** made; its cost is estimated below.
- **What could wake a model or an outside call, and its gate (all tested):**
  - `hq-media-sweep` (every 5 min: the sealed series' schedules, due publishing, the rule re-check of published items) asks `gate.holding_lock` first and does nothing at all while the holding is locked. A locked company's series and items wait.
  - The render one-shot's claim and the TTS one-shot's narration claim answer 204 while the holding or the item's company is locked.
  - Publishing (the sweep's, and the one after a card's seal) stops for the holding lock, a company kill switch or deploy freeze, holds and watch mode. A sealed card's effect itself waits while the holding is locked, like every effect.
  - Agent runs of the pipeline are refused while locked (`locked`); the step's work items are records only.
  - Rule-only: the re-check of published items touches no model and no outside service. It still sits behind the holding gate, inside the sweep.
  - The owner's own unpublish (sealed) runs when the owner asks; it only takes posts down.
  - Tests: test_nothing_runs_while_the_holding_is_locked, test_the_company_kill_switch_holds_scheduled_publishing.

### Items
- §1 ok (mandate, identity, starting team):
  - `core.departments` gains `mandate` and `identity_md`, seeded from `standard.yaml` and `holding.yaml` where empty. Every standard department has a Persian «مبدأ و مقصد», outputs, boundaries, a tool ceiling, a model ceiling (Sonnet; MEDIA Opus) and an identity; MEDIA's is written from the owner's own words.
  - `team` is read from the template, showing only charters live in `agents/roles/` for that department; staged hiring roles appear the day they go live.
  - `PUT /companies/{code}/departments/{dept}/mandate` takes 🔏 `department.mandate` on the body hash and `If-Match`. A ceiling with an unknown, A3/A4 or never-given tool is 422.
  - `GET /templates` gains `blueprint`; `company.state` carries every department's mandate and team, plus the caller's own identity.
  - The runner puts `identity_md` after the charter and before the skills for the department's manager and members, and records `agents.runs.identity_doc` (`TY-MEDIA@4`).
  - MEDIA («رسانه و طراحی», sort 25, head `media_director`, team of six). Existing companies get it by migration 0028 (the department, its asleep manager and two threads; no employee). The holding gets LEGAL (no manager) and the asleep `HQ-LGL` (charter `legal_counsel`); thread L is §3's.
  - Tests: test_p13a_departments.py: a new company's MEDIA with mandate, identity and team; an existing company by the migration's data step with no employee; LEGAL and HQ-LGL; the identity in its department's prompt only; a run reads it after the charter and records it; the owner's sealed mandate; plus test_org_work counts.
- §1.1 ok (roles written on demand, fork D):
  - `people.role_drafts` (RD-0001) with `GET`/`POST /roles/drafts`, `GET /roles/drafts/{ref}` and `POST …/retire`.
  - `role.draft` (A1, the department head): the ceiling is checked by code, 422 per field.
  - `role.decide` (A2, the CEO, delegated hiring only).
  - The gates run in order: originality (8-word runs), the overseer's review on the sha256 (`skill.review` with RD-, a fifth check `ceiling`), the draft's own academy eval (purpose `role_draft`, 70/100 = its baseline), then the CEO or a `role_new` card (always one for the holding).
  - Activation retires the version it supersedes and posts a role story. The runner, the hire checks and the gateway read file charters plus the company's active drafts; `GET /roles` shows `source`.
  - Nothing calls a model while the holding is locked.
  - Tests: test_p13a_roles.py (8), roles_test.rego, gateway test_role_tools.py (4).
- §2.1 ok (data):
  - `media.series` (SR-0001), `media.items` (MI-0001), `media.compositions` (append-only, numbered, sha256), `media.render_jobs` and `media.publish_log` (append-only). `media.voices` is §4's.
  - Every table has company_id and FORCE RLS, refuses DELETE, and is in test_rls_all_tables (filled) and test_schema_rules.
- §2.2 ok (publishing series):
  - The owner creates a series (`draft`), or the media director uses `series.propose` (`proposed` and a `media_series` card).
  - The seal is `POST …/seal {digest}` 🔏 `media.series` on the digest; another digest is 409 version_conflict. Sealing decides the pending card and resumes a paused series; the cartable's approve of that card answers 409.
  - Editing a sealed series takes it back to `proposed` and nothing publishes by itself. `pause` and `retire` need no seal.
  - The RRULE runs in the owner's zone: one item per occurrence, with the next topic of the pool, at most `max_per_day`, and no backfill beyond 30 minutes. The server computes `next_at` and `today`.
  - A series must fit its kind (422).
  - Tests: test_an_unsealed_series_publishes_nothing_and_an_edit_takes_the_seal_away, test_a_series_card_is_sealed_on_its_page_and_the_limit_answers_429, test_a_series_must_fit_its_kind.
- §2.3 ok (pipeline):
  - Each step is a work item to the least busy holder of the step's role in the company's MEDIA department. Code moves the item on: script → direction → composition → voice → render → checks → review.
  - A still is the visual designer's creatives or a composition rendered to stills (carousel `data-slides`, a single still at 3 s). A missing role holds the item and tells the director once.
  - A step written with `media.item` closes its work item `done`, with the item as evidence.
  - The composition schema (`hq_common/composition.py`) is checked in the api before storing and again in the worker:
    - no network of any kind
    - only anime.js and lottie-web light by fixed `/lib` paths
    - the company's own assets; IRANYekanX only; `lang=fa dir=rtl`
    - no Lottie expression; no secret or e-mail in the visible text
    - nondeterminism (Date.now, timers, random) is only a warning: a virtual clock drives the page
  - The voice goes through the TTS one-shot's own queue `/internal/v1/tts/media/*` (the engine of §21.4; with the profile off the item goes on silent, with captions).
  - The render queue: claim, files, outputs (type by bytes, size while streaming, ffprobe on video; the poster is the video's variant), done with runtime violations (the item goes back to its composer), fail with 3 tries.
  - The seven checks run by code (brand, red_lines, risk_warning, facts, rights, platform, qc). After the director's review, a sealed auto series with every check `pass` and every placement through an API is `scheduled` at its next occurrence; anything else is `waiting_owner` and a `media_publish` card.
  - Tests:
    - test_one_item_from_its_script_to_its_publishing: the script by a fake-model run through the gateway, then direction, composition, render through the one-shot's api, six checks `pass`, the director's review, scheduled, and published on a fake Telegram (sendVideo) and a fake Instagram (container from a signed URL, `REELS`).
    - test_a_failed_check_makes_a_card_not_a_publish: no risk warning → card, nothing published, and the card's seal publishes it.
    - test_a_composition_that_reaches_for_the_network_is_refused: fetch, `<script src=https://…>`, another font, an e-mail.
    - test_review_changes_go_back_to_the_named_role_and_a_reject_ends_it
    - test_a_runtime_violation_sends_the_item_back_to_its_composer
    - test_captions_follow_the_shots_or_the_narration
    - hq-common test_composition.py (34 cases)
- §2.3 ok (the render worker, fork R; numbers below):
  - Service `services/media-render` in the opt-in profile `media`, off by default.
  - `media-courier` runs on the internal `hq-media` network (api and OpenBao only; AppRole `media` and a token in `kv/media/config`).
  - `media-render` has `network_mode: none`, a read-only root, uid 10001, `cap_drop ALL` plus `SYS_CHROOT` for Chromium's own sandbox, Playwright's pinned seccomp, no-new-privileges, 2 CPUs, 512 pids, a 600 s deadline and `MEM_MEDIA_RENDER=960m`.
  - Headless Chromium renders frame by frame on a virtual clock, and every request outside `/lib`, `/fonts` and `/assets` is aborted and reported. ffmpeg makes H.264 High/AAC/faststart, plus a poster and WebVTT. The mark, the call to action and the captions are on a layer the composition cannot touch.
  - `make media-on`, `media-off` and `media-bench`; timer `coinepro-hq-media.timer`. hq.sh refuses it over the budget.
  - Tests:
    - services/media-render/tests (90% coverage)
    - compose-rules (every sandbox flag)
    - the bench's probe (loopback only; the api, OpenBao, Postgres, the host, 1.1.1.1, 8.8.8.8, 10.10.1.1 and the metadata address all fail)
    - the "sneak" bench (a request the rules let through is aborted at runtime)
    - live.sh (hq-media reaches only the api and OpenBao; media-render sees nothing)
- §2.3 ok (publishing, forks E and me):
  - egress `POST /v1/media/publish` (`media_out.py`), official APIs only:
    - Telegram: sendVideo, sendPhoto, sendMediaGroup, deleteMessage. Any story method is refused: a channel story is always a card.
    - Instagram: Graph API v23.0 (me, limit, create with `is_ai_generated: true`, status, publish, permalink). Media URLs only from `https://<host>/public/v1/media/<token>`.
    - Stable codes `platform_limit`, `no_channel`, `auth_failed`, `publish_error`; the token is never in an answer, an entry or a log.
  - The signed URL is HMAC with a key derived from the agent token key, one file, ≤ 15 minutes. Anything else is 404, and only render or creative files qualify. Caddy routes GET/HEAD `/public/v1/media/*` only (with the domain); `/public/*` is otherwise 404.
  - Instagram's own 50 a day gives 429 `platform_limit` with Retry-After; `GET /media/limits` shows each account.
  - Unpublish is 🔏 `media.unpublish`: Telegram deleteMessage gives `removed`, Instagram gives `remove_by_hand`, and the item becomes `rejected`.
  - Tests: egress test_media_out.py (60), test_a_signed_url_is_one_file_for_fifteen_minutes, test_a_one_off_ends_as_a_card_and_unpublishing_removes_what_it_can.
- §2.4 ok (UI redesign):
  - A `design` item runs brief → composition (ui_designer) → screenshots at phone 390×844 @2x and desktop 1440×900, full page, by the same worker → the director's review. It stays as a deliverable for the CTO and is never published (no card, no publish rows).
  - Test: test_a_design_is_rendered_to_pages_and_never_published.
- §2.5 ok (tools):
  - `media.item` (A1), `media.render` (A2; 503 channel_not_configured while `media` is off), `media.voice` (A2), `media.review` (A2, the media director only) and `series.propose` (A1).
  - They are in the gateway (`hq_gateway/media.py`; text redacted, a composition's source never rewritten), in OPA (`media.rego` + test), in the A2 grants and in OP_CLASS.
  - Tests: gateway test_media_tools.py (4), media_test.rego.
- §2.6 ok (overseer, by rule):
  - The sweep re-checks published items an hour old or more (red lines, risk warning, facts, brand), at most 5 a company a day.
  - A failure opens a `high` finding (dedupe by item) and pauses the series until the owner.
  - The model-based sampled protocol is not in `agents/protocols` (see Contract notes).
- §2 API/stream ok:
  - Every route of §22.2 and §22.7 (see RUNBOOK §31.8).
  - Stream `media.item` and `media.series` on topic `media`; `role.updated` on `people`.
  - Codes `series_not_sealed` (409) and `platform_limit` (429).
  - OpenAPI regenerated: 403 operations (+34), none removed, no schema renamed.
- §5 ok (charters and tools):
  - The p13 charters and `tools.md` are seeded from `agents/` as they are.
  - Every tool of every media charter is in the catalog; `media.review` is the media director's alone; `email.draft` and `mail.read` are the legal counsel's alone; the motion designer runs on Opus 5.5 with `media.item`, `media.render` and `substitute.call`.
  - Tests: test_the_media_charters_tools_are_all_in_the_catalog, test_the_media_tools_are_registered_and_media_review_is_the_directors_alone, test_agents_more (the hireable list).
- §6 ok (memory and cost rows): the numbers are below. The email poller, the checks and publishing run inside the existing worker; there is no new long-running service. Token estimate: below.
- §8 (this half) ok:
  - RUNBOOK §31 with its first lines (the migration, the launch gate, the §0.9 defaults) and §31.1–§31.9, plus the command table rows (`make media-on|off|bench`, the publishing accounts' `make account-secret`).
  - live.sh: the render sandbox probe, and a forged signed URL and every other `/public` path are 404 at the edge.
  - This report. The full `make check` and `make verify-live` are the parent's.
- Gates run green on r13a:
  - python lint: ruff, format and mypy --strict for the api (182 files) and services (133 files)
  - opa 131/131 at 100% coverage; yamllint; shellcheck (80 scripts)
  - OpenAPI regenerated
  - api tests: test_p13a_departments (7), test_p13a_media (14), test_p13a_prompt_sizes (1) and test_p13a_roles (8) pass.
  - The full api run on a fresh database (test_hiring alone on another fresh one) has one failure, not this half's: test_inquiries_errands::test_the_advisor_v2_has_its_read_tools. The advisor's charter on main already lists prompt 11's tools (authority.read, governance.read, meeting.item, meeting.whisper, calendar.read), which the gateway gets with prompt 11. The base fails it the same way.
  - Fixed on the way:
    - test_p10_foundation expected the kind CHECK validated; 0028 adds it NOT VALID, so the test now checks that every row fits it.
    - test_org_work and test_agents_more counted 8 departments and the pre-media hireable list.
    - Fork D's EV ref allocation broke on prompt 10's `support-shadow-…` suites.
    - Missing route docstrings for test_openapi.
  - services: the full suite of every service passes (gateway, hq-common, llm-router, claude-runtime, stt, egress, provisioner, substitutes, tts, media-render), after adding the media tools to `hq_common.tool_status.GATEWAY_TOOLS`.
  - services: gateway, hq-common, tts, egress and media-render
  - fork R also ran compose-config, compose-rules, memory-budget, hadolint and infra.sh

### Memory (measured on this CPX42, 2026-10-23; `make media-bench`, cgroup memory.peak, offline)
| Part | How it runs | Measured | Limit | Profile |
|---|---|---|---|---|
| render worker (Chromium + ffmpeg), 30 s 1080×1920 reel, 900 frames | one-shot, one job at a time | 51.3 / 55.8 / 54.6 s; container peak 718 / 776 / 728 MiB (Chromium 284–291 MiB); reel 1.5–1.8 MB, H.264 High, AAC 48 kHz, 30.0 s | `MEM_MEDIA_RENDER=960m` | `media` |
| render worker, a Lottie still / a design page | same | 1.6 s, 259 MiB / 1.7 s, 280 MiB | same | `media` |
| media courier (claim/send) | one-shot | 17 MiB | `MEM_MEDIA_COURIER=64m` | `media` |
| TTS (narrations, shared with §21.4) | the existing one-shot | unchanged (241 MiB, prompt 12) | `MEM_TTS=320m` | `tts` |
| sweep, checks, publishing, signed URL | inside the worker / api | no new service | — | — |
- Memory gate (budget 12288 MiB full, 6196 lean):
  - full+media: 11920, fits.
  - full+media+tts: 12240, fits.
  - full+media with mcp: 656 over. With substitutes: 144 over. With substitutes-web: 400 over. With stt: over.
  - lean+media: 700 over, so hq.sh refuses it with exit 3.
- **media stays off** until the owner orders the memory: `make install-systemd` once, then `make media-on`.

### Token cost per reel (estimated; no real call was made, per the run sheet)
- Measured fixed system prompt per step (\_common + charter + MEDIA's identity + the runtime's sections, the hub's own estimate of 4 characters a token; test_p13a_prompt_sizes):
  - scriptwriter 5,354; video director 5,175; motion designer 5,554; voice producer 4,831; media director 7,083.
  - Each model step resends it, plus the work brief (script, shots, brand and rules: 1–4 K) and what the step's tools returned.
- Estimate per 30 s narrated reel, the prompt's ranges checked against those sizes:
  - script (Sonnet, 2–4 steps with search and read): 18–28 K
  - direction (Sonnet, 2–3 steps): 12–20 K
  - composition (Opus 5.5, 3–6 steps; a document is 8–15 K tokens of output each time, and a preview's key frames ~1.6 K tokens each): 80–200 K
  - voice (Haiku, 1–2 steps): 6–14 K
  - review (Sonnet, 1–2 steps with the render's key frames): 12–30 K
  - **Total ≈ 130–290 K tokens a reel**, 60–70% of it Opus.
  - A still story without voice or direction: ≈ 30–60 K (script + frames + review).
- It is paid from the company's monthly envelope and shows in its efficiency star. At one reel a day, a company spends about 4–9 M tokens a month on reels.
- **The agents' daily cap stays 600 K for the whole hub** (owner decision, 2026-10-17): that is about 2–4 reels a day across every company before anything else runs. The cap is the owner's to raise from the first week's outputs.
- The director may propose moving `media_motion` to Sonnet for a series that reuses an accepted layout (the charter says so); the owner seals `/assignments`.

### Contract notes
1. §22.2 lists `POST /media/items/{ref}/publish`, while §22.7 says publishing outside a sealed series has one path, the card. Built as the card's approval: 🔏 `decision.approve` on the item's pending `media_publish` card, like the cartable. Without a pending card, it answers 409 `series_not_sealed` (its series is not sealed) or 409 `validation_failed`.
2. Publishing accounts: `tools.accounts.site` is a host (CHECK), so a channel's identity cannot be its site URL.
   - The account's `policy.inject.username` holds the Telegram channel (`@name` or `-100…`) or the Instagram page's username; site is `api.telegram.org` / `graph.instagram.com`.
   - `companies` cannot be empty, so it is `[<CO>]`. An agent's http.request with it could at most read (GET); posting is A3 and becomes a card.
   - A series' target account must be its own company's `telegram-<co>` or `instagram-<co>`.
   - The Instagram username is checked against `me` before every publish.
3. A series' RRULE is its publishing time: the sweep makes an item at each occurrence, and a reviewed item of a sealed auto series is published at the next occurrence (within `max_per_day` a day in the owner's zone).
4. All seven checks run on every item; a series must name all seven.
5. `GET /templates` keeps `departments` as codes and gains `blueprint` (mandate, identity, team per department). `company.state` gives the identity of the caller's own department only.
6. MediaItem gains `publish_at`. `render` is the first output, `pages` are a carousel's slides or a design's pages, and `outputs` stay internal (per placement). A design item ends in `review` with its `qc` and is never published.
7. Captions come from the shots' voice lines; with a narration they are spread over its real length by the share of characters (one continuous voice).
8. The voice step queues the item's narration for the TTS one-shot's own queue (`/internal/v1/tts/media/*`, service `tts`), spelled for speech by `fa_speech_script`. `voice_id: "default"` means the active voice; the registry, ParsVoice-XTTS and activation are §4's (r13b). With TTS off the item goes on silent, with captions.
9. §2.6's daily overseer protocol is not in `agents/protocols/oversight.yaml` (the consultation session's). Built as a rule re-check by code inside the sweep, with a finding and the series paused. A model-sampled PR-1xx is the consultation session's to add.
10. HQ-LGL is seeded by 0028 (no thread). Thread L and the `legal` thread kind are §22.4's (r13b). Both migrations insert idempotently.
11. The render job's contract (fork R): a still's `at_s` (default 0; the api sends 3 s, and k−0.5 for a carousel's slide k). For a design, width/height are the CSS viewport and `scale` the pixel ratio (phone 780 px wide). Outputs of one shape are drawn once. A video always has an audio track (AAC silence). A killed render arrives as `fail render_killed: …` (retried).
12. Instagram: whether the live Graph API accepts `is_ai_generated` and the Bearer header is confirmed only at the owner's first real publish. Egress added a read-only `permalink` method. There is no delete in the API, so it is `remove_by_hand`.
13. IRANYekanX is a licensed font (licence no. 136710), not open source. It is the hub's existing font (design/fonts) and ships with its licence file in the render image.
14. Network `hq-media` is 172.30.23.0/24; the other half must not reuse it.
15. A step stored with `media.item` closes its work item `done` with the item as evidence (HQE01 needs one).
16. The signed URL's key is derived (HMAC, label `hq-media-public-url-v1`) from the agent token key the api and the worker already hold; no new secret.
17. From fork D: the overseer reviews a draft with `skill.review` and its RD- ref (a fifth check `ceiling`). A draft's eval passes at 70/100. A draft role reads only its own company, even in the holding. `role.draft` takes an optional `ref`, and a draft's charter text is capped at 7,000 characters.
18. tests/test_hiring.py runs migrations down and up. With rows of the new decision kinds present, 0025's upgrade re-checks the kind CHECK; run it on a fresh database (alphabetical order does).
19. The company's monthly envelope and the hub's 600 K daily cap do not fit a daily reel per company (see the token estimate); the cap is the owner's.
20. The worker never held its OpenBao client (`hub.bao` was set in the api only), so its per-call secrets could not be read: a publishing account's token here, and prompt 10's support-channel tokens and prompt 12's deploy-diff tokens as well. The worker now sets `hub.bao` to its own AppRole client; its policy already reads `kv/tools/accounts/*`.
21. `media` fits the full profile (also with TTS). It stays off by the prompt 12 rule: the memory priority among the opt-in profiles is the owner's, and it needs `make install-systemd`.

### Owner tasks
1. §0.9's six decisions. The defaults hold until you answer:
   - Opus 5.5 for motion graphics
   - ParsVoice-XTTS in your own voice (the other half), Piper until then
   - no GPU rental, no music library
   - 2 reels / 3 stories / 2 posts a day per series
   - no counsel mailbox
2. The publishing accounts of each company. None exists yet, and nothing publishes until both steps are done for that account:
   - In the app: `telegram-<co>` (site `api.telegram.org`, the channel in `policy.inject.username`; the bot an admin with post and delete rights) and `instagram-<co>` (site `graph.instagram.com`, the page's username).
   - In your own terminal: `make account-secret KEY=telegram-<co>` and `KEY=instagram-<co>`.
   - Instagram also needs the domain over HTTPS: `HQ_SITE_ADDRESS`, and egress's `EGRESS_PUBLIC_HOST`.
3. The memory order: `media` fits the full profile with TTS, but not with MCP, the substitutes' runner or their web browser. Switch it on with `make install-systemd` and `make media-on`.
4. Each company's active brand (mark and palette): the `brand` check needs it.
5. Opening hiring for the MEDIA teams (hiring is closed).
6. Sealing each company's first series. A new series starts with `auto_publish: false` per the director's charter; every item is then a card.
7. The agents' daily token cap (600 K) against the per-reel cost above.
8. Listening to the voices blind and choosing (the other half, §4).

## Legal and voice (branch r13b: §3, §4, and the legal and voice rows of §5 and §6)
- Branch **r13b** from `dev/p13-base` 4f59c82 (prompt 10 + prompt 12's two parts joined, Piper TTS off, + main up to "Prompt 13 sent"); nothing else merged. The media studio (§1, §1.1, §2) is r13a's. **Not deployed.**
- **Migration:** `apps/api/migrations/versions/0028_1_legal_voice.py`, revision **0028_1**, down_revision **0027_1** (the parent re-chains it after r13a's 0028). Schema `legal` (cases, case_events, emails, mailbox) and in `media` (created only if missing: r13a's 0028 may make it) the tables voices, voice_samples, speech_jobs, voice_references; every table company_id + FORCE RLS + no delete (case_events and voice_samples append-only). Decision kind `email_send` and thread kind `legal` are added NOT VALID and then validated in their own statement (the head validates); thread code `L`; the wake trigger wakes the counsel on an owner message in L at P2; task classes `legal_case`, `legal_email`.
  - Two older migrations changed so a down-and-up run (test_hiring: 0009 → head) keeps later rows: **0018** adds its two thread CHECKs NOT VALID, **0025** its decision-kind CHECK NOT VALID (0028_1 validates both at the head). Deployed databases are not affected (those revisions already ran).
- **Hub state kept:** holding kill switch and `HQ_MORNING_REPORT_LLM=off` untouched; `HQ_PROVISIONING` off; no owner login, key or token used; `HQ_TTS` stays off; no published port; real-model tokens spent: **0**.
- **What could wake a model or an outside call, and its gate:**
  - the mail poller `hq-legal-mail-poll` (every 5 min): nothing at all while the holding is locked (no mailbox call); without the `mail` account nothing either;
  - the bake-off schedule `hq-voice-bakeoff` (daily 03:40): nothing while the holding is locked;
  - the TTS job (timer, `HQ_TTS=on` only): both claims (`/internal/v1/tts/claim`, `/internal/v1/voices/jobs/claim`) answer 204 while the holding is locked;
  - the sealed email's one send: the decision's effect in the worker, which waits while the holding or the company is locked or the card is held;
  - the counsel's runs (owner in thread L, a case's work item, a reply): the runner's own lock refusal; every agent write of the counsel 423 while locked.
  - The TTS output's transcription skips the model punctuation pass (synthetic speech). Rule-only and allowed while locked: none added.

### Items
#### §3 The legal counsel
- §3 seat ok: holding template gains `LEGAL` («حقوقی», `head: false`: no manager, no manager or department thread) and `HQ-LGL` («مشاور حقوقی», kind employee, charter legal_counsel, scope holding) with thread `L` (kind legal), asleep until work. (§1 lists this seat too: r13a may have it; keep one.) Tests: test_the_holding_has_legal_and_hq_lgl_in_thread_l, test_the_owner_in_thread_l_wakes_the_counsel_and_only_it_answers_there (P2; HQ-PA refused in L).
- §3.1 ok: `legal.cases` (LC-0001, company_id = the company the case is about), timeline `legal.case_events`; `GET /legal/cases` (company, status, cursor), `GET /legal/cases/{ref}` (timeline and emails), `POST /legal/cases` (owner, wakes the counsel with a P2 work item, run_meta task_class legal_case), `POST /legal/cases/{ref}/close` (409 while an email waits); stream `legal.case` on topic `legal`; `Links.case`. A CEO asks through `work.request {company: HQ, department: LEGAL}` (assigned to HQ-LGL; any other holding department still 403). Tests: test_the_counsel_reaches_only_its_own_cases, test_a_ceo_asks_the_holdings_counsel_through_a_work_item.
- §3.2 email ok: `email.draft` → card `email_send` (A3) with the exact message (from, to, cc, subject, body, attachment sha256s, lang) and `digest` = SHA-256 of its canonical form; the seal is `decision.approve` step-up on the digest (the ref is refused), amendments 422, a changed or superseded email 409 decision_not_pending, no mailbox 409 account_not_configured (the card stays a card: owner decision §0.9 #6). Approval queues it; the worker's effect sends it once after the lock checks (claim → send → record; a claim left by a crash is never resent; a failure is never retried). A new draft supersedes a waiting one (its card withdrawn); reject/return reopens the case and wakes the counsel. Tests: test_an_email_leaves_only_by_the_seal_and_exactly_once (fake SMTP: one message, exactly the sealed one; a second effect run sends nothing), test_a_change_after_the_owner_saw_it_is_a_new_card, test_without_a_connected_mailbox_a_draft_stays_a_card, test_reject_reopens_the_case_and_closing_waits_for_the_seal.
- §3.2 replies ok: the poller reads the holding mailbox through egress (IMAP, BODY.PEEK, UID cursor and UIDVALIDITY), keeps only replies naming a sent message (In-Reply-To/References), masks body and subject, stores them on the case (`email_in`), attachments through §17.1 (type by bytes; images cleaned in the child; PDF text outside the transaction; others named only), kept in the holding where the counsel's files.read reaches them, and wakes the counsel (P2, task_class legal_email). Unrelated mail is not stored. Tests: test_a_reply_reaches_its_case_and_wakes_the_counsel_unrelated_mail_does_not, test_the_poller_does_nothing_while_the_holding_is_locked.
- §3.2 mailbox ok: service account `mail` (site, `inject.username`, ports 465/587 and 993, optional `policy.mail {imap_host, smtp_host}` on the same site); the secret only from OpenBao for one call, only to egress. Egress `POST /v1/mail/send` and `/v1/mail/fetch`: the account's own host and ports, TLS with the name checked, the guard's checked public address, the envelope sender the account's address, STARTTLS required on 587, a fetched message holding the secret dropped. Tests: test_the_mailbox_password_never_shows (answers, decision, mail.read, /tools/accounts and logs), egress test_mail_out.py (11 tests, 8 of them refusals).
- §3.3 ok: forms and portals are `propose` cards `a3_action` with `action: "form_submit"` (new value). Test: test_a_form_is_an_a3_card_the_owner_submits.
- §3.4 ok: tools `case.open`, `case.note` (deadline, status), `email.draft`, `mail.read` (own cases only: another counsel's case is 404) in the gateway (addresses kept as written and checked, text redacted) and the api (OPA `legal_voice.rego`: charter legal_counsel, holding scope). Tests: gateway test_legal_tools.py (6), OPA legal_voice_test.rego (6), test_the_counsel_reaches_only_its_own_cases.

#### §4 Voice
- §4.1 ok: one registry `media.voices`: the briefings of §21.4 speak with its active voice (when the image ships it; else `HQ_TTS_VOICE`), and so does `media.voice` (A2, the voice producer in its own company; a non-commercial voice not chosen → 409 licence_not_chosen). The TTS one-shot of prompt 12 got a second queue beside the briefings (`/internal/v1/voices/jobs/{claim,done,fail}`), each job with its own voice (a voice not shipped fails, never another voice), its RTF and this synthesis' own peak (wait4). The narration's end calls `voices.ON_NARRATION` hooks (r13a's pipeline moves its item on there). Tests: test_the_briefings_speak_with_the_registrys_active_voice, test_media_voice_queues_the_narration_with_the_active_voice, tts test_voice_jobs_speak_with_their_own_voice_and_send_their_numbers.
- §4.2 ok: fixed Persian scripts (`numbers`, `latin`: RSI, MACD, Bitcoin, Ethereum, Fibonacci, `crypto`, `long` 66 words, `reel60` 159 words with the risk warning), spoken as the hub speaks them (no digit left). Daily schedule queues the missing samples; the one-shot sends each Ogg with its numbers; it goes through §17.1 (type by bytes, ffprobe length, processing row, neutral file name for the blind listening); `rtf` = work ÷ speech of the round, `mem_mb` = highest peak; `GET /media/voices` with samples; `POST /media/voices/{id}/score` 1-10. Operator run `make tts-bakeoff`. Tests: test_the_bakeoff_queues_once_and_its_audio_goes_through_17_1, test_the_bakeoff_and_the_tts_job_do_nothing_while_the_holding_is_locked, test_the_tts_images_scripts_are_the_hubs_spoken_scripts, tts test_bakeoff.py (8).
- §4.3 ok (candidates; licences as their cards state them, read 2026-10-23): see the table below. Measured on this CPU: the four Piper voices (shipped, each file pinned by sha256 in `services/tts/voice.lock.json` and `ADD --checksum`). Not measured, recorded: ParsVoice-XTTS (gated download: needs the owner's Hugging Face account; XTTS-v2 on CPU ≈ 2.5-3 GiB, over the tts budget), Chatterbox Persian (gated, CC BY-NC 4.0, over budget), ManaTTS (needs GPU training: plan and estimate in RUNBOOK §31.13), piper-gyro (dataset licence unstated: not shipped). No permissive multilingual model lists Persian (Kokoro, Chatterbox multilingual; MMS-TTS fas is CC-BY-NC). Test: test_the_registry_has_every_candidate_with_its_licence_and_numbers.
- §4.3 owner's voice ok: `POST /media/voices/reference {file_id}` (owner only; the owner's own audio upload, 60-180 s, never attached; 422 otherwise), `GET /media/voices/reference` (404 when none; `{file, duration_s, created_at, state, reason_fa}`); no agent reads it (files.read 403), it is sent nowhere; no cloning engine is installed, so it waits. No recording exists: owner task. Test: test_the_owners_reference_is_the_owners_and_never_an_agents.
- §4.4 ok: `POST /media/voices/{id}/activate` 🔏 voice.activate (target = id): non-commercial without `accept_non_commercial: true` 422; not installed or not measured 409 not_ready (ParsVoice-XTTS today); one active voice; `licence_commercial` on every row and every narration result. ParsVoice-XTTS is the owner's §0.9 default but stays a candidate until it is installed and the owner explicitly chooses it. Test: test_a_non_commercial_voice_is_never_active_without_the_owner.

#### §5, §6
- §5 ok: the charters (legal_counsel, voice_producer) and tools.md seeded as they are; charter test: every charter tool is in tools.md, `media.review` is the media director's only, `email.draft` and `mail.read` the legal counsel's only, `media.voice` the voice producer's. Test: test_every_charter_tool_is_in_the_catalog_and_the_exclusive_ones_stay_exclusive.
- §6 memory ok: the poller and the send run in the existing worker, the mailbox through the existing egress (no service, no port). TTS: the same one-shot, profile `tts` (off), `MEM_TTS=320m` kept; Piper now reads lines of at most 8 words (at 14 the heavier voices peaked 337 MiB and the container hit 320). Gate unchanged: full+tts 11216 of 12288 MiB, lean+tts 6192 of 6196. Image +190 MB disk (three voices).
- §6 cost ok: the counsel's runs use the holding's envelope (≤ 8 steps, 200K tokens a run by its charter; classes legal_case / legal_email, never on another provider); the TTS spends no token. Real tokens while building: 0.

#### §0.7, §8
- §0.7 ok: every new table in test_rls_all_tables (schemas legal, media; mailbox, voices, voice_samples, voice_references holding-only) and test_schema_rules; every change audited (legal.case_open/case_note/case_close/email_draft/email_send/email_in, voice.score/activate/reference/audio, media.voice).
- §8 ok: OpenAPI regenerated (additive: 17 operations, 27 schemas; AccountPolicy, DecisionIn and Links widened); RUNBOOK §31.11-§31.14.

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
- Container peak 264.8 MiB. RTF includes loading the model for every job. The reel text speaks 64-76 s. With 14-word lines: 293-337 MiB peaks (the container at its 320 MiB limit); with 10: up to 307 MiB.

### Contract notes
- §22.7 email `state` gains `queued` (sealed, waiting to leave, e.g. while locked), `sending` and `failed` (a send that did not go; never retried); `Email.error`.
- §22.2 `Voice` gains `installed` (the hub's TTS image ships it), `measured_on` and `version`; its OpenAPI schema is named `RegistryVoice` (the briefing's `Voice` block already had the name).
- §22.4: a case's email cannot be sealed while the mailbox is not connected (409 account_not_configured, nothing changes); the card stays readable.
- §22.4: reply attachments are kept in the holding (the counsel's files.read reads its own company only); the case's company is on the case.
- §22.3: the owner's reference must be the owner's own upload, not attached to a message (so no agent ever reads it); 60-180 s, else 422.
- `a3_action.action` gains `form_submit` (§22.4). `POST /internal/v1/media/voice` answers 202 with the job (the narration arrives later).
- `media.voices` ids are stable text keys (`piper-amir`, `parsvoice-xtts-owner`), one per engine and speaker.

### Not done, and why
- ParsVoice-XTTS and Chatterbox are not measured: both downloads are gated behind a Hugging Face account (the owner's), and both are over the tts memory budget; recorded in the registry with the reason.
- ManaTTS voice not trained: needs a rented GPU (owner decision §0.9 #3); plan and estimate in RUNBOOK §31.13.
- No bake-off audio is in the production registry yet: the hub's queue runs only with `HQ_TTS=on` and the holding unlocked; the local run's numbers seed the registry, its Ogg files stayed on this machine (scratchpad).
- Test runs (fresh database each): the whole api suite, 731 tests: 714 passed, 17 failed, none from this branch; services (hq-common, gateway, egress, tts, llm-router) all passed; lint, mypy, OPA (130 tests, 100% coverage), hadolint, yamllint, compose-config, memory-budget, gitleaks clean.
- The 17, pre-existing (checked on the base 4f59c82 with the same tests): `test_agents_more::test_propose_section_is_generated_from_the_api_models` (the p13 charters in agents/ put `motion_designer` before `referral_rescue`); `test_inquiries_errands::test_the_advisor_v2_has_its_read_tools` (prompt 11's tools are not on this base); and 15 prompt-12 tests (test_p12a_substitutes 11, test_p12_joins 3, test_p12a_advisor 1) that need the substitutes' seed and fail when they run after test_hiring's 0009 → head cycle in the same session (they pass on a fresh database).

### Owner tasks
1. §0.9 #6: the legal mailbox (Gmail, Workspace or the domain's mail): add service account `mail` in the app (site, address, ports 465 and 993) and `make account-secret KEY=mail` (an app password).
2. §0.9 #2: to try ParsVoice-XTTS: accept its terms with your own Hugging Face account and decide on the memory (it does not fit the tts budget); its licence is non-commercial.
3. §0.9 #3: a rented GPU for the ManaTTS voice (≈ $15-70), or not.
4. Record your reference voice in the app (1-3 minutes of clean speech) when a cloning engine is wanted.
5. After launch, turn the voice on (`make tts-on`) so the hub's bake-off makes the samples, listen blind, score, and choose the active voice (🔏).
