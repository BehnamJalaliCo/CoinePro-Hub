PROMPT_14 REPORT (the archive of record of the holding and of every company, with its open layer)

## Merged on 13 (branch r14f)
- **Merged on 13:** r14 (7eb7562) is merged onto the deployed prompt 13, `server/p13-media-legal` 75712ba (prompts 6 to 13, migration head 0028_1). Branch **r14f**. Not deployed; deploying is the parent's.
- **Migration chain:** `0025` → `0026` → `0026_1` → `0027` → `0027_1` → `0027_2` → `0028` → `0028_1` → `0029` (the head; down_revision `0028_1`, unchanged).
  - `0028_1` no longer validates, as r14 left it. Its text changed only; the production database ran it once and is not touched.
  - `0029` is the only revision that validates `decisions_kind_check` and `threads_kind_check`. They hold every kind of 11 to 14 (test_only_the_head_validates_the_kind_checks, test_the_head_holds_every_kind_of_11_to_14_validated).
- **Conflicts, resolved as unions:**
  - the runner's rule for system roles (below);
  - knowledge.search: 11's `knowledge`, 12's `docs`, `code` and `notes`, and 14's `records`, in the api and the gateway's `SearchIn`;
  - the decisions route: 11's authority refresh, then 14's destroy queue;
  - the app's routers (12's ask, reviews and dceo beside 14's archive);
  - the worker's mounts (12's git repo and `hq-git` beside 14's archive seed);
  - `.gitleaksignore`, and the chain line of RUNBOOK §31.
  - RUNBOOK keeps §29 (11), §30 (12), §31 (13) and §32 (14). Every report is kept.
  - OpenAPI regenerated: **528 operations**, 75712ba's 494 plus the archive's 34. Nothing removed or renamed.
- **Fixed where 11 to 14 meet:**
  - **Ask the hub reads the archive** (12 §2, contract §21.2 and §23.9):
    - `corpus.retrieve` takes kind `record`. `archive.search.ask_hits` ranks records the way the corpus ranks its candidates.
    - The ask's clearance is set on the transaction first, so RLS drops a record above it before anything is ranked: it is never counted or quoted.
    - File text is matched and quoted only where the content is visible; a sensitive value only from `confidential` up.
    - The owner's clearance in an ask is capped at `agents_max` (contract note 13).
    - Citation kind `record` in the api and in the gateway's `ask.answer`. The librarian's own record hits join its ask's retrieved set.
    - Test: test_ask_the_hub_finds_records_only_within_the_askers_clearance. It covers the owner, an agent's own-company clearance, internal everywhere, no clearance, and the librarian's own search. A lower clearance never sees a higher record, and the secret record is never in an ask.
  - **The librarian could not run on 13.** `agents.queue_run` refused every system role, and the runner let a system role run only for a meeting turn, so an ask that woke HQ-LIB always ended `failed`.
    - With 0029's `queue_run` and the union rule, a system role with a system charter runs: the librarian for its ask, the archivist for its items.
    - The secretary runs only for a meeting, and HQ-SYS (no charter) never.
    - Test: test_system_roles_with_a_system_charter_run_and_the_secretary_only_in_a_meeting. The librarian answers an ask in its own run, citing a record.
  - **A Jalali date in a document:** `archive.suggest` called the advisor's `jalali_to_gregorian`, which prompt 11 replaced. It now uses `gov_common.from_jalali` (found by mypy; test_the_archive_reads_jalali_dates_with_prompt_11s_calendar).
  - **knowledge.search:** `records` sits beside 11's four-layer `knowledge` in one call, each under its own rule (test_records_and_the_four_layers_in_one_knowledge_search).
  - **test_hiring's round trip:** r12f's `reseeded` fixture runs the deploy's seed after it, and that seed brings the archive's open layer back.
    - test_a_round_trip_keeps_a_card_of_every_later_kind now also keeps `archive_schema` and `archive_disposal` cards and ends on 0029.
    - After the re-seed it finds the levels, the classes and HQ-ARC again.
  - **Checked, unchanged:**
    - the advisor's tools test;
    - the prompt order 13 set (_common, the sealed charter, the role, the department identity, the skills). The archivist's prompt follows it, with no department;
    - the template departments: HQ-ARC (system, no department) beside 13's LEGAL with HQ-LGL, 12's HQ-LIB and 11's HQ-SEC.
  - **Tests that assumed what no longer holds:**
    - test_agents counts system runs within its own test.
    - Two archive tests count a record's notifications since the record was made: a round trip restarts the archive's ref sequences, while notifications stay.
    - test_p12f_join's chain ends on 0029.
