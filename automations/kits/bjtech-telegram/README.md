# bjtech-telegram — the Telegram channel of @behnamjalali.tech (t.me/behnamjalali_tech, «Ai & TECH»)

The owner (2026-11-19): «فعالیت به شدت قوی … با محتوای مخصوص خود تلگرام». A Persian tech & AI channel that
people keep unmuted because every post is worth opening: made FOR Telegram (long text, code you can copy,
tables, polls, voice), never an Instagram reel pasted in. You make the day's package; the hub checks it, keeps
each post for its hour and sends it to the channel with the page's bot. You never post anything yourself.

COMMON = /home/studio/kits/bjtech-common (brand/config.json: every link; DIRECTION.md: the look; fonts).
KIT = this folder. REELS = /home/studio/kits/bjtech-reels (sources.md: the official sources). PY =
/home/studio/kits/prochart-reels/venv-render/bin/python (Chromium for the cards).

## The owner's rules (never change)
- **Made for Telegram.** A post is native: a 3-minute read, copyable commands, a table, a poll, a voice note.
  The page's own reels/stories of the last days are in your order: never their copy; the same news only with a
  Telegram angle (deeper, practical, with the numbers and the links).
- **True.** Every fact, number, price and date from the official source, checked today (the vendor's own page,
  docs, changelog, GitHub repo, paper). The source link is IN the post (links are welcome in Telegram text).
  No rumours, no «leaks», no politics, sanctions, ways around a country's filtering, medical or financial advice.
- **Never a repeat (HARD).** Your order lists every topic this channel has had or has queued. A post's `topic`
  must differ from all of them and from each other (the same subject with another title is a repeat; real
  new news about the same thing is not). The hub refuses a repeated topic.
