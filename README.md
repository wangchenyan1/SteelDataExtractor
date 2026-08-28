# SteelDataExtractor · 文献抽取工作台

把复杂材料文献抽取拆成一个**配置驱动、分阶段、可试跑、可人工 review** 的小工具，
方便有类似需求的同事直接拿去改：**选模板 + 从字段库勾选字段 + 自定义抽取阶段** 即可换领域子集。

## 工作台任务流（五视图）

网页工作台按同一人完成抽取任务的顺序组织：

```text
项目 → 配置（字段 + 抽取阶段 + 过滤策略）→ 文献与运行 → 复核 → 导出
```

| 视图 | 职责 |
| --- | --- |
| 项目 | 选择 / 新建项目（模板 + 名称） |
| 配置 | 勾选字段、编辑性能阶段、白话配置过滤策略 |
| 文献与运行 | 加 PDF / 选文献 / 按项目阶段跑抽取 |
| 复核 | 左原文 · 右层级结果 · 规则未通过异色展示 |
| 导出 | 下载项目配置或抽取结果（可选是否含规则未通过项） |

抽取流水线（配置驱动，阶段来自项目配置）：

```text
PDF（可选，需 UNIPARSER_API_KEY）
  → 项目本地 paper.md + 图片
  → 按节剪裁（去掉 References / Acknowledgements，保留 Appendix 等）
  → 骨架（metadata / sample / condition）
  → 各性能阶段（按项目配置的 steps 依次执行）
  → 规则校验与图片策略 → 合并导出（paper.json，字段带 excerpt + location + status）
```

性能阶段可在配置页自定义（如「骨架 → 力学性能 → 电导性能」），不再写死为力学 / 磁学 / 图片过滤四步。
规则未通过的性能值与图片**保留在结果树中**，标记为 `status=rejected_by_rule` 并显示原因；导出时可选择是否包含。

离线 `demo_steel` **不调用 UniParser**，直接用内置 `paper.md`。

## 30 秒离线体验（无需 API key / 无需联网）

内置示例项目 `demo_steel` 用离线 mock 后端，开箱即可端到端跑通：

```bash
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace

# 方式一：命令行试跑一篇
python3 tools/workbench_server.py --run-once --project demo_steel \
  --paper-id demo_steel_2024 --mode two_stage

# 方式二：启动网页工作台
python3 tools/workbench_server.py --host 127.0.0.1 --port 8787
# 浏览器打开 http://127.0.0.1:8787 （远程可用 ssh -L 8787:127.0.0.1:8787 dp_cpu）
```

示例里故意埋了一个坑：摘要里的目标值「yield strength above 600 MPa」会被性能步
误当成测量值，**规则校验会将其标记为未通过**（仍出现在复核结果树中，异色展示）；XRD 图同理被图片策略标记为未通过。用 `--mode single_pass`
可以看到「不做策略标记」的对照结果（全部视为通过），直观对比优化前后。

## 四个入口

| 入口 | CLI / API | 说明 |
| --- | --- | --- |
| 整篇一次跑完 | `--run-once` / `POST /api/run` | 可选解析 + 全部步骤 + 校验 + 合并；`single_pass` 为少做策略标记的对照 |
| 整篇分阶段跑 | `--step <step_id>` / `POST /api/run_step` | 同一步骤图，一次只跑一步；可先看骨架再跑性能 |
| 只解析 | `--parse-only --pdf PATH` / 上传 PDF | 只生成 `paper.md` 与图片，不抽取；**需要 `UNIPARSER_API_KEY`** |
| 只重抽字段 | `--reextract-field <id>` | 骨架不动；可对当前文献或本项目已抽文献批量重跑该字段 |

分阶段跑的是「整篇的某一步」；字段重抽的是「已有结果里的某一个字段」。重跑骨架会作废旧性能/图片并自动重跑下游。

## 模板 · 字段库 · 项目覆盖

三层配置：

| 层 | 路径 | 职责 |
| --- | --- | --- |
| 模板 | `configs/templates/steel.json`（另有空模板 `blank`） | 固定层级与步骤依赖 |
| 公共字段库 | `configs/field_library/steel.json` | 可复用字段与默认规则；项目勾选默认不写库 |
| 项目覆盖层 | `configs/projects/<id>.json` | 勾选字段、私有字段、阶段计划 `steps`、规则覆盖、`property_source` / `figure_filter` |

- 新建项目：选模板 → 按类别从库勾选 → 在配置页编辑性能阶段。
- 改规则可选「仅本项目」或「写回公共库」；私有字段可提升入库。
- **导出**：导出视图可下载项目配置（字段 + 阶段 + Schema）或抽取结果；结果导出支持「含规则未通过」选项。CLI 等价：`python3 tools/workbench_server.py --export-fields-schema --project demo_steel`。

旧项目（`non_magnetic` 等）仍走 `configs/fields/*.json` 兼容路径，第一版不迁移。

## 目录结构

```text
steel_extract_tool_workspace/
  app/                # 网页工作台（五视图、字段库勾选、出处高亮、导出）
  tools/
    workbench_server.py   # 静态服务 + CLI/API
    pipeline.py           # 配置驱动抽取 pipeline
    llm_backends.py       # mock（离线）/ claude（真实）
    paper_parser.py       # paper.md 解析（文本 + 图片）
    pdf_parser.py         # UniParser PDF → paper.md（需 API key）
  configs/
    project_config.json
    templates/            # steel / blank
    field_library/        # 钢铁公共字段库
    projects/             # 项目覆盖层（demo_steel）
    fields/               # 旧项目兼容配置
  example_data/           # 内置示例文献（demo 离线用）
  test_runs/              # 试跑结果
  docs/
```

## 换成你自己的领域

1. 钢铁子集：新建项目选 `steel` 模板，从库勾选需要的字段并配置阶段即可。
2. 其它领域：用 `blank` 模板建项目，自建私有字段（第一版不提供第二套完整骨架示例）。
3. 真实抽取：`backend: "claude"`，工作区 `.env` 配 `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`。
4. PDF 解析：另需 `UNIPARSER_API_KEY`（或 `UP_API_KEY`）；无 key 时会报错提示该变量名。已有 `paper.md` 默认不重复解析。

## 运行结果落盘

```text
test_runs/<project>/<test|data>/<run_id>/
  prompt_preview/     # 各步 prompt
  inputs/             # 剪裁后文本 + input_trim_stats.json
  entities/           # 骨架
  properties/         # 各性能组原始输出
  merged_outputs/     # paper.json（含 excerpt / location / status）
  review_notes/       # 规则校验命中明细
  RUN_INFO.json / summary.md
```

PDF 解析输出写到项目配置的 `parsed_results/<paper_id>/`，**绝不写回** `/internfs/wangchenyan/shougang/Extract_data`。
