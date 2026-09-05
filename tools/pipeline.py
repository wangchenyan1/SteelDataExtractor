"""配置驱动的分阶段文献抽取 pipeline。

流程（对应分享里的方法论）：
    输入剪裁 -> Stage1 样品-状态骨架 -> Stage2 基于 condition 补性能
    -> 图片单独分类过滤 -> 规则校验兜底 -> 合并导出

设计要点：
- 字段和规则来自 configs/fields/<project>.json，改配置即可换领域；
- Stage2 只允许给 Stage1 已有的 condition 补性能，不新增样品/状态；
- 性能值按来源白/黑名单做规则校验，剔除「摘要目标/权利要求范围」等非实测来源；
- 图片按 is_microstructure_image / is_post_test_image 过滤，剔除非组织图与断后图；
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
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_model import (  # noqa: E402
    effective_fields,
    generate_steps,
    load_field_library,
    load_template,
)
from input_trim import prepare_model_text, normalize_document_kind  # noqa: E402
from llm_backends import get_backend  # noqa: E402
from paper_parser import parse_paper_md  # noqa: E402
from patent_extract_rules import PATENT_STAGE1_RULES, PATENT_STAGE2_RULES  # noqa: E402
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
                "document_kind": normalize_document_kind(overlay.get("document_kind")),
            }
    rel = project_cfg.get("field_config")
    if not rel:
        return {"fields": {}, "rules": {}, "property_source": {}, "figure_filter": {}}
    path = root / rel
    if not path.exists():
        return {"fields": {}, "rules": {}, "property_source": {}, "figure_filter": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def project_document_kind(root: Path, project_cfg: dict) -> str:
    overlay_rel = project_cfg.get("overlay")
    value = None
    if overlay_rel:
        overlay_path = Path(root) / overlay_rel
        if overlay_path.exists():
            value = json.loads(overlay_path.read_text(encoding="utf-8")).get("document_kind")
    return normalize_document_kind(value)


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


_ENTITY_IDENTITY_IDS = frozenset({
    "sample_id", "condition_id", "figure_id", "placeholder_index",
})

# 论文/专利通用：每个状态必须挂到样品（专利另有更细规则）
CONDITION_SAMPLE_BINDING_RULES = """
## 样品-状态绑定（必须严格遵守）
- 每个 condition 必须带 sample_id，且必须指向本 JSON samples 中已存在的样品 id（如 S1、S2）。
- 禁止 condition 的 sample_id 留空；禁止指向不存在的样品。
- 若全文只有一个样品，所有 condition 的 sample_id 都填该样品。
- 多样品时按原文归属填写；不确定时优先拆分样品，也不要留空 sample_id。
""".strip()

_DEFAULT_CONDITION_SAMPLE_ID_RULE = {
    "rule": "该状态归属的样品 id，必须指向本 JSON 已有 sample；禁止留空。",
    "positive_examples": "C1/C2/C3 -> S1; C4 -> S2",
    "negative_examples": "不要留空；不要指向不存在的样品；不要只建 condition 不填 sample_id",
}

_BIND_WARNING_TYPES = frozenset({
    "condition_sample_id_filled",
    "condition_sample_id_fixed",
    "condition_missing_sample_id",
    "condition_invalid_sample_id",
})


def _entity_field_slot(field_id: str):
    """标识字段用裸字符串；其余非标识字段必须带出处。"""
    if field_id in _ENTITY_IDENTITY_IDS:
        return "..."
    return {"value": "...", "unit": "", "excerpt": "...", "location": "..."}


def _condition_schema_fields(fields: dict) -> dict:
    """conditions 必须带 sample_id（挂到样品），即使它不在 condition 类字段里。"""
    cond_obj = {"sample_id": _entity_field_slot("sample_id")}
    for fid in fields.get("condition") or []:
        if fid == "sample_id":
            continue
        cond_obj[fid] = _entity_field_slot(fid)
    if "condition_id" not in cond_obj:
        cond_obj["condition_id"] = _entity_field_slot("condition_id")
    return cond_obj


FIGURE_EXTRACT_BATCH_SIZE = 12
STEP_LLM_MAX_ATTEMPTS = 5
_RETRYABLE_STAGES = frozenset({"property", "figure_extract"})


class RunCancelled(RuntimeError):
    """用户取消当前抽取。"""


def resolve_model_endpoint(ws_cfg: dict, model_id: str | None) -> tuple[str | None, str | None]:
    if not model_id:
        return None, None
    model_cfg = next((m for m in ws_cfg.get("models", []) if m.get("id") == model_id), None)
    if not model_cfg:
        return None, None
    return model_cfg.get("model"), model_cfg.get("base_url")


def _raise_if_cancelled(state: dict | None) -> None:
    if not state:
        return
    fn = state.get("cancel_check")
    if callable(fn) and fn():
        raise RunCancelled("抽取已取消")


def build_entity_prompt(field_config: dict, text: str) -> str:
    fields = field_config.get("fields", {})
    rules = dict(field_config.get("rules") or {})
    domain_hint = field_config.get("domain_hint") or "材料文献"
    rule_keys = [f"sample.{f}" for f in fields.get("sample", [])] + \
                [f"condition.{f}" for f in fields.get("condition", [])]
    # sample_id 在字段库常属 sample 类，这里强制注入 condition.sample_id 规则
    if "condition.sample_id" not in rule_keys:
        rule_keys.append("condition.sample_id")
    rules.setdefault("condition.sample_id", _DEFAULT_CONDITION_SAMPLE_ID_RULE)
    schema = {
        "paper_metadata": {f: _entity_field_slot(f) for f in fields.get("metadata", [])},
        "samples": [{f: _entity_field_slot(f) for f in fields.get("sample", [])}],
        "conditions": [_condition_schema_fields(fields)],
    }
    extra = "\n" + CONDITION_SAMPLE_BINDING_RULES + "\n"
    if normalize_document_kind(field_config.get("document_kind")) == "patent":
        extra += "\n" + PATENT_STAGE1_RULES.strip() + "\n"
    return f"""[Stage 1 · 样品-状态骨架]
