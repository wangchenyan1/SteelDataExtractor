from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_config_status_element_in_config_panel():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert 'id="configStatus"' in html
    idx = html.index('id="btnSaveConfig"')
    field_config_panel = html[html.rindex('data-view-panel="config"', 0, idx) : html.index("</section>", idx)]
    assert "configStatus" in field_config_panel


def test_save_config_view_uses_config_status():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("async function saveConfigView")
    end = js.index("function renderFields", start)
    fn = js[start:end]
    assert "setConfigStatus" in fn
    assert "runStatus" not in fn
