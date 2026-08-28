# Task 5 Report: 分阶段 run_step 与骨架失效

## RED

Created `tests/test_run_step.py`（三契约：property 先于 entity 报错；分阶段 entity→mechanical 带出处；重跑 entity 失效并自动下游）.

```
$ python3 -m pytest tests/test_run_step.py -v
ERROR collecting tests/test_run_step.py
ImportError: cannot import name 'run_step' from 'tools.pipeline'
```

## GREEN

Changed:

- `tools/pipeline.py`：抽出 `_prepare_run` / `_execute_step`；`run_extraction` 循环全部步骤；新增 `run_step`（骨架未完成 → `RuntimeError("必须先完成骨架")`；重跑 entity 删除 `properties/*`、清空性能组与过滤 figures，再自动跑全部下游）；`RUN_INFO.json` 增加 `template_id` / `completed_steps` / `invalidated_steps` / `parse_skipped`
- `tools/llm_backends.py`：mock 非标识 entity 字段包成 `{value,unit,excerpt,location}`；性能值补真实 demo 摘录（C1 yield → Table 2；C4 reject → Abstract）

```
$ python3 -m pytest tests/test_run_step.py tests/test_validate_provenance.py -v
5 passed

$ python3 -m pytest tests -q
21 passed
```

## --run-once

```
$ python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode two_stage
```

- samples=2, conditions=4, figures=2, warnings=2
- `completed_steps`: entity, mechanical, magnetic, figures
- `parse_skipped`: true；C4 yield 剔除 + XRD 过滤仍正常

## Notes

- Skip git（按任务说明）.
- 未写 Extract_data.
- 分阶段测试会在 `test_runs/demo_steel/test/` 留下 run 目录（计划允许）.
- 前端仍可能按 title 字符串渲染；规格 5.5 对象形态交 Task 10 适配.
