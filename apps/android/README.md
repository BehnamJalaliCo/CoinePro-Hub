# CoinePro HQ — Android

The owner's phone app for the hub at `https://hq.coinepro.com`: the same D3 design as the web (Divan design
system, IRANYekanX, right-to-left), built natively with Kotlin and Jetpack Compose.

| | |
|---|---|
| Package | `com.coinepro.hq` (debug: `com.coinepro.hq.debug`) |
| SDK | min 28 (Android 9), target 36, compile 37 |
| Toolchain | AGP 9.4.1 (built-in Kotlin), Kotlin 2.4.20, Gradle 9.7.1 (wrapper, checksum pinned), JDK 21 |
| UI | Compose BOM 2026.09.00, Material 3 only for sheets, dialogs and pull-to-refresh |
| Network | OkHttp 5 + kotlinx.serialization (snake_case), SSE via okhttp-sse |
| Sign-in | Credential Manager passkeys; session token encrypted with an Android Keystore AES-GCM key |

Every library is free and open source and pinned to an exact version (`gradle/libs.versions.toml`).

## What is in it

- **Sign-in and enrolment** — discoverable passkey sign-in; the one-time link from `make owner-enroll` opens
  the app directly (App Link `https://hq.coinepro.com/enroll#token=…`) or can be pasted.
- **Shell** — top bar (live-stream state, notifications, tools), bottom bar with the advisor's orb in the middle.
- **Command center** — greeting, what happened while away, the four numbers, cartable, the live holding orbit,
  today's planner and the month's budgets.
- **Cartable** — decisions by risk; a decision page with payload views (hire, deploy, budget change), cost and
  risk, and the **seal ritual**: press and hold 600 ms, then the passkey step-up for A3, hire, dismissal and budget
  changes. Reject (with a reason code), return with a note, ask in chat, review with the advisor.
- **Outputs** with the owner's 1–10 rating, **messages** and the **advisor** with live replies
  (`/threads/{code}/live`, falls back to polling), **companies** (departments, org chart, work), **employee**,
  **work** (delegation chain, budget, events), **treasury** (totals, cumulative month chart, token types,
  companies by their fixed palette slot, models, budgets, top consumers, connections), **planner** (week from
  Saturday), **notifications** (five levels; learning questions answered with one touch), **control** (kill
  switches; release needs the passkey), **audit** (hash-chain verification) and **settings** (devices,
  passkeys, **hiring** ⟨1.4.2⟩, theme, Khalvat, this app's signing fingerprint). Hiring is closed until the owner
  opens it ⟨1.4.3⟩: each CEO then hires inside the company's monthly envelope (the owner sets the envelopes, sealed
  on the body), or every hire stays the owner's card; the owner can always hire directly.
- **Stories** ⟨1.4.3⟩ — a row of company rings at the top of «فرمان»; a full-screen player in the company's colours
  (six seconds a card, hold to pause, left goes forward); a hire story welcomes or dismisses (passkey) in place.
- **Voice, photos and films** ⟨1.3⟩ — voice orders and voice in every composer, turned into exact Persian text for
  the owner to read before sending; photos, films and PDFs attached to messages and briefs.
