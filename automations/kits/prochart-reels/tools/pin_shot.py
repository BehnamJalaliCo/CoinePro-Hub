# Opens single pin pages (logged out), screenshots them and reads title/description (read-only).
import os
import json, sys, time
from playwright.sync_api import sync_playwright
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
urls = sys.argv[1:]
out = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1100, "height": 1400}, locale="en-US",
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")
    pg = ctx.new_page()
    for k, u in enumerate(urls):
        try:
            pg.goto(u, timeout=45000, wait_until="domcontentloaded"); time.sleep(6)
            pg.keyboard.press("Escape"); time.sleep(0.5)
            pg.evaluate("""() => { document.querySelectorAll('[role=dialog]').forEach(e => e.remove()); }""")
            info = pg.evaluate("""() => {
                const m = n => (document.querySelector(`meta[property="${n}"]`)||document.querySelector(`meta[name="${n}"]`)||{}).content || '';
                const v = document.querySelector('video');
                return {title: document.title, ogt: m('og:title'), ogd: m('og:description'), ogv: m('og:video'), type: m('og:type'),
                        video: !!v, vsrc: v ? (v.currentSrc || v.src || '') : '', dur: v ? v.duration : null,
                        w: v ? v.videoWidth : null, h: v ? v.videoHeight : null};
            }""")
            pg.screenshot(path=f"{os.getcwd()}/ref/pin_{k}.png")
            info["url"] = pg.url; out.append(info)
        except Exception as e:
            out.append({"url": u, "err": str(e)[:160]})
    b.close()
json.dump(out, open(os.getcwd() + "/ref/pins_detail.json", "w"), ensure_ascii=False, indent=1)
for o in out:
    print({k: (str(v)[:140] if isinstance(v, str) else v) for k, v in o.items()})
