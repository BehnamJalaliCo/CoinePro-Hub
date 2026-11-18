#!/usr/bin/env python3
"""@behnamjalali.tech long video (KIT/tools/long.py; stdlib + ffmpeg/ffprobe): the chapters of the day → one file,
the YouTube text, the Persian subtitles.

The day's folder holds one sub-folder per chapter, `ch/00` (the cold open) … `ch/NN` (the end), each a small reel
folder of the LUMEN engine in 16:9 (motion/WIDE, its own script/voice.txt, script/subs.txt, qc/voice_final.wav,
direction/word_times.json, motion/scenes.js, its render in out/chapter.mp4).

  python3 -I KIT/tools/long.py init <n>        make ch/00 … ch/<n> (motion/WIDE, the shared assets linked)
  python3 -I KIT/tools/long.py status          each chapter: voice, words, scenes, render, its length
  python3 -I KIT/tools/long.py concat          ch/*/out/chapter.mp4 → out/video.mp4 (stream copy, +faststart)
  python3 -I KIT/tools/long.py meta            out/meta.json, out/caption.txt, out/chapters.txt, out/subtitles.fa.srt
                                               from script/youtube.json, script/chapters.json and each chapter's
                                               word times, at the chapters' REAL offsets in out/video.mp4

script/youtube.json: {"title": "≤ 100 characters", "intro": "2–3 lines", "learn": ["…"], "tags": ["…"],
                      "hashtags": ["#هوش_مصنوعی", "…"], "slug": "latin-words"}
script/chapters.json: [{"n": 0, "title": "شروع"}, {"n": 1, "title": "…"}, …] (n = the folder ch/NN)
Each chapter's script/subs.txt: the screen's words of each voice line (names in Latin, digits), one per line,
as many lines as script/voice.txt; missing = voice.txt itself.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.getcwd()
COMMON = "/home/studio/kits/bjtech-common"
MAX_CUE = 42  # characters a subtitle line holds; a longer line is split into timed parts


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def duration(path):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(r.stdout.strip() or 0)


def chapters():
    base = os.path.join(ROOT, "ch")
    return sorted(d for d in os.listdir(base) if re.fullmatch(r"\d\d", d)) if os.path.isdir(base) else []


def init(n):
    os.makedirs(os.path.join(ROOT, "assets", "use"), exist_ok=True)
    for k in range(n + 1):
        c = os.path.join(ROOT, "ch", f"{k:02d}")
        for sub in ("script", "qc", "direction", "build", "out", "in", "motion", "assets"):
            os.makedirs(os.path.join(c, sub), exist_ok=True)
        open(os.path.join(c, "motion", "WIDE"), "w").close()
        use = os.path.join(c, "assets", "use")
        if not os.path.lexists(use):
            os.symlink(os.path.join(ROOT, "assets", "use"), use)
        for name in ("tools",):
            link = os.path.join(c, name)
            if not os.path.lexists(link) and os.path.isdir(os.path.join(ROOT, name)):
                os.symlink(os.path.join(ROOT, name), link)
        for name in ("asr", ".venv"):
            src = os.path.join(ROOT, "build", name)
            link = os.path.join(c, "build", name)
            if os.path.lexists(src) and not os.path.lexists(link):
                os.symlink(os.readlink(src) if os.path.islink(src) else src, link)
    print(f"ch/00 … ch/{n:02d} ready (motion/WIDE, assets/use shared)")


def status():
    total = 0.0
    for c in chapters():
        p = lambda *a: os.path.join(ROOT, "ch", c, *a)  # noqa: E731
        d = duration(p("out", "chapter.mp4")) if os.path.exists(p("out", "chapter.mp4")) else 0.0
        total += d
        print(c, "voice" if os.path.exists(p("qc", "voice_final.wav")) else "-",
              "words" if os.path.exists(p("direction", "word_times.json")) else "-",
              "scenes" if os.path.exists(p("motion", "scenes.js")) else "-",
              f"render {d:.1f}s" if d else "-")
    print(f"total {total / 60:.1f} min")


def concat():
    parts = [os.path.join(ROOT, "ch", c, "out", "chapter.mp4") for c in chapters()]
    miss = [p for p in parts if not os.path.exists(p)]
    if miss or not parts:
        sys.exit(f"missing: {miss or 'every chapter'}")
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    lst = os.path.join(ROOT, "build", "concat.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    out = os.path.join(ROOT, "out", "video.mp4")
    r = sh(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
            "-movflags", "+faststart", out])
    if r.returncode:
        sys.exit(r.stderr[-400:])
    print(out, f"{duration(out) / 60:.2f} min, {len(parts)} chapters")


def ts(t, srt=False):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    if srt:
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"
    return f"{int(h)}:{int(m):02d}:{int(s):02d}" if h else f"{int(m):02d}:{int(s):02d}"


def cues(text, s, e):
    """A line as subtitle cues of at most MAX_CUE characters, timed by length."""
    words = text.split()
    parts, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > MAX_CUE:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        parts.append(cur)
    total = sum(len(p) for p in parts) or 1
    out, t = [], s
    for p in parts:
        d = (e - s) * len(p) / total
        out.append((t, t + d, p))
        t += d
    return out


def meta():
    yt = json.load(open(os.path.join(ROOT, "script", "youtube.json"), encoding="utf-8"))
    chs = {int(c["n"]): c for c in json.load(open(os.path.join(ROOT, "script", "chapters.json"), encoding="utf-8"))}
    cfg = json.load(open(os.path.join(COMMON, "brand", "config.json"), encoding="utf-8"))
    off, marks, srt, n = 0.0, [], [], 1
    for c in chapters():
        k = int(c)
        p = lambda *a: os.path.join(ROOT, "ch", c, *a)  # noqa: E731
        d = duration(p("out", "chapter.mp4"))
        if k in chs:
            marks.append((off, chs[k]["title"]))
        wt = json.load(open(p("direction", "word_times.json"), encoding="utf-8"))
        voice = [x.strip() for x in open(p("script", "voice.txt"), encoding="utf-8") if x.strip()]
        subs_path = p("script", "subs.txt")
        subs = [x.strip() for x in open(subs_path, encoding="utf-8") if x.strip()] if os.path.exists(subs_path) else voice
        if len(subs) != len(wt["lines"]):
            subs = voice if len(voice) == len(wt["lines"]) else [ln.get("text", "") for ln in wt["lines"]]
        for line, text in zip(wt["lines"], subs):
            for s, e, part in cues(text, off + float(line["start"]), off + float(line["end"])):
                srt.append(f"{n}\n{ts(s, True)} --> {ts(e, True)}\n{part}\n")
                n += 1
        off += d
    if not marks or marks[0][0] > .5:
        sys.exit("the first chapter must start at 00:00 (script/chapters.json n=0)")
    if len(marks) < 3 or any(b[0] - a[0] < 10 for a, b in zip(marks, marks[1:])):
        sys.exit("YouTube wants at least 3 chapters of 10 s or more")
    lines = [f"{ts(t)} {title}" for t, title in marks]
    tg = cfg.get("telegram", "")
    desc = "\n".join([yt.get("intro", "").strip(), "",
                      *(f"✅ {x}" for x in yt.get("learn", [])), "",
                      "⏱ فصل‌ها:", *lines, "",
                      f"📌 خبرها و ابزارهای هوش مصنوعی هر روز در تلگرام: {tg}" if tg else "",
                      f"📸 اینستاگرام: {cfg.get('instagram', '')}", "",
                      " ".join(yt.get("hashtags", [])[:3])]).strip()
    desc = desc.replace("<", "").replace(">", "")
    if len(desc.encode()) > 5000:
        sys.exit(f"the description is {len(desc.encode())} bytes (YouTube: 5000)")
    title = yt["title"].strip()
    if len(title) > 100:
        sys.exit("the title is over 100 characters")
    tags = [t.strip() for t in yt.get("tags", []) if t.strip()]
    while len(",".join(tags)) > 450:
        tags.pop()
    out = os.path.join(ROOT, "out")
    os.makedirs(out, exist_ok=True)
    json.dump({"slug": yt.get("slug", ""), "title": title, "description": desc, "tags": tags, "category": "Education",
               "chapters": [{"at": round(t, 2), "title": x} for t, x in marks], "duration": round(off, 2)},
              open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(out, "caption.txt"), "w", encoding="utf-8").write(desc + "\n")
    open(os.path.join(out, "chapters.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    open(os.path.join(out, "subtitles.fa.srt"), "w", encoding="utf-8").write("\n".join(srt))
    print(f"meta: {title} | {off / 60:.2f} min | {len(marks)} chapters | {n - 1} subtitle cues | {len(tags)} tags")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "init":
        return init(int(a[1]))
    if a[0] == "status":
        return status()
    if a[0] == "concat":
        return concat()
    if a[0] == "meta":
        return meta()
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