- **Persian, warm and clear** (the page's voice: a friend who knows tech), English only for names, commands
  and code. Persian digits in prose; Latin digits inside code, prices with $ and model names as written.
- **Never silent on facts:** if a day has no real news, the brief is «۵ چیزی که این هفته باید بدونی» from the
  week's verified items, never invented news.

## The daily rhythm (Tehran time; 8 posts, at least 15 minutes apart, in this order)
| at | type | what | shape |
|---|---|---|---|
| 08:30 | `brief` | ☕️ «صبحانه‌ی هوش مصنوعی»: the 5–7 most important AI/tech items of the last 24 h | text, ≤ 4096; each item: bold title, 1–2 lines «یعنی چه برای تو», `<a href>` to the official source; buttons: اینستاگرام · یوتیوب |
| 10:30 | `tool` | 🛠 «ابزار/ریپوی روز»: one open-source tool or repo, tried in your head step by step | photo card (`tg_card.py`, 1080×1350) + caption, then a text part: what it does, who it is for, install lines in `<pre><code class="language-bash">`, a first example; buttons: GitHub · مستندات |
| 12:30 | `prompt` | 🧠 «پرامپت روز»: 3–5 ready prompts for one real task (Persian or English as fits), each in `<code>` (one tap copies) | text; **Wednesdays**: a PDF cheat sheet instead (`document`, made with `tg_card.py --pdf`) |
| 14:30 | `poll` | 📊 a poll on the day's subject (which tool do you use, which model wins …) or a quiz (a real fact with its explanation) | poll, anonymous, 2–6 options |
| 16:30 | `table` | ⚖️ «مقایسه»: two to four models/tools side by side (price, context, speed, best for), numbers from the official pages | photo of a rendered table (or an album of 2) + caption with the verdict and the sources |
| 18:30 | `clip` / `longread` | 🔍 «عمیق‌تر»: on a day of a page reel (at most 3 a week) the reel's video re-cut for Telegram (`tg_media.sh clip`) with a caption that goes deeper than the reel; other days a 2–3 part thread (photo + texts) explaining one thing well. **Fridays**: 📚 «خواندنی آخر هفته», the week's long read (parts: photo + up to 3 texts) | video ≤ 48 MB / parts |
| 20:30 | `voice` | 🎙 «یک دقیقه هوش مصنوعی»: one idea explained in 45–90 s by the page's narrator (Arlo) | voice (OGG/Opus) + caption: the 3 key points and the source |
| 22:00 | `tip` | 💡 «نکته‌ی شب»: one practical tip, a myth vs fact, or a reader's question answered | text + buttons: اینستاگرام · یوتیوب |
Breaking news (the hub's watcher, its own order): one `breaking` post at once, see «Breaking».

Every post ends with the channel's signature line (its own line): `🆔 @behnamjalali_tech`. The links come only
from COMMON/brand/config.json (`telegram`, `instagram`, `youtube`): never typed by hand.

## Telegram's HTML (what the hub accepts; anything else is refused)
`<b> <strong> <i> <em> <u> <ins> <s> <strike> <del> <code> <pre> <pre><code class="language-bash">
<a href="https://…"> <blockquote> <blockquote expandable> <tg-spoiler> <span class="tg-spoiler">`. Nothing else
(no `<br>`, `<p>`, `<div>`, `<h1>`, no `<img>`): a new line is a new line. Every tag closed, in order. In text,
`&` is `&amp;`, `<` is `&lt;`, `>` is `&gt;`. Links https only. The VISIBLE text (tags removed) of a text message
is at most 4096 characters, of a caption 1024 (Telegram counts UTF-16 units; an emoji counts 2): `tg_check.py`
counts it. Use `<blockquote expandable>` for a long quote or a transcript.

## telegram.txt (out/; JSON in a .txt file — the workshop's runner delivers .txt, never .json; written LAST,
## after every file it names)
```json
{"posts": [
  {"at": "08:30", "type": "brief", "topic": "صبحانه‌ی هوش مصنوعی: GPT-6.2، Gemini 4 Neon و …",
   "text": "☕️ <b>صبحانه‌ی هوش مصنوعی</b> …\n\n🆔 @behnamjalali_tech",
   "buttons": [[{"text": "اینستاگرام", "url": "https://www.instagram.com/behnamjalali.tech"},
                {"text": "یوتیوب", "url": "https://www.youtube.com/@behnamjalali-tech"}]]},
  {"at": "10:30", "type": "tool", "topic": "Codex CLI: ایجنت کدنویسی OpenAI در ترمینال",
   "parts": [{"photo": "tg_02_card.jpg", "text": "🛠 <b>ابزار روز: Codex CLI</b> …"},
             {"text": "<pre><code class=\"language-bash\">npm i -g @openai/codex</code></pre> …",
              "buttons": [[{"text": "GitHub", "url": "https://github.com/openai/codex"}]]}]},
  {"at": "14:30", "type": "poll", "topic": "نظرسنجی: کدوم ایجنت کدنویسی؟",
   "poll": {"question": "ایجنت کدنویسی اصلیت کدومه؟", "options": ["Claude Code", "Codex CLI", "Gemini CLI", "هنوز هیچ"]}},
  {"at": "20:30", "type": "voice", "topic": "یک دقیقه: پنجره‌ی متن یک میلیون توکنی یعنی چه",
   "voice": "tg_07_voice.ogg", "text": "🎙 <b>یک دقیقه هوش مصنوعی</b> …"}
]}
```
A post is ONE message (its fields at the post's level) or `parts`: up to 4 messages sent in a row (a thread).
A message has text and/or exactly ONE of: `photo` (JPEG/PNG ≤ 10 MB), `photos` (an album of 2–10, no
buttons), `video` (MP4 ≤ 48 MB), `voice` (OGG/Opus), `document` (PDF), `poll` ({question ≤ 300, options 2–10
each ≤ 100, `quiz`: the right option's index from 0 with an `explanation` ≤ 200, or `multiple`: true}).
With a file, `text` is its caption (≤ 1024 visible). Optional: `buttons` (link buttons only: up to 4 rows of up
to 3 {text, url}; only on the LAST message of a post; never on an album or a poll), `preview` (a text
message's link preview: false = off (the default), true, or the https link to preview), `silent`: true (no
notification; the 22:00 tip and night posts), `above`: true (a photo/video's caption above it).
Every post: `at` ("HH:MM" Tehran, in order, ≥ 15 min apart, not before the hour in your order), `type` (brief,
tool, prompt, poll, table, clip, voice, tip, longread, breaking, post) and `topic` (one Persian line ≤ 300: what
it is about; the no-repeat list is made of these). File names: `tg_<NN>_<what>.<ext>` (Latin, no spaces).

## Tools
- `PY -I KIT/tools/tg_card.py <page.html> <out.jpg> [--size 1080x1350]` — a card, a table or a cheat sheet
  from your own HTML (start from `KIT/templates/card.html` / `table.html`: the page's navy look, Estedad and
  Geist, RTL locked). `--pdf <out.pdf>` makes an A4 PDF from the same HTML. Read every picture at full size:
  every Persian letter, no overflow, no English word flipped.
- `bash KIT/tools/tg_media.sh voice <in.wav|ogg|mp3> <out.ogg>` — OGG/Opus mono 48 kHz (Telegram's voice);
  `bash KIT/tools/tg_media.sh clip <in.mp4> <out.mp4>` — H.264 ≤ 48 MB, faststart (the Bot API's limit).
- Voice: `speech.make` with the page's narrator **Arlo** (no style), ZERO TOLERANCE as the reels kit
  (REELS/README.md, «Voice»): take, the converted file and the final file 0/0/0 with audio_qc, else a new take.
- `python3 -I KIT/tools/tg_check.py out/` — THE package check (the hub's own rules: HTML, lengths, buttons,
  polls, files, times, signature). Deliver only when it says `OK`.

## The day, step by step (`order.ack` these steps; `order.progress` each one)
1. Read your order: the first hour, the channel's topics already used, the page's recent reels.
2. Research: today's verified items (REELS/sources.md: the vendors' own news pages, changelogs, GitHub);
   NOTES.md keeps each item's official link and the numbers you will use.
3. Plan the 8 posts in the rhythm above (Friday: the long read; Wednesday: the PDF). Each a different topic.
4. Write every text in Telegram's HTML; make the cards/tables (`tg_card.py`), the voice note, the clip.
5. `tg_check.py out/` until OK; read every picture again at full size.
6. Write `out/telegram.txt` last. `order.progress` done with the 8 topics.

## Breaking (an order from the hub's breaking-news watcher)
Check the news on the vendor's own page first: not real, not new or not important → only `out/skip.txt` with
the reason. Else ONE post, `"type": "breaking"` (no `at`: it goes out at once): the official picture (the
vendor's own launch image, as a `photo`; else a `tg_card.py` card with the name) and a caption ≤ 1024: «🔴 فوری»,
what happened in 2–4 Persian lines, what it means for the reader, the price/availability if official, the
source as `<a href>`; a button «منبع رسمی» to the same page; the signature line. Be fast: under 20 minutes.

## Where things are
- The hub's rules: apps/api/src/hq_api/domain/tg_posts.py (check, queue, the minute tick); this kit's
  tg_check.py is the same rules for you, before delivery.
- The channel: t.me/behnamjalali_tech (title «Ai & TECH»); the bot posts as an admin of it.
