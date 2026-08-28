from pathlib import Path
from tools.pipeline import run_extraction, reextract_field

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_reject_identity_field():
    run_extraction(ROOT, "demo_steel", "demo_steel_2024", mode="two_stage")
    try:
        reextract_field(ROOT, "demo_steel", "sample_id", paper_id="demo_steel_2024")
        assert False
    except ValueError as e:
        assert "标识" in str(e)


def test_reextract_one_property_keeps_others():
    out = run_extraction(ROOT, "demo_steel", "demo_steel_2024", mode="two_stage")
    before = out["result"]["conditions"][0]["mechanical_properties"]["tensile_strength"]["value"]
    rex = reextract_field(ROOT, "demo_steel", "yield_strength", paper_id="demo_steel_2024")
    after_ts = rex["result"]["conditions"][0]["mechanical_properties"]["tensile_strength"]["value"]
    assert after_ts == before
    assert "yield_strength" in rex["result"]["conditions"][0]["mechanical_properties"]
