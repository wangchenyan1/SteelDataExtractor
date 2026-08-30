# tests/test_config_stages.py
import pytest
from tools.config_model import (
    generate_steps,
    strip_empty_property_steps,
    validate_overlay_stages,
)

TEMPLATE = {
    "property_groups": [
        {"id": "mechanical_properties", "name": "力学性能"},
        {"id": "magnetic_properties", "name": "磁性能"},
    ],
    "identity_fields": ["sample_id", "condition_id"],
}


def test_overlay_steps_win_over_groups():
    fields = [
        {"id": "yield_strength", "category": "property", "group": "mechanical_properties"},
        {"id": "permeability", "category": "property", "group": "magnetic_properties"},
        {"id": "electrical_conductivity", "category": "property", "group": "conductivity_properties"},
    ]
    overlay = {
        "steps": [
            {"id": "entity", "type": "entity", "name": "骨架"},
            {"id": "mechanical", "type": "property", "name": "力学性能",
             "group": "mechanical_properties", "fields": ["yield_strength"]},
            {"id": "conductivity", "type": "property", "name": "电导性能",
             "group": "conductivity_properties", "fields": ["electrical_conductivity"]},
        ]
    }
    steps = generate_steps(TEMPLATE, fields, overlay)
    assert [s["id"] for s in steps] == ["entity", "mechanical", "conductivity"]
    assert not any(s.get("type") == "figure" for s in steps)


def test_auto_generate_omits_figure_step():
    fields = [
        {"id": "yield_strength", "category": "property", "group": "mechanical_properties"},
        {"id": "figure_id", "category": "figure", "group": None},
    ]
    steps = generate_steps(TEMPLATE, fields, {})
    assert not any(s.get("type") == "figure" for s in steps)


def test_validate_rejects_unassigned_property_field():
    fields = [
        {"id": "yield_strength", "category": "property", "group": "mechanical_properties"},
        {"id": "permeability", "category": "property", "group": "magnetic_properties"},
    ]
    overlay = {
        "selected_field_ids": ["yield_strength", "permeability"],
        "steps": [
            {"id": "entity", "type": "entity", "name": "骨架"},
            {"id": "mechanical", "type": "property", "name": "力学性能",
             "fields": ["yield_strength"]},
        ],
    }
    with pytest.raises(ValueError, match="未挂阶段"):
        validate_overlay_stages(overlay, fields)


def test_strip_empty_property_steps():
    steps = [
        {"id": "entity", "type": "entity", "name": "骨架"},
        {"id": "mechanical", "type": "property", "name": "力学性能", "fields": ["yield_strength"]},
        {"id": "empty", "type": "property", "name": "空", "fields": []},
    ]
    out = strip_empty_property_steps(steps)
    assert [s["id"] for s in out] == ["entity", "mechanical"]


def test_validate_allows_after_empty_stripped():
    fields = [{"id": "yield_strength", "category": "property", "group": "mechanical_properties"}]
    overlay = {
        "steps": [
            {"id": "entity", "type": "entity", "name": "骨架"},
            {"id": "mechanical", "type": "property", "name": "力学性能", "fields": ["yield_strength"]},
            {"id": "empty", "type": "property", "name": "空", "fields": []},
        ]
    }
    validate_overlay_stages(overlay, fields)
    assert [s["id"] for s in overlay["steps"]] == ["entity", "mechanical"]


from tools.config_model import assign_property_to_stage

NAMES = {"mechanical_properties": "力学性能", "electrical_properties": "电性能"}


def test_assign_creates_named_stage():
    field = {"id": "yield_strength", "category": "property", "group": "mechanical_properties"}
    stages = assign_property_to_stage([], field, NAMES)
    assert stages == [{
        "id": "mechanical", "type": "property", "name": "力学性能",
        "group": "mechanical_properties", "fields": ["yield_strength"],
    }]


def test_assign_same_group_reuses_stage():
    field1 = {"id": "yield_strength", "category": "property", "group": "mechanical_properties"}
    field2 = {"id": "tensile_strength", "category": "property", "group": "mechanical_properties"}
    stages = assign_property_to_stage([], field1, NAMES)
    stages = assign_property_to_stage(stages, field2, NAMES)
    assert len(stages) == 1
    assert stages[0]["fields"] == ["yield_strength", "tensile_strength"]


def test_assign_follows_existing_same_group_stage_even_if_renamed():
    stages = [{
        "id": "tensile", "type": "property", "name": "拉伸",
        "group": "mechanical_properties", "fields": ["yield_strength"],
    }]
    field = {"id": "tensile_strength", "category": "property", "group": "mechanical_properties"}
    out = assign_property_to_stage(stages, field, NAMES)
    assert len(out) == 1
    assert out[0]["name"] == "拉伸"
    assert "tensile_strength" in out[0]["fields"]


def test_merged_property_groups_appends_overlay():
    from tools.config_model import merged_property_groups
    template = {"property_groups": [{"id": "mechanical_properties", "name": "力学性能"}]}
    overlay = {"property_groups": [{"id": "fatigue_properties", "name": "疲劳性能"}]}
    ids = [g["id"] for g in merged_property_groups(template, overlay)]
    assert ids == ["mechanical_properties", "fatigue_properties"]


def test_generate_steps_includes_overlay_group():
    from tools.config_model import generate_steps
    template = {"property_groups": [{"id": "mechanical_properties", "name": "力学性能"}]}
    fields = [{"id": "fatigue_limit", "category": "property", "group": "fatigue_properties"}]
    overlay = {"property_groups": [{"id": "fatigue_properties", "name": "疲劳性能"}]}
    steps = generate_steps(template, fields, overlay)
    assert [s["id"] for s in steps if s["type"] == "property"] == ["fatigue"]
    assert steps[-1]["name"] == "疲劳性能"
