"""配置驱动的分阶段文献抽取 pipeline。

流程（对应分享里的方法论）：
    输入剪裁 -> Stage1 样品-状态骨架 -> Stage2 基于 condition 补性能
    -> 图片单独分类过滤 -> 规则校验兜底 -> 合并导出

设计要点：
- 字段和规则来自 configs/fields/<project>.json，改配置即可换领域；
- Stage2 只允许给 Stage1 已有的 condition 补性能，不新增样品/状态；
- 性能值按来源白/黑名单做规则校验，剔除「摘要目标/权利要求范围」等非实测来源；
- 图片按类型白名单过滤，剔除 XRD/衍射/示意图等非组织图；
- 每一阶段落一个中间产物，便于反查。

mode:
    two_stage    完整两阶段 + 规则校验 + 图片过滤（推荐）
    entity_only  只建样品-状态骨架
    single_pass  模拟 one-shot：抽完但不做规则校验/图片过滤（用于对比「优化前」）
"""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_model import (  # noqa: E402
    effective_fields,
    generate_steps,
    load_field_library,
    load_template,
)
from input_trim import trim_input  # noqa: E402
from llm_backends import get_backend  # noqa: E402
from paper_parser import parse_paper_md  # noqa: E402
from provenance import is_identity_field  # noqa: E402


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
def load_workspace_config(root: Path) -> dict:
    cfg_path = Path(root) / "configs" / "project_config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def load_field_config(root: Path, project_cfg: dict) -> dict:
    """有 overlay 时从 config_model 合成旧结构；否则回退读 field_config 文件。"""
    root = Path(root)
    overlay_rel = project_cfg.get("overlay")
    if overlay_rel:
        overlay_path = root / overlay_rel
        if overlay_path.exists():
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
            template_id = overlay.get("template_id") or project_cfg.get("template_id", "blank")
            template = load_template(root, template_id)
            library = load_field_library(root, template_id)
            effective = effective_fields(library, overlay)
            fields_by_cat = {
                "metadata": [], "sample": [], "condition": [], "property": [], "figure": [],
            }
            rules = {}
            for f in effective:
                cat = f.get("category") or "property"
                fields_by_cat.setdefault(cat, []).append(f["id"])
                rules[f"{cat}.{f['id']}"] = {
                    "rule": f.get("rule", ""),
                    "positive_examples": f.get("positive_examples", ""),
                    "negative_examples": f.get("negative_examples", ""),
                    "note": f.get("note", ""),
                }
            return {
                "fields": fields_by_cat,
                "rules": rules,
                "steps": generate_steps(template, effective, overlay),
                "property_source": overlay.get("property_source", {}),
                "figure_filter": overlay.get("figure_filter", {}),
                "template_id": template_id,
                "domain_hint": template.get("domain_hint") or "材料文献",
            }
    rel = project_cfg.get("field_config")
    if not rel:
        return {"fields": {}, "rules": {}, "property_source": {}, "figure_filter": {}}
    path = root / rel
    if not path.exists():
        return {"fields": {}, "rules": {}, "property_source": {}, "figure_filter": {}}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Prompt 构建（同时用于前端预览）
# ---------------------------------------------------------------------------
def _fmt_rules(rules: dict, keys: list) -> str:
    lines = []
    for i, key in enumerate(keys, 1):
        r = rules.get(key)
        if not r:
            continue
        parts = [f"{i}. [{key}] {r.get('rule', '')}"]
        if r.get("positive_examples"):
            parts.append(f"   正例: {r['positive_examples']}")
        if r.get("negative_examples"):
            parts.append(f"   反例: {r['negative_examples']}")
        lines.append("\n".join(parts))
    return "\n".join(lines) if lines else "(该配置未定义专门规则)"


def build_entity_prompt(field_config: dict, text: str) -> str:
    fields = field_config.get("fields", {})
    rules = field_config.get("rules", {})
    domain_hint = field_config.get("domain_hint") or "材料文献"
    rule_keys = [f"sample.{f}" for f in fields.get("sample", [])] + \
                [f"condition.{f}" for f in fields.get("condition", [])]
    schema = {
        "paper_metadata": {f: "..." for f in fields.get("metadata", [])},
        "samples": [{f: "..." for f in fields.get("sample", [])}],
        "conditions": [{f: "..." for f in fields.get("condition", [])}],
        "figures": [{f: "..." for f in fields.get("figure", [])}],
    }
    return f"""[Stage 1 · 样品-状态骨架]
你是{domain_hint}结构化抽取专家。本阶段只建立样品与状态的索引，不抽具体性能数值。
严格输出如下 JSON（不要 markdown 代码块，第一个字符是 {{）：

{json.dumps(schema, ensure_ascii=False, indent=2)}

## 抽取规则
{_fmt_rules(rules, rule_keys)}

## 论文正文（已剪裁）
{text}
"""


def build_property_prompt(field_config: dict, step: dict, condition_ids: list) -> str:
    rules = field_config.get("rules", {})
    src = field_config.get("property_source", {})
    step_fields = step.get("fields", [])
    group = step.get("group", "properties")
    rule_keys = [f"property.{f}" for f in step_fields]
    ids = condition_ids or ["C1", "C2", "..."]
    schema = {
        "properties": [
            {"condition_id": ids[0],
             **{f: {"value": "...", "unit": "...", "source": "measured_table"} for f in step_fields}}
        ]
    }
    return f"""[{step.get('name', '性能步骤')}] 本步只抽【{group}】：{', '.join(step_fields)}
已给定 condition 列表：{', '.join(ids)}
只允许给这些已有 condition 补本组性能，禁止新增样品或状态，也不要抽本组以外的字段。
严格输出如下 JSON：

{json.dumps(schema, ensure_ascii=False, indent=2)}

## 本组字段规则
{_fmt_rules(rules, rule_keys)}

## 性能值来源要求
允许来源: {', '.join(src.get('allow', [])) or '(未配置)'}
禁止来源: {', '.join(src.get('deny', [])) or '(未配置)'}
每个性能值必须带 source 字段说明来源。
"""