- **Hub state:** nothing new runs on its own and nothing calls a model.
  - An ask that needs the librarian still answers 423 while the holding is locked.
  - A queued system-role run is refused `locked` like every agent's.
- **Contract notes (r14f):**
  13. §23.9 says an ask searches records "within the asker's clearance". The asker is the owner, who sees everything, but the passages go to the librarian, a model.
      - Built: the owner's ask clearance is capped at the level marked `agents_max` (`confidential`). A `secret` record (encrypted, a passkey to view) never reaches a model or an ask's stored passages.
      - An agent's clearance is capped already.
  14. §21.2's citation and scope kinds have no archive kind. Added `record` (an `AR-…` ref) to both.
- **Gates on r14f (test name p14 and p14s, image tag p14):**
  - **api, the full suite, fresh database:** green. 826 passed, pytest exit 0, 45 minutes.
    - The first full run had one failure: test_p12f_join's chain still ended on 0028_1. It was fixed (4a1e6e5) and the full suite run again, fresh.
    - Before that, targeted runs: the joins (p12f, p13f, p14f), the archive's two files, test_hiring, test_agents, test_inquiries_errands, test_p11_meetings, test_rls_all_tables, test_schema_rules, test_openapi, test_worker, test_stream_topics and test_p10_foundation.
  - **services:** gateway, hq-common and llm-router: 691 passed. services/ocr is untouched since r14.
  - **lint** (ruff, format, mypy --strict; api and services): green.
  - **OpenAPI:** regenerated, 528 operations.
  - **Other gates:**
    - opa: 177/177 at 100% coverage.
    - shellcheck: 80 scripts.
    - compose-config and compose-rules: lean and full.
    - memory-budget: full 10896, full+ocr 11280 ≤ 12288 MiB, so `ocr` fits on full; lean+ocr is 60 over. `ocr` stays off.
    - infra.sh: green, including `ocr` off by default.
    - gitleaks: history and tree clean.
  - The test envs p14 and p14s are down. `make check` and `verify-live` are the parent's.

## Branch and state
- Branch **r14** from `dev/p14-base` d04b02b. That base is prompt 13 joined (media, the legal counsel with cases §22.4, voice), on prompt 12 parts A and B and prompt 10, plus main up to "Prompt 14 sent". Nothing else is merged.
  - Two forks of this agent built parts in parallel and are merged into r14:
    - **r14-gw**, head 014a321: the gateway's five tools and OPA `archive.rego`.
    - **r14-ocr**, head 29d6a88: `services/ocr`, the opt-in profile `ocr`, OpenBao transit, and the restore test's archive check.
  - Prompt 11 and the rest of prompt 12 are laid under it later by the parent.
  - **Not deployed.**
- **Migration:** `apps/api/migrations/versions/0029_archive.py`, revision **0029**, down_revision **0028_1**. It is the head.
  - It rewrites `decisions_kind_check` from the kinds it holds plus `archive_schema` and `archive_disposal`. The constraint is added NOT VALID, then **validated** at the end of 0029, together with `threads_kind_check`.
  - Downgrade re-adds both NOT VALID and drops the schema.
- **Hub state kept:**
  - The holding kill switch and `HQ_MORNING_REPORT_LLM=off` are untouched. `HQ_PROVISIONING` is off.
  - No owner login, key, token or recording was used or asked for.
  - The opt-in profile `ocr` is built and **off**. No port was published.
  - Real-model tokens spent: **0**. CI used a fake OCR and a fake transit; the real Tesseract ran only offline, in its own sandbox.
- **Base note:** the OpenAPI file committed on d04b02b was main's older copy (266 operations). It was regenerated from the code: **450 operations**, which is r13j's 416 plus the archive's 34. Nothing was removed and no schema was renamed: the archive's models all carry an `Archive` prefix.

### What runs on its own, and its gate (owner decision #8)
Every archive schedule is **rule-only**: no model, no outside call, and OCR is the hub's own Tesseract with no internet. So each one runs while the holding is locked. That is what keeps fixity alarms, the owner's reminders and the disposal cards alive before the launch.

Anything inside them that would wake an agent asks `gate.holding_lock` or `gate.automation_lock` first and waits. No work item is made and no run is queued.

