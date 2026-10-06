"""AI 응답 텍스트 → 제목 / 본문 HTML / 이미지 프롬프트 / 태그 추출."""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field

TAG_RE = re.compile(r"<(h[1-6]|p|div|ul|ol|table|section|article|blockquote)\b", re.I)

IMAGE_PROMPT_PATTERNS = [
    re.compile(r"\[\s*IMAGE[_\s-]*PROMPT[_\s-]*(\d+)\s*\]\s*[:：]?\s*(.+)", re.I),
    re.compile(r"<!--\s*IMAGE[_\s-]*PROMPT[_\s-]*(\d+)\s*[:：]\s*(.+?)\s*-->", re.I),
    re.compile(r"^\s*(?:\*\*)?\s*이미지\s*(?:프롬프트)?\s*(\d+)\s*(?:\*\*)?\s*[:：]\s*(.+)", re.M),
    re.compile(r"^\s*(?:\*\*)?\s*Image\s*(?:Prompt)?\s*#?(\d+)\s*(?:\*\*)?\s*[:：]\s*(.+)", re.M | re.I),
]

# 본문 안 이미지 위치 표시: <!-- IMAGE_1 -->, [IMAGE_1], [이미지1], [이미지 1]
IMAGE_SLOT_RE = re.compile(
    r"<!--\s*IMAGE[_\s-]*(\d+)\s*-->|\[\s*IMAGE[_\s-]*(\d+)\s*\]|\[\s*이미지\s*(\d+)\s*\]", re.I
)


@dataclass
class Article:
    title: str
    html: str
    image_prompts: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _field(text: str, name: str) -> str:
    m = re.search(rf"\[\s*{name}\s*\]\s*[:：]?\s*(.+)", text, re.I)
    return m.group(1).strip() if m else ""


def extract_image_prompts(text: str) -> list[str]:
    found: dict[int, str] = {}
    for rx in IMAGE_PROMPT_PATTERNS:
        for m in rx.finditer(text):
            idx, prompt = int(m.group(1)), m.group(2).strip().strip("*").strip()
            prompt = re.sub(r"\s*\[END\]\s*$", "", prompt)
            if prompt and idx not in found:
                found[idx] = prompt
        if found:
            break
    return [found[k] for k in sorted(found)]


def extract_html(text: str, code_blocks: list[str]) -> str:
    blocks = [c for c in code_blocks if TAG_RE.search(c)]
    if blocks:
        return "\n".join(_strip_code_header(b) for b in blocks).strip()

    m = re.search(r"\[HTML\](.*?)(\[/HTML\]|\[IMAGE[_\s-]*PROMPT|\[END\]|$)", text, re.S | re.I)
    if m and TAG_RE.search(m.group(1)):
        return m.group(1).strip()

    if TAG_RE.search(text):
        start = TAG_RE.search(text).start()
        end = max(text.rfind("</p>"), text.rfind("</ul>"), text.rfind("</ol>"),
                  text.rfind("</table>"), text.rfind("</div>"), text.rfind("-->"))
        return text[start:end + 6 if end > 0 else len(text)].strip()

    return plain_to_html(text)


def _strip_code_header(block: str) -> str:
    lines = block.strip().splitlines()
    while lines and lines[0].strip().lower() in {"html", "copy code", "코드 복사", "복사"}:
        lines.pop(0)
    return "\n".join(lines)


def plain_to_html(text: str) -> str:
    """HTML 을 못 받았을 때 마크다운/일반 텍스트를 간단한 HTML 로 바꾼다."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or re.match(r"\[(TITLE|TAGS|END|HTML|/HTML)\]", line, re.I):
            continue
        if any(rx.match(line) for rx in IMAGE_PROMPT_PATTERNS):
            continue
        if IMAGE_SLOT_RE.fullmatch(line):
            out.append(line)
            continue
        m = re.match(r"^(#{1,4})\s+(.+)", line)
        if m:
            level = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{level}>{_inline_md(m.group(2))}</h{level}>")
        elif re.match(r"^[-*•]\s+", line):
            out.append(f"<ul><li>{_inline_md(line[2:].strip())}</li></ul>")
        else:
            out.append(f"<p>{_inline_md(line)}</p>")
    return re.sub(r"</ul>\s*<ul>", "", "\n".join(out))


def _inline_md(s: str) -> str:
    s = htmllib.escape(s, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def parse_reply(text: str, code_blocks: list[str], fallback_title: str) -> Article:
    title = _field(text, "TITLE") or fallback_title
    tags_raw = _field(text, "TAGS")
    tags = [t.strip().lstrip("#") for t in re.split(r"[,\s]+", tags_raw) if t.strip().lstrip("#")]
    html = extract_html(text, code_blocks)
    prompts = extract_image_prompts(text) or extract_image_prompts("\n".join(code_blocks))
    return Article(title=title, html=html, image_prompts=prompts, tags=tags)
