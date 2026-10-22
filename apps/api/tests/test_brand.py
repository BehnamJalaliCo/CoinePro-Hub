"""Prompt 9.1 (contract §18.14): the company's brand and seal from the owner's
logo, traced by code (no model) in the worker's sandboxed child.

Every logo here is a synthetic PNG/JPEG drawn by the test; no model is called."""

from __future__ import annotations

import io
import json
import os
import random
import re
import shutil
import struct
import uuid
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import brand, events
from hq_api.db import Database
from hq_api.domain import brands as BR
from hq_api.hub import Hub
from hq_api.worker import brand_activities as BA
from hq_common import untrusted

from .conftest import agent_headers, idem, step_up

pytestmark = pytest.mark.usefixtures("relay")
INK = (20, 22, 30)
ORANGE = (253, 153, 13)


# ------------------------------------------------------------- the logos --
def _save(img: Any, fmt: str = "PNG", **kw: Any) -> bytes:
    out = io.BytesIO()
    img.save(out, format=fmt, **kw)
    return out.getvalue()


def two_colour(size: int = 768, *, mode: str = "RGBA", fmt: str = "PNG") -> bytes:
    """A dark ring with an orange bar across it, on transparency (or white)."""
    from PIL import Image, ImageDraw

    bg: tuple[int, ...] = (0, 0, 0, 0) if mode == "RGBA" else (255, 255, 255)
    img = Image.new(mode, (size, size), bg)
    d = ImageDraw.Draw(img)
    s = size / 1024
    d.ellipse((150 * s, 150 * s, 870 * s, 870 * s), fill=INK)
    d.ellipse((330 * s, 330 * s, 690 * s, 690 * s), fill=bg)
    d.rectangle((460 * s, 200 * s, 560 * s, 820 * s), fill=ORANGE)
    return _save(img, fmt, quality=90) if fmt == "JPEG" else _save(img, fmt)


def mono() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon([(100, 500), (400, 80), (700, 500)], fill=(15, 181, 174))
    return _save(img)


def photo() -> bytes:
    """A busy picture: no corner agrees with another."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:600, 0:800]
    a = np.stack([(x * 3) % 256, (y * 2) % 256, (x + y) % 256], axis=2)
    a = np.clip(a + rng.integers(-60, 60, a.shape), 0, 255).astype(np.uint8)
    return _save(Image.fromarray(a, "RGB"), "JPEG", quality=85)


def bomb(w: int = 20000, h: int = 20000) -> bytes:
    """A PNG whose header claims w x h (a few bytes of compressed zeros)."""

    def chunk(t: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(t + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", crc)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00" * 4096))
        + chunk(b"IEND", b"")
    )


def busy_mark(n: int, size: int, body: bool) -> bytes:
    """A body and many small squares: the squares cost bytes the budget lacks."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if body:
        d.ellipse((380, 380, 644, 644), fill=(30, 30, 30))
    rnd = random.Random(3)
    placed = 0
    while placed < n:
        x, y = rnd.randrange(16, 1000 - size), rnd.randrange(16, 1000 - size)
        if body and x + size > 360 and x < 664 and y + size > 360 and y < 664:
            continue
        d.rectangle((x, y, x + size, y + size), fill=(30, 30, 30))
        placed += 1
    return _save(img)


