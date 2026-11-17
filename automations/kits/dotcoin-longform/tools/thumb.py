"""The YouTube thumbnail: ChatGPT's picture fitted to 1280x720 (centre crop on the ground) + the topic's real logo
in the empty top-left corner. usage: PY -I tools/thumb.py PICTURE LOGO.png|- [logo_height=128] -> out/thumbnail.jpg"""
import sys
from PIL import Image
src, logo = sys.argv[1], sys.argv[2]
lh = int(sys.argv[3]) if len(sys.argv) > 3 else 128
im = Image.open(src).convert('RGB')
W, H = 1280, 720
s = max(W / im.width, H / im.height)
im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
x0, y0 = (im.width - W) // 2, (im.height - H) // 2
im = im.crop((x0, y0, x0 + W, y0 + H))
if logo != '-':
    g = Image.open(logo).convert('RGBA')
    g = g.resize((int(g.width * lh / g.height), lh), Image.LANCZOS)
    im.paste(g, (56, 22), g)
im.save('out/thumbnail.jpg', quality=92, optimize=True)
print('out/thumbnail.jpg', im.size)
