"""`python -m hq_stt.eval DIR [--markdown]`: word error rate of the engine on a
folder of samples (contract §17.2 quality protocol; `make stt-eval`).

A sample is `<name>.<wav|m4a|ogg|opus|mp3|webm>` plus `<name>.txt`, the exact
transcript. Both sides go through the same normalisation (hq_common.persian)
before words are compared. Prints a table (or Markdown with --markdown, which
`make stt-eval write=1` saves under docs/ops/reports/). Exit 1 if no sample.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hq_common import persian
from hq_stt import engine as E
from hq_stt.config import Settings

AUDIO = (".wav", ".m4a", ".ogg", ".opus", ".mp3", ".webm")


@dataclass
class Row:
    name: str
    words: int
    errors: int
    duration_s: float
    seconds: float

    @property
    def wer(self) -> float:
        return self.errors / self.words if self.words else 0.0


def samples(directory: Path) -> list[tuple[str, Path, str]]:
    out = []
    for audio in sorted(directory.iterdir()):
        if audio.suffix.lower() in AUDIO and audio.with_suffix(".txt").is_file():
            out.append((audio.stem, audio, audio.with_suffix(".txt").read_text("utf-8").strip()))
    return out


def evaluate(engine: E.Engine, directory: Path) -> list[Row]:
    rows = []
    for name, audio, reference in samples(directory):
        t = engine.transcribe(audio.read_bytes())
        ref = persian.words(reference)
        rows.append(
            Row(
                name,
                len(ref),
                persian.word_edit_distance(ref, persian.words(t.text_raw)),
                t.duration_s,
                t.load_s + t.transcribe_s,
            )
        )
    return rows


def render(rows: list[Row], engine: E.Engine, markdown: bool) -> str:
    total_words = sum(r.words for r in rows)
    total_errors = sum(r.errors for r in rows)
    overall = total_errors / total_words if total_words else 0.0
    head = f"engine {engine.name} {engine.model} {engine.version}"
    if markdown:
        lines = [
            f"# STT evaluation, {datetime.now(UTC):%Y-%m-%d}",
            "",
            f"- Engine: `{head}`",
            f"- Samples: {len(rows)}; words: {total_words}",
            f"- **WER: {overall:.1%}** (word accuracy {1 - overall:.1%}; target >= 95%)",
            "",
            "| sample | words | errors | WER | audio s | time s |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for r in rows:
            cells = [r.name, str(r.words), str(r.errors), f"{r.wer:.1%}"]
            cells += [f"{r.duration_s:.1f}", f"{r.seconds:.1f}"]
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines) + "\n"
    lines = [head, f"{'sample':<24} {'words':>6} {'errors':>6} {'WER':>7} {'audio':>7} {'time':>6}"]
    for r in rows:
        line = f"{r.name:<24} {r.words:>6} {r.errors:>6} {r.wer:>7.1%}"
        lines.append(line + f" {r.duration_s:>7.1f} {r.seconds:>6.1f}")
    lines.append(f"{'overall':<24} {total_words:>6} {total_errors:>6} {overall:>7.1%}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stt-eval")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    s = Settings()
    engine = E.build(s)
    rows = evaluate(engine, args.directory)
    if not rows:
        print(
            f"stt-eval: no samples (<name>.<audio> + <name>.txt) in {args.directory}",
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(render(rows, engine, args.markdown))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
