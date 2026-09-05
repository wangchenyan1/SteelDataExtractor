import time

from tools import batch_extract
from tools.llm_backends import ClaudeBackend
from tools.pipeline import RunCancelled, _raise_if_cancelled
from tools.workbench_server import handle_post, job_tracker


def setup_function():
    job_tracker.reset_jobs()


def test_backend_keeps_own_model(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    a = ClaudeBackend(tmp_path, model="Vendor2/A", base_url="http://a.example")
    b = ClaudeBackend(tmp_path, model="Vendor2/B", base_url="http://b.example")
    monkeypatch.setenv("LLM_MODEL", "Vendor2/ENV")
    captured = []

    class Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"content": [{"type": "text", "text": "{}"}], "stop_reason": "end_turn"}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.append((url, json["model"]))
        return Resp()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    a.call_json("s", "u")
    b.call_json("s", "u")
    assert captured == [("http://a.example", "Vendor2/A"), ("http://b.example", "Vendor2/B")]


def test_cancel_check_raises():
    state = {"cancel_check": lambda: True}
    try:
        _raise_if_cancelled(state)
        assert False, "should cancel"
    except RunCancelled:
        pass


def test_request_cancel_job_and_batch():
    batch = job_tracker.start_job(kind="batch", project_id="p", paper_id="2?")
    child = job_tracker.start_job(kind="run", project_id="p", paper_id="x", batch_id=batch)
    other = job_tracker.start_job(kind="run", project_id="p", paper_id="y")
    marked = job_tracker.request_cancel(batch)
    assert batch in marked
    assert child in marked
    assert other not in marked
    assert job_tracker.is_cancelled(child)
    assert not job_tracker.is_cancelled(other)


def test_finish_cancelled():
    jid = job_tracker.start_job(kind="run", project_id="p", paper_id="x")
    job_tracker.finish_job(jid, "cancelled", error="?????")
    jobs = job_tracker.list_jobs()
    assert jobs[0]["status"] == "cancelled"


def test_run_batch_api_and_workers(monkeypatch):
    seen = []

    def fake_run(root, project_id, paper_id, **kwargs):
        seen.append(paper_id)
        return {"run_id": "r_" + paper_id}

    monkeypatch.setattr(batch_extract.pipeline, "run_extraction", fake_run)
    status, data = handle_post(
        "/api/run_batch",
        {
            "project": "demo_steel",
            "paper_ids": ["p1", "p2"],
            "concurrency": 2,
        },
    )
    assert status == 200
    assert data["count"] == 2
    deadline = time.time() + 3
    while time.time() < deadline and len(seen) < 2:
        time.sleep(0.05)
    assert sorted(seen) == ["p1", "p2"]
    jobs = job_tracker.list_jobs()
    assert any(j["kind"] == "batch" for j in jobs)


def test_job_cancel_api():
    jid = job_tracker.start_job(kind="run", project_id="p", paper_id="x")
    status, data = handle_post("/api/job_cancel", {"job_id": jid})
    assert status == 200
    assert jid in data["cancelled"]
    assert job_tracker.is_cancelled(jid)


def test_ui_has_batch_and_cancel():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    html = (root / "app/index.html").read_text(encoding="utf-8")
    js = (root / "app/app.js").read_text(encoding="utf-8")
    assert 'id="btnCancelJobs"' in html
    assert "/api/run_batch" in js
    assert "/api/job_cancel" in js
