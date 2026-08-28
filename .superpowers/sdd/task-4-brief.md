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

