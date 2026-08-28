# Review package: final-review fix wave

No git. Working-tree snapshot of the four changed files (relevant hunks).

## Files

- tools/config_model.py (promote_private_field)
- tests/test_config_model.py (new tests)
- app/app.js (batch reextract counts)
- tools/pipeline.py (4 system-role strings)

---

### tools/config_model.py — load_field_library (UNCHANGED)

```python
def load_field_library(root: Path, template_id: str) -> dict:
    if template_id == "blank":
        return {"fields": []}
    path = root / "configs" / "field_library" / f"{template_id}.json"
    return _read_json(path)
```

### tools/config_model.py — promote_private_field (CHANGED)

```python
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
```

NEW vs previous: after finding match, if template_id == "blank" raise ValueError before writeback/save.

### tests/test_config_model.py — NEW

See file lines 96–161: `_private_field`, `test_promote_private_field_blank_raises`, `test_promote_private_field_steel`.
Also imports `pytest` (new).

### app/app.js — CHANGED

```javascript
      else if (out.report) {
        const okCount = out.report.filter((r) => r.ok).length;
        const failCount = out.report.filter((r) => !r.ok).length;
        $("runStatus").textContent =
          `批量重抽完成：成功 ${okCount} · 失败 ${failCount}`;
      }
```

Previously: `(out.report.ok || []).length` / `(out.report.failed || []).length`

Backend contract (`pipeline.reextract_field` unchanged this wave):
`report` is a list of `{paper_id, ok, error}`.

### tools/pipeline.py — CHANGED (4 call_json first args)

Lines 674, 701, 1018, 1059:
`"材料文献结构化抽取专家"`

Previously: `"钢铁材料文献抽取专家"`

User-facing prompt templates still inject `{domain_hint}`.

## Implementer test claims (do not re-run unless a named doubt)

- RED: test_promote_private_field_blank_raises failed FileNotFoundError on blank.json
- GREEN: tests/test_config_model.py 8 passed; full suite 30 passed
