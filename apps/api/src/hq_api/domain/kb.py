"""The support knowledge base (prompt 10 §5, contract §19.4): versioned
articles of one company, the rule that answers verbatim, the grounded check.

  propose(...)        a new article, or a new version of `ref` -> proposed
                      (an agent's referral / official_link draft carries no
                      link and no code: the owner writes them, §5.1)
  approve(...)        proposed -> approved (the route consumes the owner's
                      step-up `support.kb` = ref@version first); the ref's
                      earlier approved version and an older approved article
                      with the same policy key are retired
  retire(...)         approved/proposed -> retired; expire_due(): approved
                      past expires_at -> expired (also checked at read time)
  search(...)         the company's articles (approved only unless asked),
                      Persian-normalised full-text candidates scored by the
                      overlap of words with the question and its variants
  best_faq(...)       the rule of §4.3.2: the top approved faq and the gap
                      to the second
  cited(...)          "KB-0042@3" refs -> the cited rows; an expired, retired
                      or proposed version is not a valid citation
  grounded(...)       every link, code and figure of a draft appears exactly
                      in one of the cited articles (code, never a model)
  guard_context(...)  hq_common.outbound_guard.Approved for one company: its
                      approved links, codes and identifiers, every company
                      code and the company's employee codes

An approved article is what may reach a customer without the owner, so
every row of one version is immutable (migration 0025) and everything here
runs inside the caller's company scope (RLS).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_common import customer_mask
from hq_common import outbound_guard as G

KINDS = ("faq", "policy", "procedure", "referral", "official_link", "safety")
LINK_KINDS = ("referral", "official_link")
REF = r"^KB-[0-9]{4,6}$"
CITE = re.compile(r"^(KB-[0-9]{4,6})@([0-9]{1,6})$")
DEFAULT_VERBATIM = 0.9  # before a go-live card sets the company's own (shadow, mystery)
DEFAULT_MARGIN = 0.15
CANDIDATES = 25

# What core.fa_normalize does, in Python (the search side of the same text).
_FA = str.maketrans(
    {
        "\u064a": "\u06cc",
        "\u0649": "\u06cc",
        "\u0643": "\u06a9",
        "\u06c0": "\u0647",
        "\u0629": "\u0647",
        **{chr(0x06F0 + i): str(i) for i in range(10)},
        **{chr(0x0660 + i): str(i) for i in range(10)},
    }
)
_DROP = re.compile("[\u200c\u200d\u0640\u064b-\u065f\u0670]")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
STOP = frozenset(
    [
        "و",
        "در",
        "به",
        "از",
        "که",
        "را",
        "با",
        "این",
        "آن",
        "است",
        "هست",
        "یا",
        "برای",
        "تا",
        "هم",
        "من",
        "ما",
        "شما",
        "او",
        "چه",
        "چی",
        "چرا",
        "آیا",
        "یک",
        "بر",
        "باید",
        "می",
        "ها",
        "های",
        "رو",
        "کنم",
        "کنید",
        "کرد",
        "کردم",
        "شد",
        "شده",
        "بود",
        "the",
        "a",
        "an",
        "is",
        "are",
        "to",
        "of",
        "in",
        "on",
        "for",
        "and",
        "or",
        "i",
        "you",
        "my",
        "your",
        "it",
        "do",
        "does",
        "how",
        "what",
        "can",
    ]
)


class Variable(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")
    source: Literal["customer", "policy"] = "customer"


class Link(BaseModel):
    url: str = Field(min_length=4, max_length=2000)
    label_fa: str = Field(default="", max_length=200)


class Code(BaseModel):
    exchange: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,30}$")
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{3,40}$")


class Source(BaseModel):
    kind: Literal["owner_answer", "owner", "doc", "agent"]
    ref: str | None = Field(default=None, max_length=200)


class KbArticle(BaseModel):
    id: UUID
    ref: str
    company: str
    version: int
    kind: str
    key: str | None
    question_fa: str
    variants: list[str]
    answer_md: str
    variables: list[Variable]
    links: list[Link]
    codes: list[Code]
    status: Literal["proposed", "approved", "expired", "retired"]
    source: Source
    approved_at: datetime | None
    expires_at: datetime
    uses_30d: int
    sha256: str


def fa_normalize(text: str) -> str:
    """core.fa_normalize in Python: Arabic yeh/kaf and heh-yeh to Persian,
    Persian and Arabic digits to Latin, ZWNJ/ZWJ/tatweel/diacritics removed,
    lower case, one space."""
    text = unicodedata.normalize("NFKC", text).translate(_FA)
    return " ".join(_DROP.sub("", text).lower().split())


def words(text: str) -> set[str]:
    found = set(_WORD.findall(fa_normalize(text)))
    kept = {w for w in found if w not in STOP}
    return kept or found


def similarity(question: str, texts: Iterable[str]) -> float:
    """0..1: 1 for the same normalised words; otherwise the best Jaccard
    overlap of word sets with any of the texts."""
    q = words(question)
    best = 0.0
    nq = fa_normalize(question).strip(" ?؟!.")
    for t in texts:
        if not t:
            continue
        if fa_normalize(t).strip(" ?؟!.") == nq:
            return 1.0
        w = words(t)
        if q and w:
            best = max(best, len(q & w) / len(q | w))
    return round(best, 4)


def sha256(fields: dict[str, Any]) -> str:
    keys = ("kind", "key", "question_fa", "variants", "answer_md", "variables", "links", "codes")
    canon = json.dumps({k: fields.get(k) for k in keys}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


def status_of(
    r: dict[str, Any], now: datetime | None = None
) -> Literal["proposed", "approved", "expired", "retired"]:
    """An approved article past its expiry reads `expired` even before the
    sweep marks it."""
    st = str(r["status"])
    if st == "approved" and r["expires_at"] is not None:
        ref_now = now or datetime.now(r["expires_at"].tzinfo)
        if r["expires_at"] <= ref_now:
            return "expired"
    if st == "approved":
        return "approved"
    if st == "expired":
        return "expired"
    return "retired" if st == "retired" else "proposed"


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def render(r: dict[str, Any], company: str) -> KbArticle:
    return KbArticle(
        id=r["id"],
        ref=r["ref"],
        company=company,
        version=r["version"],
        kind=r["kind"],
        key=r["key"],
        question_fa=r["question_fa"],
        variants=list(r["variants"] or []),
        answer_md=r["answer_md"],
        variables=[Variable(**v) for v in _j(r["variables"]) or []],
        links=[Link(**x) for x in _j(r["links"]) or []],
        codes=[Code(**x) for x in _j(r["codes"]) or []],
        status=status_of(r),
        source=Source(**(_j(r["source"]) or {"kind": "owner"})),
        approved_at=r["approved_at"],
        expires_at=r["expires_at"],
        uses_30d=int(r.get("uses_30d") or 0),
        sha256=r["sha256"],
    )


USES_SQL = """(SELECT count(*) FROM support.messages m
               WHERE m.company_id = a.company_id AND m.direction = 'out' AND m.status = 'sent'
                 AND m.at > now() - interval '30 days'
                 AND (a.ref || '@' || a.version) = ANY(m.kb_refs)) AS uses_30d"""


async def load(tx: Tx, ref: str, version: int | None = None) -> dict[str, Any]:
    """One version of an article (the latest when `version` is None)."""
    row = await tx.first(
        f"""SELECT a.*, {USES_SQL} FROM support.kb_articles a
            WHERE a.ref = :ref AND (CAST(:v AS int) IS NULL OR a.version = :v)
            ORDER BY a.version DESC LIMIT 1""",  # noqa: S608 - module constants; values bound
        ref=ref,
        v=version,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no article {ref}")
    return row


async def propose(
    tx: Tx,
    *,
    company_id: UUID,
    kind: str,
    question_fa: str,
    answer_md: str,
    by_kind: Literal["owner", "agent", "service"],
    by_code: str,
    key: str | None = None,
    variants: list[str] | None = None,
    variables: list[dict[str, Any]] | None = None,
    links: list[dict[str, Any]] | None = None,
    codes: list[dict[str, Any]] | None = None,
    source: dict[str, Any] | None = None,
    ref: str | None = None,
    expiry_days: int = 180,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise ApiError(422, "validation_failed", fields={"kind": "unknown article kind"})
    if kind == "policy" and not key:
        raise ApiError(422, "validation_failed", fields={"key": "a policy article needs its key"})
    if by_kind != "owner":
        # Referral codes and links come only from the owner (§19.0): an agent's
        # draft leaves them empty, and its text never carries customer data.
        if links or codes:
            raise ApiError(
                422,
                "validation_failed",
                fields={"links": "only the owner writes links and referral codes"},
            )
        question_fa = customer_mask.quote(question_fa, max_chars=1000)
        answer_md = customer_mask.quote(answer_md, max_chars=8000)
        variants = [customer_mask.quote(v, max_chars=300) for v in variants or []]
    fields: dict[str, Any] = {
        "kind": kind,
        "key": key,
        "question_fa": question_fa.strip(),
        "variants": [v.strip() for v in (variants or []) if v.strip()][:50],
        "answer_md": answer_md.strip(),
        "variables": variables or [],
        "links": links or [],
        "codes": codes or [],
    }
    version = 1
    if ref is not None:
        prev = await tx.first(
            """SELECT company_id, kind, max(version) OVER () AS top FROM support.kb_articles
               WHERE ref = :ref LIMIT 1""",
            ref=ref,
        )
        if prev is None or prev["company_id"] != company_id:
            raise ApiError(404, "not_found", f"no article {ref} in this company")
        if prev["kind"] != kind:
            raise ApiError(422, "validation_failed", fields={"kind": f"{ref} is a {prev['kind']}"})
        version = int(prev["top"]) + 1
    row = await tx.one(
        """INSERT INTO support.kb_articles (ref, company_id, version, kind, key, question_fa, variants,
               answer_md, variables, links, codes, source, sha256, expires_at,
               proposed_by_kind, proposed_by_code)
           VALUES (COALESCE(:ref, 'KB-' || lpad(nextval('support.kb_ref_seq')::text, 4, '0')), :co, :v,
                   :kind, :key, :q, :variants, :a, CAST(:vars AS jsonb), CAST(:links AS jsonb),
                   CAST(:codes AS jsonb), CAST(:src AS jsonb), :sha,
                   now() + make_interval(days => :days), :bk, :bc)
           RETURNING *""",
        ref=ref,
        co=company_id,
        v=version,
        kind=kind,
        key=key,
        q=fields["question_fa"],
        variants=fields["variants"],
        a=fields["answer_md"],
        vars=json.dumps(fields["variables"], ensure_ascii=False),
        links=json.dumps(fields["links"], ensure_ascii=False),
        codes=json.dumps(fields["codes"], ensure_ascii=False),
        src=json.dumps(source or {"kind": "owner" if by_kind == "owner" else "agent"}),
        sha=sha256(fields),
        days=max(1, min(expiry_days, 3650)),
        bk=by_kind,
        bc=by_code[:64],
    )
    return {**row, "uses_30d": 0}


async def approve(
    tx: Tx, ref: str, version: int, *, step_up_id: UUID | None, expiry_days: int
) -> dict[str, Any]:
    row = await tx.first(
        "SELECT * FROM support.kb_articles WHERE ref = :r AND version = :v FOR UPDATE",
        r=ref,
        v=version,
    )
    if row is None:
        raise ApiError(404, "not_found", f"no article {ref}@{version}")
    if row["status"] != "proposed":
        raise ApiError(409, "validation_failed", f"{ref}@{version} is {row['status']}")
    await tx.exec(
        """UPDATE support.kb_articles SET status = 'retired', retired_at = now(), updated_at = now()
           WHERE company_id = :co AND status = 'approved'
             AND (ref = :r OR (CAST(:k AS text) IS NOT NULL AND key = :k))""",
        co=row["company_id"],
        r=ref,
        k=row["key"],
    )
    return await tx.one(
        f"""UPDATE support.kb_articles a SET status = 'approved', approved_at = now(),
                approved_step_up_id = :su, expires_at = now() + make_interval(days => :d),
                reminded_at = NULL, updated_at = now()
            WHERE id = :id RETURNING a.*, {USES_SQL}""",  # noqa: S608 - module constants
        id=row["id"],
        su=step_up_id,
        d=max(1, min(expiry_days, 3650)),
    )


async def retire(tx: Tx, ref: str) -> dict[str, Any]:
    row = await tx.first(
        """UPDATE support.kb_articles SET status = 'retired', retired_at = now(), updated_at = now()
           WHERE ref = :r AND status IN ('approved', 'proposed', 'expired')
           RETURNING id""",
        r=ref,
    )
    if row is None:
        await load(tx, ref)  # 404 when unknown
    return await load(tx, ref)


async def expire_due(tx: Tx) -> int:
    """Approved articles past their expiry become `expired` (rule-only)."""
    return await tx.exec(
        """UPDATE support.kb_articles SET status = 'expired', updated_at = now()
           WHERE status = 'approved' AND expires_at <= now()"""
    )


def _tsquery(text: str) -> str | None:
    found = sorted(words(text))[:30]
    return " | ".join(found) if found else None


async def search(
    tx: Tx,
    company_id: UUID,
    q: str,
    *,
    kinds: Iterable[str] | None = None,
    include_proposed: bool = False,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Articles of one company for `q`, best first, each with `score`. Only
    approved, unexpired versions unless `include_proposed` (the support
    lead's view also shows proposed ones)."""
    query = _tsquery(q)
    if query is None:
        return []
    statuses = ["approved", "proposed"] if include_proposed else ["approved"]
    rows = await tx.all(
        f"""SELECT a.*, {USES_SQL} FROM support.kb_articles a
            WHERE a.company_id = :co AND a.status = ANY(:st)
              AND (a.status <> 'approved' OR a.expires_at > now())
              AND (CAST(:kinds AS text[]) IS NULL OR a.kind = ANY(CAST(:kinds AS text[])))
              AND (a.search @@ to_tsquery('simple', :q)
                   OR to_tsvector('simple', core.fa_normalize(a.answer_md)) @@ to_tsquery('simple', :q))
            LIMIT :n""",  # noqa: S608 - module constants; values are bound
        co=company_id,
        st=statuses,
        kinds=list(kinds) if kinds else None,
        q=query,
        n=CANDIDATES * 2,
    )
    for r in rows:
        r["score"] = similarity(q, [r["question_fa"], *(r["variants"] or [])])
    rows.sort(key=lambda r: (-r["score"], r["ref"], -r["version"]))
    return rows[: max(1, min(limit, 50))]


