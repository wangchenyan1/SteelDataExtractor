### Task 10: README 与 demo 回归

**Files:**
- Modify: `README.md`
- Modify: `docs/tool_design_notes.md`（当前状态一段改成与规格一致，避免再写「尚未真实调用」）

- [ ] **Step 1: 更新 README 流程为 PDF（可选）→ 按节剪裁 → 骨架 → 性能组 → 图片；说明四个入口、字段库、导出**

- [ ] **Step 2: 跑全量测试**

```bash
python3 -m pytest tests -q
python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode two_stage
python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode single_pass
```

Expected: pytest 全绿；two_stage 仍剔除摘要 600 MPa；single_pass 保留该值；`paper.json` 含 excerpt/location。

对照规格验收 1、3、4、5、6、7、8。验收 2（真 UniParser）仅在有 `UNIPARSER_API_KEY` 时手工跑，无 key 确认错误信息含该变量名。

- [ ] **Step 3: Commit** `docs: update README for configurable extraction workbench`

---

## 规格覆盖对照

| 规格 | 任务 |
| --- | --- |
| 模板 + 字段库 + 覆盖 + 新项目勾选 | Task 2, 8, 9 |
| 写回库 / 提升私有字段 | Task 2, 8, 9 |
| 步骤按性能组自动生成、骨架优先 | Task 2, 5 |
| 四个入口 | Task 5, 6, 7, 8, 9 |
| 骨架重抽失效并重跑下游 | Task 5 |
| 单字段/批量重抽 | Task 6 |
| excerpt+location 与高亮 | Task 3, 4, 5, 9 |
| PDF 解析不写 Extract_data | Task 7, 8 |
| 按节剪裁 refs/ack | Task 1 |
| 导出 fields+schema | Task 3, 8, 9 |
| blank 空模板 | Task 2 |
| 不迁四个旧项目 | Task 2 `load_field_config` 兼容 |
| single_pass 保留 | Task 4/8 现有 mode |
| mock 离线 demo | Task 5, 10 |
