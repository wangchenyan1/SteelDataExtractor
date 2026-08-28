# Final whole-branch review findings to fix

Source: Senior Code Reviewer assessment **Ready with nits**.
No git. Do not `git init`. Skip commit if not inside a git work tree.

Workspace: `/internfs/wangchenyan/shougang/steel_extract_tool_workspace`

## Must fix (Important)

### 1. blank 模板 `promote_private_field` 静默丢字段

`tools/config_model.py`:

- `load_field_library` 对 `blank` **硬编码**返回 `{"fields": []}`（计划 Task 2 接口；`tests/test_config_model.py::test_blank_library_is_empty` 锁定此行为）。
- `promote_private_field` 仍调用 `writeback_library_field(root, "blank", ...)` 写 `configs/field_library/blank.json`，再把字段从 `private_fields` 挪到 `selected_field_ids`。
- 之后 `effective_fields` 因 id 不在空库里被 `continue` 跳过，私有定义已删 → **字段消失**。

规格约束（必须同时满足）：

- `docs/superpowers/specs/2026-08-27-configurable-extract-tool-design.md` §4.1：blank **没有对应字段库**；该项目只能新增私有字段。
- 同规格 §4.3：私有字段可显式提升入库（针对**有库**的模板，如 steel）。

**指定做法（不要改成给 blank 建可读库）：**

- 保持 `load_field_library(..., "blank")` 永远返回 `{"fields": []}`，不要读/依赖 `field_library/blank.json`。
- `promote_private_field` 在 `template_id == "blank"` 时 **立即 `raise ValueError`**，中文错误信息说明：空模板没有公共字段库，私有字段不能提升入库。
- 失败时 **不得** 改 overlay（private 仍在）、**不得** 写 `field_library/blank.json`。
- steel 模板的 promote 行为不变。

测试（TDD：先写失败测试再改实现）：

- 在 `tests/test_config_model.py` 用 `tmp_path` 建 blank 项目 + 一条 private_fields，调用 `promote_private_field` 应抛 `ValueError`。
- 断言 overlay 的 `private_fields` 未变、`selected_field_ids` 未偷偷加上该 id。
- 断言 `configs/field_library/blank.json` 未被创建。
- 可选：steel 项目 promote 一条 private 后，库里能读到、overlay 从 private 改为 selected（此前未覆盖）。

`writeback_library_field` 对 blank 可不改（UI/API 的 promote 才是用户路径）；若 writeback 被直接调用且文件不存在会崩，不要为此新建 blank 库。

## Should fix (reviewer nits, small)

### 2. 批量重抽 UI 计数永远显示 0

`app/app.js` 约 1009–1011：后端 `reextract_field(scope=...)` 返回 `report` 为 **列表** `[{paper_id, ok, error}, ...]`（见 `tools/pipeline.py` `reextract_field`），前端却读 `out.report.ok.length` / `out.report.failed.length`。

改成按列表项的 `ok` 布尔值计数成功/失败。不要改后端 report 形状。

无现成前端测试框架则不新增 E2E；改完自检逻辑即可。

### 3. `call_json` system 角色写死「钢铁」

计划 Global Constraints：Prompt 角色用「材料文献结构化抽取专家」，领域提示来自模板 `domain_hint`。

`tools/pipeline.py` 约 674、701、1018、1059 四处把 `"钢铁材料文献抽取专家"` 传给 `call_json`。用户可见 prompt 正文已用 `domain_hint`。

把这四处 system 角色改成 `"材料文献结构化抽取专家"`。不要改 prompt 正文里的 `{domain_hint}` 注入。

## Do not fix (Minors already in ledger)

empty LLM ok=True；skeleton-gate 空 run 目录；run_step 内 entity_only 死代码；invalidated_steps 残留；deny_phrase 不扫 excerpt；pipeline.py 拆文件；uniparser import on fake client；afterRun 仅摘录；effective_fields 静默跳过未知 id。

## Tests to run

```
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest tests/test_config_model.py -q
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest tests -q
```

报告写到：`.superpowers/sdd/final-review-fix-report.md`（含 RED/GREEN 证据与完整 pytest 输出摘要）。
