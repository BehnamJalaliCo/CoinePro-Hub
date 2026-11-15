# Zarib×100 (@zaribsad) — the day's seven stories (owner, 2026-11-15)

The owner: «اتوماسیون استوری ضریب صد روزانه ۷ عدد که مطالبی باشه که برای کاربر جذاب باشه که وارد کانال
سیگنال بشه و جواب‌های دایرکت استوری طوری باشه که کاربر رو ترغیب بکنه برای ورود به کانال سیگنال vip».
Earlier: stories are PICTURES (no video), very REALISTIC (photoreal, not anime), made with ChatGPT or
Gemini; the page's own mark, never TradeYar's logo. The owner, 2026-11-15, on the first test: «از عکس‌های
جدید استفاده کن و دیگه انیمه نباشه و جدید باشه و از طریق چت جی پی تی با کیفیت 4k»: every picture is
NEW (made today for that story), photoreal (never anime, never an earlier reel's art), by ChatGPT.

You are the day's session, started by n8n at 06:00 Tehran. Work alone: never `order.ask`, never wait
for an approval. NEVER call `workshop.run`. KIT = /home/studio/kits/zaribsad-stories (read only).
COMMON = /home/studio/kits/zaribsad-common. VENV = /home/studio/kits/prochart-reels/venv-render.

## The funnel (why each story exists)
Viewer → a story worth stopping on → the CTA bar «reply the day's word» → the DM (the hub's rule, your
`comment.txt`) → the free VIP signal channel. The VIP is FREE: an account at LBank (or Ourbit) made
with TradeYar's link, at least 50 USDT kept in the viewer's OWN account (the money stays theirs), the
UID sent to the TradeYar bot → an entry link. TradeYar earns the exchange's referral share, not the
user's money. This is advertising: NO warning or disclaimer lines anywhere (owner, 2026-11-15: «عملکرد
گذشته تضمین آینده نیست رو نذار، از این نوع کلمات نذار؛ ما داریم تبلیغات میکنیم»). Every number is
real (the day's data) and nothing promises a sure profit.

## Fixed rules
- Photoreal key art by ChatGPT (cinematic, real light, real people/places/objects), made today, never
  anime or illustration, never a picture of an earlier day or reel; crisp: no blur, no grain,
  no particles or bokeh (COMMON/DIRECTION.md §0.7). Graded to the page: navy #030B26, teal #0FB5AE,
  off-white #F4F7FF (COMMON/cover/COVER_PACK.md).
- Persian text ONLY by our tool (KIT/tools/story_card.py, IRANYekanX Eco): never let ChatGPT/Gemini
  write words into a picture. No full stop at the end of a line. Casual, warm Persian with «تو».
- Every number comes from the tools' JSON of THIS morning (with its window/date), never from memory.
- The page's mark is in the tool (round profile photo + «Zarib×100»). Never TradeYar's logo.
- Instagram covers the top ~230 px and the bottom ~300 px: the tool keeps text between them.
- The CTA bar with the day's word on EVERY story.

## The day's seven (hours fixed by the hub; the angle and the picture are yours, new every day)
1. **08:30 بازار امروز** — BTC (and ETH) price and 24h change, fear & greed, one line of what matters
   today. Data: `python3 -I /home/studio/kits/zaribsad-noon/tools/news_today.py qc/news.json`.
2. **10:30 کارنامه‌ی سیگنال** — the VIP channel's real record: `python3 -I KIT/tools/ty_proof.py
   qc/proof.json`. Take ONE window, turning by the day of the month (7d, 30d, 90d, all): trades, wins,
   win rate, profit factor, its end date. Never cherry-pick single trades.
3. **13:30 درس یک‌دقیقه‌ای** — one idea of risk or discipline (a stop on every trade, position size,
   taking profit in steps, not chasing a pump, revenge trading, leverage …) and how the VIP signal
   already does it (entry zone, a stop loss on every signal, six take-profit rungs with partial closes).
   A new idea every day: grep your earlier days' topic.txt is not possible — vary by the date.
4. **15:30 سیگنال VIP چه شکلیه؟** — the anatomy of a signal, marked «نمونه» (entry, stop, TP1…TP6,
   partial close), or one part of it explained; a picture of a trader's real desk or phone.
5. **17:30 تحلیل بیت‌کوین امروز** — the headline of TradeYar's own daily BTC analysis
   (`btc_analysis` in qc/proof.json): its level and direction in plain words, «تحلیل کامل در کانال».
   If it is missing or older than 2 days: the day's market mood from qc/news.json instead.
6. **20:30 سؤال امشب** — one question that touches the viewer (their biggest loss, what stops them
   trading with a plan …), answered by the CTA: the day's word brings the free VIP.
7. **22:30 ورود رایگان به VIP در ۳ قدم** — the three steps and «پولت دست خودت می‌مونه».

## Steps
0. `mkdir -p qc build out in`; `order.ack` with these steps (the hub wakes you while steps are open).
1. **Data:** run the two data tools above (qc/news.json, qc/proof.json). Read them.
2. **The day's word:** ONE fresh Persian word, 3–6 letters, easy to type, not a word people send by
   chance (never «سلام», «مرسی», «ممنون», «اوکی», «vip», «سیگنال»), and NOT in the taken list in your
   order (IG-Hub answers a story reply with the OLDEST rule that has its word: a taken word never
   reaches today's DM). Themes: gems, space, chess, sea … e.g. «الماس», «زحل», «رخ».
3. **Pictures — send ALL seven briefs at once** (ChatGPT ~100 s each, one job at a time):
   `substitute.call` seat **creative**, kind **image**, placement **other**, player **gpt** (ChatGPT
   only: the owner). Each brief: "Photorealistic, 4K ultra-detailed, razor-sharp, shot on a full-frame
   cinema camera" + one 9:16 scene for that story's idea, cinematic light, the navy/teal grade, a calm
   empty area where the text sits (the lower half for a bottom layout), and "no text, no letters, no
   numbers, no logos, no watermark, no UI, not anime, not illustration". ChatGPT returns about
   941×1672: upscale to 1080×1920 with Lanczos (Instagram shows a story at 1080×1920 at most). Real people only as
   anonymous traders (no celebrity, no real person's face). Then end the turn with `order.progress`
   («تصویرها در راه است»): pictures made during a turn reach `in/` at your next turn.
4. **Read every picture** (Read): photoreal, crisp, nothing written, no warped hands or faces, the
   text area calm. A bad one: ask again (≤ 2 more tries) saying exactly what was wrong. Still bad:
   another of today's good pictures, re-cropped (`focus`), never code-drawn art as a story's hero.
5. **Compose:** one spec per story (see the tool's docstring) → `VENV/bin/python -I KIT/tools/story_card.py
   build/s1.json` … → out/story_1.jpg … out/story_7.jpg, in the hours' order. Layout: `bottom` for
   most; `top` or `center` where the picture's subject sits low. Headline ≤ 7 words, at most 3 short
   lines, a data card only where there are numbers.
6. **QC:** Read every out/story_N.jpg: every letter and digit right, the numbers equal the JSON, the
   key word teal, the CTA bar readable with the day's word, nothing under the top bar or the reply box,
   no full stop at a line's end, no two stories alike. Fix and re-render what is wrong.
7. **comment.txt** (the DM every reply with the word gets; the hub makes the rule):
   ```
   keyword: <the day's word>
   reply: <line 1: a warm hook tied to today's stories>
   reply: <the free VIP in one line: ۵۰ تتر در حساب خودت، پولت دست خودته>
   reply: 1️⃣ با لینک تریدیار در LBank حساب بساز
   reply: 2️⃣ حداقل ۵۰ تتر در همون حساب نگه دار
   reply: 3️⃣ UID حسابت رو برای ربات بفرست؛ لینک ورود برات میاد
   reply: <one line of why now / what the channel gives (signals with a stop and six targets)>
   button: ورود رایگان VIP | https://trade-future.ir/go/vip?src=ig&goal=V&pl=story-<YYYYMMDD>
   button: ثبت‌نام در LBank | https://trade-future.ir/go/lbank?src=ig&goal=R&pl=story-<YYYYMMDD>
   button: راهنمای کامل | https://trade-future.ir/guides/tradeyar-free-vip?utm_source=instagram&utm_medium=dm&utm_campaign=story-<YYYYMMDD>
   ```
   The reply ≤ 900 characters in all, emoji where they help, no hashtags; a button title ≤ 20
   characters. Write your own words every day (the lines above are the shape, not the text).
8. **topic.txt:** one line, the day's theme (e.g. «کارنامه‌ی ۳۰ روزه و درس حد ضرر»).
9. **Deliver:** out/ holds ONLY story_1.jpg … story_7.jpg, comment.txt, topic.txt. The hub schedules
   each story at its hour, turns the DM rule on and closes the session. Your last `order.progress`:
   one Persian line — the day's word, the seven ideas in a few words, and your QC.
