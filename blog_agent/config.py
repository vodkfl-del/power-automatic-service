"""설정 로딩.

config.yaml(사용자 설정)과 selectors.yaml(사이트 셀렉터)을 읽어 하나의 dict 로 합친다.
사이트 UI 가 바뀌면 코드 수정 없이 selectors.yaml 만 고치면 되도록 분리해 두었다.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "browser": {
        "mode": "cdp",
        "cdp_url": "http://127.0.0.1:9222",
        "user_data_dir": str(ROOT / "chrome-profile"),
        "chrome_path": "",
        "channel": "chrome",
        "headless": False,
        "slow_mo_ms": 0,
    },
    "output_dir": str(ROOT / "output"),
    "selectors_file": str(ROOT / "selectors.yaml"),
    "writing": {
        "providers": ["gemini", "chatgpt"],
        "prompt_file": str(ROOT / "prompts" / "article_prompt.txt"),
        "max_attempts_per_provider": 3,
        "response_timeout_sec": 300,
        "stable_sec": 5,
        "min_length": 1200,
        "end_marker": "[END]",
        "max_continue": 2,
        "clarify_preamble": (
            "아래 요청은 블로그에 게시할 일반 정보성 글 작성 요청입니다. "
            "웹 검색, 사이트 접속, 파일 생성 같은 외부 행동은 필요 없으며, "
            "보유한 일반 지식만으로 텍스트를 작성해 주시면 됩니다. "
            "확인이 어려운 수치나 최신 정보는 단정하지 말고 일반적인 설명으로 대체해 주세요.\n\n"
        ),
    },
    "images": {
        "count": 6,
        "providers": ["flow", "gemini", "chatgpt"],
        "max_attempts_per_provider": 2,
        "timeout_sec": 240,
        "prompt_prefix": "",
        "prompt_suffix": "",
        "gemini_request_template": "다음 설명으로 이미지를 1장 생성해줘. 이미지 안에 글자는 넣지 마.\n\n{prompt}",
        "chatgpt_request_template": "다음 설명으로 이미지를 1장 생성해줘. 이미지 안에 글자는 넣지 마.\n\n{prompt}",
        "flow_url": "https://labs.google/fx/tools/flow",
    },
    "naver": {
        "enabled": True,
        "blog_id": "",
        "publish": False,
        "category": "",
        "heading_sizes": {"h1": 28, "h2": 24, "h3": 19, "h4": 16},
        "image_upload_timeout_sec": 60,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _resolve(path_str: str, base_dir: Path) -> str:
    p = Path(path_str).expanduser()
    return str(p if p.is_absolute() else (base_dir / p).resolve())


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    base_dir = ROOT
    if path:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"설정 파일이 없습니다: {path}")
        base_dir = path.resolve().parent
        with open(path, encoding="utf-8") as f:
            cfg = deep_merge(cfg, yaml.safe_load(f) or {})

    # 상대 경로는 설정 파일 위치 기준으로 해석
    cfg["output_dir"] = _resolve(cfg["output_dir"], base_dir)
    cfg["selectors_file"] = _resolve(cfg["selectors_file"], base_dir)
    cfg["writing"]["prompt_file"] = _resolve(cfg["writing"]["prompt_file"], base_dir)
    cfg["browser"]["user_data_dir"] = _resolve(cfg["browser"]["user_data_dir"], base_dir)

    cfg["selectors"] = load_selectors(cfg["selectors_file"])
    return cfg


def load_selectors(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
