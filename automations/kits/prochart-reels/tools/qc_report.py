#!/usr/bin/env python3
"""Render the voice-QC report (two brand colours only) to PDF.

Usage: python3 -I tools/qc_report.py QC.json VERDICTS.json OUT.pdf
VERDICTS.json: {"title":..., "sub":..., "summary":[...], "lines": {"1": ["ok"|"warn"|"bad", note], ...},
                "after":[...], "tech": [[check, value, "ok"|"warn"|"bad", note], ...] (optional)}
"""
import html
import json
import pathlib
import subprocess
import sys
import tempfile

CHROME = str(pathlib.Path.home() / ".cache/ms-playwright/chromium-1243/chrome-linux64/chrome")
FA = str.maketrans("0123456789%", "۰۱۲۳۴۵۶۷۸۹٪")

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #000000; }
body { font-family: "IRANYekanXFaNum", "IRANYekanX", sans-serif; color: #D4A64A; direction: rtl;
       font-size: 9.6pt; line-height: 1.9; padding: 14mm 13mm; }
h1 { font-size: 17pt; font-weight: 900; margin: 0 0 2px; }
.sub { font-size: 8.4pt; margin-bottom: 10px; }
.band { background: #D4A64A; color: #000000; border-radius: 10px; padding: 8px 12px; font-weight: 800; margin: 8px 0 12px; }
.box { border: 1.2px solid #D4A64A; border-radius: 10px; padding: 8px 12px; margin: 8px 0; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin-top: 6px; }
th { background: #D4A64A; color: #000000; font-weight: 800; font-size: 8.6pt; padding: 5px 6px; text-align: right; }
td { border-bottom: 1px solid #D4A64A; padding: 6px; vertical-align: top; font-size: 8.8pt; }
tr { break-inside: avoid; }
td.n { width: 22px; font-weight: 800; text-align: center; }
td.heard { opacity: 1; }
.tag { display: inline-block; border-radius: 6px; padding: 0 7px; font-weight: 800; font-size: 8.2pt; white-space: nowrap; }
.ok { border: 1.2px solid #D4A64A; }
.warn { background: #D4A64A; color: #000000; }
.bad { background: #D4A64A; color: #000000; outline: 2px solid #D4A64A; outline-offset: 2px; }
ul { margin: 4px 0; padding-right: 18px; }
h2 { font-size: 11pt; font-weight: 900; margin: 14px 0 4px; }
"""

TAG = {"ok": "درست", "warn": "شنیدن دوباره", "bad": "ایراد"}


def main() -> None:
    qc = json.load(open(sys.argv[1], encoding="utf-8"))
    v = json.load(open(sys.argv[2], encoding="utf-8"))
    out = pathlib.Path(sys.argv[3]).resolve()
    rows = []
    for ln in qc["lines"]:
        st, note = v["lines"].get(str(ln["n"]), ["ok", ""])
        rows.append(
            f"<tr><td class='n'>{str(ln['n']).translate(FA)}</td>"
            f"<td>{html.escape(ln['script'])}</td>"
            f"<td class='heard'>{html.escape(ln['heard'])}</td>"
            f"<td><span class='tag {st}'>{TAG[st]}</span>"
            f"{'<br>' + html.escape(note) if note else ''}</td></tr>"
        )
    summary = "".join(f"<li>{html.escape(s)}</li>" for s in v["summary"])
    after = "".join(f"<li>{html.escape(s)}</li>" for s in v.get("after", []))
    tech_rows = "".join(
        f"<tr><td>{html.escape(c)}</td><td>{html.escape(val).translate(FA)}</td>"
        f"<td><span class='tag {st}'>{TAG[st]}</span>{'<br>' + html.escape(nt) if nt else ''}</td></tr>"
        for c, val, st, nt in v.get("tech", []))
    tech = (f"<h2>سنجش فنی صدا</h2><table><tr><th>چه چیزی</th><th>عدد</th><th>نتیجه</th></tr>{tech_rows}</table>"
            if tech_rows else "")
    doc = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><h1>{html.escape(v['title'])}</h1><div class="sub">{html.escape(v['sub'])}</div>
<div class="band">{html.escape(v['band'])}</div>
<div class="box"><ul>{summary}</ul></div>
<h2>جمله‌به‌جمله</h2>
<table><tr><th>#</th><th>متن اصلی</th><th>آنچه شنیده شد</th><th>نتیجه</th></tr>{''.join(rows)}</table>
{tech}
<h2>قدم بعد</h2><div class="box"><ul>{after}</ul></div>
</body></html>"""
    with tempfile.TemporaryDirectory() as td:
        page = pathlib.Path(td) / "qc.html"
        page.write_text(doc, encoding="utf-8")
        subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={out}", page.as_uri()], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(out, out.stat().st_size)


if __name__ == "__main__":
    main()
