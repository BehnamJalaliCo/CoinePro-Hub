#!/usr/bin/env python3
"""Independent second ear: local Whisper (faster-whisper) transcript with word times.

Usage: build/asr/venv/bin/python -I tools/asr_words.py MODEL_DIR AUDIO OUT_TXT OUT_JSON
No prompt is given, so the script text cannot bias what is heard.
"""
import json
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel


def load16k(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def main() -> None:
    model_dir, audio, out_txt, out_json = sys.argv[1:5]
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=8)
    segs, info = model.transcribe(load16k(audio), language="fa", beam_size=5, word_timestamps=True,
                                  vad_filter=False, condition_on_previous_text=False)
    words, texts = [], []
    for s in segs:
        texts.append(s.text.strip())
        for w in s.words or []:
            words.append({"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2),
                          "p": round(w.probability, 3)})
    open(out_txt, "w", encoding="utf-8").write(" ".join(texts) + "\n")
    json.dump({"duration": info.duration, "words": words}, open(out_json, "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    low = [w for w in words if w["p"] < 0.5]
    print(json.dumps({"duration": round(info.duration, 2), "words": len(words),
                      "low_conf": [(w["w"], w["s"]) for w in low]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
