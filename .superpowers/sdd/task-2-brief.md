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

