"""Finding records (prompt 14 §4, contract §23.1, §23.9).

Everything here runs under the reader's clearance (app.clearance, RLS): a
record above it is never a candidate, so it is neither counted, ranked nor
quoted. Within what is visible, the ranking uses the record's metadata
(title, ref, searchable values, party names), its file text only where the
reader may see the content, and sensitive values only where the reader's
clearance reaches `confidential`. A snippet is cut from text the reader may
see. Postgres full text ('simple' over the Persian normaliser) plus pg_trgm
on the title; no embeddings, no model.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from hq_api import pagination
from hq_api.archive.common import J
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_common import persian

SNIPPET = 240


def norm(q: str) -> str:
    return persian.normalise(q.strip())[:200]


async def conf_rank(tx: Tx) -> int:
    v = await tx.scalar("SELECT rank FROM archive.levels WHERE key = 'confidential'")
    return int(v) if v is not None else 20


async def search(
    tx: Tx,
    *,
    q: str | None,
    scope: str | None = None,
    cls: str | None = None,
    level: str | None = None,
    party: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    offset = 0
    if cursor:
        got = pagination.decode(cursor, 1)
        offset = int((got or [0])[0])
    qn = norm(q) if q else ""
    if q is not None and len(qn) < 2:
        raise ApiError(422, "validation_failed", fields={"q": "at least 2 characters"})
    rows = await tx.all(
        """WITH q AS (SELECT plainto_tsquery('simple', core.fa_normalize(:q)) AS tq,
                             core.fa_normalize(:q) AS nq)
           SELECT r.id, r.ref, r.title_fa, r.class_key, r.level, r.level_rank, r.company_id, r.state,
                  co.code AS scope,
                  archive.can_see(r.level_rank, r.company_id) AS content,
                  CASE WHEN :q = '' THEN 0 ELSE
                    ts_rank_cd(COALESCE(r.meta_tsv, ''::tsvector), q.tq) * 2
                    + CASE WHEN archive.can_see(r.level_rank, r.company_id)
                           THEN ts_rank_cd(COALESCE(r.text_tsv, ''::tsvector), q.tq) ELSE 0 END
                    + archive.title_similarity(q.nq, core.fa_normalize(r.title_fa))
                  END AS score
           FROM archive.records r JOIN core.companies co ON co.id = r.company_id, q
           WHERE r.state <> 'disposed'
             AND (CAST(:scope AS text) IS NULL OR co.code = :scope)
             AND (CAST(:cls AS text) IS NULL OR r.class_key = :cls)
             AND (CAST(:lv AS text) IS NULL OR r.level = :lv)
             AND (CAST(:party AS text) IS NULL OR :party = ANY (r.party_refs))
             AND (CAST(:df AS date) IS NULL OR r.doc_date >= :df)
             AND (CAST(:dt AS date) IS NULL OR r.doc_date <= :dt)
             AND (:q = ''
                  OR r.meta_tsv @@ q.tq
                  OR core.fa_normalize(r.title_fa) LIKE '%' || core.like_escape(q.nq) || '%'
                  OR archive.title_similarity(q.nq, core.fa_normalize(r.title_fa)) >= 0.6
                  OR (archive.can_see(r.level_rank, r.company_id) AND r.text_tsv @@ q.tq)
                  OR (archive.can_see(GREATEST(r.level_rank, :conf), r.company_id) AND r.sens_tsv @@ q.tq))
           ORDER BY score DESC, r.created_at DESC, r.id
           LIMIT :lim OFFSET :off""",
        q=qn,
        scope=scope,
        cls=cls,
        lv=level,
        party=party,
        df=date_from,
        dt=date_to,
        conf=await conf_rank(tx),
        lim=limit + 1,
        off=offset,
    )
    items = []
    for r in rows[:limit]:
        items.append(
            {
                "ref": r["ref"],
                "title_fa": r["title_fa"],
                "class": r["class_key"],
                "scope": r["scope"],
                "level": r["level"],
                "state": r["state"],
                "snippet_fa": await snippet(tx, r, qn) if qn else "",
                "score": round(float(r["score"] or 0), 4),
            }
        )
    nxt = pagination.encode([offset + limit]) if len(rows) > limit else None
    return {"items": items, "next_cursor": nxt}


ASK_SQL = """
    WITH w AS (SELECT t, to_tsquery('simple', t || ':*') AS tq,
                      '%' || core.like_escape(t) || '%' AS pat
               FROM unnest(CAST(:words AS text[])) t WHERE t <> ''),
         qq AS (SELECT to_tsquery('simple', :tsq) AS tq)
    SELECT 'record' AS kind, r.id, r.ref, co.code AS company, r.company_id, r.title_fa AS title,
           r.class_key, r.level, r.doc_date, COALESCE(r.filed_at, r.created_at) AS at,
           archive.can_see(r.level_rank, r.company_id) AS content, m.hits, m.matched,
           ts_rank_cd(COALESCE(r.meta_tsv, ''::tsvector), qq.tq) * 2
             + CASE WHEN archive.can_see(r.level_rank, r.company_id)
                    THEN ts_rank_cd(COALESCE(r.text_tsv, ''::tsvector), qq.tq) ELSE 0 END AS rank
    FROM archive.records r JOIN core.companies co ON co.id = r.company_id, qq,
    LATERAL (
        SELECT count(*) AS hits, COALESCE(array_agg(w.pat), '{}') AS matched FROM w
        WHERE COALESCE(r.meta_tsv, ''::tsvector) @@ w.tq
           OR core.fa_normalize(r.title_fa) LIKE w.pat
           OR (archive.can_see(r.level_rank, r.company_id)
               AND COALESCE(r.text_tsv, ''::tsvector) @@ w.tq)
           OR (archive.can_see(GREATEST(r.level_rank, :conf), r.company_id)
               AND COALESCE(r.sens_tsv, ''::tsvector) @@ w.tq)
    ) m
    WHERE r.state <> 'disposed' AND m.hits > 0
      AND (CAST(:cos AS uuid[]) IS NULL OR r.company_id = ANY(:cos))
    ORDER BY m.hits DESC, rank DESC, at DESC LIMIT :lim
