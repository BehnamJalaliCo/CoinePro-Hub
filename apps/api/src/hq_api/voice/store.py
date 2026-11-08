"""The voice layer's records (schema talk): the light, the usage rows, the meter, the owner's cap.

Every function takes the caller's transaction. The data is the holding's, so callers open it over
every company (`hub.db.tx(await hub.companies.ids())`), as the owner's routes and the worker do.
The provider's key is never here: a provider's key is only ever in OpenBao.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from hq_api import events
from hq_api.db import Tx
from hq_api.voice import catalog

DEFAULT_WARN_AT = 0.8
TALK_TASK_CLASSES = ("talk_turn", "talk_summary")
LIGHT_STATES = ("missing", "checking", "ok", "failing", "capped")
# A check that never answered (the worker went away) must not leave the light yellow for ever.
CHECKING_STALE_MIN = 5


@dataclass(frozen=True)
class Clock:
    now: datetime
    tz: str
    day: date  # today, in the owner's zone
    day_start: datetime
    month_start: datetime
    day_of_month: int
    days_in_month: int


async def clock(tx: Tx) -> Clock:
    row = await tx.one(
        """WITH t AS (SELECT COALESCE((SELECT timezone FROM owner.settings WHERE id = 1),
                                      'Asia/Tehran') AS tz)
           SELECT now() AS now, tz,
                  (now() AT TIME ZONE tz)::date AS day,
                  (date_trunc('day', now() AT TIME ZONE tz) AT TIME ZONE tz) AS day_start,
                  (date_trunc('month', now() AT TIME ZONE tz) AT TIME ZONE tz) AS month_start,
                  extract(day FROM now() AT TIME ZONE tz)::int AS dom,
                  extract(day FROM (date_trunc('month', now() AT TIME ZONE tz)
                                    + interval '1 month - 1 day'))::int AS dim
           FROM t"""
    )
    return Clock(
        now=row["now"],
        tz=row["tz"],
        day=row["day"],
        day_start=row["day_start"],
        month_start=row["month_start"],
        day_of_month=int(row["dom"]),
        days_in_month=int(row["dim"]),
    )


# ---------------------------------------------------------------- settings --
def settings_of(block: dict[str, Any] | None) -> dict[str, Any]:
    """`owner.settings.voice` with its defaults: no cap (null) until the owner sets one."""
    b = dict(block or {})
    cap = b.get("month_cap_usd")
    chain = [str(x) for x in (b.get("chain") or catalog.load().default_chain)]
    return {
        # the owner, 2026-11-08: voice is off; the talk answers in text alone until he turns it on
        # (the voice code stays, it does not run and is never mentioned)
        "enabled": bool(b.get("enabled", False)),
        "month_cap_usd": float(cap) if cap is not None else None,
        "warn_at": float(b.get("warn_at") or DEFAULT_WARN_AT),
        "chain": chain,
        # the owner, 2026-11-05: Piper only after he chose a local voice (off: text, never a bad voice)
        "local": bool(b.get("local", False)),
    }


async def voice_settings(tx: Tx) -> dict[str, Any]:
    return settings_of(await tx.scalar("SELECT voice FROM owner.settings WHERE id = 1"))


def chain_for(first: str, configured: list[str], *, local: bool = True) -> list[str]:
    """The walk order: the persona's engine, then the owner's chain, Piper last, and Piper only
    while the owner's local voice is on (`local`); off, the walk ends with the remote engines and a
    sentence none of them could say stays text (the owner, 2026-11-05: never a bad voice)."""
    cat = catalog.load()
    if (
        first == catalog.LOCAL and local
    ):  # a persona that chose the free local voice never spends by itself
        return [catalog.LOCAL]
    seen: list[str] = []
    for key in [first, *configured]:
        if key in cat.engines and key != catalog.LOCAL and key not in seen:
            seen.append(key)
    return [*seen, catalog.LOCAL] if local else seen


# ------------------------------------------------------------------ light --
async def ensure_rows(tx: Tx, holding_id: UUID) -> None:
    for e in catalog.load().engines.values():
        await tx.exec(
            """INSERT INTO talk.engine_state (engine, company_id, provider, state)
               VALUES (:e, :co, :p, :s) ON CONFLICT (engine) DO NOTHING""",
            e=e.key,
            co=holding_id,
            p=e.provider,
            s="missing",
        )


async def states(tx: Tx, holding_id: UUID) -> dict[str, dict[str, Any]]:
    await ensure_rows(tx, holding_id)
    rows = await tx.all("SELECT * FROM talk.engine_state")
    return {r["engine"]: r for r in rows}


async def set_state(
    tx: Tx, engine: str, state: str, reason_fa: str | None, *, checked: bool = True
) -> bool:
    """Move the light; True when it changed (the caller then emits `voice.engine`)."""
    cur = await tx.first(
        "SELECT state, reason_fa FROM talk.engine_state WHERE engine = :e", e=engine
    )
    changed = cur is None or cur["state"] != state or cur["reason_fa"] != reason_fa
    await tx.exec(
        """UPDATE talk.engine_state SET state = :s, reason_fa = :r, updated_at = now(),
               checked_at = CASE WHEN :c THEN now() ELSE checked_at END WHERE engine = :e""",
        s=state,
        r=reason_fa,
        c=checked,
        e=engine,
    )
    return changed


async def set_secret(tx: Tx, provider: str, is_set: bool) -> None:
    """The key was written (every engine of the provider is `checking` now) or removed (`missing`)."""
    await tx.exec(
        """UPDATE talk.engine_state SET secret_set = :set, state = :s, reason_fa = :r,
               checked_at = NULL, updated_at = now() WHERE provider = :p""",
        set=is_set,
        s="checking" if is_set else "missing",
        r=None if is_set else "کلید صدا داده نشده است.",
        p=provider,
    )


async def override_of(tx: Tx, engine: str) -> dict[str, Any] | None:
    raw = await tx.scalar(
        "SELECT price_override FROM talk.engine_state WHERE engine = :e", e=engine
    )
    if raw is None:
        return None
    return dict(raw) if isinstance(raw, dict) else dict(json.loads(raw))


async def set_override(tx: Tx, engine: str, price: dict[str, Any] | None) -> None:
    await tx.exec(
        """UPDATE talk.engine_state SET price_override = CAST(:p AS jsonb), updated_at = now()
           WHERE engine = :e""",
        p=json.dumps(price) if price is not None else None,
        e=engine,
    )


async def price_for(tx: Tx, engine: str, day: date) -> catalog.InForce:
    """The price in force for `engine` on `day`: the owner's own, else the table's."""
    e = catalog.load().engines[engine]
    price, source = catalog.effective_price(e, await override_of(tx, engine))
    return catalog.price_in_force(price, day, source=source)


# ----------------------------------------------------------------- usage --
async def month_usd(tx: Tx, since: datetime) -> Decimal:
    v = await tx.scalar(
        "SELECT COALESCE(sum(usd), 0) FROM talk.voice_usage WHERE at >= :s", s=since
    )
    return Decimal(v or 0)


async def add_usage(
    tx: Tx,
    holding_id: UUID,
    *,
    engine: str,
    kind: str,
    persona: str,
    conversation_ref: str | None,
    turn_id: str | None,
    seq: int | None,
    chars: int,
    text_tokens: int,
    audio_tokens: int,
    seconds: float,
    price: catalog.InForce,
) -> Decimal:
    """One row for one sentence: the provider's counts x the price in force now."""
    usd = price.usd(text_tokens, audio_tokens)
    provider = catalog.load().engines[engine].provider
    await tx.exec(
        """INSERT INTO talk.voice_usage (company_id, engine, provider, kind, persona,
               conversation_ref, turn_id, seq, chars, text_tokens, audio_tokens, seconds, price, usd)
           VALUES (:co, :e, :p, :k, :persona, :cv, :t, :seq, :ch, :tt, :at, :sec,
                   CAST(:price AS jsonb), :usd)""",
        co=holding_id,
        e=engine,
        p=provider,
        k=kind,
        persona=persona[:80],
        cv=conversation_ref,
        t=turn_id,
        seq=seq,
        ch=chars,
        tt=text_tokens,
        at=audio_tokens,
        sec=round(seconds, 3),
        price=json.dumps(price.as_json()),
        usd=usd,
    )
    return usd


