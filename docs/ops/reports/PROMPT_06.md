PROMPT_06 REPORT (media, Persian voice, Code Workshop, voice orders)

## Tasks and acceptance tests
- §1.1 `GET /treasury/breakdown?by=day`: one row per owner day (Asia/Tehran), empty days 0, 400-day cap, to <= from -> 422. Test: test_treasury_days (UTC 21:00 lands on the next Tehran day, a zero day, both 422s)
- §1.2 `HQ_ANDROID_ORIGINS` (public apk-key-hash) in the api env. Live: `curl https://hq.coinepro.com/.well-known/assetlinks.json` -> 200, `content-type: application/json`, com.coinepro.hq and .debug with fingerprint D6:D4:...:15:BF
- §1.3 the owner's 4.1 answers in RUNBOOK §14 (NOLOGIN later, 5 urgent/h stays, Valkey without persistence); §1.4 web was already up (prompt 5)
- §2 files (RUNBOOK §15): POST /files raw body; type by magic bytes (header must agree); per-kind size held while streaming; images cleaned in the api (upright, no EXIF/GPS/XMP, 40 MP cap, WebP thumb 512, agent JPEG <= 1568); video/audio -> worker FileProcess (ffmpeg poster, <= 12 key frames on scene change >= 5 s apart or evenly spaced, 16 kHz sound track -> STT) -> file.ready / file.failed (topic files); GET /files/{id}?variant= with Range (206/416), /meta; up to 10 attachments, empty body allowed; an upload belongs to the holding until attached, then moves once to the thread's company (RLS; a guarded UPDATE keeps files.files append-only otherwise); agents get images as vision blocks, video as frames + transcript, audio as transcript, never raw media or file names; gateway tool file.view (A0, own company, OPA file.read)
  - Tests (test_files_media, fake model, fake STT): 12 allowed types uploaded (jpeg, png, webp, heic, mp4, webm, mov, wav, ogg, mp3, m4a, pdf); PNG labelled JPEG, text labelled PNG, image/gif -> 415; 64 MB streamed into an image -> 413 after <= 22 MB read; EXIF+GPS gone, thumb <= 512, Range 206/416; 30 s video -> poster, >= 3 frames, transcript, one file.ready; FX file: FX agent 200, TY agent 403 (same as a missing file), re-attach in TY 422, TY agent attaching it 422; photo to a manager -> its first model call has one ImagePart (<= 1568, no EXIF), no file name in the text
- §3 STT (RUNBOOK §16): service stt (faster-whisper 1.2.1, CTranslate2 4.8.2, large-v3-turbo int8, fa, beam 5, Silero VAD), model pinned per file (revision + sha256, services/stt/model.lock.json), offline, own internal network hq-stt (worker + stt only), no port, uid 10001, read-only rootfs, cap_drop ALL, idle unload after 300 s; opt-in profile (HQ_STT=on), refused by hq.sh while over the memory budget; normaliser hq_common.persian (50-sentence test, 100% coverage); punctuation pass (stt_punctuation, P1, light model) dropped above 8% word edit distance, skipped when the text holds a maskable secret, both texts in files.processing; POST /transcribe (Temporal Transcribe on the worker; 503 channel_not_configured while stt is off); voice_transcript messages; make stt-eval (5 synthetic samples; dir=<real samples> later)
  - Tests: sample -> text (stt service tests with a tiny fake Whisper in CI); silence -> "" (200); 16 min -> 413; image -> 415; stt off -> 503; punctuation accepted / rejected (fake model); normaliser 50 sentences; voice_transcript kind
- §4 Code Workshop control plane (docs/ops/WORKSHOP.md, RUNBOOK §17): migration 0014 (workshop.workspaces, grants, sessions, events append-only, approvals; RLS InitPlan form; audit on every change); workspaces seeded from apps/api/seed/workspaces.yaml (each company's repo + HQ-HUB; idempotent); every §17.3 endpoint with step-up where 🔏 (grant and workspaces on the body's sha256, approval on S-..../AP-.... for allow only); events workshop.session / workshop.approval (topic workshop) and SSE /live with Last-Event-ID; GET /meta workshop {runtime: null}; code_session decision (A1; OPA kinds; the seal creates the grant, re-applying is a no-op); rules 1-7 in code (only hq/<ref> pushed, PR opened, merge/deploy stay sealed; dollar cap stops the session + owner notification; kill switch / deploy freeze pause sessions, new ones 423; one writing session per repo area, the next queues; masked summaries in events, full masked transcript in the file store); adapters fake (CI), managed (Claude Managed Agents over REST, tested against a fake HTTP server; always_ask -> commands.classify: allow / refuse / ask the owner), self_hosted (design only, docs/ops/WORKSHOP.md); POST /workshop/sessions -> 503 runtime_not_configured until the owner decides
  - Tests (test_workshop): no grant without the seal; session outside its grant refused (not the driver, other company, revoked); approve needs step-up, deny does not; kill switch and freeze pause, 423 for new; budget cap stops and notifies; two writing sessions never overlap in one area; automatic scan: no GitHub token in events, logs, API responses, outbox or transcript; /live resumes from Last-Event-ID; /meta runtime null; 503 without a runtime
