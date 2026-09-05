# -*- coding: utf-8 -*-
import json
import shutil
from pathlib import Path

import pytest

from tools import config_model as cm
from tools.workbench_server import handle_post

ROOT = Path(__file__).resolve().parents[1]


def _mini_ws(tmp_path: Path) -> Path:
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    (ws / "configs/project_config.json").write_text(
        json.dumps({"default_project": "demo_steel", "projects": {}}), encoding="utf-8"
    )
    return ws


def test_apply_document_kind_identifier_paper_and_patent():
    overlay = {
        "document_kind": "paper",
        "selected_field_ids": ["title", "yield_strength"],
        "private_fields": [],
        "field_overrides": {"patent_number": {"rule": "x"}},
    }
    cm.apply_document_kind_identifier(overlay)
    ids = {f["id"] for f in overlay["private_fields"]}
    assert "doi" in ids
    assert "patent_number" not in ids
    assert "doi" in overlay["selected_field_ids"]
    assert "patent_number" not in overlay["selected_field_ids"]
    assert "patent_number" not in overlay["field_overrides"]

    overlay["document_kind"] = "patent"
    overlay["private_fields"] = [{
        "id": "doi",
        "label": "DOI",
        "category": "metadata",
        "rule": "custom doi rule",
        "value_type": "string",
    }]
    cm.apply_document_kind_identifier(overlay)
    ids = {f["id"] for f in overlay["private_fields"]}
    assert "patent_number" in ids
    assert "doi" not in ids
    assert "patent_number" in overlay["selected_field_ids"]


def test_apply_keeps_custom_doi_rule():
    overlay = {
        "document_kind": "paper",
        "selected_field_ids": ["title"],
        "private_fields": [{
            "id": "doi",
            "label": "DOI",
            "category": "metadata",
            "rule": "my custom doi",
            "value_type": "string",
        }],
        "field_overrides": {},
    }
    cm.apply_document_kind_identifier(overlay)
    doi = next(f for f in overlay["private_fields"] if f["id"] == "doi")
    assert doi["rule"] == "my custom doi"


def test_create_project_patent_no_copy(tmp_path: Path):
    ws = _mini_ws(tmp_path)
    out = cm.create_project(
        ws, "pat1", "patent proj", "steel",
        ["title", "sample_id", "yield_strength"],
        document_kind="patent",
    )
    assert out["document_kind"] == "patent"
    private_ids = {f["id"] for f in out["private_fields"]}
    assert "patent_number" in private_ids
    assert "doi" not in private_ids


def test_create_project_defaults_paper_with_doi(tmp_path: Path):
    ws = _mini_ws(tmp_path)
    out = cm.create_project(
        ws, "paper1", "paper proj", "steel",
        ["title", "sample_id", "yield_strength"],
    )
    assert out["document_kind"] == "paper"
    private_ids = {f["id"] for f in out["private_fields"]}
    assert "doi" in private_ids
    assert "patent_number" not in private_ids


def test_create_project_copy_from_switches_kind(tmp_path: Path):
    ws = _mini_ws(tmp_path)
    src = cm.create_project(
        ws, "src_cuti", "src paper", "steel",
        ["title", "sample_id", "yield_strength", "elongation"],
        document_kind="paper",
    )
    src_steps = json.loads(json.dumps(src["steps"]))
    src_ps = json.loads(json.dumps(src.get("property_source") or {}))

    out = cm.create_project(
        ws, "dst_pat", "dst patent", "blank",
        ["title"],
        document_kind="patent",
        copy_from="src_cuti",
    )
    assert out["document_kind"] == "patent"
    assert out["template_id"] == "steel"
    assert out["steps"] == src_steps
    assert out.get("property_source") == src_ps
    private_ids = {f["id"] for f in out["private_fields"]}
    assert "patent_number" in private_ids
    assert "doi" not in private_ids
    src_after = cm.load_overlay(ws, "src_cuti")
    assert src_after["document_kind"] == "paper"
    assert any(f.get("id") == "doi" for f in src_after["private_fields"])
    assert not (ws / "parsed_results" / "src_cuti").exists()
    assert not (ws / "parsed_results" / "dst_pat").exists()


def test_create_project_copy_missing_raises(tmp_path: Path):
    ws = _mini_ws(tmp_path)
    with pytest.raises(ValueError) as ei:
        cm.create_project(
            ws, "x", "x", "steel", ["title"],
            document_kind="patent", copy_from="no_such",
        )
    assert "no_such" in str(ei.value)
    assert not (ws / "configs/projects/x.json").exists()


def test_save_overlay_swaps_identifier(tmp_path: Path):
    ws = _mini_ws(tmp_path)
    cm.create_project(ws, "sw", "swap", "steel", ["title", "sample_id", "yield_strength"])
    overlay = cm.load_overlay(ws, "sw")
    assert any(f.get("id") == "doi" for f in overlay["private_fields"])
    overlay["document_kind"] = "patent"
    cm.save_overlay(ws, "sw", overlay)
    saved = cm.load_overlay(ws, "sw")
    ids = {f["id"] for f in saved["private_fields"]}
    assert "patent_number" in ids
    assert "doi" not in ids


def test_api_projects_passes_kind_and_copy(monkeypatch):
    import tools.workbench_server as wb

    captured = {}

    def fake(root, project_id, name, template_id, selected_field_ids,
             document_kind=None, copy_from=None):
        captured.update({
            "id": project_id,
            "document_kind": document_kind,
            "copy_from": copy_from,
            "template_id": template_id,
        })
        return {"document_kind": document_kind or "paper", "private_fields": []}

    monkeypatch.setattr(wb.config_model, "create_project", fake)
    status, data = handle_post("/api/projects", {
        "id": "n1",
        "name": "N1",
        "template_id": "steel",
        "selected_field_ids": ["title"],
        "document_kind": "patent",
        "copy_from": "cuti",
    })
    assert status == 200
    assert data["ok"] is True
    assert captured["document_kind"] == "patent"
    assert captured["copy_from"] == "cuti"


def test_new_project_dialog_has_kind_and_copy_controls():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert 'id="newProjectDocumentKind"' in html
    assert 'id="newProjectCopyFrom"' in html
    assert 'value="paper"' in html
    assert 'value="patent"' in html
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "document_kind" in js
    assert "copy_from" in js
    assert "async function saveNewProject" in js
    assert "function syncNewProjectCopyUI" in js
