# -*- coding: utf-8 -*-
"""Zarib100x — THE DESK engine: builds the day's page from COMMON/motion/desk.js + your motion/scene.js and
renders it (headless Chromium → ffmpeg). The render plumbing is Pro-Chart's engine6 (chunks, resume, ≤ 2
browsers, frames piped into ffmpeg); nothing of its look.

What the page gets (all inline, so the canvas is never tainted and nothing loads from the network):
  DATA.lines   direction/word_times.json «lines» (for DESK.capsFromWords), [] if missing
  DATA.facts   qc/facts.json (coin reels; series_1y = the real daily prices) · DATA.news qc/news.json ·
               DATA.tape qc/tape.json (COMMON/tools/tape.py; the HUD's price tape), {} / null if missing
  DATA.vol     the voice loudness 60×/s (0..1) from qc/voice_final.wav, [] if missing
  fonts        IRANYekanX Pro (ZF<w>; Persian digits by desk.js), IBM Plex Mono (ZM<w>), IBM Plex Sans
               Condensed (ZC<w>); weights 100…950 as listed in FONTS below
  IMG          every picture under assets/ (jpg/png/webp), as IMG['assets/<name>']; the page's mark as IMG.__mark
Your scene.js ends with DESK.reel({...}) (see desk.js's header); window.END is the video's end in seconds.

usage (PY = /home/studio/kits/prochart-reels/venv-render/bin/python; run in the day's folder):
  PY -I COMMON/motion/desk_engine.py --test 0.5,3.2,...   stills → build/dtest/NN.jpg + build/desk_sheet.jpg
                                                           + build/desk_phone.jpg (the phone-size sheet) + qc/texts.json
  PY -I COMMON/motion/desk_engine.py --render [--fps 60] [--workers 2] [--chunks 8]  → build/segd/segNN.mp4
  PY -I COMMON/motion/desk_engine.py --encode [--audio build/mix.wav] [--out out/video.mp4]
"""
import base64
import json
import os
import subprocess
import sys
import time
from array import array
from multiprocessing import Process

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()
HERE = os.path.dirname(os.path.abspath(__file__))
COMMON = os.path.dirname(HERE)
PRO = "/home/studio/kits/fonts-pro/"
OWN = os.path.join(COMMON, "fonts") + "/"
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
SEG = os.path.join(ROOT, "build", "segd")

# ⟨2026-11-26⟩ the owner: the highest quality on every page. Chrome's canvas JPEG frames are full-range BT.601;
# VF709 turns them into the BT.709 limited range the file is tagged with (before, every colour drifted: the
# brand mustard by 7 levels, pure green by 39). CRF 14 + aq-mode 3 (dark grounds without banding); the VBV cap
# keeps a reel under Instagram's 25 Mbit/s and any length under the 200 MB the hub and IG-Hub take.
VF709 = ("scale=in_color_matrix=bt601:in_range=full:out_color_matrix=bt709:out_range=tv"
         ":flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p")


def vbv():
    """-maxrate/-bufsize: at most 16 Mbit/s, and less for a reel so long that 16 would pass ~180 MB."""
    try:
        end = float(json.load(open(os.path.join(SEG, "plan.json"))).get("end") or 90)
    except (OSError, ValueError):
        end = 90.0
    k = max(4000, min(16000, int(180e6 * 8 / max(end, 1.0) / 1000) - 256))
    return ["-maxrate", f"{k}k", "-bufsize", f"{k}k"]
PAGE = os.path.join(ROOT, "motion", "desk_page.html")
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d  # noqa: E731
FONTS = {  # family name → file
    # IRANYekanX Pro with Latin digits: desk.js writes Persian digits itself (iso), so «Zarib100x» stays Latin
    **{f"ZF{w}": PRO + f"IRANYekanX-{n}.ttf" for w, n in
       ((200, "UltraLight"), (300, "Light"), (400, "Regular"), (500, "Medium"), (600, "DemiBold"), (700, "Bold"),
        (800, "ExtraBold"), (900, "Black"), (950, "ExtraBlack"))},
    **{f"ZM{w}": OWN + f"IBMPlexMono-{n}.ttf" for w, n in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"))},
    **{f"ZC{w}": OWN + f"IBMPlexSansCondensed-{n}.ttf" for w, n in ((600, "SemiBold"), (700, "Bold"))},
}
EXT = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}


