# 文档类型（文献 / 专利）剪裁 · 设计规格

日期：2026-08-28  
范围：工作台按**项目**选择文档类型，从而在送入 LLM 前选用不同的 parser 文本剪裁。不重写抽取引擎，不改 UniParser。  
前置：`2026-08-28-field-stage-config-design.md`（配置进草稿、仅「保存配置」落盘）、`2026-08-28-paper-upload-batch-design.md`（`paper.md` 仍是解析产物）。  
对照实现：`Extract_data/cuti_patent/scripts/cuti_patent_text_filter_probe.py` 的 `core_text` 规则；本仓库运行时**不依赖** `Extract_data`。

## 1. 目标与非目标

### 1.1 目标

文献和专利的 UniParser 产物都是 `paper.md`，但送进抽取模型前要丢掉的段落不同：

- **学术文献**：继续砍 References / Acknowledgements（现有 `trim_input`）。
- **专利**：丢掉摘要、技术领域、背景、权利要求等前部与权利要求块，优先从「具体实施方式 / 实施例」起保留，得到 `core_text`。

用户在配置页选「学术文献」或「专利」，随「保存配置」写入该项目；之后该项目所有文档的整篇抽取、分阶段抽取，都按这个选择做前处理。字段、阶段、prompt 仍用该项目自己的覆盖层（例如钛铜 `cuti` 继续用自己的字段和阶段），只是喂进去的文本变了。

成功标准：

- 同一项目只能是一种文档类型；改完并保存后，新的整篇/阶段跑使用对应剪裁。
- 专利样例（含摘要 / 权利要求 / 实施例）剪裁后只留下实施例侧；文献样例仍砍参考文献。
- `paper.md` 原文不被改写。

### 1.2 本块不做

- 按单篇或按某次 run 选类型（不是项目级覆盖）
- 为专利另做一套字段 / 阶段 / prompt
- 超长专利分段 stage1 / chunked 抽取
- 改 UniParser，或按类型换解析器
- 运行时 import / 调用 `Extract_data` 里的脚本
- 把现有项目（含 `cuti`）默认改成专利；缺字段一律按文献
- 本轮不使用专利脚本里的 `figure_text` / 附图说明索引（工作台当前也不跑图片过滤步）

## 2. 数据模型

### 2.1 字段

项目覆盖层 `configs/projects/<project_id>.json` 增加：

```json
"document_kind": "paper"
```

| 值 | 界面文案 | 剪裁 |
| --- | --- | --- |
| `paper` | 学术文献 | `tools/input_trim.py` 的 `trim_input` |
| `patent` | 专利 | 迁入本仓库的专利过滤器，取 `core_text` |

只允许这两个字符串。缺省、`null`、空字符串一律视为 `paper`。`create_project` 显式写入 `"document_kind": "paper"`。已有覆盖层不必回填文件。

`document_kind` 只存在覆盖层，不写 `project_config.json`。`GET /api/projects` 从覆盖层读出后挂到项目对象上，供列表徽章使用。

### 2.2 保存与校验

`save_overlay` 在写盘前规范化并校验：

- 缺省 / 空 → 写成 `"paper"`
- 非法值（任何非 `paper` / `patent`）→ `ValueError`，HTTP 与现有覆盖层校验失败一样返回错误，不写盘

前端「保存配置」把下拉当前值写入 `overlay.document_kind`，与字段 / 阶段 / 策略同一请求 PUT。下拉改动只进草稿，刷新未保存则复原。

不新增独立 REST：「选择文献还是专利」就是覆盖层字段 + 配置页控件。

## 3. 界面

配置页在「抽取阶段」卡片**上方**增加一节「文档类型」：

- 下拉两项：学术文献 / 专利
- 一句说明：只影响送入模型前的文本剪裁，不改字段和阶段；专利会去掉摘要、技术领域、背景和权利要求，从实施方式/实施例起保留
- 与其它配置一样，点「保存配置」才落盘

侧栏项目列表：项目名旁小标签「文献」或「专利」（由 `GET /api/projects` 的 `document_kind` 决定，缺省显示「文献」）。

「文献与运行」页：当前项目标题附近同样显示该标签，避免配成专利后仍看起来像在跑论文。

文献表、上传 PDF、解析流程文案保持「文献」习惯用语，本轮不改导航名。

## 4. 前处理与管线

### 4.1 分发

新增单一入口（放在 `tools/input_trim.py`：`prepare_model_text(text, document_kind, paper_id="") -> (str, dict)`；专利实现放在 `tools/patent_text_filter.py`）：

