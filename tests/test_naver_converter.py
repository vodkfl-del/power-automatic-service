from blog_agent.naver_converter import convert

HTML = """<html><head><style>p{}</style></head><body><div class="x">
<h2 id="a">첫 소제목</h2><p class="c">문단 <strong>강조</strong> <a href="javascript:x">링크</a></p>
<!-- IMAGE_1 -->
<p>[이미지 2]</p>
<h3>둘째</h3><p>내용</p><script>alert(1)</script><img src="x.png">
</div></body></html>"""


def kinds(doc):
    return [(s.kind, s.index) if s.kind == "image" else ("html", 0) for s in doc.segments]


def test_markers_split_and_cleanup():
    doc = convert(HTML, "제목", image_count=3)
    assert kinds(doc) == [("html", 0), ("image", 1), ("image", 2), ("html", 0), ("image", 3)]
    joined = "".join(s.html for s in doc.segments)
    assert "font-size:24px" in joined and "<b>첫 소제목</b>" in joined
    assert "<b>강조</b>" in joined
    for bad in ("<script", "<img", "class=", "id=", "javascript", "<div", "<h2"):
        assert bad not in joined


def test_auto_placement_without_markers():
    html = "<p>도입</p>" + "".join(f"<h2>소제목{i}</h2><p>내용{i}</p>" for i in range(5))
    doc = convert(html, "t", image_count=6)
    imgs = [s.index for s in doc.segments if s.kind == "image"]
    assert imgs == [1, 2, 3, 4, 5, 6]
    assert doc.segments[0].kind == "html" and "도입" in doc.segments[0].html
    assert doc.segments[1].kind == "image"


def test_loose_text_wrapped_in_paragraphs():
    doc = convert("그냥 텍스트<br>두번째", "t", image_count=0)
    assert all(s.kind == "html" for s in doc.segments)
    assert "<p>그냥 텍스트</p>" in doc.segments[0].html


def test_preview_contains_images():
    doc = convert("<p>a</p><p>b</p>", "제목", image_count=2)
    prev = doc.preview_html({1: "01.jpg"})
    assert 'src="01.jpg"' in prev and 'src="02.png"' in prev
