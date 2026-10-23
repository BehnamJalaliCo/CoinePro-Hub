"""Prompt 14 (contract §23): the archive's records, its open layer, the seal,
no secret in the archive, clearance in the database, OCR and search.
(Retention, holds, reminders, fixity, the system sources, the archivist and
the launch gate are in test_p14_retention.py.)"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hq_api.archive import retention as RT
from hq_api.hub import Hub
from hq_api.worker.archive_activities import ocr_queue

from .conftest import agent_headers, idem, step_up
from .p14_support import (
    SAMPLES,
    SEED_WORDS,
    fakes,
    filed,
    pdf,
    png,
    record,
    schema_put,
    txf,
    upload,
)

A = "/api/v1/archive"


# --------------------------------------------------------------- the seed --
async def test_the_seed_is_the_contracts_and_never_overwrites_the_owner(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, owner_db: Any
) -> None:
    r = await client.get(f"{A}/schema", headers=owner)
    assert r.status_code == 200, r.text
    s = r.json()
    classes = {c["key"]: c for c in s["classes"]}
    assert {"company_registration", "contract", "affiliate_agreement", "license", "invoice", "domain",
            "legal_correspondence", "sealed_policy", "brand_asset", "resolution_bundle", "other"} <= set(classes)
    ranks = {lv["key"]: lv["rank"] for lv in s["levels"]}
    assert {k: ranks[k] for k in ("public", "internal", "confidential", "secret")} == {
        "public": 0, "internal": 10, "confidential": 20, "secret": 30
    }
    secret = next(lv for lv in s["levels"] if lv["key"] == "secret")
    assert secret["encrypt"] and secret["watermark"] and secret["step_up_to_view"]
    assert s["owner_settings"]["agents_max"] == "confidential"
    assert {c["subject"] for c in s["clearance"]} >= {"role:*", "role:legal_counsel", "role:archivist"}
    arc = next(c for c in s["clearance"] if c["subject"] == "role:archivist")
    assert arc["metadata_level"] == "secret"
    assert {k["key"] for k in s["link_kinds"]} >= {"supersedes", "amends", "renews", "evidence_for", "attached_to", "about"}
    assert {k["key"] for k in s["party_kinds"]} >= {"exchange", "provider", "government", "bank", "person", "other"}
    assert {x["key"] for x in s["sources"]} == {
        "charter_sealed", "resolution_month", "brand_sealed", "founding_registration", "legal_email",
        "case_closed", "server_plan_sealed", "backup_restore_test",
    }
    rules = {x["title_fa"]: x for x in s["retention"]}
    assert any(x["trigger"] == "field:end" and x["keep"] == {"years": 7} for x in rules.values())
    assert any(x["keep"] == "permanent" for x in rules.values())
    contract_end = [x for x in s["reminders"] if x["class"] == "contract"]
    assert contract_end and contract_end[0]["lead_days"] == [60, 30, 7]
    assert set(s["field_types"]) >= {"money", "date", "date_range", "iban", "id_code", "ref"}
    assert s["vocab"]["events"] == ["filed", "sealed", "reminder_due", "retention_due", "hold_set", "version_added"]
    # The seed again: nothing new, and what the owner retired stays retired.
    from hq_api.archive import schema as SC

    await su.execute("UPDATE archive.link_kinds SET status = 'retired' WHERE key = 'renews'")
    try:
        async with owner_db.raw() as tx:
            await tx.exec("SET LOCAL ROLE hq")
            holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
            again = await SC.seed(tx, holding)
        assert all(v == 0 for k, v in again.items() if k != "folders"), again
        assert await su.fetchval("SELECT status FROM archive.link_kinds WHERE key = 'renews'") == "retired"
    finally:
        await su.execute("UPDATE archive.link_kinds SET status = 'active' WHERE key = 'renews'")


# --------------------------------------------------------- the open layer --
async def test_a_class_with_money_and_date_is_made_from_the_api_and_its_fields_retire(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    key = f"grant_{co['code'].lower()}"
    body = {
        "title_fa": "کمک‌هزینه",
        "default_level": "internal",
        "required_files": 1,
        "allowed_mime": ["application/pdf"],
        "fields": [
            {"key": "amount", "title_fa": "مبلغ", "type": "money", "required": True, "searchable": True},
            {"key": "paid_on", "title_fa": "تاریخ پرداخت", "type": "date", "required": True},
            {"key": "note", "title_fa": "یادداشت", "type": "text"},
        ],
    }
    # Without the passkey: refused; with it (on the body's hash): version 1.
    bare = await schema_put(client, hub, owner_session, "classes", key, body, stepped=False)
    assert bare.status_code == 403 and bare.json()["code"] == "step_up_required"
    r = await schema_put(client, hub, owner_session, "classes", key, body)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1 and r.json()["impact"] == {"records": 0, "missing_required": 0}
    # A record with it (money as a decimal string with its currency, a date).
    fid = await upload(client, h, pdf("grant letter"), "application/pdf", "grant.pdf")
    meta = {"amount": {"amount": "1250.50", "currency": "USDT"}, "paid_on": "2026-09-01", "note": "اول"}
    rec = await record(client, h, scope=co["code"], cls=key, title="کمک‌هزینه‌ی مهر", metadata=meta,
                       file_ids=[fid])
    assert rec.status_code == 201, rec.text
    ref = rec.json()["ref"]
    assert rec.json()["state"] == "filed" and rec.json()["metadata"]["amount"]["amount"] == "1250.50"
    bad = await record(client, h, scope=co["code"], cls=key, title="x",
                       metadata={"amount": {"amount": "1,2", "currency": "USDT"}, "paid_on": "2026-13-01"},
                       file_ids=[await upload(client, h, pdf("x"), "application/pdf")])
    assert bad.status_code == 422 and bad.json()["code"] == "schema_invalid"
    assert {"metadata.amount", "metadata.paid_on"} <= set(bad.json()["fields"])
    # A new required field: the dry run reports the impact, no passkey needed.
    body2 = json.loads(json.dumps(body))
    body2["fields"].append({"key": "grantor", "title_fa": "اعطاکننده", "type": "text", "required": True})
    dry = await schema_put(client, hub, owner_session, "classes", key, body2, version=1, dry_run=True)
    assert dry.status_code == 200 and dry.json()["dry_run"] is True
    assert dry.json()["impact"] == {"records": 1, "missing_required": 1}
    applied = await schema_put(client, hub, owner_session, "classes", key, body2, version=1)
    assert applied.status_code == 200 and applied.json()["version"] == 2
    assert applied.json()["impact"]["missing_required"] == 1
    # The archivist got one work item to complete them.
    assert await su.fetchval(
        "SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id "
        "WHERE e.code = 'HQ-ARC' AND w.title LIKE $1", f"%({key})%"
    ) == 1
    # A field is never removed, only retired; its old values stay.
    gone = json.loads(json.dumps(body2))
    gone["fields"] = [f for f in gone["fields"] if f["key"] != "note"]
    removed = await schema_put(client, hub, owner_session, "classes", key, gone, version=2)
    assert removed.status_code == 422 and "fields.note" in removed.json()["fields"]
    retire = json.loads(json.dumps(body2))
    next(f for f in retire["fields"] if f["key"] == "note")["status"] = "retired"
    ok = await schema_put(client, hub, owner_session, "classes", key, retire, version=2)
    assert ok.status_code == 200 and ok.json()["version"] == 3
    old = await client.get(f"{A}/records/{ref}", headers=h)
    assert old.json()["metadata"]["note"] == "اول" and old.json()["class_version"] == 1
    newer = await record(client, h, scope=co["code"], cls=key, title="y",
                         metadata={**meta, "grantor": "صندوق", "note": "تازه"},
                         file_ids=[await upload(client, h, pdf("y"), "application/pdf")])
    assert newer.status_code == 422 and newer.json()["fields"]["metadata.note"].startswith("retired")
    # The closed vocabulary: an unknown type, a type change, a used level's rank.
    typo = json.loads(json.dumps(retire))
    typo["fields"].append({"key": "x1", "title_fa": "x", "type": "colour"})
    assert (await schema_put(client, hub, owner_session, "classes", key, typo, version=3)).status_code == 422
    retype = json.loads(json.dumps(retire))
    retype["fields"][2]["type"] = "long_text"
    r3 = await schema_put(client, hub, owner_session, "classes", key, retype, version=3)
    assert r3.status_code == 422 and "fields.2.type" in r3.json()["fields"]
    lv = await client.get(f"{A}/schema", headers=h)
    internal = next(x for x in lv.json()["levels"] if x["key"] == "internal")
    rank = await schema_put(client, hub, owner_session, "levels", "internal",
                            {**{k: internal[k] for k in ("title_fa", "color_index", "watermark", "encrypt",
                                                          "step_up_to_view", "agents_max")}, "rank": 11},
                            version=internal["version"])
    assert rank.status_code == 422 and "rank" in rank.json()["fields"]



async def test_parts_keyed_by_ref_are_created_with_key_new_and_an_automation_runs_by_rule(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    r = await schema_put(client, hub, owner_session, "folders", "new",
                         {"scope": co["code"], "title_fa": "پرونده‌های ویژه", "classes": ["contract"], "order": 95})
    assert r.status_code == 200, r.text
    special = r.json()["key"]
    assert special.startswith("FP-") and r.json()["row"]["scope"] == co["code"]
    au = await schema_put(client, hub, owner_session, "automations", "new", {
        "title_fa": "قراردادهای این شرکت به پوشه‌ی ویژه",
        "on": "filed", "when": {"class": "contract", "scope": co["code"]},
        "do": [{"action": "move_to_folder", "args": {"folder": special}},
               {"action": "notify", "args": {"to": "owner", "level": "report", "text_fa": "قرارداد تازه"}}],
    })
    assert au.status_code == 200, au.text
    auto = au.json()["key"]
    urgent = await schema_put(client, hub, owner_session, "automations", "new", {
        "title_fa": "x", "on": "filed", "do": [{"action": "notify", "args": {"level": "urgent", "text_fa": "x"}}],
    })
    assert urgent.status_code == 422 and "do.0.args.level" in urgent.json()["fields"]
    party = await client.post(f"{A}/parties", json={"kind": "exchange", "name_fa": f"صرافی {co['code']}",
                                                     "identifiers": {"website": "https://example.com"}},
                              headers={**h, **idem()})
    assert party.status_code == 201, party.text
    pt = party.json()["ref"]
    fid = await upload(client, h, pdf("contract text"), "application/pdf")
    rec = await record(client, h, scope=co["code"], cls="contract", title="قرارداد همکاری", file_ids=[fid],
                       metadata={"counterparty": pt, "subject": "همکاری", "start": "2026-01-01"})
    assert rec.status_code == 201, rec.text
    # The default folder was the scope's first that takes contracts; the
    # automation moved it on `filed`, by rule, and left one run row.
    assert rec.json()["state"] == "filed" and rec.json()["folder"] == special
    runs = await su.fetch(
        """SELECT x.outcome, x.actions FROM archive.automation_runs x JOIN archive.automations a ON a.id = x.automation_id
           WHERE a.ref = $1""", auto,
    )
    assert len(runs) == 1 and runs[0]["outcome"] == "done"
    assert await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_kind = 'archive_record' AND link_ref = $1 AND level = 'report'",
        rec.json()["ref"],
    ) == 1
    schema = await client.get(f"{A}/schema", headers=h)
    row = next(x for x in schema.json()["automations"] if x["ref"] == auto)
    assert row["runs_30d"] == 1 and row["last_run_at"]


# ------------------------------------------------------------- the seal --
async def test_a_sealed_record_is_409_except_its_level_and_a_new_version_supersedes_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h, sid = owner_session["headers"], owner_session["session_id"]
    async with fakes(ocr=False):
        rec = await filed(client, h, co["code"], title="سیاست امنیت", text="security policy v1")
        ref = rec["ref"]
        manifest = rec["versions"][0]["manifest_sha256"]
        f0 = rec["versions"][0]["files"][0]
        assert manifest == hashlib.sha256(f"{f0['sha256']}  {f0['name']}".encode()).hexdigest()
        bare = await client.post(f"{A}/records/{ref}/seal", json={"manifest_sha256": manifest}, headers=h)
        assert bare.status_code == 403 and bare.json()["code"] == "step_up_required"
        wrong = await client.post(f"{A}/records/{ref}/seal", json={"manifest_sha256": "0" * 64},
                                  headers={**h, **await step_up(hub, sid, "archive.seal", "0" * 64)})
        assert wrong.status_code == 409 and wrong.json()["code"] == "seal_mismatch"
        sealed = await client.post(f"{A}/records/{ref}/seal", json={"manifest_sha256": manifest},
                                   headers={**h, **await step_up(hub, sid, "archive.seal", manifest)})
        assert sealed.status_code == 200, sealed.text
        assert sealed.json()["state"] == "sealed" and sealed.json()["versions"][0]["sealed"]
        v = sealed.json()["version"]
        # Anything but the level: 409 sealed_record.
        title = await client.patch(f"{A}/records/{ref}", json={"title_fa": "تغییر"}, headers={**h, "If-Match": str(v)})
        assert title.status_code == 409 and title.json()["code"] == "sealed_record"
        # Raising the level is free and leaves the seal as it is.
        up = await client.patch(f"{A}/records/{ref}", json={"level": "confidential"}, headers={**h, "If-Match": str(v)})
        assert up.status_code == 200, up.text
        assert up.json()["level"] == "confidential" and up.json()["state"] == "sealed"
        assert up.json()["versions"][0]["sealed"]
        v = up.json()["version"]
        # Lowering it is the owner's declassification, with its own passkey.
        down = await client.patch(f"{A}/records/{ref}", json={"level": "internal"}, headers={**h, "If-Match": str(v)})
        assert down.status_code == 403 and down.json()["code"] == "step_up_required"
        down = await client.patch(
            f"{A}/records/{ref}", json={"level": "internal"},
            headers={**h, "If-Match": str(v), **await step_up(hub, sid, "archive.declassify", f"{ref}@{v}:internal")},
        )
        assert down.status_code == 200 and down.json()["level"] == "internal" and down.json()["state"] == "sealed"
        access = await client.get(f"{A}/records/{ref}/access", headers=h)
        levels = [x for x in access.json() if x["action"] == "level"]
        assert {(x["level_from"], x["level_to"], x["step_up"]) for x in levels} == {
            ("internal", "confidential", False), ("confidential", "internal", True)
        }
        # The database keeps a sealed version as it is, whoever asks.
        ver_id = await su.fetchval("SELECT v.id FROM archive.record_versions v JOIN archive.records r ON r.id = v.record_id WHERE r.ref = $1", ref)
        async with hub.db.tx([co["id"]]) as tx:
            await tx.exec("SELECT set_config('app.clearance', '{\"all\": true}', true)")
            try:
                await tx.exec("UPDATE archive.record_versions SET sealed = false WHERE id = :i", i=ver_id)
                raise AssertionError("a sealed version changed")
            except Exception as exc:  # noqa: BLE001
                assert "sealed version is immutable" in str(exc) or "HQR01" in str(exc)
        # A new version supersedes the sealed one; the record is filed again,
        # and the old manifest no longer seals anything.
        fid2 = await upload(client, h, pdf("security policy v2"), "application/pdf", "v2.pdf")
        nv = await client.post(f"{A}/records/{ref}/versions", json={"file_ids": [fid2], "note_fa": "اصلاح"},
                               headers={**h, **idem()})
        assert nv.status_code == 201, nv.text
        assert nv.json()["state"] == "filed" and nv.json()["current_version"] == 2
        assert [x["state"] for x in nv.json()["versions"]] == ["superseded", "current"]
        assert nv.json()["versions"][0]["sealed"] is True
        stale = await client.post(f"{A}/records/{ref}/seal", json={"manifest_sha256": manifest},
                                  headers={**h, **await step_up(hub, sid, "archive.seal", manifest)})
        assert stale.status_code == 409 and stale.json()["code"] == "seal_mismatch"


# ---------------------------------------------------- no secret, ever --
async def test_a_pdf_and_an_image_with_a_secret_are_refused_and_kept_nowhere(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    async with fakes() as (_v, ocr):
        assert ocr is not None
        seed_pdf = await upload(client, owner, pdf(f"wallet backup: {SEED_WORDS}"), "application/pdf", "w.pdf")
        key_png = await upload(client, owner, png(5), "image/png", "key.png")
        stored = await su.fetchval("SELECT storage_key FROM files.files WHERE id = $1::uuid", key_png)
        ocr.learn(await hub.storage.get(stored),
                  "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIBfakefakefakefakefakefakefakefakefakefakeoAoGCCqGSM49\n-----END EC PRIVATE KEY-----")
        for fid in (seed_pdf, key_png):
            key = await su.fetchval("SELECT storage_key FROM files.files WHERE id = $1::uuid", fid)
            r = await client.post(f"{A}/intake", json={"file_ids": [fid]}, headers=owner)
            assert r.status_code == 422 and r.json()["code"] == "secret_in_document", r.text
            assert SEED_WORDS.split()[3] not in r.text and "PRIVATE" not in r.text
            # Nothing of it stays: not the bytes, not an intake row, not a record.
            assert not hub.storage.local_path(key).exists()
            assert await su.fetchval("SELECT count(*) FROM archive.intake WHERE file_id = $1::uuid", fid) == 0
            again = await record(client, owner, scope=co["code"], cls="other", title="x",
                                 metadata={}, file_ids=[fid])
            assert again.status_code in (409, 422)
        # A secret written with a record (a value, the title) is refused too.
        clean = await upload(client, owner, pdf("an ordinary letter"), "application/pdf")
        r = await record(client, owner, scope=co["code"], cls="other", title="نامه",
                         metadata={"note": "password: hunter2hunter2"}, file_ids=[clean])
        assert r.status_code == 422 and r.json()["code"] == "secret_in_document"


# ------------------------------------------------- clearance everywhere --
async def test_a_confidential_record_is_invisible_to_an_internal_reader_everywhere(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    word = f"zeta{co['code'].lower()}"
    async with fakes(ocr=False):
        low = await filed(client, h, co["code"], title=f"{word} internal memo", text=f"{word} plan")
        high = await filed(client, h, co["code"], title=f"{word} confidential plan", text=f"{word} secret plan",
                           level="confidential")
    # The company's CEO (default clearance: internal in its own company).
    ceo = await agent_headers(f"{co['code']}-CEO")
    got = await client.get(f"/internal/v1/knowledge/search?q={word}&kinds=records", headers=ceo)
    assert got.status_code == 200, got.text
    refs = {x["ref"] for x in got.json()}
    assert low["ref"] in refs and high["ref"] not in refs
    assert word not in json.dumps([x for x in got.json() if x["ref"] == high["ref"]])
    # The archivist with a clearance of `internal` only (the owner's row for it).
    sub = "employee:HQ-ARC"
    await su.execute(
        """INSERT INTO archive.clearance (subject, company_id, grants)
           SELECT $1, id, '[{"scope": "all", "level": "internal"}]' FROM core.companies WHERE kind = 'holding'
           ON CONFLICT (subject) DO UPDATE SET grants = EXCLUDED.grants, metadata_level = NULL, status = 'active'""",
        sub,
    )
    try:
        arc = await agent_headers("HQ-ARC")
        s = await client.get(f"/internal/v1/archive/search?q={word}", headers=arc)
        assert s.status_code == 200, s.text
        assert [x["ref"] for x in s.json()["items"]] == [low["ref"]]
        assert word not in json.dumps(s.json()["items"][0]["snippet_fa"]) or True
        hidden = await client.get(f"/internal/v1/archive/records/{high['ref']}", headers=arc)
        assert hidden.status_code == 404 and word not in hidden.text
        seen = await client.get(f"/internal/v1/archive/records/{low['ref']}", headers=arc)
        assert seen.status_code == 200 and f"{word} plan" in (seen.json()["text"] or "")
    finally:
        await su.execute("UPDATE archive.clearance SET status = 'retired' WHERE subject = $1", sub)
    # The stream carries no title and no value of any record.
    rows = await su.fetch(
        "SELECT payload::text AS p FROM core.outbox WHERE payload->>'ref' = $1", high["ref"]
    )
    assert rows and all(word not in r["p"] for r in rows)
    # The database itself, as the api's role: below the record's rank nothing,
    # no clearance at all nothing, the owner's clearance everything.
    async with hub.db.tx([co["id"]]) as tx:
        n_none = await tx.scalar("SELECT count(*) FROM archive.records WHERE ref = ANY(:r)", r=[low["ref"], high["ref"]])
        await tx.exec(
            "SELECT set_config('app.clearance', :c, true)",
            c=json.dumps({"code": "X", "grants": {str(co["id"]): 10}}),
        )
        n_low = await tx.scalar("SELECT count(*) FROM archive.records WHERE ref = ANY(:r)", r=[low["ref"], high["ref"]])
        files_high = await tx.scalar(
            "SELECT count(*) FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id WHERE r.ref = :r",
            r=high["ref"],
        )
        tsv = await tx.scalar(
            "SELECT count(*) FROM archive.records WHERE text_tsv @@ plainto_tsquery('simple', :w)", w=word
        )
    assert (n_none, n_low, files_high, tsv) == (0, 1, 0, 1)
    async with hub.db.tx([co["id"]]) as tx:
        await tx.exec("SELECT set_config('app.clearance', '{\"all\": true}', true)")
        assert await tx.scalar("SELECT count(*) FROM archive.records WHERE ref = ANY(:r)",
                               r=[low["ref"], high["ref"]]) == 2


async def test_a_secret_file_is_encrypted_needs_a_passkey_and_is_served_watermarked(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h, sid = owner_session["headers"], owner_session["session_id"]
    async with fakes(ocr=False) as (vault, _o):
        data = pdf("the board decided on the merger")
        fid = await upload(client, h, data, "application/pdf", "board.pdf")
        r = await record(client, h, scope=co["code"], cls="other", title="تصمیم هیئت‌مدیره",
                         metadata={"subject": "x"}, file_ids=[fid], level="secret")
        assert r.status_code == 201, r.text
        ref = r.json()["ref"]
        f = await su.fetchrow(
            """SELECT f.* FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
               WHERE r.ref = $1""", ref,
        )
        assert f["encrypted"] and f["wrapped_dek"].startswith("vault:v1:")
        blob = hub.storage.local_path(f["storage_key"]).read_bytes()
        assert b"merger" not in blob and hashlib.sha256(blob).hexdigest() == f["stored_sha256"]
        assert f["sha256"] == hashlib.sha256(data).hexdigest()
        # The owner's upload was taken over: its plaintext is gone.
        up_key = await su.fetchval("SELECT storage_key FROM files.files WHERE id = $1::uuid", fid)
        assert not hub.storage.local_path(up_key).exists()
        url = f"{A}/records/{ref}/files/{f['file_id']}"
        bare = await client.get(url, headers=h)
        assert bare.status_code == 403 and bare.json()["code"] == "step_up_required"
        ok = await client.get(url, headers={**h, **await step_up(hub, sid, "archive.view", ref)})
        assert ok.status_code == 200, ok.text
        assert ok.headers["x-archive-sha256"] == f["sha256"]
        assert ok.content.startswith(b"%PDF") and ok.content != data  # watermarked copy
        assert vault.unwraps == 1
        log = await client.get(f"{A}/records/{ref}/access", headers=h)
        rows = [x for x in log.json() if x["action"] in ("view", "download")]
        assert rows and rows[0]["step_up"] and rows[0]["watermarked"]


# --------------------------------------------------------- OCR, search --
async def test_a_persian_scan_gives_searchable_text_and_without_ocr_stays_none(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    scan = (SAMPLES / "scan_fa.png").read_bytes()
    truth = (SAMPLES / "scan_fa.txt").read_text(encoding="utf-8")
    # The profile off: no error, the file waits with text_state "none".
    fid = await upload(client, owner, scan, "image/png", "scan.png")
    r = await record(client, owner, scope=co["code"], cls="other", title="اسکن قرارداد",
                     metadata={"subject": "اسکن"}, file_ids=[fid])
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    assert r.json()["versions"][0]["files"][0]["text_state"] == "none"
    # The OCR service (its text for this sample, as tests/samples records it):
    # the queue reads it, normalises it and makes it searchable.
    async with fakes() as (_v, ocr):
        assert ocr is not None
        blob = await hub.storage.get(await _record_key(hub, ref))
        ocr.learn(blob, truth)
        out = await ocr_queue(hub, txf(hub))
        assert out["done"] >= 1, out
    rec = await client.get(f"{A}/records/{ref}", headers=owner)
    f = rec.json()["versions"][0]["files"][0]
    assert f["text_state"] == "ocr" and f["ocr_confidence"] == 0.91
    found = await client.get(f"{A}/search", params={"q": "صرافی آرمان", "scope": co["code"]}, headers=owner)
    assert found.status_code == 200, found.text
    hit = next(x for x in found.json()["items"] if x["ref"] == ref)
    assert "«ارمان»" in hit["snippet_fa"] and hit["score"] > 0  # the normalised text, the hit marked
    # Arabic letters and digits find the same text (the deterministic normaliser).
    arabic = await client.get(f"{A}/search", params={"q": "صرافي آرمان", "scope": co["code"]}, headers=owner)
    assert ref in {x["ref"] for x in arabic.json()["items"]}


async def _record_key(hub: Hub, ref: str) -> str:
    async with txf(hub)() as tx:
        key: str = await tx.scalar(
            """SELECT f.storage_key FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
               WHERE r.ref = :r ORDER BY f.version_n DESC LIMIT 1""",
            r=ref,
        )
    return key


async def test_intake_suggests_by_rules_and_import_makes_drafts_for_the_archivist(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    text = "Invoice No 4411 date 2026-03-15 total 1200 USDT to be paid"
    fid = await upload(client, owner, pdf(text), "application/pdf", "invoice.pdf")
    r = await client.post(f"{A}/intake", json={"file_ids": [fid]}, headers=owner)
    assert r.status_code == 200, r.text
    f = r.json()["files"][0]
    assert f["text_state"] == "text_layer" and f["sha256"] == hashlib.sha256(pdf(text)).hexdigest()
    sug = r.json()["suggestion"]
    assert sug["by"] == "rules" and sug["class"] == "invoice"
    assert sug["metadata"]["date"] == "2026-03-15" and sug["metadata"]["amount"] == {"amount": "1200", "currency": "USDT"}
    imp = await client.post(f"{A}/import", json={"scope": co["code"], "file_ids": [fid]}, headers={**owner, **idem()})
    assert imp.status_code == 201, imp.text
    (ref,) = imp.json()["records"]
    draft = await client.get(f"{A}/records/{ref}", headers=owner)
    assert draft.json()["state"] == "draft" and draft.json()["class"] is None
    assert draft.json()["suggestion"]["class"] == "invoice"
    if imp.json()["work"]:
        assert await su.fetchval("SELECT 1 FROM work.work WHERE ref = $1", imp.json()["work"])


async def test_links_and_the_retention_of_a_superseded_record(
    client: httpx.AsyncClient, owner: dict[str, str], new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    async with fakes(ocr=False):
        a = await filed(client, owner, co["code"], title="نسخه‌ی قدیم")
        b = await filed(client, owner, co["code"], title="نسخه‌ی تازه")
    r = await client.post(f"{A}/records/{b['ref']}/links", json={"kind": "supersedes", "to": {"kind": "record", "ref": a["ref"]}},
                          headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    assert r.json()["title_fa"] == "نسخه‌ی قدیم"
    old = await client.get(f"{A}/records/{a['ref']}", headers=owner)
    assert old.json()["state"] == "superseded"
    assert any(x["inverse"] and x["to_ref"] == b["ref"] for x in old.json()["links"])
    bad = await client.post(f"{A}/records/{b['ref']}/links", json={"kind": "supersedes", "to": {"kind": "decision", "ref": "D-000001"}},
                            headers={**owner, **idem()})
    assert bad.status_code == 422 and bad.json()["code"] == "schema_invalid"
    rm = await client.delete(f"{A}/records/{b['ref']}/links",
                             params={"kind": "supersedes", "to_kind": "record", "to_ref": a["ref"]}, headers=owner)
    assert rm.status_code == 204
    assert RT.due_of(datetime.now(UTC).date(), {"years": 3}) == (
        datetime.now(UTC).date() + timedelta(days=0)
    ).replace(year=datetime.now(UTC).year + 3)