"""


async def ask_hits(
    tx: Tx, words: list[str], company_ids: list[Any] | None, limit: int
) -> list[dict[str, Any]]:
    """⟨1.7⟩ «از هاب بپرس» (contract §21.2, §23.9): the records matching the
    question's words, as the corpus ranks its candidates (`hits`, `matched`,
    `rank`). The caller has set the asker's clearance on `tx` (clearance.apply):
    a record above it is no candidate at all (RLS), so it is never counted,
    ranked or quoted; the file text is matched and quoted only where the
    content is visible, a sensitive value matched only from `confidential` up."""
    import re

    safe = [s for s in (re.sub(r"[^\w]", "", w) for w in words) if s]
    if not safe:
        return []
    rows = await tx.all(
        ASK_SQL,
        words=safe,
        tsq=" | ".join(f"{w}:*" for w in safe),
        conf=await conf_rank(tx),
        cos=company_ids,
        lim=limit,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        head = " · ".join(
            str(x) for x in (r["class_key"] or "draft", r["level"], r["doc_date"]) if x
        )
        body = await _ask_text(tx, r["id"], safe) if r["content"] else None
        out.append({**dict(r), "text": head + ("\n" + body if body else "")})
    return out


async def _ask_text(tx: Tx, record_id: Any, words: list[str]) -> str | None:
    """Up to three fragments of the current version's file text around the
    question's words (the content clearance only: RLS hides the files)."""
    got = await tx.scalar(
        """SELECT ts_headline('simple', t, to_tsquery('simple', :tsq),
                              'MaxWords=60, MinWords=15, StartSel=«, StopSel=», MaxFragments=3,
                               FragmentDelimiter=" … "')
           FROM (SELECT left(core.fa_normalize(COALESCE(string_agg(f.text, ' '), '')), 60000) AS t
                 FROM archive.record_files f JOIN archive.records x ON x.id = f.record_id
                 WHERE f.record_id = :r AND f.version_n = x.current_version AND f.destroyed_at IS NULL
                   AND NOT f.quarantined) s
           WHERE t <> ''""",
        r=record_id,
        tsq=" | ".join(f"{w}:*" for w in words),
    )
    return str(got) if got else None


