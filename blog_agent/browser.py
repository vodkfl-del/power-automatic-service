"""브라우저 연결.

권장: cdp 모드
  실제 크롬을 원격 디버깅 포트로 켜 두고(python -m blog_agent chrome) Playwright 가 거기에 '접속'한다.
  - 구글/네이버가 자동화 브라우저로 판단해 로그인을 막거나 "안전하지 않은 브라우저" 경고를 띄우는 문제를 피한다.
  - 로그인은 처음 한 번 사람이 직접 하면 프로필 폴더에 유지된다.

대안: persistent 모드
  Playwright 가 전용 프로필 폴더로 크롬을 직접 실행한다. 일부 사이트에서 로그인이 막힐 수 있다.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import BrowserContext, sync_playwright

log = logging.getLogger(__name__)

CHROME_CANDIDATES = {
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    "Linux": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
}


def find_chrome(explicit: str = "") -> str:
    if explicit:
        return explicit
    for cand in CHROME_CANDIDATES.get(platform.system(), []):
        if os.path.isabs(cand) and Path(cand).exists():
            return cand
        found = shutil.which(cand)
        if found:
            return found
    raise FileNotFoundError("크롬 실행 파일을 찾지 못했습니다. config.yaml 의 browser.chrome_path 를 지정하세요.")


def _cdp_alive(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def launch_debug_chrome(cfg: dict) -> None:
    """원격 디버깅 포트가 열린 크롬을 별도 프로필로 실행한다."""
    b = cfg["browser"]
    if _cdp_alive(b["cdp_url"]):
        log.info("이미 디버깅 크롬이 실행 중입니다: %s", b["cdp_url"])
        return
    port = b["cdp_url"].rsplit(":", 1)[-1].strip("/")
    Path(b["user_data_dir"]).mkdir(parents=True, exist_ok=True)
    args = [
        find_chrome(b.get("chrome_path", "")),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={b['user_data_dir']}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://gemini.google.com/app",
        "https://chatgpt.com/",
        "https://nid.naver.com/nidlogin.login",
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if _cdp_alive(b["cdp_url"]):
            log.info("디버깅 크롬 실행 완료. 열린 탭에서 Gemini / ChatGPT / 네이버에 로그인해 두세요.")
            return
        time.sleep(0.5)
    raise RuntimeError("크롬이 디버깅 포트로 열리지 않았습니다. 포트(9222)를 다른 프로그램이 쓰는지, chrome_path 가 맞는지 확인하세요.")


@contextmanager
def open_context(cfg: dict):
    b = cfg["browser"]
    with sync_playwright() as pw:
        if b["mode"] == "cdp":
            if not _cdp_alive(b["cdp_url"]):
                launch_debug_chrome(cfg)
            browser = pw.chromium.connect_over_cdp(b["cdp_url"])
            context: BrowserContext = browser.contexts[0] if browser.contexts else browser.new_context()
            try:
                yield context
            finally:
                # 사용자의 크롬은 닫지 않는다. 연결만 끊는다.
                browser.close()
        else:
            context = pw.chromium.launch_persistent_context(
                b["user_data_dir"],
                channel=b.get("channel") or None,
                headless=b.get("headless", False),
                slow_mo=b.get("slow_mo_ms", 0),
                viewport=None,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                yield context
            finally:
                context.close()
