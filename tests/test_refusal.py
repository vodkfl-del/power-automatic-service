from blog_agent.refusal import Verdict, judge_article, lint_prompt

LONG = "본문 문장입니다. " * 300


def test_gemini_style_refusal_detected():
    for msg in ["저는 이 행동은 할 수 없어요.", "죄송하지만 그 요청은 도와드릴 수 없습니다.",
                "I can't help with that.", "문제가 발생했습니다. 다시 시도해 주세요."]:
        assert judge_article(msg, min_length=1200, end_marker="[END]").verdict == Verdict.REFUSED, msg


def test_long_article_with_negative_sentence_is_not_refusal():
    text = LONG + "이 방법은 겨울에는 사용할 수 없어요.\n" + LONG + "[END]"
    assert judge_article(text, min_length=1200, end_marker="[END]").ok


def test_truncated_without_end_marker():
    assert judge_article(LONG[:2000], min_length=1200, end_marker="[END]").verdict == Verdict.TRUNCATED


def test_too_short_with_end_marker():
    assert judge_article("짧은 글 " * 100 + "[END]", min_length=1200, end_marker="[END]").verdict == Verdict.TOO_SHORT


def test_empty():
    assert judge_article("  ", min_length=10, end_marker=None).verdict == Verdict.EMPTY


def test_lint_flags_action_instructions():
    warns = lint_prompt("최신 뉴스를 검색해서 사이트에 들어가 정리하고 AI 탐지 안 되게 써줘")
    assert len(warns) >= 3
    assert lint_prompt("친근한 말투로 정보성 글을 써 주세요") == []
