# -*- coding: utf-8 -*-
"""DotCoin long video renderer: chapter by chapter, at most 2 Chromium workers, frames piped into ffmpeg (no frame
files), each chapter split into parts that are never redone once finished (a stopped render resumes).

usage (as studio, PLAYWRIGHT_BROWSERS_PATH set):
  render.py --test CH t1,t2,...          stills -> build/test/chCC_NN.jpg + build/test/sheet_chCC.jpg
  render.py --sheet                      a contact sheet: 6 frames of every chapter -> qc/contact_sheet.jpg
  render.py --render CH[,CH...] [--fps 30] [--workers 2] [--parts 4]  -> build/ch/chCC.mp4
  render.py --concat --audio build/mix.wav --out out/video.mp4
"""
import base64
import io
import json
import os
import subprocess
import sys
import time
from multiprocessing import Process

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
PAGE = os.path.join(ROOT, "motion/engine.html")
CHD = os.path.join(ROOT, "build/ch")
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d

# ⟨2026-11-26⟩ the owner: the highest quality. YouTube gives a 1440p upload its better codecs (VP9/AV1) and more
# bits, at 1440p and at 1080p too. The chapters render at 1080p; --concat lifts each to 2560x1440 (Lanczos) once,
# resumable (a chapter lifted is kept until it is rendered again), then joins them without another encode. The
# VBV cap keeps the whole file under ~930 MB (egress's upload_long takes 1 GiB): 16 Mbit/s (YouTube's 1440p30
# figure) or less for a long video. Chrome's JPEG frames are full-range BT.601: VF709 makes them the BT.709 the
# file is tagged with (before, the colours drifted: mustard by 7 levels).
VF709 = ("scale=in_color_matrix=bt601:in_range=full:out_color_matrix=bt709:out_range=tv"
         ":flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p")
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


def kill():
    subprocess.run(["pkill", "-f", "[c]hrome-linux64/chrome"], check=False)
    time.sleep(0.4)


def open_page(p):
    b = p.chromium.launch(executable_path=CHROME, headless=True,
                          args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--js-flags=--max-old-space-size=768"])
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + PAGE)
    pg.wait_for_function("window.READY===true", timeout=120000)
    return b, pg, errs


def timeline():
    return json.load(open(os.path.join(ROOT, "build/timeline.json"), encoding="utf-8"))["chapters"]


def shot(pg, ch, t):
    pg.evaluate(f"setChapter({ch})")
    d = pg.evaluate(f"frame({t:.4f})")
    return base64.b64decode(d.split(",", 1)[1])


def test(ch, times, cols=4):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    out = os.path.join(ROOT, "build/test")
    os.makedirs(out, exist_ok=True)
    ims = []
    with sync_playwright() as p:
        b, pg, errs = open_page(p)
        t0 = time.time()
        for i, t in enumerate(times):
            im = Image.open(io.BytesIO(shot(pg, ch, t))).convert("RGB")
            im.save(os.path.join(out, f"ch{ch:02d}_{i:02d}.jpg"), quality=90)
            ims.append((t, im))
        ms = (time.time() - t0) * 1000 / max(1, len(times))
        b.close()
    if errs:
        print("JS:", errs[:6])
    sheet(ims, os.path.join(out, f"sheet_ch{ch:02d}.jpg"), cols)
    print(f"ch{ch} {len(times)} stills, {ms:.0f} ms/frame -> build/test/sheet_ch{ch:02d}.jpg")


def sheet(ims, path, cols=4, tw=480):
    from PIL import Image, ImageDraw
    th = tw * 9 // 16
    rows = (len(ims) + cols - 1) // cols
    sh = Image.new("RGB", (cols * tw + (cols + 1) * 6, rows * (th + 26) + 6), (40, 40, 40))
    d = ImageDraw.Draw(sh)
    for i, (label, im) in enumerate(ims):
        x, y = 6 + (i % cols) * (tw + 6), 6 + (i // cols) * (th + 26)
        sh.paste(im.resize((tw, th)), (x, y))
        d.text((x + 4, y + th + 4), str(label), fill=(230, 230, 230))
    sh.save(path, quality=88)


def contact():
    from PIL import Image
    from playwright.sync_api import sync_playwright
    ims = []
    with sync_playwright() as p:
        b, pg, _ = open_page(p)
        for c in timeline():
            n = 6
            for k in range(n):
                t = 0.6 + (c["end"] - 1.2) * (k + 0.5) / n
                ims.append((f"ch{c['id']} {t:.1f}s", Image.open(io.BytesIO(shot(pg, c["id"], t))).convert("RGB")))
        b.close()
    os.makedirs(os.path.join(ROOT, "qc"), exist_ok=True)
    sheet(ims, os.path.join(ROOT, "qc/contact_sheet.jpg"), cols=6, tw=400)
    print("qc/contact_sheet.jpg", len(ims))


def worker(jobs, fps):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg, errs = open_page(p)
        try:
            for ch, part, a, z in jobs:
                out = os.path.join(CHD, f"ch{ch:02d}_p{part}.mp4")
                if os.path.exists(out + ".done"):
                    continue
                pg.evaluate(f"setChapter({ch})")
                ff = subprocess.Popen(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg",
                                       "-framerate", str(fps), "-i", "-", "-vf", VF709, "-c:v", "libx264", "-preset", "medium",
                                       "-crf", "14", "-pix_fmt", "yuv420p", "-profile:v", "high", "-threads", "2", "-r", str(fps),
                                       "-g", str(fps * 2), "-x264-params", "aq-mode=3", "-color_primaries", "bt709",
                                       "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", out],
                                      stdin=subprocess.PIPE)
                t0 = time.time()
                for i in range(a, z):
                    d = pg.evaluate(f"frame({i / fps:.6f})")
                    ff.stdin.write(base64.b64decode(d.split(",", 1)[1]))
                ff.stdin.close()
                if ff.wait() != 0:
                    raise SystemExit(f"ffmpeg failed ch{ch} part {part}")
                open(out + ".done", "w").write(f"{a} {z}\n")
                print(f"ch{ch} part {part} frames {a}-{z} {round((time.time() - t0) / max(1, z - a) * 1000)} ms/f", flush=True)
            if errs:
                print("JS:", errs[:4], flush=True)
        finally:
            b.close()


