# 可配置材料文献抽取工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有钢铁抽取工作台改成「模板 + 公共字段库 + 项目覆盖」驱动，并补上 PDF 解析、按节剪裁参考文献/致谢、分阶段跑、单字段重抽、出处高亮、导出字段与 Schema。

**Architecture:** 在 `steel_extract_tool_workspace` 上演进，不重写引擎。配置解析集中在 `tools/config_model.py`；剪裁、出处、PDF 各一个模块；`pipeline.py` 只负责调度。运行时按模板层级读写 JSON。第一版只完整交付钢铁模板 + `blank` 空接口；四个旧项目保持只读快照。

**Tech Stack:** Python 3 标准库 + 现有 `pipeline.py` / `workbench_server.py` / mock 后端；测试用 `python3 -m pytest`；前端仍是 `app/index.html` + `app.js`；UniParser 仅在有 key 时调用，测试用假 client。

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-27-configurable-extract-tool-design.md`，本计划不得扩大非目标。
- 禁止写入 `/internfs/wangchenyan/shougang/Extract_data`。
- 不迁移 `non_magnetic` / `nuclear_fusion` / `cor_res` / `cuti` 四个只读快照。
- Prompt 角色用「材料文献结构化抽取专家」，领域提示来自模板 `domain_hint`。
- 工作区截至 2026-08-27 **不是 git 仓库**。每个 Commit 步先跑 `git rev-parse --is-inside-work-tree`；失败则跳过 commit，不要 `git init`。
- 测试命令：`cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest -q`。若 pytest 未安装：`python3 -m pip install pytest -q`。
- 标识字段（钢铁：`sample_id`、`condition_id` 及指向它们的外键）保持普通字符串，禁止单字段重抽。

---

## 文件结构

| 路径 | 职责 |
| --- | --- |
| `tools/input_trim.py` | 按节删除参考文献/致谢，返回剪裁文本 + 统计 |
| `tools/config_model.py` | 模板、字段库、覆盖层解析、步骤生成、写回/提升、导出 |
| `tools/provenance.py` | 出处对象形状、摘录匹配 |
| `tools/pdf_parser.py` | UniParser 包装：PDF → 项目 `parsed_results` |
| `tools/pipeline.py` | 调度：全跑 / 单步 / 重抽；调用上面模块 |
| `tools/llm_backends.py` | mock 返回 excerpt/location |
| `tools/workbench_server.py` | HTTP + CLI 扩展 |
| `configs/templates/steel.json` | 钢铁骨架 |
| `configs/templates/blank.json` | 空模板接口 |
| `configs/field_library/steel.json` | 钢铁公共字段库 |
| `configs/projects/demo_steel.json` | demo 覆盖层 |
| `configs/project_config.json` | 指向新覆盖层 |
| `tests/` | 单元/集成测试 |
| `app/index.html`, `app/app.js`, `app/styles.css` | 四个入口、字段库勾选、出处、导出 |

`configs/fields/demo_steel.json` 在 Task 2 迁移后仅作只读备份，运行时不再读取。

---

### Task 1: 按节剪裁参考文献/致谢

**Files:**
- Create: `tools/input_trim.py`
- Create: `tools/__init__.py`（空文件，使 `from tools.input_trim` 可导入）
- Create: `tests/conftest.py`
- Create: `tests/test_input_trim.py`
- Modify: `tools/pipeline.py`（`trim_input` 改为调用本模块；旧正则切到文末删除）

**Interfaces:**
- Consumes: 无
- Produces: `trim_input(text: str) -> tuple[str, dict]`，统计字典含 `raw_chars`、`kept_chars`、`kept_ratio`、`dropped_chars`、`removed_sections`（list of `{title, start, end, chars}`）、`skipped_too_early`（list）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_input_trim.py
from tools.input_trim import trim_input

APPENDIX_AFTER_REFS = """# Intro
body with see References in prose and [1] cites.

# Results
measured 685 MPa

# References
[1] Smith 2019

# Appendix
keep this appendix table
"""

ACK_THEN_REFS = """# Methods
do work

# Acknowledgements
thanks lab

# References
[1] Lee 2020
"""

ROMAN = """# VI. CONCLUSIONS
done

# VII. REFERENCES
[1] Nyilas 1990
"""

EARLY = """# References to prior work
this is related work in the first half of a long paper
""" + ("x" * 400) + """
# Results
real results here
"""


def test_keeps_appendix_after_references():
    kept, stats = trim_input(APPENDIX_AFTER_REFS)
    assert "keep this appendix table" in kept
    assert "[1] Smith 2019" not in kept
    assert "measured 685 MPa" in kept
    titles = [s["title"] for s in stats["removed_sections"]]
    assert any("References" in t for t in titles)


def test_removes_ack_and_refs_as_two_sections():
    kept, stats = trim_input(ACK_THEN_REFS)
    assert "thanks lab" not in kept
    assert "[1] Lee 2020" not in kept
    assert "do work" in kept
    assert len(stats["removed_sections"]) == 2


def test_roman_numeral_references_heading():
    kept, _ = trim_input(ROMAN)
    assert "Nyilas 1990" not in kept
    assert "done" in kept


def test_body_mentions_are_not_stripped():
    kept, _ = trim_input(APPENDIX_AFTER_REFS)
    assert "see References in prose" in kept


def test_skips_heading_in_first_half():
    kept, stats = trim_input(EARLY)
    assert "related work" in kept
    assert stats["skipped_too_early"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_input_trim.py -v`  
