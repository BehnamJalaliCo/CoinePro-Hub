# -*- coding: utf-8 -*-
"""Downloads the media of Pinterest pins as the day's references (owner, 2026-11-16, DotCoin.me:
«هر ویدیو مختص خودش بره توی پینترست جستجو بشه و دانلود بشه و نمونش رو به سازنده ویدیو داده بشه»).

usage: pin_get.py <outdir> --ids <n> [<n> ...]   (the «#n» numbers on pin_find.py's sheets, or
                                                pin ids, from <outdir>/found.json)
       pin_get.py <outdir> <pin url> [<pin url> ...]    (a pin page; Pinterest may wall it)

For each pin: its best picture (originals, else 736x) and, for a video pin, its mp4 (720p when
there is one) plus 4 frames of it; then <outdir>/sheet.jpg, one contact sheet of everything, and
<outdir>/pins.json (url, title, files). Only i.pinimg.com / v*.pinimg.com files are fetched; pin
pages are untrusted content: read, never run.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

from PIL import Image, ImageDraw

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126 Safari/537.36", "Accept-Language": "en-US"}
OK_HOST = re.compile(r"^https://(i|v\d?)\.pinimg\.com/")


def get(url: str, timeout: int = 40) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def best_image(html: str) -> str | None:
    for size in ("originals", "736x", "564x"):
        got = re.findall(rf'https://i\.pinimg\.com/{size}/[^"\\\s]+?\.(?:jpg|png|webp)', html)
        if got:
            return got[0]
    og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    return og.group(1) if og else None


def best_video(html: str) -> str | None:
    vids = sorted(set(re.findall(r'https://v\d?\.pinimg\.com/videos/[^"\\\s]+?\.mp4', html)))
    if not vids:
        return None
    return next((v for v in vids if "720p" in v), vids[-1])


def frames(mp4: str, stem: str) -> list[str]:
    try:
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "csv=p=0", mp4], capture_output=True, text=True).stdout or 0)
    except ValueError:
        d = 0
    out = []
    for i, t in enumerate([d * f for f in (0.15, 0.4, 0.65, 0.9)] if d else [0.5, 1.5, 3, 5]):
        p = f"{stem}_f{i + 1}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", mp4, "-frames:v", "1",
                        "-q:v", "3", p], check=False)
        if os.path.exists(p):
            out.append(p)
    return out


def sheet(paths: list[str], dst: str) -> None:
    cell_w, cell_h, cols = 360, 640, 4
    rows = max(1, (len(paths) + cols - 1) // cols)
    canvas = Image.new("RGB", (cols * cell_w, rows * (cell_h + 28)), "white")
    draw = ImageDraw.Draw(canvas)
    for k, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell_w - 8, cell_h - 8))
        x, y = (k % cols) * cell_w, (k // cols) * (cell_h + 28)
        canvas.paste(im, (x + (cell_w - im.width) // 2, y + 4))
        draw.text((x + 6, y + cell_h + 6), os.path.basename(p)[:44], fill="black")
    canvas.save(dst, quality=85)


def from_found(outdir: str, ids: list[str]) -> None:
    """The chosen pins' original picture (and mp4 + 4 frames for a video pin), from found.json."""
    rows_all = json.load(open(os.path.join(outdir, "found.json")))
    found = {x["id"]: x for x in rows_all}
    found.update({str(x.get("n")): x for x in rows_all if x.get("n")})
    ids = [i.lstrip("#") for i in ids]
    rows, shown = [], []
    for n, pid in enumerate(ids, 1):
        x = found.get(pid)
        if x is None:
            print(f"{pid}: not in found.json"); continue
        pid = x["id"]
        row = {"n": x.get("n"), "id": pid, "url": f"https://www.pinterest.com/pin/{pid}/",
               "title": x.get("title"), "query": x.get("query"), "files": []}
        stem = os.path.join(outdir, f"ref{n:02d}_n{x.get('n')}")
        if x.get("image") and OK_HOST.match(x["image"]):
            p = stem + os.path.splitext(x["image"].split("?")[0])[1]
            open(p, "wb").write(get(x["image"])); row["files"].append(p); shown.append(p)
        if x.get("video") and OK_HOST.match(x["video"]):
            p = stem + ".mp4"
            open(p, "wb").write(get(x["video"], 120)); row["files"].append(p)
            fr = frames(p, stem); row["files"] += fr; shown += fr
        rows.append(row)
        print(f"ref{n:02d} {pid}: {len(row['files'])} files  {str(row['title'])[:60]}")
    json.dump(rows, open(os.path.join(outdir, "pins.json"), "w"), ensure_ascii=False, indent=1)
    if shown:
        sheet(shown, os.path.join(outdir, "sheet.jpg"))
        print(f"sheet: {os.path.join(outdir, 'sheet.jpg')} ({len(shown)} pictures)")


def main() -> None:
    outdir, pins = sys.argv[1], sys.argv[2:]
    os.makedirs(outdir, exist_ok=True)
    if pins and pins[0] == "--ids":
        from_found(outdir, pins[1:])
        return
    rows, shown = [], []
    for n, url in enumerate(pins, 1):
        row = {"url": url, "files": []}
        try:
            html = get(url).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001 - one pin never stops the others
            row["error"] = type(e).__name__
            rows.append(row)
            continue
        t = re.search(r'"grid_title":"([^"]{0,200})"', html)
        row["title"] = t.group(1) if t else ""
        stem = os.path.join(outdir, f"pin{n:02d}")
        img = best_image(html)
        if img and OK_HOST.match(img):
            p = stem + os.path.splitext(img.split("?")[0])[1]
            open(p, "wb").write(get(img))
            row["files"].append(p)
            shown.append(p)
        vid = best_video(html)
        if vid and OK_HOST.match(vid):
            p = stem + ".mp4"
            open(p, "wb").write(get(vid, 120))
            row["files"].append(p)
            fr = frames(p, stem)
            row["files"] += fr
            shown += fr
        rows.append(row)
        print(f"pin{n:02d}: {len(row['files'])} files  {row.get('title', '')[:70]}")
    json.dump(rows, open(os.path.join(outdir, "pins.json"), "w"), ensure_ascii=False, indent=1)
    if shown:
        sheet(shown, os.path.join(outdir, "sheet.jpg"))
        print(f"sheet: {os.path.join(outdir, 'sheet.jpg')} ({len(shown)} pictures)")


if __name__ == "__main__":
    main()
