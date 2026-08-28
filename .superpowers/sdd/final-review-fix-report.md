# Final Review Fix Report

Date: 2026-08-27  
Workspace: `/internfs/wangchenyan/shougang/steel_extract_tool_workspace`

## What Was Implemented

### Finding 1 (Important): blank 模板 `promote_private_field` 静默丢字段

- **`tools/config_model.py` — `promote_private_field`**: 在解析出私有字段且确认 `template_id == "blank"` 后，**立即** `raise ValueError("空模板没有公共字段库，私有字段不能提升入库")`。
- 检查位于 `writeback_library_field` / `save_overlay` 之前，失败时不改 overlay、不写 `field_library/blank.json`。
- **`load_field_library(..., "blank")`** 保持硬编码 `{"fields": []}`，未改动。

### Finding 2 (Nit): 批量重抽 UI 计数永远显示 0

- **`app/app.js`**: 后端 `reextract_field(scope=project_extracted)` 返回的 `report` 为列表 `[{paper_id, ok, error}, ...]`。前端改为 `out.report.filter(r => r.ok).length` / `filter(r => !r.ok).length` 计数成功与失败。

### Finding 3 (Nit): `call_json` system 角色写死「钢铁」

- **`tools/pipeline.py`**: 四处 `"钢铁材料文献抽取专家"` 统一改为 `"材料文献结构化抽取专家"`（行 674、701、1018、1059）。prompt 正文中的 `{domain_hint}` 未动。

## What Was Tested and Test Results

| Command | Result |
|---------|--------|
| `python3 -m pytest tests/test_config_model.py -q` | **8 passed** in 0.03s |
| `python3 -m pytest tests -q` | **30 passed** in 0.18s |

新增测试：

- `test_promote_private_field_blank_raises` — blank 项目 promote 抛 `ValueError`，overlay 与 `field_library/blank.json` 均不变。
- `test_promote_private_field_steel` — steel 项目 promote 后字段入库、overlay 从 `private_fields` 迁入 `selected_field_ids`。

## TDD Evidence (RED → GREEN)

### RED — blank promote 应先失败

```bash
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && \
  python3 -m pytest tests/test_config_model.py::test_promote_private_field_blank_raises -q
```

```
F                                                                        [100%]
=================================== FAILURES ===================================
___________________ test_promote_private_field_blank_raises ____________________
...
        with pytest.raises(ValueError, match="空模板没有公共字段库"):
>           cm.promote_private_field(ws, "blank_proj", private["id"])
...
E       FileNotFoundError: [Errno 2] No such file or directory: '.../configs/field_library/blank.json'
=========================== short test summary info ============================
FAILED tests/test_config_model.py::test_promote_private_field_blank_raises
1 failed in 0.07s
```

实现前：`promote_private_field` 尝试 `writeback_library_field(root, "blank", ...)`，因 `blank.json` 不存在而 `FileNotFoundError`，而非预期的 `ValueError`。

### GREEN — 实现后

```bash
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && \
  python3 -m pytest tests/test_config_model.py -q
```

```
........                                                                 [100%]
8 passed in 0.03s
```

```bash
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest tests -q
```

```
..............................                                           [100%]
30 passed in 0.18s
```

## Files Changed

| File | Change |
|------|--------|
| `tools/config_model.py` | blank 模板 promote 早抛 `ValueError` |
| `tests/test_config_model.py` | 新增 blank/steel promote 测试；引入 `pytest` |
| `app/app.js` | 批量重抽 report 列表计数 |
| `tools/pipeline.py` | 4 处 system 角色字符串替换 |

## Self-Review Findings

1. **Finding 1 守卫位置正确**：在找到 `match` 之后、任何磁盘写入之前检查 `template_id == "blank"`；overlay 仅在 steel 等有效模板路径上才会被修改。
2. **`load_field_library("blank")` 未变**：`test_blank_library_is_empty` 仍通过，规格 §4.1 保持。
3. **steel 回归**：`test_promote_private_field_steel` 确认库文件更新且 overlay 状态迁移正确。
4. **Finding 2**：仅改前端计数逻辑，未动后端 `report` 形状；`out.report` 为数组时 `.filter` 行为符合 `pipeline.reextract_field` 返回结构。
5. **Finding 3**：全仓 `tools/pipeline.py` 已无 `"钢铁材料文献抽取专家"`；仅替换 `call_json` 第一参数，未触及 prompt 模板。
6. **范围控制**：未改 `writeback_library_field`、未拆 `pipeline.py`、未给 blank 建库文件。

## Concerns

1. **`writeback_library_field(root, "blank", ...)` 直接调用仍会崩溃**（文件不存在）— 与 findings 一致，刻意不修复；用户路径是 promote，已由 Finding 1 拦截。
2. **blank 项目若 UI 仍暴露「提升入库」**，API 会返回 HTTP 500 + 中文 `error` 字符串（`workbench_server` 通用异常处理），体验可后续在 UI 层按模板禁用该按钮（本次范围外）。
3. **Finding 2 / 3 无自动化测试**（findings 允许）；已通过代码审查与全量 pytest 间接验证未破坏后端行为。

## Git

`git rev-parse --is-inside-work-tree` → **not a git repository**。按 instructions 跳过 commit。