def grid_mark() -> bytes:
    """A body and a grid of 13 px squares: over the budget at detail 3, gone
    (speckle filter) at detail 2."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((400, 400, 624, 624), fill=(30, 30, 30))
    for gx in range(24, 1000, 36):
        for gy in range(24, 1000, 36):
            if 380 < gx < 644 and 380 < gy < 644:
                continue
            d.rectangle((gx, gy, gx + 12, gy + 12), fill=(30, 30, 30))
    return _save(img)


def dark_accent() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((60, 60, 740, 740), fill=(204, 204, 204))
    d.ellipse((300, 300, 500, 500), fill=(90, 0, 0))
    return _save(img)


def wide(w: int, h: int) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((10, 10, w - 10, h - 10), fill=INK)
    return _save(img)


# --------------------------------------------------------------- helpers --
async def put_file(
    client: httpx.AsyncClient, h: dict[str, str], data: bytes, mime: str, name: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/files",
        content=data,
        headers={**h, **idem(), "Content-Type": mime, "X-File-Name": name},
    )


async def brand_of(
    client: httpx.AsyncClient,
    wk: dict[str, Any],
    su: Any,
    h: dict[str, str],
    code: str,
    data: bytes,
    mime: str = "image/png",
    *,
    part: str = "mark",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upload a logo, ask for a brand, run the worker's trace -> the version."""
    v = await ask(client, h, code, data, mime, part=part, options=options)
    return await trace(client, wk, su, h, code, v["version"])


