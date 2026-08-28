# Task 8 Report: HTTP API 与 CLI

## RED

Created `tests/test_api_handlers.py`（`handle_get` export + field_library）.

```
$ python3 -m pytest tests/test_api_handlers.py -v
ERROR collecting tests/test_api_handlers.py
ImportError: cannot import name 'handle_get' from 'tools.workbench_server'
```

## GREEN

Changed:

- `tools/workbench_server.py`：抽出模块级 `handle_get` / `handle_post` / `handle_put`；Handler 只做 IO
  - GET：保留 health/projects/papers/paper_text/runs/result；新增 `field_library`、`project_config`、`/api/projects/<id>/config|export`
  - POST：保留 `/api/run`（无 md 且有 pdf_path/source.pdf 时先 parse）；新增 projects、parse、run_step、reextract、field_library/writeback|promote
  - PUT：`/api/projects/<id>/config` 与 `/api/project_config?project=`
  - CLI：`--export-fields-schema` / `--parse-only --pdf` / `--step` / `--reextract-field` / `--overwrite-parse`；优先级 export > parse-only > reextract > step > run-once
- `tests/test_api_handlers.py`：按 brief 两例

```
$ python3 -m pytest tests/test_api_handlers.py -v
2 passed

$ python3 -m pytest tests -q
28 passed

$ python3 tools/workbench_server.py --export-fields-schema --project demo_steel
# JSON 含 template_id=steel、fields、schema（paper_metadata/samples/conditions/figures）
```

## Notes

- Skip git（按任务说明）.
- 未写 Extract_data.
- multipart 用轻量 boundary 解析（避免 cgi 弃用警告）；JSON + 本地 `pdf_path` 为第一版主路径.
