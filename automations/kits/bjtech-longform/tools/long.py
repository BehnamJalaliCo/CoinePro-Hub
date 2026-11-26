#!/usr/bin/env python3
"""@behnamjalali.tech long video (KIT/tools/long.py; stdlib + ffmpeg/ffprobe): the chapters of the day → one file,
the YouTube text, the Persian subtitles.

The day's folder holds one sub-folder per chapter, `ch/00` (the cold open) … `ch/NN` (the end), each a small reel
folder of the LUMEN engine in 16:9 (motion/WIDE, its own script/voice.txt, script/subs.txt, qc/voice_final.wav,
direction/word_times.json, motion/scenes.js, its render in out/chapter.mp4).

  python3 -I KIT/tools/long.py init <n>        make ch/00 … ch/<n> (motion/WIDE, the shared assets linked)
  python3 -I KIT/tools/long.py status          each chapter: voice, words, scenes, render, its length
  python3 -I KIT/tools/long.py concat          ch/*/out/chapter.mp4 → each lifted to 2560x1440 once (resumable,
                                               ~7 minutes a call: "AGAIN" = run it again) → out/video.mp4 (+faststart)
  python3 -I KIT/tools/long.py bar             each chapter's direction/videobar.json (its place in the whole video, for
                                               the slim chapter progress bar the stage draws); run it after every voice
                                               is final and again before rendering
  python3 -I KIT/tools/long.py retention       THE RETENTION GATE (owner 2026-11-18): the numbers below from the real
                                               timelines and script/retention.json; exit 1 = re-cut, never publish
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
import time

ROOT = os.getcwd()
COMMON = "/home/studio/kits/bjtech-common"
MAX_CUE = 42  # characters a subtitle line holds; a longer line is split into timed parts

# ⟨2026-11-26⟩ the owner: the highest quality. YouTube gives a 1440p upload its better codecs (VP9/AV1) and more
# bits, at 1440p and at 1080p too. The chapters render at 1080p; concat lifts each to 2560x1440 (Lanczos) once,
# resumable (a chapter lifted is kept until it is rendered again), then joins them without another encode. The
# VBV cap keeps the whole file under ~930 MB (egress's upload_long takes 1 GiB): 16 Mbit/s (YouTube's 1440p30
# figure) or less for a long video.
UP_VF = "scale=2560:1440:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p,setsar=1"
UP_BUDGET_S = 420  # one --concat lifts chapters for about 7 minutes, then asks to be run again
FILE_BYTES = 930e6
AUDIO_K = 384  # AAC stereo, YouTube's figure


def up_kbps(total):
    return max(6000, min(16000, int(FILE_BYTES * 8 / max(total, 1.0) / 1000) - AUDIO_K))


def up_args(kbps, tune):
    """x264 for the 1440p lift: CRF 15, medium (slow buys ~4 % of size, nothing seen), the VBV cap."""
    return ["-vf", UP_VF, "-c:v", "libx264", "-preset", "medium", "-crf", "15", *(["-tune", "animation"] if tune else []),
            "-profile:v", "high", "-level", "5.1", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", "-g", "60",
            "-bf", "2", "-threads", "4", "-x264-params", "rc-lookahead=30:aq-mode=3", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]


def lifted(src, dst):
    return os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)


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
    kbps = up_kbps(sum(duration(p) for p in parts))
    t0, left, ups = time.time(), [], []
    for p in parts:
        up = p[:-4] + "_1440.mp4"
        ups.append(up)
        if lifted(p, up):
            continue
        if time.time() - t0 > UP_BUDGET_S:
            left.append(p.split(os.sep)[-3])
            continue
        t1 = time.time()
        r = sh(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-i", p, "-map", "0:v:0", "-map", "0:a:0", *up_args(kbps, False),
                "-c:a", "copy", up + ".part.mp4"])
        if r.returncode:
            sys.exit(r.stderr[-400:])
        os.replace(up + ".part.mp4", up)
        print(f"ch/{p.split(os.sep)[-3]} lifted to 1440p in {time.time() - t1:.0f} s", flush=True)
    if left:
        sys.exit(f"AGAIN: {len(left)} chapters still to lift to 1440p {left}; run concat again (lifted ones are kept)")
    lst = os.path.join(ROOT, "build", "concat.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in ups))
    out = os.path.join(ROOT, "out", "video.mp4")
    r = sh(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
            "-movflags", "+faststart", out])
    if r.returncode:
        sys.exit(r.stderr[-400:])
    size = os.path.getsize(out)
    print(out, f"{duration(out) / 60:.2f} min, {len(parts)} chapters, 2560x1440, {size / 1e6:.0f} MB, cap {kbps} kbit/s")
    if size > 1024 ** 3:
        sys.exit("the file is over YouTube upload_long's 1 GiB: tell the hub (never cut it by hand)")


def chapter_len(c):
    """A chapter's length: its render, else its built timeline, else its voice + the stage's tail (0.4 s)."""
    p = lambda *a: os.path.join(ROOT, "ch", c, *a)  # noqa: E731
    if os.path.exists(p("out", "chapter.mp4")):
        return duration(p("out", "chapter.mp4"))
    if os.path.exists(p("build", "timeline.json")):
        return float(json.load(open(p("build", "timeline.json")))["end"])
    wt = json.load(open(p("direction", "word_times.json"), encoding="utf-8"))
    return float(wt.get("duration") or wt["lines"][-1]["end"]) + .4


def bar():
    lens = [(c, chapter_len(c)) for c in chapters()]
    total = sum(d for _, d in lens)
    marks, off = [], 0.0
    for c, d in lens:
        marks.append(round(off, 2))
        off += d
    off = 0.0
    for c, d in lens:
        json.dump({"start": round(off, 2), "total": round(total, 2), "marks": marks[1:]},
                  open(os.path.join(ROOT, "ch", c, "direction", "videobar.json"), "w"))
        off += d
    print(f"videobar: {len(lens)} chapters, {total / 60:.2f} min")


QUESTION = re.compile(r"[؟?]\s*$")
OUTRO_MAX, STATIC_MAX, HOOK_BY, LOOP_BY, END_WINDOW = 15.0, 6.0, 8.0, 30.0, 60.0


def retention():
    """The owner's retention rules as numbers (README «Retention»). Reads each chapter's build/timeline.json (shots and
    BEATs: the longest stretch with nothing new) and script/retention.json (what the session marks: the hook question,
    the open loops, the re-hooks, the payoff, the outro) and prints every check; exit 1 when any fails."""
    rj = json.load(open(os.path.join(ROOT, "script", "retention.json"), encoding="utf-8"))
    fails, rows, off, starts = [], [], 0.0, {}
    cs = chapters()
    for c in cs:
        starts[c] = off
        tl_path = os.path.join(ROOT, "ch", c, "build", "timeline.json")
        if not os.path.exists(tl_path):
            fails.append(f"ch{c}: no build/timeline.json (run reel.py --timeline)")
            off += chapter_len(c)
            continue
        tl = json.load(open(tl_path, encoding="utf-8"))
        marks = sorted({0.0, float(tl["end"]), *(float(s["at"]) for s in tl["shots"]), *(float(b["t"]) for b in tl["beats"])})
        gaps = [(b - a, a) for a, b in zip(marks, marks[1:])]
        g, at = max(gaps) if gaps else (0.0, 0.0)
        rows.append(f"ch{c} longest stretch with nothing new {g:.1f} s at {at:.1f} s")
        if g > STATIC_MAX:
            fails.append(f"ch{c}: {g:.1f} s with nothing new at {at:.1f} s (max {STATIC_MAX:.0f})")
        voice = [x.strip() for x in open(os.path.join(ROOT, "ch", c, "script", "subs.txt"), encoding="utf-8") if x.strip()] \
            if os.path.exists(os.path.join(ROOT, "ch", c, "script", "subs.txt")) else []
        if c != cs[-1] and voice:
            last = voice[-1]
            turn = c in (rj.get("cliffs") or {})
            if not (QUESTION.search(last) or turn):
                fails.append(f"ch{c}: ends on «{last[:50]}» — no question, and no turn marked in retention.json cliffs")
        off += float(tl["end"])
    total = off
    hq = float(rj.get("hook_question_at", 99))
    rows.append(f"hook question at {hq:.1f} s (by {HOOK_BY:.0f})")
    if hq > HOOK_BY:
        fails.append(f"the hook question comes at {hq:.1f} s (by {HOOK_BY:.0f} s)")
    loop = float(rj.get("open_loop_at", 99))
    rows.append(f"open loop stated at {loop:.1f} s (by {LOOP_BY:.0f}); closes at {rj.get('open_loop_closes_at')}")
    if loop > LOOP_BY:
        fails.append(f"the open loop comes at {loop:.1f} s (by {LOOP_BY:.0f} s)")
    for k, frac in (("25", .25), ("50", .5), ("75", .75)):
        rh = (rj.get("rehooks") or {}).get(k)
        want = total * frac
        rows.append(f"re-hook {k}%: {rh} (target {ts(want)}, ±45 s)")
        if rh is None or abs(float(rh) - want) > 45:
            fails.append(f"no re-hook near {k}% ({ts(want)}): {rh}")
    pay = float(rj.get("payoff_at", 0))
    outro = float(rj.get("outro_s", 99))
    rows.append(f"payoff and takeaway at {ts(pay)} (within the last {END_WINDOW:.0f} s: from {ts(total - END_WINDOW)}); outro {outro:.1f} s")
    if pay < total - END_WINDOW:
        fails.append(f"the payoff lands at {ts(pay)}, before the last {END_WINDOW:.0f} s")
    if outro > OUTRO_MAX:
        fails.append(f"the outro is {outro:.1f} s (max {OUTRO_MAX:.0f})")
    print(f"total {ts(total)}")
    for r in rows:
        print("  " + r)
    for f in fails:
        print("FAIL " + f)
    print("RETENTION " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    sys.exit(1 if fails else 0)


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
    if a[0] == "bar":
        return bar()
    if a[0] == "retention":
        return retention()
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
