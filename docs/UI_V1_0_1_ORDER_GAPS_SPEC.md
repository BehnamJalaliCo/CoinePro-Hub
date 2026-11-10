# Update 1.0.1, part A: the UI of the reels order's seven gaps (Android and web, the same on both)

The hub side is done and committed (contract `contracts/HQ_CORE_API_v1.md` §47 to §53; OpenAPI
`apps/api/openapi/hq-api.v1.json`, regenerated; tests `apps/api/tests/test_w20_order_gaps.py`).
The owner reads Persian on a phone: short, plain, no technical word, no hostname, no English
error text. Follow the existing screens' design language (the «دیوان» tokens) and each client's
own conventions; do not restructure a screen (a later pass rebuilds the look), add to it.

Every new call must tolerate an older hub (404/405 on a new route = the feature is simply not
shown; a missing new field = its default).

## 1. The ledger of topics («دفتر موضوع‌ها»), contract §47.4
Where: the working group's page, under each member company (beside its standing-publish row).
- A row «دفتر موضوع‌ها» with the counts («۴۲ موضوع · ۴۰ نمونه»; empty: «هنوز چیزی ثبت نشده») opens the ledger
  (a sheet on Android, a dialog/panel on web).
- The ledger: a search field; two filters «موضوع‌ها» / «نمونه‌ها»; rows newest first: the title, the
  day (the app's own Jalali date format), a quiet source word: `claim` «ثبت کارمند», `package` «از
  بسته‌ی منتشرشده», `owner` «افزوده‌ی شما»; a reference row shows its link (opens outside).
  «بیشتر» loads the next page (`next_cursor`).
- Add: one field «این را قبلاً گفته‌ایم…» + «افزودن» (kind = the active filter; a reference needs
  its link). `409 topic_taken`: show the response's `message_fa` under the field.
- Free a line: a quiet «آزاد کن» on a row, confirmed in place («دوباره قابل ساخت میشود»).

API:
- `GET /api/v1/groups/{key}/members/{code}/topics?kind=&q=&limit=&cursor=` →
  `{items: [TopicEntry], topics: int, references: int, next_cursor: string|null}`
- `TopicEntry {id: uuid, kind: "topic"|"reference", title_fa, url: string|null, at: datetime,
  by: string, source: "claim"|"package"|"owner", work_ref: string|null, output: string|null}`
- `POST` same path `{kind?, title_fa?, url?}` → `201 TopicEntry` | `409` problem
  `{code: "topic_taken", message_fa, fields: {title_fa, recent}}` | `422`
- `DELETE …/topics/{id}` → `200 TopicEntry`

## 2. The company's narrator («گوینده‌ی محتوا»), contract §48
Where: the working group's member row area (beside the ledger row) AND the company's own page
if it has a natural settings place; one shared component.
- Row «گوینده‌ی محتوا»: not set → «تنظیم نشده؛ هر بار مدل انتخاب میکند»; set → «Charon · آرام و مطمئن».
- Tapping opens a picker: the voices (`voices[]`: name, gender «زن»/«مرد», `trait_fa`), one chosen;
  a text field «سبک گفتن» (≤ 500, e.g. «آرام و مطمئن، مثل گوینده‌ی خبر»); «ثبت».
- `aistudio == "signed_out"`: one quiet line «گوینده‌ی هاب از حسابش بیرون افتاده؛ یک بار ورود شما لازم
  است.» (the only owner step that exists here). `unknown` / `signed_in`: nothing.

API: `GET /api/v1/companies/{code}/narrator` → `Narrator {company, set: bool, voice, style_fa,
by: string|null, updated_at: datetime|null, voices: [{name, gender: "female"|"male", trait_fa}],
aistudio: "signed_in"|"signed_out"|"unknown"}`; `PUT` same path `{voice, style_fa?}` → `Narrator`
(`422` → `message_fa`).

## 3. The best hour («بهترین ساعت»), contract §49
- Standing publish settings of a member (where the hour `at` is edited today; also at the seal
  and at «به شرکت دیگر بده»): a switch «بهترین ساعت، خودکار». Under it, from
  `GET /api/v1/companies/{code}/best-hour?account=`:
  - `enough: true` → «بهترین ساعت این حساب: ۲۱:۰۰» and `note_fa` as a quiet second line;
  - `enough: false` → `note_fa`, then «تا آن وقت: ساعت ثابت شما» (when `at` is set) or «تا آن وقت:
    همان لحظه‌ی آماده شدن».
  The fixed hour field stays (it is the fallback).
- A member row whose `publish.best` is true says «انتشار خودکار · بهترین ساعت» (with the hour when known).
- The publish sheet's «زمان»: when `PublishPanel.best` is present, a choice «بهترین ساعت (۲۱:۰۰)» that
  sends `scheduled_at = best.at`.

API: `BestHour {account, hour: "HH:MM"|null, at: datetime|null, enough: bool, posts: int,
days: int, basis: "likes_comments", note_fa, read_at: datetime|null}`;
`MemberPublish` gains `best: bool`; `PUT /api/v1/groups/{key}/members/{code}/publish` body gains
`best?: bool` (send it with the others); the seal's and the apply's `publish` object too;
`PublishPanel.best: BestHour|null`.

## 4. A standing routine from one sentence («روال دائمی» / «کارمند ۲۴ ساعته»), contract §50
Where: the session (order) screen.
- The session's routines (`OrderReport.routines`, newest first) as a small section «روال‌های دائمی»:
  each row `when_fa` + `preview_fa`, its next run («نوبت بعد: …», `next_at`), a switch on/off
  (`POST /api/v1/automations/{ref}/state {state: "on"|"off"}`), `note_fa` when present.
  Hidden while the list is empty.
- An action «روال دائمی» in the session's actions (where «کارگروه از این جلسه» is): a small sheet with
  one sentence field (placeholder «مثلاً: هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده») and
  «بساز». Success: the sheet closes and the new row is there. `422`: show `message_fa` under the
  field, keep the text.

API: `POST /api/v1/routines {sentence_fa, company?, order?}` (send `order` = the session's ref;
header `Idempotency-Key`) → `201 SessionRoutine {ref, company, sentence_fa, when_fa, preview_fa,
state: "proposed"|"on"|"off", next_at, last_run_at, runs, order, note_fa}`.

## 5. Cancelling a scheduled post («لغو»), contract §51
Where: every list of publishes (the session's `publishes`, the output page's `PublishPanel.publishes`).
- A row whose `state` is `scheduled` or `publishing` and has a `job` gets a quiet «لغو». It asks
  once in place («این انتشار لغو شود؟» · «لغو کن» / «نه»), then
  `POST /api/v1/publishes/{job}/cancel` → `SessionPublish`; the row is replaced by the answer
  (re-read the panel/report too).
- New state `cancelled`: the row reads «لغو شد» (quiet, no link). A row with `note_fa` shows it
  under the row («در حال لغو», «لغو انجام نشد (…)»).
- `409 not_cancellable`: show its `message_fa` on the row.

## 6. JPEG, contract §52
No control. In the publish sheet, when the chosen picture (or the cover) is not a JPEG (its
mime is `image/png`, `image/webp`, `image/heic`, or its name ends with one of those), one quiet line
under it: «این تصویر هنگام انتشار خودکار به JPEG تبدیل میشود.»

## 7. Effort, contract §53
Where an output shows how it was made (`produced_with`), and in the session's live work row of a
workshop turn if the model is shown there: «ساخت: Opus 5.5 · بیشترین دقت». `produced_with.model`
(`claude-opus-5-5` → the app's existing model label) and `produced_with.effort`: `low` «کم»,
`medium` «متوسط», `high` «زیاد», `xhigh` «خیلی زیاد», `max` «بیشترین دقت». Absent: nothing.

## Rules of the repository that apply (from CLAUDE.md and the handoff)
- Never write a fixed number of companies anywhere. A server is named by its company, never a hostname.
- Never print a secret. Free and open-source libraries only; add no dependency.
- Do NOT commit, push, bump versions or edit `apps/CHANGELOG.md`, and touch nothing outside your
  client's folder (`apps/android/` or `apps/web/`). Never edit `docs/ops/`.
- No model name in code comments or docs. Comments in English, plain; user-facing text Persian.
- Demo/mock data must cover every new state so screenshots / e2e show it.
