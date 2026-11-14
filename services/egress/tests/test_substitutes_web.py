"""The substitute players at egress (prompt 12 §9.1, contract §21.13): the
reviewed recipes, the web job and logout endpoints (against a fake profile
browser), web.browse with a signed-in profile, and the three new listeners
(the runner's CLI hosts, the profile browser's per-job hosts, the owner's
sign-in window)."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from hq_egress import recipes as RC
from hq_egress.accounts import Account
from hq_egress.app import State, build_app
from hq_egress.config import Settings
from hq_egress.guard import Guard
from hq_egress.proxy import Buckets, Proxy, covered

LOCAL = ipaddress.ip_network("127.0.0.1/32")
RECIPES = Path(os.environ.get("HQ_EGRESS_RECIPES", "/recipes"))
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
KEY = "sk-ant-" + "api03-" + "C" * 80


def recipes_dir() -> Path:
    if not RECIPES.is_dir():
        pytest.skip("the recipes are mounted by test-env.sh (HQ_EGRESS_RECIPES)")
    return RECIPES


# ---------------------------------------------------------------- recipes --
def test_the_reviewed_recipes_load_and_keep_to_their_own_hosts() -> None:
    got = RC.load(recipes_dir())
    assert sorted(got) == [
        "aistudio-web", "chatgpt-web", "deepseek-web", "gemini-web", "pinterest-web",
    ]  # fmt: skip
    for key, r in got.items():
        assert r.key == key and r.site in r.hosts
        for task in r.tasks.values():
            for st in task.steps:
                assert st.do != "screenshot"  # no step can take a picture of the page
                if st.do == "fill":
                    # ⟨2026-11-13⟩ AI Studio's voice library is searched by the job's voice
                    assert st.text in ("{prompt}", "{style}", "{voice}")
    assert set(got["chatgpt-web"].tasks) == {"text", "image", "cover"}
    assert set(got["gemini-web"].tasks) == {"text", "image", "video"}
    assert set(got["deepseek-web"].tasks) == {"text"}
    assert "temporary-chat=true" in got["chatgpt-web"].start_url
    # DeepSeek: deep thinking and web search, always on, nothing else.
    ds = got["deepseek-web"]
    assert ds.features == ["deep_thinking", "web_search"]
    toggles = [str(s.selector) for s in ds.tasks["text"].steps if s.do == "click_unless"]
    assert len(toggles) == 2
    assert any("DeepThink" in t for t in toggles) and any("Search" in t for t in toggles)
    # image <= 3 minutes, video <= 10 minutes
    assert got["chatgpt-web"].tasks["image"].timeout_s <= 180
    # ⟨2026-11-14⟩ ChatGPT's page is in Persian: its made image is found by its source, not by
    # an English alt, and taken only once the answer is finished (an image chat, never temporary)
    for task in ("image", "cover"):
        steps = got["chatgpt-web"].tasks[task].steps
        assert steps[0].do == "goto" and "temporary" not in str(steps[0].url)
        last = steps[-1]
        assert last.do == "download_image" and "estuary" in str(last.selector)
        assert any(s.do == "wait_gone" and not s.optional for s in steps)
    assert got["gemini-web"].tasks["video"].timeout_s <= 600


def _recipe(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "key": "chatgpt-web",
        "version": "2026-10-22.1",
        "site": "chat.test",
        "start_url": "https://chat.test/",
        "hosts": ["chat.test"],
        "expired": {"url_contains": ["/login"]},
        "tasks": {"text": {"timeout_s": 60, "steps": [{"do": "goto", "url": "{start_url}"},
                                                      {"do": "read", "selector": "p"}]}},
    }  # fmt: skip
    base.update(over)
    return base


@pytest.mark.parametrize(
    "bad",
    [
        {"start_url": "https://elsewhere.test/"},
        {"hosts": ["other.test"]},
        {"hosts": ["chat.test", "10.0.0.1"]},
        {
            "tasks": {
                "text": {"timeout_s": 60, "steps": [{"do": "fill", "selector": "x", "text": "hi"}]}
            }
        },
        {"tasks": {"image": {"timeout_s": 900, "steps": [{"do": "pause"}]}}},
        {"tasks": {"text": {"timeout_s": 60, "steps": [{"do": "screenshot"}]}}},
        {"tasks": {"text": {"timeout_s": 60, "steps": [{"do": "click"}]}}},
        {"version": "v1"},
        {"extra": 1},
    ],
)
def test_a_recipe_that_breaks_a_rule_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RC.Recipe.model_validate(_recipe(**bad))


def test_a_recipe_file_must_be_named_for_its_key(tmp_path: Path) -> None:
    import yaml

    (tmp_path / "gemini-web.yaml").write_text(yaml.safe_dump(_recipe()))
    with pytest.raises(ValueError, match="its key"):
        RC.load(tmp_path)
    assert RC.load(tmp_path / "none") == {}


def test_a_job_gets_only_its_tasks_steps() -> None:
    r = RC.Recipe.model_validate(_recipe())
    job = r.for_job("text")
    assert job["hosts"] == ["chat.test"] and job["task"] == "text"
    assert job["steps"][0] == {"do": "goto", "url": "{start_url}", "optional": False}


# ------------------------------------------------------- the web endpoint --
class FakeWeb:
    """The profile browser (browser-web), as egress sees it."""

    def __init__(self) -> None:
        self.answer: Any = {"ok": True, "text_md": "answer", "file": None}
        self.sent: list[dict[str, Any]] = []
        self.down = False
        self.hold: asyncio.Event | None = None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("no browser-web")
        body = json.loads(request.content)
        self.sent.append({"path": request.url.path, **body})
        if self.hold is not None:
            await self.hold.wait()
        if request.url.path == "/v1/logout":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json=self.answer)


@pytest.fixture
async def web(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, FakeWeb, State]]:
    import yaml

    (tmp_path / "chatgpt-web.yaml").write_text(
        yaml.safe_dump(
            _recipe(
                tasks={
                    "text": {
                        "timeout_s": 60,
                        "steps": [
                            {"do": "goto", "url": "{start_url}"},
                            {"do": "read", "selector": "p"},
                        ],
                    },
                    "image": {
                        "timeout_s": 120,
                        "steps": [
                            {"do": "goto", "url": "{start_url}"},
                            {"do": "download_image", "selector": "img"},
                        ],
                    },
                }
            )
        )
    )
    fake = FakeWeb()
    settings = Settings(api_clients=(LOCAL,), recipes_dir=str(tmp_path))

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    state = State(
        settings,
        Guard(hub_hosts=frozenset({"hq.coinepro.com"}), resolver=resolve),
        Buckets(),
        internal=httpx.AsyncClient(transport=httpx.MockTransport(fake.handle)),
    )
    transport = httpx.ASGITransport(app=build_app(state), client=("127.0.0.1", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://egress") as c:
        yield c, fake, state


async def test_a_changed_recipe_is_read_at_the_next_job(web: Any) -> None:
    """⟨2026-11-14⟩ chatgpt-web 2026-11-13.1 never ran: egress read the recipes only at its
    start. A changed file is read at the next job; a broken one keeps the last good set."""
    import os

    import yaml

    c, _fake, state = web
    path = Path(state.settings.recipes_dir) / "chatgpt-web.yaml"
    assert state.recipes["chatgpt-web"].version == "2026-10-22.1"
    data = yaml.safe_load(path.read_text())
    data["version"] = "2026-11-14.1"
    path.write_text(yaml.safe_dump(data))
    os.utime(path, ns=(1, 1))  # (the same second as the first write: the stamp still differs)
    r = (await c.post("/v1/substitutes/web", json={"account": "chatgpt-web", "task": "text",
                                                   "prompt": "q", "timeout_s": 300})).json()  # fmt: skip
    assert r["ok"] is True and r["recipe_version"] == "2026-11-14.1"
    path.write_text("key: chatgpt-web\nversion: [broken\n")
    assert state.recipes["chatgpt-web"].version == "2026-11-14.1"


async def test_a_text_job_runs_its_recipe_in_the_profile_browser(web: Any) -> None:
    c, fake, state = web
    r = (await c.post("/v1/substitutes/web", json={"account": "chatgpt-web", "task": "text",
                                                   "prompt": f"q {KEY}", "timeout_s": 300})).json()  # fmt: skip
    assert r == {"ok": True, "text_md": "answer", "file": None, "recipe_version": "2026-10-22.1"}
    sent = fake.sent[-1]
    assert sent["path"] == "/v1/job" and sent["account"] == "chatgpt-web"
    assert sent["recipe"]["task"] == "text" and sent["recipe"]["hosts"] == ["chat.test"]
    assert KEY not in sent["prompt"]  # masked again here, whatever came
    assert sent["timeout_s"] == 60  # the recipe's own cap below the asked 300
    assert sent["proxy"]["server"] == "http://egress:3132"
    # the job's proxy login was a bucket for the site's own hosts only, gone after
    assert state.buckets.get(sent["proxy"]["username"]) is None


async def test_an_image_comes_back_as_the_original_typed_by_content(web: Any) -> None:
    c, fake, _ = web
    fake.answer = {"ok": True, "file": {"name": "x.jpg", "b64": base64.b64encode(PNG).decode()}}
    r = (await c.post("/v1/substitutes/web", json={"account": "chatgpt-web", "task": "image",
                                                   "prompt": "a calm sea, no text"})).json()  # fmt: skip
    assert r["ok"] is True and r["file"]["mime"] == "image/png"  # by content, not by name
    assert base64.b64decode(r["file"]["b64"]) == PNG
    fake.answer = {
        "ok": True,
        "file": {"name": "x.png", "b64": base64.b64encode(b"<html>").decode()},
    }
    r = (await c.post("/v1/substitutes/web", json={"account": "chatgpt-web", "task": "image",
                                                   "prompt": "p"})).json()  # fmt: skip
    assert (r["ok"], r["error"]) == (False, "recipe_failed")


async def test_expired_failed_and_off_come_back_as_they_are(web: Any) -> None:
    c, fake, _ = web
    body = {"account": "chatgpt-web", "task": "text", "prompt": "p"}
    fake.answer = {"ok": False, "error": "expired", "detail": "login page", "step": "0:goto"}
    r = (await c.post("/v1/substitutes/web", json=body)).json()
    assert (r["ok"], r["error"], r["step"]) == (False, "expired", "0:goto")
    fake.answer = {
        "ok": False,
        "error": "recipe_failed",
        "detail": "step 3 failed",
        "step": "3:click",
    }
    r = (await c.post("/v1/substitutes/web", json=body)).json()
    assert (r["error"], r["step"], r["recipe_version"]) == (
        "recipe_failed",
        "3:click",
        "2026-10-22.1",
    )
    fake.answer = {"ok": False, "error": "something-new"}
    assert (await c.post("/v1/substitutes/web", json=body)).json()["error"] == "recipe_failed"
    fake.down = True
    r = (await c.post("/v1/substitutes/web", json=body)).json()
    assert (r["ok"], r["error"]) == (False, "off")
    r = (await c.post("/v1/substitutes/web", json={**body, "task": "video"})).json()
    assert r["error"] == "recipe_failed"  # the recipe has no video task
    r = (await c.post("/v1/substitutes/web", json={**body, "account": "gemini-web"})).json()
    assert r["error"] == "off"  # no recipe mounted for it here
    bad = await c.post("/v1/substitutes/web", json={**body, "account": "evil-web"})
    assert bad.status_code == 422


async def test_files_never_go_to_a_task_that_cannot_attach_them(web: Any) -> None:
    c, fake, _ = web
    body = {"account": "chatgpt-web", "task": "image", "prompt": "Animate the attached image",
            "files": [{"name": "a.png", "b64": base64.b64encode(PNG).decode()}]}  # fmt: skip
    r = (await c.post("/v1/substitutes/web", json=body)).json()
    assert (r["ok"], r["error"], r["step"]) == (False, "unsupported", "attach")
    assert fake.sent == []  # the job never ran without its files


async def test_a_long_question_is_taken_up_to_the_hubs_own_cap(web: Any) -> None:
    from hq_egress import substitutes_web as SW

    c, fake, _ = web
    long = "س" * 60_000
    r = (await c.post("/v1/substitutes/web", json={"account": "chatgpt-web", "task": "text",
                                                   "prompt": long})).json()  # fmt: skip
    assert r["ok"] is True and len(fake.sent[-1]["prompt"]) == 60_000
    too_long = await c.post("/v1/substitutes/web", json={"account": "chatgpt-web", "task": "text",
                                                         "prompt": "x" * (SW.PROMPT_CHARS + 1)})  # fmt: skip
    assert too_long.status_code == 422


async def test_one_job_per_account_at_a_time(web: Any) -> None:
    c, fake, _ = web
    fake.hold = asyncio.Event()
    body = {"account": "chatgpt-web", "task": "text", "prompt": "p"}
    first = asyncio.create_task(c.post("/v1/substitutes/web", json=body))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if fake.sent:
            break
    second = (await c.post("/v1/substitutes/web", json=body)).json()
    assert (second["ok"], second["error"]) == (False, "busy")
    fake.hold.set()
    assert (await first).json()["ok"] is True


async def test_logout_wipes_the_profile_or_says_off(web: Any) -> None:
    c, fake, _ = web
    r = (await c.post("/v1/substitutes/web/logout", json={"account": "chatgpt-web"})).json()
    assert r == {"ok": True}
    assert fake.sent[-1] == {"path": "/v1/logout", "account": "chatgpt-web"}
    fake.down = True
    r = (await c.post("/v1/substitutes/web/logout", json={"account": "chatgpt-web"})).json()
    assert r == {"ok": False, "error": "off"}


# ------------------------------------------- web.browse with a profile --
def _ctx() -> dict[str, Any]:
    return {"company": "HQ", "actor": "HQ-SRE", "run_id": "r1", "cls": "A0", "max_bytes": 100_000}


PROFILE = {"key": "chatgpt-web", "site": "chatgpt.com", "browse": {"kind": "profile"}}


def test_a_profile_account_carries_no_secret() -> None:
    a = Account.model_validate(PROFILE)
    assert a.is_profile and a.secret is None and a.secrets() == []
    assert a.headers_for("chatgpt.com", {}) == {}
    with pytest.raises(ValidationError):
        Account.model_validate({**PROFILE, "secret": "x" * 10})
    with pytest.raises(ValidationError):
        Account.model_validate({**PROFILE, "browse": {"kind": "profile", "login_url": "https://x"}})
    with pytest.raises(ValidationError):
        Account.model_validate({"key": "k1", "site": "a.test"})  # any other needs its secret


async def test_web_browse_with_a_profile_stays_on_its_sites_own_hosts(web: Any) -> None:
    c, fake, _ = web
    fake.answer = {"steps": [{"i": 0, "do": "goto", "ok": True}], "final_url": "https://chat.test/",
                   "files": [], "blocked": None}  # fmt: skip
    body = {
        "ctx": _ctx(),
        "account": PROFILE,
        "steps": [{"do": "goto", "url": "https://chat.test/c"}],
    }
    r = (await c.post("/v1/browse", json=body)).json()
    assert r["outcome"] == "ok", r
    sent = fake.sent[-1]
    assert sent["path"] == "/v1/run" and sent["profile"] == "chatgpt-web"
    assert (
        sent["allowed_hosts"] == ["chat.test"] and sent["proxy"]["server"] == "http://egress:3132"
    )
    for url in ("https://gemini.google.com/app", "http://chat.test/", "https://evil.test/"):
        r = (
            await c.post("/v1/browse", json={**body, "steps": [{"do": "goto", "url": url}]})
        ).json()
        assert (r["outcome"], r["code"]) == ("blocked", "host_not_allowed"), url
    other = {**PROFILE, "key": "deepseek-web"}  # no recipe here: refused
    r = (await c.post("/v1/browse", json={**body, "account": other})).json()
    assert (r["outcome"], r["code"]) == ("blocked", "policy_denied")
    fake.down = True
    r = (await c.post("/v1/browse", json=body)).json()
    assert (r["outcome"], r["code"]) == ("error", "browser_unavailable")


# -------------------------------------------------------- the listeners --
class Up:
    def __init__(self) -> None:
        self.server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            await writer.drain()
            writer.close()

        self.server = await asyncio.start_server(handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]


async def _raw(port: int, data: bytes) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(data)
    await writer.drain()
    out = await asyncio.wait_for(reader.read(65536), timeout=5)
    writer.close()
    return out


def _guard(up: Up, hosts: tuple[str, ...]) -> Guard:
    async def resolve(host: str, port: int) -> list[str]:
        if host.endswith(".local-only"):
            return ["10.0.0.9"]
        return ["127.0.0.1"]

    return Guard(
        hub_hosts=frozenset({"hq.coinepro.com"}),
        resolver=resolve,
        allow=(LOCAL,),
        extra_ports={h: frozenset({up.port}) for h in hosts},
    )


async def test_the_runners_listener_reaches_only_its_clis_hosts() -> None:
    up = Up()
    await up.start()
    hosts = ("chatgpt.com", "ab.chatgpt.com", "api.openai.com", "oauth2.googleapis.com")
    p = Proxy(_guard(up, hosts), Buckets(), mode="substitutes", clients=(LOCAL,),
              allowed_hosts=Settings().substitutes_hosts, allowed_ports=(up.port,))  # fmt: skip
    server = await p.serve("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    for ok in ("chatgpt.com", "ab.chatgpt.com", "oauth2.googleapis.com"):
        out = await _raw(port, f"CONNECT {ok}:{up.port} HTTP/1.1\r\n\r\n".encode())
        assert out.startswith(b"HTTP/1.1 200"), ok
    # an API key's host, the internet at large, a neighbour, plain HTTP: never
    for target in (f"api.openai.com:{up.port}", "example.com:443", "10.10.1.1:443"):
        out = await _raw(port, f"CONNECT {target} HTTP/1.1\r\n\r\n".encode())
        assert out.startswith(b"HTTP/1.1 403") and b"host_not_allowed" in out, target
    out = await _raw(port, b"GET http://chatgpt.com/ HTTP/1.1\r\nHost: chatgpt.com\r\n\r\n")
    assert b"connect_only" in out
    server.close()
    assert up.server is not None
    up.server.close()


async def test_the_profile_listener_holds_a_job_to_its_sites_hosts() -> None:
    up = Up()
    await up.start()
    buckets = Buckets()
    hosts = ("chatgpt.com", "cdn.oaistatic.com", "gemini.google.com")
    p = Proxy(_guard(up, hosts), buckets, mode="profile", clients=(LOCAL,))
    server = await p.serve("127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    key, secret = buckets.open("substitute.web", "A2", 1_000_000,
                               hosts=frozenset({"chatgpt.com", "oaistatic.com"}))  # fmt: skip
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    head = f"Proxy-Authorization: Basic {auth}\r\n"
    out = await _raw(port, f"CONNECT cdn.oaistatic.com:{up.port} HTTP/1.1\r\n{head}\r\n".encode())
    assert out.startswith(b"HTTP/1.1 200")
    out = await _raw(port, f"CONNECT gemini.google.com:{up.port} HTTP/1.1\r\n{head}\r\n".encode())
    assert out.startswith(b"HTTP/1.1 403") and b"host_not_allowed" in out
    out = await _raw(port, f"CONNECT chatgpt.com:{up.port} HTTP/1.1\r\n\r\n".encode())
    assert out.startswith(b"HTTP/1.1 407")  # no job's credential, no way out
    (blocked,) = [e for e in buckets.drain(key) if e.blocked_reason]
    assert (blocked.host, blocked.blocked_reason) == ("gemini.google.com", "host_not_allowed")
    server.close()
    assert up.server is not None
    up.server.close()


def test_the_sign_in_window_reaches_the_recipes_hosts_with_subdomains() -> None:
    got = RC.load(recipes_dir())
    hosts = frozenset().union(*(r.sign_in_hosts() for r in got.values()))
    assert covered("auth.openai.com", hosts) and covered("accounts.google.com", hosts)
    assert not covered("example.com", hosts) and not covered("evilchatgpt.com", hosts)


def test_a_recipe_failure_carries_one_screenshot_and_nothing_else_does() -> None:
    """⟨1.10⟩ §28.4: the page as the failed step left it (a JPEG or PNG ≤ 2 MB,
    checked by content), only with recipe_failed; `reload` reaches the job."""
    import base64
    import json as _json

    from hq_egress import substitutes_web as SW

    jpeg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()
    got = {"ok": False, "error": "recipe_failed", "detail": "no box", "step": "2:fill",
           "screenshot": {"mime": "image/jpeg", "b64": jpeg}}  # fmt: skip
    body = _json.loads(SW._job_answer(got, "3", 1000).body)
    assert body["screenshot"]["mime"] == "image/jpeg" and body["step"] == "2:fill"
    timeout = _json.loads(SW._job_answer({**got, "error": "timeout"}, "3", 1000).body)
    assert "screenshot" not in timeout
    fake = {
        **got,
        "screenshot": {"mime": "image/jpeg", "b64": base64.b64encode(b"<html>").decode()},
    }
    assert "screenshot" not in _json.loads(SW._job_answer(fake, "3", 1000).body)
    assert SW.WebIn(account="gemini-web", task="text", prompt="x", reload=True).reload is True


def test_every_gemini_label_selector_takes_both_languages() -> None:
    """Audit 2026-11-11: the gemini-web profile is fa-IR, yet the video task
    waited for the English-only «Download video» label, so every video job
    failed at its wait step after the quota was spent. Each aria-label
    selector in every Gemini task names the English and the Persian label."""
    tasks = RC.load(recipes_dir())["gemini-web"].tasks
    labelled = 0
    for name, task in tasks.items():
        for s in task.steps:
            sel = str(s.selector or "")
            if "aria-label" not in sel:
                continue
            labelled += 1
            labels = [p for p in sel.split(",") if "aria-label" in p]
            assert any(any("؀" <= ch <= "ۿ" for ch in p) for p in labels), (name, sel)
            assert any(p.isascii() for p in labels), (name, sel)
    video = [s for s in tasks["video"].steps if s.do in ("wait", "download")]
    assert any("دانلود" in str(s.selector) for s in video if s.do == "download")
    assert labelled >= 4


def test_chatgpts_text_task_stands_on_the_pages_structure_not_on_one_language() -> None:
    """⟨20.1⟩ GPT's text runs on chatgpt-web now (the lesson of 19.3: the page
    is fa-IR): the prompt is sent with Enter (no label), every label kept sits
    next to a structural selector and in both languages, and the answer is read
    by structure first, by its Persian or English heading only after."""
    steps = RC.load(recipes_dir())["chatgpt-web"].tasks["text"].steps
    dos = [s.do for s in steps]
    assert "press" in dos and dos.index("press") < dos.index("read")
    for s in steps:
        sel = str(s.selector or "")
        if s.do == "click":
            assert "aria-label" not in sel and "has-text" not in sel, sel  # no label to click
        if "aria-label" in sel:
            assert "data-testid=" in sel, sel  # a label only beside a testid
            labels = [p for p in sel.split(",") if "aria-label" in p]
            assert any(any("؀" <= ch <= "ۿ" for ch in p) for p in labels), sel
            assert any(p.isascii() for p in labels), sel
    read = steps[-1]
    assert (
        read.do == "read" and "xpath" not in str(read.selector) and "markdown" in str(read.selector)
    )
    assert read.alt and "ChatGPT گفت:" in read.alt[0] and "ChatGPT said:" in read.alt[0]


def test_alt_is_for_read_only() -> None:
    with pytest.raises(ValidationError):
        RC.RStep.model_validate({"do": "click", "selector": "a", "alt": ["b"]})
    with pytest.raises(ValidationError):
        RC.RStep.model_validate({"do": "read", "selector": "a", "alt": [""]})
    s = RC.RStep.model_validate({"do": "read", "selector": "a", "alt": ["b"]})
    assert s.model_dump(exclude_none=True)["alt"] == ["b"]
    assert "alt" not in RC.RStep.model_validate({"do": "read", "selector": "a"}).model_dump(
        exclude_none=True
    )


# ----------------------------------------------- prompt 22: production lines --
def test_the_lines_recipes_are_read_only_or_type_only_what_the_job_gives() -> None:
    got = RC.load(recipes_dir())
    ai, pin = got["aistudio-web"], got["pinterest-web"]
    assert set(ai.tasks) == {"tts"} and set(pin.tasks) == {"search"}
    assert ai.tasks["tts"].timeout_s <= RC.TASK_CAP_S["tts"]
    steps = ai.tasks["tts"].steps
    # ⟨2026-11-13⟩ the 2026-11 page: the voice searched by name and its card clicked
    assert any(s.do == "fill" and s.text == "{voice}" for s in steps)
    assert any(s.do == "click" and "{voice}" in (s.selector or "") for s in steps)
    assert steps[-1].do == "download_media" and steps[-1].selector == "audio"
    assert any(s.do == "fill" and s.text == "{style}" for s in steps)
    # Pinterest is read only: it searches and collects, it never clicks a pin or a button
    assert {s.do for s in pin.tasks["search"].steps} <= {
        "goto", "wait", "fill", "press", "pause", "collect",
    }  # fmt: skip
    assert pin.tasks["search"].steps[-1].do == "collect"
    # the cover task attaches the folder's files and brings an image back
    cover = got["chatgpt-web"].tasks["cover"].steps
    assert any(s.do == "attach" for s in cover) and cover[-1].do == "download_image"
    for r in (ai, pin):
        assert r.site in r.hosts and not any(h[0].isdigit() for h in r.hosts)


@pytest.mark.parametrize(
    "step",
    [
        {"do": "select", "selector": "x", "text": "Puck"},
        {"do": "select", "selector": "x"},
        {"do": "fill", "selector": "x", "text": "{secret}"},
        {"do": "attach"},
        {"do": "collect"},
    ],
)
def test_the_new_steps_keep_their_rules(step: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RC.RStep.model_validate(step)
    assert (
        RC.RStep.model_validate({"do": "select", "selector": "x", "text": "{voice}"}).do == "select"
    )


def test_a_job_carries_the_voice_the_style_the_limit_and_the_files() -> None:
    from hq_egress import substitutes_web as SW

    a = SW.WebIn(
        account="aistudio-web", task="tts", prompt="سلام", voice="Puck", style="calm", limit=5,
        files=[SW.JobFile(name="a.png", b64="AAAA")],
    )  # fmt: skip
    assert a.voice == "Puck" and a.limit == 5 and a.files[0].name == "a.png"
    with pytest.raises(ValidationError):
        SW.WebIn(account="aistudio-web", task="tts", prompt="x", limit=99)
    with pytest.raises(ValidationError):
        SW.WebIn(account="nowhere-web", task="tts", prompt="x")  # type: ignore[arg-type]


def test_an_audio_download_is_typed_by_content() -> None:
    from hq_egress import substitutes_web as SW

    assert SW.sniff(b"RIFF\x24\x00\x00\x00WAVEfmt ") == "audio/wav"
    assert SW.sniff(b"ID3\x04\x00\x00\x00\x00\x00\x00abc") == "audio/mpeg"
    assert SW.sniff(b"OggS\x00\x02" + b"\x00" * 10) == "audio/ogg"
    assert SW.sniff(b"<html>not audio</html>") is None


def test_a_selector_names_the_jobs_voice_and_style_quoted() -> None:
    """⟨2026-11-13⟩ AI Studio's 2026-11 page: a speaker card and a style preset picked by name."""
    pytest.importorskip("playwright")  # browser_web needs it (services/scripts/browser-test.sh)
    from hq_egress import browser_web as BW
    from hq_egress.browser_web import JobIn, Proxy

    def job(voice: str | None, style: str | None) -> JobIn:
        return JobIn(account="aistudio-web", recipe={}, prompt="x", timeout_s=10,
                     proxy=Proxy(server="http://p:1"), voice=voice, style=style)  # fmt: skip

    card = {"do": "click", "selector": "button[aria-label='{voice}']"}
    assert BW._selector(card, job("Cruz", None)) == "button[aria-label='Cruz']"
    preset = {"do": "click", "selector": "x:has-text('{style}')", "optional": True}
    assert BW._selector(preset, job("Cruz", "it's")) == "x:has-text('it\\'s')"
    with pytest.raises(BW.StepFailed):
        BW._selector(card, job("Cruz'] , *[x", None))  # not a plain name
    with pytest.raises(BW.StepFailed):
        BW._selector(preset, job("Cruz", ""))  # no style: the optional step is skipped
    assert BW._selector({"do": "click", "selector": "#run"}, job(None, None)) == "#run"
