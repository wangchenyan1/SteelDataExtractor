from tools.workbench_server import handle_get, handle_post


def test_export_demo():
    status, data = handle_get("/api/projects/demo_steel/export", {})
    assert status == 200
    assert data["template_id"] == "steel"
    assert data["fields"]


def test_field_library():
    status, data = handle_get("/api/field_library", {"template": ["steel"]})
    assert status == 200
    assert data["fields"]


def test_export_results_single_and_multi_paper_ids():
    status, data = handle_get(
        "/api/projects/demo_steel/export_results",
        {"paper_ids": ["10.1007_s11665-019-04233-6"]},
    )
    assert status == 200
    assert data["paper_id"] == "10.1007_s11665-019-04233-6"
    assert "result" in data

    status, data = handle_get(
        "/api/projects/demo_steel/export_results",
        {"paper_ids": ["10.1007_s11665-019-04233-6,no_such_paper"]},
    )
    assert status == 200
    assert data["paper_id"] == "10.1007_s11665-019-04233-6"

    status, missing = handle_get(
        "/api/projects/demo_steel/export_results",
        {"paper_ids": ["no_such_paper_xyz"]},
    )
    assert status == 404
    assert "暂无运行结果" in missing["error"]


def test_projects_payload_includes_document_kind():
    status, data = handle_get("/api/projects", {})
    assert status == 200
    demo = data["projects"]["demo_steel"]
    assert demo["document_kind"] == "paper"
    cuti = data["projects"]["cuti"]
    assert cuti["document_kind"] == "paper"