- **Code Workshop** ⟨1.3⟩ — the owner's grants (sealed on the exact body), live sessions, approvals for push and PR.
- **The organisation** ⟨1.4⟩, from the tools sheet:
  - **Chief Overseer** — holds waiting on the owner (release with the passkey, or cancel), company compliance with a
    five-day trend, the last "while you were away" report, findings (verify a fix, reopen, close), the protocol
    register by area, challenges, standing orders (spoken or written, sealed) and its own thread `N`.
  - **Assistant** — thread `P` and the errands it runs on the internet, each with its trail; a commitment in the
    holding's name waits in the cartable.
  - **Stars** — best company of the week or month, the ranking from its four parts, top employees, lessons from the
    best company and each CEO's rubric. The owner's 1–10 rating stays separate.
  - **Skills** and **Academy** — new skills (spoken, with files), the overseer's four checks, the golden eval, and
    activation sealed on `ref@version`; direct teaching to a role, its diff and score, curricula and eval trends.
  - **Founding** ⟨0.4.1⟩ — the one way to a new company («تأسیس شرکت», from the companies list and the tools sheet), four steps:
    who (Persian name, a 2–4 letter code checked against every company and open founding, one line), how it starts (an idea, a
    GitHub repository, or «فقط ثبت کن» — `POST /companies` with the passkey), the brand (a logo seen in its circle and a palette
    colour, optional; kept on the phone until a founded company exists), and a review that says what happens next. A founding
    shows its stages (an idea has no audit) and «الان» in plain words; then the audit, proposal, the server plan sealed on its
    digest, the build live step by step, the owner's own login (commands to copy) and activation.
  - **Tools and internet** — egress totals and log, MCP servers enabled by the owner's seal, service accounts, the
    tool catalogue.
  - The **advisor** gains its formal inquiries; **home** gains the overseer's card; **control** gains backups.
- **The owner's tools** ⟨1.4.4⟩ on APIs the hub already serves (`docs/GAP_ANALYSIS_v2.md` §5A):
  - **Resolutions book** with search and Excel export; any message can be recorded as a resolution.
  - **Agent runs**: every run, live, with its steps and tools, and a health board per employee; runs on each work
    item and each employee.
  - **Work**: edit (If-Match), complete with evidence, cancel with a reason. **Employees**: pause, resume, dismiss
    with the passkey and a work transfer. **Removing a company** made by mistake ⟨0.4.1⟩ (its ⋯ actions and the control
    room): the code typed exactly, then the passkey; one with a history is archived instead (`company.archive`).
  - **Site checks and incidents**, with the site list editor sealed on the body.
  - **Treasury**: subscription quota, what-if per model, budget editor (holding, company month and day, dollars),
    connection name, on/off and write-only key, the calls list with paging and Excel export.
  - **Planner**: company and department scopes, a Persian month view. **Cartable** sorted by expiry or waiting time.
  - **Control**: deploy freezes set and lifted. **Settings**: the per-company, per-level notification matrix.
  - **Message search** on the messages screen; **Audit** export.
- **On the phone** ⟨1.4.4⟩:
  - **App lock** — with a secure lock screen on the phone, the app opens locked and locks again after a minute away;
    fingerprint, face or the phone's PIN opens it (Settings switch). Recents never show its content.
  - **Offline reading** — the last good answer of the screens the owner reads is kept encrypted (Keystore AES-GCM) and
    shown with a banner when the network is gone; nothing is written offline. Cleared on sign-out.
  - **Cartable widget** — pending seals and urgent items as the app last saw them (the widget never calls the hub), and
    a **quick-settings tile** that opens the voice order sheet.
- **Revenue and support** ⟨1.5⟩ (contract §19), from the tools sheet, the same data and words as the web:
  - **Revenue** — the radar (period totals against the token treasury, a 30-day line per company with direct end
    labels and its table, the companies' shares), drop and failed-pull alerts, affiliate accounts (added on the exact
    body with the passkey, the key only in the owner's terminal, pull now), the funnel (a stage without a source has
    no number) and referral rescue with its rate and steps.
  - **Support** — the teaching queue, conversations, channels (pausing is free, widening what leaves without the owner
    takes the passkey, go-live is a card), knowledge (approved with the passkey on `ref@version`) and the shadow test
    (a chat export uploaded, a run started); a conversation shows every message with its checks, sends the owner's
    reply through the outbound guard (its refusals in Persian) and teaches a knowledge proposal from the answer.
  - **Growth** — templates sealed on `ref@version:sha256`, lifecycle rules with their limits (sealed, paused,
    resumed), NPS waves. **Feedback** — the inbox, most frequent first, with state and a link to work (If-Match).
  - **Intake** on the tools screen, and the three new cards (`message_template`, `lifecycle_rule`,
    `support_go_live`) sealed with the passkey in the cartable.
