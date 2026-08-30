from pathlib import Path
import re

from tools.pipeline import (
    build_entity_prompt,
    build_property_prompt,
    load_field_config,
    load_workspace_config,
)

ROOT = Path(__file__).resolve().parents[1]


def _base_cfg(**extra):
    cfg = {
        "domain_hint": "金属材料文献",
        "fields": {
            "metadata": ["title"],
            "sample": ["sample_id", "sample_name"],
            "condition": ["condition_id", "condition_name"],
            "figure": ["figure_id"],
        },
        "rules": {},
        "property_source": {"allow": ["measured_table"], "deny": []},
    }
    cfg.update(extra)
    return cfg


def _conditions_schema_blob(prompt: str) -> str:
    match = re.search(r'"conditions":\s*\[(.*?)\]', prompt, re.S)
    assert match, prompt[:400]
    return match.group(1)


def test_entity_prompt_conditions_require_sample_id():
    prompt = build_entity_prompt(_base_cfg(), "实施例1 箔材")
    blob = _conditions_schema_blob(prompt)
    assert '"sample_id"' in blob
    assert '"condition_id"' in blob


def test_entity_prompt_paper_does_not_inject_patent_claim_rule():
    prompt = build_entity_prompt(_base_cfg(), "Steel A aged 450C")
    assert "权利要求" not in prompt


def test_entity_prompt_patent_uses_01_extract_rules():
    prompt = build_entity_prompt(_base_cfg(document_kind="patent"), "实施例1")
    assert "权利要求" in prompt
    assert "发明例" in prompt
    assert "实施例" in prompt
    assert "比较例" in prompt
    blob = _conditions_schema_blob(prompt)
    assert '"sample_id"' in blob


def test_property_prompt_keeps_string_condition_ids():
    step = {
        "id": "mechanical",
        "name": "力学性能",
        "group": "mechanical_properties",
        "fields": ["yield_strength"],
    }
    prompt = build_property_prompt(
        _base_cfg(), step, ["C1", "C2"], "Table 2 yield 685 MPa"
    )
    assert "C1" in prompt
    assert "C2" in prompt
    assert "论文正文" in prompt


def test_property_prompt_includes_stage1_skeleton():
    step = {
        "id": "mechanical",
        "name": "力学性能",
        "group": "mechanical_properties",
        "fields": ["yield_strength"],
    }
    skeleton = [
        {"condition_id": "C1", "sample_id": "S1", "condition_name": "实施例1"},
        {"condition_id": "C2", "sample_id": "S2", "condition_name": "实施例2"},
    ]
    prompt = build_property_prompt(
        _base_cfg(document_kind="patent"),
        step,
        skeleton,
        "实施例1 屈服 953 MPa",
    )
    assert "S1" in prompt
    assert "S2" in prompt
    assert "实施例1" in prompt
    assert '"sample_id"' in prompt
    assert "禁止新增" in prompt
    assert "骨架" in prompt


def test_cuti_patent_field_config_is_patent_kind():
    ws = load_workspace_config(ROOT)
    cfg = ws["projects"]["cuti_patent"]
    fc = load_field_config(ROOT, cfg)
    assert fc.get("document_kind") == "patent"


def test_review_tree_renders_conditions_missing_sample_id():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function renderResultTree")
    end = js.index("\n  function countRejected", start)
    fn = js[start:end]
    assert "未挂样品" in fn
    assert "sample_id" in fn


def test_frontend_entity_preview_puts_sample_id_on_conditions():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function buildPromptPreview")
    end = js.index("\n  function obj(", start)
    fn = js[start:end]
    assert "sample_id" in fn
