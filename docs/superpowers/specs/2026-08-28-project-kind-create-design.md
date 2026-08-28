# 新建项目选定文献 / 专利 · 设计规格

日期：2026-08-28  
范围：新建项目时选定文档类型；可选从已有项目复制抽取配置；按类型写入互斥标识字段 `doi` 或 `patent_number`；复核/导出左侧补已抽取文献列表。  
前置：`2026-08-28-document-kind-trim-design.md`（项目级 `document_kind`、剪裁分发已落地）、`2026-08-28-field-stage-config-design.md`（覆盖层字段 / 阶段）。  
不依赖 `Extract_data`。

## 1. 目标与非目标

### 1.1 目标

文献抽取和专利抽取共用同一套字段、阶段和抽取引擎，差别只有两处：

1. 送入模型前的文本剪裁（已由 `document_kind` 分发，本块不改规则）。
2. 文章级标识：文献用 `doi`，专利用独立字段 `patent_number`。

用户不再需要让人按领域手工加 `cuti_patent`、`non_magnetic_patent` 这类项目。在「新建」里选定类型，或从已有文献项目复制配置后再选「专利」，即可得到同领域的专利项目。

复核和导出页左侧栏目前空白。本块同时补上本项目已抽取文献列表，点击切换当前篇的原文与抽取结果。

成功标准：

- 新建对话框必选「学术文献」或「专利」，创建结果的 `document_kind` 与选择一致，不再写死 `paper`。
- 可选「从已有项目复制」：新项目带上源项目的字段 / 阶段 / 策略，但不带 PDF、解析结果或运行记录。
- 文献项目有效字段含 `doi`、不含 `patent_number`；专利项目相反。
- 配置页改类型并保存后，标识字段按同样规则替换。
- 同一项目仍只有一种文档类型；不按单篇混放。
- 复核、导出页左侧不再空白：列出本项目已抽取文献，点击即切到该篇原文与抽取结果。

### 1.2 本块不做

- 按单篇或按某次 run 选类型
- 为专利另做一套性能字段 / 阶段 / prompt（复制来的配置即复用）
- 把 `doi` / `patent_number` 写入公共钢铁字段库
- 自动拆出现有领域的 `*_patent` 项目，或主动改写已有覆盖层文件
- 改 UniParser、剪裁规则、导出列映射（导出仍按覆盖层里实际存在的 metadata 字段输出）
- 同一项目同时保留 `doi` 与 `patent_number`
- 复核页改值 / 标注；导出页嵌入 PDF 预览
- 给配置页或项目页也加文献列表

## 2. 数据模型

### 2.1 标识字段（私有 metadata）

两个字段都是项目覆盖层的 `private_fields` 条目，`category` 为 `metadata`，`value_type` 为 `string`。**不**加入 `configs/field_library/steel.json`，避免与现有项目里已经存在的私有 `doi` 在 `effective_fields` 中重复出现。

规范定义：

| id | 界面标签 | 规则（写入 `rule`） | 正例 |
| --- | --- | --- | --- |
| `doi` | DOI | 填写文献 DOI；可从目录名/paper_id 推断，不要编造。 | `10.1016/j.msea.2005.04.015` |
| `patent_number` | 专利号 | 填写专利号（如 CN110218899B）；可从目录名/paper_id 推断，不要编造。 | `CN110218899B` |

负例：`doi` 不要填期刊名或站点首页；`patent_number` 不要填 DOI。`note` 均为「文章级标识，全篇只出现一次。」`group` 为 `null`，`positive_examples` / `negative_examples` 用上表短句即可。

`selected_field_ids` 里同时列出该 id（与现有 cuti 对 `doi` 的写法一致）。`effective_fields` 现有逻辑不变：库勾选走图书馆，私有字段整表追加。

互斥：任一时刻覆盖层只应有其中一个。

### 2.2 应用函数 `apply_document_kind_identifier(overlay) -> overlay`

