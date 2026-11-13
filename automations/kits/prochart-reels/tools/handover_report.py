#!/usr/bin/env python3
"""Handover sheet (ProChart -> Smart Direct) for one reel, two colours only (black + mustard), phone-sized pages.

Usage: python3 tools/handover_report.py <spec.json> <out.pdf>
spec keys: title, sub, package[], replies[], dm_lines[], link, link_note, story[], after[], undo[]
"""
import html
import json
import pathlib
import subprocess
import sys

CHROME = str(pathlib.Path.home() / ".cache/ms-playwright/chromium-1243/chrome-linux64/chrome")

CSS = """
@page { size: 112mm 236mm; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #000000; }
body { font-family: "IRANYekanXFaNum", "IRANYekanX", sans-serif; color: #D4A64A; direction: rtl;
       font-size: 9.4pt; line-height: 1.85; padding: 9mm 7mm; }
h1 { font-size: 15pt; font-weight: 900; margin: 0 0 2px; line-height: 1.5; }
.sub { font-size: 8.4pt; margin-bottom: 8px; }
.band { background: #D4A64A; color: #000000; border-radius: 9px; padding: 5px 10px; font-weight: 900;
        font-size: 10.2pt; margin: 12px 0 6px; break-after: avoid; }
.box { border: 1.2px solid #D4A64A; border-radius: 9px; padding: 7px 10px; margin: 6px 0; break-inside: avoid; }
ul, ol { margin: 2px 0; padding-right: 16px; }
li { margin: 2px 0; }
.dm p { margin: 0; }
.link { font-family: "IRANYekanX", sans-serif; direction: ltr; unicode-bidi: embed; display: block; text-align: left;
        font-size: 7.6pt; word-break: break-all; border-top: 1px dashed #D4A64A; border-bottom: 1px dashed #D4A64A;
        padding: 3px 0; margin: 4px 0; }
.note { font-size: 8.2pt; }
b { font-weight: 900; }
"""


def esc(s: str) -> str:
    return html.escape(s)


def ul(items, tag="ul") -> str:
    return f"<{tag}>" + "".join(f"<li>{esc(i)}</li>" for i in items) + f"</{tag}>"


def main() -> None:
    spec = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = pathlib.Path(sys.argv[2]).resolve()
    link_span = f'<span class="link">{esc(spec["link"])}</span>'
    dm = "".join(link_span if l == "{LINK}" else f"<p>{esc(l)}</p>" for l in spec["dm_lines"])
    body = f"""
<h1>{esc(spec['title'])}</h1>
<div class="sub">{esc(spec['sub'])}</div>
<div class="band">۱. بسته‌ی انتشار، آماده‌ی «تأیید و انتشار» شما</div>
<div class="box">{ul(spec['package'])}</div>
<div class="band">۲. کامنت هوشمند: وقتی کسی «بازپخش» کامنت کرد</div>
<div class="box"><b>جواب زیر کامنتش</b> (به نوبت، تا تکراری دیده نشود):{ul(spec['replies'], 'ol')}</div>
<div class="box dm"><b>پیامی که به دایرکتش می‌رود:</b>{dm}
<span class="note">{esc(spec['link_note'])}</span></div>
<div class="band">۳. استوری</div>
<div class="box">{ul(spec['story'])}</div>
<div class="band">۴. بعد از انتشار، با دایرکت هوشمند</div>
<div class="box">{ul(spec['after'])}</div>
<div class="band">۵. برگشت‌پذیری</div>
<div class="box">{ul(spec['undo'])}</div>
"""
    page = pathlib.Path(__file__).resolve().parent.parent / "build" / "handover.html"
    page.write_text(f'<!doctype html><html lang="fa"><head><meta charset="utf-8"><style>{CSS}</style></head>'
                    f"<body>{body}</body></html>", encoding="utf-8")
    subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", page.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(out, out.stat().st_size)


if __name__ == "__main__":
    main()
