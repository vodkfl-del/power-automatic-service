"""AI 응답의 '거절/중단' 판정과 프롬프트 사전 점검.

Gemini/GPT 웹 화면은 API 와 달리 오류가 '정상 답변처럼' 텍스트로 돌아온다.
("저는 이 행동은 할 수 없어요", "I can't help with that" 등)
그래서 응답을 받은 뒤 아래 기준으로 실패 여부를 판정한다.

- REFUSED     : 짧은 응답 + 거절 문구
- TRUNCATED   : 종료 표시([END])가 없고 길이도 부족 → '이어서' 요청 대상
- TOO_SHORT   : 종료 표시는 있으나 최소 길이 미달
- EMPTY       : 아무것도 못 받음
- OK
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

REFUSAL_PATTERNS = [
    # 한국어 (Gemini / ChatGPT 에서 실제로 자주 보이는 문구들)
    r"(저는|제가)\s*(이|그)?\s*(행동|작업|요청)[은는을를]?\s*(수행|처리|도와)?\s*(할|해\s*드릴)\s*수\s*(없|가\s*없)",
    r"(도와|도움을)\s*(드릴|드리기)\s*(수\s*없|어렵)",
    r"(처리|수행|생성|작성)(할|해\s*드릴|하기)\s*수\s*없(습니다|어요|네요)",
    r"(그|이)\s*(요청|부분)(은|는|에는)\s*(도와|응답|답변)",
    r"저는\s*(텍스트\s*기반|언어\s*모델|AI)\s*(이라|이기|이므로|이어서)",
    r"정책(에|상)\s*(따라|위반|어긋)",
    r"이미지를\s*(생성|만들)(할|어\s*드릴)\s*수\s*없",
    r"(아직|현재)\s*(그|이)\s*(기능|작업)(은|을|는)\s*(지원|할\s*수)",
    r"문제가\s*발생했습니다|오류가\s*발생했습니다|다시\s*시도해\s*주세요",
    # 영어
    r"\bI\s*(can.?t|cannot|am\s+unable\s+to|won.?t\s+be\s+able\s+to)\s+(help|do|assist|create|generate|complete)",
    r"\bI.?m\s+(not\s+able|unable)\s+to\b",
    r"\bI.?m\s+just\s+a\s+language\s+model\b",
    r"\b(content|usage)\s+polic(y|ies)\b",
    r"\bsomething\s+went\s+wrong\b",
    r"\bnetwork\s+error\b",
]
_REFUSAL_RE = [re.compile(p, re.IGNORECASE) for p in REFUSAL_PATTERNS]

# 이 길이 이하의 응답에서 거절 문구가 보이면 거절로 판정.
# (긴 본문 속 "~할 수 없어요" 같은 일반 문장을 거절로 오판하지 않기 위함)
REFUSAL_MAX_LEN = 700


class Verdict(str, Enum):
    OK = "ok"
    REFUSED = "refused"
    TRUNCATED = "truncated"
    TOO_SHORT = "too_short"
    EMPTY = "empty"


@dataclass
class Judgement:
    verdict: Verdict
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == Verdict.OK


def find_refusal(text: str) -> str | None:
    for rx in _REFUSAL_RE:
        m = rx.search(text)
        if m:
            return m.group(0)
    return None


def judge_article(text: str, *, min_length: int, end_marker: str | None) -> Judgement:
    body = (text or "").strip()
    if not body:
        return Judgement(Verdict.EMPTY, "응답이 비어 있음")

    if len(body) <= REFUSAL_MAX_LEN:
        hit = find_refusal(body)
        if hit:
            return Judgement(Verdict.REFUSED, f"거절 문구 감지: {hit!r}")

    has_end = bool(end_marker) and end_marker in body
    if end_marker and not has_end and len(body) < max(min_length * 3, 6000):
        # 종료 표시가 없으면 중간에 끊긴 것으로 본다 (길이가 아주 길면 표시만 빠진 것으로 간주)
        return Judgement(Verdict.TRUNCATED, f"종료 표시 {end_marker!r} 없음 (길이 {len(body)})")

    if len(body) < min_length:
        return Judgement(Verdict.TOO_SHORT, f"길이 {len(body)} < 최소 {min_length}")

    return Judgement(Verdict.OK)


def judge_image_reply(text: str) -> Judgement:
    """이미지 요청 후 이미지가 안 나왔을 때 텍스트 응답을 판정."""
    hit = find_refusal(text or "")
    if hit:
        return Judgement(Verdict.REFUSED, f"거절 문구 감지: {hit!r}")
    return Judgement(Verdict.EMPTY, "이미지가 생성되지 않음")


# ---------------------------------------------------------------------------
# 프롬프트 사전 점검: 웹 채팅에서 거절을 자주 유발하는 표현을 미리 알려준다.
# ---------------------------------------------------------------------------
PROMPT_RISKS = [
    (r"(검색|서치)\s*해|구글링|최신\s*뉴스를?\s*찾", "웹 검색을 '행동'으로 지시하면 '그 작업은 할 수 없어요'로 끊기는 경우가 많습니다. '알고 있는 정보로 작성'으로 바꾸세요."),
    (r"(사이트|링크|URL|url)\s*(에\s*)?(들어가|접속|방문|열어)", "사이트 접속 지시는 채팅 모델이 수행할 수 없는 행동입니다. 필요한 내용을 프롬프트에 직접 붙여 넣으세요."),
    (r"(파일|이미지)\s*(을|를)?\s*(만들어|생성해|저장해|다운로드)", "글 작성 프롬프트 안의 이미지/파일 '생성' 지시는 거절 원인입니다. 이미지는 '프롬프트 텍스트'만 출력하도록 하세요."),
    (r"AI\s*(탐지|감지|티)|사람(이|처럼)\s*(쓴|보이)|GPT\s*킬러|우회", "탐지 회피류 지시는 정책 거절을 유발할 수 있습니다. '자연스러운 구어체' 같은 문체 지시로 바꾸세요."),
    (r"(실명|연예인|정치인).{0,10}(비방|폭로|루머)", "실존 인물 관련 단정적 서술은 거절 또는 중단 사유가 됩니다."),
    (r"(100%|무조건|확실히)\s*(완치|수익|효과)", "의료·금융 효과 단정 표현은 안전 필터에 걸리기 쉽습니다."),
]
_PROMPT_RISKS_RE = [(re.compile(p, re.IGNORECASE), msg) for p, msg in PROMPT_RISKS]


def lint_prompt(prompt: str) -> list[str]:
    warnings = []
    for rx, msg in _PROMPT_RISKS_RE:
        m = rx.search(prompt)
        if m:
            warnings.append(f"[{m.group(0)}] {msg}")
    return warnings
