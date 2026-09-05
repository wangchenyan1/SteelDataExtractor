#!/usr/bin/env python3
"""材料文献抽取工作台后端。

职责：
- 静态服务 app/ 下的前端 demo；
- 提供项目/字段/规则、文献列表、原文、试跑（两阶段抽取）、结果 review 等 API；
- 所有运行结果写入 test_runs/<project>/<test|data>/<run_id>/，绝不写远端 Extract_data。

启动：
    python3 tools/workbench_server.py --host 127.0.0.1 --port 8787
命令行试跑一篇：
    python3 tools/workbench_server.py --run-once --project demo_steel \
        --paper-id 10.1007_s11665-019-04233-6 --mode two_stage --partition test
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import batch_extract  # noqa: E402
import config_model  # noqa: E402
import job_tracker  # noqa: E402
import pdf_parser  # noqa: E402
import pipeline  # noqa: E402
import result_analysis  # noqa: E402
from llm_backends import _load_env  # noqa: E402

_load_env(ROOT)


STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class BinaryBody:
    """Non-JSON GET payload (PDF / images)."""

    __slots__ = ("data", "content_type")

    def __init__(self, data: bytes, content_type: str):
        self.data = data
        self.content_type = content_type


def _is_safe_paper_id(paper_id: str) -> bool:
    """Reject empty, ., .., and paper_id values with path separators."""
    if not paper_id or paper_id in (".", ".."):
        return False
    return Path(paper_id).name == paper_id


def resolve_paper_image_path(
    root: Path, project_id: str, paper_id: str, name: str
) -> Path | None:
    """Resolve basename under images_from_md/; reject path traversal."""
    if not _is_safe_paper_id(paper_id):
        return None
    if not name or Path(name).name != name:
        return None
    try:
        cfg = pipeline.load_workspace_config(root)["projects"].get(project_id)
        if not cfg:
            return None
        parsed = pipeline._resolve_parsed_dir(root, cfg)
        if not parsed:
            return None
        parsed_root = parsed.resolve()
        images_dir = (parsed / paper_id / "images_from_md").resolve()
        if not images_dir.is_relative_to(parsed_root):
            return None
        candidate = (images_dir / name).resolve()
        if not candidate.is_relative_to(images_dir):
            return None
        if not candidate.is_file():
            return None
        return candidate
    except (OSError, ValueError, KeyError):
        return None


def resolve_paper_pdf_path(root: Path, project_id: str, paper_id: str) -> Path | None:
    if not _is_safe_paper_id(paper_id):
        return None
    try:
        cfg = pipeline.load_workspace_config(root)["projects"].get(project_id)
        if not cfg:
            return None
        parsed = pipeline._resolve_parsed_dir(root, cfg)
        if not parsed:
            return None
        parsed_root = parsed.resolve()
        paper_dir = (parsed / paper_id).resolve()
        if not paper_dir.is_relative_to(parsed_root):
            return None
        for fname in ("source.pdf", f"{paper_id}.pdf"):
            p = paper_dir / fname
            if p.is_file():
                return p
        return None
    except (OSError, ValueError, KeyError):
        return None


def paper_meta(root: Path, project_id: str, paper_id: str) -> dict | None:
    if not _is_safe_paper_id(paper_id):
        return None
    try:
        cfg = pipeline.load_workspace_config(root)["projects"].get(project_id)
        if not cfg:
            return None
        parsed = pipeline._resolve_parsed_dir(root, cfg)
        if not parsed:
            return None
        parsed_root = parsed.resolve()
        paper_dir = (parsed / paper_id).resolve()
        if not paper_dir.is_relative_to(parsed_root):
            return None
        if not paper_dir.is_dir():
            return None
        images_dir = paper_dir / "images_from_md"
        image_names: list[str] = []
        md_path = paper_dir / "paper.md"
        has_md = md_path.is_file()
        if has_md:
            text = md_path.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"(?:images_from_md/)([^)\s\"']+)", text):
                name = Path(m.group(1)).name
                if name and name not in image_names:
                    image_names.append(name)
        if images_dir.is_dir() and not image_names:
            image_names = sorted(
                p.name for p in images_dir.iterdir() if p.is_file()
            )
        has_pdf = resolve_paper_pdf_path(root, project_id, paper_id) is not None
        return {
            "paper_id": paper_id,
            "has_pdf": has_pdf,
            "has_md": has_md,
            "image_count": len(image_names),
            "images": image_names,
        }
    except (OSError, ValueError, KeyError):
        return None


def _parse_bool_qs(val, default: bool = True) -> bool:
    if val is None:
        return default
    return str(val).lower() not in ("0", "false", "no", "")


try:
    from input_trim import normalize_document_kind
except ImportError:
    from tools.input_trim import normalize_document_kind


def _project_document_kind(project_id: str, cfg: dict) -> str:
    if not cfg.get("overlay"):
        return "paper"
    try:
        overlay = config_model.load_overlay(ROOT, project_id)
        return normalize_document_kind(overlay.get("document_kind"))
    except Exception:
        return "paper"


def build_projects_payload() -> dict:
    ws = pipeline.load_workspace_config(ROOT)
    projects = {}
    for pid, cfg in ws.get("projects", {}).items():
        field_config = pipeline.load_field_config(ROOT, cfg)
        projects[pid] = {
            "id": pid,
            "name": cfg.get("name", pid),
            "description": cfg.get("description", ""),
            "runnable": cfg.get("runnable", True),
            "backend": cfg.get("backend", "claude"),
            "stages": cfg.get("stages", []),
            "steps": field_config.get("steps", []),
            "fields": field_config.get("fields", {}),
            "rules": field_config.get("rules", {}),
            "property_source": field_config.get("property_source", {}),
            "figure_filter": field_config.get("figure_filter", {}),
            "papers": pipeline.list_paper_records(ROOT, cfg),
            "document_kind": _project_document_kind(pid, cfg),
        }
    return {
        "default_project": ws.get("default_project"),
        "models": ws.get("models", []),
        "projects": projects,
    }


def latest_result(project_id: str, paper_id: str, run_id: str | None = None) -> dict | None:
    ws = pipeline.load_workspace_config(ROOT)
    cfg = ws["projects"].get(project_id)
    if not cfg:
        return None
    runs = pipeline.list_runs(ROOT, cfg, paper_id)
    if not runs:
        return None
    target = next((r for r in runs if r["run_id"] == run_id), runs[0]) if run_id else runs[0]
    base = ROOT / cfg.get("test_runs", "") / target["partition"] / target["run_id"]
    paper_json = base / "merged_outputs" / "paper.json"
    warnings_path = base / "review_notes" / "validation_warnings.json"
    if not paper_json.exists():
        return None
    result = json.loads(paper_json.read_text(encoding="utf-8"))
    warnings = []
    if warnings_path.exists():
        warnings = json.loads(warnings_path.read_text(encoding="utf-8"))
    # 加载时按 is_microstructure_image / is_post_test_image 重判，不改写磁盘 paper.json
    # （磁盘里可能仍残留旧的「不在组织图白名单」文案）
    field_config = pipeline.load_field_config(ROOT, cfg)
    figures = result.get("figures") or []
    ff = (field_config.get("figure_filter") or {})
    if figures and (ff.get("require_microstructure") or ff.get("drop_if_post_test")):
        reclassed, fig_warnings = pipeline.classify_figures(
            figures, field_config, apply_filter=True
        )
        result = {**result, "figures": reclassed}
        warnings = [w for w in warnings if w.get("type") != "figure_dropped"]
        warnings.extend(fig_warnings)
    return {"run_info": target, "result": result, "warnings": warnings}


def _q(qs: dict, name: str, default=None):
    return qs.get(name, [default])[0]


def _project_cfg(project_id: str) -> dict:
    ws = pipeline.load_workspace_config(ROOT)
    cfg = ws["projects"].get(project_id)
    if not cfg:
        raise ValueError(f"未知项目: {project_id}")
    return cfg


def _parsed_dir(cfg: dict) -> Path:
    rel = cfg.get("parsed_results")
    if not rel:
        raise ValueError("项目未配置 parsed_results")
    return ROOT / rel


def _ensure_source_and_parse(
    project_id: str,
    *,
    pdf_path: str | Path | None = None,
    paper_id: str | None = None,
    overwrite: bool = False,
    pdf_bytes: bytes | None = None,
    pdf_filename: str | None = None,
) -> dict:
    """Copy source.pdf into parsed dir and call parse_pdf_to_paper."""
    cfg = _project_cfg(project_id)
    parsed_dir = _parsed_dir(cfg)

    if pdf_bytes is not None:
        name = pdf_filename or "upload.pdf"
        pid = paper_id or Path(name).stem
        paper_dir = parsed_dir / pid
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / "source.pdf").write_bytes(pdf_bytes)
        parse_src = paper_dir / f"{pid}.pdf"
        parse_src.write_bytes(pdf_bytes)
        return pdf_parser.parse_pdf_to_paper(parse_src, parsed_dir, overwrite=overwrite)

    if pdf_path:
        src = Path(pdf_path)
        if not src.exists():
            raise FileNotFoundError(f"PDF 不存在: {src}")
        pid = paper_id or src.stem
        paper_dir = parsed_dir / pid
        paper_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, paper_dir / "source.pdf")
        parse_src = paper_dir / f"{pid}.pdf"
        if src.resolve() != parse_src.resolve():
            shutil.copy2(src, parse_src)
        return pdf_parser.parse_pdf_to_paper(parse_src, parsed_dir, overwrite=overwrite)

    if paper_id:
        paper_dir = parsed_dir / paper_id
        source = paper_dir / "source.pdf"
        if not source.exists():
            raise FileNotFoundError(f"未找到 PDF：请提供 pdf_path 或上传文件（期望 {source}）")
        parse_src = paper_dir / f"{paper_id}.pdf"
        if not parse_src.exists():
            shutil.copy2(source, parse_src)
        return pdf_parser.parse_pdf_to_paper(parse_src, parsed_dir, overwrite=overwrite)

    raise ValueError("parse 需要 pdf_path、上传文件或已有 source.pdf + paper_id")


def _maybe_parse_before_run(body: dict) -> dict | None:
    """If paper.md missing and pdf available, parse first. Returns parse info or None."""
    project_id = body.get("project", "")
    paper_id = body.get("paper_id", "")
    if not project_id or not paper_id:
        return None
    cfg = _project_cfg(project_id)
    parsed_dir = _parsed_dir(cfg)
    paper_md = parsed_dir / paper_id / "paper.md"
    if paper_md.exists() and not body.get("overwrite_parse"):
        return None
    pdf_path = body.get("pdf_path")
    source = parsed_dir / paper_id / "source.pdf"
    if pdf_path or source.exists():
        return _ensure_source_and_parse(
            project_id,
            pdf_path=pdf_path,
            paper_id=paper_id,
            overwrite=bool(body.get("overwrite_parse") or body.get("overwrite")),
        )
    return None


def _run_payload(out: dict) -> dict:
    return {
        "run_id": out["run_id"],
        "run_dir": out["run_dir"],
        "run_info": out["run_info"],
        "result": out["result"],
        "entity": out["entity"],
        "property_groups": out["property_groups"],
        "figures": out["figures"],
        "warnings": out["warnings"],
        "trim_stats": out["trim_stats"],
        "steps": out["steps"],
        "prompts": out["prompts"],
        "resumed": bool(out.get("resumed")),
        "skipped_steps": out.get("skipped_steps") or [],
    }


def handle_get(route: str, qs: dict) -> tuple[int, dict | BinaryBody]:
    """Route GET API; returns (status, json_body | BinaryBody)."""
    parts = route.strip("/").split("/")

    if route == "/api/health":
        return 200, {"status": "ok", "root": str(ROOT)}
    if route == "/api/jobs":
        return 200, {"jobs": job_tracker.list_jobs()}
    if route == "/api/projects":
        return 200, build_projects_payload()
    if route == "/api/papers":
        cfg = pipeline.load_workspace_config(ROOT)["projects"].get(_q(qs, "project"), {})
        return 200, {"papers": pipeline.list_paper_records(ROOT, cfg)}
    if route == "/api/paper_text":
        cfg = pipeline.load_workspace_config(ROOT)["projects"].get(_q(qs, "project"), {})
        text = pipeline.get_paper_text(ROOT, cfg, _q(qs, "paper_id", ""))
        if text is None:
            return 404, {"error": "paper.md 未找到，请先上传 PDF 并解析"}
        return 200, {"paper_id": _q(qs, "paper_id"), "text": text}
    if route == "/api/paper_meta":
        project_id = _q(qs, "project", "")
        paper_id = _q(qs, "paper_id", "")
        meta = paper_meta(ROOT, project_id, paper_id)
        if meta is None:
            return 404, {"error": "paper 未找到"}
        return 200, meta
    if route == "/api/paper_pdf":
        project_id = _q(qs, "project", "")
        paper_id = _q(qs, "paper_id", "")
        pdf = resolve_paper_pdf_path(ROOT, project_id, paper_id)
        if pdf is None:
            return 404, {"error": "PDF 未找到"}
        return 200, BinaryBody(pdf.read_bytes(), "application/pdf")
    if route == "/api/paper_image":
        project_id = _q(qs, "project", "")
        paper_id = _q(qs, "paper_id", "")
        name = _q(qs, "name", "")
        img = resolve_paper_image_path(ROOT, project_id, paper_id, name)
        if img is None:
            return 404, {"error": "image 未找到或路径非法"}
        ctype = STATIC_TYPES.get(img.suffix.lower(), "application/octet-stream")
        return 200, BinaryBody(img.read_bytes(), ctype)
    if route == "/api/runs":
        cfg = pipeline.load_workspace_config(ROOT)["projects"].get(_q(qs, "project"), {})
        return 200, {"runs": pipeline.list_runs(ROOT, cfg, _q(qs, "paper_id"))}
    if route == "/api/run_artifacts":
        project_id = _q(qs, "project", "")
        paper_id = _q(qs, "paper_id", "")
        run_id = _q(qs, "run_id", "")
        if not project_id or not paper_id or not run_id:
            return 400, {"error": "需要 project、paper_id 与 run_id"}
        try:
            cfg = _project_cfg(project_id)
            return 200, pipeline.get_run_artifacts(ROOT, cfg, paper_id, run_id)
        except ValueError as exc:
            return 400, {"error": str(exc)}
        except FileNotFoundError as exc:
            return 404, {"error": str(exc)}
    if route == "/api/result":
        res = latest_result(_q(qs, "project", ""), _q(qs, "paper_id", ""), _q(qs, "run_id"))
        if res is None:
            return 404, {"error": "暂无运行结果，请先试跑"}
        return 200, res
    if route == "/api/analyze_list":
        project_id = _q(qs, "project", "")
        paper_id = _q(qs, "paper_id", "")
        if not project_id or not paper_id:
            return 400, {"error": "需要 project 与 paper_id"}
        try:
            cfg = _project_cfg(project_id)
        except ValueError as exc:
            return 404, {"error": str(exc)}
        dirs = result_analysis.run_dirs_for_paper(
            ROOT, cfg, paper_id, run_id=_q(qs, "run_id")
        )
        return 200, {"analyses": result_analysis.list_analyses_under_runs(dirs)}
    if route == "/api/analyze":
        project_id = _q(qs, "project", "")
        paper_id = _q(qs, "paper_id", "")
        analysis_id = _q(qs, "analysis_id", "")
        if not project_id or not paper_id or not analysis_id:
            return 400, {"error": "需要 project、paper_id 与 analysis_id"}
        try:
            cfg = _project_cfg(project_id)
        except ValueError as exc:
            return 404, {"error": str(exc)}
        found = result_analysis.find_analysis(
            result_analysis.run_dirs_for_paper(ROOT, cfg, paper_id), analysis_id
        )
        if found is None:
            return 404, {"error": "分析记录未找到"}
        return 200, found
    if route == "/api/field_library":
        template = _q(qs, "template", "steel")
        return 200, config_model.load_field_library(ROOT, template)
    if route == "/api/project_config":
        project_id = _q(qs, "project", "")
        return 200, config_model.load_overlay(ROOT, project_id)

    # /api/projects/<id>/config|export|export_results
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "projects":
        project_id, action = parts[2], parts[3]
        if action == "export":
            return 200, config_model.export_project(ROOT, project_id)
        if action == "export_results":
            include_rejected = _parse_bool_qs(_q(qs, "include_rejected"), default=True)
            paper_id = _q(qs, "paper_id")
            paper_ids_raw = _q(qs, "paper_ids") or ""
            paper_ids = [
                x.strip()
                for x in paper_ids_raw.split(",")
                if x.strip() and _is_safe_paper_id(x.strip())
            ]
            try:
                cfg = _project_cfg(project_id)
            except ValueError as exc:
                return 404, {"error": str(exc)}
            if paper_id and not paper_ids:
                paper_ids = [paper_id]
            if paper_ids:
                items = []
                for pid in paper_ids:
                    res = latest_result(project_id, pid)
                    if res is None:
                        continue
                    items.append({
                        "paper_id": pid,
                        "run_info": res["run_info"],
                        "result": pipeline.filter_result_by_status(
                            res["result"], include_rejected=include_rejected
                        ),
                        "warnings": res["warnings"],
                    })
                if not items:
                    return 404, {"error": "所选文献暂无运行结果"}
                if len(items) == 1:
                    one = items[0]
                    return 200, {
                        "project_id": project_id,
                        "paper_id": one["paper_id"],
                        "run_info": one["run_info"],
                        "result": one["result"],
                        "warnings": one["warnings"],
                    }
                return 200, {"project_id": project_id, "results": items}
            papers = pipeline.list_papers(ROOT, cfg)
            items = []
            for pid in papers:
                res = latest_result(project_id, pid)
                if res is None:
                    continue
                items.append({
                    "paper_id": pid,
                    "run_info": res["run_info"],
                    "result": pipeline.filter_result_by_status(
                        res["result"], include_rejected=include_rejected
                    ),
                    "warnings": res["warnings"],
                })
            return 200, {"project_id": project_id, "results": items}
        if action == "config":
            return 200, config_model.load_overlay(ROOT, project_id)

    return 404, {"error": "not found", "route": route}


def handle_post(route: str, body: dict, files: dict | None = None) -> tuple[int, dict]:
    """Route POST API; returns (status, json_body).

    files: optional multipart map, e.g. {"pdf": {"filename": "...", "content": b"..."}}
    """
    files = files or {}
    parts = route.strip("/").split("/")

    try:
        if route == "/api/projects":
            try:
                overlay = config_model.create_project(
                    ROOT,
                    body.get("id", ""),
                    body.get("name", ""),
                    body.get("template_id", "steel"),
                    body.get("selected_field_ids") or [],
                    document_kind=body.get("document_kind"),
                    copy_from=body.get("copy_from"),
                )
            except ValueError as exc:
                return 400, {"error": str(exc)}
            return 200, {"ok": True, "overlay": overlay, "id": body.get("id")}

        if route == "/api/parse":
            pdf_info = files.get("pdf")
            result = _ensure_source_and_parse(
                body.get("project", ""),
                pdf_path=body.get("pdf_path"),
                paper_id=body.get("paper_id"),
                overwrite=bool(body.get("overwrite", False)),
                pdf_bytes=pdf_info.get("content") if pdf_info else None,
                pdf_filename=pdf_info.get("filename") if pdf_info else None,
            )
            return 200, result

        if route == "/api/run":
            job_id = job_tracker.start_job(
                kind="run",
                project_id=body.get("project", ""),
                paper_id=body.get("paper_id", ""),
                mode=body.get("mode", "two_stage"),
                model_id=body.get("model_id") or "",
            )
            try:
                parse_info = _maybe_parse_before_run(body)
                out = pipeline.run_extraction(
                    ROOT,
                    body.get("project", ""),
                    body.get("paper_id", ""),
                    mode=body.get("mode", "two_stage"),
                    partition=body.get("partition", "test"),
                    model_id=body.get("model_id"),
                    run_id=body.get("run_id") or None,
                    force_new=bool(body.get("force_new")),
                    cancel_check=lambda: job_tracker.is_cancelled(job_id),
                )
                payload = _run_payload(out)
                if parse_info is not None:
                    payload["parse"] = parse_info
                job_tracker.finish_job(
                    job_id, "success",
                    run_id=payload.get("run_id"),
                    skeleton_done=True,
                )
                return 200, payload
            except pipeline.RunCancelled as exc:
                job_tracker.finish_job(
                    job_id, "cancelled",
                    run_id=getattr(exc, "run_id", None),
                    error=str(exc),
                    skeleton_done=getattr(exc, "skeleton_done", None),
                )
                return 200, {"ok": False, "cancelled": True, "error": str(exc)}
            except Exception as exc:
                job_tracker.finish_job(
                    job_id, "failed",
                    run_id=getattr(exc, "run_id", None),
                    error=str(exc),
                    skeleton_done=getattr(exc, "skeleton_done", None),
                )
                raise

        if route == "/api/run_batch":
            try:
                out = batch_extract.start_batch(
                    ROOT,
                    project_id=body.get("project", ""),
                    paper_ids=body.get("paper_ids") or [],
                    mode=body.get("mode", "two_stage"),
                    partition=body.get("partition", "test"),
                    model_id=body.get("model_id"),
                    concurrency=body.get("concurrency") or batch_extract.DEFAULT_CONCURRENCY,
                )
            except ValueError as exc:
                return 400, {"error": str(exc)}
            return 200, out

        if route == "/api/job_cancel":
            marked = job_tracker.request_cancel(body.get("job_id") or None)
            return 200, {"ok": True, "cancelled": marked}

        if route == "/api/run_step":
            job_id = job_tracker.start_job(
                kind="run_step",
                project_id=body.get("project", ""),
                paper_id=body.get("paper_id", ""),
                mode="",
                model_id=body.get("model_id") or "",
                step_id=body.get("step_id") or "",
            )
            try:
                out = pipeline.run_step(
                    ROOT,
                    body.get("project", ""),
                    body.get("paper_id", ""),
                    body.get("step_id", ""),
                    run_id=body.get("run_id"),
                    partition=body.get("partition", "test"),
                    model_id=body.get("model_id"),
                    cancel_check=lambda: job_tracker.is_cancelled(job_id),
                )
                payload = _run_payload(out)
                payload["step"] = out.get("step")
                payload["invalidated"] = out.get("invalidated", [])
                job_tracker.finish_job(
                    job_id, "success",
                    run_id=payload.get("run_id"),
                    skeleton_done=True,
                )
                return 200, payload
            except pipeline.RunCancelled as exc:
                job_tracker.finish_job(
                    job_id, "cancelled",
                    run_id=getattr(exc, "run_id", None),
                    error=str(exc),
                    skeleton_done=getattr(exc, "skeleton_done", None),
                )
                return 200, {"ok": False, "cancelled": True, "error": str(exc)}
            except Exception as exc:
                job_tracker.finish_job(
                    job_id, "failed",
                    run_id=getattr(exc, "run_id", None),
                    error=str(exc),
                    skeleton_done=getattr(exc, "skeleton_done", None),
                )
                raise

        if route == "/api/analyze":
            project_id = body.get("project") or ""
            paper_id = body.get("paper_id") or ""
            analysis_type = body.get("analysis_type") or ""
            if not project_id or not paper_id:
                return 400, {"error": "需要 project 与 paper_id"}
            if analysis_type not in ("vs_source", "vs_runs"):
                return 400, {"error": "analysis_type 须为 vs_source 或 vs_runs"}
            try:
                cfg = _project_cfg(project_id)
            except ValueError as exc:
                return 404, {"error": str(exc)}
            try:
                out = result_analysis.run_analysis(
                    root=ROOT,
                    project_cfg=cfg,
                    project_id=project_id,
                    paper_id=paper_id,
                    analysis_type=analysis_type,
                    run_id=body.get("run_id") or None,
                    run_id_a=body.get("run_id_a") or None,
                    run_id_b=body.get("run_id_b") or None,
                    model_id=body.get("model_id") or None,
                    focuses=body.get("focuses"),
                    custom_focus=body.get("custom_focus"),
                )
            except ValueError as exc:
                return 400, {"error": str(exc)}
            except FileNotFoundError as exc:
                return 404, {"error": str(exc)}
            return 200, out

        if route == "/api/run_delete":
            project_id = body.get("project") or ""
            paper_id = body.get("paper_id") or ""
            run_id = body.get("run_id") or ""
            if not project_id or not paper_id or not run_id:
                return 400, {"error": "需要 project、paper_id 与 run_id"}
            try:
                cfg = _project_cfg(project_id)
            except ValueError as exc:
                return 404, {"error": str(exc)}
            try:
                out = pipeline.delete_run(ROOT, cfg, paper_id, run_id)
            except ValueError as exc:
                return 400, {"error": str(exc)}
            except FileNotFoundError as exc:
                return 404, {"error": str(exc)}
            return 200, out

        if route == "/api/paper_delete":
            project_id = body.get("project") or ""
            paper_id = body.get("paper_id") or ""
            if not project_id or not paper_id:
                return 400, {"error": "需要 project 与 paper_id"}
            try:
                cfg = _project_cfg(project_id)
            except ValueError as exc:
                return 404, {"error": str(exc)}
            try:
                out = pipeline.delete_paper(ROOT, cfg, paper_id)
            except ValueError as exc:
                return 400, {"error": str(exc)}
            except FileNotFoundError as exc:
                return 404, {"error": str(exc)}
            return 200, out

        if route == "/api/project_delete":
            project_id = body.get("project") or body.get("project_id") or ""
            if not project_id:
                return 400, {"error": "需要 project"}
            try:
                out = config_model.delete_project(ROOT, project_id)
            except ValueError as exc:
                return 400, {"error": str(exc)}
            except FileNotFoundError as exc:
                return 404, {"error": str(exc)}
            return 200, out

        if route == "/api/reextract":
            out = pipeline.reextract_field(
                ROOT,
                body.get("project", ""),
                body.get("field_id", ""),
                paper_id=body.get("paper_id"),
                scope=body.get("scope"),
                partition=body.get("partition", "test"),
                model_id=body.get("model_id"),
            )
            return 200, out

        if route == "/api/field_library/writeback":
            config_model.writeback_library_field(
                ROOT, body.get("template_id", ""), body.get("field") or {}
            )
            return 200, {"ok": True}

        if route == "/api/field_library/promote":
            overlay = config_model.promote_private_field(
                ROOT, body.get("project", ""), body.get("field_id", "")
            )
            return 200, {"ok": True, "overlay": overlay}

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "projects" and parts[3] == "export":
            return 200, config_model.export_project(ROOT, parts[2])

    except Exception as exc:  # noqa: BLE001
        return 500, {"error": str(exc)}

    return 404, {"error": "not found", "route": route}


def handle_put(route: str, body: dict, qs: dict | None = None) -> tuple[int, dict]:
    """Route PUT API (project config overlay)."""
    qs = qs or {}
    parts = route.strip("/").split("/")
    try:
        if route == "/api/project_config":
            project_id = _q(qs, "project", "") or body.get("project", "")
            config_model.save_overlay(ROOT, project_id, body)
            return 200, {"ok": True}

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "projects" and parts[3] == "config":
            config_model.save_overlay(ROOT, parts[2], body)
            return 200, {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return 500, {"error": str(exc)}

    return 404, {"error": "not found", "route": route}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: N802
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_static(self, path: Path):
        if not path.exists() or not path.is_file():
            self._send_json({"error": "not found", "path": str(path)}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw)

    def _read_multipart(self) -> tuple[dict, dict]:
        """Return (form_fields_as_dict, files_map). Minimal parser (no cgi)."""
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        m = re.search(r"boundary=([^;]+)", ctype, re.I)
        if not m:
            return {}, {}
        boundary = m.group(1).strip().strip('"').encode("ascii", errors="ignore")
        body: dict = {}
        files: dict = {}
        for part in raw.split(b"--" + boundary):
            if not part or part in (b"--\r\n", b"--", b"--\n"):
                continue
            if part.startswith(b"--"):
                continue
            if part.startswith(b"\r\n"):
                part = part[2:]
            elif part.startswith(b"\n"):
                part = part[1:]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            elif part.endswith(b"\n"):
                part = part[:-1]
            header_blob, _, content = part.partition(b"\r\n\r\n")
            if not _:
                header_blob, _, content = part.partition(b"\n\n")
            headers = header_blob.decode("utf-8", errors="replace")
            name_m = re.search(r'name="([^"]+)"', headers)
            if not name_m:
                continue
            name = name_m.group(1)
            fname_m = re.search(r'filename="([^"]*)"', headers)
            if fname_m is not None:
                files[name] = {"filename": fname_m.group(1), "content": content}
            else:
                val = content.decode("utf-8", errors="replace")
                if name == "overwrite":
                    body[name] = val.lower() in ("1", "true", "yes")
                else:
                    try:
                        body[name] = json.loads(val)
                    except (TypeError, json.JSONDecodeError):
                        body[name] = val
        return body, files

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if route.startswith("/api/"):
                status, data = handle_get(route, qs)
                if isinstance(data, BinaryBody):
                    return self._send_bytes(data.data, data.content_type, status)
                return self._send_json(data, status)
            rel = route.lstrip("/") or "index.html"
            return self._send_static(APP_DIR / rel)
        except Exception as exc:  # noqa: BLE001
            return self._send_json({"error": str(exc)}, 500)

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        ctype = self.headers.get("Content-Type", "")
        try:
            if "multipart/form-data" in ctype:
                body, files = self._read_multipart()
            else:
                try:
                    body = self._read_json_body()
                except json.JSONDecodeError:
                    return self._send_json({"error": "invalid json body"}, 400)
                files = None
            status, data = handle_post(route, body, files=files)
            return self._send_json(data, status)
        except Exception as exc:  # noqa: BLE001
            return self._send_json({"error": str(exc)}, 500)

    def do_PUT(self):  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        qs = parse_qs(parsed.query)
        try:
            try:
                body = self._read_json_body()
            except json.JSONDecodeError:
                return self._send_json({"error": "invalid json body"}, 400)
            status, data = handle_put(route, body, qs=qs)
            return self._send_json(data, status)
        except Exception as exc:  # noqa: BLE001
            return self._send_json({"error": str(exc)}, 500)


def run_once(args) -> int:
    out = pipeline.run_extraction(
        ROOT, args.project, args.paper_id, mode=args.mode, partition=args.partition
    )
    print(json.dumps(out["run_info"], ensure_ascii=False, indent=2))
    print(f"\n结果目录: {out['run_dir']}")
    if out["warnings"]:
        print(f"\n规则校验命中 {len(out['warnings'])} 项：")
        for w in out["warnings"]:
            print(f"  - {w.get('detail')}")
    return 0


def export_fields_schema(args) -> int:
    data = config_model.export_project(ROOT, args.project)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def parse_only(args) -> int:
    if not args.pdf:
        print("--parse-only 需要 --pdf PATH", file=sys.stderr)
        return 2
    result = _ensure_source_and_parse(
        args.project,
        pdf_path=args.pdf,
        paper_id=args.paper_id,
        overwrite=args.overwrite_parse,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_step_cli(args) -> int:
    out = pipeline.run_step(
        ROOT,
        args.project,
        args.paper_id,
        args.step,
        partition=args.partition,
        model_id=None,
    )
    print(json.dumps({
        "run_id": out["run_id"],
        "step": out["step"],
        "invalidated": out.get("invalidated", []),
        "run_dir": out["run_dir"],
    }, ensure_ascii=False, indent=2))
    return 0


def reextract_cli(args) -> int:
    out = pipeline.reextract_field(
        ROOT,
        args.project,
        args.reextract_field,
        paper_id=args.paper_id,
        partition=args.partition,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="材料文献抽取工作台后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--run-once", action="store_true", help="命令行试跑一篇，不启动服务")
    parser.add_argument("--project", default="demo_steel")
    parser.add_argument("--paper-id", default=None)
    parser.add_argument("--mode", default="two_stage",
                        choices=["two_stage", "entity_only", "single_pass"])
    parser.add_argument("--partition", default="test", choices=["test", "data"])
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument("--pdf", default=None)
    parser.add_argument("--step", default=None)
    parser.add_argument("--reextract-field", default=None)
    parser.add_argument("--export-fields-schema", action="store_true")
    parser.add_argument("--overwrite-parse", action="store_true")
    args = parser.parse_args()

    # 互斥优先级：export > parse-only > reextract-field > step > run-once
    if args.export_fields_schema:
        return export_fields_schema(args)
    if args.parse_only:
        return parse_only(args)
    if args.reextract_field:
        return reextract_cli(args)
    if args.step:
        if not args.paper_id:
            parser.error("--step 需要 --paper-id")
        return run_step_cli(args)
    if args.run_once:
        if not args.paper_id:
            parser.error("--run-once 需要 --paper-id")
        return run_once(args)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"工作台已启动: http://{args.host}:{args.port}")
    print(f"工作区根目录: {ROOT}")
    print("Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