1. 规范化 `document_kind`（空 → `paper`）
2. `paper` → 现有 `trim_input`
3. `patent` → 专利过滤器的 `core_text`
4. 其它值 → `ValueError`（运行时不应出现；保存已拦住）

两种路径互斥，**不叠加**（专利文本不再跑参考文献剪裁）。

统计字典至少包含：`raw_chars`、`kept_chars`、`kept_ratio`、`dropped_chars`、`document_kind`。专利路径额外：`core_start_found`（是否命中实施方式/实施例标题）。

`document_kind` 的读取：覆盖层优先；读不到再当 `paper`。`pipeline` 两处必须走分发，不能再写死 `trim_input`：

- `_prepare_run`：解析 `paper.md` 之后、组 prompt 之前
- 单字段重抽：仅当 `inputs/parsed_text.txt` **不存在**时，从原文重新剪裁

`paper.md` 只读。剪裁结果仍写入该次 run 的 `inputs/parsed_text.txt`（与现网一致）。

### 4.2 改类型之后何时生效

保存 `document_kind` **不**改写已有 run。

- 整篇跑、按阶段跑：`_prepare_run` 按**当前**覆盖层重新剪裁，新 run 生效
- 只重抽：若该 run 已有 `inputs/parsed_text.txt`，沿用该文件（与现网一致）。要让新类型生效，须整篇再跑

配置保存成功提示沿用现有：「需重新抽取后结果才按新配置。」

### 4.3 专利过滤器（迁入，行为对齐 probe）

新模块 `tools/patent_text_filter.py`，从 `cuti_patent_text_filter_probe.py` **复制规则**，去掉探测脚本专属部分：

**迁入**

- 噪声清洗（`www.` / soopat / 蓝色字体提示、压缩空行）
- 标题抽取（`[54] 发明名称` 等）
- `CORE_START_RE` + `first_core_start`（有「具体实施方式」等强标题时不用光杆「实施例」）
- 命中核心起点：从该标题截到文末
- 未命中：`DROP_BLOCK_RE` 丢掉摘要 / 技术领域 / 背景 / 权利要求等块
- `core_text` 头部：`# {title}\n\n[文档ID] {paper_id}\n\n`（`paper_id` 用当前目录名；没有标题和 id 则不加头）

**不迁入本轮路径**

- `figure_text`、附图说明切片、占位符上下文索引
- `audit()`、命令行、对 `Extract_data` / `paper_parser` 的依赖
- 重要性命中审计（`IMPORTANT_RE`）

超长专利仍走现有「整篇一次」+ 模型侧截断，本轮不加分段。

## 5. API 与配置读写

| 接口 | 变化 |
| --- | --- |
| `GET /api/projects/<id>/config` | 覆盖层多 `document_kind`；缺则前端当 `paper` |
| `PUT` 同一路径 | body 带 `document_kind`；非法值 4xx，错误信息可读 |
| `GET /api/projects` | 每个项目多 `document_kind`（从覆盖层读，缺省 `paper`） |
| `POST` 新建项目 | 新覆盖层带 `"document_kind": "paper"` |
| 解析 / 跑批 / 复核 | 无新参数；剪裁只看项目覆盖层 |

## 6. 测试

- 文献：现有 `tests/test_input_trim.py` 继续通过；分发 `kind=paper` 与直接 `trim_input` 一致
- 专利：构造含「摘要 / 技术领域 / 权利要求书 / 具体实施方式或实施例」的短文本；`core_text` 含实施例侧，不含摘要与权利要求标题块
- 专利：只有光杆「实施例」、且前文也出现该词时，行为与 probe 的 `first_core_start` 一致（有强标题优先生强标题）
- 规范化：缺省 / `""` → `paper`；`"book"` 等非法值在 `save_overlay` 抛错
- `create_project` 结果含 `document_kind == "paper"`
- `GET /api/projects` 带 `document_kind`（可用现有 API handler 测试风格）
- 管线：mock 覆盖层为 `patent` 时，`_prepare_run` 使用的文本是专利 `core_text` 而不是文献剪裁结果（若现有 prepare 测试不好接，至少测分发函数 + 确认两处调用点改为分发）

不要求浏览器 E2E。配置页下拉属于实现清单，以手工点一次「改成专利 → 未保存刷新复原 → 保存后再进仍是专利」为准。

## 7. 错误处理

- 保存非法 `document_kind`：不写盘，配置页显示现有「保存配置失败：…」
- 运行时覆盖层缺字段：当 `paper`，不报错
- 专利未找到核心起点：走 drop-block 回退，不失败；可能几乎整篇保留（除去明确丢掉的块）
- 专利剪完为空：与现网空文本一样交给后续步骤，不在剪裁层另造错误码
