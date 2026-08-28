# Task 2 Report: 配置模型（模板 / 字段库 / 覆盖层 / 步骤生成）

**Status:** PASS  
**Date:** 2026-08-27  
**Commit:** skipped (per brief / user instruction)

## Deliverables

| Path | Action |
| --- | --- |
| `tools/config_model.py` | Created |
| `tests/test_config_model.py` | Created |
| `configs/templates/steel.json` | Created |
| `configs/templates/blank.json` | Created |
| `configs/field_library/steel.json` | Created (24 fields; no FK duplicates) |
| `configs/projects/demo_steel.json` | Created |
| `configs/project_config.json` | Modified (`demo_steel` +`template_id`/`overlay`) |
| `configs/fields/demo_steel.json` | Left on disk as unused backup |

## TDD evidence

### RED — failing test first

Command: `python3 -m pytest tests/test_config_model.py -v`

```
ImportError: cannot import name 'config_model' from 'tools'
ERROR tests/test_config_model.py
Interrupted: 1 error during collection
```

Expected: import failure before implementation. Observed: same.

### GREEN — after configs + `config_model.py`

Command: `python3 -m pytest tests/test_config_model.py tests/test_input_trim.py -v`

```
11 passed in 0.03s
```

Full suite: `python3 -m pytest tests -q` → `11 passed`.

## Implementation notes

- Field library ids are short names (`title`, `yield_strength`, …).
- `sample_id` / `condition_id` appear once as library PKs; condition/figure FKs come from template `parent_id_field` / `ref_fields` only (not extra library rows).
- Demo overlay `selected_field_ids` matches brief list (title … scale_bar_info); no duplicate condition `sample_id`.
- `generate_steps`: entity → property groups in template order → figures; no parse step; `step_overrides` validated so entity precedes property/figure.
- `save_overlay` writes only project overlay; `writeback_library_field` / `promote_private_field` update the library explicitly.
- `create_project` writes overlay + `project_config.json` entry (`runnable: true`, `backend: mock`, overlay path, parsed_results/test_runs).
- Task 1 `input_trim` tests remain green.

## Concerns

- None blocking. `promote_private_field` is implemented but not covered by Task 2 tests (only exercise via API presence).
- Old `field_config` path still on `demo_steel`; `load_field_config` migration is Task 4.
