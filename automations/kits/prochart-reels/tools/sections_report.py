#!/usr/bin/env python3
"""Generic two-colour (black + mustard) phone-sized Persian report.

Usage: python3 tools/sections_report.py <spec.json> <out.pdf>
spec: {title, sub, sections: [{band, boxes: [{head?, items?: [str], ordered?: bool,
                                              table?: {cols: [str], rows: [[str]]}, note?: str}]}]}
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
table { width: 100%; border-collapse: collapse; margin: 4px 0; }
th { background: #D4A64A; color: #000000; font-weight: 900; font-size: 8.6pt; padding: 3px 6px; text-align: right; }
td { border-bottom: 1px solid #D4A64A; padding: 3px 6px; font-size: 8.8pt; }
tr { break-inside: avoid; }
.note { font-size: 8.2pt; margin-top: 3px; }
b { font-weight: 900; }
"""


def esc(s: str) -> str:
    return html.escape(s)


def box(b: dict) -> str:
    parts = []
    if b.get("head"):
        parts.append(f"<b>{esc(b['head'])}</b>")
    if b.get("items"):
        tag = "ol" if b.get("ordered") else "ul"
        parts.append(f"<{tag}>" + "".join(f"<li>{esc(i)}</li>" for i in b["items"]) + f"</{tag}>")
    if b.get("table"):
        t = b["table"]
        head = "".join(f"<th>{esc(c)}</th>" for c in t["cols"])
        rows = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
        parts.append(f"<table><tr>{head}</tr>{rows}</table>")
    if b.get("note"):
        parts.append(f'<div class="note">{esc(b["note"])}</div>')
    return '<div class="box">' + "".join(parts) + "</div>"


def main() -> None:
    spec = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = pathlib.Path(sys.argv[2]).resolve()
    body = [f"<h1>{esc(spec['title'])}</h1>", f'<div class="sub">{esc(spec["sub"])}</div>']
    for s in spec["sections"]:
        body.append(f'<div class="band">{esc(s["band"])}</div>')
        body.extend(box(b) for b in s["boxes"])
    page = pathlib.Path(__file__).resolve().parent.parent / "build" / (out.stem + ".html")
    page.write_text(f'<!doctype html><html lang="fa"><head><meta charset="utf-8"><style>{CSS}</style></head>'
                    f"<body>{''.join(body)}</body></html>", encoding="utf-8")
    subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", page.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(out.name, out.stat().st_size)


if __name__ == "__main__":
    main()
