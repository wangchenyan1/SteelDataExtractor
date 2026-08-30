from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_review_pane_has_no_separate_warning_list():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    # 复核主面板不应再有独立告警条列表；未通过原因在结果树节点上
    review_start = html.index('data-view-panel="review"')
    review_end = html.index("</section>", review_start)
    review = html[review_start:review_end]
    assert 'id="resultFieldList"' in review
    assert 'id="resultReviewList"' not in review


def test_fill_result_panes_does_not_render_warning_list():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function fillResultPanes")
    end = js.index("\n  function countRejected", start)
    fn = js[start:end]
    assert "renderResultTree" in fn
    assert "resultReviewList" not in fn


def test_review_panes_share_equal_scroll_shell():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    css = (ROOT / "app/styles.css").read_text(encoding="utf-8")
    review_start = html.index('data-view-panel="review"')
    review_end = html.index("</section>", review_start)
    review = html[review_start:review_end]
    assert review.count('class="review-scroll"') == 2
    assert "--review-scroll-h" in css
    assert ".review-scroll {" in css