在内存中改 `overlay`，不写盘。调用方在 `normalize_document_kind` 之后调用。

1. `kind = overlay["document_kind"]`（此时已是 `paper` 或 `patent`）。
2. `want = "doi"` 若 `kind == "paper"`，否则 `"patent_number"`。
3. `drop = "patent_number"` 若 `kind == "paper"`，否则 `"doi"`。
4. 从 `selected_field_ids` 去掉 `drop`。
5. 从 `private_fields` 去掉 `id == drop` 的条目。
6. 从 `field_overrides` 去掉 `drop` 键（若有）。
7. 若 `private_fields` 中已有 `id == want`：保留该条目（不覆盖用户改过的规则）。否则追加第 2.1 节规范定义。
8. 若 `selected_field_ids` 中没有 `want`：插在 `title` 之后；没有 `title` 则插到列表最前。

不改 `steps`。标识字段是 metadata，不挂性能阶段。

### 2.3 调用点

| 时机 | 行为 |
| --- | --- |
| `create_project` 写盘前 | 先定 `document_kind`，再 `apply_document_kind_identifier` |
| `save_overlay` 写盘前 | 在规范化 `document_kind` 之后、`validate_overlay_stages` 之前调用 |

因此：配置页把项目从文献改成专利并「保存配置」，也会把 `doi` 换成 `patent_number`。任意一次 `save_overlay` 都会跑该函数，不只在类型发生变化时：现有文献项目若还没有 `doi`，下次保存配置会补上；已有 `cuti_patent` 若仍带着 `doi`，下次保存会换成 `patent_number`。本块不单独改已有覆盖层文件，也不写迁移脚本。

已有 run / `paper.json` 不改写。旧结果里若有 `paper_metadata.doi`，重抽或整篇再跑后才会出现 `patent_number`。保存成功提示沿用：「需重新抽取后结果才按新配置。」

## 3. 新建项目

### 3.1 `create_project` 签名

在现有参数上增加：

```
document_kind: str | None = None
copy_from: str | None = None
```

缺省 `document_kind` 仍视为 `paper`（与 `normalize_document_kind` 一致）。空字符串的 `copy_from` 视为未复制。

项目 id / 名称校验保持现状；本块不新增强制命名规则。

### 3.2 未复制：按模板勾选

与现网相同：用调用方传入的 `template_id` 与 `selected_field_ids`，补锁定字段，生成 `steps`。然后：

- 写入规范化后的 `document_kind`
- 调用 `apply_document_kind_identifier`（因此从模板新建的文献项目会带上 `doi`，专利项目会带上 `patent_number`）
- `save_overlay` + 写入 `project_config.json`（路径规则不变）

这是相对现网的行为变化：以前从 steel 模板新建的项目没有 `doi`；本块之后文献新建默认有 `doi`。

### 3.3 复制：`copy_from`

`copy_from` 必须是 `project_config.json` 里已有、且覆盖层文件存在的项目 id。否则 `ValueError`，中文信息：`复制来源不存在: <id>`。`copy_from` 等于新项目 id 同样拒绝：`不能复制到相同项目 id`。

复制时：

1. 读取源覆盖层（深拷贝）。
2. **忽略**调用方的 `template_id` 与 `selected_field_ids`，改用源项目的 `template_id`。
3. 从源覆盖层保留这些键：`template_id`、`selected_field_ids`、`private_fields`、`field_overrides`、`steps`、`step_overrides`、`property_groups`、`property_source`、`figure_filter`。源里缺的键用与现网 `create_project` 相同的空默认（`[]` / `{}` / `null`）。
4. **不**复制源的 `document_kind`；写入本次请求的 `document_kind`。
5. 调用 `apply_document_kind_identifier`。
6. 仍按现网规则补 `LOCKED_FIELD_IDS`（该 id 在源模板对应库中存在且未选则追加），避免源项目漏锁字段。
7. 写入新项目覆盖层与 `project_config.json` 条目（`parsed_results` / `test_runs` 指向新 id 目录）。不创建、不拷贝源项目的 PDF、`parsed_results`、`test_runs`。

