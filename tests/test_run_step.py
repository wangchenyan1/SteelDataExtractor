from pathlib import Path
from tools.pipeline import run_step

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_property_before_entity_raises():
    try:
        run_step(ROOT, "demo_steel", "demo_steel_2024", "mechanical")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "骨架" in str(e)


def test_staged_entity_then_mechanical():
    out_e = run_step(ROOT, "demo_steel", "demo_steel_2024", "entity", partition="test")
    assert out_e["result"]["samples"]
    assert "mechanical_properties" not in out_e["result"]["conditions"][0]
    out_m = run_step(ROOT, "demo_steel", "demo_steel_2024", "mechanical",
                     run_id=out_e["run_id"], partition="test")
    assert "mechanical_properties" in out_m["result"]["conditions"][0]
    ys = out_m["result"]["conditions"][0]["mechanical_properties"]["yield_strength"]
    assert ys.get("excerpt")
    assert ys.get("location") == "Table 2"


def test_rerun_entity_invalidates_and_reruns_downstream():
    out_e = run_step(ROOT, "demo_steel", "demo_steel_2024", "entity", partition="test")
    rid = out_e["run_id"]
    run_step(ROOT, "demo_steel", "demo_steel_2024", "mechanical", run_id=rid, partition="test")
    rerun = run_step(ROOT, "demo_steel", "demo_steel_2024", "entity", run_id=rid, partition="test")
    assert "mechanical" in rerun["invalidated"]
    assert "mechanical_properties" in rerun["result"]["conditions"][0]
