"""Prompt 14.1 §1: the owner's sign-in window is the image's own Chromium,
started directly (no Playwright, no CDP, no automation flag), so
navigator.webdriver is false and Google lets the owner sign in; the profile
jobs hide automation too (test_browser_web.py, where Playwright is);
Google's sign-in hosts are in every recipe."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hq_egress import recipes as Rc
from hq_egress.hosts import covered

SCRIPT = Path(__file__).parents[1] / "web-login.sh"
RECIPES = Path(os.environ.get("HQ_EGRESS_RECIPES", "/recipes"))
LOGIN_PAGES = {  # browser_web.LOGIN_PAGES (that module needs Playwright)
    "chatgpt-web": "https://chatgpt.com/",
    "gemini-web": "https://gemini.google.com/app",
    "deepseek-web": "https://chat.deepseek.com/",
}
ACCOUNTS = tuple(LOGIN_PAGES)
BASH = shutil.which("bash") or "/bin/bash"
FORBIDDEN = ("--remote-debugging", "--enable-automation", "--headless", "--no-sandbox")


def flags(account: str) -> list[str]:
    out = subprocess.run(
        [BASH, str(SCRIPT), "--flags", account], capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


@pytest.mark.parametrize("account", ACCOUNTS)
def test_the_window_runs_chromium_itself_without_automation(account: str) -> None:
    argv = flags(account)
    assert not any(a.startswith(f) for a in argv for f in FORBIDDEN), argv
    assert f"--user-data-dir=/profiles/{account}" in argv
    assert "--proxy-server=http://egress:3133" in argv
    assert "--no-first-run" in argv and "--disable-dev-shm-usage" in argv
    # Chrome itself never asks to sign the browser in (the owner signs in to the site).
    assert "--disable-sync" in argv and "--allow-browser-signin=false" in argv
    assert argv[-1] == LOGIN_PAGES[account]
    # ChatGPT's app needs more than the read tool's 192 MiB heap (§1.2).
    assert "--js-flags=--max-old-space-size=512" in argv
    script = SCRIPT.read_text()
    assert "hq_egress.browser_web" not in script  # no Playwright launch


def test_an_unknown_account_is_refused() -> None:
    out = subprocess.run([BASH, str(SCRIPT), "--flags", "other"], capture_output=True, text=True)
    assert out.returncode == 2


def test_google_sign_in_hosts_are_in_every_recipe() -> None:
    if not RECIPES.is_dir():
        pytest.skip("the recipes are mounted by test-env.sh (HQ_EGRESS_RECIPES)")
    loaded = Rc.load(RECIPES)
    for account in ACCOUNTS:
        hosts = loaded[account].sign_in_hosts()
        for host in ("accounts.google.com", "www.gstatic.com", "ssl.gstatic.com",
                     "fonts.gstatic.com", "gds.google.com", "consent.google.com",
                     "ogs.google.com", "accounts.google.de"):  # fmt: skip
            assert covered(host, hosts), (account, host)
