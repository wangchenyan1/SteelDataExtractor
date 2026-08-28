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

