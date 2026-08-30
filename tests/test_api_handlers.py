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


def test_projects_payload_includes_document_kind():
    status, data = handle_get("/api/projects", {})
    assert status == 200
    demo = data["projects"]["demo_steel"]
    assert demo["document_kind"] == "paper"
    cuti = data["projects"]["cuti"]
    assert cuti["document_kind"] == "paper"