async def ask(
    client: httpx.AsyncClient,
    h: dict[str, str],
    code: str,
    data: bytes,
    mime: str = "image/png",
    *,
    part: str = "mark",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Upload a logo and ask for a brand -> the processing version."""
    r = await put_file(client, h, data, mime, f"logo.{mime.split('/')[1]}")
    assert r.status_code == 201, r.text
    body: dict[str, Any] = {"file_id": r.json()["id"], "part": part}
    if options:
        body["options"] = options
    r = await client.post(f"/api/v1/companies/{code}/brand", headers={**h, **idem()}, json=body)
    assert r.status_code == 202, r.text
    v: dict[str, Any] = r.json()
    assert v["state"] == "processing" and v["part"] == part and v[part] is None
    return v


async def trace(
    client: httpx.AsyncClient,
    wk: dict[str, Any],
    su: Any,
    h: dict[str, str],
    code: str,
    version: int,
) -> dict[str, Any]:
    bid = await su.fetchval(
        """SELECT b.id FROM org.company_brands b JOIN core.companies c ON c.id = b.company_id
           WHERE c.code = $1 AND b.version = $2""",
        code,
        version,
    )
    await wk["acts"].brand.brand_trace(str(bid))
    items = (await client.get(f"/api/v1/companies/{code}/brand/versions", headers=h)).json()[
        "items"
    ]
    return next(x for x in items if x["version"] == version)


async def activate(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], v: dict[str, Any]
) -> httpx.Response:
    su_tok = await step_up(hub, owner_session["session_id"], "company.brand", v["digest"])
    return await client.post(
        f"/api/v1/companies/{v['company']}/brand/{v['version']}/activate",
        headers={**owner_session["headers"], **su_tok},
        json={},
    )


# ------------------------------------------------------- §1 data, digest --
def test_the_digest_is_the_canonical_json_of_what_is_drawn() -> None:
    b = {"mark": {"vb": "0 0 10 10", "layers": [{"role": "ink", "color": "#111111", "d": "M0 0L1 1Z"}]},
         "wordmark": None, "ink": "#111111", "accent": None, "accent_night": None, "accent_day": None,
         "palette": [{"hex": "#111111", "share": 1}]}  # fmt: skip
    canon = json.dumps(
        {k: b[k] for k in brand.DIGEST_FIELDS}, sort_keys=True, separators=(",", ":")
    )
    assert brand.digest(b) == __import__("hashlib").sha256(canon.encode()).hexdigest()
    assert brand.digest({**b, "palette": []}) == brand.digest(b)  # the palette is not sealed
    assert brand.digest({**b, "accent": "#FF0000"}) != brand.digest(b)


def test_the_page_surfaces_are_the_design_tokens() -> None:
    path = Path(os.environ.get("HQ_DESIGN_TOKENS", "/design-tokens/divan.tokens.json"))
    if not path.exists():
        pytest.skip("design/tokens is not mounted")
    prim = json.loads(path.read_text())["divan"]["color"]["primitive"]
    assert {
        "night": prim["night"]["page"]["$value"],
        "day": prim["day"]["page"]["$value"],
    } == brand.PAGE


def test_only_svg_path_grammar_is_a_d() -> None:
    good = ["M0 0L10 10Z", "M610.0 813.8L610.0 647.0C1 2 3 4 5 6Z", "m1,2 l3-4z", "M.5.5L1e2 3E-1",
            "M0 0H10V10H0Z", "M0 0A5 5 0 0 1 10 10", "M1 2 3 4 5 6"]  # fmt: skip
    bad = ["", "L0 0", "M0", "M0 0L1", 'M0 0"/><script>alert(1)</script>', "M0 0 url(#x)",
           "M0 0Z1", "M0 0A5 5 0 2 1 10 10", "M,0 0", "M0 0;", "M0 0L1 1 Z M", "<path d='M0 0'/>",
           "M0 0" + "L1 1" * 20000]  # fmt: skip
    assert all(brand.path_ok(d) for d in good), [d for d in good if not brand.path_ok(d)]
    assert not any(brand.path_ok(d) for d in bad), [d for d in bad if brand.path_ok(d)]


def test_a_too_dark_accent_gets_the_nearest_passing_lightness() -> None:
    dark = "#5A0000"
    t = brand.theme_accents(dark)
    assert t["contrast_night"] < 3 and t["accent_night"] is not None and t["accent_day"] is None
    assert brand.contrast(t["accent_night"], brand.PAGE["night"]) >= 3
    L0, C0, h0 = brand.oklch(dark)
    L1, C1, h1 = brand.oklch(t["accent_night"])
    assert L1 > L0 and abs(h1 - h0) < 0.05 and C1 <= C0 + 0.01  # lighter, the same hue
    assert brand.passing_accent("#FD990D", brand.PAGE["night"]) is None
    light = brand.theme_accents("#FFE08A")
    assert light["accent_night"] is None and light["accent_day"] is not None
    assert brand.contrast(light["accent_day"], brand.PAGE["day"]) >= 3


async def test_a_version_is_append_only_except_its_state(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any], hub: Hub,
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, two_colour())
    assert v["state"] == "proposed"
    where = "WHERE company_id = (SELECT id FROM core.companies WHERE code = :c)"
    for sql in (
        f"UPDATE org.company_brands SET ink = '#000000' {where}",
        f"UPDATE org.company_brands SET state = 'processing' {where}",
        f"DELETE FROM org.company_brands {where}",
    ):
        with pytest.raises(Exception, match=r"append-only|not a move|permission denied"):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await tx.exec(sql, c=co)
    async with hub.db.tx(await hub.companies.ids()) as tx:  # the state alone may move
        await tx.exec(f"UPDATE org.company_brands SET state = 'active' {where}", c=co)
        await tx.exec(f"UPDATE org.company_brands SET state = 'retired' {where}", c=co)
    n = await su.fetchval(
        """SELECT count(*) FROM audit.entries WHERE target_kind = 'brand' AND target_ref = $1""",
        f"{co}@{v['version']}",
    )
    assert n == 2  # brand.upload by the owner, brand.traced by the media worker


# -------------------------------------------------------- §2 the tracing --
async def test_a_transparent_two_colour_png_becomes_ink_and_accent(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, two_colour())
    assert v["state"] == "proposed", v
    layers = v["mark"]["layers"]
    assert [x["role"] for x in layers] == ["ink", "accent"]
    assert v["accent"] == layers[1]["color"] and v["ink"] == layers[0]["color"]
    assert brand.oklab(v["accent"])[1] > 0.05  # the orange
    assert v["checks"]["iou"] >= 0.9 and v["checks"]["min_feature_px_16"] >= 1
    assert v["source"]["has_alpha"] is True
    # Orange passes 3:1 on the night page, not on the day page: a darker day accent.
    assert v["accent_night"] is None and v["accent_day"] is not None
    assert brand.contrast(v["accent_day"], brand.PAGE["day"]) >= 3
    assert v["checks"]["warnings"] == [brand.WARN_DAY]
    assert v["options"] == {"colors": 2, "detail": 3}
    assert all(brand.path_ok(x["d"]) for x in layers) and v["checks"]["paths_bytes"] <= 48 * 1024
    assert re.fullmatch(r"0 0 \d+ \d+", v["mark"]["vb"])
    assert [p["hex"] for p in v["palette"]][:2] == [v["ink"], v["accent"]]
    assert abs(sum(p["share"] for p in v["palette"]) - 1) < 0.01
    assert v["digest"] == brand.digest(v)


async def test_a_one_colour_png_is_one_ink_layer(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, mono())
    assert v["state"] == "proposed" and [x["role"] for x in v["mark"]["layers"]] == ["ink"]
    assert v["accent"] is None and v["accent_night"] is None and v["accent_day"] is None
    assert v["checks"]["contrast_night"] is None and v["checks"]["iou"] >= 0.9
    # The owner asks for one colour on a two-colour logo: one layer, too.
    v = await brand_of(client, wk, su, owner, co, two_colour(), options={"colors": 1, "detail": 3})
    assert len(v["mark"]["layers"]) == 1 and v["accent"] is None and v["options"]["colors"] == 1


async def test_a_jpeg_on_flat_white_works_with_the_warning(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, two_colour(mode="RGB", fmt="JPEG"), "image/jpeg")
    assert v["state"] == "proposed", v
    assert [x["role"] for x in v["mark"]["layers"]] == ["ink", "accent"]
    assert brand.WARN_NO_ALPHA in v["checks"]["warnings"] and v["source"]["has_alpha"] is False
    assert v["checks"]["iou"] >= 0.9


async def test_a_busy_photo_fails_no_background(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, photo(), "image/jpeg")
    assert v["state"] == "failed" and v["status_reason"] == "no_background"
    assert v["mark"] is None and v["checks"] is None


async def test_a_decompression_bomb_is_refused_before_it_is_decoded(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any], tmp_path: Path,
) -> None:  # fmt: skip
    data = bomb()
    # The upload refuses it already (the api's own pixel cap) ...
    assert (await put_file(client, owner, data, "image/png", "bomb.png")).status_code == 415
    # ... and the tracer's guard refuses it on its own, without filling memory.
    path = tmp_path / "bomb.png"
    path.write_bytes(data)
    got = await untrusted.run(BA.JOB, kwargs={"path": str(path)}, limits=BA.LIMITS)
    assert not got.ok and got.error == "Refused: too_large" and got.killed is None
    assert got.usage["VmHWM"] < 120 * 1024  # KiB: nothing was decoded
    # Larger than 4096 px but under the upload's cap: the brand fails too_large.
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, wide(4200, 64))
    assert v["state"] == "failed" and v["status_reason"] == "too_large"


async def test_a_complex_logo_lowers_its_detail_or_is_too_complex(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, grid_mark(), options={"detail": 3})
    assert v["state"] == "proposed", v
    assert v["options"]["detail"] < 3 and v["checks"]["paths_bytes"] <= 48 * 1024
    assert any("پایین آمد" in w for w in v["checks"]["warnings"])
    v = await brand_of(client, wk, su, owner, co, busy_mark(3000, 26, body=False))
    assert v["state"] == "failed" and v["status_reason"] == "too_complex"


async def test_a_very_dark_accent_gets_a_lighter_night_accent(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, owner, co, dark_accent())
    assert v["state"] == "proposed" and v["ink"] == "#CCCCCC" and v["accent"] == "#5A0000"
    assert v["accent_night"] and brand.contrast(v["accent_night"], brand.PAGE["night"]) >= 3
    assert brand.luminance(v["accent_night"]) > brand.luminance(v["accent"])
    assert v["accent_day"] is None and v["checks"]["contrast_night"] < 3
    assert brand.WARN_NIGHT in v["checks"]["warnings"]


async def test_no_d_outside_the_grammar_is_ever_stored(
    client: httpx.AsyncClient, owner: dict[str, str], wk: dict[str, Any], su: Any,
    new_company: Callable[..., Any], monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    hostile = {
        "shape": {"vb": "0 0 10 10", "layers": [
            {"role": "ink", "color": "#111111", "d": 'M0 0L5 5Z"/><image href="https://x.test/a"/>'}]},
        "ink": "#111111", "accent": None, "palette": [], "options": {"colors": 1, "detail": 3},
        "checks": {"paths_bytes": 10, "min_feature_px_16": 2, "iou": 1, "warnings": []},
        "has_alpha": True, "width": 10, "height": 10,
    }  # fmt: skip

    async def fake_run(*_a: Any, **_k: Any) -> untrusted.Outcome:
        return untrusted.Outcome(True, value=hostile)

    asked = await ask(client, owner, co, mono())
    monkeypatch.setattr(BA.untrusted, "run", fake_run)  # the child answers with markup
    v = await trace(client, wk, su, owner, co, asked["version"])
    assert v["state"] == "failed" and v["status_reason"] == "invalid_path" and v["mark"] is None
    raw = await su.fetchval(
        """SELECT b.mark::text FROM org.company_brands b JOIN core.companies c ON c.id = b.company_id
           WHERE c.code = $1""",
        co,
    )
    assert raw is None
    with pytest.raises(ValueError):
        BR.compose({"part": "mark", "mark": None, "wordmark": None, "ink": "#111111", "source": {},
                    "palette": []}, hostile)  # fmt: skip


async def test_the_tracer_child_has_no_network_and_a_4096_png_fits_its_limits(
    tmp_path: Path,
) -> None:
    """§0.7: the peak memory of a 4096 px PNG, inside the worker's limits."""
    path = tmp_path / "big.png"
    path.write_bytes(two_colour(4096))
    got = await untrusted.run(BA.JOB, kwargs={"path": str(path)}, limits=BA.LIMITS)
    assert got.ok, got
    assert got.usage["network"] == "off (seccomp)" if os.uname().machine == "x86_64" else True
    print(f"\n4096 px PNG: VmHWM {got.usage['VmHWM'] // 1024} MiB, VmPeak "
          f"{got.usage['VmPeak'] // 1024} MiB, {got.usage['cpu_s']} s CPU, {got.seconds:.2f} s")  # fmt: skip
    assert got.usage["VmPeak"] < BA.LIMITS.memory_mb * 1024 and got.seconds < 30
    assert got.value["checks"]["iou"] >= 0.9 and got.value["width"] == 4096


# ---------------------------------------------------------------- §3 API --
async def test_the_seal_needs_step_up_on_the_digest_and_retires_the_old(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], wk: dict[str, Any],
    su: Any, new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = (await new_company())["code"]
    v1 = await brand_of(client, wk, su, h, co, two_colour())
    path = f"/api/v1/companies/{co}/brand/{v1['version']}/activate"
    assert (await client.post(path, headers=h, json={})).status_code == 403  # no step-up
    other = await step_up(hub, owner_session["session_id"], "company.brand", "0" * 64)
    r = await client.post(path, headers={**h, **other}, json={})
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"  # another digest
    r = await activate(client, hub, owner_session, v1)
    assert r.status_code == 200 and r.json()["state"] == "active", r.text
    assert (await client.get(f"/api/v1/companies/{co}", headers=h)).json()["brand_version"] == v1[
        "version"
    ]
    v2 = await brand_of(client, wk, su, h, co, mono())
    view = (await client.get(f"/api/v1/companies/{co}/brand", headers=h)).json()
    assert (
        view["active"]["version"] == v1["version"] and view["proposed"]["version"] == v2["version"]
    )
    assert (await activate(client, hub, owner_session, v2)).status_code == 200
    items = (await client.get(f"/api/v1/companies/{co}/brand/versions", headers=h)).json()["items"]
    states = {x["version"]: x["state"] for x in items}
    assert states == {v2["version"]: "active", v1["version"]: "retired"}
    assert [x["version"] for x in items] == sorted(states, reverse=True)
    page = (
        await client.get(f"/api/v1/companies/{co}/brand/versions", headers=h, params={"limit": 1})
    ).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    rows = await su.fetch(
        """SELECT action, step_up, summary FROM audit.entries WHERE target_kind = 'brand'
             AND target_ref = $1 AND action = 'brand.activate'""",
        f"{co}@{v2['version']}",
    )
    assert len(rows) == 1 and rows[0]["step_up"] and "retired" in rows[0]["summary"]
    # A failed or processing version is not sealed.
    v3 = await brand_of(client, wk, su, h, co, photo(), "image/jpeg")
    r = await activate(client, hub, owner_session, v3)
    assert r.status_code == 409


async def test_a_version_changed_after_the_owner_saw_it_is_not_sealed(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], wk: dict[str, Any],
    su: Any, new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = (await new_company())["code"]
    seen = await brand_of(client, wk, su, h, co, two_colour())
    async with su.transaction():  # someone rewrites the stored trace behind the owner's back
        await su.execute("SET LOCAL session_replication_role = replica")
        await su.execute(
            """UPDATE org.company_brands SET accent = '#FF0000'
               WHERE company_id = (SELECT id FROM core.companies WHERE code = $1)""",
            co,
        )
    r = await activate(client, hub, owner_session, seen)  # step-up on the digest the owner saw
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    now = (await client.get(f"/api/v1/companies/{co}/brand", headers=h)).json()["proposed"]
    assert now["digest"] != seen["digest"] and now["accent"] == "#FF0000"


async def test_brands_has_an_etag_that_changes_with_a_seal(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], wk: dict[str, Any],
    su: Any, new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    first = await client.get("/api/v1/brands", headers=h)
    assert first.status_code == 200 and first.headers["etag"] == first.json()["etag"]
    assert first.headers["cache-control"] == "private, no-cache"
    again = await client.get(
        "/api/v1/brands", headers={**h, "If-None-Match": first.headers["etag"]}
    )
    assert (
        again.status_code == 304
        and again.headers["etag"] == first.headers["etag"]
        and not again.content
    )
    co = (await new_company())["code"]
    v = await brand_of(client, wk, su, h, co, two_colour())
    assert co not in first.json()["companies"]
    assert (await activate(client, hub, owner_session, v)).status_code == 200
    after = await client.get(
        "/api/v1/brands", headers={**h, "If-None-Match": first.headers["etag"]}
    )
    assert after.status_code == 200 and after.json()["etag"] != first.json()["etag"]
    got = after.json()["companies"][co]
    assert (
        got["version"] == v["version"] and got["mark"] == v["mark"] and got["accent"] == v["accent"]
    )
    assert set(got) == {
        "version",
        "mark",
        "wordmark",
        "ink",
        "accent",
        "accent_night",
        "accent_day",
    }
    holding = (await hub.companies.holding()).code
    assert holding not in after.json()["companies"]  # the holding's seal is not data


async def test_every_brand_route_is_the_owners(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any],
) -> None:  # fmt: skip
    co = (await new_company())["code"]
    agent = await agent_headers(f"{co}-CEO")
    calls = [
        ("GET", "/api/v1/brands", None),
        ("GET", f"/api/v1/companies/{co}/brand", None),
        ("GET", f"/api/v1/companies/{co}/brand/versions", None),
        ("POST", f"/api/v1/companies/{co}/brand", {"file_id": str(uuid.uuid4()), "part": "mark"}),
        ("POST", f"/api/v1/companies/{co}/brand/1/retrace", {"options": {"detail": 2}}),
        ("POST", f"/api/v1/companies/{co}/brand/1/activate", {}),
    ]
    for method, path, body in calls:
        r = await client.request(method, path, headers={**agent, **idem()}, json=body)
        assert r.status_code == 403, (path, r.status_code)
    holding = (await hub.companies.holding()).code
    r = await client.post(
        f"/api/v1/companies/{holding}/brand",
        headers={**owner, **idem()},
        json={"file_id": str(uuid.uuid4()), "part": "mark"},
    )
    assert r.status_code == 422  # the holding's seal is fixed
    r = await client.post(f"/api/v1/companies/{co}/brand", headers=owner,
                          json={"file_id": str(uuid.uuid4())})  # fmt: skip
    assert r.status_code in (400, 422) and "dempotency" in r.text  # Idempotency-Key is required