源项目本身不被修改。

落盘顺序：先在内存做完 `apply` + 阶段校验，通过后再写覆盖层与项目表。校验失败不写任何新文件。

### 3.4 API

`POST /api/projects` body 增加可选字段：

```json
{
  "id": "cuti_patents",
  "name": "钛铜专利",
  "template_id": "steel",
  "selected_field_ids": ["title", "yield_strength"],
  "document_kind": "patent",
  "copy_from": "cuti"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` / `name` | 与现网相同 | 现网校验 |
| `template_id` | 未复制时用 | 复制时被源项目覆盖 |
| `selected_field_ids` | 未复制时用 | 复制时忽略 |
| `document_kind` | 否 | 缺省 `paper`；非法值与现网覆盖层一样 4xx |
| `copy_from` | 否 | 空或缺省 = 不复制 |

响应仍为 `{ ok, overlay, id }`。`overlay` 含最终 `document_kind` 与标识字段。

## 4. 界面

### 4.1 新建对话框（主入口）

在现有「模板」与「勾选库字段」之间增加：

1. **文档类型**（必选下拉）：学术文献 / 专利，默认学术文献。一句说明：文献砍参考文献；专利从实施方式/实施例起保留；标识字段分别为 DOI / 专利号。
2. **从已有项目复制**（下拉）：第一项「不复制（按模板勾选）」，其余为 `GET /api/projects` 的项目（显示名称 + id）。

选定复制来源后：

- 「模板」与「勾选库字段」禁用（或灰显），提示「字段与阶段将从 <源项目名> 复制，创建后可在配置页修改。」
- 提交时 `template_id` / `selected_field_ids` 仍可带当前表单值，后端以源项目为准。

未选复制：行为与现网勾选创建相同，另加文档类型。

创建成功后仍切换到新项目（现网 `selectProject`）。

### 4.2 配置页

「文档类型」下拉保留。说明改为：影响剪裁，并且保存时会把 DOI / 专利号换成与类型匹配的标识字段；不改性能字段和阶段。

下拉改动仍只进草稿，点「保存配置」才 PUT。`save_overlay` 执行标识替换。

侧栏与「文献与运行」页的文献/专利徽章不变。

文献表、上传、导航文案本块仍不改（继续叫「文献」）。

## 5. 错误处理

| 情况 | 行为 |
| --- | --- |
| 非法 `document_kind` | 与现网相同：`ValueError` / 4xx，不写盘 |
| `copy_from` 未知或覆盖层缺失 | 不写盘；界面「新建项目失败：复制来源不存在: …」 |
| `copy_from` 等于新 id | 不写盘；「不能复制到相同项目 id」 |
| 新 id 已存在 | 保持现网行为（本块不新开覆盖/拒绝规则） |
| 源项目 `steps` 校验失败 | 先在内存做完 `apply` + `validate`，通过后再写覆盖层与项目表。校验失败不写任何新文件 |
| 专利未填 `patent_number` 规则 | 使用第 2.1 节默认规则，不报错 |

## 6. 测试

不要求浏览器 E2E。至少覆盖：

- `apply_document_kind_identifier`：`paper` 保证有 `doi`、去掉 `patent_number`；`patent` 相反；已有自定义 `doi.rule` 的文献项目不被重置。
- `create_project(..., document_kind="patent")` 无复制：`document_kind == "patent"`，私有字段含 `patent_number`，不含 `doi`。
- `create_project` 缺省类型：`paper`，含 `doi`。
- 复制：在临时工作区放一个带 `doi` 与自定义 `steps` 的源项目，`copy_from` 后选 `patent`：新 overlay 的 `steps` / `property_source` 与源相同，`document_kind == "patent"`，`doi` 已换成 `patent_number`；源 overlay 未改；新 `parsed_results` 路径指向新 id 且目录未从源拷贝。
- `copy_from` 不存在：抛错且无新 overlay 文件。
- `save_overlay` 把已有 `doi` 的 overlay 改成 `patent` 后，落盘结果换成 `patent_number`。
- `POST /api/projects` 把 `document_kind` 与 `copy_from` 传进 `create_project`（可用现有 API handler 测试风格）。
- 前端：新建对话框含文档类型下拉与复制下拉；`saveNewProject` 的 JSON 含 `document_kind`；选了复制来源时请求带 `copy_from`。

