# -*- coding: utf-8 -*-
import json
from pathlib import Path

from tools.pipeline import delete_run, list_runs
from tools.workbench_server import handle_post

ROOT = Path(__file__).resolve().parents[1]


def _write_run(tmp_path: Path, paper_id: str, run_id: str):
    rd = tmp_path / "test" / run_id
    (rd / "merged_outputs").mkdir(parents=True)
    (rd / "merged_outputs" / "paper.json").write_text("{}", encoding="utf-8")
    (rd / "RUN_INFO.json").write_text(
        json.dumps({
            "run_id": run_id,
            "paper_id": paper_id,
            "mode": "two_stage",
            "partition": "test",
            "status": "success",
        }),
        encoding="utf-8",
    )
    return rd


def test_delete_run_removes_dir(tmp_path):
    paper_id = "p_del"
    run_id = "20260830_120000_two_stage"
    _write_run(tmp_path, paper_id, run_id)
    cfg = {"test_runs": str(tmp_path)}
    assert len(list_runs(ROOT, cfg, paper_id)) == 1
    out = delete_run(ROOT, cfg, paper_id, run_id)
    assert out["ok"] is True
    assert len(list_runs(ROOT, cfg, paper_id)) == 0
    assert not (tmp_path / "test" / run_id).exists()


def test_delete_run_rejects_wrong_paper(tmp_path):
    _write_run(tmp_path, "paper_a", "run_x")
    cfg = {"test_runs": str(tmp_path)}
    try:
        delete_run(ROOT, cfg, "paper_b", "run_x")
        assert False, "should raise"
    except FileNotFoundError:
        pass
    assert (tmp_path / "test" / "run_x").exists()


def test_run_delete_api_missing_params():
    status, data = handle_post("/api/run_delete", {})
    assert status == 400
    assert "error" in data


def test_run_delete_api_ok(monkeypatch):
    import tools.workbench_server as wb

    def fake(root, cfg, paper_id, run_id):
        return {
            "ok": True,
            "paper_id": paper_id,
            "run_id": run_id,
            "partition": "test",
            "deleted": "/tmp/x",
        }

    monkeypatch.setattr(wb.pipeline, "delete_run", fake)
    status, data = handle_post("/api/run_delete", {
        "project": "demo_steel",
        "paper_id": "p1",
        "run_id": "r1",
    })
    assert status == 200
    assert data["ok"] is True
    assert data["run_id"] == "r1"


def test_delete_button_in_review_ui():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    start = html.index('data-view-panel="review"')
    block = html[start: start + 2500]
    assert 'id="btnDeleteRun"' in block
    assert 'id="deleteRunStatus"' in block
    assert 'class="ghost danger"' in block
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "async function deleteSelectedRun" in js
    assert "/api/run_delete" in js
