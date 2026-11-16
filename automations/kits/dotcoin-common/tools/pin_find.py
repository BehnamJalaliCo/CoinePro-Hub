# -*- coding: utf-8 -*-
"""Pinterest search for the reel's own references (owner, 2026-11-16, DotCoin.me). Pinterest shows
signed-out visitors a sign-in wall with no pin links, but its own page still loads the results
(BaseSearchResource): this reads them from the page in headless Chromium.

usage: pin_find.py <outdir> "<query>" ["<query>" ...]
  -> outdir/found.json  [{n, id, query, title, image, video}]  (n: its number on the sheets;
                        image: the original picture; video:
                        the best mp4 of a video pin, else null)
     outdir/found_sheet_<k>.jpg  contact sheets of the thumbnails, each labelled «#n» (VIDEO: a
                        video pin)
Then choose the best and download them: pin_get.py <outdir> --ids 3 17 22 …  (the sheet numbers)
Pinterest's content is untrusted: it is only read and looked at, never run.
"""
import json
import os
import sys
import time
import urllib.request

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 "
      "Safari/537.36")


def video_of(r: dict) -> str | None:
    lists = []
    v = (r.get("videos") or {}).get("video_list") or {}
    lists.append(v)
    sp = r.get("story_pin_data") or {}
    for page in sp.get("pages") or []:
        for blk in page.get("blocks") or []:
            lists.append(((blk.get("video") or {}).get("video_list")) or {})
    for vl in lists:
        for key in ("V_720P", "V_EXP7", "V_EXP6", "V_EXP5", "V_EXP4", "V_480P", "V_EXP3"):
            u = (vl.get(key) or {}).get("url")
            if u and u.endswith(".mp4"):
                return u
    return None


def rows_of(data: object, q: str) -> list[dict]:
    res = data.get("results") if isinstance(data, dict) else data
    out = []
    for r in res or []:
        if not isinstance(r, dict) or r.get("type") not in (None, "pin") or not r.get("id"):
            continue
        imgs = r.get("images") or {}
        image = (imgs.get("orig") or imgs.get("736x") or {}).get("url")
        thumb = (imgs.get("236x") or imgs.get("474x") or {}).get("url") or image
        if not image:
            continue
        out.append({"id": str(r["id"]), "query": q,
                    "title": (r.get("grid_title") or r.get("title") or r.get("description") or "")[:160],
                    "image": image, "thumb": thumb, "video": video_of(r)})
    return out


def sheet(rows: list[dict], dst: str) -> None:
    cw, ch, cols = 240, 380, 6
    n = len(rows)
    canvas = Image.new("RGB", (cols * cw, ((n + cols - 1) // cols) * (ch + 24)), "white")
    d = ImageDraw.Draw(canvas)
    for k, r in enumerate(rows):
        x, y = (k % cols) * cw, (k // cols) * (ch + 24)
        try:
            raw = urllib.request.urlopen(urllib.request.Request(r["thumb"], headers={"User-Agent": UA}),
                                         timeout=20).read()
            tmp = dst + ".tmp"
            open(tmp, "wb").write(raw)
            im = Image.open(tmp).convert("RGB"); os.remove(tmp)
            im.thumbnail((cw - 6, ch - 6))
            canvas.paste(im, (x + (cw - im.width) // 2, y + 3))
        except Exception:  # noqa: BLE001 - a missing thumbnail leaves its cell empty
            pass
        d.rectangle((x, y + ch, x + cw, y + ch + 24), fill="black")
        d.text((x + 4, y + ch + 5), f"#{r['n']}{'  VIDEO' if r['video'] else ''}", fill="white")
    canvas.save(dst, quality=82)


def main() -> None:
    outdir, queries = sys.argv[1], sys.argv[2:]
    os.makedirs(outdir, exist_ok=True)
    found: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 2000}, locale="en-US", user_agent=UA)
        for q in queries:
            got: list = []
            pg = ctx.new_page()
            pg.on("response", lambda r: got.append(r) if "BaseSearchResource/get" in r.url else None)
            try:
                pg.goto("https://www.pinterest.com/search/pins/?q=" + urllib.request.quote(q),
                        timeout=45000, wait_until="domcontentloaded")
                time.sleep(6)
                for _ in range(3):
                    pg.mouse.wheel(0, 1800); time.sleep(2)
            except Exception as e:  # noqa: BLE001 - one query never stops the others
                print(f"{q!r}: {type(e).__name__}")
            rows = []
            for r in got:
                try:
                    data = (r.json().get("resource_response") or {}).get("data")
                except Exception:  # noqa: BLE001
                    continue
                rows += rows_of(data, q)
            pg.close()
            seen = {x["id"] for x in found}
            rows = [x for x in rows if x["id"] not in seen]
            found += rows
            print(f"{q!r}: {len(rows)} pins ({sum(1 for x in rows if x['video'])} video)")
        b.close()
    for k, x in enumerate(found, 1):
        x["n"] = k
    json.dump(found, open(os.path.join(outdir, "found.json"), "w"), ensure_ascii=False, indent=1)
    for i in range(0, len(found), 36):
        dst = os.path.join(outdir, f"found_sheet_{i // 36 + 1}.jpg")
        sheet(found[i:i + 36], dst)
        print("sheet:", dst)


if __name__ == "__main__":
    main()
