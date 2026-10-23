"""Settings from the environment (non-secret; egress holds no secret of its own)."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field

Net = ipaddress.IPv4Network | ipaddress.IPv6Network


def _nets(name: str, default: str) -> tuple[Net, ...]:
    raw = os.environ.get(name, default)
    return tuple(ipaddress.ip_network(x.strip()) for x in raw.split(",") if x.strip())


def _hosts(name: str, default: str) -> frozenset[str]:
    raw = os.environ.get(name, default)
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


@dataclass(frozen=True)
class Settings:
    api_port: int = field(default_factory=lambda: int(os.environ.get("EGRESS_PORT", "8090")))
    browser_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_BROWSER_PROXY_PORT", "3128"))
    )
    gateway_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_GATEWAY_PROXY_PORT", "3129"))
    )
    # Who may call what (compose's fixed subnets: hq-egress-api, hq-browser).
    api_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_API_CLIENTS", "172.30.8.0/24")
    )
    gateway_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_GATEWAY_PROXY_CLIENTS", "172.30.8.0/24")
    )
    # The provisioner's own listener (prompt 09): hq-prov-out, CONNECT to
    # these hosts on 443 only.
    provisioner_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_PROVISIONER_PROXY_PORT", "3130"))
    )
    provisioner_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_PROVISIONER_PROXY_CLIENTS", "172.30.11.0/24")
    )
    provisioner_hosts: frozenset[str] = field(
        default_factory=lambda: _hosts("EGRESS_PROVISIONER_HOSTS", "api.hetzner.cloud")
    )
    browser_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_BROWSER_PROXY_CLIENTS", "172.30.9.0/24")
    )
    # Prompt 12 §9.1 (contract §21.13), the substitute players. The runner's
    # listener: hq-subs, CONNECT on 443 to the hosts its two CLIs need (Codex
    # signed in with ChatGPT: chatgpt.com and auth.openai.com; Gemini CLI
    # signed in with Google: Code Assist and Google's OAuth token hosts),
    # their subdomains included. Never api.openai.com (an API key's host).
    substitutes_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_SUBSTITUTES_PROXY_PORT", "3131"))
    )
    substitutes_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_SUBSTITUTES_PROXY_CLIENTS", "172.30.13.0/24")
    )
    substitutes_hosts: frozenset[str] = field(
        default_factory=lambda: _hosts(
            "EGRESS_SUBSTITUTES_HOSTS",
            "chatgpt.com,auth.openai.com,cloudcode-pa.googleapis.com,"
            "oauth2.googleapis.com,www.googleapis.com",
        )
    )
    # The profile browser (browser-web, profile substitutes-web): its API, its
    # listener (hq-browser-web; a bucket per job, the site's own hosts only)
    # and the owner's sign-in window's listener (hq-web-login; the three
    # sites' own and sign-in hosts, from the recipes).
    web_browser_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_WEB_BROWSER_URL", "http://browser-web:8096")
    )
    web_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_WEB_PROXY_PORT", "3132"))
    )
    web_proxy_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_WEB_PROXY_URL", "http://egress:3132")
    )
    web_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_WEB_PROXY_CLIENTS", "172.30.14.0/24")
    )
    login_proxy_port: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_LOGIN_PROXY_PORT", "3133"))
    )
    login_proxy_clients: tuple[Net, ...] = field(
        default_factory=lambda: _nets("EGRESS_LOGIN_PROXY_CLIENTS", "172.30.15.0/24")
    )
    recipes_dir: str = field(
        default_factory=lambda: os.environ.get("EGRESS_RECIPES_DIR", "/recipes")
    )
    # One web job's file (an image, a video of at most 10 s).
    web_file_bytes: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_WEB_FILE_BYTES", str(25 * 1024 * 1024)))
    )
    searxng_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_SEARXNG_URL", "http://searxng:8080")
    )
    browser_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_BROWSER_URL", "http://browser:8095")
    )
    # The proxy as the browser reaches it (on its own network).
    browser_proxy_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_BROWSER_PROXY_URL", "http://egress:3128")
    )
    # The hub's own names AND public addresses (hq.sh adds the host's global
    # addresses and what its domain resolves to, 7.1): /internal is never
    # reachable by any of them, nor by a name that resolves to one of them.
    hub_hosts: frozenset[str] = field(
        default_factory=lambda: _hosts("EGRESS_HUB_HOSTS", "hq.coinepro.com")
    )
    fetch_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_FETCH_TIMEOUT_S", "15"))
    )
    # One call's caps (a run's and a company's are the api's).
    max_call_bytes: int = field(
        default_factory=lambda: int(os.environ.get("EGRESS_MAX_CALL_BYTES", str(20 * 1024 * 1024)))
    )
    browse_call_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_BROWSE_CALL_S", "20"))
    )
    # Every file of one web.browse together (screenshots and downloads, 7.1):
    # they cross egress's memory as base64 (MEM_EGRESS is measured for it).
    browse_files_bytes: int = field(
        default_factory=lambda: int(
            os.environ.get("EGRESS_BROWSE_FILES_BYTES", str(16 * 1024 * 1024))
        )
    )
    # One call's whole time (every hop, a slow server, the parsing): below the
    # gateway's 25 s for a tool, so the call's entries always come back to it.
    call_deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_CALL_DEADLINE_S", "20"))
    )
    # Connectors of code (prompt 10 §2.3): LBank's keyless market API (the
    # day's closing prices); the affiliate API's host is the account's site.
    lbank_public_url: str = field(
        default_factory=lambda: os.environ.get("EGRESS_LBANK_PUBLIC_URL", "https://api.lbkex.com")
    )
    # How long a connector call may wait for its exchange's rate limit.
    connector_wait_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_CONNECTOR_WAIT_S", "8"))
    )
    # Prompt 13 §2.3 (contract §22.2, §22.7): publishing. The hub's public
    # name (compose: HQ_SITE_ADDRESS): the only host an Instagram media URL may
    # name (its one signed file URL); empty or not a name = Instagram refused.
    public_host: str = field(
        default_factory=lambda: public_host(os.environ.get("EGRESS_PUBLIC_HOST", ""))
    )
    # One publish call's whole time: a 50 MB video to Telegram, or a Graph call.
    media_deadline_s: float = field(
        default_factory=lambda: float(os.environ.get("EGRESS_MEDIA_DEADLINE_S", "120"))
    )
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "info"))


_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOSTNAME = re.compile(rf"^(?=.{{4,253}}$){_LABEL}(?:\.{_LABEL})+$")


def public_host(raw: str) -> str:
    """The hub's public host name from a Caddy site address ("hq.example.com",
    "https://hq.example.com", "hq.example.com:443"); "" for none (":80", empty)."""
    value = raw.strip().lower()
    for prefix in ("https://", "http://"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    value = value.split("/", 1)[0]
    host, _, port = value.partition(":")
    if port and port != "443":
        return ""
    return host if _HOSTNAME.match(host) else ""
