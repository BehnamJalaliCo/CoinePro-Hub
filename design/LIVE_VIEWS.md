# LIVE_VIEWS — نماهای زنده‌ی CoinePro HQ (مطالعه‌ی طراحی، منتظر تأیید مالک)

> **وضعیت:** ❓ پیشنهاد برای تأیید مالک (۲۰۲۶-۱۱-۰۸). کد اپ‌ها و هاب عوض نشده؛ این فقط طراحی است.
> **نمونه‌ی زنده (باز کن و ببین):** `design/canvas/D4-Live.dc.html` — شب و روز، با حرکت کم هم.
> **درخواست مالک:** «بهترین و حرفه‌ای‌ترین و تخصصی‌ترین انیمیشن‌ها و استریم‌ها … نقشه نشون بده کدوم شرکت به کدوم وصل شد، قطع شد … ۱۰۰ مدل باشه، همه جای اپ … نه نصفه نیمه».

## خلاصه برای مالک (۱۲ نمای ضروری برای اعتماد، و آنچه هاب باید اضافه کند)

۱. **چراغ «زنده»** — بالای هر صفحه میگوید داده الان زنده است یا قدیمی؛ بدون آن هیچ حرکتی قابل اعتماد نیست. هاب: چیزی لازم نیست.
۲. **نقشه‌ی شبکه‌ی هلدینگ** — هاب در مرکز، هر شرکت و سرورهایش دورش (از داده، بی‌سقف)، هر اتصال روشن یا خاموش. هاب: «از کی» و «چرا» روی وضعیت سرور.
۳. **جریان روی نقشه** — فرمان تو ذره‌ی طلایی از هاب به شرکت؛ کار میان دو شرکت ذره‌ی نقره‌ای از راه هاب؛ با رسیدن فرمانت هاب یک بار میتپد. هاب: رویداد تازه‌ی `holding.flow`.
۴. **قطع شدن، قرمز با ساعت و دلیل** — خط میشکند، ساعت قطع و دلیلش به فارسی ساده؛ لمس = جزئیات و راه حل. هاب: رویداد تازه‌ی `network.link`.
۵. **کار زنده‌ی سشن** — مثل Claude Code خط‌به‌خط: چه کسی الان چه میکند؛ قدم تمام‌شده تیک میخورد. هاب: `session.activity` (در قرارداد §۴۱ هست، هنوز ساخته نشده).
۶. **نشان سشن و نگهبان توقف** — در جریان / نوبت تو / گیر کرده / آماده، با زمان آخرین قدم؛ توقف بی‌صدا دیده میشود. هاب: یک اصلاح یک‌خطی؛ امروز `session.updated` اصلاً به اپ نمیرسد.
۷. **نبض دفتر** — چند نفر الان کار میکنند، چند سشن در جریان است، چند کار منتظر توست، توکن در دقیقه. هاب: مسیر تازه‌ی `GET /live/summary`.
۸. **کنتور توکن** — خرج امروز با خط‌های ۷۰، ۹۰ و ۱۰۰ درصد و چهار نوع توکن؛ با هر مصرف واقعی جلو میرود. هاب: رویداد تازه‌ی `llm.tick` هر ۵ ثانیه.
۹. **کارت زنده‌ی شرکت** — سرورهای روشن، آدم‌های در کار، سشن‌های باز، خرج امروز، آخرین رویداد. هاب: اجازه‌ی همین رویدادها در نمای کل هلدینگ.
۱۰. **چراغ حال هر کارمند** — فکر میکند، کار میکند، منتظر است، گیر کرده (با دلیل)، تمام کرد؛ با شکل، نه فقط رنگ. هاب: رویداد تازه‌ی `employee.state`.
۱۱. **رسیدن کار فوری و تصمیم** — 🔴 با بنر و یک زنگ بم، 🟡 کارت تصمیم با خط طلایی؛ بقیه بی‌صدا. هاب: چیزی لازم نیست.
۱۲. **نوار کلید توقف** — وقتی هلدینگ یا یک شرکت قفل است، نوار قرمز روی همه‌ی صفحه‌ها و نقشه. هاب: چیزی لازم نیست.

---

## 1. How to read this catalogue

- **100 views**, grouped by screen. IDs are stable (`HM-2`), so a prompt or a review can name one.
- **Priority:** `P0` = without it the owner cannot trust what the app shows (12, listed above). `P1` = clearly useful, build after P0 (43). `P2` = good, only when cheap or asked (45).
- **Effort** per surface, assuming the foundation (K-1, K-2, K-3 below) exists: `—` nothing, `S` ≤ half a day, `M` 1–2 days, `L` 3–5 days. Order: **hub · Android (Compose) · web (Next.js)**.
- **Data:** `existing` = emitted today and routed to `/stream`; `contract-only` = written in the contract, not yet emitted; `NEW` = proposed here (§3); `fix` = a defect found while writing this (§3.1).
- **Motion** names refer to the grammar in §2 (`M1`…`M13`). Every view states what moves, when, for how long, and what happens with reduced motion.
- Language of the UI: Persian, RTL, Persian digits in prose counts, Latin tabular digits for market and token figures (D0 §5). Servers are called by their company's name («پرو-چارت · رسانه» when a company has several); hostnames and addresses never appear on the map.

## 2. The motion grammar (one language for 100 views)

D0 already rules the spirit: *calm; nothing jumps or shakes, things settle; every animation is a real change of state; reduced motion is honoured.* The grammar below makes that executable. Each primitive is built **once** per platform (K-1) and every view composes them.

