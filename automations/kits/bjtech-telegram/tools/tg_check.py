#!/usr/bin/env python3
"""The day's Telegram package, checked before delivery (stdlib only):
    python3 -I KIT/tools/tg_check.py out/
The same rules the hub applies when the package arrives (apps/api/src/hq_api/domain/tg_posts.py, the
authority): Telegram's HTML subset, visible lengths in UTF-16 units (a message 4096, a caption 1024), link
buttons only, polls, each named file present and of its kind and size, the hours in order 15 minutes apart;
plus the kit's own rule: every post ends with the signature line. Prints OK, or every fault and exits 1."""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SIGNATURE = "@behnamjalali_tech"
TEXT_MAX, CAPTION_MAX, BUTTON_TEXT, BUTTON_ROWS, BUTTONS_PER_ROW = 4096, 1024, 64, 4, 3
POLL_QUESTION, POLL_OPTION, POLL_EXPLANATION = 300, 100, 200
POSTS_MAX, PARTS_MAX, GAP_MIN, TOPIC_MAX = 12, 4, 15, 300
PHOTO_MAX, FILE_MAX, CLIP_MAX = 10 * 1024 * 1024, 50 * 1024 * 1024, 48 * 1024 * 1024
TYPES = ("brief", "tool", "prompt", "poll", "table", "clip", "voice", "tip", "longread", "breaking", "post")
ALLOWED = {"b": (), "strong": (), "i": (), "em": (), "u": (), "ins": (), "s": (), "strike": (), "del": (),
           "code": ("class",), "pre": (), "a": ("href",), "blockquote": ("expandable",), "tg-spoiler": (),
           "span": ("class",)}
