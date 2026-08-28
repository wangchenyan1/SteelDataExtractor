# Task 3 Report: 出处形状、摘录匹配、导出 Schema

**Status:** DONE  
**Date:** 2026-08-27

## Deliverables

| Path | Action |
| --- | --- |
| `tools/provenance.py` | Created |
| `tests/test_provenance.py` | Created |
| `tests/test_export.py` | Created |
| `tools/config_model.py` | Extended: `build_output_schema`, `export_project` |

Git commit skipped per brief.

## Interfaces implemented

- `is_identity_field(template, field)` — `True` if `field["id"]` is in `identity_fields`, or equals any layer `parent_id_field` / entry in `ref_fields` (so `condition.sample_id` is identity).
- `value_shape(field)` — `{value, unit, excerpt, location}`; `composition` → `value={}`; `boolean` → `value=None`; `category==property` adds `source=""`.
- `find_excerpt_span(text, excerpt)` — normalize `\s+` → single space + strip; substring on normalized text; map span back to original indices via norm→orig table.
- `build_output_schema(template, fields)` — `paper_metadata` dict; `samples`/`conditions`/`figures` each one example object; identity slots `""`; properties nested under group keys on condition.
- `export_project(root, project_id)` — 4.6 payload: `project_id`, `template_id`, `exported_at` (`isoformat(timespec="seconds")`), sorted `fields` (category then property group), `steps`, `schema`.

## RED evidence

```text
$ python3 -m pytest tests/test_provenance.py tests/test_export.py -v
collected 0 items / 2 errors

ERROR tests/test_provenance.py — ModuleNotFoundError: No module named 'tools.provenance'
ERROR tests/test_export.py — ImportError: cannot import name 'export_project' from 'tools.config_model'
Interrupted: 2 errors during collection
```

(Failure reason: missing module / missing symbol — expected before implementation.)

## GREEN evidence

```text
$ python3 -m pytest tests/test_provenance.py tests/test_export.py -v
5 passed in 0.02s

$ python3 -m pytest tests -q
16 passed in 0.03s
```

## Concerns

- Spec example shows `"figures": []` while the task brief requires one example figure object; implementation follows the brief (`figures: [obj]`).
- `deepcopy` remains unused in `config_model.py` (pre-existing); left untouched.
- `find_excerpt_span` maps the last normalized space to the first character of the original whitespace run; exclusive end is `last_orig + 1` (sufficient for the required substring tests).
