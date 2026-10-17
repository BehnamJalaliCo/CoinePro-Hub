"""Images a model may see (prompt 06 §2, contract §17.1).

The hub sends a model an image only as bytes (base64), never as a URL a model
could fetch, and only in a few safe formats. One rule set for llm-router (which
admits requests) and claude-runtime (which passes them to the CLI):

  MEDIA_TYPES     image/jpeg, image/png, image/webp
  MAX_IMAGE_BYTES 5 MiB decoded per image
  MAX_IMAGES      20 per request
  MAX_TOTAL_BYTES 20 MiB decoded per request

`decode(media_type, data)` returns the bytes or raises ValueError: the base64
must decode exactly, the bytes must be one of the formats by their magic, and
the declared media_type must be that format.
"""

from __future__ import annotations

import base64
import binascii

MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 20
MAX_TOTAL_BYTES = 20 * 1024 * 1024
# A rough token count per image for budgets and fakes (Anthropic's rule of thumb
# for a ~1092x1092 picture is about 1,600 tokens).
TOKENS_PER_IMAGE = 1600


def sniff(data: bytes) -> str | None:
    """The media type the bytes really are, or None."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode(media_type: str, data: str) -> bytes:
    """The image's bytes, checked; ValueError (never the data) otherwise."""
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"media_type must be one of {', '.join(MEDIA_TYPES)}")
    if len(data) > (MAX_IMAGE_BYTES * 4) // 3 + 4:
        raise ValueError("image is larger than 5 MiB")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("data is not valid base64") from exc
    if not raw:
        raise ValueError("image is empty")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image is larger than 5 MiB")
    actual = sniff(raw)
    if actual is None:
        raise ValueError("bytes are not a JPEG, PNG or WebP image")
    if actual != media_type:
        raise ValueError(f"bytes are {actual}, not {media_type}")
    return raw
