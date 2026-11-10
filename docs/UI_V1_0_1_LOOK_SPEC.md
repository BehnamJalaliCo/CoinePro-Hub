# Update 1.0.1, part C: the app's look, the short list (Android and web, the same on both)

Read first (in the repo): `docs/HANDOFF_2026-11-10_V1_0_1.md` section «بخش پ», `docs/UI_COMMAND_ROOM_PROPOSAL.md`
(§2 direction, §4 the motion grammar M14 to M21, and the numbered features named below),
`docs/UI_SCREEN_REVIEW_2026-11-10.md` (the patterns and «اشکال‌های واقعی»), `design/D0_BRIEF.md` §11
(what «premium» means), the board `design/canvas/D5-Command.dc.html` (panels 1, 2, 3 only), and for each
screen you rebuild its entry in `docs/ui-review/<group>.json` (`gaps_fa`, `premium_fa`): the groups are
`01a-home-orders`, `01b-session-live`, `05a-studio-outputs`, `05b-growth-revenue`, `07-knowledge-v29-v30`.

This is the ONLY scope. Deliberately NOT built: «ماموریت‌ها», «کشیک ۲۴ ساعته», «ناوگان», SEO dashboard,
YouTube / X templates, live server work, the swipe decision queue, the hold-to-seal ritual (M20),
the network-frame preview, global search, personalization. Do not touch other screen families.

The owner's standing decisions that shape every screen:
- Approval in the session is enough: one tap, no second card, no fingerprint (fingerprint only for
  money, permanent delete, keys and access, a destructive server command). So NO hold-to-seal anywhere here.
- Nothing sends the owner elsewhere: what waits for him is answered where he sees it.
- Instagram is never «وصل نیست» and never the owner's step. The owner's own voice talk is off: no
  microphone as a gold element; keep an existing mic quiet (silver) and never add one.
- Persian, short, plain; no role codes, hostnames, English error text, file paths or commands on a
  screen (a technical detail goes one tap away under «جزئیات فنی»).

## C0. Rules of the look (apply in the shared components, so every screen gains)

### C0.1 One full gold per screen («یک طلای پُر در هر صفحه»)
- Filled gold is ONE component: the primary action button (`PrimaryAction` / the existing filled gold
  button). A screen (or an open sheet) shows at most one of it: the owner's main act there.
