# -*- coding: utf-8 -*-
"""DotCoin long video: build motion/engine.html (data + fonts + assets + chapter scenes).

Timing per chapter: voice/chNN.times.json (tools/word_times.py output on the chapter's final voice) when
present, else an estimate (2.45 words/s, 0.35 s between sentences) for the design stills.
usage: PY -I motion/build.py
"""
import base64
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FD = "/home/studio/kits/fonts-pro/"
CARD = 2.6          # the chapter card before the voice (chapters 1..)
VO0 = 0.35          # the hook starts at once
TAIL = 1.1         # after a chapter's last word (the last 0.55 s is the wipe to the next card)
END_HOLD = 3.6      # the end card after the last word
RATE, GAP = 2.45, 0.35

FONTS = {"YKE": "IRANYekanXFaNum-ExtraBlack.ttf", "YKK": "IRANYekanXFaNum-Black.ttf", "YKH": "IRANYekanXFaNum-Heavy.ttf",
         "YKX": "IRANYekanXFaNum-ExtraBold.ttf", "YKB": "IRANYekanXFaNum-Bold.ttf", "YKD": "IRANYekanXFaNum-DemiBold.ttf",
         "YKM": "IRANYekanXFaNum-Medium.ttf", "YKR": "IRANYekanXFaNum-Regular.ttf", "YKL": "IRANYekanXFaNum-Light.ttf",
         "YLB": "IRANYekanX-Bold.ttf", "YLK": "IRANYekanX-Black.ttf", "ANT": "Anton-Regular.ttf", "BEB": "BebasNeue-Regular.ttf"}


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def small_png(path, size):
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def estimate(sents, vo):
    out, t = [], vo
    for s in sents:
        words = s["v"].split()
        dur = len(words) / RATE
        tot = sum(len(w) for w in words)
        ws, acc = [], t
        for w in words:
            d = dur * len(w) / tot
            ws.append({"w": w, "s": round(acc, 3), "e": round(acc + d * 0.92, 3)})
            acc += d
        out.append({"s": round(t, 3), "e": round(t + dur, 3), "words": ws})
        t += dur + GAP
    return out


def real(path, vo):
    wt = json.load(open(path, encoding="utf-8"))
    out = []
    for ln in wt["lines"]:
        ws = [{"w": w["w"], "s": round(w["s"] + vo, 3), "e": round(w["e"] + vo, 3)} for w in ln["words"]]
        out.append({"s": round(ln["start"] + vo, 3), "e": round(ln["end"] + vo, 3), "words": ws})
    return out, wt.get("duration")


def main():
    spec = json.load(open(os.path.join(ROOT, "script/chapters.json"), encoding="utf-8"))
    chs = []
    for c in spec["chapters"]:
        i = c["id"]
        vo = VO0 if i == 0 else CARD
        tp = os.path.join(ROOT, f"voice/ch{i:02d}.times.json")
        voice_dur = None
        if os.path.exists(tp):
            timing, voice_dur = real(tp, vo)
            if len(timing) != len(c["s"]):
                sys.exit(f"chapter {i}: {len(timing)} timed lines for {len(c['s'])} sentences")
        else:
            timing = estimate(c["s"], vo)
        sent = []
        for s, tm in zip(c["s"], timing):
            sent.append({**tm, "h": s.get("h", ""), "k": s.get("k", "")})
        last = sent[-1]["e"]
        if voice_dur:
            last = max(last, vo + voice_dur - 0.15)
        end = last + (END_HOLD if i == len(spec["chapters"]) - 1 else TAIL)
        chs.append({"id": i, "card": c["card"], "en": c["en"], "yt": c["yt"], "vo": vo,
                    "card_end": CARD if i else 0.0, "end": round(end, 3), "sent": sent})
    data = {"chapters": chs}
    faces = "".join(f"@font-face{{font-family:'{k}';src:url(data:font/ttf;base64,{b64(FD + v)}) format('truetype');}}"
                    for k, v in FONTS.items())
    assets = {
        "ethc": small_png(os.path.join(ROOT, "assets/logo/eth-glyph-colored.png"), 600),
        "logo": small_png(os.path.join(ROOT, "assets/logo/logo_round.png"), 360),
        "btc": "data:image/svg+xml;base64," + b64(os.path.join(ROOT, "assets/logo/bitcoin.svg")),
    }
    html = open(os.path.join(ROOT, "motion/scene.html"), encoding="utf-8").read()
    chapters_js = open(os.path.join(ROOT, "motion/chapters.js"), encoding="utf-8").read()
    for key in ("/*FONTFACES*/", "/*DATA*/", "/*ASSETS*/", "/*CHAPTERS*/"):
        assert key in html, key
    html = (html.replace("/*FONTFACES*/", faces).replace("/*DATA*/", json.dumps(data, ensure_ascii=False))
            .replace("/*ASSETS*/", json.dumps(assets)).replace("/*CHAPTERS*/", chapters_js))
    open(os.path.join(ROOT, "motion/engine.html"), "w", encoding="utf-8").write(html)
    json.dump(data, open(os.path.join(ROOT, "build/timeline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    tot = sum(c["end"] for c in chs)
    print("engine.html built;", " ".join(f"ch{c['id']}={c['end']:.1f}s" for c in chs), f"total={tot:.1f}s ({tot / 60:.2f} min)",
          "real" if all(os.path.exists(os.path.join(ROOT, f"voice/ch{c['id']:02d}.times.json")) for c in chs) else "ESTIMATED")


if __name__ == "__main__":
    main()
