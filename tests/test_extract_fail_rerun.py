from pathlib import Path
import json

from tools.pipeline import (
    _write_failed_run,
    list_paper_records,
    load_workspace_config,
    _paper_extract_status,
)

ROOT = Path(__file__).resolve().parents[1]


def test_write_failed_run_marks_status():
    ws = load_workspace_config(ROOT)
    cfg = ws["projects"]["demo_steel"]
    run_dir = ROOT / cfg["test_runs"] / "test" / "_unit_failed_run_marker"
    if run_dir.exists():
        import shutil
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    state = {
        "run_dir": run_dir,
        "run_id": "_unit_failed_run_marker",
        "project_id": "demo_steel",
        "paper_id": "10.1007_s11665-019-04233-6",
        "mode": "two_stage",
        "partition": "test",
        "backend": type("B", (), {"name": "fake"})(),
        "completed_steps": [],
        "invalidated_steps": [],
        "parse_skipped": True,
        "warnings": [],
        "entity": {"samples": [], "conditions": []},
    }
    _write_failed_run(state, RuntimeError("unit boom"))
    info = json.loads((run_dir / "RUN_INFO.json").read_text(encoding="utf-8"))
    assert info["status"] == "failed"
    assert "unit boom" in info["error"]
    # cleanup so it does not pollute paper status forever as "latest"
    import shutil
    shutil.rmtree(run_dir)


def test_list_records_expose_extract_status():
    ws = load_workspace_config(ROOT)
    cfg = ws["projects"]["demo_steel"]
    recs = list_paper_records(ROOT, cfg)
    rec = next(r for r in recs if r["paper_id"] == "10.1007_s11665-019-04233-6")
    assert "extract_status" in rec
    assert rec["extract_status"] in ("success", "failed", "none")


def test_ui_has_rerun_and_failed_label():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert ">操作<" in html
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "async function rerunPaper" in js
    assert "抽取失败" in js
    assert "重新抽取" in js
    assert "extract_status" in js