async def snippet(tx: Tx, r: dict[str, Any], qn: str) -> str:
    """From the file text when the reader may see the content, else the title."""
    if r["content"]:
        got = await tx.scalar(
            """SELECT ts_headline('simple', t, plainto_tsquery('simple', core.fa_normalize(:q)),
                                  'MaxWords=30, MinWords=8, StartSel=«, StopSel=», MaxFragments=1')
               FROM (SELECT left(core.fa_normalize(COALESCE(string_agg(f.text, ' '), '')), 60000) AS t
                     FROM archive.record_files f JOIN archive.records x ON x.id = f.record_id
                     WHERE f.record_id = :r AND f.version_n = x.current_version AND f.destroyed_at IS NULL
                       AND NOT f.quarantined) s
               WHERE t <> '' AND to_tsvector('simple', t) @@ plainto_tsquery('simple', core.fa_normalize(:q))""",
            r=r["id"],
            q=qn,
        )
        if got:
            return str(got)[:SNIPPET]
    return str(r["title_fa"])[:SNIPPET]


async def listing(
    tx: Tx,
    *,
    scope: str | None,
    cls: str | None,
    folder: str | None,
    level: str | None,
    state: str | None,
    party: str | None,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
    expiring_within_days: int | None,
    held: bool | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    from hq_api.archive.records import RECORD_SQL

    before_t, before_id = pagination.time_id(cursor)
    today = datetime.now(UTC).date()
    horizon = (
        today + timedelta(days=expiring_within_days) if expiring_within_days is not None else None
    )
    qn = norm(q) if q else None
    rows = await tx.all(
        RECORD_SQL  # noqa: S608 - a module constant; every value is a bound parameter
        + """ WHERE (CAST(:scope AS text) IS NULL OR co.code = :scope)
                AND (CAST(:cls AS text) IS NULL OR r.class_key = :cls)
                AND (CAST(:folder AS text) IS NULL OR f.ref = :folder)
                AND (CAST(:lv AS text) IS NULL OR r.level = :lv)
                AND (CAST(:st AS text) IS NULL OR r.state = :st)
                AND (CAST(:party AS text) IS NULL OR :party = ANY (r.party_refs))
                AND (CAST(:df AS date) IS NULL OR r.doc_date >= :df)
                AND (CAST(:dt AS date) IS NULL OR r.doc_date <= :dt)
                AND (CAST(:hz AS date) IS NULL OR EXISTS (
                     SELECT 1 FROM unnest(r.watch_dates) d WHERE d BETWEEN :today AND :hz))
                AND (CAST(:held AS boolean) IS NULL
                     OR (cardinality(archive.held_by(r.id)) > 0) = CAST(:held AS boolean))
                AND (CAST(:q AS text) IS NULL OR r.ref = :q
                     OR core.fa_normalize(r.title_fa) LIKE '%' || core.like_escape(core.fa_normalize(:q)) || '%'
                     OR r.meta_tsv @@ plainto_tsquery('simple', core.fa_normalize(:q)))
                AND (CAST(:bt AS timestamptz) IS NULL
                     OR (r.created_at, r.id) < (CAST(:bt AS timestamptz), CAST(:bid AS uuid)))
              ORDER BY r.created_at DESC, r.id DESC LIMIT :lim""",
        scope=scope,
        cls=cls,
        folder=folder,
        lv=level,
        st=state,
        party=party,
        df=date_from,
        dt=date_to,
        hz=horizon,
        today=today,
        held=held,
        q=qn,
        bt=before_t,
        bid=before_id,
        lim=limit + 1,
    )
    return pagination.page(rows, limit, ("created_at", "id"))


async def text_of(tx: Tx, r: dict[str, Any], version: int | None) -> str | None:
    """The text of a version's files (content clearance; RLS hides it otherwise)."""
    got = await tx.scalar(
        """SELECT string_agg(f.name || E':\n' || COALESCE(f.text, ''), E'\n\n' ORDER BY f.name)
           FROM archive.record_files f
           WHERE f.record_id = :r AND f.version_n = :v AND f.destroyed_at IS NULL AND NOT f.quarantined""",
        r=r["id"],
        v=version or r["current_version"],
    )
    return str(got) if got else None


def brief(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": r["ref"],
        "title_fa": r["title_fa"],
        "class": r["class_key"],
        "scope": r["scope"],
        "level": r["level"],
        "state": r["state"],
        "metadata": J(r["metadata"], {}),
    }