async def best_faq(
    tx: Tx, company_id: UUID, text: str
) -> tuple[dict[str, Any] | None, float, float]:
    """The top approved faq for a customer's words, its score and the
    second's (the margin rule: a verbatim answer needs a clear winner)."""
    rows = await search(tx, company_id, text, kinds=["faq"], limit=CANDIDATES)
    if not rows:
        return None, 0.0, 0.0
    second = rows[1]["score"] if len(rows) > 1 else 0.0
    return rows[0], float(rows[0]["score"]), float(second)


async def cited(
    tx: Tx, company_id: UUID, refs: Iterable[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """The valid cited articles and the refs that are not valid (unknown,
    another company's, proposed, expired or retired)."""
    good: list[dict[str, Any]] = []
    bad: list[str] = []
    for raw in dict.fromkeys(refs):
        m = CITE.match(raw)
        row = (
            await tx.first(
                """SELECT * FROM support.kb_articles WHERE ref = :r AND version = :v
                     AND company_id = :co""",
                r=m.group(1),
                v=int(m.group(2)),
                co=company_id,
            )
            if m
            else None
        )
        if row is None or status_of(row) != "approved":
            bad.append(raw)
        else:
            good.append(row)
    return good, bad


_NUMBER = re.compile(r"\d+(?:[.,/]\d+)*")


def _article_text(a: dict[str, Any]) -> str:
    parts = [a["question_fa"], *(a["variants"] or []), a["answer_md"]]
    parts += [str(x.get("url", "")) for x in _j(a["links"]) or []]
    parts += [str(x.get("code", "")) for x in _j(a["codes"]) or []]
    return "\n".join(parts)


def grounded(body: str, articles: list[dict[str, Any]]) -> list[str]:
    """What in `body` is not exactly in the cited articles: [] = grounded.
    Problems: "no_citation", "link:<url>", "code:<code>", "figure:<n>"."""
    if not articles:
        return ["no_citation"]
    source = G.normalise("\n".join(_article_text(a) for a in articles))
    links = {G.normalise_url(str(x.get("url", ""))) for a in articles for x in _j(a["links"]) or []}
    links |= set(G.urls(source))
    codes = {str(x.get("code", "")).casefold() for a in articles for x in _j(a["codes"]) or []}
    codes |= {c.casefold() for c in G.referral_codes(source)}
    problems: list[str] = []
    for url in G.urls(body):
        if url not in links:
            problems.append(f"link:{url[:120]}")
    for code in G.referral_codes(body):
        if code.casefold() not in codes:
            problems.append(f"code:{code[:40]}")
    numbers = set(_NUMBER.findall(source))
    for n in _NUMBER.findall(G.normalise(body)):
        if n not in numbers:
            problems.append(f"figure:{n[:20]}")
    return list(dict.fromkeys(problems))


async def approved_rows(tx: Tx, company_id: UUID) -> list[dict[str, Any]]:
    return await tx.all(
        """SELECT * FROM support.kb_articles
           WHERE company_id = :co AND status = 'approved' AND expires_at > now()""",
        co=company_id,
    )


async def guard_context(tx: Tx, company_id: UUID, *, extra_ids: Iterable[str] = ()) -> G.Approved:
    """The outbound guard's view of one company: only ITS approved links and
    codes (another company's are unknown here), every company code, its
    employees' codes; `extra_ids` = the current customer's own identifiers."""
    approved = G.approved_from_articles(await approved_rows(tx, company_id))
    companies = await tx.all("SELECT code FROM core.companies")
    employees = await tx.all(
        "SELECT code FROM core.employees WHERE company_id = :co", co=company_id
    )
    return dataclasses.replace(
        approved,
        identifiers=approved.identifiers | frozenset(i for i in extra_ids if i),
        company_codes=frozenset(r["code"] for r in companies),
        employee_codes=frozenset(r["code"] for r in employees),
    )


async def policy_value(tx: Tx, company_id: UUID, key: str) -> str | None:
    """The one approved policy article for `key` (e.g. vip.min_balance)."""
    row = await tx.first(
        """SELECT answer_md FROM support.kb_articles
           WHERE company_id = :co AND key = :k AND status = 'approved' AND expires_at > now()""",
        co=company_id,
        k=key,
    )
    return str(row["answer_md"]) if row else None