async def test_retrace_a_wordmark_and_what_is_carried_over(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], wk: dict[str, Any],
    su: Any, new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = (await new_company())["code"]
    # A wordmark first: proposed, but there is no mark to seal yet.
    w = await brand_of(client, wk, su, h, co, mono(), part="wordmark")
    assert w["state"] == "proposed" and w["mark"] is None and w["wordmark"]
    r = await activate(client, hub, owner_session, w)
    assert r.status_code == 409 and r.json()["missing"] == ["mark"]
    m = await brand_of(client, wk, su, h, co, two_colour())
    assert m["wordmark"] is None  # nothing active to carry yet
    assert (await activate(client, hub, owner_session, m)).status_code == 200
    # A retrace: the same file with other options, a new version.
    r = await client.post(
        f"/api/v1/companies/{co}/brand/{m['version']}/retrace",
        headers={**h, **idem()},
        json={"options": {"colors": 1, "detail": 2}},
    )
    assert r.status_code == 202 and r.json()["state"] == "processing", r.text
    rt = await trace(client, wk, su, h, co, r.json()["version"])
    assert (
        rt["source"]["file_id"] == m["source"]["file_id"]
        and rt["source"]["sha256"] == m["source"]["sha256"]
    )
    assert rt["options"] == {"colors": 1, "detail": 2} and len(rt["mark"]["layers"]) == 1
    # A wordmark now: the active mark and its colours are carried over.
    w2 = await brand_of(client, wk, su, h, co, mono(), part="wordmark")
    assert w2["mark"] == m["mark"] and (w2["ink"], w2["accent"]) == (m["ink"], m["accent"])
    assert w2["wordmark"] and w2["wordmark"] != m["mark"]
    assert w2["checks"]["paths_bytes"] == brand.paths_bytes(w2["mark"], w2["wordmark"])
    # A seeded or uploaded version's events reach the stream under the topic "companies".
    assert any(t.startswith("brand.") for t in events.TOPICS["companies"])
    n = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject = $1", f"hq.core.{co}.brand.updated"
    )
    assert n >= 8  # created, proposed and activated, version by version