- **Governance** ⟨1.5⟩ (contract §20), the «حاکمیت» group of the tools sheet, the same data and words as the web:
  - **Meeting room** — meetings before they start (agenda reordered or skipped, a lower budget, the owner's presence;
    If-Match), live (the round table compact for the phone, the queue, claims and tokens, the advisor's whisper, the
    transcript with unsourced claims flagged, the owner's voice or text jumping the queue, next round, skip, raise the
    budget, end), the minutes with their draft resolutions, the war room; the meeting types sealed on the exact body.
  - **Charter** — the holding charter and each company's addendum, versions and the server's diff, a new version with
    its red lines, and the seal bound to the `body_sha256` the server sent. **Knowledge** — four layers, sources and
    expiry, review checks, versions; the employee layer and the support articles read-only.
  - **Cards and scorecard** (a KPI without a source is a dash, never zero; targets with If-Match), **OKR**,
    **outcomes** at 30/60/90 days with prediction accuracy, the **risk register** with its 5 × 5 matrix, the
    **change calendar** with its conflicts, the **authority matrix** (sealed on the body; locked invariants shown).
  - In the cartable: the **batch seal** (several low-risk A1 cards, one passkey on the sorted `[{ref, version}]`, all or
    nothing) and the six new kinds with their payloads, a proposal's measurable promise and its reviews.
