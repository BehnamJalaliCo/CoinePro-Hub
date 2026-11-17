#!/usr/bin/env python3
"""The long video's YouTube package from the script and the real timeline: out/meta.json (title, description with
chapters, tags, category, slug, topic), out/subtitles.fa.srt (sidecar Persian subtitles from the word times) and
out/chapters.txt.

usage: python3 -I tools/yt_meta.py   (reads script/chapters.json, script/youtube.json, build/timeline.json)
script/youtube.json: {"title", "intro": [lines], "learn": [lines], "tags": [..], "hashtags": [3 tags]}
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def stamp(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def cues(words, limit=44):
    """Words of one sentence -> subtitle cues of at most `limit` characters, cut at word boundaries."""
    out, cur = [], []
    for w in words:
        if cur and len(" ".join(x["w"] for x in cur + [w])) > limit:
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def main():
    spec = json.load(open(os.path.join(ROOT, "script/chapters.json"), encoding="utf-8"))
    yt = json.load(open(os.path.join(ROOT, "script/youtube.json"), encoding="utf-8"))
    tl = json.load(open(os.path.join(ROOT, "build/timeline.json"), encoding="utf-8"))["chapters"]
    slug = spec["slug"]
    off, chap_lines, subs = 0.0, [], []
    for c, sc in zip(tl, spec["chapters"]):
        chap_lines.append(f"{stamp(off)} {sc['yt']}")
        for s, src in zip(c["sent"], sc["s"]):
            text_words = src["v"].split()
            # the timed words carry the script's own spelling when they came from word_times.py
            ws = s["words"] if len(s["words"]) == len(text_words) else [
                {"w": w, "s": s["s"] + (s["e"] - s["s"]) * i / len(text_words),
                 "e": s["s"] + (s["e"] - s["s"]) * (i + 1) / len(text_words)} for i, w in enumerate(text_words)]
            ws = [{**w, "w": tw} for w, tw in zip(ws, text_words)]
            for part in cues(ws):
                subs.append((off + part[0]["s"], off + part[-1]["e"] + 0.15, " ".join(x["w"] for x in part)))
        off += c["end"]
    # no overlaps
    for i in range(len(subs) - 1):
        a, b, t = subs[i]
        subs[i] = (a, min(b, subs[i + 1][0] - 0.02), t)
    total = off
    if len(chap_lines) < 3 or any(c["end"] < 10 for c in tl):
        sys.exit("YouTube chapters need 3+ chapters of 10+ s")
    url = f"https://dotcoin.me/learn/{slug}/"
    desc = "\n".join([
        *yt["intro"], "",
        "📖 مقاله‌ی کامل این درس، با جدول مقایسه و پرسش‌های پرتکرار:", url, "",
        "در این ویدیو:", *[f"• {x}" for x in yt["learn"]], "",
        "فصل‌ها:", *chap_lines, "",
        "دات‌کوین: آموزش ارز دیجیتال به زبان ساده", "سایت: https://dotcoin.me", "اینستاگرام: https://www.instagram.com/dotcoin.me", "",
        " ".join(yt["hashtags"][:3]),
    ])
    desc = desc.replace("<", "").replace(">", "")
    title = yt["title"].replace("<", "").replace(">", "")
    tags = []
    for t in yt["tags"]:
        t = t.strip().replace(",", " ")
        if t and t not in tags and len(",".join(tags + [t])) <= 480:
            tags.append(t)
    assert len(title) <= 100, len(title)
    assert len(desc) <= 4900, len(desc)
    meta = {"slug": slug, "topic": spec["topic"], "title": title, "description": desc, "tags": tags,
            "category": "Education", "duration_s": round(total, 2), "article": url}
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    json.dump(meta, open(os.path.join(ROOT, "out/meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "out/subtitles.fa.srt"), "w", encoding="utf-8") as f:
        for i, (a, b, t) in enumerate(subs, 1):
            f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n")
    open(os.path.join(ROOT, "out/chapters.txt"), "w", encoding="utf-8").write("\n".join(chap_lines) + "\n")
    print(f"title {len(title)} chars, description {len(desc)} chars, {len(tags)} tags, {len(subs)} subtitle cues, "
          f"{len(chap_lines)} chapters, total {stamp(total)} ({total:.1f} s)")


if __name__ == "__main__":
    main()
