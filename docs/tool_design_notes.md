# 工具设计草案

## 目标

把当前材料文献抽取流程做成一个可配置、可试跑、可人工 review 的小工具。

## 核心原则

1. 原始抽取目录只读。
2. 测试结果全部落到独立工作区。
3. 字段和规则可配置。
4. 抽取分阶段：
   - 文章信息 + 样品状态 + 图片信息
   - 性质信息
   - 人工 review
   - 合并导出

## 为什么分阶段

一次性抽取完整 JSON 容易把样品、状态、性质混在一起。

更合理的做法是先抽数据库骨架：

```text
paper_metadata
samples
conditions
figures
```

再把性质值绑定到已有 condition：

```text
properties
unmatched_properties
```

找不到归属的性质值不硬塞，进入人工 review。

## 当前状态

工作台已按规格落地。基础配置与流水线见 `docs/superpowers/specs/2026-08-27-configurable-extract-tool-design.md`；**UI 任务流、阶段可配、规则未通过展示与导出**以 `docs/superpowers/specs/2026-08-28-extract-workbench-ux-design.md` 为准。

已实现要点：

- 五视图导航：项目 → 配置 → 文献与运行 → 复核 → 导出
- 项目级性能阶段计划（`steps`）可编辑；运行时以覆盖层为准
- 规则校验与图片策略改为**标记** `status=rejected_by_rule`，结果仍保留在树中
- 复核：PDF 优先 / 渲染 md、层级结果、异色、缩略图
- 导出：项目配置（含阶段）与抽取结果；结果可选 `include_rejected`
- 四个 CLI/API 入口：整篇、分阶段、只解析、单字段重抽
- 三层配置：模板 + 公共字段库 + 项目覆盖层
- `demo_steel` 走真实多模态后端；不写回 `Extract_data`

## 测试结果保存策略

试跑结果必须按项目隔离：

```text
test_runs/<project_id>/<run_id>/
```

示例：

```text
test_runs/non_magnetic/2026-08-10_field_config_demo/
test_runs/nuclear_fusion/2026-08-10_two_stage_prompt_v1/
test_runs/cor_res/2026-08-10_corrosion_fields_v1/
test_runs/cuti/2026-08-10_conductivity_fields_v1/
```

跨项目共用材料放入：

```text
test_runs/_shared/
```