def build_reextract_property_prompt(field_config: dict, field_id: str,
                                    condition_ids: list, text: str) -> str:
    rules = field_config.get("rules", {})
    src = field_config.get("property_source", {})
    ids = condition_ids or ["C1", "C2", "..."]
    schema = {
        "properties": [
            {"condition_id": ids[0],
             field_id: {
                 "value": "...", "unit": "...", "source": "measured_table",
                 "excerpt": "...", "location": "...",
             }}
        ]
    }
    return f"""[单字段重抽 · {field_id}]
只抽字段【{field_id}】，每个值必须带 excerpt、location、source。
已给定 condition 列表：{', '.join(ids)}
只允许给这些已有 condition 补该字段，禁止新增样品或状态，也不要抽其它字段。
严格输出如下 JSON：

{json.dumps(schema, ensure_ascii=False, indent=2)}

## 字段规则
{_fmt_rules(rules, [f"property.{field_id}"])}

## 性能值来源要求
允许来源: {', '.join(src.get('allow', [])) or '(未配置)'}
禁止来源: {', '.join(src.get('deny', [])) or '(未配置)'}

## 论文正文（已剪裁）
{text}
"""


def build_reextract_entity_prompt(field_config: dict, field: dict,
                                  entity: dict, text: str) -> str:
    cat = field.get("category") or "metadata"
    fid = field["id"]
    domain_hint = field_config.get("domain_hint") or "材料文献"
    value_schema = {"value": "...", "unit": "", "excerpt": "...", "location": "..."}
    if cat == "metadata":
        schema: dict = {"paper_metadata": {fid: value_schema}}
    elif cat == "sample":
        schema = {"samples": [{"sample_id": "...", fid: value_schema}]}
    elif cat == "condition":
        schema = {"conditions": [{"condition_id": "...", fid: value_schema}]}
    elif cat == "figure":
        schema = {"figures": [{"figure_id": "...", fid: value_schema}]}
    else:
        schema = {fid: value_schema}
    return f"""[单字段重抽 · {fid}]
你是{domain_hint}结构化抽取专家。只重抽字段【{fid}】（category={cat}），不要改其它字段，不要新增样品或状态。
每个非标识值必须带 excerpt / location。
现有实体 JSON 作为上下文（只作参考，输出仅含本字段更新）：
{json.dumps(entity, ensure_ascii=False, indent=2)}

严格输出如下 JSON：
{json.dumps(schema, ensure_ascii=False, indent=2)}

## 字段规则
{_fmt_rules(field_config.get("rules", {}), [f"{cat}.{fid}"])}

## 论文正文（已剪裁）
{text}
"""


def get_steps(field_config: dict) -> list:
    """返回抽取步骤序列；未配置 steps 时按 fields 合成默认序列（向后兼容）。"""
    steps = field_config.get("steps")
    if steps:
        return steps
    fields = field_config.get("fields", {})
    out = [{"id": "entity", "type": "entity", "name": "Stage1 · 样品-状态骨架"}]
    if fields.get("property"):
        out.append({"id": "property", "type": "property", "name": "Stage2 · 性能",
                    "group": "properties", "fields": fields["property"]})
    if fields.get("figure"):
        out.append({"id": "figures", "type": "figure", "name": "Stage3 · 图片分类"})
    return out


# ---------------------------------------------------------------------------
# 规则校验
# ---------------------------------------------------------------------------
def validate_properties(properties: list, field_config: dict) -> tuple[list, list]:
    """按来源白/黑名单剔除不可靠性能值，返回(清洗后, 警告列表)。"""
    src = field_config.get("property_source", {})
    deny = set(src.get("deny", []))
    deny_phrases = [p.lower() for p in src.get("deny_phrase_patterns", [])]
    prop_fields = field_config.get("fields", {}).get("property", [])
    warnings = []
    cleaned = []
    for row in properties or []:
        cid = row.get("condition_id")
        new_row = {"condition_id": cid}
        for f in prop_fields:
            val = row.get(f)
            if not isinstance(val, dict) or val.get("value") in (None, ""):
                continue
            source = str(val.get("source", "")).lower()
            evidence = str(val.get("evidence", "")).lower()
            bad = source in deny or any(p in source or p in evidence for p in deny_phrases)
            if bad:
                warnings.append({
                    "type": "property_source_rejected",
                    "condition_id": cid,
                    "field": f,
                    "value": val.get("value"),
                    "unit": val.get("unit"),
                    "source": val.get("source"),
                    "excerpt": val.get("excerpt", ""),
                    "location": val.get("location", ""),
                    "detail": f"{cid}.{f}={val.get('value')} 来源不可靠({val.get('source')})，已剔除",
                })
                new_row[f] = {
                    "value": val.get("value"),
                    "unit": val.get("unit", ""),
                    "source": val.get("source", ""),
                    "excerpt": val.get("excerpt", ""),
                    "location": val.get("location", ""),
                    "status": "rejected_by_rule",
                    "reject_reason": f"来源不可靠({val.get('source')})",
                }
                continue
            new_row[f] = {
                "value": val.get("value"),
                "unit": val.get("unit", ""),
                "source": val.get("source", ""),
                "excerpt": val.get("excerpt", ""),
                "location": val.get("location", ""),
                "status": "accepted",
            }
        cleaned.append(new_row)
    return cleaned, warnings


