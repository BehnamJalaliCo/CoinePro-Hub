# Clicks grid items one by one to learn their pin URLs (read-only browsing).
import os
import json, sys, time
from playwright.sync_api import sync_playwright
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
q = sys.argv[1]; idxs = [int(x) for x in sys.argv[2].split(",")]; tag = sys.argv[3]
res = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1280, "height": 2200}, locale="en-US",
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")
    pg = ctx.new_page()
    search = "https://www.pinterest.com/search/pins/?q=" + q.replace(" ", "%20")
    for i in idxs:
        try:
            pg.goto(search, timeout=45000, wait_until="domcontentloaded"); time.sleep(4)
            pg.keyboard.press("Escape"); time.sleep(0.5)
            pg.evaluate("""() => { document.querySelectorAll('[role=dialog], [data-test-id=signup], [data-test-id=giftWrap]').forEach(e => e.remove()); }""")
            items = pg.query_selector_all("[data-grid-item]")
            if i >= len(items): res.append({"i": i, "err": "no item"}); continue
            items[i].scroll_into_view_if_needed(); items[i].click(force=True, timeout=8000)
            time.sleep(4)
            url = pg.url
            title = pg.title()
            pg.screenshot(path=f"{os.getcwd()}/ref/{tag}_{i}.png")
            res.append({"i": i, "url": url, "title": title})
        except Exception as e:
            res.append({"i": i, "err": str(e)[:160]})
    b.close()
json.dump(res, open(f"{os.getcwd()}/ref/{tag}.json", "w"), ensure_ascii=False, indent=1)
for r in res: print(r)
