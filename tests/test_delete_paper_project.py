# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

from tools import config_model
from tools.pipeline import delete_paper, list_runs
from tools.workbench_server import handle_post

ROOT = Path(__file__).resolve().parents[1]


def _write_run(runs_root: Path, paper_id: str, run_id: str):
    rd = runs_root / "test" / run_id
    (rd / "merged_outputs").mkdir(parents=True)
    (rd / "merged_outputs" / "paper.json").write_text("{}", encoding="utf-8")
    (rd / "RUN_INFO.json").write_text(
        json.dumps({
            "run_id": run_id,
            "paper_id": paper_id,
            "mode": "two_stage",
            "partition": "test",
            "status": "failed",
        }),
        encoding="utf-8",
    )
    return rd


def test_delete_paper_removes_parsed_and_runs(tmp_path: Path):
    parsed = tmp_path / "parsed"
    runs = tmp_path / "runs"
    paper_id = "smoke_lit_x"
    paper_dir = parsed / paper_id
    paper_dir.mkdir(parents=True)
    (paper_dir / "paper.md").write_text("# t", encoding="utf-8")
    _write_run(runs, paper_id, "20260903_r1")
    _write_run(runs, "other", "20260903_keep")
    cfg = {"parsed_results": str(parsed), "test_runs": str(runs)}

    out = delete_paper(ROOT, cfg, paper_id)
    assert out["ok"] is True
    assert out["paper_id"] == paper_id
    assert out["deleted_parsed"]
    assert len(out["deleted_runs"]) == 1
    assert not paper_dir.exists()
    assert len(list_runs(ROOT, cfg, paper_id)) == 0
    assert (runs / "test" / "20260903_keep").exists()


def test_delete_paper_rejects_path_escape(tmp_path: Path):
    cfg = {"parsed_results": str(tmp_path / "parsed"), "test_runs": str(tmp_path / "runs")}
    (tmp_path / "parsed").mkdir()
    with pytest.raises(ValueError, match="paper_id"):
        delete_paper(ROOT, cfg, "../outside")


def test_delete_project_removes_config_and_dirs(tmp_path: Path):
    cfg_path = tmp_path / "configs" / "project_config.json"
    cfg_path.parent.mkdir(parents=True)
    overlay_path = tmp_path / "configs" / "projects" / "tmp_del.json"
    overlay_path.parent.mkdir(parents=True)
    overlay_path.write_text('{"template_id":"steel","selected_field_ids":[]}', encoding="utf-8")
    parsed = tmp_path / "parsed_results" / "tmp_del"
    runs = tmp_path / "test_runs" / "tmp_del"
    parsed.mkdir(parents=True)
    runs.mkdir(parents=True)
    (parsed / "p1").mkdir()
    cfg_path.write_text(
        json.dumps({
            "default_project": "demo_steel",
            "projects": {
                "demo_steel": {"name": "??", "parsed_results": "example_data/x"},
                "tmp_del": {
                    "name": "??",
                    "overlay": "configs/projects/tmp_del.json",
                    "field_config": "configs/projects/tmp_del.json",
                    "parsed_results": "parsed_results/tmp_del",
                    "test_runs": "test_runs/tmp_del",
                },
            },
        }),
        encoding="utf-8",
    )

    out = config_model.delete_project(tmp_path, "tmp_del")
    assert out["ok"] is True
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "tmp_del" not in cfg["projects"]
    assert "demo_steel" in cfg["projects"]
    assert not overlay_path.exists()
    assert not parsed.exists()
    assert not runs.exists()


def test_delete_project_rejects_demo_steel(tmp_path: Path):
    cfg_path = tmp_path / "configs" / "project_config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        json.dumps({"projects": {"demo_steel": {"name": "??"}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        config_model.delete_project(tmp_path, "demo_steel")
    assert "demo_steel" in json.loads(cfg_path.read_text(encoding="utf-8"))["projects"]


def test_paper_delete_api_ok(monkeypatch):
    import tools.workbench_server as wb

    monkeypatch.setattr(
        wb.pipeline,
        "delete_paper",
        lambda root, cfg, paper_id: {
            "ok": True,
            "paper_id": paper_id,
            "deleted_parsed": "/tmp/p",
            "deleted_runs": [],
        },
    )
    status, data = handle_post("/api/paper_delete", {
        "project": "non_magnetic",
        "paper_id": "p1",
    })
    assert status == 200
    assert data["ok"] is True
    assert data["paper_id"] == "p1"


def test_project_delete_api_missing():
    status, data = handle_post("/api/project_delete", {})
    assert status == 400
    assert "error" in data


def test_project_delete_api_ok(monkeypatch):
    import tools.workbench_server as wb

    monkeypatch.setattr(
        wb.config_model,
        "delete_project",
        lambda root, project_id: {"ok": True, "project_id": project_id, "deleted": []},
    )
    status, data = handle_post("/api/project_delete", {"project": "tmp_x"})
    assert status == 200
    assert data["ok"] is True
    assert data["project_id"] == "tmp_x"


def test_ui_has_delete_controls():
    html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "app" / "app.js").read_text(encoding="utf-8")
    assert 'id="btnDeleteProject"' in html
    assert "paper-delete-btn" in js
    assert "/api/paper_delete" in js
    assert "/api/project_delete" in js
