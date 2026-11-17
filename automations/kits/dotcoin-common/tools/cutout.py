# -*- coding: utf-8 -*-
"""Cuts the person (or one subject) out of a picture: an RGBA PNG whose alpha is the subject.

usage: cutout.py <in.jpg|png> <out.png> [--trim] [--feather 1.5]

The model is ISNet (DIS, "isnet-general-use", Apache-2.0; the file rembg ships, md5
fc16ebd8b0c10d971d3513d564d01e29) in /home/studio/kits/models, run with onnxruntime on the CPU.
--trim crops to the subject's box (with a 2 % margin). The DotCoin.me cover (COVER_SYSTEM.md) puts
the giant English words BEHIND the cut-out person, as in the owner's selected style.
"""
import sys

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter

MODEL = "/home/studio/kits/models/isnet-general-use.onnx"
SIZE = 1024


def mask_of(img: Image.Image) -> Image.Image:
    sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    im = img.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    a = a / max(1.0, float(a.max()))
    a = (a - 0.5) / 1.0
    x = a.transpose(2, 0, 1)[None].astype(np.float32)
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    lo, hi = float(out.min()), float(out.max())
    pred = (out - lo) / max(1e-6, hi - lo)
    m = Image.fromarray((pred * 255).clip(0, 255).astype(np.uint8), "L")
    return m.resize(img.size, Image.LANCZOS)


def main() -> None:
    args = sys.argv[1:]
    trim = "--trim" in args
    feather = 1.5
    if "--feather" in args:
        i = args.index("--feather"); feather = float(args[i + 1]); del args[i:i + 2]
    args = [a for a in args if a != "--trim"]
    src, dst = args[0], args[1]
    img = Image.open(src).convert("RGB")
    m = mask_of(img)
    # a clean edge: the soft rim kept, the faint haze off
    arr = np.asarray(m).astype(np.float32)
    arr = np.where(arr < 18, 0, arr)
    m = Image.fromarray(arr.astype(np.uint8), "L")
    if feather > 0:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    out = img.convert("RGBA")
    out.putalpha(m)
    if trim:
        box = m.point(lambda v: 255 if v > 40 else 0).getbbox()
        if box:
            pad = int(0.02 * max(img.size))
            box = (max(0, box[0] - pad), max(0, box[1] - pad),
                   min(img.width, box[2] + pad), min(img.height, box[3] + pad))
            out = out.crop(box)
    out.save(dst)
    cover = float((np.asarray(m) > 128).mean())
    print(f"cutout: {dst} {out.width}x{out.height} subject={cover:.0%} of the frame")


if __name__ == "__main__":
    main()
