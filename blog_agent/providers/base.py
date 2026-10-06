"""채팅형 AI 사이트(Gemini, ChatGPT) 공통 동작."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import BrowserContext, Page

from .. import dom

log = logging.getLogger(__name__)


@dataclass
class ChatReply:
    text: str
    code_blocks: list[str] = field(default_factory=list)


class ProviderError(RuntimeError):
    pass


class ChatProvider:
    name = "base"

    def __init__(self, context: BrowserContext, selectors: dict, debug_dir: Path | None = None):
        self.context = context
        self.sel = selectors[self.name]
        self.debug_dir = debug_dir
        self._page: Page | None = None

    # -- 페이지 -------------------------------------------------------------
    @property
    def page(self) -> Page:
        if self._page is None or self._page.is_closed():
            self._page = self.context.new_page()
        return self._page

    def new_chat(self) -> None:
        """새 대화를 연다. 이전 대화 맥락(이전 거절 포함)이 다음 요청에 영향을 주지 않게 매번 새로 시작."""
        self.page.goto(self.sel["url"], wait_until="domcontentloaded")
        dom.first_visible(self.page, self.sel["input"], timeout=30)
        time.sleep(1.0)

    def close(self) -> None:
        if self._page and not self._page.is_closed():
            self._page.close()
        self._page = None

    # -- 전송/수신 ----------------------------------------------------------
    def response_count(self) -> int:
        loc = dom.all_matches(self.page, self.sel["response"])
        return loc.count() if loc else 0

    def send(self, text: str) -> None:
        box = dom.first_visible(self.page, self.sel["input"], timeout=20)
        dom.insert_long_text(self.page, box, text)
        time.sleep(0.5)
        try:
            btn = dom.first_visible(self.page, self.sel["send"], timeout=5)
            btn.click()
        except dom.SelectorNotFound:
            box.press("Enter")

    def is_generating(self) -> bool:
        return dom.any_visible(self.page, self.sel["stop"])

    def last_reply(self) -> ChatReply:
        loc = dom.all_matches(self.page, self.sel["response"])
        if not loc or loc.count() == 0:
            return ChatReply("")
        last = loc.last
        text = last.inner_text()
        codes: list[str] = []
        for csel in self.sel.get("code_block", []):
            c = last.locator(csel)
            if c.count():
                codes = [c.nth(i).inner_text() for i in range(c.count())]
                break
        return ChatReply(text, codes)

    def wait_reply(self, before_count: int, timeout: float, stable_sec: float = 5.0) -> ChatReply:
        """응답 완료 대기.

        '중지 버튼이 사라짐' + '텍스트가 stable_sec 동안 변하지 않음' 두 조건을 모두 만족해야 완료로 본다.
        (한 가지만 보면 스트리밍 중간에 끊어 읽는 오류가 생긴다)
        """
        deadline = time.time() + timeout
        last_text, last_change = "", time.time()
        started = False
        while time.time() < deadline:
            time.sleep(1.0)
            if self.response_count() <= before_count and not self.is_generating():
                continue
            started = True
            reply = self.last_reply()
            if reply.text != last_text:
                last_text, last_change = reply.text, time.time()
                continue
            if not self.is_generating() and time.time() - last_change >= stable_sec and last_text.strip():
                return reply
        if not started:
            raise ProviderError(f"{self.name}: 응답이 시작되지 않음 (전송 실패 또는 로그인 필요)")
        log.warning("%s: 응답 대기 시간 초과 - 받은 부분까지 반환", self.name)
        return self.last_reply()

    def ask(self, text: str, timeout: float, stable_sec: float = 5.0) -> ChatReply:
        before = self.response_count()
        self.send(text)
        return self.wait_reply(before, timeout, stable_sec)

    # -- 이미지 -------------------------------------------------------------
    def image_srcs(self) -> set[str]:
        srcs: set[str] = set()
        for sel in self.sel.get("image", []):
            loc = self.page.locator(sel)
            for i in range(loc.count()):
                s = loc.nth(i).get_attribute("src")
                if s:
                    srcs.add(s)
        return srcs

    def wait_new_image(self, known: set[str], timeout: float):
        """새로 나타난 이미지 중 가장 큰 것을 반환. 없으면 None."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2.0)
            if self.is_generating():
                continue
            best, best_area = None, 0
            for sel in self.sel.get("image", []):
                loc = self.page.locator(sel)
                for i in range(loc.count()):
                    img = loc.nth(i)
                    src = img.get_attribute("src") or ""
                    if not src or src in known:
                        continue
                    try:
                        w, h = img.evaluate("el => [el.naturalWidth, el.naturalHeight]")
                    except Exception:
                        continue
                    if w * h > best_area and min(w, h) >= 256:
                        best, best_area = img, w * h
            if best is not None:
                time.sleep(2.0)  # 고해상도 교체 대기
                return best
        return None

    def generate_image(self, prompt: str, dest: Path, timeout: float, template: str) -> Path:
        self.new_chat()
        known = self.image_srcs()
        before = self.response_count()
        self.send(template.format(prompt=prompt))
        img = self.wait_new_image(known, timeout)
        if img is None:
            reply = self.last_reply() if self.response_count() > before else ChatReply("")
            raise ProviderError(f"{self.name}: 이미지 없음 / 응답: {reply.text[:120]!r}")
        return dom.download_image(self.page, img, dest)

    def debug(self, tag: str) -> None:
        if self.debug_dir and self._page and not self._page.is_closed():
            dom.dump_debug(self._page, self.debug_dir, f"{self.name}_{tag}")
