# Fetches a pin page's HTML and pulls media URLs (images/videos) and texts from its embedded data (read-only).
import re, sys, json, urllib.request
for u in sys.argv[1:]:
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36", "Accept-Language": "en-US"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    mp4 = sorted(set(re.findall(r'https://v1?\.pinimg\.com/videos/[^"\\\s]+?\.(?:mp4|m3u8)', html)))
    imgs = sorted(set(re.findall(r'https://i\.pinimg\.com/(?:originals|736x|564x)/[^"\\\s]+?\.(?:jpg|png|gif|webp)', html)))
    og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    title = re.search(r'"grid_title":"([^"]{0,200})"', html)
    desc = re.search(r'"description":"([^"]{0,400})"', html)
    dur = re.findall(r'"duration":(\d+)', html)[:3]
    print("==", u)
    print(" og:image:", og.group(1) if og else None)
    print(" title:", title.group(1) if title else None)
    print(" desc:", (desc.group(1)[:300] if desc else None))
    print(" duration_ms:", dur)
    print(" videos:", mp4[:6])
    print(" images:", imgs[:4])
