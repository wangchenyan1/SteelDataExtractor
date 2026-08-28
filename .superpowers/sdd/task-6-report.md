# Task 6 Report: 单字段 / 批量重抽

## RED

Created `tests/test_reextract.py`（拒标识字段；重抽 `yield_strength` 保留其它性能字段）.

```
$ python3 -m pytest tests/test_reextract.py -v
ERROR collecting tests/test_reextract.py
ImportError: cannot import name 'reextract_field' from 'tools.pipeline'
```

## GREEN

Changed:

- `tools/pipeline.py`：新增 `reextract_field` / `_reextract_one_paper`；标识字段经 `is_identity_field` 拒绝；性能字段只抽该字段并合并进最新 `paper.json`；失败保留旧值并写 `warnings`；`scope=project_extracted` 汇总 `report`；同秒新建 run 目录冲突时加后缀避免污染分阶段测试
- `tools/llm_backends.py`：`MockBackend.call_json` 对 `hint.stage=="reextract"` + `yield_strength` 返回只含该字段的 properties（保留 excerpt/location）
- `tests/test_reextract.py`：按 brief 契约

```
$ python3 -m pytest tests/test_reextract.py -v
2 passed

$ python3 -m pytest tests -q
23 passed
```

## Notes

- Skip git（按任务说明）.
- 未写 Extract_data.
- 批量路径有实现但无独立测试；骨架非标识字段 prompt/合并已实现，本任务测试仅覆盖性能字段.
