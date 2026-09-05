"""Template / field library / project overlay config model."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.provenance import is_identity_field, value_shape

_FIELD_KEYS = (
    "id",
    "label",
    "category",
    "group",
    "origin",
    "value_type",
    "rule",
    "positive_examples",
    "negative_examples",
    "note",
)

LOCKED_FIELD_IDS = ("sample_id", "condition_id", "figure_id", "placeholder_index")
PROTECTED_PROJECT_IDS = frozenset({"demo_steel"})

_DOI_IDENTIFIER = {
    "id": "doi",
    "label": "DOI",
    "category": "metadata",
    "group": None,
    "value_type": "string",
    "rule": "填写文献 DOI；可从目录名/paper_id 推断，不要编造。",
    "positive_examples": "10.1016/j.msea.2005.04.015",
    "negative_examples": "不要填期刊名或站点首页",
    "note": "文章级标识，全篇只出现一次。",
}

_PATENT_NUMBER_IDENTIFIER = {
    "id": "patent_number",
    "label": "专利号",
    "category": "metadata",
    "group": None,
    "value_type": "string",
    "rule": "填写专利号（如 CN110218899B）；可从目录名/paper_id 推断，不要编造。",
    "positive_examples": "CN110218899B",
    "negative_examples": "不要填 DOI",
    "note": "文章级标识，全篇只出现一次。",
}


def apply_document_kind_identifier(overlay: dict) -> dict:
    """按 document_kind 互斥保留 doi 或 patent_number（私有 metadata）。原地修改并返回 overlay。"""
    try:
        from input_trim import normalize_document_kind
    except ImportError:
        from tools.input_trim import normalize_document_kind

    kind = normalize_document_kind(overlay.get("document_kind"))
    overlay["document_kind"] = kind
    want = "doi" if kind == "paper" else "patent_number"
    drop = "patent_number" if kind == "paper" else "doi"
    spec = _DOI_IDENTIFIER if want == "doi" else _PATENT_NUMBER_IDENTIFIER

    selected = [x for x in (overlay.get("selected_field_ids") or []) if x != drop]
    private = [f for f in (overlay.get("private_fields") or []) if f.get("id") != drop]
    overrides = dict(overlay.get("field_overrides") or {})
    overrides.pop(drop, None)

    has_want = any(f.get("id") == want for f in private)
    if not has_want:
        private.append(dict(spec))
    if want not in selected:
        if "title" in selected:
            idx = selected.index("title") + 1
            selected.insert(idx, want)
        else:
            selected.insert(0, want)

    overlay["selected_field_ids"] = selected
    overlay["private_fields"] = private
    overlay["field_overrides"] = overrides
    return overlay


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_template(root: Path, template_id: str) -> dict:
    path = root / "configs" / "templates" / f"{template_id}.json"
    return _read_json(path)


def load_field_library(root: Path, template_id: str) -> dict:
    if template_id == "blank":
        return {"fields": []}
    path = root / "configs" / "field_library" / f"{template_id}.json"
    return _read_json(path)


def load_overlay(root: Path, project_id: str) -> dict:
    path = root / "configs" / "projects" / f"{project_id}.json"
    return _read_json(path)


def _normalize_field(base: dict, overrides: dict | None, origin: str) -> dict:
    merged = {**base, **(overrides or {})}
    out = {k: merged.get(k) for k in _FIELD_KEYS if k != "origin"}
    out["origin"] = origin
    return out


def effective_fields(library: dict, overlay: dict) -> list[dict]:
    by_id = {f["id"]: f for f in library.get("fields", [])}
    overrides = overlay.get("field_overrides") or {}
    selected = overlay.get("selected_field_ids") or []
    result: list[dict] = []
    for fid in selected:
        if fid not in by_id:
            continue
        result.append(_normalize_field(by_id[fid], overrides.get(fid), "library"))
    for priv in overlay.get("private_fields") or []:
        result.append(_normalize_field(priv, None, "private"))
    return result


def identity_field_ids(template: dict) -> set[str]:
    return set(template.get("identity_fields") or [])


def merged_property_groups(template: dict, overlay: dict) -> list[dict]:
    """模板大类顺序 + 覆盖层自建大类；同 id 以模板为准。"""
    seen: set[str] = set()
    out: list[dict] = []
    for g in list(template.get("property_groups") or []) + list(overlay.get("property_groups") or []):
        gid = g.get("id")
        if not gid or gid in seen:
            continue
        seen.add(gid)
        out.append(g)
    return out


def generate_steps(template: dict, fields: list[dict], overlay: dict) -> list[dict]:
    if overlay.get("steps"):
        return list(overlay["steps"])

    overrides = overlay.get("step_overrides")
    if overrides:
        steps = list(overrides)
        entity_idx = next((i for i, s in enumerate(steps) if s.get("type") == "entity"), None)
        if entity_idx is None:
            raise ValueError("骨架步必须先于性能和图片")
        for i, s in enumerate(steps):
            if s.get("type") in ("property", "figure") and i < entity_idx:
                raise ValueError("骨架步必须先于性能和图片")
        return steps

    steps: list[dict] = [{"id": "entity", "type": "entity", "name": "骨架"}]

    group_fields: dict[str, list[str]] = {}
    for f in fields:
        if f.get("category") != "property":
            continue
        g = f.get("group")
        if g:
            group_fields.setdefault(g, []).append(f["id"])

    groups = merged_property_groups(template, overlay)
    group_names = {g["id"]: g.get("name", g["id"]) for g in groups}
    for ginfo in groups:
        gid = ginfo["id"]
        if gid not in group_fields:
            continue
        step_id = gid.removesuffix("_properties")
        steps.append(
            {
                "id": step_id,
                "type": "property",
                "name": group_names.get(gid, gid),
                "group": gid,
                "fields": group_fields[gid],
            }
        )

    return steps


def assign_property_to_stage(stages: list, field: dict, group_names: dict) -> list:
    stages = [dict(s, fields=list(s.get("fields") or [])) for s in (stages or [])]
    fid = field["id"]
    group = field.get("group") or ""
    if any(fid in (s.get("fields") or []) for s in stages):
        return stages
    target = None
    if group:
        target = next((s for s in stages if s.get("group") == group), None)
    elif not group:
        target = next((s for s in stages if s.get("id") == "other"), None)
        if target is None:
            target = {
                "id": "other",
                "type": "property",
                "name": "其他性能",
                "group": "other_properties",
                "fields": [],
            }
            stages.append(target)
    if target is None:
        base_id = group.removesuffix("_properties") if group else "other"
        step_id = base_id
        existing = {s.get("id") for s in stages}
        n = 2
        while step_id in existing:
            step_id = f"{base_id}_{n}"
            n += 1
        target = {
            "id": step_id,
            "type": "property",
            "name": group_names.get(group, group or "其他性能"),
            "group": group or "other_properties",
            "fields": [],
        }
        stages.append(target)
    if fid not in target["fields"]:
        target["fields"].append(fid)
    return stages


def strip_empty_property_steps(steps: list) -> list:
    out = []
    for s in steps or []:
        if s.get("type") == "property" and not list(s.get("fields") or []):
            continue
        out.append(s)
    return out


def validate_overlay_stages(overlay: dict, fields: list[dict]) -> None:
    steps = strip_empty_property_steps(overlay.get("steps") or [])
    overlay["steps"] = steps
    if not steps:
        return

    if any(s.get("type") == "figure" for s in steps):
        raise ValueError("阶段计划禁止包含 type=figure 的图片过滤步")

    entity_idxs = [i for i, s in enumerate(steps) if s.get("type") == "entity"]
    if len(entity_idxs) != 1 or entity_idxs[0] != 0:
        raise ValueError("骨架步必须位于第一且唯一")

    assigned: list[str] = []
    for s in steps:
        if s.get("type") != "property":
            continue
        fl = list(s.get("fields") or [])
        assigned.extend(fl)

    if len(assigned) != len(set(assigned)):
        raise ValueError("性能字段不能重复挂阶段")

    property_ids = {f["id"] for f in fields if f.get("category") == "property"}
    assigned_set = set(assigned)
    unassigned = sorted(property_ids - assigned_set)
    if unassigned:
        raise ValueError(f"未挂阶段: {', '.join(unassigned)}")
    extra = sorted(assigned_set - property_ids)
    if extra:
        raise ValueError(f"阶段含未知或非性能字段: {', '.join(extra)}")


def save_overlay(root: Path, project_id: str, overlay: dict) -> None:
    try:
        from input_trim import normalize_document_kind
    except ImportError:
        from tools.input_trim import normalize_document_kind

    overlay["document_kind"] = normalize_document_kind(overlay.get("document_kind"))
    apply_document_kind_identifier(overlay)
    if overlay.get("steps"):
        overlay["steps"] = strip_empty_property_steps(overlay["steps"])
        template_id = overlay.get("template_id") or "blank"
        library = load_field_library(root, template_id)
        fields = effective_fields(library, overlay)
        validate_overlay_stages(overlay, fields)
    path = root / "configs" / "projects" / f"{project_id}.json"
    _write_json(path, overlay)


def writeback_library_field(root: Path, template_id: str, field: dict) -> None:
    path = root / "configs" / "field_library" / f"{template_id}.json"
    lib = _read_json(path)
    fields = lib.setdefault("fields", [])
    fid = field["id"]
    for i, existing in enumerate(fields):
        if existing.get("id") == fid:
            updated = {**existing, **field}
            fields[i] = updated
            break
    else:
        fields.append(field)
    _write_json(path, lib)


def promote_private_field(root: Path, project_id: str, field_id: str) -> dict:
    overlay = load_overlay(root, project_id)
    private = list(overlay.get("private_fields") or [])
    match = None
    remaining = []
    for f in private:
        if f.get("id") == field_id:
            match = f
        else:
            remaining.append(f)
    if match is None:
        raise ValueError(f"private field not found: {field_id}")

    template_id = overlay["template_id"]
    if template_id == "blank":
        raise ValueError("空模板没有公共字段库，私有字段不能提升入库")

    lib_field = {k: match.get(k) for k in (
        "id", "label", "category", "group", "value_type",
        "rule", "positive_examples", "negative_examples", "note",
    )}
    writeback_library_field(root, template_id, lib_field)

    selected = list(overlay.get("selected_field_ids") or [])
    if field_id not in selected:
        selected.append(field_id)
    overlay["selected_field_ids"] = selected
    overlay["private_fields"] = remaining
    save_overlay(root, project_id, overlay)
    return overlay


def create_project(
    root: Path,
    project_id: str,
    name: str,
    template_id: str,
    selected_field_ids: list[str],
    document_kind: str | None = None,
    copy_from: str | None = None,
) -> dict:
    try:
        from input_trim import normalize_document_kind
    except ImportError:
        from tools.input_trim import normalize_document_kind

    project_id = (project_id or "").strip()
    if not project_id:
        raise ValueError("需要项目 ID")
    kind = normalize_document_kind(document_kind)
    copy_from = (copy_from or "").strip() or None
    if copy_from == project_id:
        raise ValueError("不能复制到相同项目 id")

    if copy_from:
        cfg_path = root / "configs" / "project_config.json"
        cfg = _read_json(cfg_path) if cfg_path.exists() else {"projects": {}}
        if copy_from not in (cfg.get("projects") or {}):
            raise ValueError(f"复制来源不存在: {copy_from}")
        src_path = root / "configs" / "projects" / f"{copy_from}.json"
        if not src_path.exists():
            raise ValueError(f"复制来源不存在: {copy_from}")
        src = _read_json(src_path)
        template_id = src.get("template_id") or "steel"
        overlay = {
            "template_id": template_id,
            "selected_field_ids": list(src.get("selected_field_ids") or []),
            "private_fields": deepcopy(src.get("private_fields") or []),
            "field_overrides": deepcopy(src.get("field_overrides") or {}),
            "steps": deepcopy(src.get("steps") or []),
            "step_overrides": deepcopy(src.get("step_overrides")),
            "property_groups": deepcopy(src.get("property_groups") or []),
            "property_source": deepcopy(src.get("property_source") or {}),
            "figure_filter": deepcopy(src.get("figure_filter") or {}),
            "document_kind": kind,
        }
    else:
        overlay = {
            "template_id": template_id,
            "selected_field_ids": list(selected_field_ids),
            "private_fields": [],
            "field_overrides": {},
            "step_overrides": None,
            "property_source": {},
            "figure_filter": {},
            "document_kind": kind,
        }

    library = load_field_library(root, overlay["template_id"])
    lib_ids = {f["id"] for f in library.get("fields") or []}
    selected = list(overlay.get("selected_field_ids") or [])
    for lid in LOCKED_FIELD_IDS:
        if lid in lib_ids and lid not in selected:
            selected.append(lid)
    overlay["selected_field_ids"] = selected
    apply_document_kind_identifier(overlay)
    template = load_template(root, overlay["template_id"])
    fields = effective_fields(library, overlay)
    if not overlay.get("steps"):
        overlay["steps"] = generate_steps(template, fields, overlay)
    # 校验在写盘前完成；失败不落任何新文件
    save_overlay(root, project_id, overlay)

    cfg_path = root / "configs" / "project_config.json"
    cfg = _read_json(cfg_path) if cfg_path.exists() else {"projects": {}}
    projects = cfg.setdefault("projects", {})
    projects[project_id] = {
        "name": name,
        "runnable": True,
        "backend": "mock",
        "template_id": overlay["template_id"],
        "overlay": f"configs/projects/{project_id}.json",
        "field_config": f"configs/projects/{project_id}.json",
        "parsed_results": f"parsed_results/{project_id}",
        "test_runs": f"test_runs/{project_id}",
    }
    _write_json(cfg_path, cfg)
    return overlay


def delete_project(root: Path, project_id: str) -> dict:
    """硬删除项目：配置键、overlay、parsed_results、test_runs。示例项目不可删。"""
    import shutil

    root = Path(root).resolve()
    project_id = (project_id or "").strip()
    if not project_id or Path(project_id).name != project_id or project_id in (".", ".."):
        raise ValueError("非法项目 ID")
    if project_id in PROTECTED_PROJECT_IDS:
        raise ValueError("示例项目不可删除")

    cfg_path = root / "configs" / "project_config.json"
    if not cfg_path.exists():
        raise FileNotFoundError("project_config.json 不存在")
    cfg = _read_json(cfg_path)
    projects = cfg.get("projects") or {}
    if project_id not in projects:
        raise FileNotFoundError(f"项目不存在: {project_id}")
    entry = projects[project_id] or {}
    deleted: list[str] = []

    def _safe_rmtree(rel: str, *, allow_example_data: bool = False) -> None:
        if not rel:
            return
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"拒绝删除：路径越界 {rel}") from exc
        if not allow_example_data:
            example_root = (root / "example_data").resolve()
            try:
                target.relative_to(example_root)
            except ValueError:
                pass
            else:
                raise ValueError(f"拒绝删除 example_data 下路径: {rel}")
        if target.is_dir():
            shutil.rmtree(target)
            deleted.append(str(target))
        elif target.is_file():
            target.unlink()
            deleted.append(str(target))

    _safe_rmtree(entry.get("parsed_results") or f"parsed_results/{project_id}")
    _safe_rmtree(entry.get("test_runs") or f"test_runs/{project_id}")

    overlay_rel = entry.get("overlay") or f"configs/projects/{project_id}.json"
    field_rel = entry.get("field_config") or overlay_rel
    _safe_rmtree(overlay_rel)
    if field_rel and field_rel != overlay_rel:
        still_used = any(
            (p or {}).get("field_config") == field_rel
            for pid, p in projects.items()
            if pid != project_id
        )
        if not still_used:
            _safe_rmtree(field_rel)

    del projects[project_id]
    cfg["projects"] = projects
    _write_json(cfg_path, cfg)
    deleted.append(f"project_config:{project_id}")
    return {"ok": True, "project_id": project_id, "deleted": deleted}


_CATEGORY_ORDER = ("metadata", "sample", "condition", "property", "figure")


def _field_slot(template: dict, field: dict) -> Any:
    if is_identity_field(template, field):
        return ""
    return value_shape(field)


def build_output_schema(template: dict, fields: list[dict]) -> dict:
    by_cat: dict[str, list[dict]] = {}
    for f in fields:
        by_cat.setdefault(f.get("category") or "", []).append(f)

    layers_by_id = {layer["id"]: layer for layer in template.get("layers") or []}

    paper_metadata: dict[str, Any] = {}
    for f in by_cat.get("metadata", []):
        paper_metadata[f["id"]] = _field_slot(template, f)

    sample_obj: dict[str, Any] = {}
    sample_layer = layers_by_id.get("sample") or {}
    if sample_layer.get("id_field"):
        sample_obj[sample_layer["id_field"]] = ""
    for f in by_cat.get("sample", []):
        sample_obj[f["id"]] = _field_slot(template, f)

    condition_obj: dict[str, Any] = {}
    condition_layer = layers_by_id.get("condition") or {}
    if condition_layer.get("id_field"):
        condition_obj[condition_layer["id_field"]] = ""
    if condition_layer.get("parent_id_field"):
        condition_obj[condition_layer["parent_id_field"]] = ""
    for f in by_cat.get("condition", []):
        condition_obj[f["id"]] = _field_slot(template, f)

    for f in by_cat.get("property", []):
        group = f.get("group")
        if not group:
            continue
        bucket = condition_obj.setdefault(group, {})
        bucket[f["id"]] = _field_slot(template, f)

    figure_obj: dict[str, Any] = {}
    figure_layer = layers_by_id.get("figure") or {}
    for rf in figure_layer.get("ref_fields") or []:
        figure_obj[rf] = ""
    for f in by_cat.get("figure", []):
        figure_obj[f["id"]] = _field_slot(template, f)

    return {
        "paper_metadata": paper_metadata,
        "samples": [sample_obj],
        "conditions": [condition_obj],
        "figures": [figure_obj],
    }


def _sort_export_fields(template: dict, fields: list[dict]) -> list[dict]:
    cat_rank = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    group_rank = {
        g["id"]: i for i, g in enumerate(template.get("property_groups") or [])
    }

    def key(f: dict) -> tuple:
        cat = f.get("category") or ""
        c = cat_rank.get(cat, 99)
        g = group_rank.get(f.get("group") or "", 99) if cat == "property" else 0
        return (c, g, f.get("id") or "")

    return sorted(fields, key=key)


def export_project(root: Path, project_id: str) -> dict:
    overlay = load_overlay(root, project_id)
    template_id = overlay["template_id"]
    template = load_template(root, template_id)
    library = load_field_library(root, template_id)
    fields = effective_fields(library, overlay)
    steps = generate_steps(template, fields, overlay)
    schema = build_output_schema(template, fields)
    return {
        "project_id": project_id,
        "template_id": template_id,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "fields": _sort_export_fields(template, fields),
        "steps": steps,
        "schema": schema,
    }
