# Common brief for the two app builders of version 0.11.0 (read fully)

You build the owner's app screens for prompt 21 in your own git worktree (your cwd). The coordinator merges your branch.
The hub's API for these screens is being built in parallel; **contract §29 (v1.11) in `contracts/HQ_CORE_API_v1.md` is the source of truth**
for every route, field and enum. Read §29 completely, plus §28.7, §27, §17.4, §6 and §5 where you touch them.

## Read first
- `CLAUDE.md`, especially «اپ‌ها (اندروید و وب، کار Claude سشن مشورت)»: tests only for the changed parts; servers are called by their
  company's name («تریدیار · نام سرور»), hostname/IP only as small details on the server page.
- `docs/PLAN_2026-11-02_OWNER_FOCUS.md` (the owner's complaint: the app became server issues; he wants business: SEO, products, progress,
  revenue), `docs/MANAGEMENT_REVIEW_2026-11.md` (the content working group), `docs/server-prompts/BUILDER_W1_OWNER_FOCUS.md` stage E.
- `design/` (approved design system D1/D2) and the app's existing components: **reuse the existing components and patterns; build nothing
  from scratch that exists**. Persian text justified; every Latin run isolated (bidi); market figures and all numbers in Latin digits
  (as the app already does — find its helpers).
- `apps/CHANGELOG.md` (last ten entries) to see how recent features were done.

## The screens of 0.11.0 (both apps, equal)
1. **New home** (`GET /home`, §29.13): three cards on top — «پیشنهاد مؤثر», «پیشنهاد خوب» (each with «اجرا کن / بعداً / نه»; «نه» asks a
   short reason), «پیشرفت واقعی» (before → after with the source) — then the 5-line morning summary, each working group's KPI chart per
   company, «فرمان‌های من» with their state, and only `critical` items. **No technical card or server item on the home** any more.
2. **Order report** (`GET /orders/{ref}/report`, §29.2): state, the receipt/plan, steps in plain Persian, blockers each with its one-tap fix
   (`POST /orders/{ref}/fix`), outputs, the end summary (چه شد / چه ماند / از شما چه لازم است). Live via stream `order.report`.
3. **Secretary preview** (`POST /orders/preview`, §29.4): after the owner finishes speaking or typing an order, one line
   («→ تریدیار/رسانه + IG-Hub/انتشار؛ خروجی: ۳ ریلز؛ بودجه: …») with edit (company, department, collaborators, output, mode, player) and
   «بفرست» → `POST /orders {…, route}`.
4. **Long voice** (§29.5): continuous recognition that restarts at pauses (Android SpeechRecognizer / web Web Speech API) and the full text
   editable before sending; over one minute (or when the recogniser fails) record audio and send it in chunks through
   `/transcribe/sessions…` (≤ 90 s chunks, up to 20 minutes), show progress, then the editable text.
5. **The owner's rule** (§29.3): «قانون تازه برای هلدینگ» inside the golden voice-order button area (text or voice) → `POST /rules` →
   one-tap seal; the rules list with edit and retire (`GET /rules`, `PUT /rules/{ref}`, `POST /rules/{ref}/retire`).
6. **Council v2** (§29.8): the plan in 5–10 lines with «اجرا کن», roles of each player, the fact pack, each member's answer behind «جزئیات».
7. **Readiness** (§29.9) per company per group: each check, green or not, with its fix button.
8. **Working groups** (§29.11): list; a group's page: purpose, member companies (pause/resume), seats and who fills them, routines and
   their run history, KPI charts, the weekly experiment.
9. **Connections** (§29.12) per company: each kind with its state, last read, daily figures; «وصل کن» opens the one-page guide
   (`GET /connections/guides/{kind}`) and the write-only secret field (🔏, never shows a secret back) and config.
10. **Employee states** (§29.14): idle/thinking/working/waiting/stuck/done on every employee chip and list, with the stuck reason and its fix.
- **Where the technical goes:** server, network, watch, error reader, technical findings live only under «شرکت ← فنی»
  (`?scope=all&domain=tech|infra|security&company=X`); remove them from the home and the regular notification list (the hub already
  filters `owner_visible`; the app must not re-add technical feeds on the home).
- Every owner-facing string is plain Persian (§29.7): no ids, refs, English tech terms or service names in the UI copy you write.

## Tests and demo data
- Add demo/mock data for every new route (deterministic: fixed dates, fixed values, animations stopped in screenshot/e2e runs — lesson of
  the last CI), following how the app's existing mocks/demo holding are done.
- Unit tests and screenshot (Android) / e2e (web) tests **only for the screens you changed**, per CLAUDE.md. Before you push, open the
  screenshots of the changed screens yourself and look at them (the Read tool shows images).
- Do NOT change `apps/VERSION`, `apps/CHANGELOG.md`, or the web `package.json` "version" (the coordinator bumps to 0.11.0 at merge).
- Do NOT touch `apps/api`, `services`, `infra` or the other app.

## Git
- Commit on your worktree's branch; English, descriptive, small logical commits; end every message with exactly:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01FSatGsTQQo1oNbkoq916K2`.
  Never write a model id anywhere else.
- You may push your branch to `origin` to run CI (`.github/workflows/clients.yml` runs on push for `apps/web/**` / `apps/android/**`), named
  as your brief says. Never push to any other branch, never force-push. Read CI results with the GitHub MCP tools
  (`mcp__github__actions_list`, `mcp__github__get_job_logs`, owner `behnamjalalico`, repo `coinepro-hub`; load them with ToolSearch).
  If CI is red, fix that and push again.

## Report back (final message, English, ≤ 40 lines)
Screens built (files), routes used and any mismatch with §29 you noticed, tests and CI results (run ids), screenshots you inspected, what
is not done and why, what the coordinator must do at merge.
