#!/usr/bin/env python3
"""Technical QC of a narration file with ffmpeg: duration, loudness, peak, long silences.

Usage: python3 -I tools/audio_qc.py AUDIO [OUT.json]
Rules (reels narration): duration 60–90 s; no inner silence > 0.8 s (−40 dBFS);
true peak ≤ −1 dBTP after mastering; integrated loudness is normalised to −14 LUFS at mux time.
"""
import json
import re
import subprocess
import sys


def run(args):
    return subprocess.run(args, capture_output=True, text=True).stderr


def main() -> None:
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,sample_rate,channels",
                            "-of", "json", src], capture_output=True, text=True).stdout
    info = json.loads(probe)
    dur = float(info["format"]["duration"])
    st = info["streams"][0]
    eb = run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = eb[eb.rfind("Summary:"):]
    lufs = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1))
    lra = float(re.search(r"LRA:\s+(-?[\d.]+) LU", summ).group(1))
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summ)
    peak = float(tp.group(1)) if tp and tp.group(1) != "-inf" else None
    sd = run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "silencedetect=noise=-40dB:d=0.8", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", sd)]
    ends = [(float(a), float(b)) for a, b in re.findall(r"silence_end: (-?[\d.]+) \| silence_duration: ([\d.]+)", sd)]
    sil = []
    for i, s in enumerate(starts):
        e, d = ends[i] if i < len(ends) else (dur, dur - s)
        edge = s <= 0.05 or e >= dur - 0.05
        sil.append({"start": round(max(s, 0), 2), "dur": round(d, 2), "edge": edge})
    inner = [s for s in sil if not s["edge"]]
    vol = run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "astats=metadata=0", "-f", "null", "-"])
    clip = re.findall(r"Number of samples clipped:\s*(\d+)|Peak count:\s*(\d+)", vol)
    res = {
        "codec": st.get("codec_name"), "sample_rate": st.get("sample_rate"), "channels": st.get("channels"),
        "duration_s": round(dur, 2), "lufs_i": lufs, "lra": lra, "true_peak_dbtp": peak,
        "silences": sil, "inner_long_silences": inner,
        "checks": {
            "duration_60_90": 60 <= dur <= 90,
            "no_inner_silence_over_0_8s": not inner,
            "peak_below_0dbtp": peak is not None and peak < 0,
        },
    }
    print(json.dumps(res, ensure_ascii=False))
    if out:
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
