"""4단계: 주제별 폴더 관리.

output/<주제>/
  ├─ article.html          AI 가 쓴 원본 HTML
  ├─ article_naver.html    스마트에디터용 변환본 (브라우저로 열면 이미지 포함 미리보기)
  ├─ article.txt           제목/태그/본문 텍스트
  ├─ image_prompts.txt     이미지 프롬프트 6개
  ├─ 01.png ~ 06.png       번호가 붙은 이미지
  ├─ state.json            단계별 진행 상태 (재실행 시 완료된 단계는 건너뜀)
  └─ _debug/               실패 시 스크린샷·HTML
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def safe_folder_name(topic: str, max_len: int = 80) -> str:
    name = INVALID.sub("_", topic).strip()
    name = re.sub(r"\s+", " ", name).rstrip(". ")
    return (name[:max_len].rstrip(". ") or "untitled")


def topic_folder(output_dir: str | Path, topic: str) -> Path:
    folder = Path(output_dir) / safe_folder_name(topic)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def existing_image(folder: Path, idx: int) -> Path | None:
    for ext in IMAGE_EXTS:
        p = folder / f"{idx:02d}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def image_files(folder: Path, count: int) -> list[Path | None]:
    return [existing_image(folder, i) for i in range(1, count + 1)]


class State:
    def __init__(self, folder: Path):
        self.path = folder / "state.json"
        self.data: dict = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def done(self, step: str) -> bool:
        return self.data.get(step, {}).get("status") == "done"

    def set(self, step: str, status: str, **info) -> None:
        self.data[step] = {"status": status, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **info}
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
