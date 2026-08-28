# 可配置材料文献抽取工作台 · 设计规格

日期：2026-08-27  
范围：在现有 `steel_extract_tool_workspace` 上演进（方案 1），不重写引擎。  
第一版：钢铁模板做完整；其它化学材料领域只留模板接口。

## 1. 目标与非目标

### 目标

把当前偏钢铁、骨架写死的抽取小工具，做成配置驱动的工作台：

- 同事开新项目时，选模板，再从**带分类的公共字段库**勾选字段。
- 同一钢铁骨架下，不同领域勾不同字段（无磁钢侧重磁性能，钛铜侧重力学与工艺）。
- 支持直接传 PDF 解析，再抽取。
- 整篇可一次跑完，也可分阶段跑；也可只重抽某一个字段（当前文献或本项目已抽文献批量）。
- 每条结果带原文摘录和位置，能匹配则在原文高亮。
- 可导出当前项目的**生效字段清单**和对应的抽取 **Schema**，方便同事带走或对照结果。

### 非目标（第一版不做）

- 不做聚合物、化合物等完整示例模板与示例数据，只留空模板接口。
- 不把现有无磁钢 / 钛铜 / 耐蚀钢 / 核聚变四个只读快照项目迁到新结构。
- 不写回 `/internfs/wangchenyan/shougang/Extract_data`。
- 不做任意实体图（自由增减层级关系）；第一版骨架由模板固定。
- 不做精确到字符偏移的出处定位。
- 不用模型去判断「哪一段是参考文献」；剪裁只靠 Markdown 标题规则。不把附录、Supplementary 当成参考文献删掉。

## 2. 架构

在现有网页工作台 + `pipeline.py` + JSON 配置上增加三层配置、解析入口、分阶段调度、字段重抽和出处。

```text
PDF
  → 解析（UniParser，逻辑同 shougang/scripts/parsing/parser.py）
  → 项目本地 paper.md + 图片
  → 按模板 / 字段库 / 项目覆盖层分步抽取
  → paper.json（每条值带 excerpt + location）
```

三个配置层：

| 层 | 职责 | 谁改 |
| --- | --- | --- |
| 模板 | 骨架：有哪些层级、性能挂在哪、图片如何引用 | 工具维护；第一版只完整交付钢铁 |
| 公共字段库 | 可复用字段、默认类别、默认规则 | 显式写回才改；项目保存不改库 |
| 项目覆盖层 | 勾选字段、私有字段、规则/类别覆盖、步骤微调 | 同事日常改这里 |

运行时流水线按**模板层级名**读写 JSON，不再把「样品 / 状态」写死在 prompt 和合并逻辑里。钢铁模板的层级名仍是 `metadata` / `sample` / `condition` / `property` / `figure`。

其它领域：第一版用空模板 `blank` 建项目并自建私有字段；不提供第二套骨架示例，也不把钢铁字段库套到其它模板上。

## 3. 四个入口

| 入口 | 行为 |
| --- | --- |
| 整篇一次跑完 | 解析（如需要）+ 全部抽取步骤 + 校验 + 合并。HTTP `/api/run` 与 CLI `--run-once` 保留。`single_pass` 仍作为一次抽完、少做规则校验/图片过滤的对照模式。 |
| 整篇分阶段跑 | 同一步骤图，一次只执行一步。可停下来看中间结果，再跑下一步。 |
| 只解析 | 只生成 `paper.md` 与图片，不抽取。 |
| 只重抽字段 | 骨架不动。可对当前文献的某一个字段，或对本项目已有抽取结果的文献批量重跑该字段。 |

分阶段与字段重抽的区别：分阶段跑的是「整篇的某一步」（例如力学性能组）；字段重抽的是「已有结果里的某一个字段」。

## 4. 配置模型

### 4.1 模板（钢铁）

路径：`configs/templates/steel.json`

固定层级：