def classify_figures(figures: list, field_config: dict, apply_filter: bool) -> tuple[list, list]:
    """按类型白名单过滤图片。apply_filter=False 时保留全部（模拟 one-shot）。"""
    ff = field_config.get("figure_filter", {})
    keep_types = set(ff.get("keep_types", []))
    warnings = []
    kept = []
    for fig in figures or []:
        if not apply_filter:
            kept.append({**fig, "status": "accepted"})
            continue
        ftype = fig.get("figure_type")
        reason = None
        if keep_types and ftype not in keep_types:
            reason = f"类型 {ftype} 不在组织图白名单"
        elif ff.get("require_microstructure") and fig.get("is_microstructure_image") is not True:
            reason = "非组织图 is_microstructure_image=false"
        elif ff.get("drop_if_post_test") and fig.get("is_post_test_image") is True:
            reason = "断后/post-test 图不入组织图库"
        if reason:
            warnings.append({
                "type": "figure_dropped",
                "figure_id": fig.get("figure_id"),
                "figure_type": ftype,
                "detail": f"{fig.get('figure_id')} 被过滤：{reason}",
            })
            kept.append({**fig, "status": "rejected_by_rule", "reject_reason": reason})
            continue
        kept.append({**fig, "status": "accepted"})
    return kept, warnings


