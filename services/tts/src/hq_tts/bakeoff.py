"""`python -m hq_tts.bakeoff`: the measured bake-off of prompt 13 §4.2 on this
machine's CPU, with no api and no network: every voice the image ships speaks
the same fixed scripts; for each sample the real-time factor (work seconds
per second of speech) and the peak resident memory of that synthesis alone
(wait4), and the container's own peak (cgroup v2). The Ogg files go to --out
for listening; the report (JSON, numbers only) to stdout.

    python -m hq_tts.bakeoff [--scripts scripts.json] [--out /out] [--voices a,b]

scripts.json: [{"key": "numbers", "spoken": "..."}, ...], by default the
image's bakeoff_scripts.json: the scripts as the hub speaks them
(hq_api.domain.voices.SCRIPTS through the hub's normaliser).
On the hub the same measurement runs through the api's bake-off queue (the
TTS one-shot, opt-in); this is the operator's run (RUNBOOK §31.13).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from hq_tts.engine import Engine, Piper, cgroup_peak_mb, installed
from hq_tts.job import Settings

# The fixed scripts as the hub speaks them (the api's SCRIPTS through its
# normaliser; apps/api's test keeps the two equal).
SCRIPTS = Path(__file__).resolve().parents[2] / "bakeoff_scripts.json"


def measure(
    engines: dict[str, Engine], scripts: list[dict[str, str]], out: Path | None
) -> dict[str, Any]:
    report: dict[str, Any] = {"voices": {}}
    for voice, engine in engines.items():
        samples: list[dict[str, Any]] = []
        for sc in scripts:
            with tempfile.TemporaryDirectory(prefix="bakeoff-") as tmp:
                spoken = engine.speak(sc["spoken"], Path(tmp))
            if out is not None:
                (out / f"{voice}.{sc['key']}.ogg").write_bytes(spoken.ogg)
            samples.append(
                {
                    "script": sc["key"],
                    "words": len(sc["spoken"].split()),
                    "audio_s": spoken.duration_s,
                    "synth_s": spoken.synth_s,
                    "rtf": round(spoken.rtf, 3),
                    "peak_mb": spoken.peak_rss_mb,
                }
            )
        audio = sum(x["audio_s"] for x in samples)
        work = sum(x["synth_s"] for x in samples)
        report["voices"][voice] = {
            "rtf": round(work / audio, 3) if audio else None,
            "peak_mb": max((x["peak_mb"] for x in samples), default=None),
            "audio_s": round(audio, 2),
            "samples": samples,
        }
    peak = cgroup_peak_mb()
    report["container_peak_mb"] = round(peak, 1) if peak is not None else None
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hq_tts.bakeoff")
    ap.add_argument("--scripts", default=str(SCRIPTS))
    ap.add_argument("--out")
    ap.add_argument("--voices", default="")
    a = ap.parse_args(argv)
    s = Settings()
    root = Path(s.voices_dir)
    wanted = [v for v in a.voices.split(",") if v] or installed(root)
    engines: dict[str, Engine] = {v: Piper(root, v, s.threads) for v in wanted}
    scripts = json.loads(Path(a.scripts).read_text(encoding="utf-8"))
    out = Path(a.out) if a.out else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    print(json.dumps(measure(engines, scripts, out), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
