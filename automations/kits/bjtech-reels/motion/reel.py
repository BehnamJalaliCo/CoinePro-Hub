# -*- coding: utf-8 -*-
"""@behnamjalali.tech LUMEN engine (KIT/motion/reel.py): the day's scenes (motion/scenes.js) on the kit's stage
(KIT/motion/stage.html) -> stills, a contact sheet, the 60 fps render and the final file. One engine for both
sizes: the reel (1080x1920) and, with an empty file motion/WIDE in the day's folder, the long YouTube video
(1920x1080; the long-video kit renders it chapter by chapter).

Run in the day's folder with the render venv (PY = /home/studio/kits/prochart-reels/venv-render/bin/python),
PLAYWRIGHT_BROWSERS_PATH=/home/studio/kits/prochart-reels/ms-playwright, under `nice`:
  PY -I KIT/motion/reel.py --test 0.4,1.2,3.5,...      stills -> build/test/NN.jpg + build/test_sheet.jpg (with times)
  PY -I KIT/motion/reel.py --timeline                  build/timeline.json (END, the shots, the beats) for sound.py
  PY -I KIT/motion/reel.py --render [--workers 2] [--chunks 8] [--fps 60]   -> build/seg/segNN.mp4 (resumable)
  PY -I KIT/motion/reel.py --encode [--audio build/mix.wav] [--out out/video.mp4]
  PY -I KIT/motion/reel.py --sheet [--step 2] [--video out/video.mp4] [--out qc/contact_sheet.jpg]
  PY -I KIT/motion/reel.py --frames 8 [--video out/video.mp4]  -> build/final_frames.jpg (random frames of the file)

What it puts into the page (motion/reel.html, rebuilt on every call):
- the words with their real times: direction/word_times.json (tools/word_times.py on qc/voice_final.wav);
- the stills: every picture in assets/use/ (jpg/png/webp), by its file name without extension (upscaled with
  Lanczos so a camera push stays sharp, cached in build/assets/; a PNG keeps its alpha);
- the fonts: Estedad (Persian), Geist (Latin), Geist Mono (code) from /home/studio/kits/fonts-bj (OFL);
- the page's round mark (COMMON/brand/profile_round.png) for the end card;
- the day's scenes: motion/scenes.js (CONFIG + SHOT(...) calls; the stage's header is the API).
HQ render rule: at most 2 browsers, each closed after its work (never a pkill: another session may be rendering),
frames piped straight into ffmpeg.
"""
import base64
import io
import json
import os
import random
import subprocess
import sys
import time
from multiprocessing import Process

