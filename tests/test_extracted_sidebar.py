from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sidebar_has_shared_extracted_list():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert 'data-view-panel="review export"' in html
    start = html.index('data-view-panel="review export"')
    end = html.index("</section>", start)
    block = html[start:end]
    assert 'id="extractedPaperList"' in block
    assert "已抽取" in block


def test_set_view_splits_data_view_panel():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function setView")
    end = js.index("// ---------------------------------------------------------------- init", start)
    fn = js[start:end]
    assert "split" in fn
    assert "data-view-panel" in fn


def test_extracted_list_renders_extracted_only_and_loads_review():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "function renderExtractedPaperList" in js
    start = js.index("function renderExtractedPaperList")
    end = js.index("\n  function ", start + 10)
    # allow next function after a reasonable chunk
    fn = js[start:start + 2500]
    assert "extracted" in fn
    assert "还没有已抽取" in fn
    assert "selectExtractedPaper" in js
    sel = js[js.index("function selectExtractedPaper") : js.index("function selectExtractedPaper") + 800]
    if "async function selectExtractedPaper" in js:
        sel = js[js.index("async function selectExtractedPaper") : js.index("async function selectExtractedPaper") + 800]
    assert "loadReview" in sel
    assert "selectPaperRow" in sel


def test_review_view_autoloads_extracted_current():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function setView")
    end = js.index("// ---------------------------------------------------------------- init", start)
    fn = js[start:end]
    assert 'name === "review"' in fn or 'name==="review"' in fn
    assert "loadReview" in fn