- **Management tools** ⟨1.5⟩ (contract §21), the «ابزار مدیریت» group of the tools sheet and inside the screens the owner
  already uses, the same data and words as the web:
  - **Advisor** — the devil's-advocate switch (thread A only), the weekly review (agenda items done, deferred or noted;
    If-Match; the minutes as a deliverable), memos and proactive notes. **Ask the hub** on the home: a question of ≤ 500
    characters, optionally limited to companies, answered with its sources (code with path, lines and commit).
  - In the cartable: a pending card says how long it has waited and its reminders; the **deploy card** shows its diff file
    by file (a cut file opens whole), CI, tests, the window and the second review; the **evaluation** card of the HR round
    (passkey); each card's **memo** in standard and devil mode with the substitutes' second and third opinions; and the
    digital CEO's prediction once the owner has decided.
  - **Notes** (no delete: archive; promote to work, an order or an errand), the **morning briefing and the CEOs' weekly
    letters** with their voice, **department rank and the HR round** on the company and employee pages, **waste and ROI**
    in the treasury, the **connection wizard** in the tools (sealed on the exact body with the wizard's key), **run
    health and claims**, the **digital CEO** (accuracy, calibration, principles), the **substitute players** (seats and
    daily caps, the $20-equivalent usage, CLI sign-in and sign-out with the passkey, the browser profile, creatives with
    placement and overlay, accepted or rejected) and the **management settings**.
- **Media and legal** ⟨1.6⟩ (contract §22), the «رسانه و حقوقی» group of the tools sheet and inside the company pages,
  the same data and words as the web:
  - **Media studio** — every company's items by stage on a pipeline board (scripting to published, and what is held or
    failed), what waits for the owner, the next automatic publication and the hub's voice; an item with its render (poster
    and player), voice, captions and assets, its script with sources, shots, composition, the code checks and the media
    manager's QC, each placement's publication and its cost; a one-off item (always a card; a UI design goes to the CTO);
    the file shared to the phone's apps; unpublishing with the passkey on the item.
  - **Publishing series** — kind, channels and placements (the platforms' own rules), a weekly schedule, topics, format,
    checks and the daily cap; edits with If-Match return a sealed series to «منتظر مُهر»; the seal is the passkey on the
    series' `digest`; pause and retire are free. The channels' week and each account's remaining platform limit.
  - **The hub's voice** — the active voice, the blind listening test scored 1–10, the registry with licences and CPU
    speed, activation with the passkey (a non-commercial licence acknowledged first in words), and the owner's own
    reference voice recorded on the phone (60–180 s).
  - **Legal counsel** — cases by company and status with their counterpart, deadlines and timeline, the mailbox, thread
    `L`, a new case with files; an email the counsel drafted is sealed with the passkey on the message's digest, exactly
    as it will leave (the same in the cartable's `email_send` card), returned with a note or rejected.
  - **Departments and roles on demand** — a department's mandate (from, to, delivers, limits, ceilings, character and a
    starting team) written and sealed on the exact body with If-Match; the roles its manager writes, their gates and
    eval, asked for by the owner and retired; their `role_new` card and story.
  - In the cartable: `media_publish` (render, placements, checks), `media_series` (sealed on the series page),
    `email_send` and `role_new`; refs `SR-`, `MI-`, `LC-`, `RD-` and thread `L` open their pages; stream topics `media`
    and `legal`; the §22.6 codes (a platform's limit says how long to wait) in Persian.
- **The archive** ⟨1.7⟩ (contract §23), the «بایگانی» group of the tools sheet, the same data, calls and words as the web:
  - **Home** — Persian-normalised search with snippets from the files' own text; filters by scope, class, folder, level,
    party and the document's dates; drafts with their suggestion; what expires soonest; the last fixity run; a party's
    records. **سند تازه**: files from the system picker are uploaded, then `POST /archive/intake` scans them for secrets
    (a refused file is named, never what it held), hashes and reads them and suggests a class and metadata; the owner
    makes a draft, files at once, or sends one draft per file to the archivist.
  - **A record** — metadata typed by its class (money with its currency, Jalali dates, parties, ref links, sensitive
    fields masked to their last four), files and versions with their SHA-256 and manifest (a level that asks for it is
    viewed with the passkey on the ref; images and PDF pages drawn on the phone, or opened in another app), links (added,
    removed unless sealed), holds, the seal on the current manifest, raising the level and declassifying it with the
    passkey on `ref@version:level` (a sealed record too), retention and reminders, the access log (a level change is a
    row); a draft is completed and filed (If-Match); a disposed record shows only its tombstone.
  - **Legal holds** (placed with the caller's key, released with the passkey on the ref; also on a legal case's page),
    **reminders** (marked done) and **the end of retention** (its disposal card).
  - **The open layer** — one tab per part of the schema (classes and their fields, folders, levels, clearance,
    retention, reminders, party kinds, link kinds, automations, and any part the hub adds), the parties registry and the
    system sources; every form is drawn from `GET /archive/schema` and its closed vocabulary. A save is a dry run first
    (its impact), then the passkey on the SHA-256 of the exact body and a PUT with If-Match (`If-None-Match: *` for a new
    key); nothing is deleted, only retired; `schema_invalid` errors stand next to their fields.
  - In the cartable: `archive_schema` (the change against the current row, its impact; void when the row moved on) and
    `archive_disposal` (its records; a held one is skipped); refs `AR-`, `LH-`, `PT-`, `FP-`, `RR-`, `RM-`, `AU-` open
    their pages; stream topic `archive`; the §23 codes (`clearance`, `sealed_record`, `schema_invalid`,
    `secret_in_document`, `held`) in Persian.
- **The companies' servers** ⟨1.8⟩ (contract §26, prompt 17; built ahead of the hub against the contract, the demo answers every call):
  - **«سرورها»** on each company page and **«همه‌ی سرورها»** in the tools sheet — each server's state (reachable, unreachable, waiting to be
    reached, host key changed), whether the hub made it or it was attached, when it was last seen, and from its latest `server.map` the disk and
    memory bars and what runs on it. A server's page: its **map** (system, disks, RAM and swap, containers, compose projects, systemd units and
    timers, cron, listening ports with the public ones marked, repositories with remote, branch and head, n8n and other automations, the sites
    it serves; refreshed on demand), its **activity** live (`/infra/servers/{id}/activity` and the stream's `server.call`: who, which tool, the
    masked command, exit code and duration, its Claude session and the full transcript) and its **sessions**.
  - **«یک کار بسپار»** — Claude Code on the server itself (`runtime: "company_server"`), driven by the company's CEO or a manager, or by the
    owner; the brief spoken or written, with files; watched, steered and stopped on the Workshop's own session page.
  - **«ترمینال»** — the owner's own command (`POST /infra/servers/{id}/exec`, a passkey per command bound to its exact body), the output streamed
    into a monospace, left-to-right panel that scrolls both ways; `sudo`, stop, and the last commands a tap away (in memory only).
  - **Seals** — a destructive command (`server.awaiting_seal`, a `server_destructive` card) stands at the top of the cartable and on the server
    with the whole command, the server, the kind of loss and who asked; the seal is the passkey on `server.destructive` (`<CODE>:<server>`), a
    «نه» needs none. **«قوانین سرورها»** (settings, control, tools) switches the six categories with the passkey and says what runs free.
  - **Attaching** — company, name, private IPv4, the work user and the host key fingerprint (checked on the phone: a private range, not the hub,
    never root, `SHA256:` and 43 characters), sealed `server.attach`; then the hub's key line with the setup sheet's restrictions to copy or send
    to that server's Claude with `COMPANY_SERVER_ACCESS_SETUP.md`, and the wait until it is reachable. Re-pin and detach in the server's ⋮.
  - **Kill switch** — a stopped company's servers are locked (no task, no terminal); the control room shows the servers and their live calls.
