"""抽取结果 LLM 分析：三类焦点（数值绑定 / 工艺 / 图片），结构化落盘。"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_compare import diff_results  # noqa: E402

FOCUS_ORDER = ("value_binding", "process_binding", "figure_judgment")
VALID_FOCUS = set(FOCUS_ORDER)
VALID_SEVERITY = {"high", "medium", "low"}
MAX_ISSUES = 12

_PROCESS_KEYS = re.compile(
    r"(process|processing|heat_treat|anneal|age|aging|roll|temper|solution|"
    r"quench|冷轧|时效|退火|固溶|淬火|工艺|加工|热处理|condition_name|"
    r"processing_overview|microstructure_overview)",
    re.I,
)
_VALUE_KEYS = re.compile(
    r"(composition|strength|hardness|elongation|conductivity|yield|tensile|"
    r"modulus|strain|stress|property|成分|强度|硬度|延伸|电导)",
    re.I,
)


def _slot(v: Any) -> Any:
    if isinstance(v, dict) and "value" in v:
        return v.get("value")
    return v


def _compact_fact(v: Any) -> Any:
    if not isinstance(v, dict):
        return v
    if "value" in v or "excerpt" in v:
        out = {"value": v.get("value")}
        if v.get("unit"):
            out["unit"] = v.get("unit")
        if v.get("status"):
            out["status"] = v.get("status")
        return out
    return {k: _compact_fact(x) for k, x in v.items() if not str(k).startswith("_")}


def slice_result_for_analysis(result: dict | None) -> dict:
    """裁成三块：数值绑定 / 工艺 / 图片，控制 token。"""
    r = result or {}
    values: dict[str, Any] = {"samples": [], "conditions": []}
    process: dict[str, Any] = {"samples": [], "conditions": []}

    for s in r.get("samples") or []:
        if not isinstance(s, dict):
            continue
        sid = _slot(s.get("sample_id"))
        v_row: dict[str, Any] = {"sample_id": sid}
        p_row: dict[str, Any] = {"sample_id": sid}
        for k, val in s.items():
            if k == "sample_id":
                continue
            if _PROCESS_KEYS.search(k):
                p_row[k] = _compact_fact(val)
            elif _VALUE_KEYS.search(k) or k == "composition":
                v_row[k] = _compact_fact(val)
            elif k not in ("figures",):
                # 未知文本偏工艺，未知数值组偏数值
                if isinstance(val, str) or (
                    isinstance(val, dict) and isinstance(val.get("value"), str)
                    and not _VALUE_KEYS.search(k)
                ):
                    if len(str(_slot(val) or "")) > 20 or _PROCESS_KEYS.search(k):
                        p_row[k] = _compact_fact(val)
                    else:
                        v_row[k] = _compact_fact(val)
                else:
                    v_row[k] = _compact_fact(val)
        if len(v_row) > 1:
            values["samples"].append(v_row)
        if len(p_row) > 1:
            process["samples"].append(p_row)

    for c in r.get("conditions") or []:
        if not isinstance(c, dict):
            continue
        cid = _slot(c.get("condition_id"))
        sid = _slot(c.get("sample_id"))
        v_row = {"condition_id": cid, "sample_id": sid}
        p_row = {"condition_id": cid, "sample_id": sid}
        for k, val in c.items():
            if k in ("condition_id", "sample_id"):
                continue
            if k.endswith("_properties") or _VALUE_KEYS.search(k):
                v_row[k] = _compact_fact(val)
            elif _PROCESS_KEYS.search(k):
                p_row[k] = _compact_fact(val)
            else:
                # 状态名等
                if isinstance(val, (str, dict)):
                    p_row[k] = _compact_fact(val)
        if len(v_row) > 2:
            values["conditions"].append(v_row)
        if len(p_row) > 2:
            process["conditions"].append(p_row)

    figures = []
    for f in r.get("figures") or []:
        if not isinstance(f, dict):
            continue
        keep = {
            "figure_id": _slot(f.get("figure_id")),
            "figure_type": _compact_fact(f.get("figure_type")),
            "is_microstructure_image": _compact_fact(f.get("is_microstructure_image")),
            "is_post_test_image": _compact_fact(f.get("is_post_test_image")),
            "status": f.get("status"),
            "reject_reason": f.get("reject_reason"),
        }
        for k in ("caption", "figure_caption", "image_purpose", "description", "图注"):
            if k in f:
                keep[k] = _compact_fact(f[k])
        # also any key containing caption/purpose
        for k, val in f.items():
            if k in keep:
                continue
            if re.search(r"caption|purpose|图注|用途", k, re.I):
                keep[k] = _compact_fact(val)
        figures.append(keep)

    return {
        "value_binding": values,
        "process_binding": process,
        "figure_judgment": {"figures": figures},
    }


def filter_diff_for_analysis(diff_rows: list[dict]) -> list[dict]:
    """只保留与三类焦点相关的 diff 行。"""
    out = []
    for row in diff_rows or []:
        path = str(row.get("path") or "")
        if (
            _VALUE_KEYS.search(path)
            or _PROCESS_KEYS.search(path)
            or path.startswith("figures[")
            or ".composition" in path
            or "_properties." in path
        ):
            out.append(row)
    return out


def build_analyze_prompt(
    analysis_type: str,
    *,
    sliced: dict | None = None,
    source_text: str | None = None,
    diff_rows: list[dict] | None = None,
    mode_a: str | None = None,
    mode_b: str | None = None,
) -> tuple[str, str]:
    system = (
        "你是材料文献抽取结果质检助手。只检查三类硬问题，禁止综述、禁止焦点外评论、禁止建议再抽更多字段："
        "1) value_binding：数值是否准确，且是否挂到正确样品/状态（张冠李戴、单位错、摘要目标当实测）；"
        "2) process_binding：工艺/热处理/轧制/时效是否与该样品或状态对应；"
        "3) figure_judgment：图片判断是否准确（组织图/断后图/类型/用途是否与图注或原文一致）。"
        "无硬问题则 issues=[]。只输出 JSON。"
        "summary≤80字；issues最多12条；每条 detail≤120字 suggestion≤60字；不要大段原文。"
        "每条必须含 focus（value_binding|process_binding|figure_judgment）、"
        "severity（high|medium|low）、category、path、title、detail、suggestion。"
    )
    if analysis_type == "vs_source":
        user = {
            "task": "vs_source",
            "instruction": "对照原文与抽取切片，只报上述三类硬问题；可 issues=[]。",
            "result_slices": sliced or {},
            "source_text": (source_text or "")[:120000],
            "source_note": "原文可能已经过剪裁。",
        }
    elif analysis_type == "vs_runs":
        user = {
            "task": "vs_runs",
            "instruction": "根据结构化差异，判断两类抽取在三类焦点上谁更可能对；勿复述全部 diff。",
            "mode_a": mode_a,
            "mode_b": mode_b,
            "diff_rows": diff_rows or [],
        }
    else:
        raise ValueError(f"未知 analysis_type: {analysis_type}")
    return system, json.dumps(user, ensure_ascii=False, indent=2)


def postprocess_analysis(raw: dict | None, analysis_type: str) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    summary = str(raw.get("summary") or "").strip()
    if len(summary) > 80:
        summary = summary[:80]
    issues_in = raw.get("issues") if isinstance(raw.get("issues"), list) else []
    cleaned = []
    for it in issues_in:
        if not isinstance(it, dict):
            continue
        focus = str(it.get("focus") or "").strip()
        if focus not in VALID_FOCUS:
            continue
        sev = str(it.get("severity") or "medium").lower()
        if sev not in VALID_SEVERITY:
            sev = "medium"
        detail = str(it.get("detail") or "").strip()[:120]
        suggestion = str(it.get("suggestion") or "").strip()[:60]
        title = str(it.get("title") or "").strip()[:40]
        if not title and not detail:
            continue
        cleaned.append({
            "severity": sev,
            "focus": focus,
            "category": str(it.get("category") or "other"),
            "path": str(it.get("path") or ""),
            "title": title or focus,
            "detail": detail,
            "suggestion": suggestion,
        })

    sev_rank = {"high": 0, "medium": 1, "low": 2}
    focus_rank = {f: i for i, f in enumerate(FOCUS_ORDER)}
    cleaned.sort(key=lambda x: (sev_rank.get(x["severity"], 9), focus_rank.get(x["focus"], 9)))
    cleaned = cleaned[:MAX_ISSUES]
    return {
        "analysis_type": analysis_type,
        "summary": summary or ("未发现上述三类硬问题" if not cleaned else "见问题列表"),
        "issues": cleaned,
    }


def _analysis_dir(run_dir: Path) -> Path:
    d = Path(run_dir) / "analysis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_analysis(
    run_dir: Path,
    analysis_type: str,
    payload: dict,
    *,
    status: str = "success",
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "failed" if status == "failed" else analysis_type
    name = f"{stamp}_{suffix}.json"
    path = _analysis_dir(run_dir) / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _default_call_json(root: Path, project_cfg: dict, model_id: str | None) -> Callable:
    from llm_backends import get_backend
    from pipeline import load_workspace_config

    ws = load_workspace_config(root)
    if model_id and project_cfg.get("backend") == "claude":
        model_cfg = next((m for m in ws.get("models", []) if m.get("id") == model_id), None)
        if model_cfg:
            if model_cfg.get("model"):
                os.environ["LLM_MODEL"] = model_cfg["model"]
            if model_cfg.get("base_url"):
                os.environ["LLM_BASE_URL"] = model_cfg["base_url"]
    backend = get_backend(project_cfg.get("backend", "claude"), root)
    return lambda system, user: backend.call_json(system, user)


def run_dirs_for_paper(
    root: Path, project_cfg: dict, paper_id: str, run_id: str | None = None
) -> list[Path]:
    from pipeline import list_runs

    root = Path(root)
    runs = list_runs(root, project_cfg, paper_id)
    if run_id:
        runs = [r for r in runs if r.get("run_id") == run_id]
    return [root / project_cfg["test_runs"] / r["partition"] / r["run_id"] for r in runs]


def find_analysis(run_dirs: list[Path], analysis_id: str) -> dict | None:
    if not analysis_id:
        return None
    for rd in run_dirs:
        ad = Path(rd) / "analysis"
        if not ad.exists():
            continue
        for p in ad.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("analysis_id") == analysis_id or p.stem == analysis_id:
                return data
    return None


def list_analyses_under_runs(run_dirs: list[Path]) -> list[dict]:
    items = []
    for rd in run_dirs:
        ad = Path(rd) / "analysis"
        if not ad.exists():
            continue
        for p in sorted(ad.glob("*.json"), reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append({
                "analysis_id": data.get("analysis_id") or p.stem,
                "path": str(p),
                "analysis_type": data.get("analysis_type"),
                "created_at": data.get("created_at"),
                "status": data.get("status", "success"),
                "summary": (data.get("summary") or "")[:80],
                "run_id": data.get("inputs", {}).get("run_id")
                or data.get("inputs", {}).get("run_id_a")
                or Path(rd).name,
            })
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items


def run_analysis(
    *,
    root: Path,
    project_cfg: dict,
    project_id: str,
    paper_id: str,
    analysis_type: str,
    run_id: str | None = None,
    run_id_a: str | None = None,
    run_id_b: str | None = None,
    model_id: str | None = None,
    call_json: Callable | None = None,
) -> dict:
    """执行分析。call_json(system, user) -> dict，便于测试 mock。"""
    from pipeline import (  # local import to avoid cycles in tests
        _latest_merged_run,
        get_paper_text,
        list_runs,
    )

    root = Path(root)
    created_at = datetime.now().isoformat(timespec="seconds")

    if analysis_type == "vs_source":
        if run_id:
            runs = [r for r in list_runs(root, project_cfg, paper_id) if r["run_id"] == run_id]
            if not runs:
                raise FileNotFoundError(f"未找到 run: {run_id}")
            meta = runs[0]
            run_dir = root / project_cfg["test_runs"] / meta["partition"] / meta["run_id"]
            paper_path = run_dir / "merged_outputs" / "paper.json"
            if not paper_path.exists():
                raise FileNotFoundError(f"run 无 paper.json: {run_id}")
        else:
            meta, paper_path = _latest_merged_run(root, project_cfg, paper_id)
            run_dir = paper_path.parent.parent
        result = json.loads(paper_path.read_text(encoding="utf-8"))
        text_path = run_dir / "inputs" / "parsed_text.txt"
        if text_path.exists():
            source_text = text_path.read_text(encoding="utf-8", errors="replace")
        else:
            source_text = get_paper_text(root, project_cfg, paper_id) or ""
        sliced = slice_result_for_analysis(result)
        system, user = build_analyze_prompt(
            "vs_source", sliced=sliced, source_text=source_text
        )
        anchor_run = meta["run_id"]
        inputs = {"run_id": anchor_run, "run_id_a": None, "run_id_b": None}

    elif analysis_type == "vs_runs":
        if not run_id_a or not run_id_b:
            raise ValueError("vs_runs 需要 run_id_a 与 run_id_b")
        if run_id_a == run_id_b:
            raise ValueError("请选择两个不同的 run")
        runs = {r["run_id"]: r for r in list_runs(root, project_cfg, paper_id)}
        if run_id_a not in runs or run_id_b not in runs:
            raise FileNotFoundError("Run A 或 Run B 不属于该文献或不存在")
        meta_a, meta_b = runs[run_id_a], runs[run_id_b]
        dir_a = root / project_cfg["test_runs"] / meta_a["partition"] / run_id_a
        dir_b = root / project_cfg["test_runs"] / meta_b["partition"] / run_id_b
        pa = dir_a / "merged_outputs" / "paper.json"
        pb = dir_b / "merged_outputs" / "paper.json"
        if not pa.exists() or not pb.exists():
            raise FileNotFoundError("对比双方都需要成功的 paper.json")
        ra = json.loads(pa.read_text(encoding="utf-8"))
        rb = json.loads(pb.read_text(encoding="utf-8"))
        diff_rows = filter_diff_for_analysis(diff_results(ra, rb, include_same=False))
        system, user = build_analyze_prompt(
            "vs_runs",
            diff_rows=diff_rows[:200],
            mode_a=meta_a.get("mode"),
            mode_b=meta_b.get("mode"),
        )
        run_dir = dir_a
        anchor_run = run_id_a
        inputs = {
            "run_id": None,
            "run_id_a": run_id_a,
            "run_id_b": run_id_b,
            "mode_a": meta_a.get("mode"),
            "mode_b": meta_b.get("mode"),
        }
    else:
        raise ValueError(f"未知 analysis_type: {analysis_type}")

    analysis_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + analysis_type
    base_payload = {
        "analysis_id": analysis_id,
        "analysis_type": analysis_type,
        "project_id": project_id,
        "paper_id": paper_id,
        "created_at": created_at,
        "model_id": model_id,
        "inputs": inputs,
    }

    if call_json is None:
        call_json = _default_call_json(root, project_cfg, model_id)

    try:
        raw = call_json(system, user)
        processed = postprocess_analysis(raw if isinstance(raw, dict) else {}, analysis_type)
        payload = {**base_payload, "status": "success", **processed, "raw_error": None}
        path = save_analysis(run_dir, analysis_type, payload, status="success")
        return {"ok": True, "analysis_id": analysis_id, "path": str(path), "analysis": payload}
    except Exception as exc:
        payload = {
            **base_payload,
            "status": "failed",
            "summary": "",
            "issues": [],
            "raw_error": str(exc),
        }
        path = save_analysis(run_dir, analysis_type, payload, status="failed")
        return {
            "ok": False,
            "analysis_id": analysis_id,
            "path": str(path),
            "analysis": payload,
            "error": str(exc),
        }
