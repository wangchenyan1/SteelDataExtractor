# SteelDataExtractor · 文献抽取小工具

把复杂材料文献抽取拆成一个**配置驱动、分阶段、可试跑、可人工 review** 的小工具，
方便有类似需求的同事直接拿去改：**选模板 + 从字段库勾选字段** 即可换领域子集。

抽取流水线（配置驱动，不写死两阶段）：

```text
PDF（可选，需 UNIPARSER_API_KEY）
  → 项目本地 paper.md + 图片
  → 按节剪裁（去掉 References / Acknowledgements，保留 Appendix 等）
  → 骨架（metadata / sample / condition）
  → 各性能组（按勾选字段自动生成步骤）
  → 图片过滤
  → 规则校验 → 合并导出（paper.json，字段带 excerpt + location）
```

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
误当成测量值，**规则校验会把它剔除**；同时 XRD 图会被图片过滤去掉。用 `--mode single_pass`
可以看到「不做规则校验」的对照结果（错误值和 XRD 都保留），直观对比优化前后。

## 四个入口

| 入口 | CLI / API | 说明 |
| --- | --- | --- |
| 整篇一次跑完 | `--run-once` / `POST /api/run` | 可选解析 + 全部步骤 + 校验 + 合并；`single_pass` 为少做校验/过滤的对照 |
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
| 项目覆盖层 | `configs/projects/<id>.json` | 勾选字段、私有字段、规则覆盖、`property_source` / `figure_filter` |

- 新建项目：选模板 → 按类别从库勾选 → 步骤按已勾选性能组自动生成。
- 改规则可选「仅本项目」或「写回公共库」；私有字段可提升入库。
- **导出**：网页「导出」或 `python3 tools/workbench_server.py --export-fields-schema --project demo_steel`，得到生效字段 + 与合并结果形状一致的 Schema。

旧项目（`non_magnetic` 等）仍走 `configs/fields/*.json` 兼容路径，第一版不迁移。

## 目录结构

```text
steel_extract_tool_workspace/
  app/                # 网页工作台（四入口、字段库勾选、出处高亮、导出）
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

1. 钢铁子集：新建项目选 `steel` 模板，从库勾选需要的字段即可。
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
  merged_outputs/     # paper.json（含 excerpt / location）
  review_notes/       # 规则校验命中明细
  RUN_INFO.json / summary.md
```

PDF 解析输出写到项目配置的 `parsed_results/<paper_id>/`，**绝不写回** `/internfs/wangchenyan/shougang/Extract_data`。