- **Live** — `/api/v1/stream`, one connection per lane of topics (the hub takes at most 200 characters of `topics`;
  `core/data/StreamTopics.kt`); events refresh the screens that show the touched data (the same invalidation map as the web). The first
  lane is the alert lane (`work,decisions,deliverables,notifications,control`); the others open only while the app is on screen.
- **Alerts with the app closed** (the background link; owner's decision: no FCM, no Google, no second app) — a foreground service
  (`device/HubLinkService`, type `specialUse` with its reason in the manifest; `dataSync` is capped at six hours a day from Android 15)
  keeps the process in the foreground so the stream's alert lane stays open: the same connection the app uses, never a second one. One
  quiet notification «اتصال به ستاد» says «وصل به ستاد · زنده» (or why it is down); a tap opens the app; «قطع تا بازگشت» stops it until
  the app is opened again. `core/link/AlertCenter` turns events into alerts on five channels — «فوری» (urgent notifications, a kill
  switch someone else moved; high), «منتظر تو» (cards waiting for the seal, holds, serious findings), «فرمان‌ها» (the orders tracker),
  «خروجی‌ها و گزارش‌ها» (low, silent) and «ورود به ستاد» — after reading from the hub what each one is and whether it still stands: a
  notification already read (here or on the web), a card already decided, an output already seen or an order's own output is not told.
  Every event is told once (event ids kept across restarts), the same alert raised again updates its count, a burst sounds once, a
  channel with several alerts gets an InboxStyle summary, a tap opens the page through the ref router and marks the hub's notification
  read, and reading it in the app takes it out of the shade. With the app on screen the app's toast speaks instead, never both. With the
  app lock on, the lock screen shows only «پیام تازه از ستاد». Reconnects back off (1 s doubling, with jitter; 30 s cap on screen,
  5 min in the background) and resume with Last-Event-ID (kept for six hours across process restarts); with no network the link waits for
  the system's network callback instead of retrying blind, and a new network reconnects at once; a connection silent for 50 s (the hub
  beats every 15 s) is taken for dead. A WorkManager watchdog every 15 minutes starts the service again if the system stopped it, and
  `BOOT_COMPLETED` / `MY_PACKAGE_REPLACED` start it after a reboot or an update; when Android refuses a background start, one quiet
  notice offers a tap to reconnect. A session that expires with the app closed posts «برای ادامه‌ی اعلان‌ها وارد شو» once and stops the
  link. Connects, drops and restarts go to «خطاخوان» at info level, repeats folded. Settings → «اعلان‌ها وقتی اپ بسته است»: the switch
  (on by default once notifications are allowed), the state, the permission, the battery-optimisation exemption and, on Samsung, the
  «Never sleeping apps» tip. In the demo, closing the app plays what the link would hear: a card, an order delivered, an urgent alert.
