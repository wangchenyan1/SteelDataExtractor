# Task 10 Report: README 与 demo 回归

## 变更

- 更新 `README.md`：流水线改为 PDF（可选）→ 按节剪裁 → 骨架 → 性能组 → 图片；说明四入口、字段库/覆盖/导出；强调 `demo_steel` 离线路径；不宣称无 key 可用 UniParser。
- 更新 `docs/tool_design_notes.md`「当前状态」：与规格一致，去掉「尚未真实调用抽取模型」。
- 按用户指示 **跳过 git commit**。

## 命令输出（摘要）

### pytest

```text
............................                                             [100%]
28 passed in 0.17s
```

### `--mode two_stage`

```text
run_id: 20260827_154829_two_stage
warnings: 2
  - C4.yield_strength=600 来源不可靠(abstract_target)，已剔除
  - Figure 3 被过滤：类型 XRD 不在组织图白名单
figures: 2
```

`paper.json`：C1–C3 有 yield_strength；**无** C4/600；全部 property 对象含 `excerpt`/`location`（13/13）。

### `--mode single_pass`

```text
run_id: 20260827_154839_single_pass
warnings: 0
figures: 3
```

`paper.json`：C4 保留 `yield_strength=600`（`source=abstract_target`，`excerpt`/`location` 齐全）；property 14/14 含出处。

### UniParser 无 key（验收 2 附注）

`tools/pdf_parser.py` 无 key 时抛 `RuntimeError`，文案含 **`UNIPARSER_API_KEY`**。本环境未设 key，未做真解析。

## 规格验收对照（1、3–8）

| # | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| 1 | 离线 demo | pytest 28 绿；mock `--run-once` two_stage/single_pass；`parse_skipped: true` | **evidenced** |
| 2 | 真 UniParser | 无 key；错误文案含变量名；未跑真 PDF | 手工项，未真跑 |
| 3 | 新项目选字段 | `test_config_model.py`：`test_create_project_selects_subset`、`test_unselected_group_omits_step` | **evidenced**（单测） |
| 4 | 覆盖 vs 写回 | `test_overlay_does_not_write_library`、`test_writeback_updates_library` | **evidenced**（单测） |
| 5 | 骨架失效 | `test_rerun_entity_invalidates_and_reruns_downstream` | **evidenced**（单测） |
| 6 | 出处 | 本次 two_stage/single_pass `paper.json` 均带 excerpt/location；`test_provenance*` / `test_validate_provenance*` | **evidenced** |
| 7 | 导出 | `test_export.py`、`test_api_handlers.test_export_demo` | **evidenced**（单测） |
| 8 | 剪裁 | `test_input_trim.test_keeps_appendix_after_references` 等 | **evidenced**（单测） |

## Concerns

- 验收 3/4/5/7/8 本次靠既有单测证据，未在本任务中再手工点 UI / 另起 CLI 复跑。
- 验收 2 真 UniParser 未跑（无 key）。
- Brief 中的 commit 步骤按用户「Skip git」跳过。
