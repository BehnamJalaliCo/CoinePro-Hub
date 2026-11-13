#!/usr/bin/env python3
"""Which wording does the audio support? Forced-text likelihood with the local Whisper model.

Usage: build/asr/venv/bin/python -I tools/word_probe.py MODEL_DIR AUDIO START END "TEXT A" "TEXT B" [...]
Cuts AUDIO[START:END], transcribes the clip on its own (no context, no prompt), then scores each candidate
text by teacher forcing (sum of log-probabilities of its tokens). Higher = the audio supports that wording more.
"""
import json
import math
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.audio import pad_or_trim
from faster_whisper.tokenizer import Tokenizer


def load16k(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def main() -> None:
    model_dir, audio_path, a, b = sys.argv[1:5]
    cands = sys.argv[5:]
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=8)
    audio = load16k(audio_path)[int(float(a) * 16000): int(float(b) * 16000)]
    segs, _ = model.transcribe(audio, language="fa", beam_size=5, condition_on_previous_text=False, vad_filter=False)
    heard = " ".join(s.text.strip() for s in segs)
    feats = model.feature_extractor(audio)
    num_frames = min(feats.shape[-1], 3000)
    enc = model.encode(pad_or_trim(feats))
    tok = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task="transcribe", language="fa")
    scores = []
    for c in cands:
        ids = tok.encode(" " + c.strip())
        r = model.model.align(enc, tok.sot_sequence, [ids], num_frames)[0]
        lp = [math.log(max(p, 1e-12)) for p in r.text_token_probs]
        scores.append({"text": c, "tokens": len(ids), "logp_sum": round(sum(lp), 2),
                       "min_p": round(min(r.text_token_probs), 3)})
    print(json.dumps({"clip": [float(a), float(b)], "heard_alone": heard, "scores": scores}, ensure_ascii=False))


if __name__ == "__main__":
    main()