现有 `test_create_project_defaults_document_kind_paper` / `test_create_project_selects_subset` 若断言「无私有字段」或精确字段列表，按「文献新建会多出 `doi`」更新。

复核 / 导出侧栏（第 8 节）：

- 静态：侧栏一节 `data-view-panel="review export"`，内含 `#extractedPaperList`；`setView` 按空白拆分 `data-view-panel`。
- `app.js` 存在根据 `extracted === true` 渲染列表、点击调用与 `loadReview` 相同载入路径的逻辑。
- 空列表文案含「还没有已抽取」。

## 7. 相对已落地能力的关系

- 剪裁分发、徽章、配置页下拉：**保留**。本块补上新建入口、复制、标识字段，以及复核/导出侧栏。
- 仓库里已有的 `cuti_patent` 可继续用；不是本块的交付物，也不删除。用户之后可以用「从 cuti 复制 + 专利」自己建同类项目。
- 配置页说明从「不改字段」改为「会替换标识字段」，避免与实现矛盾。

## 8. 复核 / 导出：已抽取文献侧栏

复核和导出视图里，主布局左侧栏（与项目页的项目列表、文献页的运行进度同一条 `aside.sidebar`）目前没有对应的 `data-view-panel`，所以是空的。本块补上**本项目已抽取文献**列表，交互对齐 VS Code 最左侧资源管理器：窄列、可滚动、当前项高亮、点击切换。

### 8.1 谁出现在列表里

只列当前项目 `papers` 里 `extracted === true` 的条目（与「文献与运行」表的「已抽取」同一判定）。未解析、只解析未抽取的不出现。

每项主文案：`title`，没有标题则用 `paper_id`。标题过长单行省略。不在侧栏做搜索、分组或勾选批量。

无已抽取文献时，列表区一句：`本项目还没有已抽取文献`。不假装有可点项。

### 8.2 和当前文献的关系

列表与全站 `state.paperId` 共用。当前项加 `active`（样式可复用项目列表 / 文献表高亮）。

点击一项：

1. 将该篇设为当前文献（同步文献页下拉 / 表格高亮，若那些节点在 DOM 里）。
2. 立即走与「载入原文和最新结果」相同的路径：左侧原文（PDF 优先，否则渲染 `paper.md`），右侧最新抽取结果。
3. **不自动切换顶栏视图**。在复核页当场更新左右栏；在导出页只改「当前文献」，「导出抽取结果」针对这篇（未选时仍导出本项目全部已抽，现网文案保留）。从导出切到复核时，若当前篇已抽取，进入复核即自动载入，不必再点「载入原文和最新结果」。

进入复核视图时：若已有当前 `paperId` 且该篇在已抽列表中，自动载入一次。

### 8.3 两页共用一块 DOM

侧栏增加**一个** `section`，`data-view-panel="review export"`（空格分隔）。`setView` 改为：元素的 `data-view-panel` 按空白拆开，当前视图名在其中则显示。这样复核和导出共用同一份 `#extractedPaperList`，同一高亮，不必维护两套 DOM。

标题：`已抽取`。不改项目页、配置页、文献与运行页的侧栏内容。

不新开 API：继续用现有项目 `papers` 与 `/api/result`。

### 8.4 本块侧栏不做

- 未抽取文献、解析失败项
- 在侧栏里删除文献或删除 run
- 导出页再做一套原文/结果预览（原文对照只在复核页）
