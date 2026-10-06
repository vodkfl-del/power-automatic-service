"""3단계-1: 일반 HTML → 네이버 스마트에디터 ONE 붙여넣기용 HTML.

스마트에디터는 붙여넣은 HTML 중 일부 태그만 서식으로 인식한다.
- h1~h4      → 굵은 글씨 + 글자 크기 지정한 문단 (소제목처럼 보이게)
- strong/em  → b / i
- blockquote → 기울임 인용 문단
- ul/ol/li, table, a, br → 유지
- div/section 등 레이아웃 태그, class/id, script/style, 외부 img → 제거
본문 중 이미지 위치 표시(<!-- IMAGE_1 -->, [IMAGE_1], [이미지1])를 기준으로
'HTML 조각 / 이미지 번호'가 번갈아 나오는 segments 로 나눈다.
위치 표시가 없으면 소제목 앞에 고르게 자동 배치한다.
"""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from .article import IMAGE_SLOT_RE

REMOVE_TAGS = {"script", "style", "iframe", "form", "button", "input", "noscript", "head", "meta", "link",
               "svg", "img", "picture", "video", "audio", "canvas", "nav", "title"}
UNWRAP_TAGS = {"html", "body", "div", "section", "article", "main", "header", "footer", "aside", "figure",
               "figcaption", "span", "font", "center", "small", "mark", "code"}
KEEP_ATTRS = {"a": {"href"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}, "span": {"style"}}
SAFE_STYLE = re.compile(r"^\s*(color|background-color|font-size|font-weight)\s*:", re.I)
BLOCK_TAGS = {"p", "ul", "ol", "table", "blockquote", "hr"}
IMG_TAG = "x-se-image"


@dataclass
class Segment:
    kind: str  # "html" | "image"
    html: str = ""
    index: int = 0


@dataclass
class NaverDoc:
    title: str
    segments: list[Segment] = field(default_factory=list)

    def preview_html(self, image_names: dict[int, str] | None = None) -> str:
        image_names = image_names or {}
        parts = [f"<h1>{htmllib.escape(self.title)}</h1>"]
        for s in self.segments:
            if s.kind == "html":
                parts.append(s.html)
            else:
                name = image_names.get(s.index, f"{s.index:02d}.png")
                parts.append(f'<p style="text-align:center"><img src="{name}" style="max-width:100%"></p>')
        return ("<!doctype html><meta charset='utf-8'><title>" + htmllib.escape(self.title) + "</title>"
                "<body style='max-width:720px;margin:auto;font-family:sans-serif;line-height:1.8'>"
                + "\n".join(parts) + "</body>")


def _mark_image_slots(raw: str) -> str:
    def repl(m: re.Match) -> str:
        n = next(g for g in m.groups() if g)
        return f"<{IMG_TAG} data-i='{int(n)}'></{IMG_TAG}>"
    return IMAGE_SLOT_RE.sub(repl, raw)


def _clean_attrs(tag: Tag) -> None:
    allowed = KEEP_ATTRS.get(tag.name, set())
    if tag.name == IMG_TAG:
        return
    for attr in list(tag.attrs):
        if attr not in allowed:
            del tag.attrs[attr]
    if "style" in tag.attrs:
        style = ";".join(d for d in tag["style"].split(";") if SAFE_STYLE.match(d))
        if style:
            tag["style"] = style
        else:
            del tag.attrs["style"]
    if tag.name == "a" and not str(tag.get("href", "")).startswith(("http://", "https://")):
        tag.unwrap()


def convert(html: str, title: str, image_count: int = 6, heading_sizes: dict | None = None) -> NaverDoc:
    sizes = {"h1": 28, "h2": 24, "h3": 19, "h4": 16, **(heading_sizes or {})}
    soup = BeautifulSoup(_mark_image_slots(html), "html.parser")

    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for t in soup.find_all(REMOVE_TAGS):
        t.decompose()
    for t in soup.find_all(["strong"]):
        t.name = "b"
    for t in soup.find_all(["em"]):
        t.name = "i"
    for t in soup.find_all("pre"):
        t.name = "p"
    # 스타일 있는 span 은 유지, 나머지 레이아웃 태그는 벗겨낸다
    for t in soup.find_all(UNWRAP_TAGS):
        if t.name == "span" and t.get("style") and SAFE_STYLE.search(t.get("style", "")):
            continue
        t.unwrap()
    for t in soup.find_all(True):
        _clean_attrs(t)

    for level in ("h1", "h2", "h3", "h4", "h5", "h6"):
        for h in soup.find_all(level):
            size = sizes.get(level, 16)
            text = h.decode_contents().strip()
            new = BeautifulSoup(f'<p data-heading="1"><span style="font-size:{size}px"><b>{text}</b></span></p>',
                                "html.parser").p
            h.replace_with(new)
    for q in soup.find_all("blockquote"):
        inner = q.get_text(" ", strip=True)
        q.replace_with(BeautifulSoup(f"<p><i>“{htmllib.escape(inner)}”</i></p>", "html.parser").p)

    blocks = _top_level_blocks(soup)
    title = re.sub(r"\s+", " ", title).strip()
    return NaverDoc(title=title, segments=_to_segments(blocks, image_count))


