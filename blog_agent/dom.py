"""페이지 조작 공통 도우미."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Frame, Locator, Page

PageLike = Page | Frame


class SelectorNotFound(RuntimeError):
    pass


def first_visible(page: PageLike, selectors: Iterable[str], timeout: float = 10.0) -> Locator:
    """후보 셀렉터 중 화면에 보이는 첫 요소를 반환 (마지막 매칭 요소 기준)."""
    selectors = list(selectors)
    deadline = time.time() + timeout
    while True:
        for sel in selectors:
            loc = page.locator(sel)
            try:
                n = loc.count()
            except Exception:
                continue
            for i in range(n - 1, -1, -1):
                item = loc.nth(i)
                try:
                    if item.is_visible():
                        return item
                except Exception:
                    pass
        if time.time() >= deadline:
            raise SelectorNotFound(f"요소를 찾지 못함: {selectors}")
        time.sleep(0.3)


def any_visible(page: PageLike, selectors: Iterable[str]) -> bool:
    try:
        first_visible(page, selectors, timeout=0)
        return True
    except SelectorNotFound:
        return False


def all_matches(page: PageLike, selectors: Iterable[str]) -> Locator | None:
    """후보 중 1개 이상 매칭되는 첫 셀렉터의 Locator."""
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    return None


def insert_long_text(page: Page, target: Locator, text: str) -> None:
    """긴 프롬프트 입력.

    keyboard.type() 은 줄바꿈마다 Enter 가 눌려 프롬프트가 '반쪽'만 전송되는 대표적 오류 원인이다.
    insert_text 는 Enter 이벤트 없이 한 번에 넣으므로 줄바꿈이 있어도 중간 전송되지 않는다.
    """
    target.click()
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.press("Delete")
    page.keyboard.insert_text(text)


def paste_html(page: PageLike, target: Locator, html: str, plain: str = "") -> None:
    """contenteditable 에 HTML 을 '붙여넣기' 이벤트로 넣는다 (스마트에디터가 서식을 해석)."""
    target.evaluate(
        """(el, [html, plain]) => {
            el.focus();
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            dt.setData('text/plain', plain || el.innerText || '');
            const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
            el.dispatchEvent(ev);
        }""",
        [html, plain],
    )


def download_image(page: Page, img: Locator, dest: Path) -> Path:
    """<img> 를 파일로 저장. http(s) 는 로그인 쿠키를 공유하는 request 로, blob/data 는 페이지 안에서 읽는다."""
    src = img.get_attribute("src") or ""
    data: bytes
    if src.startswith("data:"):
        data = base64.b64decode(src.split(",", 1)[1])
    elif src.startswith("blob:") or not src.startswith("http"):
        b64 = img.evaluate(
            """async (el) => {
                const r = await fetch(el.src);
                const b = await r.blob();
                return await new Promise(res => {
                    const fr = new FileReader();
                    fr.onload = () => res(fr.result.split(',')[1]);
                    fr.readAsDataURL(b);
                });
            }"""
        )
        data = base64.b64decode(b64)
    else:
        resp = page.context.request.get(src)
        if not resp.ok:
            # 쿠키 요청이 막히면 캔버스로 다시 그려 추출
            b64 = img.evaluate(
                """(el) => { const c = document.createElement('canvas');
                    c.width = el.naturalWidth; c.height = el.naturalHeight;
                    c.getContext('2d').drawImage(el, 0, 0);
                    return c.toDataURL('image/png').split(',')[1]; }"""
            )
            data = base64.b64decode(b64)
        else:
            data = resp.body()
    if len(data) < 5000:
        raise RuntimeError(f"이미지가 너무 작음({len(data)} bytes) - 썸네일/아이콘일 가능성")
    dest = dest.with_suffix(_guess_ext(data))
    dest.write_bytes(data)
    return dest


def _guess_ext(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def dump_debug(page: Page, folder: Path, tag: str) -> None:
    """오류 시 스크린샷과 HTML 을 남겨 원인 파악을 쉽게 한다."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H%M%S")
    try:
        page.screenshot(path=str(folder / f"{stamp}_{tag}.png"), full_page=False)
        (folder / f"{stamp}_{tag}.html").write_text(page.content(), encoding="utf-8")
        (folder / f"{stamp}_{tag}.json").write_text(json.dumps({"url": page.url}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