- `metadata`（文章信息）：一篇文献一份。
- `sample`（样品信息）：多个，带 `sample_id`。
- `condition`（状态信息）：多个，带 `condition_id`，通过 `sample_id` 挂到样品。
- `property`（性能）：挂在 `condition` 上，再按性能组分子对象（如 `mechanical_properties`）。
- `figure`（图片信息）：通过 `sample_id` / `condition_id` 引用骨架。

模板还声明：

- 允许的性能组列表（可被项目追加）。
- 步骤依赖：骨架步必须先于所有性能步和图片步。

模板不含字段列表（字段在库和覆盖层）。第一版另附一份空模板 `configs/templates/blank.json`：结构与钢铁相同，可用来建项目，但没有对应字段库；该项目只能新增私有字段。不实现第二套完整骨架（聚合物/化合物等）。

### 4.2 公共字段库

路径：`configs/field_library/steel.json`（第一版按钢铁模板建一份库；其它模板以后各有各的库，互不混用。）

库按类别组织，不是平铺清单。钢铁库类别与模板层级对应：

- 文章信息：文献名称、DOI、材料体系等
- 样品信息：样品编号、名称、成分、产品形态等
- 状态信息：状态编号、热处理、测试温度、工艺描述等
- 性能：再按性能组（力学性能、磁性能等）
- 图片信息：图号、类型、比例尺等

每条库字段固定包含：

- `id`：稳定标识，如 `doi`、`yield_strength`
- `label`：显示名，如「DOI 号」
- `category`：`metadata` | `sample` | `condition` | `property` | `figure`
- `group`：仅 `property` 使用，对应性能组 id；其它类别为 `null`
- `value_type`：`string` | `number_with_unit` | `composition` | `enum` | `boolean`
- `rule`、`positive_examples`、`negative_examples`、`note`

库是只读引用。项目勾选、改规则、改类别、加私有字段，默认都不写库。

### 4.3 项目覆盖层

路径保持项目清单在 `configs/project_config.json`；每个项目一份覆盖层 `configs/projects/<project_id>.json`（第一版把现有 `configs/fields/demo_steel.json` 的职责拆到「覆盖层 + 对库的引用」，demo 仍可跑）。

覆盖层包含：

- `template_id`：如 `steel`
- `selected_field_ids`：从库勾选的字段
- `private_fields`：本项目新建、未进库的字段（结构与库字段相同）
- `field_overrides`：对库字段的本项目修改（规则、类别、性能组、正反例）。未出现的键沿用库。
- `step_overrides`：可选。缺省则按性能组自动生成步骤。
- `property_source` / `figure_filter`：沿用现有白黑名单机制，放在项目覆盖层。

保存规则：

- 项目内编辑：只写覆盖层。
- 编辑一条来自库的字段时，明确二选一：**仅本项目覆盖**（默认）或 **写回公共字段库**。
- 私有字段可显式「提升到公共库」：写入库，并从 `private_fields` 改为 `selected_field_ids` 引用。
- 写回库会改变该字段的默认值；已有项目若未覆盖该键，下次加载会看到新默认。仅本项目覆盖的键不受影响。

### 4.4 新项目选字段

开新项目是主路径，不是附加功能：

1. 选模板（第一版主要是钢铁）。
2. 按类别浏览公共字段库并勾选。未勾选的库字段不进入该项目的 prompt 与步骤。
3. 需要时再新增私有字段，或覆盖某条库字段。

无磁钢与钛铜这类项目：同一钢铁模板，勾选集合不同。

### 4.5 步骤自动生成

有效字段 = 勾选的库字段经覆盖后 + 私有字段。

默认步骤：

1. `parse`（仅当本篇还没有 `paper.md` 且本次提供了 PDF 时；已有 md 则跳过）
2. `entity`：所有 `metadata` + `sample` + `condition` 字段，一次调用建骨架
3. 每个性能组一个 `property` 步骤：该组下的全部性能字段
4. `figure`：对骨架步已产出的图片记录做白名单过滤（确定性规则，不调 LLM）。钢铁模板下，图片元数据仍在骨架步由模型填写。

项目可用 `step_overrides` 合并或拆开性能步，但禁止把性能/图片排到骨架之前。空性能组不生成步骤。