ROOT = os.environ.get("REEL_ROOT") or os.getcwd()
KIT = os.environ.get("BJ_KIT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMON = os.environ.get("BJ_COMMON", "/home/studio/kits/bjtech-common")
FD = os.environ.get("BJ_FONTS", "/home/studio/kits/fonts-bj") + "/"
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
STAGE = os.environ.get("BJ_STAGE", "/home/studio/kits/bjtech-reels/motion/stage.html")
if not os.path.exists(STAGE):
    STAGE = os.path.join(KIT, "motion", "stage.html")
PAGE = os.path.join(ROOT, "motion", "reel.html")
SEG = os.path.join(ROOT, "build", "seg")
WIDE = os.path.exists(os.path.join(ROOT, "motion", "WIDE"))
W, H = (1920, 1080) if WIDE else (1080, 1920)
FONTS = {"EST:300": "Estedad-Light.ttf", "EST:400": "Estedad-Regular.ttf", "EST:500": "Estedad-Medium.ttf",
         "EST:600": "Estedad-SemiBold.ttf", "EST:700": "Estedad-Bold.ttf", "EST:800": "Estedad-ExtraBold.ttf",
         "EST:900": "Estedad-Black.ttf", "GEI:400": "Geist-Regular.ttf", "GEI:500": "Geist-Medium.ttf",
         "GEI:600": "Geist-SemiBold.ttf", "GEI:700": "Geist-Bold.ttf", "GEI:800": "Geist-Black.ttf",
         "GEI:900": "Geist-Black.ttf", "GMO:400": "GeistMono-Regular.ttf", "GMO:500": "GeistMono-Medium.ttf",
         "GMO:600": "GeistMono-SemiBold.ttf", "GMO:700": "GeistMono-Bold.ttf"}
# a still covers 1.25x the frame (a push-in stays sharp)
MIN_W, MIN_H, MAX_W = (2400, 1350, 3000) if WIDE else (1350, 2400, 1700)
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d


def b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def still(path):
    """A still as a data URL, upscaled (Lanczos) to cover MIN_W x MIN_H, cached in build/assets/."""
    from PIL import Image
    name = os.path.splitext(os.path.basename(path))[0]
    os.makedirs(os.path.join(ROOT, "build", "assets"), exist_ok=True)
    im = Image.open(path)
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    ext = "png" if alpha else "jpg"
    cache = os.path.join(ROOT, "build", "assets", f"{name}.{ext}")
    if not os.path.exists(cache) or os.path.getmtime(cache) < os.path.getmtime(path):
        im = im.convert("RGBA" if alpha else "RGB")
        k = max(MIN_W / im.width, MIN_H / im.height, 1.0)
        k = min(k, MAX_W / im.width) if im.width * k > MAX_W and not alpha else k
        if k > 1.0:
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        if alpha:
            im.save(cache, "PNG", optimize=True)
        else:
            im.save(cache, "JPEG", quality=92, subsampling=0)
    mime = "image/png" if alpha else "image/jpeg"
    return name, f"data:{mime};base64,{b64(cache)}"


def logo(name="profile_round.png", size=400):
    """A round mark of COMMON/brand as a data URL: profile_round.png (the end card draws its own ring around it) or
    ⟨2026-11-19⟩ logo_round.png (with its thin spectral rim: the handle pill's logo, never a coloured dot)."""
    from PIL import Image
    p = os.path.join(COMMON, "brand", name)
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def build():
    wt = json.load(open(os.path.join(ROOT, "direction", "word_times.json"), encoding="utf-8"))
    vb = os.path.join(ROOT, "direction", "videobar.json")  # a long video's chapter: its place in the whole (long.py bar)
    data = {"dur": wt.get("duration"), "size": "wide" if WIDE else "reel",
            "videobar": json.load(open(vb, encoding="utf-8")) if os.path.exists(vb) else None,
            "lines": [{"n": l["n"], "text": l.get("text", ""), "s": l["start"], "e": l["end"],
                       "words": [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in l["words"]]} for l in wt["lines"]]}
    use = os.path.join(ROOT, "assets", "use")
    imgs = dict(still(os.path.join(use, f)) for f in sorted(os.listdir(use))
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))) if os.path.isdir(use) else {}
    cache = {}
    fonts = {k: cache.setdefault(v, b64(FD + v)) for k, v in FONTS.items()}
    html = open(STAGE, encoding="utf-8").read()
    scenes = open(os.path.join(ROOT, "motion", "scenes.js"), encoding="utf-8").read()
    for key in ("/*DATA*/", "/*IMAGES*/", "/*FONTS*/", "/*LOGO*/", "/*LOGOR*/", "/*SCENES*/"):
        assert key in html, key
    html = (html.replace("/*DATA*/", json.dumps(data, ensure_ascii=False)).replace("/*IMAGES*/", json.dumps(imgs))
            .replace("/*FONTS*/", json.dumps(fonts)).replace("/*LOGO*/", json.dumps(logo()))
            .replace("/*LOGOR*/", json.dumps(logo("logo_round.png", 160)))
            .replace("/*SCENES*/", scenes))
    os.makedirs(os.path.dirname(PAGE), exist_ok=True)
    open(PAGE, "w", encoding="utf-8").write(html)
    return PAGE


def kill():
    """Nothing to kill: every browser this tool opens is closed by it (another session's are never touched)."""


