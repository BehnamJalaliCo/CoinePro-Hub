"""W23 (2026-11-11): the owner is addressed as «تو» in what the hub's code writes for him.

The owner, the holding's managing director, is «تو», never «شما», and is told what to do with a
singular imperative («بزن», «بده», «ببین»), never a plural one. The modules swept for it (their
string constants; docstrings aside, they may quote someone) and the seed texts he reads say no
«شما», «خودتان» or plural verb. The few strings in them that speak to someone else stay as they
are, each named in `ELSEWHERE` with its reason.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import yaml

import hq_api

SEED = Path(str(hq_api.__file__)).resolve().parents[2] / "seed"
LETTER = "\u0621-\u063a\u0641-\u064a\u0670-\u06d3\u200c"  # Persian letters and the ZWNJ
PLURAL = re.compile(
    rf"(?<![{LETTER}])(?:شما(?:ست)?|خودتان|"
    r"(?:کنید|بکنید|نکنید|بزنید|نزنید|بدهید|ندهید|ببینید|بچسبانید|بگذارید|بنویسید|بگویید|"
    r"بپرسید|بفرستید|نفرستید|نفرستادید|ببرید|بروید|بخوانید|بیندازید|بیاورید|بسازید|بگیرید|"
    r"بمانید|باشید|بخواهید|بسنجید|بردارید|شوید|بشوید|گردانید|دهید|"
    r"کرده‌اید|نداشته‌اید|گذاشته‌اید|ساختید|خواستید|گفتید|بردید|دادید|زدید|کردید|"
    r"میخواهید|نمیخواهید|می‌خواهید|میتوانید|می‌توانید|دارید|ندارید|هستید|میبینید|بدانید))"
    rf"(?![{LETTER}])"
)

# every module swept here: what the owner reads of each is «تو»
MODULES = (
    "hq_api.domain.ads",
    "hq_api.domain.advisor",
    "hq_api.domain.affiliate_gaps",
    "hq_api.domain.automations",
    "hq_api.domain.backups",
    "hq_api.domain.briefings",
    "hq_api.domain.catalogue",
    "hq_api.domain.creative_overlay",
    "hq_api.domain.dispatch",
    "hq_api.domain.erase",
    "hq_api.domain.files",
    "hq_api.domain.hiring",
    "hq_api.domain.home",
    "hq_api.domain.hub_ops",
    "hq_api.domain.kits",
    "hq_api.domain.leads",
    "hq_api.domain.links",
    "hq_api.domain.newsletter",
    "hq_api.domain.notify",
    "hq_api.domain.personas",
    "hq_api.domain.playbooks",
    "hq_api.domain.routines",
    "hq_api.domain.rules",
    "hq_api.domain.tech_summary",
    "hq_api.domain.usage",
    "hq_api.routes.links",
    "hq_api.routes.voice_engines",
    "hq_api.talk.cards",
    "hq_api.talk.context",
    "hq_api.talk.engine",
    "hq_api.talk.player",
    "hq_api.talk.scrub",
    "hq_api.talk.service",
    "hq_api.voice.engines.gemini",
    "hq_api.voice.jobs",
    "hq_api.voice.speaker",
)

# strings of these modules that are not addressed to the owner (module -> fragment -> why)
ELSEWHERE: dict[str, dict[str, str]] = {
    "hq_api.talk.cards": {
        "شما را به این جلسه آورد": "ask_brief: the brief of the asked agent, not the owner",
        "شما در آن حاضر هستید": "ask_brief: the brief of the asked agent, not the owner",
    },
    "hq_api.domain.leads": {
        "با این سرنخ تماس بگیرید.": "the follow-up work's brief for the company's sales role",
    },
    "hq_api.domain.affiliate_gaps": {
        "لطفاً تسویه‌ی این ماه را بررسی کنید و نتیجه را برای ما بنویسید.": (
            "the letter to the affiliate partner, a third party"
        ),
    },
}

# the seed texts the owner reads: the connection guides, the key answer, the voice sample
SEED_TEXTS = (
    *sorted((SEED / "connection_guides").glob("*.md")),
    SEED / "talk" / "secrets.yaml",
    SEED / "voice" / "engines.yaml",
)


def strings_of(source: str) -> list[ast.Constant]:
    """Every string constant of a module, its docstrings aside."""
    tree = ast.parse(source)
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
    ]


def plural_in(name: str) -> list[str]:
    module = importlib.import_module(name)
    source = Path(str(module.__file__)).read_text(encoding="utf-8")
    allowed = ELSEWHERE.get(name, {})
    found = []
    for node in strings_of(source):
        text = str(node.value)
        for fragment in allowed:
            text = text.replace(fragment, "")
        found += [f"{node.lineno}: {m.group(0)}" for m in PLURAL.finditer(text)]
    return found


def test_the_pattern_finds_a_plural_and_spares_the_words_that_only_look_like_one() -> None:
    for said in ("فرمان تازه بدهید.", "سؤال از شما", "این تصمیم شماست", "از ترمینال خودتان",
                 "اگر لازمش دارید", "تا نگه نداشته‌اید", "«کلید را بدهید»"):  # fmt: skip
        assert PLURAL.search(said), said
    for said in ("شماره‌ی کار", "شمارنده‌ی کارها", "میشماریم", "شمال", "شمایل", "فرمان تازه بده.", "کلید را بدهد",
                 "کلید تازه", "تأیید شد", "باید", "تولید", "از تو چه لازم است", "خودت گفتی"):  # fmt: skip
        assert not PLURAL.search(said), said


def test_what_the_owner_reads_of_the_swept_modules_says_tu() -> None:
    for name in MODULES:
        assert plural_in(name) == [], name


def test_every_kept_plural_is_still_there_and_still_not_for_the_owner() -> None:
    for name, allowed in ELSEWHERE.items():
        assert name in MODULES, name
        source = Path(str(importlib.import_module(name).__file__)).read_text(encoding="utf-8")
        for fragment, why in allowed.items():
            assert fragment in source and why, (name, fragment)


def test_the_seed_texts_the_owner_reads_say_tu() -> None:
    assert len(SEED_TEXTS) > 2
    for path in SEED_TEXTS:
        text = path.read_text(encoding="utf-8")
        assert PLURAL.findall(text) == [], path.name
    answer = yaml.safe_load((SEED / "talk" / "secrets.yaml").read_text(encoding="utf-8"))
    assert answer["answer_fa"] == "کلید را با دکمه‌ی 🔑 بده."
