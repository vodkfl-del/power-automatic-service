"""3단계-2: 네이버 블로그 스마트에디터 ONE 에 글 + 이미지 입력.

기본값은 '임시저장'까지만 한다(naver.publish: false). 확인 후 직접 발행하는 것을 권장.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Frame, Page

from . import dom
from .naver_converter import NaverDoc

log = logging.getLogger(__name__)


class NaverError(RuntimeError):
    pass


def _editor_frame(page: Page, sel: dict) -> Page | Frame:
    """글쓰기 화면은 mainFrame iframe 안에 있을 때가 있다."""
    for _ in range(40):
        frame = page.frame(name=sel.get("frame", "mainFrame"))
        target = frame or page
        if dom.any_visible(target, sel["title"]):
            return target
        time.sleep(0.5)
    raise NaverError("스마트에디터를 찾지 못했습니다 (로그인 여부와 blog_id 를 확인하세요)")


def _close_popups(target, selectors: list[str]) -> None:
    """'작성 중인 글 이어쓰기', 도움말 패널 같은 팝업을 닫는다."""
    for _ in range(3):
        closed = False
        for sel in selectors:
            loc = target.locator(sel)
            try:
                if loc.count() and loc.first.is_visible():
                    loc.first.click()
                    closed = True
                    time.sleep(0.5)
            except Exception:
                pass
        if not closed:
            return


def _focus_end_of_body(target, page: Page, sel: dict) -> None:
    body = dom.all_matches(target, sel["body"])
    if body is None:
        raise NaverError("본문 입력 영역을 찾지 못했습니다")
    body.last.click()
    page.keyboard.press("ControlOrMeta+End")


def _upload_image(page: Page, target, sel: dict, path: Path, timeout: float) -> None:
    btn = dom.first_visible(target, sel["image_button"], timeout=10)
    with page.expect_file_chooser(timeout=10_000) as fc:
        btn.click()
    fc.value.set_files(str(path))
    time.sleep(1.5)
    deadline = time.time() + timeout
    while time.time() < deadline and dom.any_visible(target, sel.get("uploading", [])):
        time.sleep(0.5)
    time.sleep(1.0)


def publish(context: BrowserContext, cfg: dict, doc: NaverDoc, images: dict[int, Path],
            tags: list[str], debug_dir: Path) -> dict:
    ncfg = cfg["naver"]
    sel = cfg["selectors"]["naver"]
    if not ncfg.get("blog_id"):
        raise NaverError("config.yaml 의 naver.blog_id 를 입력하세요")

    page = context.new_page()
    try:
        page.goto(sel["write_url"].format(blog_id=ncfg["blog_id"]), wait_until="domcontentloaded")
        target = _editor_frame(page, sel)
        time.sleep(2.0)
        _close_popups(target, sel.get("popup_close", []))

        title_box = dom.first_visible(target, sel["title"], timeout=15)
        title_box.click()
        page.keyboard.insert_text(doc.title)

        _focus_end_of_body(target, page, sel)
        for seg in doc.segments:
            if seg.kind == "html":
                para = dom.all_matches(target, sel["body"]).last
                dom.paste_html(target, para, seg.html)
                time.sleep(0.8)
            else:
                img = images.get(seg.index)
                if not img:
                    log.warning("이미지 %02d 없음 - 건너뜀", seg.index)
                    continue
                log.info("[네이버] 이미지 %02d 업로드", seg.index)
                _upload_image(page, target, sel, img, ncfg["image_upload_timeout_sec"])
            _focus_end_of_body(target, page, sel)

        if ncfg.get("publish"):
            dom.first_visible(target, sel["publish_open"], timeout=10).click()
            time.sleep(1.5)
            if tags:
                try:
                    tag_in = dom.first_visible(target, sel["tag_input"], timeout=5)
                    for t in tags[:10]:
                        tag_in.click()
                        page.keyboard.insert_text(t)
                        page.keyboard.press("Enter")
                except dom.SelectorNotFound:
                    log.warning("태그 입력칸을 찾지 못해 태그는 생략")
            dom.first_visible(target, sel["publish_confirm"], timeout=10).click()
            time.sleep(4.0)
            status = "published"
        else:
            dom.first_visible(target, sel["save"], timeout=10).click()
            time.sleep(2.0)
            status = "draft_saved"
        log.info("[네이버] 완료: %s", status)
        return {"status": status, "url": page.url}
    except Exception:
        dom.dump_debug(page, debug_dir, "naver")
        raise
    finally:
        if ncfg.get("close_tab_after", False):
            page.close()
