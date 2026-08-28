# tests/test_config_model.py
from pathlib import Path
import json
import shutil
import pytest
from tools import config_model as cm

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_demo_effective_fields_and_steps():
    overlay = cm.load_overlay(ROOT, "demo_steel")
    lib = cm.load_field_library(ROOT, "steel")
    fields = cm.effective_fields(lib, overlay)
    ids = [f["id"] for f in fields]
    assert "title" in ids
    assert "yield_strength" in ids
    assert "permeability" in ids
    tmpl = cm.load_template(ROOT, "steel")
    steps = cm.generate_steps(tmpl, fields, overlay)
    types = [s["type"] for s in steps]
    assert types[0] == "entity"
    assert "property" in types
    assert types[-1] == "figure"
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert "mechanical_properties" in groups
    assert "magnetic_properties" in groups


def test_unselected_group_omits_step():
    overlay = cm.load_overlay(ROOT, "demo_steel")
    overlay = dict(overlay)
    overlay["selected_field_ids"] = [i for i in overlay["selected_field_ids"] if i != "permeability"]
    lib = cm.load_field_library(ROOT, "steel")
    fields = cm.effective_fields(lib, overlay)
    steps = cm.generate_steps(cm.load_template(ROOT, "steel"), fields, overlay)
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert "magnetic_properties" not in groups
    assert "mechanical_properties" in groups


def test_overlay_does_not_write_library(tmp_path: Path):
    # copy steel library into tmp workspace layout
    ws = tmp_path
    (ws / "configs/field_library").mkdir(parents=True)
    (ws / "configs/projects").mkdir(parents=True)
    (ws / "configs/templates").mkdir(parents=True)
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    overlay = json.loads((ROOT / "configs/projects/demo_steel.json").read_text())
    overlay["field_overrides"] = {"title": {"rule": "PROJECT ONLY RULE"}}
    (ws / "configs/projects/demo_steel.json").write_text(json.dumps(overlay), encoding="utf-8")
    lib_before = (ws / "configs/field_library/steel.json").read_text()
    cm.save_overlay(ws, "demo_steel", overlay)
    assert (ws / "configs/field_library/steel.json").read_text() == lib_before
    fields = cm.effective_fields(cm.load_field_library(ws, "steel"), cm.load_overlay(ws, "demo_steel"))
    title = next(f for f in fields if f["id"] == "title")
    assert title["rule"] == "PROJECT ONLY RULE"


def test_writeback_updates_library(tmp_path: Path):
    ws = tmp_path
    (ws / "configs/field_library").mkdir(parents=True)
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    cm.writeback_library_field(ws, "steel", {"id": "title", "rule": "NEW LIB RULE", "label": "文献名称",
                                            "category": "metadata", "group": None, "value_type": "string",
                                            "positive_examples": "", "negative_examples": "", "note": ""})
    lib = cm.load_field_library(ws, "steel")
    title = next(f for f in lib["fields"] if f["id"] == "title")
    assert title["rule"] == "NEW LIB RULE"


def test_blank_library_is_empty():
    lib = cm.load_field_library(ROOT, "blank")
    assert lib["fields"] == []


def test_create_project_selects_subset(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    (ws / "configs/project_config.json").write_text(json.dumps({
        "default_project": "demo_steel", "projects": {}
    }), encoding="utf-8")
    cm.create_project(ws, "mini", "力学子集", "steel", ["title", "sample_id", "yield_strength"])
    overlay = cm.load_overlay(ws, "mini")
    assert overlay["selected_field_ids"] == ["title", "sample_id", "yield_strength"]
    steps = cm.generate_steps(cm.load_template(ws, "steel"),
                              cm.effective_fields(cm.load_field_library(ws, "steel"), overlay), overlay)
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert groups == ["mechanical_properties"]


def _private_field(field_id: str = "custom_note") -> dict:
    return {
        "id": field_id,
        "label": "自定义备注",
        "category": "metadata",
        "group": None,
        "value_type": "string",
        "rule": "提取备注",
        "positive_examples": "",
        "negative_examples": "",
        "note": "",
    }


def test_promote_private_field_blank_raises(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/blank.json", ws / "configs/templates/blank.json")
    private = _private_field()
    overlay = {
        "template_id": "blank",
        "selected_field_ids": [],
        "private_fields": [private],
        "field_overrides": {},
        "step_overrides": None,
        "property_source": {},
        "figure_filter": {},
    }
    (ws / "configs/projects/blank_proj.json").write_text(
        json.dumps(overlay, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="空模板没有公共字段库"):
        cm.promote_private_field(ws, "blank_proj", private["id"])
    after = cm.load_overlay(ws, "blank_proj")
    assert after["private_fields"] == [private]
    assert after["selected_field_ids"] == []
    assert not (ws / "configs/field_library/blank.json").exists()


def test_promote_private_field_steel(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    private = _private_field("lab_note")
    overlay = {
        "template_id": "steel",
        "selected_field_ids": ["title"],
        "private_fields": [private],
        "field_overrides": {},
        "step_overrides": None,
        "property_source": {},
        "figure_filter": {},
    }
    (ws / "configs/projects/steel_proj.json").write_text(
        json.dumps(overlay, ensure_ascii=False), encoding="utf-8"
    )
    cm.promote_private_field(ws, "steel_proj", private["id"])
    lib = cm.load_field_library(ws, "steel")
    promoted = next(f for f in lib["fields"] if f["id"] == private["id"])
    assert promoted["label"] == private["label"]
    after = cm.load_overlay(ws, "steel_proj")
    assert after["private_fields"] == []
    assert "lab_note" in after["selected_field_ids"]
