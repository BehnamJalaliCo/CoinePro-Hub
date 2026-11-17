"""One frame every 2 s of the whole timeline -> qc/every2s.jpg (cols 8) and the ms per frame"""
import io, json, sys, time
sys.path.insert(0, 'motion')
import render as R
from PIL import Image
from playwright.sync_api import sync_playwright
tl = R.timeline(); ims = []; off = 0.0; step = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
with sync_playwright() as p:
    b, pg, errs = R.open_page(p); t0 = time.time(); n = 0
    for c in tl:
        t = 0.5
        while t < c['end']:
            ims.append((f"{off + t:.0f}s ch{c['id']}", Image.open(io.BytesIO(R.shot(pg, c['id'], t))).convert('RGB'))); t += step; n += 1
        off += c['end']
    print('ms/frame', round((time.time() - t0) * 1000 / max(1, n)), 'JS', errs[:4])
    b.close()
R.sheet(ims, 'qc/every2s.jpg', cols=8, tw=300)
print(len(ims))
