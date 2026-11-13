# Reads pin ids, titles and durations from a Pinterest search grid (read-only).
import os
import json, re, sys, time
from playwright.sync_api import sync_playwright
CHROME = "/home/studio/kits/prochart-reels/ms-playwright/chromium-1243/chrome-linux64/chrome"
q = sys.argv[1]; tag = sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1280, "height": 2200}, locale="en-US",
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")
    pg = ctx.new_page()
    pg.goto("https://www.pinterest.com/search/pins/?q=" + q.replace(" ", "%20"), timeout=45000, wait_until="domcontentloaded")
    time.sleep(5)
    html = pg.content()
    # pin ids from any attribute or relative link
    ids = []
    for m in re.finditer(r'/pin/(\d{6,})', html):
        if m.group(1) not in ids: ids.append(m.group(1))
    items = pg.eval_on_selector_all("[data-grid-item], [data-test-id='pin'], [data-test-id='pinWrapper']", """els => els.map(e => {
        const img = e.querySelector('img'); const a = e.querySelector('a');
        const t = (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,60);
        return {a: a ? a.getAttribute('href') : null, alt: img ? (img.alt||'') : '', text: t,
                attrs: Array.from(e.attributes).map(x => x.name + '=' + x.value).join(' ').slice(0,200)};
    })""")
    pg.screenshot(path=f"{os.getcwd()}/ref/{tag}.png")
    b.close()
json.dump({"ids": ids, "items": items}, open(f"{os.getcwd()}/ref/{tag}.json", "w"), ensure_ascii=False, indent=1)
print("ids:", len(ids), ids[:30])
print("items:", len(items))
for it in items[:30]:
    print(it["a"], "|", it["text"][:20], "|", it["alt"][:100])
