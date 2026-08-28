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

