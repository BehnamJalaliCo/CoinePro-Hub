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
  - **Founding** — from a repository or an idea: audit, proposal, the server plan sealed on its digest, the build live
    step by step, then the owner's own login (commands to copy) and activation.
  - **Tools and internet** — egress totals and log, MCP servers enabled by the owner's seal, service accounts, the
    tool catalogue.
  - The **advisor** gains its formal inquiries; **home** gains the overseer's card; **control** gains backups.
- **The owner's tools** ⟨1.4.4⟩ on APIs the hub already serves (`docs/GAP_ANALYSIS_v2.md` §5A):
  - **Resolutions book** with search and Excel export; any message can be recorded as a resolution.
  - **Agent runs**: every run, live, with its steps and tools, and a health board per employee; runs on each work
    item and each employee.
  - **Work**: edit (If-Match), complete with evidence, cancel with a reason. **Employees**: pause, resume, dismiss
    with the passkey and a work transfer. **New company** straight from the companies list.
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
- **Live** — one SSE connection to `/api/v1/stream` while the app is in the foreground; events refresh the
  screens that show the touched data (the same invalidation map as the web).

## Layout

```
app/src/main/java/com/coinepro/hq/
  core/net/        Api (contract v1.6; every 🔏 write names its step-up action and target), Models, Models14 … Models19
  core/auth/       Auth (sign-in, enrolment, step-up), Passkeys, TokenVault
  core/data/       QueryCache (shared cached queries), HoldingStream (SSE)
  core/format/     Jalali dates, figures, Persian labels
  designsystem/    Theme, icons and marks, components, seal, avatar and orb, charts, Markdown subset
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

Push notifications through FCM are dropped (owner's decision, 2026-10-17: one user, the GitHub release is enough, no Firebase project). Notifications arrive in the app over the live stream.
The in-app stream covers notifications while the app is open.