### 4.6 导出项目字段与 Schema

导出的是**当前项目生效配置**（库字段经覆盖 + 私有字段），不是整份公共库，也不是其它项目的字段。

一次导出一份 JSON 文件，建议文件名 `<project_id>_fields_schema.json`，结构固定为：

```json
{
  "project_id": "demo_steel",
  "template_id": "steel",
  "exported_at": "2026-08-27T12:00:00",
  "fields": [
    {
      "id": "title",
      "label": "文献名称",
      "category": "metadata",
      "group": null,
      "origin": "library",
      "value_type": "string",
      "rule": "...",
      "positive_examples": "...",
      "negative_examples": "...",
      "note": ""
    }
  ],
  "steps": [{"id": "entity", "type": "entity", "name": "..."}],
  "schema": {
    "paper_metadata": {"title": {"value": "", "unit": "", "excerpt": "", "location": ""}},
    "samples": [{"sample_id": "", "sample_name": {"value": "", "unit": "", "excerpt": "", "location": ""}}],
    "conditions": [{"condition_id": "", "sample_id": "", "mechanical_properties": {}}],
    "figures": []
  }
}
```

约定：

- `fields` 按类别、再按性能组排序；`origin` 为 `library` 或 `private`。规则是生效规则（含覆盖）。
- `schema` 是该项目抽取结果 `paper.json` 的骨架（含出处字段形状），与界面「完整抽取 Schema」一致，并与实际合并输出对齐。标识字段在 schema 里仍是字符串。
- `steps` 是当前会实际执行的步骤列表（自动生成结果再叠加 `step_overrides`）。
- 导出不包含 API key、PDF、抽取结果。第一版只导出、不提供从该文件「一键导入覆盖另一项目」（避免和字段库写回语义搅在一起）。

HTTP：`GET /api/projects/:id/export`。CLI：`--export-fields-schema`。

## 5. 流水线行为

### 5.1 依赖与失效

- 性质值和图片挂在模板声明的实体 id 上。钢铁模板即 `sample_id` / `condition_id`。
- **必须先成功完成骨架，才能跑性能步和图片步。** 分阶段界面上，骨架未完成时这两类步骤不可用。
- **重跑整个骨架步 = 作废本 run 中已有的全部性质和图片，并自动把下游步骤全部重跑。** 不得把旧性能按 id 硬接到新骨架上。
- 只重跑某一个性能步：骨架保持，其它性能组结果保留。
- 只重抽某一个字段：不跑整个骨架步，因此不失效下游；只替换该字段。
- 标识字段不可单字段重抽：钢铁下为 `sample_id`、`condition_id`，以及指向它们的外键。要改编号必须重跑整个骨架步。

### 5.2 整篇一次跑完

一次调度：解析（如需要）→ 按 5.7 剪裁送入模型的文本 → 骨架 → 各性能组 → 图片 → 校验 → 合并。  
已有 `paper.md` 默认跳过解析；`--overwrite-parse` 或界面「覆盖解析」才重跑 UniParser。

`mode=single_pass`：仍抽完整 JSON，但跳过性能来源校验和图片白名单过滤，用于对照。

### 5.3 整篇分阶段跑

步骤图与一次跑完相同。每次请求带 `run_id` + `step_id`。  
中间产物仍落在该 `run_id` 下的 `entities/`、`properties/` 等目录。  
某步失败：该步可单独重试；不自动继续下游。骨架失败则下游保持不可用。

### 5.4 只重抽字段

输入：`project_id`、`field_id`、范围（`paper_id` 或「本项目全部已抽文献」）。

行为：

- 使用该字段的当前规则（含项目覆盖）。
- 只让模型产出该字段（外加 excerpt / location；性能字段外加 source）。性能字段的调用仍带上已有 condition 列表，禁止新增样品/状态。
- 合并时只替换该字段；同对象其它字段原样保留。标识字段拒绝此接口。
- 批量范围 = 该项目 `test_runs` 里已有合并结果的文献（按每篇最新成功 run）。一篇失败记入报告，继续下一篇。
- 失败时该字段保留旧值，并写警告，不丢整篇 `paper.json`。

