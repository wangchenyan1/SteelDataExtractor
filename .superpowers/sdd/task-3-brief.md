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

