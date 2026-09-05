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
    # demo_steel overlay does not select permeability; do not regenerate steps
    steps = overlay.get("steps") or []
    types = [s["type"] for s in steps]
    assert types[0] == "entity"
    assert "property" in types
    assert "figure" not in types
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert "mechanical_properties" in groups
    assert "magnetic_properties" not in groups


def test_unselected_group_omits_step():
    overlay = cm.load_overlay(ROOT, "demo_steel")
    overlay = dict(overlay)
    overlay["selected_field_ids"] = [i for i in overlay["selected_field_ids"] if i != "permeability"]
    # 测自动生成：清除显式 steps，回退按 group 合成
    overlay["steps"] = None
    lib = cm.load_field_library(ROOT, "steel")
    fields = cm.effective_fields(lib, overlay)
    steps = cm.generate_steps(cm.load_template(ROOT, "steel"), fields, overlay)
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert "magnetic_properties" not in groups
    assert "mechanical_properties" in groups
    assert "figure" not in [s["type"] for s in steps]


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


def test_steel_library_has_seed_property_fields():
    lib = json.loads((ROOT / "configs/field_library/steel.json").read_text(encoding="utf-8"))
    ids = {f["id"] for f in lib["fields"]}
    assert {"hardness", "electrical_conductivity", "impact_toughness"} <= ids
    by_id = {f["id"]: f for f in lib["fields"]}
    assert by_id["hardness"]["group"] == "mechanical_properties"
    assert by_id["electrical_conductivity"]["group"] == "electrical_properties"
    assert by_id["impact_toughness"]["group"] == "impact_properties"
    assert "conductivity" not in ids
    tmpl = json.loads((ROOT / "configs/templates/steel.json").read_text(encoding="utf-8"))
    group_ids = [g["id"] for g in tmpl["property_groups"]]
    assert "electrical_properties" in group_ids
    assert group_ids == [
        "mechanical_properties",
        "magnetic_properties",
        "electrical_properties",
        "impact_properties",
        "corrosion_properties",
        "phase_stability",
    ]


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
    assert "title" in overlay["selected_field_ids"]
    assert "sample_id" in overlay["selected_field_ids"]
    assert "yield_strength" in overlay["selected_field_ids"]
    assert "condition_id" in overlay["selected_field_ids"]  # 库中存在则补锁定
    assert overlay.get("steps")
    assert overlay["steps"][0]["type"] == "entity"
    assert any(s.get("group") == "mechanical_properties" for s in overlay["steps"])
    cfg = json.loads((ws / "configs/project_config.json").read_text(encoding="utf-8"))
    assert cfg["projects"]["mini"]["backend"] == "mock"


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
    # lab_note 已提升出私有字段；save_overlay 会按文献类型补上 doi 标识
    assert not any(f.get("id") == "lab_note" for f in after["private_fields"])
    assert "lab_note" in after["selected_field_ids"]
    assert any(f.get("id") == "doi" for f in after["private_fields"])


def test_domain_projects_are_runnable_with_overlay():
    ws = json.loads((ROOT / "configs/project_config.json").read_text(encoding="utf-8"))
    for pid in ("non_magnetic", "nuclear_fusion", "cor_res", "cuti"):
        cfg = ws["projects"][pid]
        assert cfg.get("runnable") is True
        assert cfg.get("overlay")
        overlay = cm.load_overlay(ROOT, pid)
        assert overlay.get("steps")
        assert overlay["steps"][0]["type"] == "entity"
        assert not any(s.get("type") == "figure" for s in overlay["steps"])
        lib = cm.load_field_library(ROOT, overlay.get("template_id") or "steel")
        fields = cm.effective_fields(lib, overlay)
        cm.validate_overlay_stages(overlay, fields)
        assert fields


def test_save_overlay_normalizes_and_rejects_document_kind(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    overlay = json.loads((ROOT / "configs/projects/demo_steel.json").read_text(encoding="utf-8"))
    overlay.pop("document_kind", None)
    (ws / "configs/projects/demo_steel.json").write_text(
        json.dumps(overlay, ensure_ascii=False), encoding="utf-8"
    )
    cm.save_overlay(ws, "demo_steel", overlay)
    saved = cm.load_overlay(ws, "demo_steel")
    assert saved["document_kind"] == "paper"

    overlay["document_kind"] = "patent"
    cm.save_overlay(ws, "demo_steel", overlay)
    assert cm.load_overlay(ws, "demo_steel")["document_kind"] == "patent"

    overlay["document_kind"] = "book"
    with pytest.raises(ValueError, match="非法 document_kind"):
        cm.save_overlay(ws, "demo_steel", overlay)
    assert cm.load_overlay(ws, "demo_steel")["document_kind"] == "patent"


def test_create_project_defaults_document_kind_paper(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    (ws / "configs/project_config.json").write_text(
        json.dumps({"default_project": "demo_steel", "projects": {}}), encoding="utf-8"
    )
    cm.create_project(ws, "mini2", "力学子集", "steel", ["title", "sample_id", "yield_strength"])
    overlay = cm.load_overlay(ws, "mini2")
    assert overlay["document_kind"] == "paper"
    assert any(f.get("id") == "doi" for f in overlay.get("private_fields") or [])
    assert "doi" in overlay["selected_field_ids"]