Expected: FAIL with `ModuleNotFoundError` or `cannot import trim_input`

- [ ] **Step 3: Write `tools/input_trim.py`**

先加 `tests/conftest.py`：

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
```

以及空的 `tools/__init__.py`。

实现要点（必须全部满足）：

- 只匹配 Markdown 标题行：`^(#{1,6})\s+(.+?)\s*$`
- 规范化：去冒号；剥开头编号：阿拉伯 `^\d+[\.\)]\s*`、罗马 `^[IVXLCDM]+\.\s*`（忽略大小写）、中文 `^[一二三四五六七八九十]+[、.]\s*`
- 命中集合（大小写不敏感、整段相等）：
  - refs: `reference`, `references`, `bibliography`, `参考文献`, `文献引用`, `references and notes`
  - ack: `acknowledgement`, `acknowledgements`, `acknowledgment`, `acknowledgments`, `致谢`, `鸣谢`
- 节范围：从该标题起到下一个 **level <= 当前** 的标题之前；无下一标题则到文末
- 起点字符偏移 `< len(text) * 0.5` → 不删，记 `skipped_too_early`
- 多节都删，互不依赖顺序
- `pipeline.trim_input` 改为 `from input_trim import trim_input` 再 re-export，删除旧 `TRIM_SECTION_RE` 切到文末逻辑

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_input_trim.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git rev-parse --is-inside-work-tree && git add tools/input_trim.py tests/test_input_trim.py tools/pipeline.py && git commit -m "$(cat <<'EOF'
feat: trim only References/Acknowledgements sections

EOF
)"
```

若不是 git 仓库则跳过。

---

### Task 2: 配置模型（模板 / 字段库 / 覆盖层 / 步骤生成）

**Files:**
- Create: `tools/config_model.py`
- Create: `tests/test_config_model.py`
- Create: `configs/templates/steel.json`
- Create: `configs/templates/blank.json`
- Create: `configs/field_library/steel.json`
- Create: `configs/projects/demo_steel.json`
- Modify: `configs/project_config.json`（demo_steel 增加 `template_id`、`overlay` 指向 `configs/projects/demo_steel.json`）

**Interfaces:**
- Consumes: JSON 文件
- Produces:
  - `load_template(root: Path, template_id: str) -> dict`
  - `load_field_library(root: Path, template_id: str) -> dict`（blank 返回 `{"fields": []}`）
  - `load_overlay(root: Path, project_id: str) -> dict`
  - `effective_fields(library: dict, overlay: dict) -> list[dict]` 每项含 `id,label,category,group,origin,value_type,rule,positive_examples,negative_examples,note`
  - `generate_steps(template: dict, fields: list[dict], overlay: dict) -> list[dict]`
  - `identity_field_ids(template: dict) -> set[str]`
  - `save_overlay(root: Path, project_id: str, overlay: dict) -> None`（不写库）
  - `writeback_library_field(root: Path, template_id: str, field: dict) -> None`
  - `promote_private_field(root: Path, project_id: str, field_id: str) -> dict` 更新库和 overlay
  - `create_project(root: Path, project_id: str, name: str, template_id: str, selected_field_ids: list[str]) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_model.py
from pathlib import Path
import json
import shutil
import tempfile
from tools import config_model as cm

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_demo_effective_fields_and_steps():
    overlay = cm.load_overlay(ROOT, "demo_steel")
    lib = cm.load_field_library(ROOT, "steel")
    fields = cm.effective_fields(lib, overlay)
    ids = [f["id"] for f in fields]
    assert "title" in ids
    assert "yield_strength" in ids
    assert "permeability" in ids
    tmpl = cm.load_template(ROOT, "steel")
    steps = cm.generate_steps(tmpl, fields, overlay)
    types = [s["type"] for s in steps]
    assert types[0] == "entity"
    assert "property" in types
    assert types[-1] == "figure"
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert "mechanical_properties" in groups
    assert "magnetic_properties" in groups


def test_unselected_group_omits_step():
    overlay = cm.load_overlay(ROOT, "demo_steel")
    overlay = dict(overlay)
    overlay["selected_field_ids"] = [i for i in overlay["selected_field_ids"] if i != "permeability"]
    lib = cm.load_field_library(ROOT, "steel")
    fields = cm.effective_fields(lib, overlay)
    steps = cm.generate_steps(cm.load_template(ROOT, "steel"), fields, overlay)
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert "magnetic_properties" not in groups
    assert "mechanical_properties" in groups