| Schedule | When | What waits while locked |
|---|---|---|
| `hq-archive-daily` | 04:30, owner's zone | The archivist's retention-review item. A role's or a CEO's reminder stays `pending`. The archivist's weekly report. |
| `hq-archive-fixity` | 03:20 | The platform SRE's item. The urgent alarm to the owner still goes out. |
| `hq-archive-ocr` | every 2 min | Nothing wakes an agent. Without `HQ_OCR_URL` it does nothing at all. |
| `hq-archive-sources` | every 15 min | Nothing wakes an agent. |

- An automation's `work_item` and a role `notify` are `deferred` while the holding or the record's company is locked.
- The archivist (HQ-ARC) is refused by the runner while locked (`locked`), like every agent.
- Test: `test_the_archive_jobs_are_rule_only_and_wake_no_agent_while_the_holding_is_locked`. It runs all four jobs with the holding engaged, then counts no new HQ-ARC run and no new HQ-ARC work item; released, the sweep makes the archivist's item.
- Real Tesseract on the hub's own samples ran only with `make ocr-test` (offline). The OCR profile stays off until the owner turns it on.

## Items
- §0 ok (before starting):
  - The p14 charters and `tools.md` are seeded from `agents/` as they are: archivist v1 and legal_counsel v2.
  - `hq_common.charters` learns kind `system`, as prompt 11 asks, so the archivist's charter loads.
  - No paid service or SaaS was added: Tesseract 5 (Apache-2.0), pypdf, Pillow, resvg-py, Postgres FTS, pg_trgm and OpenBao transit.
  - Memory numbers are below.
- §1 ok (data and migration):
  - New schema `archive` with 25 tables, each with company_id under FORCE RLS in the once-per-query tenant form. No row is ever deleted.
    - The open layer and its runs: levels, clearance, classes and class_versions, fields, folders, party_kinds, parties, link_kinds, retention_rules, reminder_rules, automations and automation_runs, sources.
    - Records: records, record_versions, record_files, intake, links, holds, reminders, access_log, fixity_runs, tombstones, destroy_queue.
  - Clearance in the database:
    - `archive.can_see(level_rank, scope)` checks content; the 3-argument form checks metadata, adding the archivist's own filings up to its `metadata_level`.
    - Both read `app.clearance`, which the api sets with SET LOCAL. Without it nothing is visible.
    - They sit in the policies of records, record_files (content only), record_versions, links, reminders, access_log and tombstones.
  - Search columns: `meta_tsv`, `sens_tsv` and `text_tsv` over the Persian normaliser (`hq_common.persian`, then `core.fa_normalize`), and a gin_trgm index on the title.
  - Refs: AR-000001, FP-0001, PT-0001, RR-0001, LH-0001, RM-0001, AU-0001.
  - Append-only: a sealed version and its file are immutable by trigger (HQR01 → 409 sealed_record). A destroyed file stays destroyed. A sealed link is never removed.
  - Tests: test_rls_all_tables (filled), test_schema_rules (`archive` in SCHEMAS), `test_a_sealed_record_is_409_except_its_level_…` (as hq_api, the trigger refuses).
- §2 ok (the open layer):
  - Seed: `infra/seed/archive/*.yaml`, read through `HQ_ARCHIVE_SEED`, mounted read-only into api, worker and api-migrate. It holds the values §23 names: 11 classes with their fields, 4 levels, 3 clearance rows, 6 retention rules, 4 reminder rules, 6 party kinds, 6 link kinds, 8 sources, and the file plan of every scope.
    - Idempotent: a row is added only when its key or seed_key is missing, so a row the owner retired stays retired.
  - `GET /archive/schema` also returns `vocab`, the parties, usage counts and `owner_settings.agents_max`.
  - `PUT /archive/schema/{part}/{key}`:
    - 🔏 `archive.schema` (clearance: `archive.clearance`) on the body hash, with `If-Match`. A new key sends `If-None-Match: *`; parts keyed by ref are created with key `new`.
    - `?dry_run=1` returns the impact only.
    - Errors are `422 schema_invalid` with `fields`, against the closed vocabulary.
    - A class change is a new class version; a field is never removed, only retired, and its type and enum options are kept; a used level keeps its rank.
    - The answer is `{part, key, version, impact: {records, missing_required}, row}`.
  - `POST …/retire` takes the same step-up on its body.
  - A class that leaves filed records without a newly required field gives the archivist one work item «تکمیل N سند».
  - The `archive_schema` card carries `{part, key, base_version, body, impact}` and is checked when proposed (`propose` kind for role `system` in internal.rego). The owner's seal applies the same body, and the card is void (409 decision_not_pending) once that row changed.
  - Tests: test_the_seed_is_the_contracts_and_never_overwrites_the_owner, test_a_class_with_money_and_date_is_made_from_the_api_and_its_fields_retire, test_parts_keyed_by_ref_are_created_with_key_new_and_an_automation_runs_by_rule, test_the_archivist_files_drafts_only_… (the card).
