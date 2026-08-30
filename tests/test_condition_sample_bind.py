# -*- coding: utf-8 -*-
from tools.pipeline import (
    CONDITION_SAMPLE_BINDING_RULES,
    bind_condition_sample_ids,
    build_entity_prompt,
)


def _paper_cfg():
    return {
        "domain_hint": "metal",
        "document_kind": "paper",
        "fields": {
            "metadata": ["title"],
            "sample": ["sample_id", "composition"],
            "condition": ["condition_id", "condition_name"],
            "figure": ["figure_id"],
        },
        "rules": {},
    }


def test_paper_entity_prompt_requires_condition_sample_binding():
    prompt = build_entity_prompt(_paper_cfg(), "Steel A aged; Table 2 YS")
    assert "condition.sample_id" in prompt
    assert "sample_id" in prompt
    # binding block injected for papers too
    assert CONDITION_SAMPLE_BINDING_RULES.splitlines()[0] in prompt
    assert "sample_id" in CONDITION_SAMPLE_BINDING_RULES
    assert "????" not in prompt


def test_bind_fills_single_sample_missing_ids():
    entity = {
        "samples": [{"sample_id": "S1", "composition": {"value": "C 0.1"}}],
        "conditions": [
            {"condition_id": "C1", "condition_name": {"value": "ST"}},
            {"condition_id": "C2", "sample_id": "", "condition_name": {"value": "CR"}},
            {"condition_id": "C3"},
        ],
    }
    out, warnings = bind_condition_sample_ids(entity)
    assert all(c.get("sample_id") == "S1" for c in out["conditions"])
    assert any(w["type"] == "condition_sample_id_filled" for w in warnings)
    assert len([w for w in warnings if w["type"] == "condition_sample_id_filled"]) == 3


def test_bind_warns_when_multi_sample_missing():
    entity = {
        "samples": [{"sample_id": "S1"}, {"sample_id": "S2"}],
        "conditions": [
            {"condition_id": "C1", "sample_id": "S1"},
            {"condition_id": "C2"},
        ],
    }
    out, warnings = bind_condition_sample_ids(entity)
    assert out["conditions"][0]["sample_id"] == "S1"
    assert not out["conditions"][1].get("sample_id")
    assert any(w["type"] == "condition_missing_sample_id" for w in warnings)


def test_bind_fixes_invalid_id_when_single_sample():
    entity = {
        "samples": [{"sample_id": "S1"}],
        "conditions": [{"condition_id": "C1", "sample_id": "SX"}],
    }
    out, warnings = bind_condition_sample_ids(entity)
    assert out["conditions"][0]["sample_id"] == "S1"
    assert any(w["type"] == "condition_sample_id_fixed" for w in warnings)


def test_bind_keeps_valid_multi_sample_links():
    entity = {
        "samples": [{"sample_id": "S1"}, {"sample_id": "S2"}],
        "conditions": [
            {"condition_id": "C1", "sample_id": "S1"},
            {"condition_id": "C2", "sample_id": "S2"},
            {"condition_id": "C3", "sample_id": "S1"},
        ],
    }
    out, warnings = bind_condition_sample_ids(entity)
    assert [c["sample_id"] for c in out["conditions"]] == ["S1", "S2", "S1"]
    assert warnings == []
