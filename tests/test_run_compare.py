from pathlib import Path

from tools.run_compare import diff_results, flatten_result

ROOT = Path(__file__).resolve().parents[1]


def test_mode_select_copy_in_html():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert "完整流程（跑当前全部步骤 + 校验）" in html
    assert "只抽骨架" in html
    assert "对照：一次抽完（少做校验/图片过滤）" in html
    assert "不限于两步" in html
    assert 'value="two_stage"' in html
    assert 'value="entity_only"' in html
    assert 'value="single_pass"' in html


def test_compare_panel_in_review():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    start = html.index('data-view-panel="review"')
    block = html[start : start + 3500]
    assert 'id="compareRunA"' in block
    assert 'id="compareRunB"' in block
    assert 'id="btnCompareRuns"' in block
    assert 'id="runComparePanel"' in block
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "async function compareSelectedRuns" in js
    assert "function flattenResult" in js
    assert "modeLabel" in js


def test_run_option_label_uses_paper_and_mode():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function runOptionLabel")
    block = js[start : start + 500]
    assert "paper_id" in block
    assert "modeLabel" in block
    assert "${paper}_${mode}" in block or "${paper}_" in block


def test_flatten_and_diff_detects_value_change():
    a = {
        "paper_metadata": {"doi": {"value": "10.1", "excerpt": "x"}},
        "samples": [{"sample_id": "S1", "composition": {"value": "C 0.1", "excerpt": "t"}}],
        "conditions": [],
        "figures": [],
    }
    b = {
        "paper_metadata": {"doi": {"value": "10.1", "excerpt": "x"}},
        "samples": [{"sample_id": "S1", "composition": {"value": "C 0.2", "excerpt": "t"}}],
        "conditions": [],
        "figures": [],
    }
    flat_a = flatten_result(a)
    assert flat_a["samples[S1].composition"] == "C 0.1"
    rows = diff_results(a, b, include_same=False)
    assert len(rows) == 1
    assert rows[0]["path"] == "samples[S1].composition"
    assert rows[0]["a"] == "C 0.1"
    assert rows[0]["b"] == "C 0.2"


def test_diff_include_same():
    a = {"paper_metadata": {"title": {"value": "T"}}, "samples": [], "conditions": [], "figures": []}
    b = {"paper_metadata": {"title": {"value": "T"}}, "samples": [], "conditions": [], "figures": []}
    assert diff_results(a, b, include_same=False) == []
    assert len(diff_results(a, b, include_same=True)) >= 1
