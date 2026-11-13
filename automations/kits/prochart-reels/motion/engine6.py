# -*- coding: utf-8 -*-
"""ProChart reel engine v6 = engine5 motion graphics + toon.js animation layer (a character acts out every sentence).

Owner's fixed rules (2026-11-13): every word/sentence becomes animation + motion graphics, both in every scene; no preview
videos (direction on paper), the video is made once as the final output. HQ render rule: at most 2 browsers at a time,
each closed after its work, frames piped straight into ffmpeg (no frame files), leftover Chromium killed before a render.
The render is split in chunks; a finished chunk (segment + .done) is never redone, so a stopped render resumes.

usage (build/.venv/bin/python -I motion/engine6.py ...):
  --test 0.5,12.3,...           stills for our own check -> build/e6test/NN.jpg + build/e6_sheet.jpg (not for the owner)
  --render [--fps 60] [--workers 2] [--chunks 8]   -> build/seg6/segNN.mp4
  --encode --out out/NAME.mp4 [--audio build/mix.wav]
"""
import base64
import json
import os
import subprocess
import sys
import time
import wave
from array import array
from multiprocessing import Process

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()  # the day's own folder
KIT = "/home/studio/kits/prochart-reels"
HERE = os.path.join(ROOT, "motion")
FD = "/home/studio/kits/prochart-reels/fonts/"
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
VOICE = os.path.join(ROOT, "qc/voice_final.wav")
SEG = os.path.join(ROOT, "build", "seg6")
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
FONTS = {"4": "Regular", "6": "DemiBold", "7": "Bold", "8": "ExtraBold", "9": "Black", "X": "ExtraBlack"}


def envelope():
    """Voice loudness 60 times a second (0..1) for the lip-sync."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", VOICE, "-ac", "1", "-ar", "6000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = array("h")
    a.frombytes(raw)
    out = []
    for i in range(0, len(a), 100):
        blk = a[i:i + 100]
        out.append((sum(x * x for x in blk) / max(1, len(blk))) ** 0.5)
    pk = sorted(out)[int(len(out) * 0.97)] or 1
    return [round(min(1.0, max(0.0, (v / pk - 0.08) / 0.92)), 3) for v in out]


def build_html() -> str:
    wt = json.load(open(os.path.join(ROOT, "direction/word_times.json"), encoding="utf-8"))
    ed = json.load(open(os.path.join(ROOT, "direction/edit.json"), encoding="utf-8"))
    data = {
        "lines": [{"n": l["n"], "words": [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in l["words"]]} for l in wt["lines"]],
        "beats": {b["id"]: b["start"] for b in ed["beats"]},
        "end": ed["video_end"],
        "subs": [{"start": c["start"], "end": c["end"], "words": [{"w": w["w"], "s": w["s"]} for w in c["words"]]}
                 for c in ed["subtitles"]],
        "vol": envelope(),
    }
    fonts = {k: base64.b64encode(open(FD + f"IRANYekanXFaNum-{v}.ttf", "rb").read()).decode() for k, v in FONTS.items()}
    logo = base64.b64encode(open(os.path.join(KIT, "coverkit2/logo/prochart-mark-mustard.png"), "rb").read()).decode()
    html = open(os.path.join(HERE, "engine5_template.html"), encoding="utf-8").read()
    toon = open(os.path.join(HERE, "toon.js"), encoding="utf-8").read()
    assert "function draw(t){" in html and "  subtitles(t);\n  WIPES.forEach" in html
    html = html.replace("function draw(t){", toon + "\nfunction draw(t){", 1)
    html = html.replace("  subtitles(t);\n  WIPES.forEach", "  toonLayer(t);\n  subtitles(t);\n  WIPES.forEach", 1)
    html = html.replace("C.toDataURL('image/jpeg',0.93)", "C.toDataURL('image/jpeg',0.95)")
    html = html.replace("/*DATA*/", json.dumps(data, ensure_ascii=False))
    html = html.replace("/*FONTS*/", json.dumps(fonts)).replace("/*LOGO*/", json.dumps("data:image/png;base64," + logo))
    out = os.path.join(HERE, "engine6.html")
    open(out, "w", encoding="utf-8").write(html)
    return out


def kill_chrome():
    subprocess.run(["pkill", "-f", "ms-playwright/chromium-1243/chrome-linux64/chrome"], check=False)
    time.sleep(0.5)


def open_page(p, page):
    b = p.chromium.launch(executable_path=CHROME, headless=True,
                          args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--js-flags=--max-old-space-size=512"])
    pg = b.new_page(viewport={"width": 1080, "height": 1920})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + page)
    pg.wait_for_function("window.READY===true", timeout=60000)
    return b, pg, errs


def grab(pg, t):
    d = pg.evaluate(f"frame({t:.6f})")
    return base64.b64decode(d.split(",", 1)[1])


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
                                       "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-profile:v", "high",
                                       "-level", "5.1", "-threads", "2", "-x264-params", "rc-lookahead=20", "-r", str(fps),
                                       "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out],
                                      stdin=subprocess.PIPE)
                t0 = time.time()
                for i in range(a, z):
                    for attempt in range(4):
                        try:
                            data = grab(pg, i / fps)
                            break
                        except Exception as e:  # noqa: BLE001 — reopen the browser and retry this frame
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


def main() -> None:
    page = build_html()
    end = json.load(open(os.path.join(ROOT, "direction/edit.json"), encoding="utf-8"))["video_end"]
    if "--test" in sys.argv:
        from playwright.sync_api import sync_playwright
        kill_chrome()
        times = [float(x) for x in arg("--test", "1").split(",")]
        out = os.path.join(ROOT, "build", "e6test")
        os.makedirs(out, exist_ok=True)
        for f in os.listdir(out):
            os.remove(os.path.join(out, f))
        with sync_playwright() as p:
            b, pg, errs = open_page(p, page)
            t0 = time.time()
            for k, t in enumerate(times):
                open(os.path.join(out, f"{k:02d}.jpg"), "wb").write(grab(pg, t))
            print("ms/frame", round((time.time() - t0) * 1000 / len(times)), "JS errors:", errs[:8])
            b.close()
        cols = int(arg("--cols", "6"))
        rows = (len(times) + cols - 1) // cols
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", os.path.join(out, "%02d.jpg"), "-vf",
                        f"scale={arg('--w', '216')}:-2,tile={cols}x{rows}:padding=4:color=0x333333", "-frames:v", "1", "-q:v", "3",
                        os.path.join(ROOT, "build", "e6_sheet.jpg")], check=True)
        print("sheet build/e6_sheet.jpg", len(times))
        return
    if "--render" in sys.argv:
        fps = int(arg("--fps", "60"))
        os.makedirs(SEG, exist_ok=True)
        n = int(round(end * fps))
        nc = int(arg("--chunks", "8"))
        k = min(2, int(arg("--workers", "2")))  # HQ rule: never more than 2 browsers
        bounds = [(ci, n * ci // nc, n * (ci + 1) // nc) for ci in range(nc)]
        json.dump({"fps": fps, "n": n, "chunks": bounds}, open(os.path.join(SEG, "plan.json"), "w"))
        kill_chrome()
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
