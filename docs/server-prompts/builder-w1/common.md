# Common brief for every prompt-21 builder (read fully)

You are one of three parallel builders of **prompt 21** of the CoinePro HQ hub (repo checked out in your git worktree, your cwd).
The coordinator (me) merges your branch afterwards. Work ONLY in your worktree. Do not push. Commit on your worktree's branch.

## Read first (do not assume from memory)
- `CLAUDE.md` (project rules: Persian for the owner, English terminal output, no secrets printed, companies are data — never a fixed
  number of companies, upgrade-not-rebuild, rules first / AI last).
- `contracts/HQ_CORE_API_v1.md` **§29 (v1.11) is binding** — the shapes, routes, field names and enums there are what the Android and web
  apps are being built against in parallel. If you truly must deviate, edit §29 in your worktree in the same commit and say so in your report.
  Also read §28.7 (what prompt 20.1 already built: spend by domain `domain/spend.py`, per-company cap, catalogue rules).
- `docs/MANAGEMENT_REVIEW_2026-11.md` (the content working group, the protocols to pause, the routing table).
- `docs/PLAN_2026-11-02_OWNER_FOCUS.md` (the owner's asks; findings of prompt 20).
- `apps/api/src/hq_api/domain/humanize.py` (already built: `humanize`, `check`, `plain`, `is_persian_answer`) — every owner-facing text
  you write must pass `humanize.check(...) == []` (write clean Persian at the source; humanize is a safety net).

## Code conventions (match the codebase)
- Python 3.12, FastAPI, SQL via `hq_api.db.Tx` (`tx.all/one/first/scalar/exec` with `:named` params), migrations are raw SQL strings in
  `apps/api/migrations/versions/` executed by `execute_script`. RLS: every new table gets `company_id`, ENABLE+FORCE RLS and the same
  policies/grants as recent migrations (copy the pattern from `0034_cleanup_catalogue_watch.py`); `tests/test_rls_all_tables.py` checks it.
- Read neighbouring modules before writing; reuse helpers (notify.raise_notification, W.create, events.emit, audit.record, gate.automation_lock,
  owner_tz, Principal SERVICE patterns, `allow(ctx, op, input)` + OPA policies in `infra/opa/policy/*.rego` for internal agent ops and the
  OP_CLASS map in `apps/api/src/hq_api/routes/internal.py`).
- Agent tools: an api internal route under `/internal/v1/...`, a gateway handler in `services/gateway/src/hq_gateway/` (see `watch.py` as a small
  example, registered into `T.TOOLS`), a line in `agents/tools.md`, the tool in the charters that use it, the OPA rule. Owner routes need
  `owner_ctx`; step-up (🔏) uses the existing stepup helpers (grep `stepup.` in routes).
- Settings go in `apps/api/src/hq_api/config.py` (env with defaults) and, if the worker/api need them in production, in
  `infra/compose/compose.yaml` under both `api` and `worker` env blocks.
- Worker schedules: `apps/api/src/hq_api/worker/schedules.py` (+ workflows/activities). Keep new periodic work rule-based (no model).
- Charter edits: bump `version:` in the frontmatter of every charter you change.
- **Commit messages:** English, descriptive, small logical commits; end every message with exactly these two lines:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01FSatGsTQQo1oNbkoq916K2`. Never write a model id anywhere else (code, docs).
- **Do NOT commit `apps/api/openapi/hq-api.v1.json`** (the coordinator regenerates it once after merging; leave it unchanged).
- Your migration file already exists as a no-op slot: fill ONLY your own slot (do not renumber, do not create other migration files).

## Tests (real Postgres, NATS, Temporal, OPA in Docker; already prepared)
- Docker daemon is running; the test image `coinepro-hq/api-test:local` exists. Make your own copy of the test-env script pointing at
  YOUR worktree, with a unique env name:
  ```
  S=/tmp/claude-0/-home-user-CoinePro-Hub/42c1fc53-2607-5317-8d32-7b7a79da9e4d/scratchpad
  sed "s#/home/user/CoinePro-Hub#$PWD#g" $S/test-env.sh > $S/test-env-<you>.sh && chmod +x $S/test-env-<you>.sh
  HQ_TEST_TARGET=api HQ_TEST_IMAGE_TAG=local HQ_TEST_NAME=<you> $S/test-env-<you>.sh run sh -c "cd /api && pytest -rA tests/test_x.py 2>&1 | tail -40"
  ```
  (pytest's addopts already has `-q`; do not add another `-q` or the summary disappears — use `-rA` and grep PASSED/FAILED.)
  When done: `HQ_TEST_TARGET=api HQ_TEST_NAME=<you> $S/test-env-<you>.sh down`.
- Services tests (gateway): image `coinepro-hq/services-test:local`; same script without HQ_TEST_TARGET:
  `HQ_TEST_IMAGE_TAG=local HQ_TEST_NAME=<you>s $S/test-env-<you>.sh run sh -c 'pytest -p no:cacheprovider gateway/tests 2>&1 | tail -5'`.
- Lint/types exactly like CI: `/tmp/claude-0/venv-api/bin/ruff check` and `ruff format` (that venv's ruff is the CI version) on apps/api and
  services; mypy: `cd apps/api && MYPYPATH=$PWD/../../services/hq-common/src PYTHONPATH=$PWD/../../services/hq-common/src:src /tmp/claude-0/venv-api/bin/mypy src`.
- Write tests for everything you build (new files named `tests/test_p21_<topic>.py`), and run the existing test files of every module you
  changed. Do not run the whole suite (it takes ~1h); the coordinator does.
- The sandbox has 4 CPUs and two other builders test at the same time: keep test runs targeted.

## Report back (final message, English, ≤ 40 lines)
What you built (files), the contract sections covered and any deviation, tests run and their result, what is NOT done and why,
anything the coordinator must do at merge (settings, compose, conflicts you expect), and what the deploy prompt must say
(migration steps, data moves, things to switch on).
