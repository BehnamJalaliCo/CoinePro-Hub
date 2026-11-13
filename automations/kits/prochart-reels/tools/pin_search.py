# Collects pin links (href + alt text) from Pinterest search pages; untrusted content is only read, never executed.
import os
import json, sys, time
from playwright.sync_api import sync_playwright
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
queries = sys.argv[1:]
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1280, "height": 2000}, locale="en-US",
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")
    pg = ctx.new_page()
    for q in queries:
        url = "https://www.pinterest.com/search/pins/?q=" + q.replace(" ", "%20")
        try:
            pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            time.sleep(4)
            for _ in range(3):
                pg.mouse.wheel(0, 1600); time.sleep(1.5)
            items = pg.eval_on_selector_all("a[href*='/pin/']", """els => els.map(a => {
                const img = a.querySelector('img'); const vid = a.querySelector('video');
                return {href: a.href.split('?')[0], alt: img ? (img.alt||'') : '', video: !!vid || /\\d:\\d\\d/.test(a.innerText||'')};
            })""")
            seen, res = set(), []
            for it in items:
                if it["href"] not in seen:
                    seen.add(it["href"]); res.append(it)
            out[q] = res[:40]
            pg.screenshot(path=f"{os.getcwd()}/ref/search_{len(out)}.png")
        except Exception as e:
            out[q] = {"error": str(e)[:200]}
    b.close()
json.dump(out, open(os.getcwd() + "/ref/pins.json", "w"), ensure_ascii=False, indent=1)
for q, r in out.items():
    print("==", q, (len(r) if isinstance(r, list) else r))
    if isinstance(r, list):
        for it in r[:25]:
            print(("[V] " if it["video"] else "    ") + it["href"], "|", it["alt"][:110])