你是{domain_hint}结构化抽取专家。本阶段只建立样品与状态的索引，不抽具体性能数值，也不抽取图片 figures（图片另有独立步骤）。
每个非标识字段必须是 {{value, unit, excerpt, location}} 对象：excerpt 为原文原句（可高亮），location 为章节/表号；标识字段（sample_id / condition_id）保持字符串。
每个 condition 必须填写 sample_id，指向已有样品。
严格输出如下 JSON（不要 markdown 代码块，第一个字符是 {{）：

{json.dumps(schema, ensure_ascii=False, indent=2)}

## 抽取规则
{_fmt_rules(rules, rule_keys)}
{extra}
## 论文正文（已剪裁）
{text}
"""


def build_figure_extract_prompt(field_config: dict, text: str, entity: dict,
                                batch_labels: list[str] | None = None) -> str:
    """图片抽取专用 prompt：在已有骨架上补充 figures。"""
    fields = field_config.get("fields", {})
    rules = field_config.get("rules") or {}
    domain_hint = field_config.get("domain_hint") or "材料文献"
    fig_fields = fields.get("figure") or []
    rule_keys = [f"figure.{f}" for f in fig_fields]
    schema = {
        "figures": [{f: _entity_field_slot(f) for f in fig_fields}],
    }
    skeleton = {
        "samples": [
            {
                "sample_id": s.get("sample_id"),
                "sample_name": s.get("sample_name"),
            }
            for s in (entity or {}).get("samples") or []
        ],
        "conditions": condition_skeleton_from_entity(entity or {}),
    }
    batch_note = ""
    if batch_labels:
        batch_note = (
            "\n本批只处理这些图片标签（勿输出未列出的图）：\n- "
            + "\n- ".join(batch_labels)
            + "\n"
        )
    return f"""[Stage · 图片抽取]
你是{domain_hint}结构化抽取专家。本阶段只抽取图片 figures，并尽量关联到已有 sample_id / condition_id。
不要新增样品或状态，不要输出性能数值。
标识字段 figure_id / placeholder_index 保持字符串；其余字段用 {{value, unit, excerpt, location}}。
严格输出如下 JSON（不要 markdown 代码块，第一个字符是 {{）：

{json.dumps(schema, ensure_ascii=False, indent=2)}

## 已有样品-状态骨架（只读约束）
{json.dumps(skeleton, ensure_ascii=False, indent=2)}
{batch_note}
## 抽取规则
{_fmt_rules(rules, rule_keys)}

## 论文正文（已剪裁）
{text}
"""


def normalize_entity_provenance(entity: dict) -> dict:
    """把骨架里裸字符串包成出处对象；已有对象补齐缺省键。不伪造 excerpt。

    figures 保持原样（分类依赖 figure_type 等裸字段）。
    """
    def wrap(field_id: str, raw):
        if field_id in _ENTITY_IDENTITY_IDS:
            if isinstance(raw, dict) and "value" in raw:
                return raw.get("value")
            return raw
        if raw is None:
            return {"value": "", "unit": "", "excerpt": "", "location": ""}
        if isinstance(raw, dict) and ("value" in raw or "excerpt" in raw or "location" in raw):
            out = {
                "value": raw.get("value", ""),
                "unit": raw.get("unit", "") or "",
                "excerpt": raw.get("excerpt", "") or "",
                "location": raw.get("location", "") or "",
            }
            if raw.get("status"):
                out["status"] = raw["status"]
            if raw.get("reject_reason"):
                out["reject_reason"] = raw["reject_reason"]
            return out
        return {"value": raw, "unit": "", "excerpt": "", "location": ""}

    return {
        "paper_metadata": {
            k: wrap(k, v) for k, v in (entity.get("paper_metadata") or {}).items()
        },
        "samples": [
            {k: wrap(k, v) for k, v in (s or {}).items()}
            for s in (entity.get("samples") or [])
        ],
        "conditions": [
            {k: wrap(k, v) for k, v in (c or {}).items()}
            for c in (entity.get("conditions") or [])
        ],
        "figures": list(entity.get("figures") or []),
    }


def _fact_text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or "")
    if value is None:
        return ""
    return str(value)


def _identity_text(raw) -> str:
    if isinstance(raw, dict):
        return str(raw.get("value") or "").strip()
    if raw is None:
        return ""
    return str(raw).strip()


def bind_condition_sample_ids(entity: dict) -> tuple[dict, list]:
    """确保每个 condition 尽量挂到已有 sample；单样品可自动补全。

    返回 (entity, warnings)。会原地修改 entity 内的 conditions/samples。
    """
    entity = entity if isinstance(entity, dict) else {}
    samples = entity.get("samples") if isinstance(entity.get("samples"), list) else []
    conditions = entity.get("conditions") if isinstance(entity.get("conditions"), list) else []
    warnings: list = []

    known: list[str] = []
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict):
            continue
        sid = _identity_text(sample.get("sample_id"))
        if not sid:
            sid = f"S{i + 1}"
            sample["sample_id"] = sid
        known.append(sid)
    known_set = set(known)

    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        cid = _identity_text(cond.get("condition_id")) or "?"
        sid = _identity_text(cond.get("sample_id"))
        if not sid:
            if len(known) == 1:
                cond["sample_id"] = known[0]
                warnings.append({
                    "type": "condition_sample_id_filled",
                    "detail": f"{cid} 缺少 sample_id，已自动挂到唯一样品 {known[0]}",
                    "condition_id": cid,
                    "sample_id": known[0],
                })
            else:
                warnings.append({
                    "type": "condition_missing_sample_id",
                    "detail": f"{cid} 缺少 sample_id，无法挂到样品",
                    "condition_id": cid,
                })
            continue
        if sid not in known_set:
            if len(known) == 1:
                cond["sample_id"] = known[0]
                warnings.append({
                    "type": "condition_sample_id_fixed",
                    "detail": f"{cid} 的 sample_id={sid} 无效，已改挂到唯一样品 {known[0]}",
                    "condition_id": cid,
                    "sample_id": known[0],
                })
            else:
                warnings.append({
                    "type": "condition_invalid_sample_id",
                    "detail": f"{cid} 的 sample_id={sid} 不在 samples 中",
                    "condition_id": cid,
                    "sample_id": sid,
                })
    return entity, warnings


def normalize_condition_skeleton(rows) -> list[dict]:
    """Accept ['C1'] or [{condition_id, sample_id, condition_name}]."""
    if not rows:
        return [{"condition_id": "C1", "sample_id": "", "condition_name": ""}]
    out: list[dict] = []
    for item in rows:
        if isinstance(item, str):
            out.append({"condition_id": item, "sample_id": "", "condition_name": ""})
            continue
        if not isinstance(item, dict):
            continue
        out.append({
            "condition_id": item.get("condition_id") or "",
            "sample_id": item.get("sample_id") or "",
            "condition_name": _fact_text(item.get("condition_name")),
        })
    return out or [{"condition_id": "C1", "sample_id": "", "condition_name": ""}]


def condition_skeleton_from_entity(entity: dict) -> list[dict]:
    return normalize_condition_skeleton((entity or {}).get("conditions") or [])


def build_property_prompt(field_config: dict, step: dict, condition_ids: list,
                          text: str) -> str:
    rules = field_config.get("rules", {})
    src = field_config.get("property_source", {})
    step_fields = step.get("fields", [])
    group = step.get("group", "properties")
    rule_keys = [f"property.{f}" for f in step_fields]
    skeleton = normalize_condition_skeleton(condition_ids)
    first = skeleton[0]
    schema = {
        "properties": [
            {"condition_id": first.get("condition_id") or "C1",
             "sample_id": first.get("sample_id") or "S1",
             **{f: {
                 "value": "...", "unit": "...", "source": "measured_table",
                 "excerpt": "...", "location": "...",
             } for f in step_fields}}
        ]
    }
    extra = ""
    if normalize_document_kind(field_config.get("document_kind")) == "patent":
        extra = "\n" + PATENT_STAGE2_RULES.strip() + "\n"
    return f"""[{step.get('name', '性能步骤')}] 本步只抽【{group}】：{', '.join(step_fields)}
只允许给 Stage1 骨架里已有的样品-状态补本组性能，禁止新增样品或状态，也不要抽本组以外的字段。
每个性能值必须带 excerpt、location、source。
严格输出如下 JSON（不要 markdown 代码块，第一个字符是 {{）：

{json.dumps(schema, ensure_ascii=False, indent=2)}

## 样品-状态骨架（Stage1 已确定，禁止新增或改 id）
{json.dumps(skeleton, ensure_ascii=False, indent=2)}
{extra}
## 本组字段规则
{_fmt_rules(rules, rule_keys)}

## 性能值来源要求
允许来源: {', '.join(src.get('allow', [])) or '(未配置)'}
禁止来源: {', '.join(src.get('deny', [])) or '(未配置)'}
每个性能值必须带 source 字段说明来源。

## 论文正文（已剪裁）
{text}
"""


def build_reextract_property_prompt(field_config: dict, field_id: str,
                                    condition_ids: list, text: str) -> str:
    rules = field_config.get("rules", {})
    src = field_config.get("property_source", {})
    skeleton = normalize_condition_skeleton(condition_ids)
    first = skeleton[0]
    schema = {
        "properties": [
            {"condition_id": first.get("condition_id") or "C1",
             "sample_id": first.get("sample_id") or "S1",
             field_id: {
                 "value": "...", "unit": "...", "source": "measured_table",
                 "excerpt": "...", "location": "...",
             }}
        ]
    }
    extra = ""
    if normalize_document_kind(field_config.get("document_kind")) == "patent":
        extra = "\n" + PATENT_STAGE2_RULES.strip() + "\n"
    return f"""[单字段重抽 · {field_id}]
只抽字段【{field_id}】，每个值必须带 excerpt、location、source。
只允许给 Stage1 骨架里已有的样品-状态补该字段，禁止新增样品或状态，也不要抽其它字段。
严格输出如下 JSON：

{json.dumps(schema, ensure_ascii=False, indent=2)}

## 样品-状态骨架（Stage1 已确定，禁止新增或改 id）
{json.dumps(skeleton, ensure_ascii=False, indent=2)}
{extra}
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


def _ensure_figure_extract_step(steps: list, field_config: dict) -> list:
    """有图片字段时在末尾注入 figure_extract；去掉旧的用户可见 figure 过滤步。"""
    fields = field_config.get("fields") or {}
    out = [s for s in (steps or []) if s.get("type") != "figure"]
    has_fig_fields = bool(fields.get("figure"))
    if not has_fig_fields:
        return [s for s in out if s.get("type") != "figure_extract"]
    if any(s.get("type") == "figure_extract" for s in out):
        return out
    out.append({
        "id": "figure_extract",
        "type": "figure_extract",
        "name": "图片抽取",
    })
    return out


def get_steps(field_config: dict) -> list:
    """返回抽取步骤序列；未配置 steps 时按 fields 合成默认序列（向后兼容）。"""
    steps = field_config.get("steps")
    if steps:
        out = list(steps)
    else:
        fields = field_config.get("fields", {})
        out = [{"id": "entity", "type": "entity", "name": "Stage1 · 样品-状态骨架"}]
        if fields.get("property"):
            out.append({"id": "property", "type": "property", "name": "Stage2 · 性能",
                        "group": "properties", "fields": fields["property"]})
    return _ensure_figure_extract_step(out, field_config)


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


def _figure_slot_value(raw):
    """骨架图字段可能是出处对象；过滤时取裸值。"""
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw


def _figure_bool(raw):
    val = _figure_slot_value(raw)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "y")
    return val


def normalize_figure_type(raw) -> str:
    """把自由文本类型归到白名单枚举（OM/SEM/TEM/EBSD 等）。

    模型常写 optical micrograph / SEM fracture …，而 figure_filter.keep_types
    用短码；不做归一会导致真组织图被整批标成「不在白名单」。
    """
    val = _figure_slot_value(raw)
    if val is None:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    compact = s.upper().replace(" ", "_").replace("-", "_")
    exact = {
        "OM": "OM", "SEM": "SEM", "TEM": "TEM", "EBSD": "EBSD",
        "XRD": "XRD", "SAED": "SAED", "EDS": "EDS", "EDX": "EDX", "EPMA": "EPMA",
        "STRESS_STRAIN_CURVE": "stress_strain_curve",
        "HYSTERESIS_LOOP": "hysteresis_loop",
        "SCHEMATIC": "schematic",
        "OTHER": "other",
    }
    if compact in exact:
        return exact[compact]
    for code, canon in exact.items():
        if compact.startswith(code + "_"):
            return canon
    low = s.lower()

    def _has_token(token: str) -> bool:
        return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", low) is not None

    if _has_token("ebsd"):
        return "EBSD"
    if "transmission electron" in low or _has_token("tem"):
        return "TEM"
    if "scanning electron" in low or _has_token("sem"):
        return "SEM"
    if "xrd" in low or "x-ray" in low or "x ray" in low or "diffraction pattern" in low:
        return "XRD"
    if "saed" in low:
        return "SAED"
    if "optical" in low or "macrograph" in low:
        return "OM"
    if "hysteresis" in low or "b-h" in low or "b–h" in low:
        return "hysteresis_loop"
    if "stress" in low and "strain" in low:
        return "stress_strain_curve"
    if (
        "schematic" in low
        or "diagram" in low
        or "drawing" in low
        or "solidification mode" in low
    ):
        return "schematic"
    if "plot" in low or "curve" in low or "chart" in low or "profile" in low:
        return "other"
    if "color scale" in low or "colorbar" in low or "colour bar" in low:
        return "other"
    return s


def classify_figures(figures: list, field_config: dict, apply_filter: bool) -> tuple[list, list]:
    """按 is_microstructure_image / is_post_test_image 过滤图片。

    不再用 figure_type 白名单做硬过滤（模型常写自由文本，短码对不上会误杀）。
    apply_filter=False 时保留全部（模拟 one-shot）。
    """
    ff = field_config.get("figure_filter", {}) or {}
    # 只认配置里的两个开关；不再读 keep_types / drop_types
    require_micro = bool(ff.get("require_microstructure"))
    drop_post = bool(ff.get("drop_if_post_test"))
    warnings = []
    kept = []
    for fig in figures or []:
        if not apply_filter:
            out = {**fig, "status": "accepted"}
            out.pop("reject_reason", None)
            kept.append(out)
            continue
        ftype = _figure_slot_value(fig.get("figure_type"))
        reason = None
        if require_micro and _figure_bool(fig.get("is_microstructure_image")) is not True:
            reason = "非组织图 is_microstructure_image=false"
        elif drop_post and _figure_bool(fig.get("is_post_test_image")) is True:
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
        out = {**fig, "status": "accepted"}
        out.pop("reject_reason", None)
        kept.append(out)
    return kept, warnings


def _apply_figure_policy(state: dict, apply_rules: bool) -> None:
    """无用户 figure 步时，对 entity.figures 做策略后处理并写入 state。"""
    source = (state.get("entity") or {}).get("figures") or []
    figures, fig_warnings = classify_figures(
        source, state["field_config"], apply_filter=apply_rules)
    state["figures"] = figures
    state["warnings"] = [w for w in state["warnings"] if w.get("type") != "figure_dropped"]
    if apply_rules:
        state["warnings"].extend(fig_warnings)


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


_PATENT_SECTION_TITLES = frozenset({
    "技术领域",
    "背景技术",
    "发明内容",
    "附图说明",
    "具体实施方式",
    "具体实施例",
    "实施方式",
    "权利要求书",
    "摘要",
    "说明书附图",
    "技術領域",
    "背景技術",
    "發明內容",
    "圖式簡單說明",
    "具體實施方式",
    "申請專利範圍",
})

_PATENT_TITLE_LINE_RE = (
    re.compile(r"\[54\]\s*发明名称\s*([^\n]{3,120})"),
    re.compile(r"\(54\)\s*发明名称\s*([^\n]{3,120})"),
    re.compile(r"发明名称\s*[:：]?\s*([^\n]{3,120})"),
)


def paper_title_from_md(text: str) -> str | None:
    """列表展示用标题：专利优先发明名称；跳过「技术领域」等节名。"""
    text = text or ""
    for pat in _PATENT_TITLE_LINE_RE:
        match = pat.search(text)
        if not match:
            continue
        title = re.sub(r"\s+", " ", match.group(1)).strip(" #")
        if title and title not in _PATENT_SECTION_TITLES:
            return title[:120]

    first_heading: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("#"):
            continue
        title = s.lstrip("#").strip()
        if not title:
            continue
        if first_heading is None:
            first_heading = title
        if title in _PATENT_SECTION_TITLES:
            continue
        return title
    return first_heading


def _paper_extract_status(root: Path, project_cfg: dict, paper_id: str) -> tuple[str, str | None, bool, bool]:
    """返回 (latest_status, error, has_any_success, skeleton_done)。

    latest_status: success | failed | none
    has_any_success: 是否存在可复核的合并结果（旧成功 run 仍可进复核侧栏）。
    skeleton_done: 最新 run 是否已写出骨架（entities）。
    """
    runs = list_runs(root, project_cfg, paper_id)
    if not runs:
        return "none", None, False, False
    has_success = False
    for meta in runs:
        if meta.get("status") == "failed":
            continue
        run_dir = Path(root) / project_cfg["test_runs"] / meta["partition"] / meta["run_id"]
        if (run_dir / "merged_outputs" / "paper.json").exists():
            has_success = True
            break
    latest = runs[0]
    skeleton_done = bool(latest.get("skeleton_done"))
    run_dir = Path(root) / project_cfg["test_runs"] / latest["partition"] / latest["run_id"]
    paper_path = run_dir / "merged_outputs" / "paper.json"
    if latest.get("status") == "failed" or not paper_path.exists():
        err = latest.get("error") or "抽取未完成"
        return "failed", str(err), has_success, skeleton_done
    return "success", None, True, skeleton_done


def list_paper_records(root: Path, project_cfg: dict) -> list:
    records = []
    for pid in list_papers(root, project_cfg):
        text = get_paper_text(root, project_cfg, pid) or ""
        status, err, has_success, skeleton_done = _paper_extract_status(root, project_cfg, pid)
        rec = {
            "paper_id": pid,
            "title": paper_title_from_md(text),
            "parsed": True,
            "extracted": has_success,
            "extract_status": status,
            "extract_skeleton_done": skeleton_done,
        }
        if err:
            rec["extract_error"] = err
        records.append(rec)
    return records


def filter_result_by_status(result: dict, include_rejected: bool = True) -> dict:
    """Return a deep copy of result; drop rejected_by_rule props/figures when include_rejected is False."""
    out = copy.deepcopy(result)
    if include_rejected:
        return out
    for cond in out.get("conditions") or []:
        if not isinstance(cond, dict):
            continue
        for key, val in list(cond.items()):
            if not key.endswith("_properties") or not isinstance(val, dict):
                continue
            cond[key] = {
                k: v
                for k, v in val.items()
                if not (isinstance(v, dict) and v.get("status") == "rejected_by_rule")
            }
    figures = out.get("figures")
    if isinstance(figures, list):
        out["figures"] = [
            f for f in figures
            if not (isinstance(f, dict) and f.get("status") == "rejected_by_rule")
        ]
    return out


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
                rec = {"run_id": d.name, "partition": partition, **meta}
                rec["skeleton_done"] = _run_skeleton_done(rec, d)
                runs.append(rec)
    return runs


def _run_skeleton_done(meta: dict, run_dir: Path) -> bool:
    completed = [str(x) for x in (meta.get("completed_steps") or [])]
    if any(sid == "entity" or str(sid).endswith("entity") for sid in completed):
        return True
    ent = run_dir / "entities"
    return ent.is_dir() and any(ent.glob("*.json"))


_ARTIFACT_MAX_CHARS = 200_000
_ARTIFACT_ROOT_FILES = ("RUN_INFO.json", "summary.md")
_ARTIFACT_GROUPS = (
    ("output", ("merged_outputs", "entities", "properties")),
    ("note", ("review_notes",)),
    ("log", ("logs",)),
    ("prompt", ("prompt_preview",)),
)
_ARTIFACT_KIND_RANK = {"output": 0, "note": 1, "log": 2, "meta": 3, "prompt": 4}


def get_run_artifacts(root: Path, project_cfg: dict, paper_id: str, run_id: str) -> dict:
    """返回某 run 的抽取产物（paper.json / entity / properties）及 prompt、失败日志。"""
    paper_id = (paper_id or "").strip()
    run_id = (run_id or "").strip()
    if not paper_id or not run_id:
        raise ValueError("需要 paper_id 与 run_id")
    if Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("非法 run_id")

    runs = list_runs(root, project_cfg, paper_id)
    meta = next((r for r in runs if r.get("run_id") == run_id), None)
    if not meta:
        raise FileNotFoundError(f"未找到该文献下的 run: {run_id}")

    base = (Path(root) / project_cfg.get("test_runs", "")).resolve()
    run_dir = (base / meta["partition"] / run_id).resolve()
    try:
        run_dir.relative_to(base)
    except ValueError as exc:
        raise ValueError("拒绝读取：路径越界") from exc
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run 目录不存在: {run_id}")

    files: list[dict] = []
    candidates: list[tuple[str, Path]] = []
    for name in _ARTIFACT_ROOT_FILES:
        p = run_dir / name
        if p.is_file():
            candidates.append(("meta", p))
    for kind, subs in _ARTIFACT_GROUPS:
        for sub in subs:
            d = run_dir / sub
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.is_file() and p.suffix.lower() in {".txt", ".json", ".md", ".log"}:
                    candidates.append((kind, p))

    seen: set[str] = set()
    for kind, path in candidates:
        rel = path.relative_to(run_dir).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        truncated = False
        if len(text) > _ARTIFACT_MAX_CHARS:
            text = text[:_ARTIFACT_MAX_CHARS]
            truncated = True
        files.append({
            "name": rel,
            "kind": kind,
            "bytes": len(raw),
            "truncated": truncated,
            "text": text,
        })
    files.sort(key=lambda f: (_ARTIFACT_KIND_RANK.get(f.get("kind"), 9), f.get("name") or ""))
    return {
        "run_id": run_id,
        "paper_id": paper_id,
        "partition": meta.get("partition"),
        "run_info": meta,
        "files": files,
    }


def delete_run(root: Path, project_cfg: dict, paper_id: str, run_id: str) -> dict:
    """删除某文献下指定 run 目录（含 analysis）。不碰 parsed_results。"""
    import shutil

    root = Path(root)
    paper_id = (paper_id or "").strip()
    run_id = (run_id or "").strip()
    if not paper_id or not run_id:
        raise ValueError("需要 paper_id 与 run_id")
    if Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("非法 run_id")

    runs = list_runs(root, project_cfg, paper_id)
    meta = next((r for r in runs if r.get("run_id") == run_id), None)
    if not meta:
        raise FileNotFoundError(f"未找到该文献下的 run: {run_id}")

    base = (root / project_cfg.get("test_runs", "")).resolve()
    run_dir = (base / meta["partition"] / run_id).resolve()
    try:
        run_dir.relative_to(base)
    except ValueError as exc:
        raise ValueError("拒绝删除：路径越界") from exc
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run 目录不存在: {run_id}")

    info_path = run_dir / "RUN_INFO.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except Exception:
            info = {}
        if info.get("paper_id") and info.get("paper_id") != paper_id:
            raise ValueError("run 与 paper_id 不匹配，拒绝删除")

    shutil.rmtree(run_dir)
    return {
        "ok": True,
        "paper_id": paper_id,
        "run_id": run_id,
        "partition": meta["partition"],
        "deleted": str(run_dir),
    }


def delete_paper(root: Path, project_cfg: dict, paper_id: str) -> dict:
    """硬删除一篇文献：parsed_results 下该目录 + 该 paper_id 的全部 runs。"""
    import shutil

    root = Path(root)
    paper_id = (paper_id or "").strip()
    if not paper_id or Path(paper_id).name != paper_id or paper_id in (".", ".."):
        raise ValueError("非法 paper_id")

    parsed_key = project_cfg.get("parsed_results") or ""
    if not parsed_key:
        raise ValueError("项目未配置 parsed_results")
    parsed_root = (root / parsed_key).resolve()
    paper_dir = (parsed_root / paper_id).resolve()
    try:
        paper_dir.relative_to(parsed_root)
    except ValueError as exc:
        raise ValueError("拒绝删除：路径越界") from exc

    deleted_runs: list[dict] = []
    for meta in list_runs(root, project_cfg, paper_id):
        deleted_runs.append(delete_run(root, project_cfg, paper_id, meta["run_id"]))

    deleted_parsed = None
    if paper_dir.is_dir():
        shutil.rmtree(paper_dir)
        deleted_parsed = str(paper_dir)
    elif not deleted_runs:
        raise FileNotFoundError(f"文献不存在: {paper_id}")

    return {
        "ok": True,
        "paper_id": paper_id,
        "deleted_parsed": deleted_parsed,
        "deleted_runs": deleted_runs,
    }


def run_id_model_slug(model_id: str | None) -> str:
    """把 model_id 收成可进目录名的片段；缺省为 default。"""
    raw = (model_id or "").strip() or "default"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-_")
    return slug or "default"


def build_run_id(mode: str, model_id: str | None = None,
                 *, stamp: str | None = None, existing: set[str] | None = None) -> str:
    """生成带模式与模型的 run_id：{stamp}_{mode}_{model_slug}[_{n}]。"""
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_part = (mode or "two_stage").strip() or "two_stage"
    slug = run_id_model_slug(model_id)
    base = f"{stamp}_{mode_part}_{slug}"
    if not existing:
        return base
    if base not in existing:
        return base
    n = 1
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def _empty_entity() -> dict:
    return {"paper_metadata": {}, "samples": [], "conditions": [], "figures": []}


def _checkpoint_run(state: dict, *, status: str = "running") -> None:
    """每步成功后把 completed_steps 写入 RUN_INFO，便于失败后续跑。"""
    run_dir = state.get("run_dir")
    if not run_dir:
        return
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    backend = state.get("backend")
    info_path = run_dir / "RUN_INFO.json"
    prev = {}
    if info_path.exists():
        try:
            prev = json.loads(info_path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    info = {
        **prev,
        "run_id": state.get("run_id"),
        "project_id": state.get("project_id"),
        "paper_id": state.get("paper_id"),
        "mode": state.get("mode"),
        "partition": state.get("partition"),
        "backend": getattr(backend, "name", None) or prev.get("backend") or "",
        "created_at": state.get("created_at") or prev.get("created_at"),
        "status": status,
        "completed_steps": list(state.get("completed_steps") or []),
        "invalidated_steps": list(state.get("invalidated_steps") or []),
        "parse_skipped": bool(state.get("parse_skipped", True)),
        "samples": len((state.get("entity") or {}).get("samples") or []),
        "conditions": len((state.get("entity") or {}).get("conditions") or []),
        "template_id": state.get("template_id"),
        "model_id": state.get("model_id") or run_id_model_slug(state.get("model_id")),
    }
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


def find_resumable_run(
    root: Path,
    project_cfg: dict,
    paper_id: str,
    *,
    mode: str = "two_stage",
    partition: str = "test",
    model_id: str | None = None,
) -> str | None:
    """找同篇、同模式、同模型、骨架已完成但未成功结束的 run，供续跑。"""
    want_model = (model_id or "").strip()
    for meta in list_runs(root, project_cfg, paper_id):
        if (meta.get("mode") or "two_stage") != (mode or "two_stage"):
            continue
        if (meta.get("partition") or "test") != (partition or "test"):
            continue
        got_model = (meta.get("model_id") or "").strip()
        if want_model and got_model and want_model != got_model:
            continue
        if meta.get("status") == "success":
            continue
        completed = list(meta.get("completed_steps") or [])
        run_dir = Path(root) / project_cfg.get("test_runs", "") / meta.get("partition", partition) / meta["run_id"]
        has_entity_file = any((run_dir / "entities").glob("*.json")) if (run_dir / "entities").exists() else False
        if "entity" in completed or any(sid.endswith("entity") or sid == "entity" for sid in completed) or has_entity_file:
            # 确认至少有一个 entity 类型步完成，或磁盘已有骨架
            return meta["run_id"]
    return None


def _infer_completed_from_disk(state: dict) -> None:
    """旧失败 run 可能没写 completed_steps，用磁盘产物补齐。"""
    run_dir = Path(state["run_dir"])
    done = list(state.get("completed_steps") or [])
    for step in get_steps(state["field_config"]):
        sid = step.get("id")
        stype = step.get("type")
        if sid in done:
            continue
        if stype == "entity" and (run_dir / "entities" / f"{sid}.json").exists():
            done.append(sid)
        elif stype == "property" and (run_dir / "properties" / f"{sid}_clean.json").exists():
            done.append(sid)
        elif stype in ("figure", "figure_extract") and (
                run_dir / "properties" / f"{sid}_figures.json").exists():
            done.append(sid)
    state["completed_steps"] = done


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
    return [
        s for s in get_steps(field_config)
        if s.get("type") in ("property", "figure", "figure_extract")
    ]


def _merge_figure_rows(batches: list[list]) -> list:
    """按 figure_id / placeholder_index 合并分批结果，后者覆盖前者同键。"""
    by_key: dict = {}
    order: list = []
    for rows in batches:
        for fig in rows or []:
            if not isinstance(fig, dict):
                continue
            key = fig.get("figure_id") or fig.get("placeholder_index") or id(fig)
            if key not in by_key:
                order.append(key)
            by_key[key] = fig
    return [by_key[k] for k in order]


def _run_figure_extract_llm(state: dict, step_id: str) -> list:
    """分批调用 LLM 抽取 figures，返回合并后的原始列表。"""
    images = list(state.get("images_payload") or [])
    field_config = state["field_config"]
    text = state["trimmed_text"]
    entity = state.get("entity") or {}
    run_dir = state["run_dir"]
    batches: list[list] = []
    if not images:
        prompt = build_figure_extract_prompt(field_config, text, entity, None)
        state["prompts"][step_id] = prompt
        (run_dir / "prompt_preview" / f"{step_id}_prompt.txt").write_text(
            prompt, encoding="utf-8")
        raw = _call_backend_json(
            state, "材料文献结构化抽取专家", prompt, None,
            {"stage": "figure_extract", "step_id": step_id, "paper_id": state["paper_id"]},
        )
        return list((raw or {}).get("figures") or [])

    multi = len(images) > FIGURE_EXTRACT_BATCH_SIZE
    for bi in range(0, len(images), FIGURE_EXTRACT_BATCH_SIZE):
        chunk = images[bi:bi + FIGURE_EXTRACT_BATCH_SIZE]
        batch_idx = bi // FIGURE_EXTRACT_BATCH_SIZE
        labels = [str(im.get("label") or f"Image {bi + j}") for j, im in enumerate(chunk)]
        prompt = build_figure_extract_prompt(field_config, text, entity, labels)
        prompt_name = (
            f"{step_id}_batch{batch_idx}_prompt.txt" if multi else f"{step_id}_prompt.txt"
        )
        if batch_idx == 0:
            state["prompts"][step_id] = prompt
        (run_dir / "prompt_preview" / prompt_name).write_text(prompt, encoding="utf-8")
        hint_step = f"{step_id}_batch{batch_idx}" if multi else step_id
        raw = _call_backend_json(
            state, "材料文献结构化抽取专家", prompt, chunk,
            {
                "stage": "figure_extract",
                "step_id": hint_step,
                "paper_id": state["paper_id"],
            },
        )
        (run_dir / "properties" / f"{hint_step}_raw.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        batches.append(list((raw or {}).get("figures") or []))
    return _merge_figure_rows(batches)


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
        elif stype in ("figure", "figure_extract"):
            fig_path = run_dir / "properties" / f"{sid}_figures.json"
            if fig_path.exists():
                try:
                    figures = json.loads(fig_path.read_text(encoding="utf-8"))
                except Exception:
                    figures = []
    state["property_groups"] = property_groups
    steps_now = get_steps(state["field_config"])
    if not any(s.get("type") in ("figure", "figure_extract") for s in steps_now):
        figures = entity.get("figures", [])
    state["figures"] = figures


def _write_run_outputs(state: dict) -> dict:
    """合并结果并写 paper.json / RUN_INFO / summary，返回 result。"""
    steps = get_steps(state["field_config"])
    entity, bind_warnings = bind_condition_sample_ids(state.get("entity") or {})
    state["entity"] = entity
    # 保留 Stage1 已记录的自动补全审计；只刷新仍未绑定/无效的告警
    prev = state.get("warnings") or []
    state["warnings"] = [
        w for w in prev
        if w.get("type") not in ("condition_missing_sample_id", "condition_invalid_sample_id")
    ]
    seen = {
        (w.get("type"), w.get("condition_id"))
        for w in state["warnings"]
        if w.get("type") in _BIND_WARNING_TYPES
    }
    for w in bind_warnings:
        key = (w.get("type"), w.get("condition_id"))
        if key in seen:
            continue
        state["warnings"].append(w)
        seen.add(key)
    property_groups = state["property_groups"]
    has_fig_llm = any(s.get("type") in ("figure", "figure_extract") for s in steps)
    if not has_fig_llm:
        _apply_figure_policy(state, state["apply_rules"])
    elif not state.get("figures") and (state.get("entity") or {}).get("figures"):
        _apply_figure_policy(state, state["apply_rules"])
    figures = state["figures"]

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
        "status": "success",
        "steps": len(steps),
        "samples": len(result.get("samples", [])),
        "conditions": len(result.get("conditions", [])),
        "figures": len(result.get("figures", [])),
        "warnings": len(warnings),
        "template_id": state.get("template_id"),
        "completed_steps": list(state.get("completed_steps") or []),
        "invalidated_steps": list(state.get("invalidated_steps") or []),
        "parse_skipped": bool(state.get("parse_skipped", True)),
        "model_id": state.get("model_id") or run_id_model_slug(state.get("model_id")),
    }
    state["run_info"] = run_info
    (run_dir / "RUN_INFO.json").write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(
        _build_summary_md(run_info, state["trim_stats"], warnings), encoding="utf-8")
    return result


def _prepare_run(root: Path, project_id: str, paper_id: str, *,
                 mode: str = "two_stage", partition: str = "test",
                 model_id: str | None = None, run_id: str | None = None,
                 cancel_check=None) -> dict:
    """建/接 run 目录、解析文本、trim；返回可执行步骤的 run_state。"""
    root = Path(root)
    ws_cfg = load_workspace_config(root)
    project_cfg = ws_cfg["projects"].get(project_id)
    if not project_cfg:
        raise ValueError(f"未知项目: {project_id}")
    model_name, model_base = resolve_model_endpoint(ws_cfg, model_id)

    field_config = load_field_config(root, project_cfg)
    parsed_dir = _resolve_parsed_dir(root, project_cfg)
    paper_md = parsed_dir / paper_id / "paper.md"
    if not paper_md.exists():
        raise FileNotFoundError(f"paper.md 不存在: {paper_md}")

    backend = get_backend(
        project_cfg.get("backend", "claude"),
        root,
        model=model_name,
        base_url=model_base,
    )
    apply_rules = mode != "single_pass"

    parsed = parse_paper_md(paper_id, paper_md)
    kind = project_document_kind(root, project_cfg)
    trimmed_text, trim_stats = prepare_model_text(
        parsed.text_with_placeholders, kind, paper_id=paper_id
    )
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
        runs_base = Path(root) / project_cfg["test_runs"] / partition
        existing = {p.name for p in runs_base.iterdir()} if runs_base.is_dir() else set()
        run_id = build_run_id(mode, model_id, existing=existing)
        run_dir = runs_base / run_id

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
        "cancel_check": cancel_check,
    }
    if resume:
        _load_run_artifacts(state)
        _infer_completed_from_disk(state)
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
    _raise_if_cancelled(state)
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
        # 骨架不传图、不抽 figures，降低截断 / 503
        ent = _call_backend_json(
            state, "材料文献结构化抽取专家", prompt, None,
            {"stage": "entity", "step_id": sid, "paper_id": paper_id},
        )
        ent = normalize_entity_provenance(ent if isinstance(ent, dict) else {})
        ent, bind_warnings = bind_condition_sample_ids(ent)
        entity = _empty_entity()
        if ent.get("paper_metadata"):
            entity["paper_metadata"].update(ent.get("paper_metadata") or {})
        entity["samples"].extend(ent.get("samples") or [])
        entity["conditions"].extend(ent.get("conditions") or [])
        # 忽略模型若仍返回的 figures；图片改由 figure_extract 步处理
        entity["figures"] = []
        state["entity"] = entity
        state["figures"] = []
        state["condition_ids"] = [c.get("condition_id") for c in entity["conditions"]]
        state["warnings"] = [
            w for w in state.get("warnings") or []
            if w.get("type") not in _BIND_WARNING_TYPES
        ]
        state["warnings"].extend(bind_warnings)
        (run_dir / "entities" / f"{sid}.json").write_text(
            json.dumps({k: ent.get(k) for k in ("paper_metadata", "samples", "conditions")
                        if k in ent}, ensure_ascii=False, indent=2), encoding="utf-8")
        state["step_reports"].append({
            "id": sid, "name": sname, "type": stype,
            "output": {"samples": entity["samples"], "conditions": entity["conditions"]},
            "warnings": bind_warnings,
        })

    elif stype == "property":
        if mode == "entity_only":
            return
        group = step.get("group", "properties")
        prompt = build_property_prompt(
            field_config, step,
            condition_skeleton_from_entity(state.get("entity") or {}),
            state["trimmed_text"])
        state["prompts"][sid] = prompt
        (run_dir / "prompt_preview" / f"{sid}_prompt.txt").write_text(prompt, encoding="utf-8")
        raw = _call_backend_json(
            state, "材料文献结构化抽取专家", prompt, None,
            {"stage": "property", "step_id": sid, "paper_id": paper_id},
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

    elif stype == "figure_extract":
        if mode == "entity_only":
            return
        raw_figs = _run_figure_extract_llm(state, sid)
        state["entity"]["figures"] = raw_figs
        figures, fig_warnings = classify_figures(
            raw_figs, field_config, apply_filter=apply_rules)
        state["figures"] = figures
        state["warnings"] = [w for w in state["warnings"] if w.get("type") != "figure_dropped"]
        if apply_rules:
            state["warnings"].extend(fig_warnings)
        (run_dir / "properties" / f"{sid}_figures.json").write_text(
            json.dumps(figures, ensure_ascii=False, indent=2), encoding="utf-8")
        state["step_reports"].append({
            "id": sid, "name": sname, "type": stype,
            "output": figures, "warnings": fig_warnings if apply_rules else [],
        })

    elif stype == "figure":
        # 兼容旧 run：仅规则过滤，不再作为主抽图路径
        figures, fig_warnings = classify_figures(
            state["entity"].get("figures", []), field_config, apply_filter=apply_rules)
        state["figures"] = figures
        state["warnings"] = [w for w in state["warnings"] if w.get("type") != "figure_dropped"]
        if apply_rules:
            state["warnings"].extend(fig_warnings)
        state["prompts"][sid] = "（图片分类为确定性规则步骤：按 is_microstructure_image / is_post_test_image 过滤，非 LLM prompt）"
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
    _checkpoint_run(state)


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
            elif stype in ("figure", "figure_extract") and (
                    state["run_dir"] / "properties" / f"{sid}_figures.json").exists():
                invalidated.append(sid)

    _clear_properties_dir(state["run_dir"])
    state["property_groups"] = {}
    if isinstance(state.get("entity"), dict):
        state["entity"]["figures"] = []
    state["figures"] = []
    state["warnings"] = [
        w for w in state["warnings"]
        if w.get("type") not in ("property_source_rejected", "figure_dropped")
    ]
    state["completed_steps"] = [sid for sid in state["completed_steps"] if sid not in down_ids]
    state["invalidated_steps"] = list(invalidated)
    return invalidated



def dump_llm_failure(run_dir: Path | str | None, step_id: str, exc: BaseException) -> dict:
    """失败时落盘完整 raw 与 stop_reason；返回写入的相对路径信息。"""
    if not run_dir:
        return {}
    run_dir = Path(run_dir)
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    sid = (step_id or "llm").strip() or "llm"
    written: dict = {"step_id": sid}

    raw = getattr(exc, "raw_text", None)
    if raw is None:
        raw = getattr(exc, "response_body", None)
    if raw is not None:
        raw_path = logs / f"{sid}_llm_raw.txt"
        raw_path.write_text(str(raw), encoding="utf-8")
        written["raw"] = str(raw_path)

    meta = {
        "error": str(exc),
        "error_type": type(exc).__name__,
        "stop_reason": getattr(exc, "stop_reason", None),
        "http_status": getattr(exc, "http_status", None),
    }
    meta_path = logs / f"{sid}_llm_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    written["meta"] = str(meta_path)
    return written


def _call_backend_json(state: dict, system_prompt: str, text_prompt: str,
                       images: list | None, hint: dict | None) -> dict:
    hint = dict(hint or {})
    sid = hint.get("step_id") or hint.get("stage") or hint.get("field_id") or "llm"
    stage = str(hint.get("stage") or "")
    attempts = STEP_LLM_MAX_ATTEMPTS if stage in _RETRYABLE_STAGES else 1
    last_exc: BaseException | None = None
    for i in range(1, attempts + 1):
        _raise_if_cancelled(state)
        try:
            return state["backend"].call_json(system_prompt, text_prompt, images, hint)
        except Exception as exc:
            last_exc = exc
            dump_name = str(sid) if attempts == 1 or i == attempts else f"{sid}_try{i}"
            dump_llm_failure(state.get("run_dir"), dump_name, exc)
            if i >= attempts:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("LLM 调用失败")


def _write_failed_run(state: dict, exc: BaseException) -> None:
    """抽取中途失败时落 RUN_INFO，便于文献表标「抽取失败」并支持重新抽取。"""
    run_dir = state.get("run_dir")
    if not run_dir:
        return
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "review_notes").mkdir(parents=True, exist_ok=True)
    backend = state.get("backend")
    run_info = {
        "run_id": state.get("run_id"),
        "project_id": state.get("project_id"),
        "paper_id": state.get("paper_id"),
        "mode": state.get("mode"),
        "partition": state.get("partition"),
        "backend": getattr(backend, "name", None) or str(backend or ""),
        "created_at": state.get("created_at") or datetime.now().isoformat(timespec="seconds"),
        "status": "cancelled" if isinstance(exc, RunCancelled) else "failed",
        "error": str(exc),
        "completed_steps": list(state.get("completed_steps") or []),
        "invalidated_steps": list(state.get("invalidated_steps") or []),
        "parse_skipped": bool(state.get("parse_skipped", True)),
        "samples": len((state.get("entity") or {}).get("samples") or []),
        "conditions": len((state.get("entity") or {}).get("conditions") or []),
        "figures": 0,
        "warnings": len(state.get("warnings") or []),
        "template_id": state.get("template_id"),
        "model_id": state.get("model_id") or run_id_model_slug(state.get("model_id")),
    }
    stop_reason = getattr(exc, "stop_reason", None)
    if stop_reason:
        run_info["stop_reason"] = stop_reason
    http_status = getattr(exc, "http_status", None)
    if http_status is not None:
        run_info["http_status"] = http_status
    (run_dir / "RUN_INFO.json").write_text(
        json.dumps(run_info, ensure_ascii=False, indent=2), encoding="utf-8")
    state["run_info"] = run_info


def run_extraction(root: Path, project_id: str, paper_id: str,
                   mode: str = "two_stage", partition: str = "test",
                   model_id: str | None = None, run_id: str | None = None,
                   force_new: bool = False, cancel_check=None) -> dict:
    state = None
    try:
        root = Path(root)
        ws_cfg = load_workspace_config(root)
        project_cfg = ws_cfg["projects"].get(project_id)
        if not project_cfg:
            raise ValueError(f"未知项目: {project_id}")
        resume_id = None if force_new else run_id
        if not resume_id and not force_new:
            resume_id = find_resumable_run(
                root, project_cfg, paper_id,
                mode=mode, partition=partition, model_id=model_id,
            )
        state = _prepare_run(
            root, project_id, paper_id, mode=mode, partition=partition,
            model_id=model_id, run_id=resume_id, cancel_check=cancel_check)
        steps = get_steps(state["field_config"])
        skipped: list[str] = []
        for step in steps:
            if mode == "entity_only" and step.get("type") != "entity":
                continue
            sid = step.get("id")
            if state.get("resume") and sid in (state.get("completed_steps") or []):
                skipped.append(sid)
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
            "resumed": bool(state.get("resume")),
            "skipped_steps": skipped,
        }
    except Exception as exc:
        if state is not None:
            _write_failed_run(state, exc)
            try:
                exc.run_id = state.get("run_id")
                exc.skeleton_done = _skeleton_done(state)
            except Exception:
                pass
        raise


def run_step(root: Path, project_id: str, paper_id: str, step_id: str,
             run_id: str | None = None, partition: str = "test",
             model_id: str | None = None, cancel_check=None) -> dict:
    """分阶段执行单个步骤；重跑骨架时作废并自动重跑全部下游。"""
    state = None
    try:
        state = _prepare_run(
            root, project_id, paper_id,
            mode="two_stage", partition=partition, model_id=model_id, run_id=run_id,
            cancel_check=cancel_check)
        step = _find_step(state["field_config"], step_id)
        stype = step.get("type")
        invalidated: list = []

        if stype in ("property", "figure", "figure_extract") and not _skeleton_done(state):
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
    except Exception as exc:
        if state is not None:
            _write_failed_run(state, exc)
            try:
                exc.run_id = state.get("run_id")
                exc.skeleton_done = _skeleton_done(state)
            except Exception:
                pass
        raise


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
    ws_cfg = load_workspace_config(root)
    model_name, model_base = resolve_model_endpoint(ws_cfg, model_id)
    backend = get_backend(
        project_cfg.get("backend", "claude"),
        root,
        model=model_name,
        base_url=model_base,
    )

    text_path = run_dir / "inputs" / "parsed_text.txt"
    if text_path.exists():
        trimmed_text = text_path.read_text(encoding="utf-8", errors="replace")
    else:
        raw = get_paper_text(root, project_cfg, paper_id) or ""
        kind = project_document_kind(root, project_cfg)
        trimmed_text, _ = prepare_model_text(raw, kind, paper_id=paper_id)

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
            condition_ids = condition_skeleton_from_entity(result)
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
