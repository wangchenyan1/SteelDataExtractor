# tests/test_config_stages.py
import pytest
from tools.config_model import generate_steps, validate_overlay_stages

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