# ---------------------------------------------------------------------------
# 合并
# ---------------------------------------------------------------------------
def merge_result(entity: dict, property_groups: dict, figures: list) -> dict:
    """property_groups: {group_name: [ {condition_id, field:{value,unit}, ...}, ... ]}"""
    group_maps = {}
    for group, rows in property_groups.items():
        group_maps[group] = {
            r.get("condition_id"): {k: v for k, v in r.items() if k != "condition_id"}
            for r in rows or []
        }
    conditions = []
    for cond in entity.get("conditions", []) or []:
        cid = cond.get("condition_id")
        merged = dict(cond)
        for group, cid_map in group_maps.items():
            props = cid_map.get(cid)
            if props:
                merged[group] = props
        conditions.append(merged)
    return {
        "paper_metadata": entity.get("paper_metadata", {}),
        "samples": entity.get("samples", []),
        "conditions": conditions,
        "figures": figures,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _resolve_parsed_dir(root: Path, project_cfg: dict) -> Path | None:
    rel = project_cfg.get("parsed_results")
    if not rel:
        return None
    return Path(root) / rel


def list_papers(root: Path, project_cfg: dict) -> list:
    parsed_dir = _resolve_parsed_dir(root, project_cfg)
    if not parsed_dir or not parsed_dir.exists():
        return []
    return sorted(
        d.name for d in parsed_dir.iterdir()
        if d.is_dir() and (d / "paper.md").exists()
    )


def get_paper_text(root: Path, project_cfg: dict, paper_id: str) -> str | None:
    parsed_dir = _resolve_parsed_dir(root, project_cfg)
    if not parsed_dir:
        return None
    p = parsed_dir / paper_id / "paper.md"
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


def list_runs(root: Path, project_cfg: dict, paper_id: str | None = None) -> list:
    base = Path(root) / project_cfg.get("test_runs", "")
    if not base.exists():
        return []
    runs = []
    for partition in ("test", "data"):
        pdir = base / partition
        if not pdir.exists():
            continue
        for d in sorted(pdir.iterdir(), reverse=True):
            info = d / "RUN_INFO.json"
            if info.exists():
                try:
                    meta = json.loads(info.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
                if paper_id and meta.get("paper_id") != paper_id:
                    continue
                runs.append({"run_id": d.name, "partition": partition, **meta})
    return runs


def _empty_entity() -> dict:
    return {"paper_metadata": {}, "samples": [], "conditions": [], "figures": []}


def _skeleton_done(state: dict) -> bool:
    steps = get_steps(state["field_config"])
    entity_ids = {s.get("id") for s in steps if s.get("type") == "entity"}
    return bool(entity_ids & set(state.get("completed_steps") or []))


def _find_step(field_config: dict, step_id: str) -> dict:
    for step in get_steps(field_config):
        if step.get("id") == step_id:
            return step
    raise ValueError(f"未知步骤: {step_id}")


def _downstream_steps(field_config: dict) -> list:
    return [s for s in get_steps(field_config) if s.get("type") in ("property", "figure")]


def _clear_properties_dir(run_dir: Path) -> None:
    prop_dir = run_dir / "properties"
    if not prop_dir.exists():
        return
    for p in prop_dir.iterdir():
        if p.is_file():
            p.unlink()


def _load_run_artifacts(state: dict) -> None:
    """从已有 run 目录恢复 entity / property_groups / figures。"""
    run_dir = state["run_dir"]
    entity = _empty_entity()
    for ent_path in sorted((run_dir / "entities").glob("*.json")):
        try:
            ent = json.loads(ent_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if ent.get("paper_metadata"):
            entity["paper_metadata"].update(ent.get("paper_metadata") or {})
        entity["samples"].extend(ent.get("samples") or [])
        entity["conditions"].extend(ent.get("conditions") or [])
        entity["figures"].extend(ent.get("figures") or [])
    state["entity"] = entity
    state["condition_ids"] = [c.get("condition_id") for c in entity["conditions"]]

    property_groups: dict = {}
    figures: list = []
    for step in get_steps(state["field_config"]):
        sid = step.get("id")
        stype = step.get("type")
        if stype == "property":
            clean_path = run_dir / "properties" / f"{sid}_clean.json"
            if clean_path.exists():
                try:
                    property_groups[step.get("group", "properties")] = json.loads(
                        clean_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        elif stype == "figure":
            fig_path = run_dir / "properties" / f"{sid}_figures.json"
            if fig_path.exists():
                try:
                    figures = json.loads(fig_path.read_text(encoding="utf-8"))
                except Exception:
                    figures = []
    state["property_groups"] = property_groups
    if not any(s.get("type") == "figure" for s in get_steps(state["field_config"])):
        figures = entity.get("figures", [])
    state["figures"] = figures


def _write_run_outputs(state: dict) -> dict:
    """合并结果并写 paper.json / RUN_INFO / summary，返回 result。"""
    steps = get_steps(state["field_config"])
    entity = state["entity"]
    property_groups = state["property_groups"]
    figures = state["figures"]
    if not any(s.get("type") == "figure" for s in steps):
        figures = entity.get("figures", [])
        state["figures"] = figures

    result = merge_result(entity, property_groups, figures)
    result["_paper_id"] = state["paper_id"]
    result["_pipeline"] = {
        "mode": state["mode"],
        "backend": state["backend"].name,
        "input_trim": state["trim_stats"],
        "condition_ids": state["condition_ids"],
        "rules_applied": state["apply_rules"],
        "steps": [{"id": s.get("id"), "type": s.get("type"),
                   "name": s.get("name"), "group": s.get("group")} for s in steps],
    }
    warnings = state["warnings"]
    if warnings:
        result["_validation_warnings"] = warnings

    run_dir = state["run_dir"]
    (run_dir / "merged_outputs" / "paper.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "review_notes" / "validation_warnings.json").write_text(
        json.dumps(warnings, ensure_ascii=False, indent=2), encoding="utf-8")

    run_info = {
        "run_id": state["run_id"],
        "project_id": state["project_id"],
        "paper_id": state["paper_id"],
        "mode": state["mode"],
        "partition": state["partition"],
        "backend": state["backend"].name,
        "created_at": state.get("created_at") or datetime.now().isoformat(timespec="seconds"),
        "steps": len(steps),
        "samples": len(result.get("samples", [])),
        "conditions": len(result.get("conditions", [])),
        "figures": len(result.get("figures", [])),
        "warnings": len(warnings),
        "template_id": state.get("template_id"),
        "completed_steps": list(state.get("completed_steps") or []),
        "invalidated_steps": list(state.get("invalidated_steps") or []),
        "parse_skipped": bool(state.get("parse_skipped", True)),
    }
    if state.get("model_id"):
        run_info["model_id"] = state["model_id"]
    state["run_info"] = run_info
    (run_dir / "RUN_INFO.json").write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(
        _build_summary_md(run_info, state["trim_stats"], warnings), encoding="utf-8")
    return result


def _prepare_run(root: Path, project_id: str, paper_id: str, *,
                 mode: str = "two_stage", partition: str = "test",
                 model_id: str | None = None, run_id: str | None = None) -> dict:
    """建/接 run 目录、解析文本、trim；返回可执行步骤的 run_state。"""
    root = Path(root)
    ws_cfg = load_workspace_config(root)
    project_cfg = ws_cfg["projects"].get(project_id)
    if not project_cfg:
        raise ValueError(f"未知项目: {project_id}")
    if not project_cfg.get("runnable", False):
        raise RuntimeError(
            f"项目 {project_id} 为只读快照，本地无 parsed_results，无法试跑；"
            f"请选择 demo_steel 离线体验。"
        )

    if model_id and project_cfg.get("backend") == "claude":
        model_cfg = next((m for m in ws_cfg.get("models", []) if m.get("id") == model_id), None)
        if model_cfg:
            if model_cfg.get("model"):
                os.environ["LLM_MODEL"] = model_cfg["model"]
            if model_cfg.get("base_url"):
                os.environ["LLM_BASE_URL"] = model_cfg["base_url"]

    field_config = load_field_config(root, project_cfg)
    parsed_dir = _resolve_parsed_dir(root, project_cfg)
    paper_md = parsed_dir / paper_id / "paper.md"
    if not paper_md.exists():
        raise FileNotFoundError(f"paper.md 不存在: {paper_md}")

    backend = get_backend(project_cfg.get("backend", "mock"), root)
    apply_rules = mode != "single_pass"

    parsed = parse_paper_md(paper_id, paper_md)
    trimmed_text, trim_stats = trim_input(parsed.text_with_placeholders)
    images_payload = [
        {"label": im.label or f"Image {im.index}", "media_type": im.media_type, "data": im.data_b64}
        for im in parsed.images
    ]

    # 已有 paper.md → 跳过 UniParser；本工具不在此路径调用解析
    parse_skipped = True
    created_at = datetime.now().isoformat(timespec="seconds")
    completed_steps: list = []
    invalidated_steps: list = []
    resume = False

    if run_id:
        run_dir = Path(root) / project_cfg["test_runs"] / partition / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"run 不存在: {run_dir}")
        resume = True
        info_path = run_dir / "RUN_INFO.json"
        if info_path.exists():
            try:
                prev = json.loads(info_path.read_text(encoding="utf-8"))
                completed_steps = list(prev.get("completed_steps") or [])
                created_at = prev.get("created_at") or created_at
                if "parse_skipped" in prev:
                    parse_skipped = bool(prev["parse_skipped"])
            except Exception:
                pass
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{stamp}_{mode}"
        run_dir = Path(root) / project_cfg["test_runs"] / partition / run_id
        n = 1
        while run_dir.exists():
            run_id = f"{stamp}_{mode}_{n}"
            run_dir = Path(root) / project_cfg["test_runs"] / partition / run_id
            n += 1

    for sub in ("prompt_preview", "inputs", "entities", "properties", "merged_outputs", "review_notes", "logs"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    (run_dir / "inputs" / "parsed_text.txt").write_text(trimmed_text, encoding="utf-8")
    (run_dir / "inputs" / "input_trim_stats.json").write_text(
        json.dumps(trim_stats, ensure_ascii=False, indent=2), encoding="utf-8")

    template_id = field_config.get("template_id") or project_cfg.get("template_id")
    state = {
        "root": root,
        "project_id": project_id,
        "paper_id": paper_id,
        "mode": mode,
        "partition": partition,
        "model_id": model_id,
        "run_id": run_id,
        "run_dir": run_dir,
        "project_cfg": project_cfg,
        "field_config": field_config,
        "backend": backend,
        "apply_rules": apply_rules,
        "trimmed_text": trimmed_text,
        "trim_stats": trim_stats,
        "images_payload": images_payload,
        "entity": _empty_entity(),
        "property_groups": {},
        "figures": [],
        "warnings": [],
        "condition_ids": [],
        "prompts": {},
        "step_reports": [],
        "completed_steps": completed_steps,
        "invalidated_steps": invalidated_steps,
        "parse_skipped": parse_skipped,
        "template_id": template_id,
        "created_at": created_at,
        "resume": resume,
    }
    if resume:
        _load_run_artifacts(state)
        # 恢复已有校验警告
        warn_path = run_dir / "review_notes" / "validation_warnings.json"
        if warn_path.exists():
            try:
                state["warnings"] = json.loads(warn_path.read_text(encoding="utf-8"))
            except Exception:
                state["warnings"] = []
    return state


def _execute_step(state: dict, step: dict) -> None:
    """执行单个抽取步骤，更新 state 并落中间产物。"""
    stype = step.get("type")
    sid = step.get("id", stype)
    sname = step.get("name", sid)
    field_config = state["field_config"]
    run_dir = state["run_dir"]
    backend = state["backend"]
    paper_id = state["paper_id"]
    apply_rules = state["apply_rules"]
    mode = state["mode"]

    if stype == "entity":
        prompt = build_entity_prompt(field_config, state["trimmed_text"])
        state["prompts"][sid] = prompt
        (run_dir / "prompt_preview" / f"{sid}_prompt.txt").write_text(prompt, encoding="utf-8")
        ent = backend.call_json(
            "材料文献结构化抽取专家", prompt, state["images_payload"],
            hint={"stage": "entity", "step_id": sid, "paper_id": paper_id},
        )
        entity = _empty_entity()
        if ent.get("paper_metadata"):
            entity["paper_metadata"].update(ent.get("paper_metadata") or {})
        entity["samples"].extend(ent.get("samples") or [])
        entity["conditions"].extend(ent.get("conditions") or [])
        entity["figures"].extend(ent.get("figures") or [])
        state["entity"] = entity
        state["condition_ids"] = [c.get("condition_id") for c in entity["conditions"]]
        (run_dir / "entities" / f"{sid}.json").write_text(
            json.dumps(ent, ensure_ascii=False, indent=2), encoding="utf-8")
        state["step_reports"].append({
            "id": sid, "name": sname, "type": stype,
            "output": {"samples": entity["samples"], "conditions": entity["conditions"]},
            "warnings": [],
        })

    elif stype == "property":
        if mode == "entity_only":
            return
        group = step.get("group", "properties")
        prompt = build_property_prompt(field_config, step, state["condition_ids"])
        state["prompts"][sid] = prompt
        (run_dir / "prompt_preview" / f"{sid}_prompt.txt").write_text(prompt, encoding="utf-8")
        raw = backend.call_json(
            "材料文献结构化抽取专家", prompt, None,
            hint={"stage": "property", "step_id": sid, "paper_id": paper_id},
        )
        (run_dir / "properties" / f"{sid}_raw.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        raw_props = raw.get("properties", [])
        step_warnings: list = []
        step_field_cfg = {
            "property_source": field_config.get("property_source", {}),
            "fields": {"property": step.get("fields", [])},
        }
        if apply_rules:
            cleaned, step_warnings = validate_properties(raw_props, step_field_cfg)
        else:
            cleaned = [
                {"condition_id": r.get("condition_id"),
                 **{k: {
                     "value": v.get("value"),
                     "unit": v.get("unit", ""),
                     "source": v.get("source", ""),
                     "excerpt": v.get("excerpt", ""),
                     "location": v.get("location", ""),
                 }
                    for k, v in r.items() if k != "condition_id" and isinstance(v, dict)}}
                for r in raw_props
            ]
        state["property_groups"][group] = cleaned
        # 重跑单步时去掉该组旧警告再追加
        state["warnings"] = [
            w for w in state["warnings"]
            if not (w.get("type") == "property_source_rejected"
                    and any(f in (w.get("field"),) for f in step.get("fields", [])))
        ]
        state["warnings"].extend(step_warnings)
        (run_dir / "properties" / f"{sid}_clean.json").write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        state["step_reports"].append({
            "id": sid, "name": sname, "type": stype, "group": group,
            "output": cleaned, "warnings": step_warnings,
        })

    elif stype == "figure":
        figures, fig_warnings = classify_figures(
            state["entity"].get("figures", []), field_config, apply_filter=apply_rules)
        state["figures"] = figures
        state["warnings"] = [w for w in state["warnings"] if w.get("type") != "figure_dropped"]
        if apply_rules:
            state["warnings"].extend(fig_warnings)
        state["prompts"][sid] = "（图片分类为确定性规则步骤：按 figure_filter 白名单过滤，非 LLM prompt）"
        (run_dir / "properties" / f"{sid}_figures.json").write_text(
            json.dumps(figures, ensure_ascii=False, indent=2), encoding="utf-8")
        state["step_reports"].append({
            "id": sid, "name": sname, "type": stype,
            "output": figures, "warnings": fig_warnings if apply_rules else [],
        })

    else:
        raise ValueError(f"不支持的步骤类型: {stype}")

    completed = [x for x in state["completed_steps"] if x != sid]
    completed.append(sid)
    state["completed_steps"] = completed


def _invalidate_downstream(state: dict) -> list:
    """作废已完成的下游 property/figure 步骤，返回失效 step_id 列表。"""
    down_ids = {s.get("id") for s in _downstream_steps(state["field_config"])}
    invalidated = [sid for sid in state["completed_steps"] if sid in down_ids]
    if not invalidated and not state["property_groups"] and not list(
            (state["run_dir"] / "properties").glob("*")):
        return []

    # 即使 completed_steps 未记下游，只要磁盘有 properties 产物也视为失效
    if not invalidated:
        for step in _downstream_steps(state["field_config"]):
            sid = step.get("id")
            stype = step.get("type")
            if stype == "property" and (state["run_dir"] / "properties" / f"{sid}_clean.json").exists():
                invalidated.append(sid)
            elif stype == "figure" and (state["run_dir"] / "properties" / f"{sid}_figures.json").exists():
                invalidated.append(sid)

    _clear_properties_dir(state["run_dir"])
    state["property_groups"] = {}
    state["figures"] = []
    state["warnings"] = [
        w for w in state["warnings"]
        if w.get("type") not in ("property_source_rejected", "figure_dropped")
    ]
    state["completed_steps"] = [sid for sid in state["completed_steps"] if sid not in down_ids]
    state["invalidated_steps"] = list(invalidated)
    return invalidated


def run_extraction(root: Path, project_id: str, paper_id: str,
                   mode: str = "two_stage", partition: str = "test",
                   model_id: str | None = None) -> dict:
    state = _prepare_run(
        root, project_id, paper_id, mode=mode, partition=partition, model_id=model_id)
    steps = get_steps(state["field_config"])
    for step in steps:
        if mode == "entity_only" and step.get("type") != "entity":
            continue
        _execute_step(state, step)
    result = _write_run_outputs(state)
    return {
        "run_id": state["run_id"],
        "run_dir": str(state["run_dir"]),
        "run_info": state["run_info"],
        "result": result,
        "entity": state["entity"],
        "property_groups": state["property_groups"],
        "figures": state["figures"],
        "warnings": state["warnings"],
        "trim_stats": state["trim_stats"],
        "steps": state["step_reports"],
        "prompts": state["prompts"],
    }


def run_step(root: Path, project_id: str, paper_id: str, step_id: str,
             run_id: str | None = None, partition: str = "test",
             model_id: str | None = None) -> dict:
    """分阶段执行单个步骤；重跑骨架时作废并自动重跑全部下游。"""
    state = _prepare_run(
        root, project_id, paper_id,
        mode="two_stage", partition=partition, model_id=model_id, run_id=run_id)
    step = _find_step(state["field_config"], step_id)
    stype = step.get("type")
    invalidated: list = []

    if stype in ("property", "figure") and not _skeleton_done(state):
        raise RuntimeError("必须先完成骨架")

    if stype == "entity":
        # 重跑骨架：作废下游并自动重跑
        had_downstream = bool(state.get("property_groups")) or any(
            sid for sid in state.get("completed_steps") or []
            if sid in {s.get("id") for s in _downstream_steps(state["field_config"])}
        ) or any((state["run_dir"] / "properties").glob("*"))
        if had_downstream:
            invalidated = _invalidate_downstream(state)
        _execute_step(state, step)
        if had_downstream:
            for down in _downstream_steps(state["field_config"]):
                if state["mode"] == "entity_only" and down.get("type") != "entity":
                    continue
                _execute_step(state, down)
    else:
        state["invalidated_steps"] = []
        _execute_step(state, step)

    result = _write_run_outputs(state)
    return {
        "run_id": state["run_id"],
        "run_dir": str(state["run_dir"]),
        "run_info": state["run_info"],
        "step": step_id,
        "result": result,
        "invalidated": invalidated,
        "entity": state["entity"],
        "property_groups": state["property_groups"],
        "figures": state["figures"],
        "warnings": state["warnings"],
        "trim_stats": state["trim_stats"],
        "steps": state["step_reports"],
        "prompts": state["prompts"],
    }


def _resolve_reextract_field(root: Path, project_cfg: dict, field_id: str) -> tuple[dict, dict]:
    """Return (template, field_def). Raise if identity or unknown."""
    template_id = project_cfg.get("template_id", "blank")
    overlay_rel = project_cfg.get("overlay")
    overlay = {}
    if overlay_rel:
        overlay_path = Path(root) / overlay_rel
        if overlay_path.exists():
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
            template_id = overlay.get("template_id") or template_id
    template = load_template(root, template_id)
    if is_identity_field(template, {"id": field_id}):
        raise ValueError("标识字段不可单字段重抽")

    field = None
    if overlay:
        library = load_field_library(root, template_id)
        for f in effective_fields(library, overlay):
            if f.get("id") == field_id:
                field = f
                break
    if field is None:
        # fallback: synthesize from field_config categories
        fc = load_field_config(root, project_cfg)
        for cat, ids in (fc.get("fields") or {}).items():
            if field_id in ids:
                field = {"id": field_id, "category": cat, "group": None}
                if cat == "property":
                    for step in get_steps(fc):
                        if step.get("type") == "property" and field_id in (step.get("fields") or []):
                            field["group"] = step.get("group")
                            break
                break
    if field is None:
        raise ValueError(f"未知字段: {field_id}")
    return template, field


def _latest_merged_run(root: Path, project_cfg: dict, paper_id: str,
                       partition: str | None = None) -> tuple[dict, Path]:
    """最新带 merged paper.json 的成功 run。"""
    runs = list_runs(root, project_cfg, paper_id)
    if partition:
        runs = [r for r in runs if r.get("partition") == partition]
    for meta in runs:
        run_dir = Path(root) / project_cfg["test_runs"] / meta["partition"] / meta["run_id"]
        paper_path = run_dir / "merged_outputs" / "paper.json"
        if paper_path.exists():
            return meta, paper_path
    raise FileNotFoundError(f"未找到文献 {paper_id} 的合并结果 paper.json")


def _apply_property_reextract(result: dict, field_id: str, group: str,
                              cleaned_rows: list) -> None:
    by_cid = {r.get("condition_id"): r for r in cleaned_rows or []}
    for cond in result.get("conditions") or []:
        cid = cond.get("condition_id")
        row = by_cid.get(cid)
        if not row or field_id not in row:
            continue
        props = cond.setdefault(group, {})
        props[field_id] = row[field_id]


def _apply_entity_reextract(result: dict, field: dict, patch: dict) -> None:
    cat = field.get("category")
    fid = field["id"]
    if cat == "metadata":
        val = (patch.get("paper_metadata") or {}).get(fid)
        if val is not None:
            result.setdefault("paper_metadata", {})[fid] = val
    elif cat == "sample":
        by_id = {s.get("sample_id"): s for s in patch.get("samples") or []}
        for sample in result.get("samples") or []:
            src = by_id.get(sample.get("sample_id"))
            if src and fid in src:
                sample[fid] = src[fid]
    elif cat == "condition":
        by_id = {c.get("condition_id"): c for c in patch.get("conditions") or []}
        for cond in result.get("conditions") or []:
            src = by_id.get(cond.get("condition_id"))
            if src and fid in src:
                cond[fid] = src[fid]
    elif cat == "figure":
        by_id = {f.get("figure_id"): f for f in patch.get("figures") or []}
        for fig in result.get("figures") or []:
            src = by_id.get(fig.get("figure_id"))
            if src and fid in src:
                fig[fid] = src[fid]


def _reextract_one_paper(root: Path, project_id: str, project_cfg: dict,
                         field: dict, field_id: str, paper_id: str,
                         partition: str, model_id: str | None) -> dict:
    root = Path(root)
    meta, paper_path = _latest_merged_run(root, project_cfg, paper_id, partition)
    run_dir = paper_path.parent.parent
    result = json.loads(paper_path.read_text(encoding="utf-8"))
    warnings = list(result.get("_validation_warnings") or [])

    # load prior warnings file if present
    warn_path = run_dir / "review_notes" / "validation_warnings.json"
    if warn_path.exists():
        try:
            warnings = json.loads(warn_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    field_config = load_field_config(root, project_cfg)
    if model_id and project_cfg.get("backend") == "claude":
        ws_cfg = load_workspace_config(root)
        model_cfg = next((m for m in ws_cfg.get("models", []) if m.get("id") == model_id), None)
        if model_cfg:
            if model_cfg.get("model"):
                os.environ["LLM_MODEL"] = model_cfg["model"]
            if model_cfg.get("base_url"):
                os.environ["LLM_BASE_URL"] = model_cfg["base_url"]
    backend = get_backend(project_cfg.get("backend", "mock"), root)

    text_path = run_dir / "inputs" / "parsed_text.txt"
    if text_path.exists():
        trimmed_text = text_path.read_text(encoding="utf-8", errors="replace")
    else:
        raw = get_paper_text(root, project_cfg, paper_id) or ""
        trimmed_text, _ = trim_input(raw)

    note = {
        "field_id": field_id,
        "paper_id": paper_id,
        "run_id": meta.get("run_id"),
        "ok": False,
        "error": None,
        "raw": None,
    }

    try:
        cat = field.get("category")
        if cat == "property":
            condition_ids = [
                c.get("condition_id") for c in (result.get("conditions") or [])
                if c.get("condition_id")
            ]
            prompt = build_reextract_property_prompt(
                field_config, field_id, condition_ids, trimmed_text)
            (run_dir / "prompt_preview" / f"reextract_{field_id}_prompt.txt").write_text(
                prompt, encoding="utf-8")
            raw = backend.call_json(
                "材料文献结构化抽取专家", prompt, None,
                hint={"stage": "reextract", "field_id": field_id, "paper_id": paper_id},
            )
            note["raw"] = raw
            raw_props = raw.get("properties", [])
            step_field_cfg = {
                "property_source": field_config.get("property_source", {}),
                "fields": {"property": [field_id]},
            }
            cleaned, step_warnings = validate_properties(raw_props, step_field_cfg)
            # drop prior reextract warnings for this field, keep others
            warnings = [
                w for w in warnings
                if not (w.get("type") in ("property_source_rejected", "reextract_failed")
                        and w.get("field") == field_id)
            ]
            warnings.extend(step_warnings)
            group = field.get("group") or "properties"
            updated = copy.deepcopy(result)
            _apply_property_reextract(updated, field_id, group, cleaned)
        else:
            entity_ctx = {
                "paper_metadata": result.get("paper_metadata", {}),
                "samples": [
                    {k: v for k, v in s.items()
                     if not isinstance(v, dict) or "value" in v or k.endswith("_id")}
                    for s in (result.get("samples") or [])
                ],
                "conditions": [
                    {k: v for k, v in c.items()
                     if k in ("condition_id", "sample_id") or not isinstance(v, dict)
                     or "value" in v}
                    for c in (result.get("conditions") or [])
                ],
                "figures": result.get("figures", []),
            }
            prompt = build_reextract_entity_prompt(
                field_config, field, entity_ctx, trimmed_text)
            (run_dir / "prompt_preview" / f"reextract_{field_id}_prompt.txt").write_text(
                prompt, encoding="utf-8")
            raw = backend.call_json(
                "材料文献结构化抽取专家", prompt, None,
                hint={"stage": "reextract", "field_id": field_id, "paper_id": paper_id},
            )
            note["raw"] = raw
            updated = copy.deepcopy(result)
            _apply_entity_reextract(updated, field, raw)
            warnings = [
                w for w in warnings
                if not (w.get("type") == "reextract_failed" and w.get("field") == field_id)
            ]

        if warnings:
            updated["_validation_warnings"] = warnings
        elif "_validation_warnings" in updated:
            del updated["_validation_warnings"]

        paper_path.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        warn_path.parent.mkdir(parents=True, exist_ok=True)
        warn_path.write_text(
            json.dumps(warnings, ensure_ascii=False, indent=2), encoding="utf-8")
        note["ok"] = True
        (run_dir / "review_notes" / f"reextract_{field_id}.json").write_text(
            json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "paper_id": paper_id,
            "run_id": meta.get("run_id"),
            "run_dir": str(run_dir),
            "result": updated,
            "warnings": warnings,
            "ok": True,
            "error": None,
        }
    except Exception as e:
        # 失败：保留旧值，不删除 paper.json
        err = str(e)
        warnings.append({
            "type": "reextract_failed",
            "field": field_id,
            "paper_id": paper_id,
            "detail": f"字段 {field_id} 重抽失败，已保留旧值: {err}",
        })
        note["ok"] = False
        note["error"] = err
        (run_dir / "review_notes").mkdir(parents=True, exist_ok=True)
        (run_dir / "review_notes" / f"reextract_{field_id}.json").write_text(
            json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
        warn_path.parent.mkdir(parents=True, exist_ok=True)
        warn_path.write_text(
            json.dumps(warnings, ensure_ascii=False, indent=2), encoding="utf-8")
        # refresh warnings on disk paper.json without wiping fields
        try:
            kept = json.loads(paper_path.read_text(encoding="utf-8"))
            kept["_validation_warnings"] = warnings
            paper_path.write_text(
                json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return {
            "paper_id": paper_id,
            "run_id": meta.get("run_id"),
            "run_dir": str(run_dir),
            "result": result,
            "warnings": warnings,
            "ok": False,
            "error": err,
        }


def reextract_field(root: Path, project_id: str, field_id: str,
                    paper_id: str | None = None, scope: str | None = None,
                    partition: str = "test", model_id: str | None = None) -> dict:
    """单字段重抽；scope=project_extracted 时对每篇最新成功 run 批量重抽。"""
    root = Path(root)
    ws_cfg = load_workspace_config(root)
    project_cfg = ws_cfg["projects"].get(project_id)
    if not project_cfg:
        raise ValueError(f"未知项目: {project_id}")
    if not project_cfg.get("runnable", False):
        raise RuntimeError(
            f"项目 {project_id} 为只读快照，本地无 parsed_results，无法试跑；"
            f"请选择 demo_steel 离线体验。"
        )

    _, field = _resolve_reextract_field(root, project_cfg, field_id)

    if scope == "project_extracted":
        runs = list_runs(root, project_cfg, paper_id=None)
        if partition:
            runs = [r for r in runs if r.get("partition") == partition]
        seen: set[str] = set()
        papers: list[str] = []
        for r in runs:
            pid = r.get("paper_id")
            if not pid or pid in seen:
                continue
            run_dir = Path(root) / project_cfg["test_runs"] / r["partition"] / r["run_id"]
            if (run_dir / "merged_outputs" / "paper.json").exists():
                seen.add(pid)
                papers.append(pid)
        report = []
        results = []
        for pid in papers:
            try:
                out = _reextract_one_paper(
                    root, project_id, project_cfg, field, field_id, pid,
                    partition, model_id)
                report.append({
                    "paper_id": pid,
                    "ok": bool(out.get("ok")),
                    "error": out.get("error"),
                })
                results.append(out)
            except Exception as e:
                report.append({"paper_id": pid, "ok": False, "error": str(e)})
        return {
            "field_id": field_id,
            "scope": scope,
            "report": report,
            "results": results,
        }

    if not paper_id:
        raise ValueError("需要 paper_id，或使用 scope=project_extracted")

    out = _reextract_one_paper(
        root, project_id, project_cfg, field, field_id, paper_id,
        partition, model_id)
    return {
        "field_id": field_id,
        "paper_id": paper_id,
        "run_id": out.get("run_id"),
        "run_dir": out.get("run_dir"),
        "result": out.get("result"),
        "warnings": out.get("warnings"),
        "ok": out.get("ok"),
        "error": out.get("error"),
    }


def _build_summary_md(info: dict, trim: dict, warnings: list) -> str:
    lines = [
        f"# 抽取运行摘要 {info['run_id']}",
        "",
        f"- 项目: {info['project_id']} | 文献: {info['paper_id']}",
        f"- 模式: {info['mode']} | 后端: {info['backend']}",
        f"- 样品: {info['samples']} | 状态: {info['conditions']} | 图片(保留): {info['figures']}",
        f"- 输入剪裁: 保留 {trim['kept_chars']}/{trim['raw_chars']} 字符 "
        f"({trim['kept_ratio'] * 100:.1f}%)",
        f"- 规则校验命中: {len(warnings)} 项",
        "",
        "## 规则校验明细",
    ]
    if warnings:
        for w in warnings:
            lines.append(f"- {w.get('detail')}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"