def render(chs, fps, nw, parts):
    tl = {c["id"]: c for c in timeline()}
    os.makedirs(CHD, exist_ok=True)
    jobs = []
    for ch in chs:
        n = int(round(tl[ch]["end"] * fps))
        edges = [round(n * k / parts) for k in range(parts + 1)]
        jobs += [(ch, k, edges[k], edges[k + 1]) for k in range(parts)]
        json.dump({"fps": fps, "frames": n, "parts": parts, "end": tl[ch]["end"]}, open(os.path.join(CHD, f"ch{ch:02d}.json"), "w"))
    kill()
    ps = [Process(target=worker, args=(jobs[w::nw], fps)) for w in range(nw)]
    [x.start() for x in ps]
    [x.join() for x in ps]
    kill()
    for ch in chs:
        meta = json.load(open(os.path.join(CHD, f"ch{ch:02d}.json")))
        segs = [os.path.join(CHD, f"ch{ch:02d}_p{k}.mp4") for k in range(meta["parts"])]
        if not all(os.path.exists(s + ".done") for s in segs):
            print(f"ch{ch}: parts missing")
            continue
        lst = os.path.join(CHD, f"ch{ch:02d}.txt")
        open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                        os.path.join(CHD, f"ch{ch:02d}.mp4")], check=True)
        for s in segs:
            os.remove(s)
        print(f"ch{ch}.mp4 done ({meta['frames']} frames)")


def concat(audio, out):
    """Each chapter lifted to 1440p (resumable, ~7 minutes a call: "AGAIN" = run it again), then one file."""
    tl = timeline()
    total = sum(c["end"] for c in tl)
    kbps = up_kbps(total)
    miss = [c["id"] for c in tl if not os.path.exists(os.path.join(CHD, "ch%02d.mp4" % c["id"]))]
    if miss:
        sys.exit(f"chapters not rendered: {miss}")
    t0, left = time.time(), []
    for c in tl:
        src, dst = os.path.join(CHD, "ch%02d.mp4" % c["id"]), os.path.join(CHD, "ch%02d_1440.mp4" % c["id"])
        if lifted(src, dst):
            continue
        if time.time() - t0 > UP_BUDGET_S:
            left.append(c["id"])
            continue
        t1 = time.time()
        subprocess.run(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-an",
                        *up_args(kbps, True), dst + ".part.mp4"], check=True)
        os.replace(dst + ".part.mp4", dst)
        print(f"ch{c['id']:02d} lifted to 1440p in {time.time() - t1:.0f} s", flush=True)
    if left:
        sys.exit(f"AGAIN: {len(left)} chapters still to lift to 1440p {left}; run --concat again (lifted ones are kept)")
    lst = os.path.join(CHD, "all.txt")
    open(lst, "w").write("".join("file '" + os.path.join(CHD, "ch%02d_1440.mp4" % c["id"]) + "'\n" for c in tl))
    cmd = ["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", f"{AUDIO_K}k", "-ar", "48000", "-ac", "2",
           "-t", f"{total:.3f}", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    size = os.path.getsize(out)
    print("wrote", out, f"2560x1440, {size / 1e6:.0f} MB, video cap {kbps} kbit/s")
    if size > 1024 ** 3:
        sys.exit("the file is over YouTube upload_long's 1 GiB: tell the hub (never cut it by hand)")


if __name__ == "__main__":
    if "--test" in sys.argv:
        ch = int(arg("--test", "0"))
        times = [float(x) for x in sys.argv[sys.argv.index("--test") + 2].split(",")]
        kill()
        test(ch, times)
        kill()
    elif "--sheet" in sys.argv:
        kill()
        contact()
        kill()
    elif "--render" in sys.argv:
        render([int(x) for x in arg("--render", "0").split(",")], int(arg("--fps", 30)), min(2, int(arg("--workers", 2))),
               int(arg("--parts", 4)))
    elif "--concat" in sys.argv:
        concat(arg("--audio", os.path.join(ROOT, "build/mix.wav")), arg("--out", os.path.join(ROOT, "out/video.mp4")))
