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
FOCUS_SPECS = {
    "value_binding": (
        "value_binding：数值是否准确，且是否挂到正确样品/状态"
        "（张冠李戴、单位错、摘要目标当实测）"
    ),
    "process_binding": (
        "process_binding：工艺/热处理/轧制/时效是否与该样品或状态对应"
    ),
    "figure_judgment": (
        "figure_judgment：图片判断是否准确（组织图/断后图/类型/用途是否与图注或原文一致）"
    ),
}
VALID_SEVERITY = {"high", "medium", "low"}
MAX_ISSUES = 12
CUSTOM_FOCUS = "custom"
CUSTOM_FOCUS_MAX = 800


def normalize_focuses(focuses) -> list[str]:
    """勾选的内置焦点；None 表示三类全开。空列表表示只靠自定义说明。"""
    if focuses is None:
        return list(FOCUS_ORDER)
    if isinstance(focuses, str):
        focuses = [x.strip() for x in focuses.replace("，", ",").split(",") if x.strip()]
    out: list[str] = []
    for item in focuses or []:
        key = str(item or "").strip()
        if key in VALID_FOCUS and key not in out:
            out.append(key)
    return out


def normalize_custom_focus(text) -> str:
    return str(text or "").strip()[:CUSTOM_FOCUS_MAX]


def resolve_analyze_scope(focuses, custom_focus: str | None) -> tuple[list[str], str]:
    selected = normalize_focuses(focuses)
    custom = normalize_custom_focus(custom_focus)
    if not selected and not custom:
        raise ValueError("请至少勾选一类检查，或填写自定义检查重点")
    return selected, custom


def allowed_focus_ids(selected: list[str], custom: str) -> list[str]:
    ids = list(selected)
    if custom and CUSTOM_FOCUS not in ids:
        ids.append(CUSTOM_FOCUS)
    return ids

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


def slice_result_for_analysis(result: dict | None, focuses=None) -> dict:
    """裁成数值绑定 / 工艺 / 图片；可按勾选焦点只留对应切片。"""
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

    full = {
        "value_binding": values,
        "process_binding": process,
        "figure_judgment": {"figures": figures},
    }
    selected = normalize_focuses(focuses) if focuses is not None else list(FOCUS_ORDER)
    if not selected:
        return full
    return {k: full[k] for k in selected if k in full}


def filter_diff_for_analysis(diff_rows: list[dict], focuses=None) -> list[dict]:
    """只保留与所选焦点相关的 diff 行。"""
    selected = normalize_focuses(focuses) if focuses is not None else list(FOCUS_ORDER)
    if not selected:
        selected = list(FOCUS_ORDER)
    want_value = "value_binding" in selected
    want_process = "process_binding" in selected
    want_fig = "figure_judgment" in selected
    out = []
    for row in diff_rows or []:
        path = str(row.get("path") or "")
        hit_value = bool(
            _VALUE_KEYS.search(path) or ".composition" in path or "_properties." in path
        )
        hit_process = bool(_PROCESS_KEYS.search(path))
        hit_fig = path.startswith("figures[")
        if (want_value and hit_value) or (want_process and hit_process) or (want_fig and hit_fig):
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
    focuses=None,
    custom_focus: str | None = None,
) -> tuple[str, str]:
    selected, custom = resolve_analyze_scope(focuses, custom_focus)
    allowed = allowed_focus_ids(selected, custom)
    lines = []
    for i, fid in enumerate(selected, 1):
        lines.append(f"{i}) {FOCUS_SPECS[fid]}；")
    if custom:
        lines.append(f"{len(lines) + 1}) custom：按用户指定重点检查——{custom}；")
    focus_enum = "|".join(allowed)
    system = (
        "你是材料文献抽取结果质检助手。只检查用户指定的硬问题，禁止综述、禁止焦点外评论、禁止建议再抽更多字段："
        + "".join(lines)
        + "无硬问题则 issues=[]。只输出 JSON。"
        "summary≤80字；issues最多12条；每条 detail≤120字 suggestion≤60字；不要大段原文。"
        f"每条必须含 focus（{focus_enum}）、"
        "severity（high|medium|low）、category、path、title、detail、suggestion。"
    )
    if analysis_type == "vs_source":
        user = {
            "task": "vs_source",
            "instruction": "对照原文与抽取切片，只报用户指定范围内的硬问题；可 issues=[]。",
            "focuses": allowed,
            "custom_focus": custom or None,
            "result_slices": sliced or {},
            "source_text": (source_text or "")[:120000],
            "source_note": "原文可能已经过剪裁。",
        }
    elif analysis_type == "vs_runs":
        user = {
            "task": "vs_runs",
            "instruction": "根据结构化差异，判断两边在用户指定焦点上谁更可能对；勿复述全部 diff。",
            "focuses": allowed,
            "custom_focus": custom or None,
            "mode_a": mode_a,
            "mode_b": mode_b,
            "diff_rows": diff_rows or [],
        }
    else:
        raise ValueError(f"未知 analysis_type: {analysis_type}")
    return system, json.dumps(user, ensure_ascii=False, indent=2)


def postprocess_analysis(
    raw: dict | None,
    analysis_type: str,
    *,
    allowed_focus: list[str] | None = None,
) -> dict:
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
        allowed = set(allowed_focus) if allowed_focus else set(VALID_FOCUS)
        if focus not in allowed:
            if focus == CUSTOM_FOCUS and CUSTOM_FOCUS in allowed:
                pass
            else:
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
    focus_rank = {f: i for i, f in enumerate(list(FOCUS_ORDER) + [CUSTOM_FOCUS])}
    cleaned.sort(key=lambda x: (sev_rank.get(x["severity"], 9), focus_rank.get(x["focus"], 9)))
    cleaned = cleaned[:MAX_ISSUES]
    return {
        "analysis_type": analysis_type,
        "summary": summary or ("未发现所选范围内的硬问题" if not cleaned else "见问题列表"),
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
    from pipeline import load_workspace_config, resolve_model_endpoint

    ws = load_workspace_config(root)
    model_name, model_base = resolve_model_endpoint(ws, model_id)
    backend = get_backend(
        project_cfg.get("backend", "claude"),
        root,
        model=model_name,
        base_url=model_base,
    )
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
    focuses=None,
    custom_focus: str | None = None,
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
    selected, custom = resolve_analyze_scope(focuses, custom_focus)
    allowed = allowed_focus_ids(selected, custom)

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
        sliced = slice_result_for_analysis(result, selected)
        system, user = build_analyze_prompt(
            "vs_source",
            sliced=sliced,
            source_text=source_text,
            focuses=selected,
            custom_focus=custom,
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
        diff_rows = filter_diff_for_analysis(
            diff_results(ra, rb, include_same=False), selected
        )
        system, user = build_analyze_prompt(
            "vs_runs",
            diff_rows=diff_rows[:200],
            mode_a=meta_a.get("mode"),
            mode_b=meta_b.get("mode"),
            focuses=selected,
            custom_focus=custom,
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
        "focuses": allowed,
        "custom_focus": custom or None,
    }

    if call_json is None:
        call_json = _default_call_json(root, project_cfg, model_id)

    try:
        raw = call_json(system, user)
        processed = postprocess_analysis(
            raw if isinstance(raw, dict) else {},
            analysis_type,
            allowed_focus=allowed,
        )
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