def _top_level_blocks(soup: BeautifulSoup) -> list[Tag | str]:
    """최상위 노드를 문단 단위 블록 목록으로 정리. 떠도는 텍스트는 <p> 로 감싼다."""
    blocks: list[Tag | str] = []
    pending_inline: list[str] = []

    def flush():
        text = "".join(pending_inline).strip()
        if text:
            blocks.append(BeautifulSoup(f"<p>{text}</p>", "html.parser").p)
        pending_inline.clear()

    for node in list(soup.contents):
        if isinstance(node, NavigableString):
            for line in str(node).split("\n\n"):
                pending_inline.append(htmllib.escape(line) if line.strip() else "")
                if line.strip():
                    flush()
            continue
        if node.name == IMG_TAG:
            flush()
            blocks.append(node)
        elif node.name in BLOCK_TAGS:
            flush()
            # <p> 안에 이미지 표시만 있으면 이미지 블록으로 올린다
            imgs = node.find_all(IMG_TAG)
            if imgs and not node.get_text(strip=True):
                blocks.extend(imgs)
            elif imgs:
                for im in imgs:
                    im.extract()
                blocks.append(node)
                blocks.extend(imgs)
            elif node.get_text(strip=True) or node.name in {"hr", "table"}:
                blocks.append(node)
        elif node.name == "br":
            flush()
        else:
            pending_inline.append(str(node))
    flush()
    return blocks


def _is_img(b) -> bool:
    return isinstance(b, Tag) and b.name == IMG_TAG


def _auto_positions(blocks: list, n: int) -> list[int]:
    """이미지 n장을 넣을 블록 인덱스(그 앞에 삽입). 첫 장은 도입 문단 뒤, 나머지는 소제목 앞."""
    if not blocks or n <= 0:
        return []
    first = 1 if len(blocks) > 1 else len(blocks)
    headings = [i for i, b in enumerate(blocks) if isinstance(b, Tag) and b.get("data-heading") and i > first]
    rest = n - 1
    if len(headings) >= rest:
        cands = headings
    else:
        cands = sorted(set(headings) | set(range(first + 1, len(blocks) + 1)))
    picks: list[int] = []
    if rest > 0 and cands:
        step = len(cands) / rest
        picks = [cands[min(int(i * step), len(cands) - 1)] for i in range(rest)]
    positions = [first] + picks
    while len(positions) < n:
        positions.append(len(blocks))
    return positions


def _to_segments(blocks: list, image_count: int) -> list[Segment]:
    marked = [int(b["data-i"]) for b in blocks if _is_img(b)]
    placed: set[int] = set()
    seq: list[tuple[str, object]] = []

    if marked:
        for b in blocks:
            if _is_img(b):
                i = int(b["data-i"])
                if 1 <= i <= image_count and i not in placed:
                    placed.add(i)
                    seq.append(("image", i))
            else:
                seq.append(("html", b))
        for i in range(1, image_count + 1):
            if i not in placed:
                seq.append(("image", i))
    else:
        positions = _auto_positions(blocks, image_count)
        by_pos: dict[int, list[int]] = {}
        for img_no, pos in enumerate(positions, start=1):
            by_pos.setdefault(pos, []).append(img_no)
        for i, b in enumerate(blocks):
            for img_no in by_pos.get(i, []):
                seq.append(("image", img_no))
            seq.append(("html", b))
        for img_no in by_pos.get(len(blocks), []):
            seq.append(("image", img_no))

    segments: list[Segment] = []
    buf: list[str] = []
    for kind, val in seq:
        if kind == "html":
            if isinstance(val, Tag) and val.has_attr("data-heading"):
                del val["data-heading"]
            buf.append(str(val))
        else:
            if buf:
                segments.append(Segment("html", "\n".join(buf)))
                buf = []
            segments.append(Segment("image", index=val))
    if buf:
        segments.append(Segment("html", "\n".join(buf)))
    return segments


def convert_file(src: Path, title: str = "", image_count: int = 6) -> NaverDoc:
    html = Path(src).read_text(encoding="utf-8")
    return convert(html, title or Path(src).stem, image_count)