def test_overlay_does_not_write_library(tmp_path: Path):
    # copy steel library into tmp workspace layout
    ws = tmp_path
    (ws / "configs/field_library").mkdir(parents=True)
    (ws / "configs/projects").mkdir(parents=True)
    (ws / "configs/templates").mkdir(parents=True)
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    overlay = json.loads((ROOT / "configs/projects/demo_steel.json").read_text())
    overlay["field_overrides"] = {"title": {"rule": "PROJECT ONLY RULE"}}
    (ws / "configs/projects/demo_steel.json").write_text(json.dumps(overlay), encoding="utf-8")
    lib_before = (ws / "configs/field_library/steel.json").read_text()
    cm.save_overlay(ws, "demo_steel", overlay)
    assert (ws / "configs/field_library/steel.json").read_text() == lib_before
    fields = cm.effective_fields(cm.load_field_library(ws, "steel"), cm.load_overlay(ws, "demo_steel"))
    title = next(f for f in fields if f["id"] == "title")
    assert title["rule"] == "PROJECT ONLY RULE"


def test_writeback_updates_library(tmp_path: Path):
    ws = tmp_path
    (ws / "configs/field_library").mkdir(parents=True)
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    cm.writeback_library_field(ws, "steel", {"id": "title", "rule": "NEW LIB RULE", "label": "文献名称",
                                            "category": "metadata", "group": None, "value_type": "string",
                                            "positive_examples": "", "negative_examples": "", "note": ""})
    lib = cm.load_field_library(ws, "steel")
    title = next(f for f in lib["fields"] if f["id"] == "title")
    assert title["rule"] == "NEW LIB RULE"


def test_blank_library_is_empty():
    lib = cm.load_field_library(ROOT, "blank")
    assert lib["fields"] == []


