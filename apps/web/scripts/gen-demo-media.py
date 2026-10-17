#!/usr/bin/env python3
"""Demo attachments for mock mode (src/lib/api/mock-media.ts): two pictures and one voice note, as data URLs.

Development only. The fixtures module never reaches a production build (next.config aliases it away), and the
Android debug build reads the same file through scripts/dump_demo_fixtures.mjs.
Needs Pillow (with WebP) and ffmpeg. Deterministic: the same script writes the same bytes.
"""
import base64
import io
import math
import random
import subprocess
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / 'src/lib/api/mock-media.ts'
W, H = 960, 600


def webp(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, 'WEBP', quality=70, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()


def chart() -> Image.Image:
    """A gold H1 chart with the owner's circle around the drop: "what happened here?"."""
    rnd = random.Random(7)
    img = Image.new('RGB', (W, H), (17, 19, 24))
    d = ImageDraw.Draw(img)
    for y in range(80, H - 40, 70):
        d.line([(40, y), (W - 40, y)], fill=(34, 37, 45), width=1)
    for x in range(40, W - 40, 120):
        d.line([(x, 40), (x, H - 40)], fill=(28, 31, 38), width=1)
    price, pts = 300.0, []
    for i in range(46):
        drift = -9 if 30 <= i <= 34 else (2.2 if i > 34 else 1.1)
        o = price
        c = o + drift + rnd.uniform(-7, 7)
        hi, lo = max(o, c) + rnd.uniform(2, 9), min(o, c) - rnd.uniform(2, 9)
        pts.append((o, hi, lo, c))
        price = c
    top, bot = max(p[1] for p in pts), min(p[2] for p in pts)
    sy = lambda v: 70 + (top - v) / (top - bot) * (H - 160)
    for i, (o, hi, lo, c) in enumerate(pts):
        x = 64 + i * 18.6
        up = c >= o
        col = (46, 160, 120) if up else (214, 84, 84)
        d.line([(x, sy(hi)), (x, sy(lo))], fill=col, width=2)
        y0, y1 = sorted((sy(o), sy(c)))
        d.rounded_rectangle([x - 5, y0, x + 5, max(y1, y0 + 2)], radius=2, fill=col)
    cx, cy = 64 + 32 * 18.6, sy(pts[32][3])
    ring = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    r = ImageDraw.Draw(ring)
    r.ellipse([cx - 92, cy - 70, cx + 92, cy + 82], outline=(212, 175, 92, 255), width=6)
    r.line([(cx + 120, cy - 150), (cx + 74, cy - 74)], fill=(212, 175, 92, 255), width=6)
    r.polygon([(cx + 66, cy - 60), (cx + 92, cy - 82), (cx + 70, cy - 90)], fill=(212, 175, 92, 255))
    img.paste(ring, (0, 0), ring)
    return img


def sketch() -> Image.Image:
    """A phone photo of a paper sketch: the sign-up form, with the slow step circled."""
    img = Image.new('RGB', (W, H), (232, 226, 214))
    noise = Image.effect_noise((W, H), 18).convert('RGB')
    img = Image.blend(img, noise, 0.06)
    d = ImageDraw.Draw(img)
    ink = (52, 58, 72)
    px, py, pw, ph = 330, 40, 300, 520
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=34, outline=ink, width=5)
    d.line([(px + 120, py + 22), (px + 180, py + 22)], fill=ink, width=5)
    y = py + 90
    for w in (200, 230, 230, 230):
        d.rounded_rectangle([px + 34, y, px + 34 + w, y + 44], radius=10, outline=ink, width=4)
        y += 74
    d.rounded_rectangle([px + 34, y + 10, px + pw - 34, y + 62], radius=14, fill=(196, 160, 82), outline=ink, width=4)
    hx, hy = px + pw / 2, y + 36
    d.ellipse([hx - 150, hy - 58, hx + 150, hy + 62], outline=(196, 52, 52), width=7)
    d.line([(hx + 140, hy - 30), (hx + 240, hy - 110)], fill=(196, 52, 52), width=6)
    d.line([(hx + 268, hy - 210), (hx + 268, hy - 150)], fill=(196, 52, 52), width=8)
    d.ellipse([hx + 262, hy - 136, hx + 274, hy - 124], fill=(196, 52, 52))
    return img.filter(ImageFilter.GaussianBlur(0.6)).rotate(-1.6, resample=Image.BICUBIC, fillcolor=(222, 216, 204))


def voice() -> tuple[str, float]:
    """3.4 s of a soft, speech-like murmur (syllable envelope over a voiced tone), AAC in MP4."""
    rate, secs = 16000, 3.4
    rnd = random.Random(3)
    sylls, t = [], 0.12
    while t < secs - 0.25:
        dur = rnd.uniform(0.14, 0.3)
        sylls.append((t, dur, rnd.uniform(150, 190)))
        t += dur + rnd.uniform(0.03, 0.18)
    frames = bytearray()
    for n in range(int(rate * secs)):
        s = n / rate
        v = 0.0
        for st, du, f0 in sylls:
            if st <= s < st + du:
                env = math.sin(math.pi * (s - st) / du) ** 1.5
                ph = 2 * math.pi * f0 * s
                v += env * (0.55 * math.sin(ph) + 0.25 * math.sin(2 * ph) + 0.12 * math.sin(3 * ph) + 0.06 * math.sin(5 * ph))
        frames += int(max(-1, min(1, v * 0.5)) * 32767).to_bytes(2, 'little', signed=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav, m4a = Path(tmp) / 'v.wav', Path(tmp) / 'v.m4a'
        with wave.open(str(wav), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '24k', '-ac', '1',
                        '-map_metadata', '-1', '-fflags', '+bitexact', '-flags:a', '+bitexact', str(m4a)], check=True)
        return 'data:audio/mp4;base64,' + base64.b64encode(m4a.read_bytes()).decode(), secs


def main() -> None:
    a, secs = voice()
    OUT.write_text(
        '// Generated by scripts/gen-demo-media.py — demo attachments for mock mode only. Do not edit.\n'
        f"export const DEMO_CHART = {{ url: '{webp(chart())}', width: {W}, height: {H} }};\n"
        f"export const DEMO_SKETCH = {{ url: '{webp(sketch())}', width: {W}, height: {H} }};\n"
        f"export const DEMO_VOICE = {{ url: '{a}', seconds: {secs} }};\n",
        encoding='utf-8',
    )
    print(f'wrote {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT} ({OUT.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