def jload(rel, default):
    p = os.path.join(ROOT, rel)
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def envelope(path):
    if not os.path.exists(path):
        return []
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "6000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = array("h")
    a.frombytes(raw)
    out = [(sum(x * x for x in a[i:i + 100]) / max(1, len(a[i:i + 100]))) ** 0.5 for i in range(0, len(a), 100)]
    pk = sorted(out)[int(len(out) * 0.97)] if out else 1
    return [round(min(1.0, max(0.0, (v / (pk or 1) - 0.08) / 0.92)), 3) for v in out]


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def build_html() -> str:
    wt = jload("direction/word_times.json", {})
    data = {
        "lines": [{"n": ln.get("n"), "words": [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in ln["words"]]}
                  for ln in wt.get("lines", [])],
        "facts": jload("qc/facts.json", {}),
        "news": jload("qc/news.json", {}),
        "tape": jload("qc/tape.json", None),
        "vol": envelope(os.path.join(ROOT, "qc/voice_final.wav")),
    }
    fonts = {k: b64(v) for k, v in FONTS.items() if os.path.exists(v)}
    imgs = {}
    adir = os.path.join(ROOT, "assets")
    for dp, _, fs in os.walk(adir):
        for f in sorted(fs):
            ext = os.path.splitext(f)[1].lower()
            if ext in EXT:
                full = os.path.join(dp, f)
                imgs[os.path.relpath(full, ROOT)] = f"data:image/{EXT[ext]};base64," + b64(full)
    mark = os.path.join(COMMON, "brand", "profile_round.png")
    if os.path.exists(mark):
        imgs["__mark"] = "data:image/png;base64," + b64(mark)
    desk = open(os.path.join(HERE, "desk.js"), encoding="utf-8").read()
    scene = open(os.path.join(ROOT, "motion", "scene.js"), encoding="utf-8").read()
    html = ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;background:#160A0E;overflow:hidden}"
            "canvas{display:block}</style></head><body><canvas id='c' width='1080' height='1920'></canvas><script>\n"
            f"const DATA={json.dumps(data, ensure_ascii=False)};\nconst __FONTS={json.dumps(fonts)};\n"
            f"const __IMGS={json.dumps(imgs)};\nwindow.READY=false;\n{desk}\n"
            "Promise.all([...Object.entries(__FONTS).map(([k,b])=>new FontFace(k,`url(data:font/ttf;base64,${b})`).load()"
            ".then(f=>document.fonts.add(f))),...Object.entries(__IMGS).map(([k,src])=>new Promise((ok,no)=>{const im=new Image();"
            "im.onload=()=>{IMG[k]=im;ok();};im.onerror=()=>no(new Error('image '+k));im.src=src;}))])"
            ".then(()=>{\n" + scene + "\nif(!window.END)throw new Error('scene.js must call DESK.reel({... END})');"
            "window.READY=true;}).catch(e=>{window.READY_ERR=String(e);console.error(e);});\n</script></body></html>")
    open(PAGE, "w", encoding="utf-8").write(html)
    return PAGE


def kill_chrome():
    subprocess.run(["pkill", "-f", "ms-playwright/chromium-1243/chrome-linux64/chrome"], check=False)
    time.sleep(0.5)


def open_page(p, page):
    b = p.chromium.launch(executable_path=CHROME, headless=True,
                          args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--allow-file-access-from-files",
                                "--js-flags=--max-old-space-size=768"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + page)
    pg.wait_for_function("window.READY===true || !!window.READY_ERR", timeout=120000)
    err = pg.evaluate("window.READY_ERR || ''")
    if err:
        b.close()
        raise SystemExit(f"page failed: {err} {errs[:3]}")
    return b, pg, errs


def grab(pg, t):
    return base64.b64decode(pg.evaluate(f"frame({t:.6f})").split(",", 1)[1])


def worker(page, chunks, fps):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg, errs = open_page(p, page)
        try:
            for ci, a, z in chunks:
                out = os.path.join(SEG, f"seg{ci:02d}.mp4")
                if os.path.exists(out + ".done"):
                    continue
                ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
                                       "-vf", VF709, "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p",
                                       "-profile:v", "high", "-level", "5.1", "-threads", "2", *vbv(),
                                       "-x264-params", "rc-lookahead=20:aq-mode=3", "-r", str(fps),
                                       "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                                       "-color_range", "tv", out],
                                      stdin=subprocess.PIPE)
                t0 = time.time()
                for i in range(a, z):
                    for _ in range(4):
                        try:
                            data = grab(pg, i / fps)
                            break
                        except Exception as e:  # noqa: BLE001 — reopen the browser, retry this frame
                            print("retry", i, str(e)[:80], flush=True)
                            try:
                                b.close()
                            except Exception:  # noqa: BLE001
                                pass
                            time.sleep(1)
                            b, pg, errs = open_page(p, page)
                    else:
                        raise SystemExit(f"frame {i} failed")
                    ff.stdin.write(data)
                ff.stdin.close()
                if ff.wait() != 0:
                    raise SystemExit(f"ffmpeg failed on chunk {ci}")
                open(out + ".done", "w").write(f"{a} {z}\n")
                print(f"chunk {ci} frames {a}-{z} {round((time.time() - t0) / max(1, z - a) * 1000)} ms/frame", flush=True)
            if errs:
                print("JS:", errs[:5], flush=True)
        finally:
            b.close()