- Gold as a thin line or a small mark only says «this waits for you» (the «نوبت تو» mark, the edge of
  the «منتظر تو» card, an unread row's 2px edge).
- Everything else that is gold today turns silver / ivory in the shared components: a selected chip
  or tab, a switch that is on, «کپی» and other small text actions, section titles, work numbers,
  the play button, the mic, the «همه» link, tags like «بی‌امتیاز». Selection = ivory text on a
  raised surface with a silver hairline. A switch that is on = silver knob on a lighter track.
- A warning keeps its own amber sign with an icon (it must not read as gold in the day theme).
- Second and later actions of a list (e.g. the 2nd «تأیید و انتشار» of a list) are outlined (quiet),
  never filled.

### C0.2 The decision bar («نوار تصمیم چسبیده به پایین»)
One shared component `DecisionBar`, stuck to the bottom above the system inset (and above the
composer when there is one): one optional line of context (what is decided, in one sentence), ONE
primary action (the screen's full gold), up to two quiet actions beside it (e.g. «اصلاح», «بعداً»),
and a state for «working» (the primary shows a small arc and is disabled) and «done» (a drawn tick,
M8, then the bar leaves). Used by: the output page («تأیید و انتشار» · «اصلاح»), the working group's
seal («مُهر کارگروه» · one-line summary), the session's «منتظر تو» card (C2.3 is its in-thread form),
the publish sheet («انتشار»), the ledger / narrator / routine sheets («ثبت», «افزودن», «بساز»).
The action it replaces is removed from the bottom of the scroll (never two).

### C0.3 Motion, in the shared components (all become instant with reduced motion)
- **165 / M14 continuity:** a tapped card grows into the screen it opens (session, output, working
  group, company treasury). Android: Compose shared-element / container transform where the Compose
  version in the project supports it, else scale+fade from the touched bounds (320 ms, spring without
  bounce). Web: the View Transitions API (`document.startViewTransition`, a shared
  `view-transition-name` on the card and the page header) with a plain fallback.
- **166 / M15 spring sheet:** ONE shared sheet: a handle, height by its content (never a full-height
  sheet with an empty half), follows the finger, settles with a spring, drag down to close; the
  primary action is stuck to its bottom (the decision bar). Every sheet of the six families uses it.
- **167 / M16 touch feedback:** every pressable surface (button, card, row, chip) scales to 0.98 and
  back in 120 ms. One shared modifier / CSS class; no touch without an answer.
- **168 / M21 subtle haptics:** tick = one light tap (a step done, a selection, «خوانده شد»);
  seal = one heavier tap (an approval sent); error = two short taps. Android: the platform haptic
  constants through one small `Haptics` helper; web: `navigator.vibrate` (10 to 30 ms) when present,
  silently nothing otherwise. Never on a passive update.
- Lists settle in steps the first time (M17: 30 ms apart, at most 8 rows). Headers of the session,
  output and working-group pages collapse on scroll to one line (M18).
- Nothing moves at rest: no pulsing, no shimmer on idle content.

### C0.4 Numbers and text
- A Latin token inside Persian text (money, a percentage, a ref like O-000152, P0, a file name, a
  handle) is one isolated LTR run (U+2066 … U+2069 / `<bdi dir="ltr">`): add one shared helper and
  use it in the shared number, money and ref formatters.
- The separator between facts is NOT «·» next to a Persian digit (it reads as a zero). The shared
  separator becomes a thin vertical hairline with spacing (or a spaced «،» where it is a sentence).
- An amount is never cut with «…»: the shared amount text shrinks its font to fit (down to a floor),
  and a table that is wider than the screen scrolls sideways inside its card.
- Money, rank and percent: Latin tabular digits. A count inside a sentence: Persian digits. One kind
  of digit for one kind of number on a screen.

## C1. The five real defects (fix at the cause; both clients where the screen exists)
1. Bidi: «P0» shown as «(0P)» in the stop sheet; the commission amount reversed on the advisor page;
   the cost label scrambled in the server seal card → C0.4's isolate.
2. «·» beside a Persian digit («۲ از ۴ کار» reads «۲۰ از ۴ کار») on home and the session header →
   C0.4's separator, everywhere the shared one is used.
3. Cut amounts (commission shortfall, ad spend) and the report table whose last column leaves the
   edge → C0.4.
4. Text against the owner's decisions: the publish card's «حساب کلید ندارد؛ این بار نه» for Instagram
   (replace: the publishing path is the technical team's work, e.g. «مسیر انتشار این شرکت را تیم فنی
   وصل میکند؛ بعد خودش منتشر میشود.»), and the terminal command shown to the owner on the studio item
   page (remove it from the page; at most under «جزئیات فنی»).
5. Android screenshot tests that capture something else: `revenue-funnel`, `revenue-accounts`,
   `revenue-rescue` do not show what their names say; `deploy-memo` = `deploy-memo-devil` and
   `session-chat-your-turn` = `session-live-waiting` are identical pairs. Make each test render its
   own state and re-record. (Web: check the matching e2e specs assert their own state.)

## C2. The three pages

### C2.1 The command bar, everywhere (features 1, 2; UI of 73 and 153; D5 panel 1)
- A round command button (the HQ mark inside a thin gold ring, NOT filled gold) on every top-level
  screen, in the same corner above the navigation. Hidden only inside a session (its composer is the
  command there) and while a sheet is open.
- Tap → the spring sheet «چه میخواهی؟»:
  1. the text field (autofocus; placeholder «بنویس چه میخواهی؛ درباره‌ی هر چیزی»);
  2. template chips that only fill the starting text (the path is the same one path):
     «ریلز اینستاگرام» → «برای {شرکت} یک ریلز اینستاگرام بساز: »,
     «موشن‌گرافی» → «برای {شرکت} یک موشن‌گرافی بساز: »,
     «کارمند ۲۴ ساعته» → switches the sheet to the routine form (below);
  3. «برای کدام شرکت؟»: the companies as their own marks (the brand mark / initials tile the app
     already draws, with the name under it), from the companies the hub returns (any number; a
     horizontal row that scrolls); tap selects one or several (silver ring = selected); none
     selected = the holding decides;
  4. the pace: «با من» / «خودکار» (a two-part silver switch; the app's existing default);
  5. the decision bar: «باز کن» (full gold, enabled once there is text).
- «باز کن» uses the existing new-order call; several companies = the existing way the app sends an
  order for more than one company (if the hub takes one company per order, the text names the others
  and the order goes to the holding). On success the sheet becomes the session (M14) and the app is
  in that session. A failure keeps the text and shows `message_fa` above the bar; haptic error.
- «کارمند ۲۴ ساعته» (features 73, 153): the same sheet shows one sentence field (placeholder «مثلاً: هر
  روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده»), the company marks (one), and «بساز» →
  `POST /api/v1/routines {sentence_fa, company}` (part A item 4; no card, no fingerprint). Success:
  a quiet confirmation row with `when_fa` and «نوبت بعد: …», and «باشه». `422` → `message_fa`.
  In a session, «همین را هر هفته بساز» is the existing «روال دائمی» action of part A (keep it there).
- The home screen's old inline «فرمان تازه» card becomes one row that opens this sheet.

### C2.2 The session, redesigned, with the workshop inside it (features 13, 14, 15, 75, 28, 29, 30; D5 panel 2)
- **One-line header (13):** the short title · «کار ۳ از ۴» · the pace · the mood light. The rest
  («جزئیات», the full order text, the plan) is behind the header's tap (the existing details sheet).
  It collapses on scroll (M18). A segmented progress line under it: done parts silver, the part that
  waits for the owner gold, the rest empty.
- **Mood light (75):** a small shape + one word, never colour alone: «فکر میکند» (hollow ring),
  «کار میکند» (ring with a turning arc, M7, only while work is live), «منتظر تو» (gold dot),
  «گیر کرده» (red broken ring), «آرام» (grey dot), «تمام» (tick). From `SessionActivity.mood`
  (new, below); on an older hub derive it: `stuck_fa` → stuck, `waiting_fa` → waiting,
  `working` not empty → working, else idle.
- **Work timeline (14):** the thread's event rows become thin centred lines without a box («مدیر
  رسانه آمد · ۰۹:۳۰»); each step of live work is one line with its real clock time and the company's
  name; a finished step gets a calm drawn tick (M8). The owner's messages have a thin gold edge, the
  holder's a silver mark. «کپی» and the time under every bubble go away: they appear on long-press
  (Android) / hover or the bubble's menu (web).
- **The «الان» bar (7 of the patterns; 28):** stuck above the composer while something works:
  the worker's mark, «{who} · {company}», the full sentence of what it does (`last_fa`, else
  `doing_fa`; wraps to two lines, never «…»), a timer in Latin tabular digits, and «نگه دار» at the
  far edge (48dp, quiet red outline; one tap stops the live work through the existing stop/cancel
  call; it then reads «ادامه بده»). A 4px silver work line under it moves only while work is live (M5).
  - A workshop or direct turn (`kind` = `workshop` | `direct`, `cap_s` set) shows the **build ring
    (28)**: a ring that fills with real elapsed time out of `cap_s` (60 minutes), the minute in its
    middle («۲۳» over «از ۶۰ دقیقه»), and the last work line beside it. At 90% the ring turns amber.
  - A direct turn is the holder himself («{holder} · دارد روی فرمان تو کار میکند»), no «کارگاه» word.
  - Several workers: their marks side by side; tap opens the live-work sheet with each one's line.
- **The «منتظر تو» card (15):** ONE place for the question (not header + bubble + bar): a card with
  a thin gold edge right above the composer: the question, then 2 or 3 ready answers as buttons when
  the question offers them (the hub's quick replies if the report carries them; else, for a question
  that names two or three options with «یا», offer those options; always a last quiet
  «خودت تصمیم بگیر و ادامه بده»), and a small line «۶ دقیقه منتظر | کار ۳ از ۴ ایستاده». One tap sends
  that answer through the existing reply call; the card folds into the owner's message in the thread
  (M1), haptic seal. Typing still works. Everywhere «تو», never «شما».
- **A stuck session:** one «گره» card instead of stacked banners: one full sentence of why
  (`stuck_fa`) and one primary action when the hub offers one (else «ادامه بده»).
- **Output files strip (29):** the session's output files as a horizontal strip of tiles right in
  the thread where they arrived and pinned in the header's details: a picture shows itself, a video
  its poster frame with a duration, a PDF / text its type mark and name; the tile's caption is the
  file's plain name and size. Tap opens it in place. Under a publishable tile the quiet outlined
  «تأیید و انتشار» (opens the existing publish sheet); when it is the thing the session waits on, it
  is the decision bar's full gold instead.
- **In-session video player (30):** a tap on a video tile plays it inside the session (inline,
  muted autoplay off; one more tap = full screen with controls and sound). Android: the platform
  player (no new dependency unless the project already has one); web: the `<video>` element with the
  authenticated file URL the app already uses for downloads. Errors say «این ویدیو پخش نشد؛ دانلودش کن»
  with the download action.
- **«ساخت»:** where part A showed `produced_with` («ساخت: Opus 5.5 | بیشترین دقت»), keep it as the
  quiet last line of the output tile's details.
- **Direct session (contract §54):** `OrderReport.direct` true → the details say «مسئول این جلسه
  خودش کار را انجام میدهد (جلسه‌ی مستقیم)»; nothing else changes for the owner.
- **End:** a closed session ends with an end leaf: what was made (the files strip), how long, how
  many tokens; never half an empty screen.

New hub data (contract §55.1; tolerate its absence):
`SessionActivity.mood: "thinking"|"working"|"waiting"|"stuck"|"idle"` and `mood_fa`;
`Worker` gains `kind: "run"|"workshop"|"direct"|"server"`, `cap_s: int|null`, `last_fa: string|null`,
`last_at: datetime|null`.

### C2.3 The publish desk («میز انتشار», feature 43; D5 panel 3 without the hold-to-seal)
A new top-level page (in the navigation where «خروجی‌ها» lives: a tab or a segment of it named
«میز انتشار»; also reachable from the home pulse).
- `GET /api/v1/publish-desk` (new, contract §55.2; 404 on an older hub → the entry is hidden):
  `PublishDesk {ready: [DeskCard], queue: [DeskCard], done: [DeskCard]}`
  `DeskCard {output: string, title_fa: string, company: string, company_fa: string,
   order: string|null, group_fa: string|null,
   file: DeskFile, cover: DeskFile|null, files: int,
   kind: "reel"|"post"|"story"|"carousel", channel: "instagram",
   account: string|null, accounts: [string], route_ready: bool,
   caption: string|null, state: "ready"|"scheduled"|"publishing"|"published"|"failed"|"cancelled"|"waiting_setup",
   publish: SessionPublish|null, best: BestHour|null, mode: "ask"|"auto"|null, at: datetime}`
  `DeskFile {id: uuid, name: string, mime: string, size: int}`
- Three sections, in this order, each hidden while empty:
  1. **«آماده‌ی انتشار»**: one card per output: the media itself large (the poster / picture in its
     network frame ratio: reel 9:16 capped in height, post 1:1 or 4:5), the company's mark and name,
     «اینستاگرام | @account», the first two lines of the caption (tap = all of it), the suggested
     time («بهترین ساعت این حساب: 21:00» when `best.enough`, else nothing), and the action
     «تأیید و انتشار» (opens the existing publish sheet prefilled: file, cover, caption, account,
     best hour). Only the FIRST card's action is full gold; the others are outlined.
     `route_ready` false: no action; the quiet line «مسیر انتشار این شرکت را تیم فنی وصل میکند».
  2. **«در صف»**: `scheduled` / `publishing` cards, soonest first: a small poster, the time in Latin
     tabular digits («امشب 21:30»), «خودکار» when `publish.auto`, the quiet «لغو» of part A (§51)
     with its in-place confirm, and `publish.note_fa` when present.
  3. **«منتشرشده»** (the last 7 days): a small poster, when, the link («باز کن» opens outside),
     `failed` with its `note_fa` and a quiet «دوباره», `cancelled` as «لغو شد».
- Empty desk: one calm sentence «چیزی آماده‌ی انتشار نیست؛ هر خروجی تأییدشدنی همین‌جا می‌آید.»
- Pull to refresh; it re-reads after a publish or a cancel.

## C3. The six screen families, rebuilt premium (use each screen's `premium_fa` as the guide, the
rules of C0 as the law, and the owner's decisions above when the two differ)

1. **Home (`home`):** top: the «نوبت تو» row: a large gold count and under it the waiting items as
   cards that are answered right there (a session's question with its ready answers as in C2.2; a
   decision with its own action). Then the **office pulse (123)** as ONE row (~160dp instead of four
   tiles): «چند نفر کار میکنند» | «چند جلسه باز است» | «چند کار منتظر تو», each a number with a tiny
   24-hour sparkline when the hub gives a series (else just the number) and «تا HH:MM». Then the one-row
   command entry (C2.1). Then open sessions: each row a card that opens by M14, with three states
   only («در کار», «منتظر تو», «تمام»), no six-step chain and no percent bar. The three unnamed icons
   at the top get labels. Everywhere «جلسه», never «سشن».
2. **Session (`order-session-*`, `session-live-*`, `session-chat-*`):** C2.2.
3. **Output and «تأیید و انتشار» (`output`, `output-publish*`, `outputs`):** the output page opens
   with the thing itself (the media large, playable in place; a document's first lines), then the
   numbers row, then the text; the summary is not repeated. The decision bar carries «تأیید و
   انتشار» (full gold) and «اصلاح» (quiet; opens the composer of its session with the output quoted;
   an output of no session: the existing feedback path). «خوانده شد» and «بایگانی» are quiet. The
   publish sheet is the shared spring sheet: media preview, kind, account, caption, time (now / a
   time / «بهترین ساعت (21:00)»), the comment word, the JPEG line of part A, and «انتشار» in its
   decision bar. The outputs list: media cards with posters, «بی‌امتیاز» as a silver dot, filters
   collapsing into one bar on scroll.
4. **Working group (`playbook-*`, `v29-group`, `v29-groups`):** the sealed page opens with the member
   companies as tiles (state, last run, next run; a silver work line only while something runs) and
   each routine's last seven runs as dots; the definition (goal, rules, connections) folds under
   «تعریف کارگروه». Each member's settings are one grouped block: «انتشار خودکار» (switch, silver
   when on) with «بهترین ساعت، خودکار» and the fixed hour, «گوینده‌ی محتوا», «دفتر موضوع‌ها» (parts A1
   to A3 rebuilt in this look). The draft page's «مُهر کارگروه» lives in the decision bar with a
   one-line summary («۳ جایگاه | ۲ روال | ۱ اتصال»); one tap, no fingerprint. A member that stands
   still has its one-line reason and a quiet «راه بینداز».
5. **Notifications (`notifications*`, feature 133):** three levels only: **فوری** (red sign, rings),
   **تصمیم** (gold sign), **خبر** (silent: report, info, learning together). Top: a fixed section
   «از تو کاری میخواهد» (urgent and decision items not yet answered), each with its own action right
   there («تأیید», «ببین», the session's ready answers) and its deadline as a ring that empties;
   then the rest by day («امروز», «دیروز», the date). Rows are compact (about 72dp): level sign,
   title, one line, time; unread = a 2px gold edge only. Swipe = «خوانده شد» with a drawn tick and a
   haptic tick; the per-card «خوانده شد» button goes. Machine titles are said in Persian (the raw
   text one tap away). The filter is one bar: «همه | فوری | تصمیم | خبر». Notification settings keep
   their place but speak of the same three levels.
6. **Token treasury and accounts (`treasury*`, features 111, 112):**
   - `GET /api/v1/treasury/limits` (new, contract §55.3; 404 → this block is hidden and the old
     quota card stays):
     `Limits {accounts: [ClaudeAccount], waiting: bool, today: TodayMeter}`
     `ClaudeAccount {key: string, name_fa: string, state: "working"|"ready"|"full"|"off",
      utilization: number|null (0..1), window_fa: string|null, resets_at: datetime|null,
      observed_at: datetime|null}`
     `TodayMeter {spent: int, cap: int, share: number (0..), state: "calm"|"warm"|"near"|"full",
      resets_at: datetime, note_fa: string}`
   - **Two Claude accounts (112):** each account one ring: the share used in its middle (Latin
     tabular percent; «—» when unknown), its name under it («اکانت اصلی», «اکانت دوم»), and one line:
     `working` → «الان همین کار میکند», `ready` → «آماده», `full` → «پر است؛ {HH:MM} خالی میشود»
     (from `resets_at`, the owner's clock; a countdown «۲ ساعت و ۱۰ دقیقه دیگر»), `off` → «خاموش».
     The working one has the turning arc (M7) only while a call is live, else a still silver ring.
     `waiting` true: one amber line «هر دو اکانت پر است؛ کارها تا {HH:MM} در صف میمانند».
   - **Today's meter (111):** a horizontal meter of today's agent spend with three marks at 70%, 90%
     and 100%, the number («412K از 600K») in Latin tabular digits, `note_fa` under it, and when it
     resets. Colour by `state` (calm silver, warm amber at 70, near red-amber at 90, full red).
   - The month view keeps its chart but opens with the verdict sentence and one big number, the
     three small numbers in one row; digits follow C0.4; every number says when it was read.

## Deliverables and rules
- Both clients, the same design, the same Persian words. Add no dependency (web: no `npm run gen`,
  API types by hand as in `v47.ts`; Android: `HubFeature` / `gated()` for every new call).
- Mock / demo data for every new state; Android: Roborazzi screenshots for every rebuilt screen in
  day and night, re-recorded and LOOKED AT (read the PNG) before you report; web: Playwright specs for
  the command sheet, the session's waiting card and «الان» bar, the publish desk, the limits block,
  and the notifications' three levels; `npx tsc --noEmit -p .` and `npm run lint` clean.
- Run only the tests of what changed, plus (Android) `:app:assembleRelease` at the end.
- Do NOT commit, push, bump versions or edit `apps/CHANGELOG.md`; touch nothing outside your client's
  folder; never edit `docs/ops/`. No model name in comments or docs (the UI may say «Opus 5.5» where
  the hub's data says so). No fixed number of companies. A server is named by its company.
- Report at the end, briefly: what was built per section (C0 to C3), what was not and why, the
  tests run and their result, and the screenshot / spec files to look at.
