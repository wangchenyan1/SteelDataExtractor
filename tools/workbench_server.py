#!/usr/bin/env python3
"""材料文献抽取工作台后端。

职责：
- 静态服务 app/ 下的前端 demo；
- 提供项目/字段/规则、文献列表、原文、试跑（两阶段抽取）、结果 review 等 API；
- 所有运行结果写入 test_runs/<project>/<test|data>/<run_id>/，绝不写远端 Extract_data。

启动：
    python3 tools/workbench_server.py --host 127.0.0.1 --port 8787
命令行试跑一篇（无需页面/网络，用内置样例）：
    python3 tools/workbench_server.py --run-once --project demo_steel \
        --paper-id demo_steel_2024 --mode two_stage --partition test
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

import config_model  # noqa: E402
import pdf_parser  # noqa: E402
import pipeline  # noqa: E402


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


def resolve_paper_image_path(
    root: Path, project_id: str, paper_id: str, name: str
) -> Path | None:
    """Resolve basename under images_from_md/; reject path traversal."""
    if not name or Path(name).name != name:
        return None
    try:
        cfg = pipeline.load_workspace_config(root)["projects"].get(project_id)
        if not cfg:
            return None
        parsed = pipeline._resolve_parsed_dir(root, cfg)
        if not parsed:
            return None
        images_dir = (parsed / paper_id / "images_from_md").resolve()
        candidate = (images_dir / name).resolve()
        if not candidate.is_relative_to(images_dir):
            return None
        if not candidate.is_file():
            return None
        return candidate
    except (OSError, ValueError, KeyError):
        return None


def resolve_paper_pdf_path(root: Path, project_id: str, paper_id: str) -> Path | None:
    try:
        cfg = pipeline.load_workspace_config(root)["projects"].get(project_id)
        if not cfg:
            return None
        parsed = pipeline._resolve_parsed_dir(root, cfg)
        if not parsed:
            return None
        paper_dir = parsed / paper_id
        for fname in ("source.pdf", f"{paper_id}.pdf"):
            p = paper_dir / fname
            if p.is_file():
                return p
        return None
    except (OSError, ValueError, KeyError):
        return None


def paper_meta(root: Path, project_id: str, paper_id: str) -> dict | None:
    try:
        cfg = pipeline.load_workspace_config(root)["projects"].get(project_id)
        if not cfg:
            return None
        parsed = pipeline._resolve_parsed_dir(root, cfg)
        if not parsed:
            return None
        paper_dir = parsed / paper_id
        if not paper_dir.is_dir():
            return None
        images_dir = paper_dir / "images_from_md"
        image_count = 0
        if images_dir.is_dir():
            image_count = sum(1 for p in images_dir.iterdir() if p.is_file())
        has_pdf = resolve_paper_pdf_path(root, project_id, paper_id) is not None
        has_md = (paper_dir / "paper.md").is_file()
        return {
            "paper_id": paper_id,
            "has_pdf": has_pdf,
            "has_md": has_md,
            "image_count": image_count,
        }
    except (OSError, ValueError, KeyError):
        return None


def _parse_bool_qs(val, default: bool = True) -> bool:
    if val is None:
        return default
    return str(val).lower() not in ("0", "false", "no", "")


def build_projects_payload() -> dict:
    ws = pipeline.load_workspace_config(ROOT)
    projects = {}
    for pid, cfg in ws.get("projects", {}).items():
        field_config = pipeline.load_field_config(ROOT, cfg)
        projects[pid] = {
            "id": pid,
            "name": cfg.get("name", pid),
            "description": cfg.get("description", ""),
            "runnable": cfg.get("runnable", False),
            "backend": cfg.get("backend", "mock"),
            "stages": cfg.get("stages", []),
            "steps": field_config.get("steps", []),
            "fields": field_config.get("fields", {}),
            "rules": field_config.get("rules", {}),
            "property_source": field_config.get("property_source", {}),
            "figure_filter": field_config.get("figure_filter", {}),
            "papers": pipeline.list_papers(ROOT, cfg),
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
    }


def handle_get(route: str, qs: dict) -> tuple[int, dict | BinaryBody]:
    """Route GET API; returns (status, json_body | BinaryBody)."""
    parts = route.strip("/").split("/")

    if route == "/api/health":
        return 200, {"status": "ok", "root": str(ROOT)}
    if route == "/api/projects":
        return 200, build_projects_payload()
    if route == "/api/papers":
        cfg = pipeline.load_workspace_config(ROOT)["projects"].get(_q(qs, "project"), {})
        return 200, {"papers": pipeline.list_papers(ROOT, cfg)}
    if route == "/api/paper_text":
        cfg = pipeline.load_workspace_config(ROOT)["projects"].get(_q(qs, "project"), {})
        text = pipeline.get_paper_text(ROOT, cfg, _q(qs, "paper_id", ""))
        if text is None:
            return 404, {"error": "paper.md 未找到（该项目可能是只读快照，本地无原文）"}
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
    if route == "/api/result":
        res = latest_result(_q(qs, "project", ""), _q(qs, "paper_id", ""), _q(qs, "run_id"))
        if res is None:
            return 404, {"error": "暂无运行结果，请先试跑"}
        return 200, res
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
            try:
                cfg = _project_cfg(project_id)
            except ValueError as exc:
                return 404, {"error": str(exc)}
            if paper_id:
                res = latest_result(project_id, paper_id)
                if res is None:
                    return 404, {"error": "暂无运行结果"}
                return 200, {
                    "project_id": project_id,
                    "paper_id": paper_id,
                    "run_info": res["run_info"],
                    "result": pipeline.filter_result_by_status(
                        res["result"], include_rejected=include_rejected
                    ),
                    "warnings": res["warnings"],
                }
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
            overlay = config_model.create_project(
                ROOT,
                body.get("id", ""),
                body.get("name", ""),
                body.get("template_id", "steel"),
                body.get("selected_field_ids") or [],
            )
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
            parse_info = _maybe_parse_before_run(body)
            out = pipeline.run_extraction(
                ROOT,
                body.get("project", ""),
                body.get("paper_id", ""),
                mode=body.get("mode", "two_stage"),
                partition=body.get("partition", "test"),
                model_id=body.get("model_id"),
            )
            payload = _run_payload(out)
            if parse_info is not None:
                payload["parse"] = parse_info
            return 200, payload

        if route == "/api/run_step":
            out = pipeline.run_step(
                ROOT,
                body.get("project", ""),
                body.get("paper_id", ""),
                body.get("step_id", ""),
                run_id=body.get("run_id"),
                partition=body.get("partition", "test"),
                model_id=body.get("model_id"),
            )
            payload = _run_payload(out)
            payload["step"] = out.get("step")
            payload["invalidated"] = out.get("invalidated", [])
            return 200, payload

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
        paper_id=None if args.paper_id == "demo_steel_2024" else args.paper_id,
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
    parser.add_argument("--paper-id", default="demo_steel_2024")
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
        return run_step_cli(args)
    if args.run_once:
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
