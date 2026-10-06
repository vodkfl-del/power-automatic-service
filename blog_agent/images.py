"""2단계: 이미지 생성 에이전트.

이미지마다 Flow → Gemini → ChatGPT 순으로 시도한다(순서는 config 에서 변경).
이미 저장된 번호(01~06)는 건너뛰므로, 중간에 멈춰도 다시 실행하면 남은 것만 만든다.
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import BrowserContext

from .providers import IMAGE_PROVIDERS, FlowProvider, ProviderError
from .storage import existing_image

log = logging.getLogger(__name__)


class ImagesIncomplete(RuntimeError):
    pass


def _make_provider(name: str, context: BrowserContext, cfg: dict, debug_dir: Path):
    cls = IMAGE_PROVIDERS[name]
    if cls is FlowProvider:
        return cls(context, cfg["selectors"], debug_dir, url=cfg["images"]["flow_url"])
    return cls(context, cfg["selectors"], debug_dir)


def normalize_prompts(prompts: list[str], count: int, topic: str) -> list[str]:
    """프롬프트 개수를 count 에 맞춘다. 부족하면 주제 기반 기본 프롬프트로 채운다."""
    prompts = [p for p in prompts if p.strip()][:count]
    fillers = [
        f"{topic}를 주제로 한 블로그 대표 이미지, 밝고 깔끔한 사진 스타일",
        f"{topic}와 관련된 일상 장면, 자연광, 사실적인 사진",
        f"{topic}의 핵심 개념을 표현한 미니멀 일러스트",
        f"{topic} 관련 소품을 정돈해 둔 탑뷰 사진",
        f"{topic}를 실천하는 사람의 뒷모습, 따뜻한 색감",
        f"{topic} 정리를 상징하는 깔끔한 책상 위 노트와 커피",
    ]
    i = 0
    while len(prompts) < count:
        prompts.append(fillers[i % len(fillers)])
        i += 1
    return prompts


def generate_images(context: BrowserContext, cfg: dict, prompts: list[str], folder: Path, debug_dir: Path) -> dict:
    icfg = cfg["images"]
    results: dict[int, dict] = {}
    providers = {name: _make_provider(name, context, cfg, debug_dir) for name in icfg["providers"]}
    try:
        for idx, prompt in enumerate(prompts, start=1):
            done = existing_image(folder, idx)
            if done:
                log.info("[이미지 %02d] 이미 있음: %s", idx, done.name)
                results[idx] = {"file": done.name, "provider": "existing"}
                continue

            full_prompt = f"{icfg['prompt_prefix']}{prompt}{icfg['prompt_suffix']}"
            results[idx] = {"file": None, "errors": []}
            for name, provider in providers.items():
                template = icfg.get(f"{name}_request_template", "{prompt}")
                for attempt in range(1, icfg["max_attempts_per_provider"] + 1):
                    log.info("[이미지 %02d] %s 시도 %d", idx, name, attempt)
                    try:
                        path = provider.generate_image(full_prompt, folder / f"{idx:02d}", icfg["timeout_sec"], template)
                        results[idx] = {"file": path.name, "provider": name, "prompt": prompt}
                        log.info("  저장: %s", path.name)
                        break
                    except (ProviderError, Exception) as e:  # noqa: BLE001
                        provider.debug(f"img{idx:02d}_{attempt}")
                        log.warning("  실패: %s", str(e)[:200])
                        results[idx]["errors"].append(f"{name}#{attempt}: {str(e)[:200]}")
                if results[idx].get("file"):
                    break
    finally:
        for p in providers.values():
            p.close()

    missing = [i for i, r in results.items() if not r.get("file")]
    summary = {"images": results, "missing": missing}
    if missing:
        raise ImagesIncomplete(f"이미지 생성 실패 번호: {missing}")
    return summary
