from tools.config_model import export_project
from pathlib import Path

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_export_demo_contains_fields_steps_schema():
    data = export_project(ROOT, "demo_steel")
    assert data["project_id"] == "demo_steel"
    assert data["template_id"] == "steel"
    ids = [f["id"] for f in data["fields"]]
    assert "yield_strength" in ids
    assert any(s["type"] == "entity" for s in data["steps"])
    schema = data["schema"]
    assert "paper_metadata" in schema
    assert "samples" in schema
    assert "conditions" in schema
    assert "excerpt" in schema["paper_metadata"]["title"]
    assert schema["samples"][0]["sample_id"] == ""
    assert "mechanical_properties" in schema["conditions"][0]
    assert "excerpt" in schema["conditions"][0]["mechanical_properties"]["yield_strength"]