改规则后的重抽是显式动作，保存覆盖层不会自动重跑。

### 5.5 出处

标识字段（`sample_id`、`condition_id` 及外键）保持普通字符串，不包出处。

其余抽取事实统一为对象：

```json
{
  "value": "685",
  "unit": "MPa",
  "source": "measured_table",
  "excerpt": "The yield strength of A-700 is 685 MPa",
  "location": "Table 2"
}
```

- `number_with_unit`：如上，`unit` 必填（无量纲可为空字符串）。
- `string` / `enum` / `boolean`：`value` 为对应类型，`unit` 为空字符串。
- `composition`：`value` 仍为元素-含量对象，出处挂在该对象同级的 `excerpt` / `location` 上，不给每个元素单独出处。
- `source` 仅性能字段必填；文章/样品/状态事实可省略。
- `location` 为表号、图号或章节标题（如 `Table 2`、`Section 3.1`）。

工作台在 `paper.md` 文本视图里用 `excerpt` 做规范化子串匹配并高亮。若当时正在看 PDF，点击字段则切到文本视图再高亮。未命中则在字段旁展示摘录和位置，不高亮其它段落。

校验阶段不得丢弃 `excerpt` / `location` / `source`。来源黑名单仍可剔除不可靠性能值，被剔除的值进入 review 列表并保留出处，方便核对。

### 5.6 PDF 解析

将 `/internfs/wangchenyan/shougang/scripts/parsing/parser.py` 的逻辑收进工具（如 `tools/pdf_parser.py`），不在运行时依赖那份脚本路径。

保留行为：

- UniParser 同步解析：`OCRHighQuality` 文本/表/公式，图和 chart 为 base64。
- 写出 `paper.md`，把 data-url 图存到 `images_from_md/`，并保存 `uniparser_submit_result.json`。
- 已存在 `paper.md` 默认跳过，除非覆盖。

必须改掉的硬编码：

- 默认 PDF 目录、默认输出到 `Extract_data/...` 一律不用。
- 输出到该项目配置的 `parsed_results` 目录下 `<paper_id>/`。新建项目默认为工作区内 `parsed_results/<project_id>/`。`demo_steel` 仍指向 `example_data/example_demo/parsed_results`。
- 上传的 PDF 同时保存为该文献目录下的 `source.pdf`，供以后打开，不替代 `paper.md` 作为抽取输入。
- API key 仍读环境变量 `UNIPARSER_API_KEY` / `UP_API_KEY` 或工作区 `.env`，不写进配置文件。

离线 `demo_steel` 继续用内置 `example_data/.../paper.md`，不调用 UniParser。

现有 `tools/paper_parser.py` 职责不变：从 `paper.md` 拆文本占位符和图片，供抽取模型使用。

### 5.7 输入剪裁（只去掉参考文献 / 致谢节）

**可实现，且已对照真实 UniParser `paper.md`。** 在核聚变批次 103 篇解析结果里：102 篇有独立 Markdown 标题（`# References` / `# Acknowledgements` / `# 参考文献` / `# 5. References` / `# VII. REFERENCES` 等）；0 篇出现在全文前半；3 篇在参考文献之后还有 `# Highlights` 或 `# Figure captions`。现有「从第一个匹配标题切到文末」会把这 3 篇后面的图注/highlight 一并丢掉。

因此改为按节删除，规则如下（确定性，不调 LLM）：

落盘的 `paper.md` 始终是完整原文。剪裁只作用于送进抽取模型的文本；工作台左侧仍显示完整 `paper.md`，出处高亮也在完整文本上做。

