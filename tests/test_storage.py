from blog_agent.storage import State, existing_image, safe_folder_name, topic_folder


def test_safe_folder_name():
    assert safe_folder_name('a/b:c*d?"e<f>|g. ') == "a_b_c_d__e_f__g"
    assert safe_folder_name("   ") == "untitled"


def test_folder_state_and_images(tmp_path):
    f = topic_folder(tmp_path, "겨울철 습도")
    assert f.name == "겨울철 습도"
    (f / "02.jpg").write_bytes(b"x")
    assert existing_image(f, 2).name == "02.jpg" and existing_image(f, 1) is None
    s = State(f)
    s.set("write", "done", provider="gemini")
    assert State(f).done("write") and not State(f).done("images")
