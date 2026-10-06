"""Google Flow (labs.google/fx/tools/flow) 이미지 생성.

Flow 는 채팅 화면이 아니라 '프로젝트' 화면이라 새 대화 개념이 없다.
config.yaml 의 images.flow_url 에 이미지 생성 모드로 맞춰 둔 프로젝트 URL 을 넣어 두면
그 화면에서 프롬프트 입력 → 새로 생긴 이미지를 저장한다.
"""
from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import BrowserContext

from .. import dom
from .base import ChatProvider, ProviderError


class FlowProvider(ChatProvider):
    name = "flow"

    def __init__(self, context: BrowserContext, selectors: dict, debug_dir: Path | None = None, url: str = ""):
        super().__init__(context, selectors, debug_dir)
        self.url = url

    def new_chat(self) -> None:
        if self.url and self.url.rstrip("/") not in self.page.url:
            self.page.goto(self.url, wait_until="domcontentloaded")
        dom.first_visible(self.page, self.sel["input"], timeout=60)
        time.sleep(1.0)

    def is_generating(self) -> bool:
        return False

    def response_count(self) -> int:
        return 0

    def generate_image(self, prompt: str, dest: Path, timeout: float, template: str = "{prompt}") -> Path:
        self.new_chat()
        known = self.image_srcs()
        self.send(prompt)
        img = self.wait_new_image(known, timeout)
        if img is None:
            msg = ""
            try:
                msg = dom.first_visible(self.page, self.sel.get("error_text", []), timeout=0).inner_text()
            except dom.SelectorNotFound:
                pass
            raise ProviderError(f"flow: 이미지 없음 {msg[:120]!r}")
        return dom.download_image(self.page, img, dest)
