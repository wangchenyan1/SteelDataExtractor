from tools import workbench_server as wb
from tools.workbench_server import handle_get

jt = wb.job_tracker


def setup_function():
    jt.reset_jobs()


def test_start_and_list_running():
    jid = jt.start_job(
        kind="run",
        project_id="cuti_patent",
        paper_id="CN123",
        mode="two_stage",
        model_id="claude-4.5-sonnet",
    )
    jobs = jt.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == jid
    assert jobs[0]["status"] == "running"
    assert jobs[0]["paper_id"] == "CN123"


def test_finish_success_and_failed_order():
    a = jt.start_job(kind="run", project_id="cuti", paper_id="p1")
    b = jt.start_job(kind="run", project_id="cuti_patent", paper_id="p2")
    jt.finish_job(a, "success", run_id="run_a")
    jobs = jt.list_jobs()
    assert jobs[0]["job_id"] == b
    assert jobs[0]["status"] == "running"
    assert jobs[1]["run_id"] == "run_a"
    jt.finish_job(b, "failed", error="LLM HTTP 404")
    jobs = jt.list_jobs()
    assert all(j["status"] != "running" for j in jobs)
    assert jobs[0]["job_id"] == b
    assert "404" in jobs[0]["error"]


def test_jobs_api():
    jt.start_job(kind="run", project_id="cuti", paper_id="x")
    status, data = handle_get("/api/jobs", {})
    assert status == 200
    assert data["jobs"]
    assert data["jobs"][0]["paper_id"] == "x"


def test_job_progress_in_ui():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/index.html").read_text(encoding="utf-8")
    assert 'id="jobProgress"' in html
    assert 'id="jobProgressBody"' in html
    js = (root / "app/app.js").read_text(encoding="utf-8")
    assert "/api/jobs" in js
    assert "function startJobPolling" in js
