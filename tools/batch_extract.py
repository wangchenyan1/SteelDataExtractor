"""Server-side batch extract with concurrency and cancel."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

_TOOLS = str(Path(__file__).resolve().parent)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import job_tracker
import pipeline

DEFAULT_CONCURRENCY = 2
MAX_CONCURRENCY = 8


def clamp_concurrency(n) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        v = DEFAULT_CONCURRENCY
    return max(1, min(MAX_CONCURRENCY, v))


def start_batch(
    root: Path,
    *,
    project_id: str,
    paper_ids: list[str],
    mode: str = "two_stage",
    partition: str = "test",
    model_id: str | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict:
    ids = [str(x).strip() for x in (paper_ids or []) if str(x).strip()]
    if not ids:
        raise ValueError("paper_ids required")
    conc = clamp_concurrency(concurrency)
    batch_id = job_tracker.start_job(
        kind="batch",
        project_id=project_id,
        paper_id=f"{len(ids)} papers",
        mode=mode,
        model_id=model_id or "",
    )
    thread = threading.Thread(
        target=_run_batch,
        kwargs={
            "root": Path(root),
            "batch_id": batch_id,
            "project_id": project_id,
            "paper_ids": ids,
            "mode": mode,
            "partition": partition,
            "model_id": model_id,
            "concurrency": conc,
        },
        daemon=True,
    )
    thread.start()
    return {
        "batch_id": batch_id,
        "paper_ids": ids,
        "concurrency": conc,
        "count": len(ids),
    }


def _run_batch(
    *,
    root: Path,
    batch_id: str,
    project_id: str,
    paper_ids: list[str],
    mode: str,
    partition: str,
    model_id: str | None,
    concurrency: int,
) -> None:
    sem = threading.Semaphore(concurrency)
    workers: list[threading.Thread] = []
    ok = 0
    fail = 0
    cancelled = 0
    lock = threading.Lock()

    def one(paper_id: str) -> None:
        nonlocal ok, fail, cancelled
        job_id = job_tracker.start_job(
            kind="run",
            project_id=project_id,
            paper_id=paper_id,
            mode=mode,
            model_id=model_id or "",
            batch_id=batch_id,
        )
        try:
            if job_tracker.is_cancelled(job_id):
                job_tracker.finish_job(job_id, "cancelled", error="cancelled")
                with lock:
                    cancelled += 1
                return
            out = pipeline.run_extraction(
                root,
                project_id,
                paper_id,
                mode=mode,
                partition=partition,
                model_id=model_id,
                cancel_check=lambda: job_tracker.is_cancelled(job_id),
            )
            job_tracker.finish_job(
                job_id,
                "success",
                run_id=out.get("run_id"),
                skeleton_done=True,
            )
            with lock:
                ok += 1
        except pipeline.RunCancelled as exc:
            job_tracker.finish_job(
                job_id,
                "cancelled",
                run_id=getattr(exc, "run_id", None),
                error=str(exc),
                skeleton_done=getattr(exc, "skeleton_done", None),
            )
            with lock:
                cancelled += 1
        except Exception as exc:
            job_tracker.finish_job(
                job_id,
                "failed",
                run_id=getattr(exc, "run_id", None),
                error=str(exc),
                skeleton_done=getattr(exc, "skeleton_done", None),
            )
            with lock:
                fail += 1
        finally:
            sem.release()

    try:
        for paper_id in paper_ids:
            if job_tracker.is_cancelled(batch_id):
                with lock:
                    cancelled += 1
                continue
            sem.acquire()
            t = threading.Thread(target=one, args=(paper_id,), daemon=True)
            workers.append(t)
            t.start()
        for t in workers:
            t.join()
        if job_tracker.is_cancelled(batch_id):
            job_tracker.finish_job(
                batch_id,
                "cancelled",
                error=f"cancelled ok={ok} fail={fail} skip={cancelled}",
            )
        elif fail:
            job_tracker.finish_job(
                batch_id,
                "failed",
                error=f"ok={ok} fail={fail} skip={cancelled}",
            )
        else:
            job_tracker.finish_job(batch_id, "success")
    except Exception as exc:
        job_tracker.finish_job(batch_id, "failed", error=str(exc))