| Key | Name | What moves | Duration · easing | Allowed only when |
|---|---|---|---|---|
| M1 | Settle «نشستن» | opacity 0→1, 6 px → 0 | 320 ms standard (200 ms for list rows) | a new thing arrives |
| M2 | Crossfade «تغییر حال» | colour, label, figure | 200 ms standard | a state or a figure changes (figures never count up) |
| M3 | Ripple «موج» | one ring 1→1.5×, opacity .55→0 | 600 ms standard, **once** | a node changed state |
| M4 | Particle «ذره» | a 4 px dot (+2 trail dots) along an edge | 900 ms standard (proposed token `travel`) | one event crossed one edge |
| M5 | Work band «نوار کار در جریان» | 4 px band moving | 1.6 s linear loop | **only while** a run is queued or running (D0 §4) |
| M6 | Breath «دم» | dot opacity .55↔1 | 1.6 s loop | **only while** a model call is in flight, or the advisor listens |
| M7 | Arc «چرخه» | 12 px arc turning | 1 s per turn | **only while** a step or a job runs |
| M8 | Draw «ترسیم» | stroke draws in | 320 ms; 480 ms for a new node or edge (ceremony) | a tick, a new edge, a new hop |
| M9 | Break «گسست» | an edge splits, a 6–8 px gap opens | 320 ms once; reversed on reconnect | a link drops |
| M10 | Ceremony «آیین» | the holding seal's lapis gem brightens, one gold ring expands | 480 ms ceremony easing | **owner acts only**: an order arrives, a seal |
| M11 | Reorder «جابه‌جایی» | FLIP of positions | 320 ms standard | a list's order changes |
| M12 | Fill «پر شدن» | bar or arc length | 600 ms standard | a meter's real value changes |
| M13 | Glint «برق تحریر» | the tahrir under a figure .3→1→.3 | 600 ms once | a headline figure changed (gold = concerns the owner, silver = agents' work) |

**Colour of motion.** Gold = from or for the owner (an order, a seal, «منتظر تو»). Silver = agents and the system at work. Lapis = data and machines (a read across companies, a job on a server). Positive / negative / warning are **states only**, never traffic.

**Rules (all views):**
1. Every motion maps to exactly one event (or to the real clock for a countdown). Nothing moves at rest. No ambient particle fields, no rotating globes, no fake «thinking» waves.
2. Loops (M5, M6, M7) live only as long as the process they show, and stop the moment it ends.
3. One ceremony at a time; ceremonies are gold and belong to the owner.
4. At most 3 particles in flight per edge; more fold into a «×n» chip on the edge. At most 24 animating elements per screen; at most one loop per card.
5. Figures change by crossfade; never a count-up from a made-up value (D0 §5). Missing data is «—», never zero.
6. Sound only for 🔴 (one low bell) and the seal (paper); never for traffic.
7. **Hidden, then back:** when the app or tab is hidden every loop stops and particles are not drawn. On return the state is applied at once; if more than 20 events arrived, a chip says «۲۰ رویداد در نبودت» instead of replaying them.
8. **Reduced motion** (Android *Remove animations* / animator scale 0, already read by `designsystem/Motion.kt`; web `prefers-reduced-motion`, already in `globals.css`): every primitive becomes an instant state change; a particle becomes a 1.5 s tint on its edge plus the «×n» chip; loops become a static glyph and a word («در حال انجام»).
9. **Accessibility:** state is always shape + word, never colour alone. P0 events are announced (TalkBack live region / `aria-live="polite"`; 🔴 assertive). Every map has a table view (HM-8).
10. **Battery and frames:** one particle layer per screen (web: one SVG group or `<canvas>` driven by one `requestAnimationFrame`; Android: one `Canvas` driven by `withFrameNanos`), running only while a particle exists; ≤ 4 ms per frame on a mid-range phone.

Proposed token additions (need the owner's approval, `tokens/README.md` rule 3): `motion.duration.travel 900ms`, `motion.duration.ripple 600ms` (also used by M12, M13), `motion.duration.loop 1600ms`.

### 2.1 Foundation (built once, not counted among the 100)

| ID | What | hub · Android · web |
|---|---|---|
| K-1 | **Motion kit:** M1–M13 as Compose modifiers/composables and as web components/CSS, with the reduced-motion switch and the particle layer. Android has `Motion.kt`, web has `hq-flow`, `hq-ring`, `hq-breath`… keyframes: extend, do not fork. | — · M · M |
| K-2 | **Live store:** seed from `GET /live/summary` (it returns the stream sequence `seq`), then apply events after `seq` (`Last-Event-ID`), de-duplicated by event id; one reducer per view; a burst limiter (rule 4). Web `lib/stream.ts` and Android `HoldingStream` already read the stream with resume: they gain the reducer and the seed. | — · M · M |
| K-3 | **Hub live plumbing:** fixes F1 and F2, `GET /live/summary`, the topic prefixes of §3.3, tests. | M · — · — |

## 3. The hub's live data: what exists, what is broken, what is new

The hub already streams a lot (`apps/api/src/hq_api/events.py`, 50 topics, envelope `{id, type, at, company, ref, data}`, JetStream `HQ_CORE`, 30 days). Useful today: `server.state`, `server.call`, `server.awaiting_seal` (servers) · `links.updated` (holding) · `work.created|delegated|updated|completed` with `root_ref` · `run.started|step|finished` · `activity.changed` · `llm.call.started|finished` with tokens by type, model and cost (bridged from llm-router) · `budget.alert` · `decision.created|decided|reminded` · `deliverable.created` · `notification.created` · `control.changed` · `presence.changed` · `order.report` · `group.run` · `connection.updated` · `line.updated`, `line_run.updated` · `automation.run` · `substitute.updated` · `talk.turn`, `talk.card`, `voice.engine`, `voice.meter` · `hub.job` · `backup.done|failed` · `oversight.*` · `founding.updated`, `provision.step`.

### 3.1 Two defects found while writing this (both block P0)

- **F1 — `session.updated` never reaches the apps.** The contract (§35.7) puts it on topic `orders`, and both apps listen for it (`apps/web/src/lib/stream.ts`, Android `OrderSession.kt`), but `TOPICS["orders"]` is `("order.",)` and `routes/stream.py` filters by prefix, so `session.*` matches no topic and is dropped. Checked: `session.updated` → no topic. Fix: `"orders": ("order.", "session.")`. The same applies to the coming `session.activity` (§41.1).
- **F2 — the holding view strips what the map needs.** `company=*` (the holding summary that scales to any number of companies) passes only `activity.changed` in full and reduces everything else to `{id, type, at, company}`. Fix: also pass in full the small, text-free events the P0 views need — `server.state`, `network.link`, `holding.flow`, `employee.state`, `llm.tick`, `session.updated`, `control.changed`, `links.updated`.

### 3.2 New events and routes

All follow §7: metadata only, plain Persian labels at most, never a message body, prompt, tool payload, secret, hostname or address. Emitted inside the writer's transaction through the outbox (`events.emit`), like every event today.

**P0**

| Name | Topic | `data` | Emitted when | Used by |
|---|---|---|---|---|
| `session.activity` *(contract-only, §41.1)* | `orders` (after F1) | `{order, working: n, line: {id, at, who_fa, company, text_fa, kind: "start"\|"step"\|"end"\|"wake"\|"ask"\|"join"\|"task"\|"memory", state: "running"\|"done"\|"failed", task_n\|null}}` — additive to §41.1: `line.id` (run id + step n, so the end of a step updates its line), `kind`, `state`, `task_n` | each run start, step and end of a work of the order's tree; the holder woken by the sweep (`wake`); someone joins (`join`); a plan task ticked (`task`) | SE-1, SS-1, SS-3, SS-4, SE-2, OF-1 |
| `holding.flow` | `holding` (add prefix `holding.`) | `{from, to, kind: "order"\|"request"\|"accept"\|"deliver"\|"read"\|"playbook"\|"publish", via: "hub", ref, root_ref\|null, label_fa\|null (≤ 60, plain)}`; `from`/`to` = `"hub"`, a company code, or `"outside"` | an owner order is routed (`hub` → holder company); a cross-company work request is created / accepted / delivered back (A → hub → B); an agent reads another company's data (files, knowledge, a connection) for a work; a playbook is applied to another company; a line publishes | HM-2, OF-4, WG-3, HM-11 |
| `network.link` | `servers` (add prefix `network.`) | `{from: server, to: "hub"\|server, port\|null, ok, ms\|null, error\|null, error_fa\|null, since, last_ok_at\|null}` | a measured link (`netcheck`, §26.6) changes `ok`, or crosses the slow threshold; at most once per link per minute; every result during an owner's check | HM-1, HM-3, HM-6 |
| `employee.state` | `activity` (prefix `employee.` already routed) | `{employee, company, department, state: "idle"\|"thinking"\|"working"\|"waiting"\|"stuck"\|"done", since, work_ref\|null, root_ref\|null, stuck_fa\|null}` | the §29.14 state changes; coalesced to at most one per employee per 2 s (`stuck` and `done` at once) | PE-1, OF-1, CO-1, CO-2, SE-1 |
| `llm.tick` | `llm` (routes as is) | `{company, window_s: 5, calls, in_flight, tokens: {input, output, cache_read, cache_write, thinking}, equiv_usd, day: {tokens, equiv_usd, budget_usd\|null, pct\|null}}` | every 5 s for each company that had a call in the window (nothing when idle); built in the worker bridge that already consumes the router's call events | MO-1, MO-2, OF-1, CO-1, MO-5 |
| `server.state` *(additive)* | `servers` | adds `{prev_state, since, reason: "no_poll"\|"runner_stopped"\|"server_unreachable"\|"revoked"\|"fallback_public"\|"slow"\|null, reason_fa, hub_rtt_ms, open_jobs}` | as today, plus when `via` changes and when the RTT tier changes. `reason` is inferred: the runner is silent but other servers still reach the server's ports → `runner_stopped`; nobody reaches it → `server_unreachable`; otherwise `no_poll` | HM-1, HM-3, HM-5, SV-1 |
| `GET /live/summary` *(route)* | — | `{seq, at, people: {working, thinking, waiting, stuck, total}, sessions: {moving, your_turn, stuck, ready}, approvals, urgent_unread, servers: {online, offline, total}, tokens: {today, per_min, equiv_usd_today, budget_usd\|null}, control: {holding, companies_locked: [code]}, companies: [{code, working, total, sessions_open, servers_online, servers_total, spend_today_usd, last_event_at}]}` — `seq` is the stream's last sequence when read, so the client resumes exactly after it | owner, any time | K-2, every P0 |

**P1:** `substitute.call {player, seat, via, caller: {kind: "session"|"line"|"work"|"council", ref}, state: "started"|"done"|"failed", ms|null, reason_fa|null}` (topic `treasury`, routes as is) · `hub.stats {memory: {total_mb, budget_mb, free_mb}, services: [{key, state, mem_used_mb}], at}` (topic `hub`, at most once a minute, only on change) · talk live deltas on the in-memory LiveHub like §16.3 (`GET /talk/conversations/{ref}/live`: `reply.started|delta|done|failed`; never on NATS, never stored) · additive `run.step.summary_fa`, `talk.turn.state: "started"`, `llm.call.*.root_ref` (bridge allow-list) · `GET /infra/network/history?link&from&to`.

**P2:** `server.vitals {server, load1, mem_used_mb, disk_used_pct}` (from the runner's poll, ≤ 1/min) · `n8n.execution {workflow, state, ms}` · `notification.read {ids}` · `GET /live/replay?from&to&topics` (a bounded page of envelopes from JetStream) · additive `automation.run.cause_event_id`, `line_run.updated.progress`.

### 3.3 Topic table changes (one place: `events.TOPICS`)

`orders`: `("order.", "session.")` (F1) · `holding`: `("links.", "holding.")` · `servers`: `("server.", "network.")`. `employee.state`, `llm.tick`, `substitute.call` and `hub.stats` route under existing prefixes. The Android `StreamTopics` and web `stream.ts` need no new topic names; `stream.ts` adds `holding.`, `network.` and `employee.` to its invalidation map.

---

## 4. The catalogue

### A. Everywhere (shell) — GL

**GL-1 · چراغ «زنده» · Live heartbeat** — `P0` · — · S · S
- *Shows / why:* one small indicator in the header and in the corner of every live panel: «زنده» / «در حال وصل» / «قدیمی · ۲ دقیقه» / «بی‌اتصال». Every other live view is only as true as this; when the stream is down the owner must see that figures are frozen, not believe in a calm holding.
- *Motion:* a byte from the hub (an event or the 15 s heartbeat comment) gives the dot one breath (600 ms), at most one every 2 s; reconnecting = a thin arc turning while retrying (M7); stale after 45 s of silence = amber, still. Reduced: no breath; the word carries it.
- *Data:* client only — the hub's heartbeat comment every 15 s and `Last-Event-ID` resume; web `stream.ts` (`SILENCE_MS` 45 s) and Android `HoldingStream` already measure silence.

**GL-2 · نوار کلید توقف · Kill-switch band** — `P0` · — · S · S
- *Shows / why:* a 4 px negative band across the top of every screen: «هلدینگ قفل است · از ۱۴:۰۲ · به دستور تو»; a locked company is hatched at 45° on the map and on its card. When a lock is on, the stillness everywhere has a reason the owner can see.
- *Motion:* the band settles from the top edge (M1, 320 ms) on engage and retracts on release; the hatch fades in (M2). Reduced: instant.
- *Data:* existing `control.changed`, `GET /control/state`.

**GL-3 · برچسب «قدیمی» · Stale figures** — `P1` · — · S · S
- Any figure older than its freshness budget (live counters 60 s, treasury 5 min, daily KPIs 26 h) turns muted with «قدیمی» and its age (D0 principle 3). M2 once. Data: each event's and snapshot's `at`.

**GL-4 · «چرا حرکت کرد؟» · Why did this move** — `P1` · — · M · M
- Long-press (Android) or hover (web) on anything that just moved — a particle, a glinting figure, a dot — shows the event behind it in words: what, when, who, and a link to the object. Every animation is accountable to one event id. No motion. Data: the client keeps the last 200 envelopes.

**GL-5 · خلوت · Khalvat dim and return** — `P2` · — · S · S
- Entering khalvat dims the app one step (M10, 480 ms); traffic on the map stops (state changes stay). Back: «در نبودت چه گذشت» counts settle in. Data: existing `presence.changed`, `GET /owner/away-summary`.

**GL-6 · بازپخش یک ساعت · Replay** — `P2` · M · L · M
- The D2-approved replay bar under the map: scrub the last hour at 4×; flows and breaks replay. Data: NEW `GET /live/replay`.

### B. The office (home) — OF

**OF-1 · نبض دفتر · Office pulse** — `P0` · S · S · S
- *Shows / why:* four figures on top of the office: «الان کار میکنند» (people working, of all), «سشن در جریان», «منتظر تو» (approvals + sessions on your turn), «توکن در دقیقه». The answer to the owner's first question on opening the app: is my holding working, and is anything waiting for me?
- *Motion:* a figure changes by crossfade (M2) and its tahrir glints once (M13): gold when it concerns the owner, silver for agents' work. Reduced: crossfade only.
- *Data:* NEW `GET /live/summary` (seed), then NEW `employee.state`, `session.updated` (after F1), existing `decision.created|decided`, NEW `llm.tick`.

**OF-2 · سشن‌ها جابه‌جا میشوند · Session cards reorder** — `P1` · S (F1) · S · S
- A card whose badge changes moves to its group (نوبت تو → آماده → گیر کرده → در جریان) with M11; the badge crossfades. Data: `session.updated` (F1).

**OF-3 · سینی مُهر · Approvals tray** — `P1` · — · S · S
- A new approval enters from the start edge (right, RTL) with M1 and one gold hairline; one decided on another device folds out with «مُهر شد · وب». Data: existing `decision.created|decided`.

**OF-4 · بوم دفتر زنده · The office canvas, live** — `P1` · — · M · M
- The office's canvas (§35.6) becomes the holding map in miniature: same nodes and edges, flows only, no labels; tap → HM. Data: as HM-1, HM-2.

**OF-5 · خط پول · Money line** — `P2` · — · S · S — revenue against spend this month settles on `payment.read` and NEW `llm.tick`.

**OF-6 · پیشنهاد تازه · A suggestion arrives** — `P2` · — · S · S — M1 into the cards; existing `suggestion.updated`, `home.updated`.

**OF-7 · گزارش صبح آماده · Morning brief ready** — `P2` · — · S · S — a gold dot on the brief; the spoken brief's waveform moves only while it plays. Existing `briefing.ready`.

### C. The holding network map (centrepiece) — HM

The full specification is in §5; the entries here are the views it is made of.

**HM-1 · نقشه‌ی زنده‌ی شبکه · Live topology and runner state** — `P0` · S · L · L
- *Shows / why:* the holding seal at the centre (the hub); every company, from data, on the inner ring; each company's servers as satellites on the outer ring; three kinds of edge: the **work spoke** hub↔company, the **runner link** hub↔server (solid = private network, dashed = public fallback), and the owner's **company links** as chords (serves / publishes / feeds / sells / supports). Each server is online / offline / pending / revoked by shape and colour. The owner asked for exactly this — «کدوم شرکت به کدوم وصل شد، قطع شد» — and it is the one place where the architecture is visible: servers never talk to each other; the hub carries everything.
- *Motion:* on first load nodes settle (M1, staggered, ≤ 600 ms in all); a state change crossfades the node's ring (M2) and gives one ripple (M3). Nothing moves at rest. Reduced: static, state by shape.
- *Data:* existing `GET /infra/network`, `GET /links` (Canvas), `server.state`, `links.updated`; F2; additive `server.state` fields.

**HM-2 · جریان روی خط‌ها و تپش هاب · Traffic along edges, hub pulse** — `P0` · M · M · M
- *Shows / why:* what is crossing right now. Gold = the owner's order (hub → holder company); silver = agents' work (requests, deliveries); lapis = a read of data or a job on a server. A cross-company request travels **A → hub → B**, because that is the truth; the A–B chord glows while it travels if an `on` link exists. When an owner order arrives, the seal pulses once (M10) before the particle leaves. Makes the invisible visible: the owner sees his order leave and the answer come back, and sees companies working together.
- *Motion:* M4 (900 ms); ≤ 3 in flight per edge, the rest fold into «×n»; the hub pulse only for owner acts. Reduced: the edge tints 1.5 s and the chip counts.
- *Data:* NEW `holding.flow`; existing `server.call` for jobs (out and back). Replaces today's guess in `components/live/orbit.tsx`, which infers the direction from `work.*` type names.

**HM-3 · قطع شد: قرمز، از کی، چرا · Disconnection** — `P0` · M · M · M
- *Shows / why:* a link that drops turns red and visibly breaks; the server gets a red ring and an ×; a chip stays: «قطع · ۱۴:۰۲ · runner روی سرور ایستاده». Tap → when it dropped, the last good contact, how long (real time, live), why in plain words, what is blocked (jobs queued on it, sessions waiting for it), and what fixes it. Reconnection closes the gap and shows positive for 2 s. The owner never has to ask «چرا کار نمیکند؟».
- *Motion:* M9 once; red is a state, not a blink. Reduced: instant.
- *Data:* additive `server.state` (`since`, `reason`, `reason_fa`, `prev_state`); NEW `network.link`; existing `GET /infra/network`.

**HM-4 · برگه‌ی جزئیات گره و خط · Node and edge detail** — `P1` · S · M · M
- Tap a company: people working, open sessions, its servers and their RTT, the last 10 flows. Tap an edge: kind, `purpose_fa`, open works, last flows, a 24 h latency sparkline. Data: existing `GET /links`, `GET /infra/network`; NEW `GET /infra/network/history`.

**HM-5 · راه خصوصی یا عمومی · Route indicator** — `P1` · S · S · S
- A runner that falls back to the public address gets a dashed link and a small globe; back to private → solid (M2). Data: `server.state.via`, emitted on change.

**HM-6 · بررسی شبکه · Network check sweep** — `P1` · S · S · S
- The owner taps «بررسی شبکه»: a lapis sweep runs along each link under test and each result lands as a tick or a cross as it arrives (Android `servers/Network.kt` polls today). Data: existing `POST /infra/network/check`; NEW `network.link` per result.

**HM-7 · نوار ۶۰ دقیقه · Map timeline** — `P2` · — · M · M
- One tick per flow or break in the last hour under the map (colour = kind); tap a tick → its edge lights. Data: the client's buffer (GL-6 for older).

**HM-8 · نمای جدول · Table view** — `P1` · — · M · S
- The same live data as a table (company, servers online, people working, sessions, flows per hour, last event): unlimited companies, sortable; a changed row tints once. The reduced-motion default. Data: as HM-1.

**HM-9 · رده‌ی تأخیر · Latency tier** — `P2` · S · S · S — runner link weight by RTT tier (normal / slow). Additive `server.state.hub_rtt_ms`.

**HM-10 · پیوند ویرایش شد · A link edited live** — `P2` · — · S · S — a chord draws (M8, 480 ms) or fades to dotted when turned off. Existing `links.updated`.

**HM-11 · انتشار به بیرون · Publishing to the world** — `P2` · S · S · S — a silver particle leaves a company for the map's edge with the platform's glyph when a line publishes. `holding.flow kind publish`.

**HM-12 · شرکت تازه شکل میگیرد · A company forming** — `P2` · — · M · M — a dashed octagon appears on the ring; provisioning steps fill it; at `sealed` it becomes solid with the company's seal (M10) and the ring re-spaces (M11). Existing `founding.updated`, `provision.step`.

### D. A company — CO

**CO-1 · کارت زنده‌ی شرکت · Company card live state** — `P0` · S · M · M
- *Shows / why:* on the companies list and the office: the mark with its activity arc (share of people working, in the company's chart colour, D2), servers online (x/y, a shape per state), people working with one state dot each (≤ 12, then «+n»), open sessions by badge, today's spend against the company's cap, the age of the last event. One card answers «is this company alive, working, healthy, and what does it cost today» without opening it — for any number of companies.
- *Motion:* the arc fills (M12); dots crossfade per person (M2); a figure settles (M2); the only loop is the work band, and only while a run of the company really runs. Reduced: static.
- *Data:* `GET /live/summary.companies[]` (seed), NEW `employee.state`, `server.state`, `session.updated` (F1), NEW `llm.tick`; F2.

**CO-2 · مدار دپارتمان‌ها · Departments orbit** — `P1` · — · L · M
- D2-approved: eight departments around the CEO, managers inner, people outer, live; a delegation inside the company draws a silver particle CEO → manager → person. Data: NEW `employee.state` (department), existing `work.delegated`.

**CO-3 · کارهای در جریان · Work in progress** — `P1` · — · S · S
- Rows with a gold band for the owner's orders and a silver one for self-started work (D2); progress fills on `work.updated`; the band runs only while a run of that work runs. Existing `work.updated`, `run.started|finished`.

**CO-4 · امضای حرکتی شرکت · Company motion signature** — `P2` · S · M · M — D2-approved: TradeYar's candles rise, FX's spark, Pro-Chart's arrow turns once on a delivery (< 600 ms). Existing `deliverable.created`; the signature kind on the company record (data).

**CO-5 · رسیدن پرداخت · A payment arrives** — `P2` · — · S · S — the revenue figure settles with «تازه». Existing `payment.read`, `revenue.day`.

**CO-6 · مرحله‌ی سفر شرکت · Journey stage** — `P2` · — · S · S — the stage pill moves on (M11). Existing `journey.stage`.

**CO-7 · نقطه‌ی تازه‌ی KPI · A KPI's new day** — `P2` · — · S · S — the sparkline draws its new point (M8). Existing daily read, `home.updated`.

### E. Sessions (the list) — SS

**SS-1 · نشان سشن و نگهبان توقف · Session badge and stall watch** — `P0` · S · S · S
- *Shows / why:* on every session row and in the session's header: the badge (در جریان / نوبت تو / آماده / گیر کرده / بسته), the reason line, «آخرین قدم ۷ دقیقه پیش», and a thin ring filling toward the 10-minute idle sweep (§41.3). When the hub wakes the holder, a line says so; after the second window the badge turns «گیر کرده» with the reason in plain words and «ادامه بده» (nudge). This is the owner's complaint of 2026-11-08: work that silently stopped while the app still said «در جریان».
- *Motion:* the work band (M5) only while `moving`; the idle ring advances once a minute (real clock); badge M2; `your_turn` one gold glint (M13). Reduced: the ring is text «۷ از ۱۰ دقیقه».
- *Data:* existing `session.updated` — **after F1**; `session.activity` (`kind: wake`); seed `GET /orders/{ref}/activity` (`idle_since`); existing `POST /orders/{ref}/nudge`.

**SS-2 · گروه‌بندی زنده · Live grouping** — `P1` · S (F1) · S · S — M11 on badge change in the sessions list. `session.updated`.

**SS-3 · آمدن به جلسه · Someone joins** — `P1` · — · S · S — a medal slides into the participants' stack (M1) with «… آمد». `session.activity kind join`, `order.report`.

**SS-4 · شمار کارها · Tasks meter** — `P1` · — · S · S — a segmented bar {done/total}; a segment fills (M12) on a tick. `session.activity kind task`, `order.report`.

### F. A session — SE

**SE-1 · کار زنده‌ی سشن · Session live work panel** — `P0` · M · M · M
- *Shows / why:* the session's work as Claude Code shows its own: a header «۲ نفر الان کار میکنند» with each worker's medal, state dot and what they are doing («ویدیو را رندر میکند»); below, lines in order — who (silver), what in plain words, time. The line in progress carries a turning arc and its elapsed seconds; when the step ends the arc becomes a tick, or a cross with the reason. Auto-scroll only when the owner is at the bottom; else a pill «۳ خط تازه». The owner: «مثل خودت که کلود کدی از کار کردنت آدم میفهمه کار میکنی».
- *Motion:* a new line settles (M1, 200 ms); M7 while a step runs; the tick draws (M8). More than 5 lines a second are appended without motion. Reduced: no arc, «در حال انجام».
- *Data:* `session.activity` (contract-only §41.1, routed after F1) with additive `line.id`, `line.state`, `line.kind`; seed `GET /orders/{ref}/activity`.

**SE-2 · ریل مراحل · Plan rail** — `P1` · — · S · S — the owner's numbered steps as a rail; the current one is gold (it is the owner's plan); a tick draws when `order.progress` ticks it; a task waiting on the owner says «از تو میپرسد». `order.report.tasks`, `session.activity kind task`.

**SE-3 · جواب در حال نوشتن · Reply being written** — `P1` · M · M · M — the holder's turn streams in as it is written, a caret only while writing. NEW talk live deltas (§3.2 P1).

**SE-4 · کسی دارد جواب میدهد · Someone is answering** — `P1` · S · S · S — the answering participant's medal, or the ChatGPT / Gemini / DeepSeek logo, shows three calm dots; with «نظر همه» each lights in turn. Additive `talk.turn.state: started`.

**SE-5 · کارت در حال اجرا · A card running** — `P1` · — · S · S — a hire / line / automation card's border runs (gold for owner-made) while it executes, then settles to «انجام شد» or its exact `reason_fa`. Existing `talk.card`.

**SE-6 · درخت فرمان · The order's tree** — `P1` · — · M · M — root → children → cross-company requests; nodes draw in as works are created; the gold thread from the owner; depth ≤ 2 (D2). Existing `work.created|delegated` with `root_ref`.

**SE-7 · کنتور هزینه‌ی سشن · Session cost meter** — `P1` · S · S · S — tokens and $ of this order, filling per call. Additive `llm.call.finished.root_ref`.

**SE-8 · حافظه به‌روز شد · Memory folded** — `P2` · S · S · S — «تا اینجا» shows «به‌روز شد» with a tahrir draw. `session.activity kind memory`.

**SE-9 · فایل در راه · A file processing** — `P2` · — · S · S — upload bar (client), then processing → ready. Existing `file.ready`.

### G. Cartable — CA

**CA-1 · رقص کارت تصمیم · Decision card choreography** — `P1` · — · S · S — arrives (M1 + one gold hairline); decided elsewhere folds out with where; a deadline ring on the real clock (per minute; per second under 10 minutes). Existing `decision.created|decided|reminded`.

**CA-2 · آیین مُهر · The seal ritual** — `P1` (built on web; port and keep) · — · M · — — press and hold 600 ms, paper sound optional, the Jalali date engraved (D1).

**CA-3 · خروجی با امضای شرکت · An output arrives** — `P2` · — · S · S — enters the outputs box with the company's signature (CO-4). Existing `deliverable.created`.

**CA-4 · مُهر گروهی · Batch seal** — `P2` · — · S · S — the batch seal (§20.10) stamps each card 120 ms apart, then one ceremony.

### H. People and agents — PE

**PE-1 · چراغ حال هر نفر · A person's live state** — `P0` · M · S · S
- *Shows / why:* on every medal everywhere (session workers, company cards, departments, people): **thinking** = a silver dot that breathes (a model call in flight); **working** = a silver ring turning slowly (a tool or a server job runs); **waiting** = a hollow lapis ring; **stuck** = a negative «!» (long-press: the reason and the fix); **done** = a positive tick; **idle** = nothing. A different shape per state, never colour alone. The owner's «ول کردند رفتند» is answered here: the state of each person is the atom every count above is built from.
- *Motion:* M6 and M7 only while the state lasts; M2 between states. Reduced: static glyphs.
- *Data:* NEW `employee.state` (topic `activity` already routes `employee.`); `activity.changed` stays for older clients.

**PE-2 · پشت میز · At the desk** — `P1` · S · M · M — D2-approved agent view: steps in plain words, tools through the Gateway with class A0–A4 and counts, this work's budget. Existing `run.started|step|finished`; additive `run.step.summary_fa`.

**PE-3 · مسیر ارجاع · Delegation path** — `P1` · — · M · M — D2: owner → CEO → manager → person, depth ≤ 2, tokens per hop; a new hop draws (M8); depth 3 shown as forbidden. Existing `work.delegated`, `GET /work/{id}` chain.

**PE-4 · بودجه‌ی این کار · Run budget** — `P1` · — · S · S — «38K / 60K tok» fills per call (M12). Existing `llm.call.finished` (`work_ref`).

**PE-5 · کارمند تازه آمد · A hire arrives** — `P2` · — · S · S — the new medal settles into its department (M10: the owner sealed it). Existing `hiring.changed`, `employee.updated`.

**PE-6 · جابه‌جایی رتبه · Ranking moves** — `P2` · — · S · S — M11. Existing `rankings.updated`.

**PE-7 · ستاره · A star awarded** — `P2` · — · S · S — a star settles on the medal. Existing `stars.rollup`.

### I. Money and tokens — MO

**MO-1 · کنتور توکن · Token meter** — `P0` · M · M · M
- *Shows / why:* today's tokens and equivalent $ against the daily budget: one track with marks at 70, 90 and 100 %, filled in four stacked segments (input, output, cache, thinking — chart slots 1–4 of palette v2, 2 px gaps, a legend with values, because the day palette carries a colour-blind warning) and the burn rate in tokens per minute. The holding's real cost, moving as it is spent: a runaway like the 50 M-token hour of §28.7 is seen while it happens, not the next morning.
- *Motion:* the fill advances per tick (M12); the work band rides the leading edge only while calls are in flight (M5); crossing 70 % turns the mark amber, 90 % the fill amber, 100 % red with a 🔴. Reduced: the fill jumps.
- *Data:* NEW `llm.tick`; existing `budget.alert`; seed `GET /treasury/summary`.

**MO-2 · منحنی روز و مخروط پیش‌بینی · Day curve and forecast** — `P1` · — · M · M — D2-approved cumulative curve with the budget line and the forecast cone; the line extends each minute and the cone narrows. NEW `llm.tick`.

**MO-3 · چراغ سهمیه · Quota light** — `P1` · — · S · S — ok / warning / limited with the real reset time and the paused priorities. Existing `budget.alert {kind: quota}`, `GET /treasury/quota`.

**MO-4 · کنتور صدا · Voice meter** — `P1` · — · S · S — talk voice $ against the owner's cap; amber/red light (§32.6). Existing `voice.meter`.

**MO-5 · خرج شرکت‌ها · Company spend** — `P2` · — · S · S — bars by company, M11 once a minute. NEW `llm.tick`.

**MO-6 · ترکیب مدل‌ها · Model mix** — `P2` · — · S · S — share per model, per minute. Existing `llm.call.finished.model`.

**MO-7 · درآمد زنده · Revenue** — `P2` · — · S · S — Existing `revenue.day`, `payment.read`.

**MO-8 · هدررفت تازه · Waste found** — `P2` · — · S · S — a waste item settles in the treasury (§21.7). Existing routes.

### J. Servers and connections — SV

**SV-1 · ضربان سرور · Server heartbeat row** — `P1` · S · S · S — each server row: state shape, last seen (relative, refreshed every 10 s), private/public, RTT; offline red with since and reason (as HM-3). Additive `server.state`.

**SV-2 · کارهای سرور · Server jobs** — `P1` · — · S · S — a job row appears on `server.call running` with its actor's medal and the masked command (M7), and ends with the exit chip and duration. Existing `server.call`.

**SV-3 · منتظر مُهر · Awaiting seal** — `P1` · — · S · S — a job waiting for the owner's seal shows the gold seal once and its card. Existing `server.awaiting_seal`.

**SV-4 · وصل شدن سرور تازه · A server plugs in** — `P2` · — · S · S — after the pairing approval the node appears and its runner link draws (M8, 480 ms). Existing `server.state` pending → online.

**SV-5 · چراغ اتصال‌های رشد · Growth connections** — `P1` · — · S · S — Search Console, GA4, Instagram, Telegram…: connected / error / missing, last read relative; the daily read ticks each. Existing `connection.updated`.

**SV-6 · ترمینال مالک · The owner's terminal** — `P2` (built) · — · — · — — lines stream; the caret blinks only while the command runs; exit chip.

**SV-7 · علائم حیاتی سرور · Server vitals** — `P2` · M · S · S — load, memory, disk from each poll. NEW `server.vitals`.

### K. Working groups and playbooks — WG

**WG-1 · ساعت روتین‌ها · Routines dial** — `P1` · — · M · M — each group's routines on a 24 h dial (Tehran time); a dot leaves the dial when `group.run` fires and lands on the company's row as done / failed / skipped with its `note_fa`. Existing `group.run`.

**WG-2 · کارگروه مُهر شد · A playbook sealed** — `P2` · — · S · S — the seal ceremony; members appear. Existing `group.playbook`.

**WG-3 · کارگروه به شرکت دیگر رفت · A playbook applied** — `P2` · S · S · S — a gold particle source → hub → target on the map. `holding.flow kind playbook`.

**WG-4 · صندلی پر شد · A seat filled** — `P2` · — · S · S — the medal slides into its seat. Existing `group.playbook`, `employee.updated`.

**WG-5 · نتیجه‌ی آزمایش · An experiment closes** — `P2` · — · S · S — the figure settles with kept / dropped.

### L. Production lines — PL

**PL-1 · ریل قدم‌های اجرا · Line run rail** — `P1` · — · M · M — the steps (متن، تکرار، صدا، الگو، شورا، ساخت، رندر، کاور، کیفیت، انتشار) as a rail in reading order; the current step carries the work band; a seal step shows the gold seal; a failed step is red with `error_fa`. Existing `line_run.updated`.

**PL-2 · پیشرفت رندر · Render progress** — `P2` · S · S · S — a percentage on the render step. Additive `line_run.updated.progress`.

**PL-3 · منتشر شد · Published** — `P1` · — · S · S — the platform glyph gets a tick and the link; HM-11 on the map. Existing `line_run.updated`.

**PL-4 · یادگیری ۲۴ ساعت و ۷ روز · Learning** — `P2` · — · S · S — figures arrive and their points draw. Existing `insights.updated`.

**PL-5 · تا خودکار شدن · Good runs to auto** — `P2` · — · S · S — a ring `good_runs / auto_after`; at the threshold «خودکار کن» (gold) settles in. Existing `line.updated`.

### M. Automations and n8n — AU

**AU-1 · تپش خودکارسازی · Automation run** — `P1` · — · S · S — each automation row shows its last run; a blip with ok / failed on `automation.run`. Existing.

**AU-2 · علت ← اثر · Cause to effect** — `P2` · S · M · M — when an event-triggered automation runs, a thin line ties the triggering event in the feed to the automation. Additive `automation.run.cause_event_id`.

**AU-3 · اجراهای n8n · n8n executions** — `P2` · M · S · S — workflows active / inactive and their executions, live. NEW `n8n.execution`.

**AU-4 · تبلیغ خودش می‌ایستد · Ad budget stops** — `P2` · — · S · S — the spend bar meets its cap and «متوقف شد» drops in. Existing `ad.paused|resumed`.

### N. Outside players: ChatGPT, Gemini, DeepSeek, AI Studio — XP

**XP-1 · چراغ نیمکت · Bench lights** — `P1` · — · S · S — each player with its own logo: signed in / expired / signed out; ready / limited (until the real time) / error; AI Studio's voice engine beside them. When a player signs out the lines that use it fail: the owner sees it first here. Existing `substitute.updated`, `voice.engine`.

**XP-2 · به زمین آمد · Called onto the pitch** — `P1` · S · S · S — a player's logo lights while it answers and a thin silver line ties it to its caller (session, line, council); the answer carries «منبع: ChatGPT». NEW `substitute.call`.

**XP-3 · دور شورا · A council round** — `P1` · — · M · M — each model's seat lights while it answers, its stance settles, then the verdict (§27.2, §29.8). Existing `work.council`.

**XP-4 · زنجیره‌ی صدا · Voice chain fallback** — `P2` · — · S · S — when the AI Studio voice fails or the cap is hit, the light steps to the next engine (amber) with one line. Existing `voice.engine`, `voice.meter`.

**XP-5 · ارزش اشتراک · A subscription's value** — `P2` · — · S · S — this month's `value_ratio` fills. Existing `substitute.updated`.

### O. Hub services and memory — HS

**HS-1 · بودجه‌ی حافظه‌ی هاب · Memory budget gauge** — `P1` · S · M · M — total, budget and free, each service a segment; switching a service shows its job and the segment grows or shrinks when done (M12); a refusal glints the blocking segments amber once. Existing `GET /hub/services`, `hub.job`; NEW `hub.stats`.

**HS-2 · کارهای هاب · Hub operations** — `P1` · — · S · S — `hub.job` queued → running → done / failed, the same look as SV-2. Existing.

**HS-3 · ضربان پشتیبان‌گیری · Backup heartbeat** — `P2` · — · S · S — last backup relative; a tick on `backup.done`, red on `backup.failed`. Existing.

**HS-4 · دیده‌بان · The watch** — `P1` · — · S · S — a protocol run shows progress; a finding settles with its severity; a hold shows the gold seal. Existing `oversight.watch|finding|hold`.

**HS-5 · رشد دانشنامه · Knowledge growth** — `P2` · — · S · S — the count settles; expiring items amber. Existing `knowledge.updated|expiring`.

**HS-6 · زنجیره‌ی دفتر · Audit chain verified** — `P2` · — · S · S — after the nightly check the chain line draws to its anchor once; a break is red. `GET /audit/verify`.

### P. Notifications — NO

**NO-1 · رسیدن کار فوری و تصمیم · What needs you arrives** — `P0` · — · S · S
- *Shows / why:* 🔴 urgent: a banner settles from the top and stays until acknowledged, with the single low bell; 🟡 decision: a toast with a gold hairline and the cartable badge; 🔵 🟢 🟣: silently into the list. In khalvat only 🔴 interrupts. The owner can trust the silence because the bell is rare.
- *Motion:* M1 for the banner; no shake, no repeat; the bell once. Reduced: instant; a haptic on Android.
- *Data:* existing `notification.created`, `decision.created`; push already covers the closed app.

**NO-2 · ستون رویدادها · The event feed** — `P1` · — · S · S — D2: rows settle at the top (M1, 200 ms), bursts grouped («۳ تحویل تازه»), filter chips, each row tied to GL-4. All topics, metadata only.

**NO-3 · خوانده شد جای دیگر · Read elsewhere** — `P2` · S · S · S — the unread dot fades when read on another device. NEW `notification.read`.

**NO-4 · جمع شدن در خلاصه · Digest folding** — `P2` · — · S · S — in khalvat the items fold into one digest card at digest time.

---

## 5. The holding network map, in full

**Nodes**
- **Hub** — the holding seal (the shamseh rim with 24 rays, the lapis gem, the two-metal monogram; D2 revision). It never moves. Its gem brightens only on owner acts (M10).
- **Company** — its own mark in an octagon (a company without a mark falls back to the monogram, D2), its name under it, an activity arc around it in its chart colour (palette v2 slot stored on the company; a ninth company and beyond use the neutral «other» ink, never a recycled hue). From data: `GET /links` nodes of kind `company`, never a fixed count (owner rule 9).
- **Server** — a small rounded square on the outer ring at its company's angle (± a few degrees per extra server). Online = solid positive outline; offline = negative outline with ×; pending = dashed warning; revoked = muted. Up to four per company are drawn; more fold into «+n».

**Edges**
- **Work spoke** hub↔company: a gold hairline. Orders, requests and deliveries travel here.
- **Runner link** hub↔server: a fine lapis line; solid over the private network, dashed with a small globe over the public fallback; red and broken when the runner is silent. Jobs travel here.
- **Company link** (the owner's, §35.6): a chord between two companies curving through the inner ring; `on` = gold-ink hairline, `off` = dotted muted. It never carries particles itself (servers do not talk directly); it glows while a request along it travels through the hub.

**Event → motion**

| Event | What the map does |
|---|---|
| `holding.flow kind order` | hub M10, then a gold particle hub → holder company |
| `holding.flow kind request` | silver particle A → hub, the hub's rim flickers once, hub → B; the A–B chord glows 1.5 s if `on` |
| `holding.flow kind deliver` / `accept` | silver particle B → hub → A (or company → hub for a root delivery) |
| `holding.flow kind read` | lapis particle data owner → hub → reader |
| `server.call state running` | lapis particle hub → server; the server shows M7 while the job runs |
| `server.call state done / failed` | silver particle server → hub; `failed` leaves a red tick on the server for 4 s |
| `server.state` online → offline | M9 on the runner link, red ring and × on the server, a chip «قطع · time · reason» |
| `server.state` offline → online | the gap closes (M9 reversed), the link positive for 2 s, then normal |
| `server.state via public` | the runner link turns dashed with a globe |
| `network.link ok: false` | the measured link is drawn red with its chip (server↔server links appear only while failing) |
| `links.updated` | the chord draws in (M8, 480 ms) or fades to dotted |
| `control.changed` engaged | the company's sector hatched, its spoke muted; GL-2 band |
| `employee.state` | the company's activity arc (M12) and its working count |
| `founding.updated` / `provision.step` | HM-12 |

**Scale (any number of companies).** Ring capacity = ⌊2πR / (node + gap)⌋ for the current width. Up to capacity: full nodes. Beyond: nodes shrink to a legible minimum (28 dp / 28 px), the busiest at the top. Beyond again: a second ring opens; the least active fold into a «بقیه · n» node that opens a list. The table view (HM-8) always shows every company. Ordering is by live activity, never alphabetical, so the action is always on top. Particles are capped per edge (rule 4), so a hundred busy companies do not become noise.

**Tap.** Hub → today's orders, flows per hour, servers online, stream state. Company → HM-4. Server → HM-3's sheet (state, since, last good contact, reason, blocked work, fix; hostname and address only on the server's own page, small). Edge → kind, purpose, open works, last flows, latency.

**Truth rules for the map.** Every particle is one event (GL-4 shows it). A server is offline only when the hub says so (never inferred by the client from silence). If the stream is not live (GL-1), particles stop and the map says «قدیمی» — a frozen map must never look like a calm holding.

## 6. Build order and cost

1. **Hub wave (P0 data):** F1, F2, the topic prefixes, `GET /live/summary`, additive `server.state`, `session.activity`, `employee.state`, `llm.tick`, `holding.flow`, `network.link`, with tests. About 6–8 days of hub work (K-3 M, `session.activity` M, `employee.state` M, `llm.tick` M, `holding.flow` M, `network.link` S–M, the rest S).
2. **Trust wave (both apps):** K-1, K-2, then GL-1, GL-2, NO-1, SS-1, SE-1, PE-1 — the session complaint first, because it is the owner's latest. About 6–8 days per app.
3. **Map wave (both apps):** HM-1, HM-2, HM-3, CO-1, OF-1, MO-1. About 8–10 days on Android, 7–9 on web.
4. **P1** by screen, in the order the owner uses them: sessions → office → map extras → people → money → servers → lines → the rest.

Every wave: the five-state rule of D1 (normal, loading, empty, error, offline), the reduced-motion screenshot next to the full one in each ScreensTest / Playwright test, and the frame budget measured on a mid-range phone.

**Not done, on purpose:** no glow or blur (D0), no coloured shadows, no ambient motion, no count-up numbers, no carousel that turns by itself, no sound for traffic, no animation that is not tied to an event.