1. 只看 Markdown 标题行（一行以 `#` 开头）。正文里的 “see References”、`[4]` 不删。
2. 规范化标题：去掉 `#`、首尾空白和冒号；再去掉开头编号，包括阿拉伯数字（`5.` / `5)`）、罗马数字（`VII.`）、中文序号（`六、`）。规范化后必须**整段**等于下列之一（大小写不敏感）：
   - 参考文献：`reference`、`references`、`bibliography`、`参考文献`、`文献引用`、`references and notes`
   - 致谢：`acknowledgement`、`acknowledgements`、`acknowledgment`、`acknowledgments`、`致谢`、`鸣谢`
   真实数据里出现过的写法（`REFERENCES`、`ACKNOWLEDGMENT`、`5. References`、`VII. REFERENCES`）都覆盖在上述规则内。
3. 每个命中标题对应**一节**：从该标题行起到下一个同级或更高级标题之前（不含下一标题）；后面没有标题则到文末。致谢和参考文献各删各的。下一标题若是 `Highlights`、`Figure captions`、`Appendix` 等，那一节保留。
4. 该标题起点落在全文前 50% 字符处则不删，记入 `skipped_too_early`（本批 103 篇未出现，作为误匹配保险）。
5. 对不上任何标题时全文送入模型，不强行猜（例如标题写成 `VII. REFERENCES` 却漏了罗马数字规则——实现时必须覆盖罗马数字，避免再漏）。

剪裁统计写入 `inputs/input_trim_stats.json`：删了哪些节（标题、起止、字符数）、跳过了哪些、保留比例。

第一版不做：用模型判断参考文献、按「参考文献」正文关键词切割、删除附录/图注。

## 6. 界面

仍为左右对照工作台，去掉「只能钢铁 / 只能已有 paper.md」的假设。

主操作：上传 PDF 或选择已有文献；四个入口按钮；分阶段步骤条。骨架未完成时性能步、图片步灰色。重跑骨架前确认：「下游性质和图片将作废并重跑」。

左侧原文：有 PDF 显示 PDF，否则 `paper.md`。点击右侧字段时尝试高亮出处。

右侧结果：按模板类别展示（文章信息、样品、状态、各性能组、图片），每条可见值、单位、位置、摘录状态（已定位 / 仅摘录）。

字段配置（同一页）：

- 新项目：选模板 → 按类别勾选库字段 → 可选新增私有字段。
- 已有项目：勾选变更、编辑规则、把字段改到另一类别或另一性能组（只写覆盖层）。
- 改库字段时选择「仅本项目」或「写回公共库」。
- 性能组变化后预览将生成的步骤，需要时再改 `step_overrides`。
- **导出项目字段与 Schema**：字段配置区提供「导出」；下载一份 JSON（见 4.6）。页面上仍可单独复制 Schema 文本。

字段改动保存后立即作用于**下一次**抽取或重抽，不改写已经落盘的旧 run，除非用户再跑。

## 7. 错误处理

| 情况 | 处理 |
| --- | --- |
| UniParser 无 key / 服务失败 | 停在解析步，返回明确错误；不进入抽取。 |
| 解析结果 `content` 为空 | 该文献失败，不写空 `paper.md` 充数。 |
| 骨架调用失败或 JSON 无效 | 不跑下游；分阶段下性能/图片保持不可用。 |
| 某一个性能步失败 | 其它已完成性能组保留；该步可重试。 |
| 单字段重抽失败 | 保留旧值 + 字段级警告。 |
| 批量重抽中单篇失败 | 记入报告，继续其余文献。 |
| 摘录无法在原文匹配 | 不视为抽取失败；标记「仅摘录」。 |
| 性能来源命中黑名单 | 从最终性能中剔除，进入 review 列表，保留出处。 |

远端 `Extract_data` 只读。本工具只写工作区内的 `parsed_results/` 与 `test_runs/`。

## 8. 数据与 API

### 8.1 落盘

```text
parsed_results/<project_id>/<paper_id>/   # 路径以项目配置为准
  source.pdf                    # 上传过 PDF 时
  paper.md
  images_from_md/
  uniparser_submit_result.json  # 仅真正调用过 UniParser 时

test_runs/<project_id>/<test|data>/<run_id>/
  RUN_INFO.json
  summary.md
  inputs/
  prompt_preview/
  entities/
  properties/
  merged_outputs/paper.json
  review_notes/
```