- **Notifications** ⟨0.4.1⟩ — «خوانده‌نشده» holds only what is unread: a tap opens it and it leaves the list, a swipe or «خوانده شد»
  marks it read (five seconds to undo, since the hub cannot mark one unread again), «همه خوانده شد» moves everything up to the newest
  shown; «خوانده‌شده» keeps the rest. The same alert raised again (the overseer's hourly finding) is one row with its count, opened on
  every time; each row is labelled by what it is about (its link), not its level.
- **One ref router** ⟨0.4.1⟩ (`core/data/Refs.kt`) — every ref, notification link and planner row opens its own page by prefix (`W-`
  work, `MT-` meeting room, `D-` cartable, `O-` output, `AR-` archive, `C-` founding…); only a work item reaches the work page.
- **Outputs read and filed** ⟨1.7.3⟩ (contract §5.2) — «تازه» / «خوانده‌شده» / «همه» and «بی‌امتیاز», filters (category, company,
  producer, date range, search), grouped by Jalali day; a swipe (with undo), the page's «خوانده شد» or «همه را خوانده‌شده کن» marks
  seen, «بایگانی کن» files it as an `AR-` draft. Until the hub serves ⟨1.7.3⟩ (`POST /deliverables/seen` answers 404/405), «seen» is
  kept on the phone and sent up once the hub sends `seen_at`.
- **Markdown** — the hub's reports as written: headings, quotes, nested lists, code, rules and GFM tables (a real table, right to left,
  figures Latin, scrolling sideways inside its card when wide); refs open their pages.
- **Voice to text on the phone** — every voice-to-text (orders, notes, composers) uses the phone's own speech recognition in Persian
  (`fa-IR`) while the hub's `/transcribe` is off; the hub is asked only where the phone has none (and keeps the original audio then).
  The gold button in the middle of the bottom bar speaks an order (a long press types one); the advisor is first in the tools sheet.
- **«خطاخوان»** (Settings, and the tools sheet) — a forensic log per app version: a new version opens an empty log with an "app started"
  line and keeps the last three versions' logs apart («نسخه‌های قبلی», read-only); up to 1000 entries per version. Every entry has a sequence
  number, its time in Asia/Tehran and in UTC to the millisecond, a level (error, warning, info), the app version, screen, foreground or
  background, the network (wifi, cellular…), the masked path, status, duration, the server's code and sentence, the request id (the app sends
  its own `X-Request-Id` on every call and the hub echoes it, so the hub's logs match), an allow-list of response headers, and the last ten
  screens and steps before it. Crashes (stack trimmed, shown on the next start), contract mismatches with their field, stream drops and
  reconnects, passkey and speech-recognition failures are recorded too. A hub restart's burst of 502/503/504 or unanswered calls is one
  entry ("hub unreachable, N requests, from–to", with the tally and the requests it touched); real 4xx and 5xx stay their own. Filter by level,
  search, copy or share as plain text with a header (version, device, Android, time zone, export time in both zones). Secrets never enter it:
  tokens, cookies, `X-Step-Up`, passwords and keys are redacted by name in any text, ids and contacts masked (`ErrorLogTest`).