def test_create_project_selects_subset(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    (ws / "configs/project_config.json").write_text(json.dumps({
        "default_project": "demo_steel", "projects": {}
    }), encoding="utf-8")
    cm.create_project(ws, "mini", "力学子集", "steel", ["title", "sample_id", "yield_strength"])
    overlay = cm.load_overlay(ws, "mini")
    assert overlay["selected_field_ids"] == ["title", "sample_id", "yield_strength"]
    steps = cm.generate_steps(cm.load_template(ws, "steel"),
                              cm.effective_fields(cm.load_field_library(ws, "steel"), overlay), overlay)
    groups = [s.get("group") for s in steps if s["type"] == "property"]
    assert groups == ["mechanical_properties"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config_model.py -v`  
Expected: FAIL import error

- [ ] **Step 3: Write configs + `config_model.py`**

`configs/templates/steel.json`：

```json
{
  "id": "steel",
  "name": "钢铁样品-状态",
  "domain_hint": "金属材料文献",
  "layers": [
    {"id": "metadata", "name": "文章信息", "cardinality": "one", "json_key": "paper_metadata"},
    {"id": "sample", "name": "样品信息", "cardinality": "many", "json_key": "samples", "id_field": "sample_id"},
    {"id": "condition", "name": "状态信息", "cardinality": "many", "json_key": "conditions", "id_field": "condition_id", "parent_layer": "sample", "parent_id_field": "sample_id"},
    {"id": "property", "name": "性能", "attach_to": "condition"},
    {"id": "figure", "name": "图片信息", "cardinality": "many", "json_key": "figures", "ref_fields": ["sample_id", "condition_id"]}
  ],
  "property_groups": [
    {"id": "mechanical_properties", "name": "力学性能"},
    {"id": "magnetic_properties", "name": "磁性能"}
  ],
  "identity_fields": ["sample_id", "condition_id"]
}
```

`configs/templates/blank.json`：与 steel 相同结构，`id`/`name` 改为 `blank` / `空模板`，`domain_hint` 为空字符串，`property_groups` 为 `[]`。

`configs/field_library/steel.json`：`{"fields":[...]}`。把现有 `configs/fields/demo_steel.json` 的每个字段拆成库条目：

- `id` = 字段名（如 `title`）
- `category` = 原层级（metadata/sample/condition/property/figure）
- `group` = 性能字段填 `mechanical_properties` 或 `magnetic_properties`（yield/tensile/elongation → mechanical；permeability → magnetic；其它 `null`）
- `label` 用中文显示名（文献名称、DOI 号可先不加 doi，demo 没有 doi 就不要编）
- `value_type`：`sample_id`/`condition_id`/`figure_id`/`placeholder_index` 为 `string` 且属于标识或外键；`composition` 为 `composition`；带单位的性能和 `test_temperature`/`scale_bar_info` 为 `number_with_unit`；`is_microstructure_image`/`is_post_test_image` 为 `boolean`；有枚举语义的 `product_form`/`condition_type`/`figure_type` 为 `enum`；其余 `string`
- 规则四元组从 `rules["metadata.title"]` 等原样搬

`configs/projects/demo_steel.json` 字段约定：

- 库字段 `id` 用短名（`title`、`yield_strength`）。
- `sample_id` 只作为样品主键进库一次；condition/figure 上的外键由模板 `parent_id_field` / `ref_fields` 声明，不另建库字段。
- `selected_field_ids` 为短名列表，对应现有 demo 的 `fields` 展开（不要重复勾选 condition 的 `sample_id`）：
  `title`, `material_system`, `sample_id`, `sample_name`, `product_form`, `alloy_family`, `composition`, `base_processing_description`, `condition_id`, `condition_name`, `condition_type`, `heat_treatment_condition`, `test_temperature`, `condition_processing_description`, `yield_strength`, `tensile_strength`, `elongation`, `permeability`, `figure_id`, `placeholder_index`, `figure_type`, `is_microstructure_image`, `is_post_test_image`, `scale_bar_info`
- `property_source` 与 `figure_filter` 从现有 demo 配置原样拷入 overlay。
- `step_overrides` 为 `null`。自动生成应为 entity → mechanical → magnetic → figures；property 步的 `id` 为 `mechanical`、`magnetic`。
- overlay 另含 `template_id`: `"steel"`。

`generate_steps` 规则：

1. 始终先 `{"id":"entity","type":"entity","name":"骨架"}`
2. 每个出现在有效字段里的 `group` 按模板 `property_groups` 顺序生成 property 步，`id` 取 group 去掉 `_properties` 后缀（`mechanical_properties` → `mechanical`），`fields` 为该组字段 id 列表
3. 若有效字段含任何 `category==figure`，最后加 `{"id":"figures","type":"figure","name":"图片过滤"}`
4. 若 overlay `step_overrides` 非空则用它，但若某 property/figure 排在 entity 之前则 `raise ValueError("骨架步必须先于性能和图片")`
5. 不在这里插入 `parse` 步；解析由 pipeline 在缺 `paper.md` 时单独做

`create_project`：写 `configs/projects/<id>.json`，并更新 `configs/project_config.json` 的 `projects` 项：`runnable: true`，`backend: mock`（测试里即可），`field_config` 可保留旧键但 overlay 路径为 `configs/projects/<id>.json`，`parsed_results`: `parsed_results/<id>`，`test_runs`: `test_runs/<id>`。

`project_config.json` 的 `demo_steel` 增加 `"template_id": "steel"`，`"overlay": "configs/projects/demo_steel.json"`。旧 `field_config` 暂时保留但 `load_field_config` 在下一任务改为走 overlay。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_config_model.py tests/test_input_trim.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**（非 git 则跳过）

```bash
git add configs tests/test_config_model.py tools/config_model.py
git commit -m "$(cat <<'EOF'
feat: add template, field library, and project overlay

EOF
)"
```

---

### Task 3: 出处形状、摘录匹配、导出 Schema

**Files:**
- Create: `tools/provenance.py`
- Create: `tests/test_provenance.py`
- Create: `tests/test_export.py`
- Modify: `tools/config_model.py`（增加 `build_output_schema`、`export_project`）

**Interfaces:**
- Consumes: Task 2 的 effective fields + template
- Produces:
  - `IDENTITY_PASS_THROUGH` 判定：`is_identity_field(template, field) -> bool`（id 在 `identity_fields` 或等于某层 `parent_id_field` / `ref_fields`）
  - `value_shape(field: dict) -> dict`：非标识字段返回 `{"value":"","unit":"","excerpt":"","location":""}`；`value_type==composition` 则 `value` 为 `{}`；`value_type==boolean` 则 `value` 为 `None`；性能字段另加 `"source":""`
  - `find_excerpt_span(text: str, excerpt: str) -> tuple[int,int] | None`：空白规范化后子串匹配，返回原文起止；找不到返回 None
  - `build_output_schema(template, fields) -> dict`
  - `export_project(root, project_id) -> dict` 符合规格 4.6

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provenance.py
from tools.provenance import find_excerpt_span, value_shape, is_identity_field
from tools.config_model import load_template
from pathlib import Path

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_find_excerpt_ignores_whitespace():
    text = "The yield strength of A-700 is 685 MPa"
    span = find_excerpt_span(text, "yield strength of A-700 is 685 MPa")
    assert span is not None
    start, end = span
    assert "685 MPa" in text[start:end]


def test_find_excerpt_missing():
    assert find_excerpt_span("hello", "not here") is None


def test_identity_not_wrapped():
    tmpl = load_template(ROOT, "steel")
    assert is_identity_field(tmpl, {"id": "sample_id", "category": "sample"})
    assert is_identity_field(tmpl, {"id": "sample_id", "category": "condition"})
    assert not is_identity_field(tmpl, {"id": "title", "category": "metadata"})


def test_property_shape_has_source():
    shape = value_shape({"id": "yield_strength", "category": "property", "value_type": "number_with_unit"})
    assert set(shape) >= {"value", "unit", "excerpt", "location", "source"}
```

```python
# tests/test_export.py
from tools.config_model import export_project
from pathlib import Path

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_export_demo_contains_fields_steps_schema():
    data = export_project(ROOT, "demo_steel")
    assert data["project_id"] == "demo_steel"
    assert data["template_id"] == "steel"
    ids = [f["id"] for f in data["fields"]]
    assert "yield_strength" in ids
    assert any(s["type"] == "entity" for s in data["steps"])
    schema = data["schema"]
    assert "paper_metadata" in schema
    assert "samples" in schema
    assert "conditions" in schema
    assert "excerpt" in schema["paper_metadata"]["title"]
    assert schema["samples"][0]["sample_id"] == ""
    assert "mechanical_properties" in schema["conditions"][0]
    assert "excerpt" in schema["conditions"][0]["mechanical_properties"]["yield_strength"]
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `python3 -m pytest tests/test_provenance.py tests/test_export.py -v`

- [ ] **Step 3: Implement**

`find_excerpt_span`：把 text 与 excerpt 都 `re.sub(r"\s+", " ", s).strip()`，在规范化串上找子串，再映射回原文索引（用扫描原文字符、跳过多余空白的双指针）。

`build_output_schema`：

- `paper_metadata`: 每个 metadata 字段 → value_shape
- `samples`: 一个示例对象，id 字段 `""`，其它 value_shape
- `conditions`: 含 `condition_id`/`sample_id` 字符串，再按 group 把性能字段放进子对象
- `figures`: 一个示例对象

`export_project`：`exported_at` 用 `datetime.now().isoformat(timespec="seconds")`；`fields` 按 category 顺序 metadata/sample/condition/property/figure，property 内再按 group；`origin` 为 library 或 private。

- [ ] **Step 4: Run tests, expect PASS**

- [ ] **Step 5: Commit**（非 git 跳过）`feat: add provenance helpers and project export`

---

### Task 4: Pipeline 改走配置模型，校验保留出处

**Files:**
- Modify: `tools/pipeline.py`
- Modify: `tools/llm_backends.py`（本任务只要求校验不丢 excerpt；mock 补 excerpt 放 Task 5 也可，本任务最小：validate 保留已有 excerpt）
- Create: `tests/test_validate_provenance.py`

**Interfaces:**
- Consumes: `config_model.effective_fields` / `generate_steps`；`input_trim.trim_input`
- Produces: `load_field_config` 改为合成旧结构（fields 按 category 列表 + rules + steps + property_source），供现有 prompt 函数继续工作；`validate_properties` 清洗后仍保留 `excerpt`/`location`/`source`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validate_provenance.py
from tools.pipeline import validate_properties

CFG = {
    "property_source": {"allow": ["measured_table"], "deny": ["abstract_target"], "deny_phrase_patterns": ["above"]},
    "fields": {"property": ["yield_strength"]},
}


def test_keeps_excerpt_on_clean_value():
    props = [{"condition_id": "C1", "yield_strength": {
        "value": "685", "unit": "MPa", "source": "measured_table",
        "excerpt": "A-700 is 685 MPa", "location": "Table 2"}}]
    cleaned, warnings = validate_properties(props, CFG)
    assert cleaned[0]["yield_strength"]["excerpt"] == "A-700 is 685 MPa"
    assert cleaned[0]["yield_strength"]["location"] == "Table 2"
    assert warnings == []


def test_rejected_value_listed_with_excerpt():
    props = [{"condition_id": "C4", "yield_strength": {
        "value": "600", "unit": "MPa", "source": "abstract_target",
        "excerpt": "above 600 MPa", "location": "Abstract"}}]
    cleaned, warnings = validate_properties(props, CFG)
    assert "yield_strength" not in cleaned[0]
    assert warnings[0]["excerpt"] == "above 600 MPa"
```

- [ ] **Step 2: Run, expect FAIL**（当前 cleaned 只留 value/unit）

- [ ] **Step 3: Change `validate_properties`**

清洗成功时写入：

```python
new_row[f] = {
    "value": val.get("value"),
    "unit": val.get("unit", ""),
    "source": val.get("source", ""),
    "excerpt": val.get("excerpt", ""),
    "location": val.get("location", ""),
}
```

剔除时 warning 带上 `excerpt`/`location`。`single_pass` 分支同样保留这些键。

同时改 `load_field_config`：若 project 有 `overlay`，则用 `config_model` 合成：

```python
fields_by_cat = {"metadata": [], "sample": [], "condition": [], "property": [], "figure": []}
rules = {}
for f in effective:
    fields_by_cat[f["category"]].append(f["id"])
    rules[f"{f['category']}.{f['id']}"] = {
        "rule": f["rule"], "positive_examples": f["positive_examples"],
        "negative_examples": f["negative_examples"], "note": f["note"],
    }
return {
    "fields": fields_by_cat,
    "rules": rules,
    "steps": generate_steps(...),
    "property_source": overlay.get("property_source", {}),
    "figure_filter": overlay.get("figure_filter", {}),
    "template_id": overlay["template_id"],
}
```

无 overlay 的旧项目（四个快照）仍读 `field_config` 文件。

`build_entity_prompt` 把「钢铁/金属材料文献」改成从 template `domain_hint` 拼进「你是{domain_hint}结构化抽取专家」，缺省「材料文献」。

- [ ] **Step 4: Run `python3 -m pytest tests/test_validate_provenance.py tests/test_config_model.py -v` — PASS**

再跑一次离线抽取确认不崩：

```bash
python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode two_stage
```

Expected: 打印 run_info，warnings 含 C4 摘要目标值被剔除。

- [ ] **Step 5: Commit** `fix: keep excerpt/location through property validation`

---

### Task 5: 分阶段 `run_step` 与骨架失效

**Files:**
- Modify: `tools/pipeline.py`
- Modify: `tools/llm_backends.py`（给 mock 性能补上 excerpt/location，摘录用 demo `paper.md` 里真实句子）
- Create: `tests/test_run_step.py`

**Interfaces:**
- Consumes: 现有 `run_extraction` 内部循环
- Produces:
  - `run_step(root, project_id, paper_id, step_id, run_id: str | None = None, partition="test", model_id=None) -> dict`
  - 返回含 `run_id`、`step`、`result`（当前合并结果）、`invalidated`（list）
  - 若 `run_id` 为空则新建 run 目录；否则接着写同一 `test_runs/.../run_id`
  - 骨架步未完成时跑 property/figure → `raise RuntimeError("必须先完成骨架")`
  - 重跑 entity：删除该 run 下 `properties/*`、合并结果里的性能组和过滤后 figures，把 entity 结果写回，然后**自动依次跑所有下游步骤**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_step.py
from pathlib import Path
from tools.pipeline import run_step

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_property_before_entity_raises():
    try:
        run_step(ROOT, "demo_steel", "demo_steel_2024", "mechanical")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "骨架" in str(e)


def test_staged_entity_then_mechanical():
    out_e = run_step(ROOT, "demo_steel", "demo_steel_2024", "entity", partition="test")
    assert out_e["result"]["samples"]
    assert "mechanical_properties" not in out_e["result"]["conditions"][0]
    out_m = run_step(ROOT, "demo_steel", "demo_steel_2024", "mechanical",
                     run_id=out_e["run_id"], partition="test")
    assert "mechanical_properties" in out_m["result"]["conditions"][0]
    ys = out_m["result"]["conditions"][0]["mechanical_properties"]["yield_strength"]
    assert ys.get("excerpt")
    assert ys.get("location") == "Table 2"


def test_rerun_entity_invalidates_and_reruns_downstream():
    out_e = run_step(ROOT, "demo_steel", "demo_steel_2024", "entity", partition="test")
    rid = out_e["run_id"]
    run_step(ROOT, "demo_steel", "demo_steel_2024", "mechanical", run_id=rid, partition="test")
    rerun = run_step(ROOT, "demo_steel", "demo_steel_2024", "entity", run_id=rid, partition="test")
    assert "mechanical" in rerun["invalidated"]
    assert "mechanical_properties" in rerun["result"]["conditions"][0]
```

- [ ] **Step 2: Run, expect FAIL**（`run_step` 不存在）

- [ ] **Step 3: Implement `run_step`**

重构 `run_extraction`：抽出 `_prepare_run(...)`（建目录、解析文本、trim）和 `_execute_step(run_state, step)`。`run_extraction` 循环全部非 parse 步骤。`run_step` 只跑一个。

`RUN_INFO.json` 增加：`template_id`、`completed_steps`、`invalidated_steps`、`parse_skipped`。

Mock 性能值补 excerpt/location，例如 C1 yield：

```python
"yield_strength": {
  "value": "685", "unit": "MPa", "source": "measured_table",
  "excerpt": "A-700 | 700 | 685 | 1020 | 42",
  "location": "Table 2"
}
```

C4 剔除项：

```python
"excerpt": "yield strength above 600 MPa", "location": "Abstract"
```

entity 的 `title` 等非标识字段也包成 `{value, unit, excerpt, location}`。注意现有 merge 和前端假设 title 是字符串——**合并结果按规格 5.5**：非标识一律对象。前端 Task 10 再适配。mock entity 的 title：

```python
"title": {"value": "Effect of Annealing Temperature on a High-Nitrogen Austenitic Stainless Steel", "unit": "", "excerpt": "Effect of Annealing Temperature on Microstructure and Mechanical Properties of a High-Nitrogen Austenitic Stainless Steel", "location": "Title"}
```

`composition`：`{"value": {"C":"0.05",...}, "excerpt":"Steel A (Cr-Mn-N) | 0.05 | 18.2", "location":"Table 1"}`

- [ ] **Step 4: Run `python3 -m pytest tests/test_run_step.py tests/test_validate_provenance.py -v` — PASS**

- [ ] **Step 5: Commit** `feat: add staged run_step with skeleton invalidation`

---

### Task 6: 单字段 / 批量重抽

**Files:**
- Modify: `tools/pipeline.py`
- Create: `tests/test_reextract.py`

**Interfaces:**
- Produces: `reextract_field(root, project_id, field_id, paper_id: str | None = None, scope: str | None = None, partition="test", model_id=None) -> dict`
  - `scope="project_extracted"` 时忽略 paper_id，对 `list_runs` 里每篇最新成功 run 各重抽一次
  - 标识字段 → `raise ValueError("标识字段不可单字段重抽")`
  - 失败：该字段保持旧值，`warnings` 追加，不删除 `paper.json`
  - 成功：只替换该字段，写新的 merged `paper.json`（可在同一 run 覆盖 merged，并在 `review_notes/reextract_<field>.json` 留记录）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reextract.py
from pathlib import Path
from tools.pipeline import run_extraction, reextract_field

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_reject_identity_field():
    run_extraction(ROOT, "demo_steel", "demo_steel_2024", mode="two_stage")
    try:
        reextract_field(ROOT, "demo_steel", "sample_id", paper_id="demo_steel_2024")
        assert False
    except ValueError as e:
        assert "标识" in str(e)


def test_reextract_one_property_keeps_others():
    out = run_extraction(ROOT, "demo_steel", "demo_steel_2024", mode="two_stage")
    before = out["result"]["conditions"][0]["mechanical_properties"]["tensile_strength"]["value"]
    rex = reextract_field(ROOT, "demo_steel", "yield_strength", paper_id="demo_steel_2024")
    after_ts = rex["result"]["conditions"][0]["mechanical_properties"]["tensile_strength"]["value"]
    assert after_ts == before
    assert "yield_strength" in rex["result"]["conditions"][0]["mechanical_properties"]
```

Mock 对 `hint={"stage":"reextract","field_id":"yield_strength"}` 返回只含该字段的 properties 列表。在 `MockBackend.call_json` 增加分支。

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement**

- 性能字段：prompt 只要求该字段 + excerpt/location/source，带上已有 condition_id 列表，禁止新增样品/状态
- 骨架非标识字段：prompt 只改该字段，输入现有 entity JSON 作为上下文
- 合并：深拷贝最新 `paper.json`，按 category 写入
- `scope=project_extracted`：`papers = unique paper_id from list_runs`；循环 try/except，汇总 `report: [{paper_id, ok, error}]`

- [ ] **Step 4: pytest `tests/test_reextract.py` PASS**

- [ ] **Step 5: Commit** `feat: reextract a single field without rerunning the skeleton`

---

### Task 7: PDF 解析包装（假 client 可测）

**Files:**
- Create: `tools/pdf_parser.py`
- Create: `tests/test_pdf_parser.py`

**Interfaces:**
- Consumes: 规格 5.6；逻辑对齐 `/internfs/wangchenyan/shougang/scripts/parsing/parser.py` 的 `save_base64_images` / `parse_one_pdf`，**禁止 import 那份脚本，禁止默认路径指向 Extract_data**
- Produces:
  - `parse_pdf_to_paper(pdf_path: Path, output_dir: Path, *, client=None, overwrite: bool=False, host: str | None=None, api_key: str | None=None) -> dict`
  - `output_dir` 为 `<parsed_results>/<paper_id>/` 的父目录，paper_id = `pdf_path.stem`
  - 写出 `paper.md`、`images_from_md/`、`uniparser_submit_result.json`；调用方负责把原 PDF 复制为 `source.pdf`
  - 已有 `paper.md` 且 `overwrite=False` → `{status:"skipped"}`
  - `content` 空 → raise，不写空 md
  - 无 key 且未注入 client → `RuntimeError` 文案含 `UNIPARSER_API_KEY`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pdf_parser.py
from pathlib import Path
import json
from tools.pdf_parser import parse_pdf_to_paper, save_base64_images

class FakeClient:
    def trigger_file(self, **kwargs):
        return {"token": "t1"}
    def get_formatted(self, token, **kwargs):
        md = "hello\n\n![figure](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==)\n"
        return {"content": md}


def test_writes_md_and_image(tmp_path: Path):
    pdf = tmp_path / "p1.pdf"
    pdf.write_bytes(b"%PDF-fake")
    out = tmp_path / "parsed"
    result = parse_pdf_to_paper(pdf, out, client=FakeClient())
    paper_dir = out / "p1"
    assert (paper_dir / "paper.md").exists()
    assert "images_from_md/" in (paper_dir / "paper.md").read_text()
    assert list((paper_dir / "images_from_md").glob("*"))
    assert result["status"] == "success"


def test_skip_existing(tmp_path: Path):
    pdf = tmp_path / "p1.pdf"
    pdf.write_bytes(b"%PDF-fake")
    paper_dir = tmp_path / "parsed" / "p1"
    paper_dir.mkdir(parents=True)
    (paper_dir / "paper.md").write_text("old", encoding="utf-8")
    result = parse_pdf_to_paper(pdf, tmp_path / "parsed", client=FakeClient(), overwrite=False)
    assert result["status"] == "skipped"
    assert (paper_dir / "paper.md").read_text() == "old"


def test_empty_content_does_not_write(tmp_path: Path):
    class Empty:
        def trigger_file(self, **kwargs):
            return {"token": "t"}
        def get_formatted(self, token, **kwargs):
            return {"content": ""}
    pdf = tmp_path / "p1.pdf"
    pdf.write_bytes(b"%PDF")
    try:
        parse_pdf_to_paper(pdf, tmp_path / "parsed", client=Empty())
        assert False
    except RuntimeError:
        pass
    assert not (tmp_path / "parsed" / "p1" / "paper.md").exists()
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `tools/pdf_parser.py`**

从 `scripts/parsing/parser.py` 拷 `IMAGE_PATTERN`、`save_base64_images`、`image_extension`。真实 client 仅当 `client is None` 时 `UniParserClient(host=..., api_key=get_api_key())`。`get_api_key` 读 `UNIPARSER_API_KEY` 或 `UP_API_KEY`。不要写死 CuTi 路径。

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit** `feat: wrap UniParser PDF parsing into the workbench`

---

### Task 8: HTTP API 与 CLI

**Files:**
- Modify: `tools/workbench_server.py`
- Create: `tests/test_api_handlers.py`

**Interfaces:**
- Produces: 规格 8.2 全部端点。路由可用 `urlparse` 手工拆，不必上 Flask。
  - `POST /api/projects` body: `{id, name, template_id, selected_field_ids}`
  - `POST /api/parse` body: `{project, paper_id, overwrite}`；测试可不测 multipart。实现上传：若 `Content-Type` 为 `application/json` 则 `{project, pdf_path}` 指向已有文件；若 `multipart` 则保存到 parsed 目录 `source.pdf` 再 parse。第一版 JSON+本地路径足够，界面用 `<input type=file>` 走 multipart。
  - `POST /api/run` 保持；无 md 且请求带 `pdf_path` 或已上传 source.pdf 则先 parse
  - `POST /api/run_step` `{project, paper_id, step_id, run_id, partition, model_id}`
  - `POST /api/reextract` `{project, field_id, paper_id, scope, partition}`
  - `GET /api/field_library?template=steel`
  - `GET/PUT /api/projects/<id>/config` — 若 stdlib 解析路径不便，用 query：`GET /api/project_config?project=` 与 `PUT /api/project_config?project=`
  - 规格写了 `/api/projects/:id/config`。**实现用路径** `/api/projects/<id>/config` 和 `/api/projects/<id>/export`：在 `do_GET`/`do_PUT`/`do_POST` 里 `parts = route.strip("/").split("/")`
  - `POST /api/field_library/writeback` `{template_id, field}`
  - `POST /api/field_library/promote` `{project, field_id}`
  - CLI: `--parse-only --pdf PATH`、`--step entity`、`--reextract-field yield_strength`、`--export-fields-schema`

为避免改 Handler 难以测，把路由函数做成模块级 `handle_get(route, qs) -> tuple[int, dict]`、`handle_post(route, body, files=None)`，Handler 只做 IO。测试直接调 `handle_*`。

- [ ] **Step 1: Write failing tests for handle_get export and handle_post run_step**

```python
# tests/test_api_handlers.py
from tools.workbench_server import handle_get, handle_post


def test_export_demo():
    status, data = handle_get("/api/projects/demo_steel/export", {})
    assert status == 200
    assert data["template_id"] == "steel"
    assert data["fields"]


def test_field_library():
    status, data = handle_get("/api/field_library", {"template": ["steel"]})
    assert status == 200
    assert data["fields"]
```

- [ ] **Step 2: FAIL then implement routing + CLI flags**

`argparse` 增加：

```python
parser.add_argument("--parse-only", action="store_true")
parser.add_argument("--pdf", default=None)
parser.add_argument("--step", default=None)
parser.add_argument("--reextract-field", default=None)
parser.add_argument("--export-fields-schema", action="store_true")
parser.add_argument("--overwrite-parse", action="store_true")
```

互斥优先级：`export` > `parse-only` > `reextract-field` > `step` > `run-once`。

- [ ] **Step 3: pytest `tests/test_api_handlers.py` PASS**

- [ ] **Step 4: `python3 tools/workbench_server.py --export-fields-schema --project demo_steel` 打印 JSON 且含 schema**

- [ ] **Step 5: Commit** `feat: expose parse, staged run, reextract, and export APIs`

---

### Task 9: 前端四个入口、字段库勾选、出处高亮、导出

**Files:**
- Modify: `app/index.html`
- Modify: `app/app.js`
- Modify: `app/styles.css`

**Interfaces:**
- Consumes: Task 8 API
- Produces: 可离线用 demo 操作的 UI（浏览器手工验；本任务用静态检查 + 现有 mock 跑通）

- [ ] **Step 1: 改 index.html 主操作区**

替换「试运行两阶段抽取」单一按钮为四个：

- `#btnRunAll` 整篇一次跑完
- `#btnRunStep` 跑当前选中步骤（步骤条 `#stepList` 可点，`data-step-id`）
- `#btnParseOnly` 只解析
- `#btnReextract` 只重抽：旁边 `<select id="reextractField">` 与 `<select id="reextractScope">`（当前文献 / 本项目已抽文献）

步骤条：property/figure 在 entity 未完成时加 `disabled`。重跑 entity 前 `confirm("下游性质和图片将作废并重跑")`。

字段配置区：

- 分类展示库字段 checkbox（从 `/api/field_library`）
- 已有「新增字段」改为写入 PUT overlay 的 `private_fields`
- 编辑规则对话框增加单选：`仅本项目` / `写回公共库`
- 「导出」按钮 `#btnExport`：`GET /api/projects/<id>/export` 后下载 `<id>_fields_schema.json`
- 新项目对话框：模板 select（steel/blank）+ 按类勾选 + 提交 `POST /api/projects`

结果列表：每个非标识字段显示 value、location、摘录状态。点击调用 `highlightExcerpt(paperText, excerpt)`：规范化空白后 `indexOf`；命中则把 `#paperTextViewer` 里对应片段包 `<mark>`（若正在显示 PDF iframe，先隐藏 iframe 显示文本视图）。未命中在字段旁显示 excerpt 文本，不加 mark。

- [ ] **Step 2: app.js 把 title 等对象取值改为 `field.value ?? field` 兼容旧字符串**

- [ ] **Step 3: 离线验收命令**

```bash
python3 tools/workbench_server.py --run-once --project demo_steel --paper-id demo_steel_2024 --mode two_stage
python3 tools/workbench_server.py --export-fields-schema --project demo_steel | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['schema']['paper_metadata']['title']['excerpt']=='' or True; assert d['fields']"
```

手工：打开工作台，点字段看 Table 2 高亮；改 title 规则仅本项目，确认 `configs/field_library/steel.json` 未变。

- [ ] **Step 4: Commit** `feat: workbench UI for staged run, field library, provenance, export`

---

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