def page_end(page):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg, _ = open_page(p, page)
        end = float(pg.evaluate("window.END"))
        b.close()
    return end


def main() -> None:
    page = build_html()
    if "--build" in sys.argv:
        print("page", page)
        return
    if "--test" in sys.argv:
        from playwright.sync_api import sync_playwright
        kill_chrome()
        times = [float(x) for x in arg("--test", "1").split(",")]
        out = os.path.join(ROOT, "build", "dtest")
        os.makedirs(out, exist_ok=True)
        for f in os.listdir(out):
            os.remove(os.path.join(out, f))
        with sync_playwright() as p:
            b, pg, errs = open_page(p, page)
            t0 = time.time()
            for k, t in enumerate(times):
                open(os.path.join(out, f"{k:02d}.jpg"), "wb").write(grab(pg, t))
            ms = round((time.time() - t0) * 1000 / len(times))
            # every string the page drew while rendering the stills: tools/textlint.py reads it
            texts = pg.evaluate("window.DESK_TEXTS()")
            os.makedirs(os.path.join(ROOT, "qc"), exist_ok=True)
            json.dump(texts, open(os.path.join(ROOT, "qc", "texts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            print("ms/frame", ms, "JS errors:", errs[:8], "texts:", len(texts))
            b.close()
        kill_chrome()
        cols = int(arg("--cols", "6"))
        rows = (len(times) + cols - 1) // cols
        for name, w in (("desk_sheet.jpg", arg("--w", "216")), ("desk_phone.jpg", "360")):
            c2 = cols if name == "desk_sheet.jpg" else min(4, cols)
            r2 = (len(times) + c2 - 1) // c2
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", os.path.join(out, "%02d.jpg"), "-vf",
                            f"scale={w}:-2:flags=lanczos,tile={c2}x{r2}:padding=6:color=0x222222", "-frames:v", "1", "-q:v", "3",
                            os.path.join(ROOT, "build", name)], check=True)
        print("sheets build/desk_sheet.jpg build/desk_phone.jpg (360 px = a phone's width: read every word there)", len(times), rows)
        return
    if "--render" in sys.argv:
        fps = int(arg("--fps", "60"))
        os.makedirs(SEG, exist_ok=True)
        kill_chrome()
        end = page_end(page)
        n = int(round(end * fps))
        nc = int(arg("--chunks", "8"))
        k = min(2, int(arg("--workers", "2")))  # HQ rule: never more than 2 browsers
        bounds = [(ci, n * ci // nc, n * (ci + 1) // nc) for ci in range(nc)]
        json.dump({"fps": fps, "n": n, "end": end, "chunks": bounds}, open(os.path.join(SEG, "plan.json"), "w"))
        procs = [Process(target=worker, args=(page, bounds[j::k], fps)) for j in range(k)]
        for pr in procs:
            pr.start()
        for pr in procs:
            pr.join()
        kill_chrome()
        done = [c for c in bounds if os.path.exists(os.path.join(SEG, f"seg{c[0]:02d}.mp4.done"))]
        print("chunks done", len(done), "of", nc, "exit", [pr.exitcode for pr in procs])
        return
    if "--encode" in sys.argv:
        plan = json.load(open(os.path.join(SEG, "plan.json")))
        end = plan["end"]
        segs = [os.path.join(SEG, f"seg{c[0]:02d}.mp4") for c in plan["chunks"]]
        miss = [s for s in segs if not os.path.exists(s + ".done")]
        if miss:
            raise SystemExit(f"missing chunks {miss}")
        lst = os.path.join(SEG, "list.txt")
        open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
        audio = arg("--audio", os.path.join(ROOT, "build", "mix.wav"))
        out = arg("--out", os.path.join(ROOT, "out", "video.mp4"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
                        "-filter_complex", f"[1:a]apad=whole_dur={end},atrim=0:{end},aformat=channel_layouts=stereo[a]",
                        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-t", f"{end}", "-movflags", "+faststart", out], check=True)
        print("wrote", out)


if __name__ == "__main__":
    main()
