# -*- coding: utf-8 -*-
"""DotCoin long video, engine v2: build motion/engine.html from script/chapters.json (sentences with their
shots), the chapter voices' word times, the fonts, the pictures and the scene library.

Each sentence of a chapter carries `shots`: [{type, p:{…}, w?: a word of the sentence the shot starts on,
tr?: cut|whip|zoom|wipe|slam|flash|push, cam?: push|pull|pan-l|pan-r|rise|tilt|crash|static, bgk?:
black|mustard|paper|content}]. A chapter (from the second) opens on its card (the re-hook). The builder
places every shot on the voice's real times and refuses a cut the retention rules forbid: a shot longer
than MAX_SHOT seconds, or a scene type the library does not have. It writes build/timeline.json (every
shot and its transition: the sound's cues).
usage: PY -I motion/build2.py [--estimate]
"""
import base64
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FD = "/home/studio/kits/fonts-pro/"
CARD, VO0, TAIL, END_HOLD = 2.6, 0.3, 0.9, 3.4
RATE, GAP = 2.45, 0.35
MAX_SHOT = 8.5
TRS = ["whip", "slam", "zoom", "wipe", "push", "flash"]
CAMS = ["push", "pan-l", "pull", "pan-r", "rise", "tilt"]
FONTS = {"YKE": "IRANYekanXFaNum-ExtraBlack.ttf", "YKK": "IRANYekanXFaNum-Black.ttf", "YKH": "IRANYekanXFaNum-Heavy.ttf",
         "YKX": "IRANYekanXFaNum-ExtraBold.ttf", "YKB": "IRANYekanXFaNum-Bold.ttf", "YKD": "IRANYekanXFaNum-DemiBold.ttf",
         "YKM": "IRANYekanXFaNum-Medium.ttf", "YKR": "IRANYekanXFaNum-Regular.ttf", "YKL": "IRANYekanXFaNum-Light.ttf",
         "YLB": "IRANYekanX-Bold.ttf", "YLK": "IRANYekanX-Black.ttf", "ANT": "Anton-Regular.ttf", "BEB": "BebasNeue-Regular.ttf"}


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def picture(path, size):
    from PIL import Image
    im = Image.open(path)
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    if im.mode == "RGBA":
        im.save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    im.save(buf, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


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
    return out, None


def real(path, vo):
    wt = json.load(open(path, encoding="utf-8"))
    out = []
    for ln in wt["lines"]:
        ws = [{"w": w["w"], "s": round(w["s"] + vo, 3), "e": round(w["e"] + vo, 3)} for w in ln["words"]]
        out.append({"s": round(ln["start"] + vo, 3), "e": round(ln["end"] + vo, 3), "words": ws})
    return out, wt.get("duration")


def word_at(sent, sub):
    n = lambda x: re.sub(r"[؟?:،؛.!«»]", "", x.replace("‌", ""))
    for w in sent["words"]:
        if n(sub) and n(sub) in n(w["w"]):
            return w["s"]
    return None


def scene_types():
    src = open(os.path.join(ROOT, "motion/scenes2.js"), encoding="utf-8").read()
    custom = os.path.join(ROOT, "motion/custom.js")
    if os.path.exists(custom):
        src += open(custom, encoding="utf-8").read()
    return set(re.findall(r"SCN\.([a-z0-9_]+)\s*=", src))


def main():
    spec = json.load(open(os.path.join(ROOT, "script/chapters.json"), encoding="utf-8"))
    types = scene_types()
    problems, chs, cues = [], [], []
    n_ch = len(spec["chapters"])
    for c in spec["chapters"]:
        i = c["id"]
        vo = VO0 if i == 0 else CARD
        tp = os.path.join(ROOT, f"voice/ch{i:02d}.times.json")
        timing, vdur = real(tp, vo) if (os.path.exists(tp) and "--estimate" not in sys.argv) else estimate(c["s"], vo)
        if len(timing) != len(c["s"]):
            sys.exit(f"chapter {i}: {len(timing)} timed lines for {len(c['s'])} sentences")
        last = timing[-1]["e"]
        if vdur:
            last = max(last, vo + vdur - 0.15)
        end = round(last + (END_HOLD if i == n_ch - 1 else TAIL), 3)
        shots = []
        if i > 0:
            shots.append({"type": "chapter", "t0": 0.0, "bgk": "mustard", "cam": "static", "tr": "cut", "nochrome": True, "si": 0,
                          "p": {"n": i, "title": c.get("card", ""), "en": c.get("en", ""), "hook": c.get("hook", "")}})
        k = 0
        for si, (s, tm) in enumerate(zip(c["s"], timing)):
            lst = s.get("shots") or [{"type": "kinetic", "p": {"text": s.get("h") or s["v"], "key": s.get("k", "")}}]
            for j, sh in enumerate(lst):
                if sh["type"] not in types:
                    problems.append(f"ch{i} s{si}: no scene type {sh['type']}")
                if j == 0:
                    t0 = 0.0 if (i == 0 and si == 0) else max(vo if si == 0 else 0, tm["s"] - 0.12)
                else:
                    w = word_at(tm, sh.get("w", "")) if sh.get("w") else None
                    t0 = (w - 0.1) if w is not None else tm["s"] + (tm["e"] - tm["s"]) * j / len(lst)
                shots.append({**sh, "t0": round(t0, 3), "si": si, "tr": sh.get("tr") or TRS[k % len(TRS)],
                              "cam": sh.get("cam") or CAMS[k % len(CAMS)], "bgk": sh.get("bgk") or "black", "p": sh.get("p") or {}})
                k += 1
        shots.sort(key=lambda x: x["t0"])
        for a, b in zip(shots, shots[1:] + [None]):
            a["d"] = round((b["t0"] if b else end) - a["t0"], 3)
            if a["d"] > MAX_SHOT:
                problems.append(f"ch{i} s{a['si']} {a['type']}: {a['d']:.1f} s on one layout (max {MAX_SHOT}): split it")
            if a["d"] < 0.6:
                problems.append(f"ch{i} s{a['si']} {a['type']}: only {a['d']:.2f} s")
        cues += [{"ch": i, "t": s["t0"], "tr": s["tr"], "type": s["type"]} for s in shots if s["t0"] > 0]
        sent = [{**tm, "h": s.get("h", ""), "k": s.get("k", "")} for s, tm in zip(c["s"], timing)]
        chs.append({"id": i, "card": c.get("card", ""), "en": c.get("en", ""), "yt": c.get("yt", ""), "vo": vo,
                    "card_end": CARD if i else 0.0, "end": end, "energy": c.get("energy", 0.9), "sent": sent, "shots": shots})
    data = {"chapters": chs, "palette": spec.get("palette") or {}}
    faces = "".join(f"@font-face{{font-family:'{k}';src:url(data:font/ttf;base64,{b64(FD + v)}) format('truetype');}}"
                    for k, v in FONTS.items())
    assets = {"logo": picture(os.path.join(ROOT, "assets/logo/logo_round.png"), 360)}
    for f in sorted(os.listdir(os.path.join(ROOT, "assets"))):
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            assets[os.path.splitext(f)[0]] = picture(os.path.join(ROOT, "assets", f), 1920)
    for f in sorted(os.listdir(os.path.join(ROOT, "assets/logo"))):
        if f.lower().endswith(".png") and not f.startswith("logo_round"):
            assets[os.path.splitext(f)[0]] = picture(os.path.join(ROOT, "assets/logo", f), 600)
    html = open(os.path.join(ROOT, "motion/engine2.html"), encoding="utf-8").read()
    scenes = open(os.path.join(ROOT, "motion/scenes2.js"), encoding="utf-8").read()
    custom = os.path.join(ROOT, "motion/custom.js")
    html = (html.replace("/*FONTFACES*/", faces).replace("/*DATA*/", json.dumps(data, ensure_ascii=False))
            .replace("/*ASSETS*/", json.dumps(assets)).replace("/*SCENES*/", scenes)
            .replace("/*CUSTOM*/", open(custom, encoding="utf-8").read() if os.path.exists(custom) else ""))
    open(os.path.join(ROOT, "motion/engine.html"), "w", encoding="utf-8").write(html)
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    json.dump({"chapters": chs, "cues": cues}, open(os.path.join(ROOT, "build/timeline.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    tot = sum(c["end"] for c in chs)
    n_shots = sum(len(c["shots"]) for c in chs)
    used = sorted({s["type"] for c in chs for s in c["shots"]})
    print(f"engine.html: {len(chs)} chapters, {n_shots} shots ({tot / max(1, n_shots):.1f} s a shot), {len(used)} scene types "
          f"{used}, total {tot:.1f} s ({tot / 60:.2f} min)")
    for p in problems:
        print("  RULE:", p)
    return 1 if any("no scene type" in p or "max" in p for p in problems) else 0


if __name__ == "__main__":
    sys.exit(main())
