from tools import workbench_server as wb

REAL_PAPER = "10.1007_s11665-019-04233-6"


def test_paper_meta_real_imported_paper():
    code, body = wb.handle_get("/api/paper_meta", {
        "project": ["demo_steel"], "paper_id": [REAL_PAPER]})
    assert code == 200
    assert body["has_md"] is True
    assert body["image_count"] >= 10
    assert "figure_001.png" in body["images"]


def test_paper_image_real_figure():
    from tools.workbench_server import resolve_paper_image_path
    p = resolve_paper_image_path(
        wb.ROOT, "demo_steel", REAL_PAPER, "figure_001.png")
    assert p is not None and p.exists()
    assert p.stat().st_size > 2000


def test_paper_image_rejects_traversal():
    from tools.workbench_server import resolve_paper_image_path
    assert resolve_paper_image_path(
        wb.ROOT, "demo_steel", REAL_PAPER, "../evil.png") is None


def test_paper_image_rejects_bad_paper_id():
    from tools.workbench_server import resolve_paper_image_path
    assert resolve_paper_image_path(
        wb.ROOT, "demo_steel", "..", "figure_001.png") is None
    assert resolve_paper_image_path(
        wb.ROOT, "demo_steel", "../x", "figure_001.png") is None


def test_paper_meta_rejects_bad_paper_id():
    code, _ = wb.handle_get("/api/paper_meta", {
        "project": ["demo_steel"], "paper_id": [".."]})
    assert code == 404
    code, _ = wb.handle_get("/api/paper_meta", {
        "project": ["demo_steel"], "paper_id": ["../x"]})
    assert code == 404


def test_paper_pdf_rejects_bad_paper_id():
    code, _ = wb.handle_get("/api/paper_pdf", {
        "project": ["demo_steel"], "paper_id": [".."]})
    assert code == 404
    code, _ = wb.handle_get("/api/paper_pdf", {
        "project": ["demo_steel"], "paper_id": ["../x"]})
    assert code == 404
