# The sample reel — Claude Fable 5.2 (2026-11-18, by the hub's builder; never published, never sent to the owner)

The first reel of the LUMEN engine, made end to end with this kit's own steps, to set the bar and the rules.
Files: /home/Hub/sites/bjtech-sample/ (sample.mp4, cover.jpg, contact_sheet.jpg, word_times.json, timeline.json).

## Topic and facts (anthropic.com/claude/fable, read 2026-11-18)
- Claude Fable 5.2, «Our most capable model for technical work», announced **Nov 9, 2026**.
- $8 / 1M input tokens, $40 / 1M output (Fable 5.1: $10 / $50); cache reads $0.20.
- FrontierCode 2.0 (agentic coding): Fable 5.2 **49.1** (xhigh), Fable 5.1 32.4, Opus 5.5 45.5, GPT-6 Astra 42.8,
  Gemini 4 Carbon 41.1. AutomationBench (business workflows): Fable 51.4, Opus 42.5, Astra 41.4, **Carbon 53.9**
  (the honest twist: the reel says where the model is NOT first).
- Discovered Materials (quoted on the page): 13 phonon benchmark cases from **3.3 h to under 4 min** (~36x).
- «creates simulations, animations, and educational videos with sound in code» (the page's own words).
- Available in AWS, Google Cloud, Microsoft Foundry and the Claude API. Pillar `model`, look tr 0 (scan), mood 1.

## Script (134 words, Arlo, 59.6 s voice, 62.2 s with the end card)
The hook is the number (3 h → 4 min), the question by line 3 («از GPT-6 Astra و Gemini 4 Carbon هم بهتره؟»),
a fact every line, the twist (Carbon wins office automation), the payoff (which one, for what), the ending (the
price today, the verdict, the full circle: «همین ویدیو هم با کد ساخته شده»), the call to action («مدل»).

## Voice (speech.make path: api_speak, Arlo, no style)
- Take 1: 59.8 s, audio_qc 0 clicks / 0 cuts / 0 bursts; every line heard (sound match 0.948). Whisper wrote
  «کود» for «کد», «نهوم» for «نهم» (that IS how «نهم» is said) and digits for numbers: ASR habits, not errors;
  word_probe confirmed «نهم نوامبر» and «چهل و دو و هشت دهم».
- voice_seams pauses 0.40 → assemble → voice_final 59.57 s, −16.4 LUFS, 0/0/0.

## Build and QC (what was fixed — now rules of the stage)
- Round 1: a panel's title printed twice (a shadow offset leaking from the panel's lift into its text: fixed in
  PANEL and T()); the grid floor drew a hard band at the horizon (now its lines fade by depth); captions grew to
  three rows over the panels (now pages of two rows, clear of the right rail); «≈36×» flipped to «×36≈» (≈ was
  not seen as Latin: fixed); the price cards were empty for 3 s (both now show from the start with the old price;
  the new one lands on its word).
- Round 2: shots 7/10 → 8.5/10 average; the verdict shot's first 1.5 s held only its title (a lesson for the
  README: «nothing empty while a line is spoken»).
- Timeline: 10 shots, 24 beats, longest stretch 3.28 s. Render: 3,730 frames at 60 fps, 178 s with 2 workers
  (about 90 ms a frame). Mix −14.0 LUFS, true peak −1.7 dBTP; the file's own audio 0/0/0.
- Self-score 8.5/10. The strongest frames: the hook's clock running down and «≈36×», the spectral benchmark bars,
  «همین ویدیو = کد» with the edge glow. Weakest: the code-to-preview shot (a plain sine preview: a real mini scene
  drawn by the code would be stronger).

## Texts
caption.txt and comment.txt here (the DM gives the official comparison and pricing pages + the Telegram button).
