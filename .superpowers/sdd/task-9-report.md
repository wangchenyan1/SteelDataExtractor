# Task 9 Report: 前端四个入口、字段库勾选、出处高亮、导出

## Changes

### `app/index.html` — 新增 / 替换的 ID

| ID | 用途 |
| --- | --- |
| `#btnRunAll` | 整篇一次跑完 → `POST /api/run` |
| `#btnRunStep` | 跑当前步骤 → `POST /api/run_step` |
| `#btnParseOnly` | 只解析 → `POST /api/parse` |
| `#btnReextract` | 只重抽 → `POST /api/reextract` |
| `#reextractField` | 重抽字段下拉 |
| `#reextractScope` | 当前文献 / `project_extracted` |
| `#btnExport` | 导出 → `GET /api/projects/<id>/export` 下载 |
| `#btnNewProject` | 打开新建项目对话框 |
| `#newProjectDialog` / `#newProjectId` / `#newProjectName` / `#newProjectTemplate` / `#newProjectFieldChecks` / `#saveNewProject` | 新项目：模板 + 勾选 → `POST /api/projects` |
| `#fieldLibraryChecks` | 库字段 checkbox（`GET /api/field_library`） |
| `#ruleScopeProject` / `#ruleScopeLibrary` | 规则：仅本项目 / 写回公共库 |
| `#resultFieldList` | 结果字段列表（value / location / 摘录状态，点击高亮） |
| `#pdfPathInput` | 可选 PDF 路径（parse / run） |
| `#stepList` `li[data-step-id]` | 可点步骤条；property/figure 在 entity 未完成时 `disabled` |

移除：`#runExtractBtn`。

### `app/app.js` — API 调用

- `displayValue(field)`：`field.value ?? field`
- `POST /api/run`（`btnRunAll`）、`/api/run_step`（含 entity 重跑 `confirm`）、`/api/parse`、`/api/reextract`
- `GET /api/field_library?template=`；勾选变更 → `PUT /api/projects/<id>/config`（`selected_field_ids`）
- 新增字段 → overlay `private_fields` + PUT
- 规则「仅本项目」→ `field_overrides` PUT；「写回公共库」→ `POST /api/field_library/writeback`
- 导出：`GET .../export` → 下载 `<id>_fields_schema.json`
- `highlightExcerpt(paperText, excerpt)`：规范化空白 `indexOf`；命中则包 `<mark>`（先藏 PDF iframe）

### `app/styles.css`

步骤禁用、操作区、库勾选、结果字段行、`<mark>`、规则单选、新项目对话框样式。

## CLI（Step 3）

```
$ python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode two_stage
# ok：completed_steps=[entity, mechanical, magnetic, figures]；warnings=2

$ python3 tools/workbench_server.py --export-fields-schema --project demo_steel | python3 -c "..."
# assert 通过（schema + fields）
```

静态检查：HTML 关键 ID 齐全；`app.js` 括号平衡。

## Notes

- Skip git（按任务说明）。
- 未写 Extract_data。
- **未能打开浏览器**做手工「Table 2 高亮 / title 仅本项目不改库」验收；需本地起 `workbench_server.py` 后在工作台点验。

## Review fix (Important findings)

### What changed (`app/app.js` only)

1. **Field-library checkbox save seed** — `onLibraryCheckChange` now seeds from `selectedFieldIds()` (same Set the UI checkboxes use, including fallback to `project.fields`), instead of `overlay.selected_field_ids || []`, which could be empty and wipe the project on first toggle.
2. **Result list excerpt status** — Added `excerptMatchesInText` (same whitespace-normalized `indexOf` as `highlightExcerpt`). `renderResultFieldList` shows 「已定位」/「仅摘录」 at render time (not only after click); click still updates status + miss hint.
3. **Restore `entityDone` on project/paper select** — Added `applyEntityDoneFromRunInfo` / `restoreEntityDoneFromLatestRun` (reads latest `/api/result` `completed_steps` / samples). Called from `selectProject`, `paperSelect` change, and `usePaperBtn`; `loadReview` / `afterRun` reuse the helper. Re-renders step list so property/figure are not stuck disabled after a successful skeleton.

### Covering tests

None for JS. Self-check / grep notes:

- `onLibraryCheckChange` contains `new Set(selectedFieldIds())`; no `overlay.selected_field_ids || []` seed.
- `excerptMatchesInText` used by both `highlightExcerpt` and `renderResultFieldList`; status strings 「已定位」/「仅摘录」 present; 「有摘录」 absent.
- `restoreEntityDoneFromLatestRun` called from `selectProject` and paper select handlers; `applyEntityDoneFromRunInfo` shared with `loadReview` / `afterRun`.
- Brace/paren/bracket counts balanced (python count check).

### Commands run

```
$ node --check app/app.js
# node: command not found

$ python3 -c "... balance + assert selectedFieldIds seed / 已定位 / restoreEntityDone ..."
# python self-check ok
# parens/brackets/braces balanced
```
