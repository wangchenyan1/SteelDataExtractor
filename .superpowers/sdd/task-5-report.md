# Task 5 Report: HTTP — PDF / 图片 / paper_meta / 结果导出

**Status:** PASS  
**Branch:** `feat/extract-workbench-ux`  
**Commit:** `1764d96` — `feat: serve paper PDF/images and export results with status filter`

## Summary

- 新增 `GET /api/paper_meta`、`/api/paper_pdf`、`/api/paper_image`；`resolve_paper_image_path` 仅允许 `images_from_md/` 下 basename，拒绝路径穿越。
- `do_GET` 支持 `BinaryBody`（PDF/图片按 content-type 返回字节；其它 API 仍 JSON）。
- `pipeline.filter_result_by_status`：`include_rejected=False` 时剥离 `*_properties` 与 `figures` 中 `rejected_by_rule`。
- `GET /api/projects/:id/export_results`：有 `paper_id` 返回单篇最新结果，否则项目内各篇最新结果列表；支持 `include_rejected`。

## Tests

```text
# RED
python3 -m pytest tests/test_paper_assets.py tests/test_export_results.py -v
# collection ImportError (filter_result_by_status) + paper_assets 3 failed

# GREEN
python3 -m pytest tests/test_paper_assets.py tests/test_export_results.py tests/test_export.py -v
# 5 passed
```

## Files touched

- `tools/workbench_server.py` — BinaryBody、资源 resolve、新路由、do_GET 分支
- `tools/pipeline.py` — `filter_result_by_status`
- `tests/test_paper_assets.py` — 新建
- `tests/test_export_results.py` — 新建

## Concerns

1. demo 样例无 `source.pdf`，`has_pdf=False`，`/api/paper_pdf` 对 demo 为 404（符合接口语义）。
2. `export_results` 缺省 `include_rejected=true`（不剥离）；前端需显式传 `false` 才得到「仅 accepted」。
3. 过滤仅处理 `conditions[*].*_properties` 与顶层 `figures`；其它嵌套结构未覆盖。

## Review fix — paper_id sandbox (Important)

**Finding:** `paper_id` 未限制在 `parsed_results/<paper_id>` 内，`..` / `../x` 可逃逸 `parsed_results`。

**Fix:**
- 新增 `_is_safe_paper_id`：拒绝空、`.`、`..` 及含路径分隔符的 `paper_id`（要求 `Path(paper_id).name == paper_id`）。
- `resolve_paper_image_path` / `resolve_paper_pdf_path` / `paper_meta`：resolve 后校验 `paper_dir`/`images_dir` 位于 `parsed.resolve()` 下。
- 负向测试：`paper_id=".."` / `"../x"` → image resolve 返回 None；meta/pdf HTTP 404。

**Tests (post-fix):**

```text
python3 -m pytest tests/test_paper_assets.py tests/test_export_results.py tests/test_export.py -v
# 8 passed in 0.07s
```