# --------------------------------------------------------- §4 founding --
async def test_a_founding_activates_with_a_sealed_brand(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], wk: dict[str, Any],
    su: Any, new_company: Callable[..., Any],
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    holding = (await hub.companies.holding()).id
    ref = await su.fetchval(
        """INSERT INTO core.foundings (company_id, source, state, name_fa, name_en, code, new_company_id,
               created_by_kind, created_by_code)
           VALUES ($1, '{"kind": "idea", "brief_md": "b"}', 'ready_for_login', 'ش', 'S', $2, $3,
                   'owner', 'owner') RETURNING ref""",
        holding,
        co["code"],
        co["id"],
    )
    f = (await client.get(f"/api/v1/foundings/{ref}", headers=h)).json()
    assert f["brand"] == {"state": "missing", "version": None}
    v = await brand_of(client, wk, su, h, co["code"], two_colour())
    f = (await client.get(f"/api/v1/foundings/{ref}", headers=h)).json()
    assert f["brand"] == {"state": "proposed", "version": v["version"]}
    tok = await step_up(hub, owner_session["session_id"], "founding.activate", ref)
    r = await client.post(f"/api/v1/foundings/{ref}/activate", headers={**h, **tok}, json={})
    assert r.status_code == 409 and r.json()["missing"] == ["brand"]  # proposed is not sealed
    assert (await activate(client, hub, owner_session, v)).status_code == 200
    r = await client.post(f"/api/v1/foundings/{ref}/activate", headers={**h, **tok})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "active" and r.json()["brand"] == {
        "state": "active",
        "version": v["version"],
    }
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM core.employees e WHERE e.id = r.employee_id AND e.code = $1 AND r.state = 'queued'""",
        f"{co['code']}-CEO",
    )


# ---------------------------------------------------------------- §5 seed --
async def _seed(owner_db: Database, root: Path | None = None) -> int:
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        return await BR.seed(tx, root)


def _file_ds(path: Path) -> list[str]:
    return re.findall(r'<path\s[^>]*?\bd="([^"]*)"', path.read_text(encoding="utf-8"))


async def test_the_seed_is_version_1_of_every_design_folder(
    client: httpx.AsyncClient, owner: dict[str, str], owner_db: Database, su: Any,
) -> None:  # fmt: skip
    root = BR.brands_dir()
    if not root.is_dir():
        pytest.skip("design/brand/companies is not mounted")
    await _seed(owner_db)  # idempotent (a migration round trip may have run before)
    assert await _seed(owner_db) == 0
    got = (await client.get("/api/v1/brands", headers=owner)).json()["companies"]
    codes = {
        r["code"] for r in await su.fetch("SELECT code FROM core.companies WHERE kind = 'company'")
    }
    folders = [p for p in sorted(root.iterdir()) if p.is_dir() and brand.seed_folder(p)]
    assert folders  # whatever their number: no count is fixed anywhere
    for folder in folders:
        code = folder.name.upper()
        if code not in codes:
            continue
        files = brand.seed_folder(folder)
        assert files is not None
        mark_file = next(p for p in folder.iterdir() if brand.MARK_FILE.search(p.name))
        b = got[code]
        assert [x["d"] for x in b["mark"]["layers"]] == _file_ds(
            mark_file
        )  # the design file's own d
        assert b["mark"] == files["mark"] and b["wordmark"] == files["wordmark"]
        assert b["ink"] == brand.colours_of(files["mark"])[0]
        v = (await client.get(f"/api/v1/companies/{code}/brand", headers=owner)).json()["active"]
        assert (
            v["source"]["kind"] == "seed"
            and v["source"]["path"] == f"design/brand/companies/{folder.name}/"
        )
        assert v["checks"]["iou"] == 1.0 and v["palette"] and v["digest"] == brand.digest(v)


async def test_the_seed_reads_folders_never_codes_and_never_touches_an_upload(
    client: httpx.AsyncClient, owner: dict[str, str], owner_db: Database, wk: dict[str, Any],
    su: Any, new_company: Callable[..., Any], tmp_path: Path,
) -> None:  # fmt: skip
    root = BR.brands_dir()
    src = (
        next((p for p in sorted(root.iterdir()) if p.is_dir() and brand.seed_folder(p)), None)
        if root.is_dir()
        else None
    )
    if src is None:
        pytest.skip("design/brand/companies is not mounted")
    fresh, uploaded, nofolder = await new_company(), await new_company(), await new_company()
    for co in (fresh, uploaded):
        shutil.copytree(src, tmp_path / co["code"].lower())
    await brand_of(client, wk, su, owner, uploaded["code"], mono())
    assert await _seed(owner_db, tmp_path) == 1  # the fresh one; the uploaded one is left alone
    assert await _seed(owner_db, tmp_path) == 0
    got = (await client.get("/api/v1/brands", headers=owner)).json()["companies"]
    assert fresh["code"] in got and got[fresh["code"]]["version"] == 1
    assert nofolder["code"] not in got  # no folder, no seed: it shows its code
    states = await su.fetch(
        """SELECT b.version, b.state, b.source->>'kind' AS kind FROM org.company_brands b
           JOIN core.companies c ON c.id = b.company_id WHERE c.code = $1""",
        uploaded["code"],
    )
    assert [(r["state"], r["kind"]) for r in states] == [("proposed", "upload")]