- **Company control** (contract §9) — every company card in «شرکت‌ها» (and «کنترل») shows its state at a glance: running, stopped
  (its own switch or the holding's) or deploys closed, a chip with its icon and a coloured edge; its mark in a ring where a gold comet
  orbits while its agents work (`GET /runs?state=running` and the stream's `run.*` and `activity.changed`); today's spend
  (`/treasury/breakdown?by=company` for today), open work, cards waiting and active staff. Stop or resume, close or open deploys on the
  card; a long press (or ⋯) adds the cartable filtered to the company, an order to its CEO, a message and the control room. The holding's
  card on top carries the switch that stops everything. Stopping asks no passkey (a reason, or one tap «فوری»); resuming is sealed
  (`kill_switch.release` on `holding` or `company:<CODE>`), opening deploys too (`deploy_freeze.lift` on `company:<CODE>`); the
  confirmation says exactly what happens. Every action shows at once and rolls back if the hub refuses. A company's page opens on its
  **control room**: the state and the switches, their history (audit rows, with the owner's reasons from `/owner/interactions`), the
  month's budget as a gauge with a quick edit (`PUT /budgets`, `budgets.update` on the body), the live activity of its agents, hiring
  and its envelope, and its sites' health.
- **Priorities in words** ⟨0.4⟩ — P0…P4 are chosen and shown by name with the code small beside it: «اضطراری» (incident and war room;
  runs even with the kill switch on), «فوری» (what product users see), «مهم» (the owner's level; a reserved slot), «عادی» (the default:
  scheduled operations), «هر وقت شد» (background; paused first when the quota warns). The chosen one's meaning sits under the picker
  (`ui/work/Priority.kt`, `core/format/Priority.kt`); red belongs to the emergency alone.
- **«فرمان‌های من»** ⟨0.4⟩ — every order the owner gave (home's card, the cartable's header, the tools sheet): company, title, priority, the
  stage on a stepper (ثبت شد → مدیرعامل گرفت → واگذار شد → در حال انجام → تحویل شد → تمام), an estimate in steps of 5 that moves only when
  something happens (stage weight plus the share of the children done; `core/data/Orders.kt`), who holds it now down the delegation, when it
  last moved, and its output. An order's page adds the timeline of its events, its children's and its runs' step summaries, live from the
  stream. An order delegated, delivered, failed or done is a toast with a way in while the app is open, and a notification on the «فرمان‌ها»
  channel while it is closed (the background link below; Android 13+ asks first; no push service). The live feeds name works by ref and title, never by id: an id is looked up once
  (`core/data/WorkTitles.kt`) behind a skeleton.
- **A hub restart** ⟨0.4⟩ — a read that meets 502/503/504 or no answer is retried twice quietly; four such failures within 15 s mean the
  hub is away (`core/net/HubHealth.kt`): one calm banner «هاب در حال راه‌اندازی دوباره است؛ خودکار وصل میشوم», screens keep what they had (or
  their skeletons) instead of an error on every card, the app probes `/meta` with a growing pause, and the first answer refreshes what waited.
  In the demo, a long press on «نمایشی» plays a nine-second restart.
- **The tools sheet** ⟨0.4⟩ — opens at half height; two tiles to a row in eight titled groups, each tile with its icon, name and one line on
  what it is for; a row of the groups' names jumps to one; the tiles arrive with a spring, one after another (still with animations removed).
- **Motion** — `designsystem/Motion.kt`: three durations (120, 220, 400 ms) and the standard and emphasised curves for everything that
  moves (screens pushed and popped, list items arriving and reordering, press feedback, expand and collapse, counters, meters, the
  breathing glow of the gold button while it listens, the shimmer of what is loading); loops run in the draw phase only. With the phone's
  «remove animations» every state is instant and every loop still.

## Layout

```
app/src/main/java/com/coinepro/hq/
  core/net/        Api (contract v1.7; every 🔏 write names its step-up action and target), Models, Models14 … Models21
  core/auth/       Auth (sign-in, enrolment, step-up), Passkeys, TokenVault
  core/data/       QueryCache (shared cached queries), HoldingStream (SSE), LiveActivity (who works now), Control (switches, optimistic),
                   Orders (stage, estimate, holders, timeline, notices), OrderWatcher, WorkTitles (ids to refs and titles)
  core/link/       the background link: HubLink (what runs when), AlertCenter and AlertRules (events to alerts), Backoff, LinkJournal,
                   NetworkWatch, LinkStore
  core/diag/       ErrorLog («خطاخوان», per version), Diag
  core/format/     Jalali dates, figures, Persian labels
  designsystem/    Theme, motion and spacing, icons and marks, components, seal, avatar and orb, charts, Markdown subset
  designsystem/generated/   made by scripts/gen_assets.py from design/ — never edited by hand
  ui/              screens
app/src/debug/     the demo holding (fixtures shared with the web); not in release builds
app/src/test/      API contract, fixture decoding, formatting and screenshot tests; screenshots/ = every screen, night and day
```

## Build

```bash
export ANDROID_HOME=/path/to/android-sdk     # or sdk.dir in local.properties
./gradlew testDebugUnitTest assembleDebug assembleRelease
./gradlew recordRoborazziDebug               # refresh app/src/test/screenshots after a design change
python3 scripts/gen_assets.py                # after design/ changes (CI runs it with --check)
node --experimental-strip-types scripts/dump_demo_fixtures.mjs   # after the web's mock fixtures change
```

CI (`.github/workflows/clients.yml`) runs the tests and publishes both APKs to the prerelease
**android-latest**: `coinepro-hq.apk` is the app, `coinepro-hq-debug.apk` the development build with
**«نمایش آزمایشی»** on the sign-in screen (the demo holding, no server, no passkey).

## Passkeys on Android

The owner's signing key exists (alias `coinepro-hq`, created 2026-10-17; kept by the owner and in the four
repository secrets below). Its public identity, which the hub needs:

- SHA-256: `D6:D4:15:6F:7F:0E:AE:95:4A:F4:14:BA:A8:8B:6A:E8:C6:84:27:03:5F:62:71:B4:C5:ED:97:0F:39:2A:15:BF`
  (the web's `assetlinks.json` default, for `com.coinepro.hq` and `com.coinepro.hq.debug`)
- WebAuthn origin: `android:apk-key-hash:1tQVb38OrpVK9BS6qItq6MaEJwNfYnG0xe2XDzkqFb8` (the API's `HQ_ANDROID_ORIGINS`) <!-- gitleaks:allow (public certificate hash, not a secret) -->

Both the release and the debug build are signed with it when the secrets are present.

### How it was set up (for a future key)

Credential Manager only lets an app use the hub's passkeys when the domain vouches for the app. That needs the
app's signing key, which is the owner's alone.

1. **Signing key** — on the owner's own machine, once:
   `keytool -genkeypair -v -keystore coinepro-hq.jks -alias hq -keyalg RSA -keysize 4096 -validity 10000`.
   Keep it outside git. For CI add four repository secrets: `HQ_SIGNING_KEYSTORE_B64` (the file, base64),
   `HQ_SIGNING_STORE_PASSWORD`, `HQ_SIGNING_KEY_ALIAS`, `HQ_SIGNING_KEY_PASSWORD`. Locally,
   `apps/android/keystore.properties` (git-ignored, mode 600) with `storeFile`, `storePassword`, `keyAlias`,
   `keyPassword`.
2. **Digital Asset Links** — the web serves `https://hq.coinepro.com/.well-known/assetlinks.json` from two
   variables of the web service: `HQ_ANDROID_PACKAGES` (default `com.coinepro.hq`) and
   `HQ_ANDROID_CERT_SHA256` (the fingerprint, `AA:BB:…`; several allowed, comma-separated).
3. **API allow-list** — the API accepts the app's WebAuthn origin from `HQ_ANDROID_ORIGINS`
   (`android:apk-key-hash:…`).

The app shows both values under **تنظیمات → این اپ** with copy buttons, computed from the key it was signed with.
Until then the app installs and runs, the demo works in the debug build, and sign-in reports that the app is not
yet linked to the domain.

Push notifications through FCM are dropped (owner's decision, 2026-10-17: one user, the GitHub release is enough, no Firebase project).
Notifications arrive over the app's own live stream: in the app while it is open, and through the background link's foreground service
while it is closed (see **Alerts with the app closed** above).