def open_page(p):
    b = p.chromium.launch(executable_path=CHROME, headless=True,
                          args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--js-flags=--max-old-space-size=768"])
    pg = b.new_page(viewport={"width": W, "height": H})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + PAGE)
    pg.wait_for_function("window.READY===true || !!window.BOOT_ERROR", timeout=120000)
    if pg.evaluate("window.BOOT_ERROR || ''"):
        raise SystemExit("the stage did not start: " + pg.evaluate("window.BOOT_ERROR"))
    return b, pg, errs


def grab(pg, t):
    d = pg.evaluate(f"frame({t:.6f})")
    return base64.b64decode(d.split(",", 1)[1])


def label_sheet(items, path, cols=6, tw=270):
    """items: [(label, PIL image)] -> one sheet with the label under each frame."""
    from PIL import Image, ImageDraw
    if WIDE:
        tw = tw * 16 // 9
    th = tw * H // W
    rows = (len(items) + cols - 1) // cols
    sh = Image.new("RGB", (cols * tw + (cols + 1) * 6, rows * (th + 28) + 6), (34, 34, 38))
    d = ImageDraw.Draw(sh)
    for i, (lab, im) in enumerate(items):
        x, y = 6 + (i % cols) * (tw + 6), 6 + (i // cols) * (th + 28)
        sh.paste(im.convert("RGB").resize((tw, th)), (x, y))
        d.text((x + 6, y + th + 6), str(lab), fill=(235, 235, 235))
    sh.save(path, quality=88)


def timeline(pg):
    tl = pg.evaluate("timeline()")
    json.dump(tl, open(os.path.join(ROOT, "build", "timeline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return tl


def test(times):
    from PIL import Image
    from playwright.sync_api import sync_playwright
    out = os.path.join(ROOT, "build", "test")
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))
    items = []
    with sync_playwright() as p:
        b, pg, errs = open_page(p)
        timeline(pg)
        t0 = time.time()
        for k, t in enumerate(times):
            raw = grab(pg, t)
            open(os.path.join(out, f"{k:02d}.jpg"), "wb").write(raw)
            items.append((f"{t:.2f}s", Image.open(io.BytesIO(raw))))
        ms = (time.time() - t0) * 1000 / max(1, len(times))
        b.close()
    label_sheet(items, os.path.join(ROOT, "build", "test_sheet.jpg"), cols=int(arg("--cols", "6")))
    print(f"{len(times)} stills, {ms:.0f} ms/frame -> build/test_sheet.jpg", "JS errors:", errs[:6])


def worker(chunks, fps):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg, errs = open_page(p)
        try:
            for ci, a, z in chunks:
                out = os.path.join(SEG, f"seg{ci:02d}.mp4")
                if os.path.exists(out + ".done"):
                    continue
                ff = subprocess.Popen(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg",
                                       "-framerate", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                                       "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "5.1", "-threads", "2",
                                       "-r", str(fps), "-color_primaries", "bt709", "-color_trc", "bt709",
                                       "-colorspace", "bt709", out], stdin=subprocess.PIPE)
                t0 = time.time()
                for i in range(a, z):
                    for attempt in range(4):
                        try:
                            data = grab(pg, i / fps)
                            break
                        except Exception as e:  # noqa: BLE001 - reopen the browser, try the frame again
                            print("retry", i, str(e)[:80], flush=True)
                            try:
                                b.close()
                            except Exception:  # noqa: BLE001
                                pass
                            time.sleep(1)
                            b, pg, errs = open_page(p)
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


def render():
    from playwright.sync_api import sync_playwright
    fps = int(arg("--fps", "60"))
    os.makedirs(SEG, exist_ok=True)
    kill()
    with sync_playwright() as p:
        b, pg, _ = open_page(p)
        end = timeline(pg)["end"]
        b.close()
    n = int(round(end * fps))
    nc = int(arg("--chunks", "8"))
    k = min(2, int(arg("--workers", "2")))  # HQ rule: never more than 2 browsers
    plan = os.path.join(SEG, "plan.json")
    bounds = [(ci, n * ci // nc, n * (ci + 1) // nc) for ci in range(nc)]
    if os.path.exists(plan) and json.load(open(plan)).get("n") != n:
        raise SystemExit("the timeline changed since the last render: rm -rf build/seg, then render again")
    json.dump({"fps": fps, "n": n, "end": end, "chunks": bounds}, open(plan, "w"))
    procs = [Process(target=worker, args=(bounds[j::k], fps)) for j in range(k)]
    [pr.start() for pr in procs]
    [pr.join() for pr in procs]
    kill()
    done = [c for c in bounds if os.path.exists(os.path.join(SEG, f"seg{c[0]:02d}.mp4.done"))]
    print("chunks done", len(done), "of", nc, "exit", [pr.exitcode for pr in procs])


def encode():
    plan = json.load(open(os.path.join(SEG, "plan.json")))
    segs = [os.path.join(SEG, f"seg{c[0]:02d}.mp4") for c in plan["chunks"]]
    miss = [s for s in segs if not os.path.exists(s + ".done")]
    if miss:
        raise SystemExit(f"missing chunks {miss}")
    lst = os.path.join(SEG, "list.txt")
    open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
    audio = arg("--audio", os.path.join(ROOT, "build", "mix.wav"))
    out = arg("--out", os.path.join(ROOT, "out", "video.mp4"))
    end = plan["end"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", audio,
                    "-filter_complex", f"[1:a]apad=whole_dur={end},atrim=0:{end},aformat=channel_layouts=stereo[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-t", f"{end:.3f}", "-movflags", "+faststart", out], check=True)
    print("wrote", out, f"{end:.2f}s")


def video_frames(video, times):
    from PIL import Image
    out = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-f", "image2pipe",
                              "-c:v", "mjpeg", "-q:v", "3", "-"], capture_output=True, check=True).stdout
        out.append((f"{t:.1f}s", Image.open(io.BytesIO(raw))))
    return out


