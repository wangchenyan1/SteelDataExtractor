# Task 4 Report: Pipeline 改走配置模型，校验保留出处

## RED

Created `tests/test_validate_provenance.py` (keep excerpt on clean; rejected warning carries excerpt).

```
$ python3 -m pytest tests/test_validate_provenance.py -v
FAILED test_keeps_excerpt_on_clean_value — KeyError: 'excerpt'
FAILED test_rejected_value_listed_with_excerpt — KeyError: 'excerpt'
2 failed
```

## GREEN

Changed `tools/pipeline.py`:

- `validate_properties`: cleaned values keep `source`/`excerpt`/`location`; reject warnings include `excerpt`/`location`
- `single_pass` branch: same provenance keys retained
- `load_field_config`: if `overlay` present, synthesize fields/rules/steps/property_source/figure_filter/domain_hint via `config_model`; else fallback to `field_config` JSON
- `build_entity_prompt`: `你是{domain_hint}结构化抽取专家`，缺省「材料文献」
- sys.path: workspace root inserted so `config_model → tools.provenance` works under `python3 tools/workbench_server.py`

```
$ python3 -m pytest tests/test_validate_provenance.py tests/test_config_model.py -v
8 passed

$ python3 -m pytest tests -q
18 passed
```

## --run-once

```
$ python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode two_stage
```

Result:

- run_id: `20260827_145626_two_stage`
- samples=2, conditions=4, figures=2, warnings=2
- C4.yield_strength=600 来源不可靠(abstract_target)，已剔除 ✓
- Figure 3 XRD 被过滤（预期旁路）

## Notes

- Skip git (per task instruction).
- Did not write Extract_data.
- Snapshot projects without overlay still use `field_config` fallback.
