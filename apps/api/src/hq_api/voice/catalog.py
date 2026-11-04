"""The voice engines as data (apps/api/seed/voice/engines.yaml) and their prices by day.

Nothing here touches the database: the seed file is read once, and a price is a pure function of
(the table or the owner's override, the day). A scheduled change (`next`) applies by itself on its
day; the owner's override replaces the table's whole price object for that engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "voice" / "engines.yaml"
PER_M = Decimal(1_000_000)
LOCAL = "piper"  # always the chain's last link
WARN_DAYS = 14  # the app warns this many days before a `next` price
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@dataclass(frozen=True)
class Provider:
    key: str
    title_fa: str
    key_pattern: str | None
    kv_path: str | None
    host: str | None


@dataclass(frozen=True)
class EngineDef:
    key: str
    title_fa: str
    provider: str
    model: str
    languages: int
    rank_fa: str
    price: dict[str, Any]
    note_fa: str | None = None


@dataclass(frozen=True)
class Catalog:
    providers: dict[str, Provider]
    engines: dict[str, EngineDef]
    gemini_voices: tuple[dict[str, str], ...]
    piper_voices: tuple[dict[str, str], ...]
    voices_as_of: str
    sample_text_fa: str
    check_text_fa: str
    default_chain: tuple[str, ...]

    def engine(self, key: str) -> EngineDef | None:
        return self.engines.get(key)

    def provider_of(self, engine: str) -> Provider:
        return self.providers[self.engines[engine].provider]

    def engines_of(self, provider: str) -> list[EngineDef]:
        return [e for e in self.engines.values() if e.provider == provider]

    def voices_of(self, engine: str) -> list[dict[str, str]]:
        e = self.engines[engine]
        rows = self.piper_voices if e.provider == "local" else self.gemini_voices
        return [dict(r) for r in rows]


@lru_cache(maxsize=1)
def load() -> Catalog:
    raw = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))
    providers = {
        k: Provider(k, v["title_fa"], v.get("key_pattern"), v.get("kv_path"), v.get("host"))
        for k, v in raw["providers"].items()
    }
    engines = {
        e["key"]: EngineDef(
            key=e["key"],
            title_fa=e["title_fa"],
            provider=e["provider"],
            model=e["model"],
            languages=int(e["languages"]),
            rank_fa=e["rank_fa"],
            price=e["price"],
            note_fa=e.get("note_fa"),
        )
        for e in raw["engines"]
    }
    return Catalog(
        providers=providers,
        engines=engines,
        gemini_voices=tuple(raw["gemini_voices"]),
        piper_voices=tuple(raw["piper_voices"]),
        voices_as_of=str(raw["voices_as_of"]),
        sample_text_fa=str(raw["sample_text_fa"]),
        check_text_fa=str(raw["check_text_fa"]),
        default_chain=tuple(raw["default_chain"]),
    )


# ------------------------------------------------------------------ prices --
def parse_day(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True)
class InForce:
    """The price a sentence made on one day was charged at."""

    text_in_per_m: Decimal
    audio_out_per_m: Decimal
    audio_tokens_per_s: int
    source: str  # "table" | "owner"
    from_next: bool  # true when the table's `next` price applied that day

    def usd(self, text_tokens: int, audio_tokens: int) -> Decimal:
        return (
            Decimal(text_tokens) * self.text_in_per_m + Decimal(audio_tokens) * self.audio_out_per_m
        ) / PER_M

    def as_json(self) -> dict[str, Any]:
        return {
            "text_in_per_m": str(self.text_in_per_m),
            "audio_out_per_m": str(self.audio_out_per_m),
            "audio_tokens_per_s": self.audio_tokens_per_s,
            "source": self.source,
            "next_applied": self.from_next,
        }


def price_in_force(price: dict[str, Any], day: date, *, source: str = "table") -> InForce:
    """`price` is a table's (or the owner's) price object: the current figures until `valid_until`
    (inclusive), then `next` from its `from` day on (a `next` also applies from its own day even
    when `valid_until` is not set)."""
    nxt = price.get("next")
    use_next = False
    if nxt:
        start = parse_day(nxt.get("from"))
        until = parse_day(price.get("valid_until"))
        if (start is not None and day >= start) or (until is not None and day > until):
            use_next = True
    src = nxt if use_next and nxt else price
    return InForce(
        text_in_per_m=_dec(src["text_in_per_m"]),
        audio_out_per_m=_dec(src["audio_out_per_m"]),
        audio_tokens_per_s=int(price.get("audio_tokens_per_s") or 0),
        source=source,
        from_next=use_next,
    )


def next_price_note(price: dict[str, Any], today: date, *, title_fa: str = "") -> str | None:
    """A plain Persian line when a `next` price starts within WARN_DAYS (the app shows it)."""
    nxt = price.get("next")
    if not nxt:
        return None
    start = parse_day(nxt.get("from"))
    if start is None or not (today < start <= today + timedelta(days=WARN_DAYS)):
        return None
    old = _dec(price["audio_out_per_m"])
    new = _dec(nxt["audio_out_per_m"])
    days = (start - today).days
    when = f"از {_jalali_words(start)}"
    if old > 0 and new >= old * 2:
        what = "قیمت دو برابر میشود"
    elif old > 0 and new > old:
        what = f"قیمت از {old:g} به {new:g} دلار برای هر میلیون توکن صدا میرسد"
    elif new < old:
        what = f"قیمت از {old:g} به {new:g} دلار برای هر میلیون توکن صدا کم میشود"
    else:
        return None
    name = f" ({title_fa})" if title_fa else ""
    return f"{when} {what}{name}؛ {str(days).translate(_FA_DIGITS)} روز مانده."


def _jalali_words(d: date) -> str:
    """The Gregorian day as the owner reads it in the warning («۱ ژانویه»)."""
    months = (
        "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
        "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
    )  # fmt: skip
    return f"{str(d.day).translate(_FA_DIGITS)} {months[d.month - 1]}"


def effective_price(
    engine: EngineDef, override: dict[str, Any] | None
) -> tuple[dict[str, Any], str]:
    """(the price object in use, its source): the owner's override else the table's."""
    if override:
        return override, "owner"
    return engine.price, "table"
