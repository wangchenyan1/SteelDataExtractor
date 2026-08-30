"""????????????????? run ????? app.js ??????"""

from __future__ import annotations

from typing import Any


def _slot_value(raw: Any) -> Any:
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw


def _fact_display(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict) and ("value" in raw or "excerpt" in raw):
        val = raw.get("value")
        text = "" if val is None else str(val)
        status = raw.get("status") or ""
        return f"{text} [{status}]" if status else text
    if isinstance(raw, (dict, list)):
        return ""
    return str(raw)


def _put(out: dict, path: str, raw: Any) -> None:
    if isinstance(raw, dict) and ("value" in raw or "excerpt" in raw or "status" in raw):
        out[path] = _fact_display(raw)
        return
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            _put(out, f"{path}.{k}" if path else k, v)
        return
    if isinstance(raw, list):
        return
    out[path] = "" if raw is None else str(raw)


def flatten_result(result: dict | None) -> dict[str, str]:
    """? paper.json ?? path -> ??????"""
    out: dict[str, str] = {}
    r = result or {}
    meta = r.get("paper_metadata") or {}
    if isinstance(meta, dict):
        for k, v in meta.items():
            _put(out, f"paper_metadata.{k}", v)

    for i, sample in enumerate(r.get("samples") or []):
        if not isinstance(sample, dict):
            continue
        sid = _slot_value(sample.get("sample_id")) or f"#{i}"
        base = f"samples[{sid}]"
        for k, v in sample.items():
            if k == "sample_id":
                out[f"{base}.sample_id"] = "" if sid is None else str(sid)
                continue
            _put(out, f"{base}.{k}", v)

    for i, cond in enumerate(r.get("conditions") or []):
        if not isinstance(cond, dict):
            continue
        cid = _slot_value(cond.get("condition_id")) or f"#{i}"
        base = f"conditions[{cid}]"
        for k, v in cond.items():
            if k in ("condition_id", "sample_id"):
                out[f"{base}.{k}"] = "" if _slot_value(v) is None else str(_slot_value(v))
                continue
            if isinstance(v, dict) and not ("value" in v or "excerpt" in v) and v:
                # ???
                for pk, pv in v.items():
                    _put(out, f"{base}.{k}.{pk}", pv)
            else:
                _put(out, f"{base}.{k}", v)

    for i, fig in enumerate(r.get("figures") or []):
        if not isinstance(fig, dict):
            continue
        fid = _slot_value(fig.get("figure_id")) or f"#{i}"
        base = f"figures[{fid}]"
        for k, v in fig.items():
            if k.startswith("_"):
                continue
            _put(out, f"{base}.{k}", v)

    return out


def diff_flattened(
    a: dict[str, str], b: dict[str, str], *, include_same: bool = False
) -> list[dict]:
    """?? {path, a, b, changed} ?????? changed?"""
    keys = sorted(set(a) | set(b))
    rows = []
    for path in keys:
        va = a.get(path, "")
        vb = b.get(path, "")
        changed = va != vb
        if changed or include_same:
            rows.append({"path": path, "a": va, "b": vb, "changed": changed})
    return rows


def diff_results(result_a: dict | None, result_b: dict | None, *, include_same: bool = False) -> list[dict]:
    return diff_flattened(flatten_result(result_a), flatten_result(result_b), include_same=include_same)
