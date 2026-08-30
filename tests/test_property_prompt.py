from tools.pipeline import build_property_prompt


def test_property_prompt_includes_paper_text():
    cfg = {
        "fields": {"property": ["yield_strength"]},
        "rules": {},
        "property_source": {"allow": ["measured_table"], "deny": []},
    }
    step = {
        "id": "mechanical",
        "name": "力学性能",
        "group": "mechanical_properties",
        "fields": ["yield_strength"],
    }
    text = "Table 2. A-700 yield strength 685 MPa"
    prompt = build_property_prompt(cfg, step, ["C1", "C2"], text)
    assert "论文正文" in prompt
    assert text in prompt
    assert "C1" in prompt
    assert "第一个字符是 {" in prompt
