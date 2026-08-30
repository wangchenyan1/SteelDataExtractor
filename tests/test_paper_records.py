from pathlib import Path
from tools import workbench_server as wb
from tools.pipeline import paper_title_from_md, list_paper_records, load_workspace_config

ROOT = Path(__file__).resolve().parents[1]


def test_title_from_first_heading():
    md = "preface\n# High temperature tensile\n\nHello\n"
    assert paper_title_from_md(md) == "High temperature tensile"


def test_title_none_without_heading():
    assert paper_title_from_md("no heading here") is None


def test_patent_title_prefers_invention_name_over_section():
    md = """(54)发明名称一种高强耐蚀Cu-Ti系合金箔材及其制备方法

## 技术领域
本发明属于金属材料。

# 一种高强耐蚀Cu-Ti系合金箔材及其制备方法
"""
    assert paper_title_from_md(md) == "一种高强耐蚀Cu-Ti系合金箔材及其制备方法"


def test_patent_title_skips_section_heading():
    md = """## 技术领域

正文

# 一种铜钛合金箔
"""
    assert paper_title_from_md(md) == "一种铜钛合金箔"


def test_list_paper_records_demo_steel():
    ws = load_workspace_config(ROOT)
    cfg = ws["projects"]["demo_steel"]
    recs = list_paper_records(ROOT, cfg)
    ids = {r["paper_id"] for r in recs}
    assert "10.1007_s11665-019-04233-6" in ids
    rec = next(r for r in recs if r["paper_id"] == "10.1007_s11665-019-04233-6")
    assert rec["parsed"] is True
    assert rec["title"]


def test_api_papers_objects():
    code, body = wb.handle_get("/api/papers", {"project": ["demo_steel"]})
    assert code == 200
    assert body["papers"]
    assert isinstance(body["papers"][0], dict)
    assert "paper_id" in body["papers"][0]
    assert "parsed" in body["papers"][0]