# ----------------------------------------------------------------- meter --
def _money(value: Any) -> float:
    return float(round(Decimal(value or 0), 8))


async def meter(tx: Tx, period: str, holding_id: UUID) -> dict[str, Any]:
    """`VoiceMeter` (contract §32.6) for today or the month, all by code."""
    clk = await clock(tx)
    start = clk.day_start if period == "today" else clk.month_start
    cfg = await voice_settings(tx)
    by_engine = await tx.all(
        """SELECT engine, COALESCE(sum(usd), 0) AS usd, COALESCE(sum(seconds), 0) AS seconds,
                  COALESCE(sum(audio_tokens), 0)::bigint AS audio_tokens
           FROM talk.voice_usage WHERE at >= :s GROUP BY engine ORDER BY sum(usd) DESC, engine""",
        s=start,
    )
    by_persona = await tx.all(
        """SELECT persona, COALESCE(sum(usd), 0) AS usd, COALESCE(sum(seconds), 0) AS seconds
           FROM talk.voice_usage WHERE at >= :s AND kind = 'speech' AND persona <> ''
           GROUP BY persona ORDER BY sum(usd) DESC, persona""",
        s=start,
    )
    voice_usd = sum((Decimal(r["usd"]) for r in by_engine), Decimal(0))
    month = await month_usd(tx, clk.month_start)
    projected = month / clk.day_of_month * clk.days_in_month
    talk = await tx.first(
        """SELECT COALESCE(sum(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)
                  + COALESCE(cache_read_tokens, 0) + COALESCE(cache_write_tokens, 0)), 0)::bigint
                  AS tokens,
                  COALESCE(sum(COALESCE(cost_usd, 0) + COALESCE(equiv_cost_usd, 0)), 0) AS usd
           FROM llm.calls WHERE task_class = ANY(:tc) AND started_at >= :s""",
        tc=list(TALK_TASK_CLASSES),
        s=start,
    )
    st = await states(tx, holding_id)
    note = None
    for e in catalog.load().engines.values():
        if st.get(e.key, {}).get("secret_set") or e.key == catalog.LOCAL:
            price, _ = catalog.effective_price(e, await override_of(tx, e.key))
            note = catalog.next_price_note(price, clk.day, title_fa=e.title_fa)
            if note:
                break
    return {
        "period": period,
        "voice_usd": _money(voice_usd),
        "cap_usd": cfg["month_cap_usd"],
        "projected_usd": _money(projected),
        "by_engine": [
            {
                "engine": r["engine"],
                "usd": _money(r["usd"]),
                "seconds": float(round(Decimal(r["seconds"]), 3)),
                "audio_tokens": int(r["audio_tokens"]),
            }
            for r in by_engine
        ],
        "by_persona": [
            {
                "persona": r["persona"],
                "usd": _money(r["usd"]),
                "seconds": float(round(Decimal(r["seconds"]), 3)),
            }
            for r in by_persona
        ],
        "talk_tokens": int((talk or {}).get("tokens") or 0),
        "talk_usd_equiv": _money((talk or {}).get("usd")),
        "price_note_fa": note,
        "updated_at": datetime.now(UTC),
    }


# ----------------------------------------------------------------- events --
async def emit_engine(
    tx: Tx, holding_code: str, engine: str, state: str, reason_fa: str | None
) -> None:
    """`voice.engine` on the stream: the light of one engine moved."""
    await events.emit(
        tx,
        holding_code,
        "voice.engine",
        engine,
        {
            "engine": engine,
            "provider": catalog.load().engines[engine].provider,
            "state": state,
            "reason_fa": reason_fa,
        },
    )


async def emit_meter(tx: Tx, holding_code: str) -> None:
    """`voice.meter` on the stream: the counters the talk screen shows move live."""
    clk = await clock(tx)
    cfg = await voice_settings(tx)
    today = await tx.scalar(
        "SELECT COALESCE(sum(usd), 0) FROM talk.voice_usage WHERE at >= :s", s=clk.day_start
    )
    month = await month_usd(tx, clk.month_start)
    await events.emit(
        tx,
        holding_code,
        "voice.meter",
        None,
        {
            "today_usd": _money(today),
            "month_usd": _money(month),
            "cap_usd": cfg["month_cap_usd"],
            "projected_usd": _money(month / clk.day_of_month * clk.days_in_month),
        },
    )