- §3 ok (documents, versions, files):
  - Uploads go through §17.1. Intake runs before any transaction: the text layer in a child process (OCR through the worker for images and scans), then the secret scan over the name, the text and every value written. Then SHA-256 and the rule-based suggestion.
    - A secret answers `422 secret_in_document`, and the owner's waiting upload is destroyed (bytes, variants, extracted text). Nothing of it is logged or answered.
  - `allowed_mime` and `required_files` come from the class. `manifest_sha256` is the SHA-256 of the sorted `"<sha256>  <name>"` lines; the seal is on it, and the server recomputes it.
  - `secret`:
    - AES-256-GCM with a data key from OpenBao transit `archive-secret` (datakey/plaintext). Only the wrapped key is stored, and the transit key never leaves OpenBao.
    - 🔏 `archive.view` (target = ref) to see the file.
    - A level change across the encryption boundary stores the file again; the old object is removed after the commit.
  - Watermark: the viewer, the time and the ref. A PDF gets an overlay page merged by pypdf; an image is drawn on by Pillow, in a child process. The original is untouched.
  - Every view, download, metadata read and level change is an `access_log` row; `GET …/access` is the owner's.
  - Import: one draft per file and one archivist work item.
  - The archive keeps its own copy in hq-files. The owner's waiting upload is taken over (removed) once a record holds it; a file attached in a message stays with that message.
  - Tests: test_a_sealed_record_is_409_except_its_level_and_a_new_version_supersedes_it, test_a_pdf_and_an_image_with_a_secret_are_refused_and_kept_nowhere, test_a_secret_file_is_encrypted_needs_a_passkey_and_is_served_watermarked, test_intake_suggests_by_rules_and_import_makes_drafts_for_the_archivist, test_links_and_the_retention_of_a_superseded_record, hq-common test_openbao_transit.py.
- §4 ok (OCR and search):
  - `services/ocr` (the r14-ocr fork):
    - Tesseract 5.5.0 with pinned tessdata_fast `fas` + `eng` (revision and SHA-256 in `model.lock.json`), fetched by `make ocr-fetch`.
    - Sandbox: uid 10001, read-only root, cap_drop ALL, no-new-privileges, on the internal `hq-ocr` network (172.30.24.0/24) with the worker only. No port. One job at a time (a second gets 429).
  - The worker reaches it two ways:
    - the queue `hq-archive-ocr`, one file per step;
    - the `ArchiveOcr` workflow, which an intake awaits for up to 60 s.
  - The OCR text is normalised, indexed and stored with `ocr_confidence`. A page under 0.6 is marked in `low_confidence_pages` for the archivist.
  - A secret found by OCR after a file was kept quarantines it: not served, not indexed, and the owner gets a report.
  - `GET /archive/search` filters by clearance before ranking. The snippet comes only from text the reader may see; a sensitive value matches only from `confidential` up.
  - `knowledge.search` gains kind `records`, within the role's clearance (gateway and api).
  - Rule-based suggestions: Jalali and Gregorian dates, amounts with their unit, IBAN (شبا), national code, registration number, class key words, registry parties. Never filed by themselves.
  - Tests: test_a_persian_scan_gives_searchable_text_and_without_ocr_stays_none (the sample `services/ocr/tests/samples/scan_fa.png` and its ground truth), `make ocr-test` (13 cases with real Tesseract: 29 of 31 words on the image, 28 of 31 on the scanned PDF), test_a_confidential_record_is_invisible_to_an_internal_reader_everywhere.
