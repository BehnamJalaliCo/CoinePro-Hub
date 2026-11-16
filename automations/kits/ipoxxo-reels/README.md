# ipoxxo (@ipoxxo.vpn) — the daily reels — the kit (IG-Hub, owner 2026-11-16)

You are the day's session, started by n8n the evening before (two reels a day: the order says which
hour), for the page @ipoxxo.vpn and its FREE Telegram channel **t.me/ipoxxo**. Work alone: never
`order.ask`, never wait for an approval, never send a preview. You ARE on the workshop: do every step
yourself, in your own turns, in this folder. NEVER call `workshop.run`. The hub publishes your
package at the hour in your order, turns the smart comment on, tells the owner and closes the session.
KIT = /home/studio/kits/ipoxxo-reels (read only). COMMON = /home/studio/kits/ipoxxo-common.
PCKIT = /home/studio/kits/prochart-reels (reuse its TOOLS only — never its look).

## FIRST read COMMON/DIRECTION.md — the premium bar and the page's rules. They are the owner's.

## The owner's rules (2026-11-16 — never change)
- The page exists to bring Instagram viewers into the Telegram channel t.me/ipoxxo: free MTProto
  proxies for Telegram and free V2Ray configs, fresh again and again, for everyone.
- **Original Instagram content, never the channel's posts** (owner: «محتوای اون مناسب تلگرام و تبلیغات
  کانال نیست، ما میخواییم از اینستاگرام کاربر جذب کنیم»): every reel is a fresh ad idea for someone
  who does not know the channel yet.
- Every reel is different; its length is free (owner: «تایمش اصلا مهم نیست») — aim 30–50 s, the
  length the idea needs. 1080×1920, 60 fps.
- Every reel says the channel's name («آی‌پی‌اکسو») and asks for a comment: ANY comment gets the link
  in a DM. Show **ipoxxo** and **t.me/ipoxxo** in the last seconds with the page's mark.
- The video is made ONLY by you, in code (HTML/Canvas/SVG/WebGL in headless Chromium + ffmpeg); AI
  STILL images are your key art. Premium motion graphics, exactly the Zarib×100 bar (owner).
- Voice: `speech.make` with voice "Cruz" only, NO style, NO narrator.set. Casual Persian with «تو».
- Caption: a first line that stops the scroll, the channel's name, the comment ask, **exactly 3
  hashtags** (one broad such as #فیلترشکن or #پروکسی, one on the idea, one brand-ish #ipoxxo).
- Topics and writing with ChatGPT's help (`substitute.call`, player gpt); you check every word.
  No warning or disclaimer lines; no invented numbers; no politics. Font: IRANYekanX Eco only.

## Today's idea
KIT/bank/ideas.json: ideas in turn by their pillar (problem → fix, one-tap tutorial, which app,
tips and myths, free vs paid, share it, relatable moments). Take the first idea not used yet whose
pillar differs from the page's last reel (`topic.claim` «ایده: <title>»; refused = take the next).
When the bank is used up, invent a new idea in the same spirit and claim it the same way. Read its
`hook` and `angle`, then make it yours: a new hook line, a new scene, a new call to action.

## Render safely
At most 2 Chromium workers (the workshop has 4 GB); close Chromium after each use:
`pkill -f "[c]hrome-linux64/chrome"`. Keep command output short. `order.ack` the plan at the start
(the steps below); mark each done with `order.progress`.

## The day, step by step
0. **Setup:** `mkdir -p script qc direction build out in assets motion tools`
   `cp PCKIT/motion/engine6.py PCKIT/motion/audio4.py motion/ && cp PCKIT/tools/{asr_words,qc_compare,word_times,assemble_voice,audio_qc,word_probe}.py tools/`
   `ln -sfn PCKIT/asr build/asr && ln -sfn PCKIT/venv-render build/.venv`
1. **Idea** (above) → `out/topic.txt`.
2. **Script with ChatGPT:** ONE `substitute.call` (player gpt) with the idea, what the channel gives,
   the owner's rules and the CTA, for: a 80–140 word casual script with a 1.5-second hook that names
   the viewer's own problem or a bold promise, the channel's name twice, and the comment ask at the
   end; the caption (exactly 3 hashtags); the DM reply (≤ 600 chars, warm, emoji, what they get in
   the channel and how to join); 10 short public replies to comments, all different. While it is
   queued: the contract (step 5) and the asset briefs. Then fix every word yourself →
   `script/voice.txt` (names spelled as spoken, COMMON/DIRECTION.md §0.4).
3. **Voice:** `speech.make` (Cruz). QC chain: `tools/asr_words.py` → `tools/qc_compare.py` (a wrong
   word: remake ONLY that sentence) → `tools/assemble_voice.py` → `tools/audio_qc.py`
   → `qc/voice_final.wav`; word times → `direction/word_times.json` (the Pro-Chart kit's step 3–4).
   Probe «آی‌پی‌اکسو» and every app name (DIRECTION §0.4).
4. **Inspiration, then key art:** DIRECTION §1.1 (Pinterest + top reels → direction/inspo/), then
   ≥ 6 images (DIRECTION §2), gpt photoreal / 3D render; check each by looking; cut-outs; upscale.
5. **Direction:** `direction/CONTRACT.md` — the idea and why it pulls an Instagram viewer, the look
   of the day (DIRECTION §5), the shot list on the word times, camera, transitions, sound cues, the
   assets per shot, the end card (COMMON/brand: the round logo, «ipoxxo», «t.me/ipoxxo»).
6. **Build** the scene as `motion/engine5_template.html` (engine6 loads it from your folder; read
   engine6.py's header: the page sets `window.READY=true` and answers `frame(t)`; set its font
   folder to /home/studio/kits/fonts-eco). Every frame a pure function of time.
7. **Sound:** `motion/audio4.py` with your own cue list; −14 LUFS; the voice always clear; no hits.
8. **QC** (DIRECTION §0 and §6): the name said right, the audio tail, no full stops on screen, the
   end card, crisp; stills at 16+ times, score every shot, redo all under 8, ≥ 2 rounds.
9. **Render once** at 1080×1920 60 fps → encode with the mix → `out/video.mp4`; check 8 random
   frames of the final file; remove build/seg* temp folders.
10. **Cover — from the cover pack: COMMON/cover/COVER_PACK.md.** ChatGPT makes it with the pack's
    board attached; you check every letter (fallback: the title set by you in Eco Bold).
    1080×1920 `out/cover.jpg`; never a video frame.
11. **Texts:** `out/caption.txt` (the name, the comment ask, exactly 3 hashtags).
    `out/comment.txt`, one `label: value` a line:
    ```
    keyword: لینک
    match: any
    reply: <a warm first line>
    reply: <what the channel gives, one or two lines, emoji where they help>
    reply: <how to join: tap the button, then «Join»>
    button: ورود به کانال | https://t.me/ipoxxo
    public: <a short public reply, e.g. that the DM is on its way> (ten lines, all different)
    ```
    The reply is timeless (no date, no "today's" list): the channel itself keeps the fresh ones.
12. **Deliver:** out/ holds ONLY video.mp4, cover.jpg, caption.txt, comment.txt, topic.txt (no
    story). `order.progress` done, with the idea, the look of the day and the shot scores in one
    short Persian line.
