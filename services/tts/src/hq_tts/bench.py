"""`python -m hq_tts.bench`: the acceptance measurement of prompt 12 §4: a
fixed 120-word Persian script becomes Ogg/Opus with a real-time factor under
0.5 and a peak resident memory under 300 MB (the numbers go in the report).
Exit 1 when a limit is broken."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from hq_tts.engine import Piper, cgroup_peak_mb
from hq_tts.job import Settings

RTF_MAX = 0.5
RSS_MAX_MB = 300.0

# 120 words, the way a spoken script reads (no digit, no markdown).
SAMPLE = (
    "سلام مدیر کل عزیز. گزارش صبحگاهی امروز آماده است. در کارتابل تصمیم سه کارت منتظر توست؛ "
    "یکی از آن‌ها ریسک بالا دارد و به استخدام یک کارشناس فنی مربوط است. "
    "دیروز دوازده خروجی تازه ثبت شد و هفت تای آن‌ها هنوز امتیاز ندارند. "
    "مصرف دیروز همه‌ی شرکت‌ها روی هم یک و شش دهم میلیون توکن بود، "
    "یعنی چهار دلار و بیست سنت. هدررفت دیروز شش درصد بود و بیشترین سهم را "
    "اجراهای شکست‌خورده داشتند. هیچ بودجه‌ای به آستانه‌ی هشدار نرسیده است. "
    "یادآوری کارتابل: دو کارت بیش از یک روز منتظرند و یک کارت بیش از سه روز. "
    "نامه‌ی هفتگی مدیرعامل‌ها شنبه ساعت نه می‌رسد. "
    "کلید توقف هلدینگ همچنان فعال است، پس هیچ ایجنتی کار تازه‌ای شروع نمی‌کند. روز خوبی داشته باشی."
)


def main() -> int:
    s = Settings()
    engine = Piper(Path(s.voices_dir), s.voice, s.threads)
    with tempfile.TemporaryDirectory(prefix="tts-bench-") as tmp:
        spoken = engine.speak(SAMPLE, Path(tmp))
    out = {
        "words": len(SAMPLE.split()),
        "voice": s.voice,
        "audio_s": spoken.duration_s,
        "synth_s": spoken.synth_s,
        "rtf": round(spoken.rtf, 3),
        "peak_rss_mb": spoken.peak_rss_mb,
        "container_peak_mb": round(peak, 1) if (peak := cgroup_peak_mb()) is not None else None,
        "ogg_bytes": len(spoken.ogg),
        "ogg_magic": spoken.ogg[:4] == b"OggS",
        "ok": spoken.rtf < RTF_MAX
        and spoken.peak_rss_mb < RSS_MAX_MB
        and spoken.ogg[:4] == b"OggS",
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