LINK = re.compile(r"^https://[^\s<>\"']{3,1000}$")
HM = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
MAGIC = {"photo": (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"), "voice": (b"OggS",), "document": (b"%PDF-",)}


def utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


class Html(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open: list[str] = []
        self.errors: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            self.errors.append(f"<{tag}> is not Telegram HTML")
            return
        for k, v in attrs:
            if k not in ALLOWED[tag]:
                self.errors.append(f"attribute {k} on <{tag}>")
            elif tag == "a" and not LINK.match(str(v or "")):
                self.errors.append(f"<a href> must be https: {str(v)[:60]}")
            elif tag == "span" and v != "tg-spoiler":
                self.errors.append('<span> only with class="tg-spoiler"')
            elif tag == "code" and not re.fullmatch(r"language-[a-z0-9_+-]{1,30}", str(v or "")):
                self.errors.append("class on <code> is only language-…")
        self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in ALLOWED:
            if not self.open or self.open[-1] != tag:
                self.errors.append(f"</{tag}> out of order")
            else:
                self.open.pop()

    def handle_startendtag(self, tag, attrs):
        self.errors.append(f"<{tag}/> is not Telegram HTML (a new line is a new line)")

    def handle_data(self, data):
        self.text.append(data)


def read_html(raw: str) -> tuple[str, list[str]]:
    p = Html()
    p.feed(raw)
    p.close()
    errors = list(dict.fromkeys(p.errors))
    if p.open:
        errors.append("unclosed: " + " ".join(f"<{t}>" for t in p.open))
    if re.search(r"&(?!(lt|gt|amp|quot|#[0-9]{1,7}|#x[0-9a-fA-F]{1,6});)", raw):
        errors.append("a bare & (write &amp;)")
    return "".join(p.text), errors


def check_file(out: Path, name, kind: str, where: str, errors: list[str]) -> None:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        errors.append(f"{where}: bad {kind} file name {name!r}")
        return
    f = out / name
    if not f.is_file():
        errors.append(f"{where}: {name} is not in out/")
        return
    size, head = f.stat().st_size, f.open("rb").read(12)
    cap = PHOTO_MAX if kind == "photo" else CLIP_MAX if kind == "video" else FILE_MAX
    if not 0 < size <= cap:
        errors.append(f"{where}: {name} is {size / 1e6:.1f} MB (at most {cap / 1e6:.0f} MB)")
    if kind == "video" and head[4:8] != b"ftyp":
        errors.append(f"{where}: {name} is not an MP4")
    elif kind in MAGIC and not head.startswith(MAGIC[kind]):
        errors.append(f"{where}: {name} is not a {kind} ({'JPEG/PNG' if kind == 'photo' else kind})")


def check_buttons(raw, where: str, errors: list[str]) -> None:
    rows = raw if isinstance(raw, list) and raw and isinstance(raw[0], list) else [raw]
    if not isinstance(raw, list) or not 1 <= len(rows) <= BUTTON_ROWS:
        errors.append(f"{where}: buttons: 1-{BUTTON_ROWS} rows")
        return
    for row in rows:
        if not isinstance(row, list) or not 1 <= len(row) <= BUTTONS_PER_ROW:
            errors.append(f"{where}: buttons: each row 1-{BUTTONS_PER_ROW}")
            continue
        for b in row:
            if not isinstance(b, dict) or set(b) != {"text", "url"}:
                errors.append(f"{where}: a button is exactly {{text, url}}")
                continue
            if not str(b["text"]).strip() or utf16(str(b["text"])) > BUTTON_TEXT:
                errors.append(f"{where}: button text 1-{BUTTON_TEXT}")
            if not LINK.match(str(b["url"])):
                errors.append(f"{where}: button url must be https: {str(b['url'])[:60]}")


def check_message(out: Path, m, where: str, last: bool, errors: list[str]) -> str:
    if not isinstance(m, dict):
        errors.append(f"{where}: not an object")
        return ""
    mains = [k for k in ("photo", "photos", "video", "voice", "document", "poll") if m.get(k)]
    if len(mains) > 1:
        errors.append(f"{where}: only one of photo/photos/video/voice/document/poll")
    main = mains[0] if mains else "text"
    seen = ""
    if m.get("text") is not None:
        if main == "poll":
            errors.append(f"{where}: a poll has no text")
        text, faults = read_html(str(m["text"]))
        errors.extend(f"{where}: {e}" for e in faults)
        cap = TEXT_MAX if main == "text" else CAPTION_MAX
        if utf16(text) > cap:
            errors.append(f"{where}: {utf16(text)} visible characters (at most {cap})")
        seen = text
    elif main == "text":
        errors.append(f"{where}: a message with no text and no file")
    if main in ("photo", "video", "voice", "document"):
        check_file(out, m.get(main), main, where, errors)
    elif main == "photos":
        pics = m.get("photos")
        if not isinstance(pics, list) or not 2 <= len(pics) <= 10:
            errors.append(f"{where}: an album is 2-10 photos")
        else:
            for p in pics:
                check_file(out, p, "photo", where, errors)
    elif main == "poll":
        p = m["poll"] if isinstance(m["poll"], dict) else {}
        opts = [str(o).strip() for o in p.get("options") or [] if str(o).strip()]
        if not str(p.get("question") or "").strip() or utf16(str(p.get("question"))) > POLL_QUESTION:
            errors.append(f"{where}: poll question 1-{POLL_QUESTION}")
        if not 2 <= len(opts) <= 10 or any(utf16(o) > POLL_OPTION for o in opts) or len(set(opts)) != len(opts):
            errors.append(f"{where}: poll options 2-10, each ≤ {POLL_OPTION}, all different")
        if "quiz" in p and (not isinstance(p["quiz"], int) or not 0 <= p["quiz"] < len(opts)):
            errors.append(f"{where}: quiz is the right option's index (from 0)")
        if p.get("explanation"):
            if "quiz" not in p:
                errors.append(f"{where}: only a quiz has an explanation")
            text, faults = read_html(str(p["explanation"]))
            errors.extend(f"{where}: explanation: {e}" for e in faults)
            if utf16(text) > POLL_EXPLANATION:
                errors.append(f"{where}: explanation ≤ {POLL_EXPLANATION}")
        seen = str(p.get("question") or "")
    if m.get("buttons"):
        if main in ("photos", "poll"):
            errors.append(f"{where}: an album or a poll takes no buttons")
        elif not last:
            errors.append(f"{where}: buttons only on the post's last message")
        check_buttons(m["buttons"], where, errors)
    preview = m.get("preview", False)
    if preview not in (False, True) and not (isinstance(preview, str) and LINK.match(preview)):
        errors.append(f"{where}: preview is true, false or an https link")
    extra = set(m) - {"photo", "photos", "video", "voice", "document", "poll", "text", "buttons", "preview",
                      "silent", "above", "at", "type", "topic", "parts", "n"}
    if extra:
        errors.append(f"{where}: unknown keys {sorted(extra)}")
    return seen


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
    errors: list[str] = []
    try:
        doc = json.loads((out / "telegram.json").read_text("utf-8"))
    except (OSError, ValueError) as e:
        print(f"telegram.json: {e}")
        return 1
    posts = doc.get("posts") if isinstance(doc, dict) else None
    if not isinstance(posts, list) or not posts:
        print('telegram.json must be {"posts": [...]}')
        return 1
    breaking = all(isinstance(p, dict) and p.get("type") == "breaking" for p in posts)
    if len(posts) > (1 if breaking else POSTS_MAX):
        errors.append(f"at most {1 if breaking else POSTS_MAX} posts")
    last_min, topics = -GAP_MIN, set()
    for i, p in enumerate(posts, 1):
        where = f"post {i}"
        if not isinstance(p, dict):
            errors.append(f"{where}: not an object")
            continue
        if p.get("type") not in TYPES:
            errors.append(f"{where}: type is one of {', '.join(TYPES)}")
        topic = " ".join(str(p.get("topic") or "").split())
        if not topic or len(topic) > TOPIC_MAX:
            errors.append(f"{where}: topic (one line, ≤ {TOPIC_MAX})")
        elif topic in topics:
            errors.append(f"{where}: the same topic twice")
        topics.add(topic)
        if not breaking:
            hm = str(p.get("at") or "")
            if not HM.fullmatch(hm):
                errors.append(f"{where}: at is HH:MM (Tehran)")
            else:
                mins = int(hm[:2]) * 60 + int(hm[3:])
                if mins < last_min + GAP_MIN:
                    errors.append(f"{where}: {hm} is less than {GAP_MIN} minutes after the post before")
                last_min = mins
        msgs = p.get("parts") if isinstance(p.get("parts"), list) else [p]
        if not 1 <= len(msgs) <= PARTS_MAX:
            errors.append(f"{where}: parts 1-{PARTS_MAX}")
        seen = ""
        for k, m in enumerate(msgs, 1):
            seen = check_message(out, m, where if len(msgs) == 1 else f"{where} message {k}", k == len(msgs), errors)
        if p.get("type") != "poll" and SIGNATURE not in seen:
            errors.append(f"{where}: the last message ends with the signature line «🆔 {SIGNATURE}»")
    if errors:
        print("\n".join(dict.fromkeys(errors)))
        return 1
    print(f"OK: {len(posts)} posts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
