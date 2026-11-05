"""Prompt 23.2 (migration 0046): a ref default pads to its width but never cuts.

Before 0046 every `ref` default was `lpad(nextval(seq)::text, w, '0')`, and lpad cuts a longer string: once
`meetings.meeting_ref_seq` passed 9999 its refs repeated (29300..29309 -> MT-2930) and the meetings planner failed on
`meetings_ref_key` every minute, so no meeting was made from 2026-11-03.
"""

from __future__ import annotations

from typing import Any


async def test_no_ref_default_cuts_a_long_number(su: Any) -> None:
    left = await su.fetch(
        """SELECT ns.nspname || '.' || c.relname || '.' || a.attname AS col
             FROM pg_attrdef d
             JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
             JOIN pg_class c ON c.oid = d.adrelid
             JOIN pg_namespace ns ON ns.oid = c.relnamespace
            WHERE pg_get_expr(d.adbin, d.adrelid) LIKE '%lpad((nextval(%'"""
    )
    assert [r["col"] for r in left] == []
    meeting = await su.fetchval(
        """SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d
             JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
            WHERE d.adrelid = 'meetings.meetings'::regclass AND a.attname = 'ref'"""
    )
    assert meeting.startswith(
        "core.pad_ref('MT-'::text, nextval('meetings.meeting_ref_seq'::regclass), 4)"
    )


async def test_pad_ref_pads_and_never_cuts_for_the_app_roles(su: Any) -> None:
    async with su.transaction():
        await su.execute("SET LOCAL ROLE hq_worker")
        got = await su.fetch(
            """SELECT core.pad_ref('MT-', n, 4) AS ref
                 FROM unnest(ARRAY[7, 9999, 10000, 29300, 29309]::bigint[]) WITH ORDINALITY AS u(n, i)
                ORDER BY i"""
        )
    refs = [r["ref"] for r in got]
    assert refs == ["MT-0007", "MT-9999", "MT-10000", "MT-29300", "MT-29309"]
    assert len(set(refs)) == len(refs)


def test_a_persona_face_is_a_file_id_or_none() -> None:
    """23.2: `face: secretary.webp` named no file; every talk screen asked GET /files/secretary.webp (a 422)."""
    from uuid import UUID

    from hq_api.talk import data

    data.personas.cache_clear()
    for key, p in data.personas().items():
        assert p.face is None or str(UUID(p.face)) == p.face, key
    assert data._file_id("secretary.webp") is None
    assert (
        data._file_id("C31EF6FE-38B6-4F64-8B0C-A45E40489753")
        == "c31ef6fe-38b6-4f64-8b0c-a45e40489753"
    )
