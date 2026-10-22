PROMPT_09_1 REPORT (the company seal from the owner's PNG logo; contract §18.14) — code only

- **Branch** `r91` (server/p09-1-seal), from server/p09-founding 319b1f8. **Not deployed** (the parent merges 9.2, runs `make check` and deploys). Migration **0024** (down_revision 0023).
- §0 ok: read CLAUDE.md, the run sheet, contract §3.1, §17.1, §18.8, §18.14 and §18.16, design/brand/SEAL.md, design/brand/companies/README.md and apps/web/scripts/gen-assets.mjs; both apps (b92125c) read from main. No model is called anywhere; CI uses synthetic PNG and JPEG files only.
- §0.6 ok: org.company_brands has company_id, FORCE RLS, one audit row per change (brand.upload, brand.retrace, brand.traced, brand.failed, brand.activate, brand.seed) and the owner's interaction row; it is in test_rls_all_tables and test_schema_rules (schema `org`).
- §0.7 ok: measured in the test image (test_the_tracer_child_has_no_network_and_a_4096_png_fits_its_limits). A 4096 x 4096 RGBA PNG peaks at 188 MiB resident and 268 MiB of address space, 1.5 s of CPU; an RGB one at about 190 MiB and 300 MiB. The child gets 384 MiB of address space, 50 s of CPU and a 60 s deadline. The worker runs one child at a time, and the full profile's worker cap (512m, about 100 MiB of its own) holds it, so the cap stays as it is and the input stays 4096 px. The lean profile (224m) would not hold it; there the kernel stops the child first, and the version fails `too_large`.
- §1 ok: 0024 adds org.company_brands. It is versioned and append-only except its state: a trigger allows content only while `processing`, and allows only these moves: processing to proposed or failed, proposed or retired to active, active to retired. There is no DELETE, and at most one active version per company. `Company.brand_version` and `Founding.brand` are read from this table. The digest is sha256 of the canonical JSON (sorted keys, no spaces) of mark, wordmark, ink, accent, accent_night and accent_day, and the server recomputes it. Tests: test_the_digest_is_the_canonical_json_of_what_is_drawn, test_a_version_is_append_only_except_its_state.
- §2 ok: hq_api/brand_trace.py runs in the worker's activity `brand_trace` (workflow BrandTrace). The work happens in an hq_common.untrusted child with no network, using a new `Limits(network=False)`: a seccomp filter refuses socket() and io_uring, and Python's socket module refuses too. The steps:
  - bomb guard (`MAX_IMAGE_PIXELS`), 4096 px cap, type checked by content
  - background from alpha, or from the four corners when they agree within CIE ΔE76 ≤ 5 and the border is that colour
  - trim with 4% padding, work at 1024 px
  - OKLab weighted k-means: alpha < 0.5 and colour edges do not vote; ink is the largest low-chroma cluster
  - VTracer per layer, binary spline; detail 1..5 sets the speckle filter and the corner threshold; holes even-odd; 2 decimals in a shared vb
  - 48 KB budget, with detail lowered automatically down to 1
  - every d checked against the SVG path grammar, in the child and again in the worker
  - resvg re-raster: iou at 256 px; thinnest feature at 16 px; OKLCH lightness fix for 3:1 on both themes' page surfaces; palette ≤ 6 by area
  Tests:
  - test_a_transparent_two_colour_png_becomes_ink_and_accent (iou ≥ 0.9)
  - test_a_one_colour_png_is_one_ink_layer
  - test_a_jpeg_on_flat_white_works_with_the_warning
  - test_a_busy_photo_fails_no_background
  - test_a_decompression_bomb_is_refused_before_it_is_decoded: 20000 px refused unread, under 120 MiB
  - test_a_complex_logo_lowers_its_detail_or_is_too_complex
  - test_a_very_dark_accent_gets_a_lighter_night_accent
  - test_no_d_outside_the_grammar_is_ever_stored
  - test_only_svg_path_grammar_is_a_d
  - test_a_too_dark_accent_gets_the_nearest_passing_lightness
  - hq-common's test_a_child_without_network_opens_no_socket
- §3 ok: the brand routes, all owner only:
  - `POST /companies/{code}/brand` (202, Idempotency-Key required)
  - `GET /companies/{code}/brand` and `/brand/versions` (a Page, newest first)
  - `POST /…/{version}/retrace` (202)
  - `POST /…/{version}/activate`, 🔏 `company.brand` on the recomputed digest; the previous version is retired, with one audit row
  - `GET /brands`, with ETag, `Cache-Control: private, no-cache` and 304
  `brand.updated` goes on the new stream topic `companies`. Tests:
  - test_the_seal_needs_step_up_on_the_digest_and_retires_the_old (no step-up 403, another digest 403)
  - test_a_version_changed_after_the_owner_saw_it_is_not_sealed
  - test_brands_has_an_etag_that_changes_with_a_seal
  - test_every_brand_route_is_the_owners (agent token 403, holding 422)
  - test_retrace_a_wordmark_and_what_is_carried_over
- §4 ok: `POST /foundings/{ref}/activate` without an active brand answers `409 not_ready` with `missing: ["brand"]` (Problem gains `missing`), unless the body is `{skip_brand: true}`. `Founding.brand` is `missing`, `proposed` or `active`. Tests: test_founding's end-to-end run (409, then skip_brand works), and test_a_founding_activates_with_a_sealed_brand (a proposed brand is still 409; an active brand works).
- §5 ok: the seed runs in api-migrate's seed() and makes an active version 1 for each folder of design/brand/companies/<code>/ whose company exists and has no version yet. It uses `*-mark-flat.svg` and `*-wordmark*-flat.svg`, with layers by --logo-ink/--logo-accent as in gen-assets.mjs, and `source.kind: "seed"`. No company code is in the code: folders are read, and their number is not fixed. It is idempotent, and an upload is never touched. api-migrate and test-env mount the folders read-only as HQ_BRANDS_DIR. Tests:
  - test_the_seed_is_version_1_of_every_design_folder: every d equals the design file's own d
  - test_the_seed_reads_folders_never_codes_and_never_touches_an_upload
- §6 ok: the OpenAPI is regenerated and RUNBOOK §27 is added (building a mark from a PNG: options, errors and their fixes; the seed; the holding's seal is not data). Gates on this branch, test env p9a, image tag p9a, all green:
  - api: full suite on a fresh database, 427 tests, exit 0 (schemathesis fuzz included), 85% coverage overall
  - hq-common: 209 passed
  - lint: ruff and mypy --strict
  - OPA: 102/102
  - shellcheck, compose-config, compose-rules, yamllint, memory-budget and gitleaks: ok
  The full `make check` and `make verify-live` are the parent's.
- Licences: VTracer 0.6.15 is MIT (visioncortex). The rasteriser is resvg 0.48.1 through resvg-py 0.5.0: resvg is Apache-2.0 OR MIT (MPL-2.0 before its relicence), and resvg-py is MIT. numpy 2.5.3 is BSD-3-Clause and is the same pin as stt's. All three are pinned with hashes through lock.sh; only apps/api's two locks changed.
- Real-model spend: 0 tokens. Nothing here calls a model or anything outside the hub. The trace is code in a no-network child, so it runs while the holding kill switch is engaged (the owner is never locked out). reconcile_decisions also restarts versions left `processing` for over 10 minutes; that is rule-only too.
- **Contract notes:**
  - `CompanyBrand` gains `part` (`mark`|`wordmark`, the part this version traced).
  - `/brand/versions` is a `Page` (§1 lists); both apps accept a list or a page.
  - A `retired` version can be sealed again; it is the way back to an older seal.
  - Sealing a version that is not proposed or retired is `409 validation_failed`; the web mock's `brand_not_proposed` is not a server code.
  - A version without a mark is `409 not_ready` with `missing: ["mark"]`.
  - `digest` is always recomputed from the stored row; a processing or failed version has one too, but cannot be sealed.
  - Problem gains `missing`.
  - Background, foreground and edge decisions use CIE ΔE76. OKLab x 100 makes near-black noise look far, which turned black backgrounds into a third colour. Quantisation stays in OKLab.
  - "Low chroma" is OKLCH C < 0.08; without such a cluster, the least chromatic one is ink.
  - `iou` is pooled over the layers (sum of intersections over sum of unions), so a colour swap counts.
  - `min_feature_px_16` is the thinnest ink part or gap on the trace rasterised at 256 px, by an octagonal opening, times 16/256. It is capped near 3.06.
  - The accent fix keeps hue and chroma, and lowers chroma only where sRGB cannot hold it.
  - «بدون شفافیت» follows the image's transparency, not its format: a WebP with alpha has no warning, a PNG without alpha has it.
  - `options` after the trace holds the colours found and the detail used.
  - Status reasons beyond the contract's two: too_large, too_small, unreadable, unsupported, empty, invalid_path, stopped.
  - A logo upload still in the holding moves to the company, like a first attachment; another company's file is 422.
  - `POST` on the holding is 422: its seal is fixed.
  - The seeded versions get `accent_day` where their accent fails 3:1 on the day page (TY's teal, FX's orange). The web mock leaves it null; the server applies the rule.
  - The seed's `source.path` is `design/brand/companies/<folder>/`; its checks.iou is 1.0 (the design file is the source) and its palette is by rasterised area.
  - Founding activation checks the brand after the step-up; a refused call rolls back, so the step-up stays usable.
- For the owner: nothing to do before the deploy. After it, give each company's PNG logo in the app (company page or founding step «مُهر شرکت»), look at the previews and seal it. The existing companies already show their seeded version 1.

- **Deploy (2026-10-22, `server/p09-1-seal` 8de5373, on top of the deployed 8+9):** backup first (snapshot 97bdb04b, local + Google Drive); `make up` ran migration 0023 → 0024; all services healthy; `make verify-live` passed (only the known by-IP GAP lines). Seeded brands: FX, PC and TY v1 active (from `design/brand/companies/`). Zero model calls since the deploy; the holding kill switch stays engaged. The merge with 9.2 needed one fix: 9.2's placeholder `FoundingBrand` gave way to 9.1's (7 founding/brand tests and lint green again).

این گزارش را برای Claude سشن مشورت ببر.
