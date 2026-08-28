from tools import workbench_server as wb


def test_paper_meta_demo():
    code, body = wb.handle_get("/api/paper_meta", {
        "project": ["demo_steel"], "paper_id": ["demo_steel_2024"]})
    assert code == 200
    assert body["has_md"] is True
    assert "has_pdf" in body


def test_paper_image_demo():
    # handle_get 若只返回 JSON，可改为测内部 resolve 函数
    from tools.workbench_server import resolve_paper_image_path
    p = resolve_paper_image_path(wb.ROOT, "demo_steel", "demo_steel_2024", "fig1_om.png")
    assert p is not None and p.exists()


def test_paper_image_rejects_traversal():
    from tools.workbench_server import resolve_paper_image_path
    assert resolve_paper_image_path(
        wb.ROOT, "demo_steel", "demo_steel_2024", "../evil.png") is None
