# -*- coding: utf-8 -*-
"""bitmart — the cover FALLBACK only (cover/COVER_SYSTEM.md step 4): when ChatGPT wrote the Persian title wrong
three times, its fourth picture comes WITHOUT any Persian, and this sets the title on it in the family's exact
style: Anjoman Max SuperHeavy in ink navy, the key word in a rounded navy box with orange letters (DotCoin's chip
in bitmart's colours). Never his cut-out photo as a cover (the owner rejected the code-made covers, 2026-11-26).

usage (PY = /home/studio/kits/prochart-reels/venv-render/bin/python; in the day's folder):
  PY -I COMMON/tools/cover_make.py build/cover.json
build/cover.json = {"background": "in/cover_gpt.jpg", "title": ["ده هزار بیت‌کوین", "برای [دو تا پیتزا]"],
                    "y": 1380, "out": "out/cover.jpg"}   # [..] = the word in the box; y = the first line's baseline
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
COMMON = os.path.dirname(HERE)
PY = sys.executable

SCENE = r"""
const S = STORY, {B, W, H} = S, C0 = __COVER;
function chipLine(s, y, px) {   // one RTL line, centred; [..] in a rounded navy box with orange letters
  const parts = s.split(/(\[[^\]]+\])/).filter(Boolean);
  const ws = parts.map(q => S.measure(q.replace(/[\[\]]/g, ''), {kind: 'A', w: 990, px}) + (q.startsWith('[') ? px * 0.5 : 0));
  let x = W / 2 + ws.reduce((a, v) => a + v, 0) / 2;
  parts.forEach((q, i) => {
    if (q.startsWith('[')) {
      X.save(); X.fillStyle = B.nv; X.beginPath(); X.roundRect(x - ws[i], y - px * 0.95, ws[i], px * 1.28, px * 0.24); X.fill(); X.restore();
      S.txt(q.slice(1, -1), x - px * 0.25, y, {kind: 'A', w: 990, px, col: B.or});
    } else S.txt(q, x, y, {kind: 'A', w: 990, px, col: B.nv});
    x -= ws[i];
  });
}
const SHOTS = [{a: 0, b: 1, tr: 'cut', draw: () => {
  S.plate('assets/bg.jpg', {p: 0, push: [1, 1], grade: 0});
  const n = C0.title.length, px = n >= 3 ? 100 : 116, lh = px * 1.36;
  C0.title.forEach((ln, i) => chipLine(ln, (C0.y || 1380) + i * lh, px));
}}];
S.reel({shots: SHOTS, caps: [], hud: null, hudIn: 99, END: 1});
"""


def main() -> None:
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    out = os.path.abspath(spec.get("out", "out/cover.jpg"))
    root = tempfile.mkdtemp(prefix="bm_cover_", dir=os.path.abspath("build") if os.path.isdir("build") else None)
    try:
        os.makedirs(os.path.join(root, "motion"))
        os.makedirs(os.path.join(root, "assets"))
        shutil.copy(spec["background"], os.path.join(root, "assets", "bg.jpg"))
        cfg = {k: spec.get(k) for k in ("title", "y")}
        open(os.path.join(root, "motion", "scene.js"), "w", encoding="utf-8").write(
            f"const __COVER = {json.dumps(cfg, ensure_ascii=False)};\n" + SCENE)
        env = dict(os.environ, REEL_ROOT=root)
        subprocess.run([PY, "-I", os.path.join(COMMON, "motion", "story_engine.py"), "--test", "0.5", "--cols", "1"],
                       env=env, check=True, capture_output=True)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(root, "build", "stest", "00.jpg"), "-q:v", "2", out], check=True)
        print("wrote", out)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
