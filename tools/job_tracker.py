"""进程内抽取任务表：进度、取消、批量父子关系。"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_MAX_FINISHED = 40
_SEQ = 0
_DONE = frozenset({"success", "failed", "cancelled"})


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def start_job(
    *,
    kind: str,
    project_id: str,
    paper_id: str,
    mode: str = "",
    model_id: str = "",
    step_id: str = "",
    batch_id: str = "",
) -> str:
    global _SEQ
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _SEQ += 1
        seq = _SEQ
    rec = {
        "job_id": job_id,
        "seq": seq,
        "kind": kind or "run",
        "project_id": project_id or "",
        "paper_id": paper_id or "",
        "mode": mode or "",
        "model_id": model_id or "",
        "step_id": step_id or "",
        "batch_id": batch_id or "",
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "run_id": None,
        "error": None,
        "skeleton_done": None,
        "cancel_requested": False,
    }
    with _LOCK:
        _JOBS[job_id] = rec
    return job_id


def finish_job(
    job_id: str,
    status: str,
    *,
    run_id: str | None = None,
    error: str | None = None,
    skeleton_done: bool | None = None,
) -> None:
    if not job_id:
        return
    with _LOCK:
        rec = _JOBS.get(job_id)
        if not rec:
            return
        rec["status"] = status if status in _DONE else "failed"
        rec["finished_at"] = _now()
        if run_id:
            rec["run_id"] = run_id
        if error:
            rec["error"] = str(error)[:500]
        if skeleton_done is not None:
            rec["skeleton_done"] = bool(skeleton_done)
        _trim_finished_locked()


def is_cancelled(job_id: str | None) -> bool:
    if not job_id:
        return False
    with _LOCK:
        rec = _JOBS.get(job_id)
        if not rec:
            return False
        if rec.get("cancel_requested") or rec.get("status") == "cancelled":
            return True
        batch_id = rec.get("batch_id") or ""
        if batch_id and batch_id != job_id:
            parent = _JOBS.get(batch_id)
            if parent and (parent.get("cancel_requested") or parent.get("status") == "cancelled"):
                return True
        return False


def request_cancel(job_id: str | None = None) -> list[str]:
    """取消指定任务；batch 会连同子任务；job_id 为空则取消全部进行中。"""
    marked: list[str] = []
    with _LOCK:
        targets = []
        if job_id:
            rec = _JOBS.get(job_id)
            if rec:
                targets.append(rec)
                if rec.get("kind") == "batch":
                    for child in _JOBS.values():
                        if child.get("batch_id") == job_id and child is not rec:
                            targets.append(child)
        else:
            targets = [j for j in _JOBS.values() if j.get("status") == "running"]
        for rec in targets:
            rec["cancel_requested"] = True
            marked.append(rec["job_id"])
    return marked


def _trim_finished_locked() -> None:
    done = [j for j in _JOBS.values() if j.get("status") != "running"]
    if len(done) <= _MAX_FINISHED:
        return
    done.sort(key=lambda j: j.get("finished_at") or "")
    for old in done[: len(done) - _MAX_FINISHED]:
        _JOBS.pop(old["job_id"], None)


def list_jobs() -> list[dict]:
    with _LOCK:
        items = [dict(j) for j in _JOBS.values()]
    running = [j for j in items if j.get("status") == "running"]
    done = [j for j in items if j.get("status") != "running"]
    running.sort(key=lambda j: j.get("seq") or 0, reverse=True)
    done.sort(key=lambda j: j.get("seq") or 0, reverse=True)
    return running + done


def reset_jobs() -> None:
    """Clear in-memory jobs (tests)."""
    global _SEQ
    with _LOCK:
        _JOBS.clear()
        _SEQ = 0
