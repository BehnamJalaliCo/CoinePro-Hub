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
def test_the_three_reviewed_recipes_load_and_keep_to_their_own_hosts() -> None:
    got = RC.load(recipes_dir())
    assert sorted(got) == ["chatgpt-web", "deepseek-web", "gemini-web"]
    for key, r in got.items():
        assert r.key == key and r.site in r.hosts
        for task in r.tasks.values():
            for st in task.steps:
                assert st.do != "screenshot"  # no step can take a picture of the page
                if st.do == "fill":
                    assert st.text == "{prompt}"
    assert set(got["chatgpt-web"].tasks) == {"text", "image"}
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
