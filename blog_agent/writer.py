"""1단계: 글 작성 에이전트.

복구 순서(사이트별):
  1회차  새 대화 + 원본 프롬프트
  2회차  새 대화 + '정보성 글 작성일 뿐 외부 행동 불필요' 안내문을 앞에 붙인 프롬프트
  3회차  새 대화 + 안내문 + 프롬프트 (사이트 일시 오류 대비 재시도)
  → 그래도 실패하면 다음 사이트(예: Gemini → ChatGPT)로 넘어간다.
응답이 중간에 끊기면(TRUNCATED) 같은 대화에서 '이어서 작성'을 요청해 합친다.
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import BrowserContext

from .article import Article, parse_reply
from .providers import CHAT_PROVIDERS, ChatProvider, ChatReply, ProviderError
from .refusal import Verdict, judge_article, lint_prompt

log = logging.getLogger(__name__)

CONTINUE_MSG = "끊긴 지점부터 이어서 작성해 주세요. 앞 내용은 반복하지 말고, 같은 형식을 유지하고, 마지막에 {end} 를 붙여 주세요."


class WritingFailed(RuntimeError):
    pass


def build_prompt(template: str, topic: str) -> str:
    return template.replace("{topic}", topic).replace("{주제}", topic)


def _merge(a: ChatReply, b: ChatReply) -> ChatReply:
    return ChatReply(a.text.rstrip() + "\n" + b.text.lstrip(), a.code_blocks + b.code_blocks)


def _one_attempt(provider: ChatProvider, prompt: str, wcfg: dict) -> tuple[ChatReply, Verdict, str]:
    provider.new_chat()
    reply = provider.ask(prompt, wcfg["response_timeout_sec"], wcfg["stable_sec"])
    j = judge_article(reply.text, min_length=wcfg["min_length"], end_marker=wcfg["end_marker"])

    continues = 0
    while j.verdict == Verdict.TRUNCATED and continues < wcfg["max_continue"]:
        continues += 1
        log.info("  응답이 끊김(%s) → 이어서 작성 요청 %d회", j.reason, continues)
        more = provider.ask(CONTINUE_MSG.format(end=wcfg["end_marker"]), wcfg["response_timeout_sec"], wcfg["stable_sec"])
        reply = _merge(reply, more)
        j = judge_article(reply.text, min_length=wcfg["min_length"], end_marker=wcfg["end_marker"])

    if j.verdict == Verdict.TRUNCATED and len(reply.text) >= wcfg["min_length"]:
        # 이어쓰기 후에도 종료 표시만 빠진 경우: 분량이 충분하면 통과
        return reply, Verdict.OK, "종료 표시 없으나 분량 충족"
    return reply, j.verdict, j.reason


def write_article(context: BrowserContext, cfg: dict, topic: str, debug_dir: Path) -> tuple[Article, dict]:
    wcfg = cfg["writing"]
    template = Path(wcfg["prompt_file"]).read_text(encoding="utf-8")
    base_prompt = build_prompt(template, topic)

    for w in lint_prompt(base_prompt):
        log.warning("프롬프트 점검: %s", w)

    history: list[dict] = []
    for pname in wcfg["providers"]:
        provider = CHAT_PROVIDERS[pname](context, cfg["selectors"], debug_dir)
        try:
            for attempt in range(1, wcfg["max_attempts_per_provider"] + 1):
                prompt = base_prompt if attempt == 1 else wcfg["clarify_preamble"] + base_prompt
                log.info("[글작성] %s 시도 %d", pname, attempt)
                try:
                    reply, verdict, reason = _one_attempt(provider, prompt, wcfg)
                except (ProviderError, Exception) as e:  # noqa: BLE001 - 사이트 오류는 모두 재시도 대상
                    provider.debug(f"write_err{attempt}")
                    log.warning("  %s 오류: %s", pname, e)
                    history.append({"provider": pname, "attempt": attempt, "verdict": "error", "reason": str(e)[:300]})
                    continue

                history.append({"provider": pname, "attempt": attempt, "verdict": verdict.value, "reason": reason})
                if verdict == Verdict.OK:
                    art = parse_reply(reply.text, reply.code_blocks, fallback_title=topic)
                    (debug_dir.parent / "raw_reply.txt").write_text(reply.text, encoding="utf-8")
                    log.info("  성공: 제목=%r, 이미지 프롬프트 %d개", art.title, len(art.image_prompts))
                    return art, {"provider": pname, "history": history}
                provider.debug(f"write_{verdict.value}{attempt}")
                log.warning("  실패(%s): %s", verdict.value, reason)
        finally:
            provider.close()

    raise WritingFailed(f"모든 사이트에서 글 작성 실패: {history}")
