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


def test_library_check_does_not_save_overlay_immediately():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("async function onLibraryCheckChange")
    end = js.index("async function saveOverlay", start)
    fn = js[start:end]
    assert "saveOverlay" not in fn
    assert "assignPropertyToDraft" in fn


def test_stage_editor_renders_chips_not_property_checkboxes():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function renderStageEditor")
    end = js.index("function loadConfigEditor", start)
    fn = js[start:end]
    assert "stage-chip" in fn
    assert 'input[type="checkbox"]' not in fn or "checkbox" not in fn.split("stage-fields")[-1][:400]


def test_locked_field_ids_constant():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "sample_id" in js
    assert "LOCKED_FIELD_IDS" in js


def test_papers_view_has_upload_and_table():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    papers = html[html.index('data-view-panel="papers"'):]
    assert 'id="pdfFileInput"' in papers
    assert "multiple" in papers
    assert 'id="paperTable"' in papers
    assert 'id="btnImportPdfs"' in papers
    assert 'id="btnRunSelected"' in papers
    assert 'id="paperRunPreview"' not in papers.split("legacy")[0] or 'hidden' in papers


def test_import_pdfs_function_exists():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "async function importPdfs" in js
    assert "async function runSelectedPapers" in js
    assert "FormData" in js


def test_update_run_buttons_restores_import():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function updateRunButtons")
    end = js.index("function updateUploadVisibility", start)
    fn = js[start:end]
    assert "btnImportPdfs" in fn


def test_add_property_group_ui():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert 'id="btnAddPropertyGroup"' in html
    assert 'id="fieldLabel"' in html
    assert 'id="fieldGroup"' in html


def test_save_config_includes_property_groups():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    fn = js[js.index("async function saveConfigView") : js.index("function renderFields")]
    assert "property_groups" in fn


def test_ui_has_no_readonly_snapshot_copy():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert "只读快照" not in js
    assert "只读快照" not in html
    assert "不可试跑" not in js


def test_config_has_document_kind_select_above_stages():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    kind_idx = html.index('id="documentKind"')
    stage_idx = html.index(">抽取阶段<")
    assert kind_idx < stage_idx
    select = html[kind_idx:stage_idx]
    assert 'value="paper"' in select
    assert 'value="patent"' in select
    assert "学术文献" in html
    assert "专利" in html
    assert 'id="projectKindBadge"' in html
    assert 'id="papersKindBadge"' in html


def test_document_kind_stays_in_draft_until_save():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("async function saveConfigView")
    end = js.index("function renderFields", start)
    fn = js[start:end]
    assert "document_kind" in fn
    bind = js[js.index("function bindEvents"):]
    assert 'documentKind"' in bind or "documentKind" in bind
    hydrate = js[js.index("async function refreshProjectConfig"): js.index("function splitCsv")]
    assert "document_kind" in hydrate
    assert "kind-badge" in js or "projectKindBadge" in js
