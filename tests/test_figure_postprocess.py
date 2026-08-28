from pathlib import Path
from tools.pipeline import run_extraction, load_workspace_config, load_field_config

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_demo_two_stage_marks_xrd_without_figure_step():
    out = run_extraction(ROOT, "demo_steel", "demo_steel_2024", mode="two_stage")
    ws = load_workspace_config(ROOT)
    steps = load_field_config(ROOT, ws["projects"]["demo_steel"]).get("steps") or []
    assert not any(s.get("type") == "figure" for s in steps)
    figs = out["result"]["figures"]
    xrd = next(f for f in figs if f.get("figure_type") == "XRD" or f.get("figure_id") == "Figure 3")
    assert xrd["status"] == "rejected_by_rule"