- §5 ok (retention, disposal, hold):
  - The daily sweep (rule-only):
    - `then: review` gives the archivist ONE item, only while the holding is unlocked.
    - `dispose_card` makes at most one pending `archive_disposal` card a week for the owner (A3, step-up), never listing a held record.
  - At the seal, in the deciding transaction:
    - A record held since, or no longer due, is skipped and named in the resolution.
    - For the rest: the file rows are destroyed (with a secret's wrapped key), a tombstone keeps ref, class, title, dates, every file's hash and the decision, and the metadata and text are cleared.
    - The bytes are removed from `destroy_queue` after the commit (and by the daily job if a crash left any).
  - Rejected: the owner keeps them (`disposal_kept`).
  - Holds:
    - `archive.hold` is the counsel's (A2, for its own case) or the owner's. The scope is an explicit `records` list, or facets that must all match.
    - A held record answers 423 held to any change except a new version.
    - Releasing is the owner's alone: 🔏 `archive.hold.release` (the step-up action CHECK and pattern now take a third segment).
  - Backups:
    - The archive's files are in hq-files: in the hourly backup and on the Drive.
    - `restore-test.sh` (and the weekly test) restores the newest live archive file and checks its sha256 against the restored database. The PASS line names it (`archive=AR-…`), and the status JSON has `archive: {ref, ok}`.
    - RUNBOOK §32.5 says how restic's own retention ages out the snapshots that still hold a disposed file.
  - Tests: test_the_disposal_card_lists_only_unheld_records_and_its_seal_leaves_a_tombstone, test_a_record_held_between_the_card_and_its_seal_is_skipped, test_the_counsel_holds_what_its_case_concerns, the backup gate's new cases (scripts/quality/backup.sh).
- §6 ok (reminders and automation):
  - Daily, by `reminder_rules`: the nearest lead time that has come makes ONE reminder per record, field, date and lead.
    - `cartable` is a `decision`-level notification (§21.8, held in Khalvat, in the digest); `digest` is a `report` line; a role's or a CEO's reminder is a work item that waits while locked.
    - Closed by `POST /archive/reminders/{id}/done`, or by itself when the record's date changes.
  - Automations: the closed events, simple conditions, the six actions (notify never urgent, `raise_level` only up). No model. One `automation_runs` row and one audit row per run.
  - Tests: test_a_contract_ending_in_30_days_gets_one_cartable_reminder, test_parts_keyed_by_ref_are_created_with_key_new_and_an_automation_runs_by_rule.
- §7 ok (system sources):
  - `GET/PUT /archive/sources`. Each new event is filed once (a unique `source_ref`) as a `filed` record of its class, with `source.kind: "system"`:
    - charter_sealed (from `governance.charters` once prompt 11 is under it)
    - resolution_month (a finished Jalali month per company)
    - brand_sealed, founding_registration, server_plan_sealed, backup_restore_test (the first restore test of each Jalali month)
    - legal_email (every sent email of a case, from 13) and case_closed (the case and its timeline, linked to the case; it also sets the retention trigger `case_closed`)
  - The PDF is made by the hub's own libraries: resvg-py draws A4 pages in IRANYekanX, right to left, and Pillow binds them, in a child process. Its text is kept as `text_layer`.
  - Test: test_the_system_sources_file_the_hubs_own_records (a switch off files nothing; once per event).
- §8 ok (fixity):
  - Nightly one seventh of the files (the slice is fixed by the file id, so all of them each week); `manual` and `weekly` check all. Each run is a `fixity_runs` row; `GET /archive/fixity` returns `{at, checked, failed: [ref], next_at}`.
  - A mismatch or a missing object raises one `urgent` data-loss notification, the event `fixity.failed`, and a P1 item for the platform SRE (only while unlocked). Reading such a file answers 409.
  - Test: test_a_tampered_file_raises_the_data_loss_alarm.
- §9 ok (agents, OPA, gateway):
  - Tools: `archive.search` and `archive.read` (A0), `archive.file` and `archive.link` (A1), `archive.hold` (A2, the counsel with its case).
  - They are in the gateway (`hq_gateway/archive.py`; 9 tests), in OPA (`archive.rego`, its tests, the ops list, the employee's A2 grant), and in OP_CLASS and tool_status. The api re-checks the role and reads under the agent's own clearance.
  - The archivist **HQ-ARC** is a holding employee of kind `system` with charter `archivist`, made by the seed's `holding.yaml`.
    - The runner and `agents.queue_run` run a system role that has a system charter; HQ-SYS never runs.
    - `archive.file` on an owner's imported draft writes a suggestion only. It never files, seals, declassifies, releases or disposes: the owner's routes answer it 403.
  - Tests: test_the_archivist_files_drafts_only_and_never_seals_declassifies_releases_or_disposes, archive_test.rego (OPA 144/144), gateway test_archive_tools.py.
- §10 ok (cards, step-up, stream, codes):
  - Cards `archive_schema` (A2) and `archive_disposal` (A3, code only): both 🔏 with `decision.approve` on the card's ref, both sealed as they are (no amendments).
  - Step-ups: `archive.seal`, `archive.view`, `archive.declassify`, `archive.schema`, `archive.clearance`, `archive.hold.release`.
  - Stream topic `archive`; its events carry no title and no value.
  - Codes: `clearance` (403), `sealed_record` (409), `schema_invalid` (422 with fields), `secret_in_document` (422), and `held` (423, existing).
  - OpenAPI regenerated.
- §11 ok (tests): every case §11 lists is above. The runs are in "Gates run".
- §12 ok (this report and RUNBOOK §32, with §32.1–§32.11 and the command table's OCR rows).

### Memory (measured on this CPX42, 2026-10-23; cgroup memory.peak, offline)
| Part | Measured | Limit | Profile |
|---|---|---|---|
| OCR, one image page | 0.22–0.53 s, 53–61 MiB | `MEM_OCR=320m` (2× 149) | `ocr` (off) |
| OCR, scanned PDF | about 1.1–1.4 s a page; 142 MiB for 3 pages, 145–149 MiB for 21 pages | same | `ocr` |
| OCR idle | 18 MiB | same | `ocr` |
| `ocr-fetch` (one-shot) | 25 MiB | `MEM_OCR_FETCH=64m` | `ocr` |
| sweep, reminders, fixity, sources, PDFs, watermark | inside the worker / api (child processes under hq_common.untrusted limits) | — | — |
- tessdata_fast was chosen over tessdata_best: it read more of the sample (29/31 words against 27/31 on the image, 28/31 against 25/31 on the PDF) at about half the memory and time. best stays pinned for comparison.
- Memory gate (budget 12288 MiB on full, 6196 on lean):
  - **Fits:** full 10896; full+ocr 11280; full+ocr+tts 11600; full+ocr+substitutes 11792.
  - **Over:** full+ocr+media 12304 and full+ocr+mcp 12304 (16 over each); lean+ocr 6256 (60 over).
  - hq.sh refuses `up` over the budget (exit 3).
- **`ocr` stays off** until the owner turns it on: `make ocr-fetch` once, then `make ocr-on`. Full profile only, not with media or mcp.

### Contract notes
1. §23.1 says the owner or the archivist files a draft the owner uploaded, and §23.11 says the archivist classifies drafts. But red line 4 of the prompt and §23.0 say a model only suggests. Built the safe reading:
   - `archive.file` on an imported draft (the same files) writes the archivist's `suggestion` (`by: archivist`); the owner files it (`POST …/file`).
   - Elsewhere `archive.file` makes a new draft. No agent ever moves a record to `filed`.
2. §23.4 lists Clearance subjects `role:<role>|employee:<code>`, and the seed's "every agent role internal in its own company" needs a default. Built as subject `role:*`, used when neither the employee's nor the role's row exists.
   - Grant scopes are `own`, `holding`, `all` or a company code. `agents_max` caps content grants only; the metadata level is uncapped, as §23.12 says for the archivist.
3. `archive.declassify` targets `ref@version:level`, but the contract does not say which version. Built with the record's row `version` (its `If-Match` value), so a declassification is bound to the record as the owner saw it.
4. §23.8 names no class for `server_plan_sealed` and `backup_restore_test`. Both are filed as `other`. `founding_registration` is filed as `company_registration` without its registration number (the source cannot know it; the impact counts it).
5. The step-up action `archive.hold.release` has three segments. The step-up options route's pattern and `auth.step_ups`' CHECK take an optional third segment (migration 0029).
6. Images are scanned for secrets through their OCR text. While the `ocr` profile is off, an image's pixels cannot be read: intake keeps it with `text_state: "none"`, and when OCR later finds a secret the file is quarantined (not served, not indexed, the owner told; disposal stays the owner's).
7. The stream is the owner's alone today, so no reader below a record's clearance consumes it. To keep red line 3 anyway, archive events carry only ref, state, level and class: never a title or a value.
8. A search snippet is cut from the normalised text: Persian letters are kept, but آ shows as ا, because the index and the query both go through `core.fa_normalize`.
9. "Ask the hub" (§21.2) is part of prompt 12's rest, which is not on this base. When the parent lays it under, its corpus should read records through `hq_api.archive.search.search` under the asker's clearance (the owner: everything). `knowledge.search` kind `records` is already in place.
10. The system PDFs are rendered pages (resvg + Pillow), so they have no PDF text layer. Their text is filed from the source with `text_state: "text_layer"` (the hub wrote it).
11. The migration chain for the parent:
    - `0029` is the head and the only migration that validates `decisions_kind_check` and `threads_kind_check`.
    - `0028_1` now leaves them NOT VALID (its text changed; a database that already ran it is not touched).
    - When server/p13-media-legal, prompt 11 and the rest of prompt 12 are laid under r14:
      - keep `0028_1` without VALIDATE;
      - move `0029`'s down_revision to the head they end with;
      - keep every later re-add of a kind CHECK NOT VALID.
12. The OpenAPI file committed on the base d04b02b was main's older copy. The regenerated file matches the code.

### Owner tasks (in this order; none was done here)
1. Turn on the `ocr` profile if the budget allows it: `make ocr-fetch` once (one download over the internet), then `make ocr-on`. Full profile only, and not with media or mcp.
2. Review the seeded levels, clearance and retention rules (RUNBOOK §32.1, §32.5). The retention periods are defaults, not legal advice.
3. Upload the first documents: `POST /files`, then `POST /archive/intake` and `POST /archive/records` (or `/archive/import` for the archivist to classify once the hub is launched). Then seal what is final.
4. On launch, releasing the kill switch lets the archivist run (its work items, weekly report and review items start then).

### Gates run (test name p14 and p14s, image tag p14)
- **api, the full suite once** (fresh database). It stopped at 30 failures in `test_p14_retention`, and every failure had a cause outside the archive's code:
  - The archive tests ran after `test_hiring`, which runs the migrations down to 0009 and back up in the same session. That left the archive's open layer empty: the seed runs at deploy, not in a migration.
    - Fixed in the tests: they reseed when the open layer is missing.
    - Fixed in the migrations: `0028_1` no longer validates the kind CHECKs and `0029`, the head, does. Otherwise `0028_1`'s VALIDATE fails on an `archive_disposal` card during the way back up.
  - `test_openapi` needed a description on six archive routes: added.
  - Known, the same on the base (PROMPT_13's note):
    - `test_inquiries_errands::test_the_advisor_v2_has_its_read_tools` needs prompt 11's tools.
    - `test_p12a_substitutes`, `test_p12a_advisor`' locked case and `test_p12_joins`' three seat tests need the substitutes' seed, which `test_hiring`'s down-and-up removes. Run alone they pass, together with test_openapi: only test_openapi failed, and it is fixed above.
- **api, again after the fixes:**
  - test_p14_retention, test_hiring, test_p14_archive, test_p10_foundation, test_openapi in that order (archive cards exist before the down-and-up): all green.
  - The 20 files the full run had not reached (test_people … test_workshop_review, with test_rls_all_tables, test_schema_rules, test_stream_topics, test_worker, test_tools_mcp, test_org_work, test_agents_more): all green except the known `test_the_advisor_v2_has_its_read_tools`.
  - Before that: test_identity, test_p10_foundation and the archive's 19 tests (test_p14_archive 10, test_p14_retention 9), all green.
- **services:** hq-common (with the new test_openbao_transit.py), gateway (9 new archive tests) and llm-router, all green. On r14-ocr: services/ocr, 9 passed and 4 skipped there, and all 13 with real Tesseract in the ocr image (`make ocr-test`).
- **lint** (ruff, format, mypy --strict; api and services): green.
- **OpenAPI** regenerated: 450 operations; against r13j's file nothing removed and no schema renamed.
- **Other gates:**
  - opa: 144/144 at 100% coverage.
  - shellcheck: 80 scripts.
  - compose-config, memory-budget and yamllint: green.
  - gitleaks: history and tree clean. Two history findings are in `.gitleaksignore`: the secret-scan fixture's fake EC key, in my own commits 3d0fecd and 71ed23f. It is assembled at runtime since.
  - On r14-ocr: hadolint, compose-rules, infra.sh and the backup gate.
- The test envs p14 and p14s are down. On r14-ocr, the throwaway volume `p14o-ocr-models` (about 23 MB) is kept.
- `make check` and `verify-live` are the parent's.
