from blog_agent.article import extract_image_prompts, parse_reply, plain_to_html

REPLY = """[TITLE] 겨울철 습도 관리
[TAGS] 습도, #가습기, 겨울
html
Copy code
<h2>왜 중요할까</h2><p>설명</p><!-- IMAGE_1 -->
[IMAGE_PROMPT_1] a cozy living room with a humidifier
[IMAGE_PROMPT_2]: wet towel hanging indoors
[END]"""


def test_parse_reply_with_code_block():
    art = parse_reply(REPLY, ["html\nCopy code\n<h2>왜 중요할까</h2><p>설명</p><!-- IMAGE_1 -->"], "fallback")
    assert art.title == "겨울철 습도 관리"
    assert art.tags == ["습도", "가습기", "겨울"]
    assert art.html.startswith("<h2>")
    assert art.image_prompts == ["a cozy living room with a humidifier", "wet towel hanging indoors"]


def test_parse_reply_without_code_block_uses_inline_html():
    art = parse_reply(REPLY, [], "fallback")
    assert "<h2>왜 중요할까</h2>" in art.html


def test_korean_prompt_format():
    assert extract_image_prompts("이미지 1: 거실\n**이미지 2**: 창문") == ["거실", "창문"]


def test_plain_markdown_fallback():
    html = plain_to_html("## 소제목\n본문 **강조**\n- 항목1\n- 항목2")
    assert "<h3>소제목</h3>" in html and "<b>강조</b>" in html and html.count("<ul>") == 1