`RUN_INFO.json` 增加：`template_id`、已完成步骤、失效步骤、解析是否跳过。

同一文献分阶段跑共用一个 `run_id`，直到整篇完成或用户新开一次运行。

### 8.2 HTTP（在现有 workbench_server 上扩展）

- `POST /api/projects`：新建项目（模板 + 勾选字段 + 名称）
- `POST /api/parse`：PDF → `paper.md`
- `POST /api/run`：整篇一次跑完（可含「无 md 则先解析」）
- `POST /api/run_step`：`run_id` + `step_id`；若 `step_id` 为骨架且该 run 已有下游结果，则作废并重跑下游
- `POST /api/reextract`：`field_id` + `paper_id` 或 `scope=project_extracted`
- `GET /api/field_library?template=steel`
- `GET/PUT /api/projects/:id/config`：覆盖层读写
- `POST /api/field_library/writeback`：把某字段写回库（需显式）
- `POST /api/field_library/promote`：私有字段提升入库
- `GET /api/projects/:id/export`：下载生效字段 + Schema（见 4.6）

CLI 与 HTTP 能力对齐：`--run-once` 保留；增加 `--parse-only`、`--step`、`--reextract-field`、`--export-fields-schema`。

## 9. 验收

1. **离线 demo（无 UniParser、无抽取 API key）**  
   用 `demo_steel` 内置文献：一次跑完、分阶段（先骨架后性能）、单字段重抽、结果可点出处（mock 后端返回 excerpt/location）。改项目规则后库文件内容不变。

2. **解析**  
   有 UniParser key 时，上传 PDF 后在 `parsed_results/<project>/...` 得到 `paper.md` 与图片；不写 `Extract_data`。无 key 时错误信息明确。已有 md 默认不重复解析。

3. **新项目选字段**  
   基于钢铁模板新建项目，按类别从库勾选子集（例如只勾文章信息 + 样品 + 力学），生成的步骤不含未勾选的磁性能组；跑 demo 文本时 prompt 只含勾选字段。

4. **覆盖 vs 写回**  
   改一条库字段规则并选「仅本项目」，库文件不变。选「写回」后库文件更新。

5. **骨架失效**  
   分阶段已抽完性能后重跑骨架：旧性能不得出现在新合并结果里，下游自动重跑。

6. **出处**  
   最终 `paper.json` 的字段对象含 `excerpt` 与 `location`；能匹配的在原文高亮，不能匹配的展示摘录而不乱高亮。

7. **导出**  
   在 demo_steel 点导出（或 CLI）得到 JSON：含该项目勾选/私有字段及规则、步骤、以及与合并结果形状一致的 schema。改覆盖层后再导出，文件中的规则随之变化；公共库未写回则库文件仍不变。

8. **剪裁**  
   一篇 `paper.md` 在参考文献节之后还有 `## Appendix` 时：送入模型的文本不含 References/Acknowledgements 节，但含 Appendix；落盘的 `paper.md` 仍完整。从第一个参考文献标题切到文末的旧行为视为失败。

## 10. 现有代码如何演进

- `tools/pipeline.py`：prompt/合并改为读模板层级；性能步按项目有效字段分组；校验保留出处；增加 `run_step` 与 `reextract_field`；输入剪裁改为按节删除参考文献/致谢（见 5.7）。
- `tools/pdf_parser.py`：新文件，移植 UniParser 调用与存图，路径改到工作区。
- `tools/workbench_server.py`：增加上一节 API；上传 PDF。
- `app/`：四个入口、步骤依赖、字段库勾选、出处高亮、覆盖/写回选择、导出字段与 Schema。
- `configs/templates/`、`configs/field_library/`、`configs/projects/`：新配置；`demo_steel` 作为第一份完整钢铁示例。
- 四个旧项目（`non_magnetic` 等）保持只读快照，第一版不迁移。

Prompt 角色描述改为「材料文献结构化抽取专家」，由模板注入领域提示（钢铁模板仍可写明金属材料），避免写死「只能钢铁」。
