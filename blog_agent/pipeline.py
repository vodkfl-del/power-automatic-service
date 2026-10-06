"""전체 흐름: 글 작성 → 이미지 6장 → 네이버 변환/입력 → 폴더 정리.

각 단계 결과는 state.json 에 기록되어, 오류로 멈춘 뒤 같은 주제로 다시 실행하면
완료된 단계는 건너뛰고 실패한 단계부터 이어서 진행한다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from playwright.sync_api import BrowserContext

from . import images as images_step
from . import naver_converter, naver_publisher, writer
from .article import Article
from .storage import State, image_files, topic_folder

log = logging.getLogger(__name__)

STEPS = ("write", "images", "convert", "naver")


def _save_article(folder: Path, art: Article) -> None:
    (folder / "article.html").write_text(art.html, encoding="utf-8")
    (folder / "image_prompts.txt").write_text(
        "\n".join(f"{i}. {p}" for i, p in enumerate(art.image_prompts, 1)), encoding="utf-8")
    (folder / "article.json").write_text(json.dumps(art.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_article(folder: Path) -> Article:
    return Article(**json.loads((folder / "article.json").read_text(encoding="utf-8")))


def run_topic(context: BrowserContext, cfg: dict, topic: str, only: set[str] | None = None,
              force: bool = False) -> dict:
    steps = set(only or STEPS)
    if not cfg["naver"].get("enabled", True):
        steps.discard("naver")
    folder = topic_folder(cfg["output_dir"], topic)
    debug_dir = folder / "_debug"
    state = State(folder)
    count = cfg["images"]["count"]
    log.info("===== 주제: %s  →  %s", topic, folder)

    # 1) 글 작성
    if "write" in steps and (force or not state.done("write")):
        state.set("write", "running")
        try:
            art, info = writer.write_article(context, cfg, topic, debug_dir)
        except Exception as e:
            state.set("write", "failed", error=str(e)[:500])
            raise
        _save_article(folder, art)
        state.set("write", "done", **info)
    art = _load_article(folder)

    # 2) 이미지
    if "images" in steps and (force or not state.done("images")):
        state.set("images", "running")
        prompts = images_step.normalize_prompts(art.image_prompts, count, topic)
        try:
            summary = images_step.generate_images(context, cfg, prompts, folder, debug_dir)
        except Exception as e:
            state.set("images", "failed", error=str(e)[:500])
            raise
        state.set("images", "done", **summary)

    # 3) 스마트에디터용 변환
    doc = naver_converter.convert(art.html, art.title, count, cfg["naver"].get("heading_sizes"))
    files = {i: p for i, p in enumerate(image_files(folder, count), 1) if p}
    if "convert" in steps or "naver" in steps:
        (folder / "article_naver.html").write_text(
            doc.preview_html({i: p.name for i, p in files.items()}), encoding="utf-8")
        (folder / "article.txt").write_text(
            f"제목: {art.title}\n태그: {', '.join(art.tags)}\n\n" + _plain_text(art.html), encoding="utf-8")
        state.set("convert", "done", segments=len(doc.segments))

    # 4) 네이버 입력
    if "naver" in steps and (force or not state.done("naver")):
        if len(files) < count:
            log.warning("이미지가 %d/%d 장뿐입니다. 있는 것만 넣습니다.", len(files), count)
        state.set("naver", "running")
        try:
            result = naver_publisher.publish(context, cfg, doc, files, art.tags, debug_dir)
        except Exception as e:
            state.set("naver", "failed", error=str(e)[:500])
            raise
        state.set("naver", "done", **result)

    log.info("===== 완료: %s", folder)
    return state.data


def _plain_text(html: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
