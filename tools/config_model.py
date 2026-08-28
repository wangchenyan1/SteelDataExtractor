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


def generate_steps(template: dict, fields: list[dict], overlay: dict) -> list[dict]:
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
        g = f.get("group")
        if g:
            group_fields.setdefault(g, []).append(f["id"])

    group_names = {g["id"]: g.get("name", g["id"]) for g in template.get("property_groups") or []}
    for ginfo in template.get("property_groups") or []:
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

    if any(f.get("category") == "figure" for f in fields):
        steps.append({"id": "figures", "type": "figure", "name": "图片过滤"})

    return steps


def save_overlay(root: Path, project_id: str, overlay: dict) -> None:
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
) -> dict:
    overlay = {
        "template_id": template_id,
        "selected_field_ids": list(selected_field_ids),
        "private_fields": [],
        "field_overrides": {},
        "step_overrides": None,
        "property_source": {},
        "figure_filter": {},
    }
    save_overlay(root, project_id, overlay)

    cfg_path = root / "configs" / "project_config.json"
    cfg = _read_json(cfg_path) if cfg_path.exists() else {"projects": {}}
    projects = cfg.setdefault("projects", {})
    projects[project_id] = {
        "name": name,
        "runnable": True,
        "backend": "mock",
        "template_id": template_id,
        "overlay": f"configs/projects/{project_id}.json",
        "field_config": f"configs/projects/{project_id}.json",
        "parsed_results": f"parsed_results/{project_id}",
        "test_runs": f"test_runs/{project_id}",
    }
    _write_json(cfg_path, cfg)
    return overlay


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