- §5 voice orders: POST/GET /orders: text (typed or from /transcribe?purpose=order) masked, then rules (apps/api/seed/order_rules.yaml + each company's code and name + role names), then the light model (order_routing, P1, json_schema {routes:[{company,to,kind,summary_fa}]}, on the worker via the OrderRouting workflow; every code it returns is checked against the directory, invented ones dropped), then the advisor (thread A) only when ambiguous; work -> CEO or the department manager (shortcut, depth 1), code -> the running session, a new session under a grant, or a code_session decision ($20, 7 days), question -> advisor, meeting -> a work order for the CEO; order, its audio and routes kept (planner); order.routed (topic orders)
  - Tests (test_orders): «به مدیر فنی FX بگو …» -> FX-TECH-MGR with no model call; an ambiguous order -> the advisor; a code order without a grant -> a code_session decision; delegation depth 2 holds; the light model runs on the worker and its output is checked
- Stream topics files, workshop, orders in events.TOPICS

## STT performance (this CPX42, int8, beam 5, 4 threads)
| | large-v3-turbo | medium | small |
|---|---:|---:|---:|
| 30 s audio | **8.8 s** (target <= 10 s: met) | 11.9 s | 4.2 s |
| 5 min audio | 57.7 s | 91.6 s | 38.6 s |
| peak RSS (load / 30 s / 5 min, MiB) | 1644 / 1301 / 1460 | 1581 / 1561 / 1773 | 610 / 648 / 1225 |
| after idle unload | 177 | 137 | 157 |
| WER, 5 synthetic espeak-ng samples | 82.9% | 63.4% | 92.7% |

The WER numbers are from robotic synthetic voices and say nothing about the >= 95% target; it needs the owner's real recordings (`make stt-eval dir=...`).

## Memory
- Gate: full 11216 MiB <= 12486 (80% of this server); full+cadvisor 11408 <= 12288 ok; **full+stt 13392 > 12288 (over by 1104), lean+stt 7968 > 6196**: printed, not enabled, so the gate passes; HQ_STT=on is refused (exit 3) by up/run/create/start/restart while over
- stt is therefore OFF; /transcribe answers 503 channel_not_configured; videos are processed without a transcript until it is on
- Three options (numbers in RUNBOOK §16):
  1. smaller model: small needs ~1536m -> 12880, still 592 over; medium needs more than turbo
  2. lower limits (live use / limit): postgres 174/1536 -> 1024, prometheus 159/768 -> 512, tempo 115/384 -> 256, loki 72/512 -> 384, otel-collector 40/384 -> 256: -1152 -> 12240, fits with 48 MiB spare (or claude-runtime 3 concurrent CLI runs instead of 5, -768); with small, postgres + loki alone fit (-640)
  3. bigger server: CPX52 (12 vCPU, 24 GB) or CCX33 (8 dedicated vCPU, 32 GB): at 24 GB the budget is 19660 and full+stt fits with ~6 GB spare (cost: the owner's)

## Real-model spend (budget 300K)
- 4 calls, 2,959 tokens (2,747 in incl. cache / 212 out), far under 300K; the forks used none (Whisper is local, CI is fake)
  - vision through llm-router -> claude-runtime (Sonnet 5.5, one generated 800x500 JPEG): 1,070 in / 20 out; answer correct (red square left, blue circle right)
  - punctuation pass (Haiku 5.5, stt_punctuation, P1) on 3 synthetic normalised transcripts: all accepted, word edit ratio 0 / 0.05 / 0, 2-4 marks added; 1,677 in / 192 out
- Live (prod images, nothing stored): ffprobe/poster/key frames/sound track on a 30 s clip in 0.9 s; a 4000x3000 JPEG with GPS -> no metadata, agent 1568x1176, thumb 512x384. The synthetic red->green cut has nearly equal luma, so scene detection found 2 frames and the evenly spaced fallback (6) was used, as designed

## Gates
- make check: all 14 gates pass (gitleaks, compose-config, ports, compose-rules, memory-budget, shellcheck, yamllint, hadolint, opa 80/80 100%, infra, python lint, python test, python audit, live)
- Tests: api 267 passed, coverage 88.33% (domain 91%); services 352 passed, 90.17% (hq_stt 98%, persian 100%); pip-audit: no known vulnerabilities
- Deploy (make up): migrations 0012 -> 0013 -> 0014; 21 containers healthy; ffmpeg 7.1.5 in the worker; task classes stt_punctuation and order_routing seeded (not transferable); /api/v1/files, /transcribe, /orders, /workshop/sessions -> 401 without a session; /internal still 404; memory used 3.8 GB, available 11.8 GB
- Branch server/p06-media-voice-workshop from main 52d9ef4 (merges of the three forks: vision, stt, workshop/orders)

## Contract notes
- file.view (A0, own company): args {file_id}; result {id, mime, size, kind, status, width?, height?, duration_s?, transcript?, view: {image_file_ids}}; ref file:<id>. Please add it to agents/tools.md (until then it answers unknown_tool to the charters)
- GET /internal/v1/files/{id}/meta (agents) adds frames [{id, at_s}] to FileRef; a missing and a forbidden file are both 403 policy_denied (no existence oracle)
- FileRef gained kind, status, width, height, duration_s, variants {thumb, poster}, transcript (defaults keep old clients working); variants are fetched with ?variant=thumb|poster on the original's id
- An owner upload sits in the holding until its first attachment; a file already attached in another operating company is 422 (upload again), never shared across companies
- stt is on its own internal network hq-stt (worker + stt), not hq-core as the prompt said: hq-core holds Temporal, and nothing else needs to reach Whisper
- The punctuation pass is skipped (punctuation = off) when the normalised text holds something the masker would hide: no model reads a spoken secret
- /transcribe stores the audio as a file (purpose message|order|note); attaching a purpose=message audio makes the message kind voice_transcript
- New error code runtime_not_configured (503, message_fa)
- CodeSession gains area, held (budget | company_locked | work_lock) and transcript_file; new owner-only GET /workshop/sessions/{ref}/transcript
- OrderOut gains routed_by (rule | model | advisor); routes gain message_ref and note_fa; the workshop events list is a Page
- PUT /workshop/workspaces takes the whole list; a workspace left out is paused, never deleted
- A grant's driver must be in the workspace's company; owner-ordered code_session defaults: $20, 7 days
- Gaps left open (safest behaviour now): session attachments are recorded but not yet sent to the runtime; workshop usage is kept on the session row, not yet in the Token Treasury ledger (managed runs are billed on the separate API key)
- Seeded repos (behnamjalalico/TradeYar, CoineProFx, CoinePro-App, CoinePro-Hub) come from the web mock; the owner can change them in the app

## Decisions waiting for the owner
1. STT memory: one of the three options above (stt stays off until then)
2. Workshop runtime: managed (a separate API key with a monthly cap; agent + environment in Claude Managed Agents, ids and key in OpenBao kv/hq-api/workshop/managed) or self_hosted (a separate builder host, 20x subscription; design only)
3. Per-workspace GitHub tokens: fine-grained, one repo each, contents + pull requests, in kv/hq-api/workshop/github/<WORKSPACE-CODE> (the owner puts them there; nobody sees them)
4. Left from measurement, for the owner to keep or delete: volume stt-measure-models (~3.6 GB) and image coinepro-hq/stt:measure

## Review of 6 (PROMPT_06_1_FIXES.md; owner 2026-10-18: blockers §1.2-§1.4 only, on server/p07-platform)
- 1.1 ⛔ set aside with 0.2 (the workshop runs no session until the owner picks a runtime)
- 1.2 ok: the workshop's approval_result says `allow` (the contract's name), not `allowed`; test reads `data.allow`
- 1.3 ok: treasury breakdown/what-if take a bare date as the owner's day (`to` counts its own day) and a time without a zone as the owner's time; default from = 1st of the owner's month; `from=2026-10-01` was a 500. Test: by=company/day/model/task_class, naive times, what-if, the default
- 1.4 ok, with 7.1 §1.2 (one helper, hq_common.untrusted): images are parsed only in a limited child (192 MiB address space, 20 s CPU, killed at 30 s, oom_score_adj 1000), outside any transaction; metadata (EXIF/GPS/XMP/IPTC, comments, previews, trailing data) is stripped from the photo's own bytes without decoding it, so the original keeps its pixels and a one-tag orientation (browsers and Coil rotate it); the agent variant and thumb are decoded at reduced scale and upright; MAX_PIXELS 40 MP, > 80 MP and anything the limits stop → 415, not 500. Test: a 40 MP photo through both upload paths, 201 in ~1 s, api growth < 50 MB, GPS gone
- Left for after the weekly limit renews (owner): every "باید" and small item of 6.1, STT (§0), deleting stt-measure. Open from 1.4: HEIC above ~14 MP (24 MP iPhone photos), WebP above ~9 MP and PNG above ~30 MP do not fit the child's 192 MiB and answer 415; lean's api limit (224m) cannot hold a 192 MiB child next to it

این گزارش را برای Claude سشن مشورت ببر.