def duration(video):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                                capture_output=True, text=True, check=True).stdout)


def sheet():
    video = arg("--video", os.path.join(ROOT, "out", "video.mp4"))
    step = float(arg("--step", "2"))
    dur = duration(video)
    times = [round(k * step, 3) for k in range(int(dur // step) + 1) if k * step < dur - 0.05]
    out = arg("--out", os.path.join(ROOT, "qc", "contact_sheet.jpg"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    label_sheet(video_frames(video, times), out, cols=int(arg("--cols", "7")), tw=240)
    print(out, len(times), "frames, every", step, "s")


def frames():
    video = arg("--video", os.path.join(ROOT, "out", "video.mp4"))
    dur = duration(video)
    n = int(arg("--frames", "8"))
    times = sorted(round(random.uniform(0.2, dur - 0.2), 2) for _ in range(n))
    label_sheet(video_frames(video, times), os.path.join(ROOT, "build", "final_frames.jpg"), cols=4, tw=300)
    print("build/final_frames.jpg", times)


def main():
    if "--sheet" in sys.argv:
        return sheet()
    if "--frames" in sys.argv:
        return frames()
    if "--encode" in sys.argv:
        return encode()
    build()
    if "--test" in sys.argv:
        kill()
        test([float(x) for x in arg("--test", "1").split(",")])
        kill()
    elif "--timeline" in sys.argv:
        from playwright.sync_api import sync_playwright
        kill()
        with sync_playwright() as p:
            b, pg, errs = open_page(p)
            tl = timeline(pg)
            b.close()
        kill()
        print(f"END {tl['end']:.2f}s, {len(tl['shots'])} shots; longest shot {tl['longest']:.2f}s", "JS errors:", errs[:6])
    elif "--render" in sys.argv:
        render()
    else:
        print("built", PAGE)


if __name__ == "__main__":
    main()
