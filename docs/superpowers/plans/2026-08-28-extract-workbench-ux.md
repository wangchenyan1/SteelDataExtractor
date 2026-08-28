# 抽取工作台任务流与复核体验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把工作台改成五视图任务流，支持项目级自定义性能阶段，规则未通过项以 `status` 异色保留在结果中，复核支持 PDF/渲染 md 与层级+缩略图。

**Architecture:** 后端先改 `validate_properties` / `classify_figures` 为标记语义，并用覆盖层 `steps` 作为阶段唯一真相；图片策略改为流水线内部后处理（不进用户阶段列表）。前端把 `app/` 拆成五视图，配置页编辑字段/阶段/策略，复核页做层级与原文对照。不重写 LLM 调度核心。

**Tech Stack:** Python 3 标准库 + 现有 `pipeline.py` / `config_model.py` / `workbench_server.py`；`python3 -m pytest`；前端 `app/index.html` + `app.js` + `styles.css`（可引入轻量 Markdown 渲染，如 CDN `marked`）；离线 `demo_steel` mock。

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-28-extract-workbench-ux-design.md`；前置能力见 `2026-08-27-configurable-extract-tool-design.md`。本计划不得做标注（改值/恢复误杀）、不得任意骨架、不得写回 `Extract_data`。
- 禁止写入 `/internfs/wangchenyan/shougang/Extract_data`。
- 不迁移四个只读快照项目。
- 工作区可能无可用 git（`safe.directory` / 无仓库）。每个 Commit 步：先 `git -c safe.directory=* rev-parse --is-inside-work-tree`；失败则**跳过 commit**，不要改 global git config，不要重复 `git init`。
- 测试：`cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest -q`
- `status` 取值仅：`accepted` | `rejected_by_rule`；缺省旧数据视为 `accepted`。
- 用户可见阶段不得包含 `type=figure` / 名称「图片过滤」；图片策略仍在跑完性能后内部执行。

---

## 文件结构

| 路径 | 职责 |
| --- | --- |
| `tools/pipeline.py` | `validate_properties` / `classify_figures` 标记；合并后内部跑图片策略；读 `steps` |
| `tools/config_model.py` | `steps` 为真相；`validate_overlay_stages`；默认生成不含 figure 步；保存校验 |
| `tools/workbench_server.py` | PDF/图片 GET；结果导出；`paper_meta`（是否有 pdf） |
| `configs/projects/demo_steel.json` | 写入显式 `steps`；保留策略 |
| `tests/test_validate_provenance.py` | 拒绝项保留在 cleaned + status |
| `tests/test_classify_figures_status.py` | 图片标记而非删除 |
| `tests/test_config_stages.py` | 阶段校验与 `steps` 优先 |
| `tests/test_export.py` / `tests/test_export_results.py` | 配置含阶段；结果导出筛选 |
| `app/index.html` | 五视图壳 |
| `app/app.js` | 视图路由、配置/运行/复核/导出逻辑 |
| `app/styles.css` | 异色块、层级、导航 |
| `app/vendor/marked.min.js`（或 CDN） | md 渲染（可选本地 vendoring） |

---

### Task 1: 性能校验改为标记 status（非删除）

**Files:**
- Modify: `tools/pipeline.py`（`validate_properties`）
- Modify: `tests/test_validate_provenance.py`

**Interfaces:**
- Consumes: 现有 `validate_properties(properties, field_config) -> tuple[list, list]`
- Produces: 清洗后仍含被拒字段；对象含 `status`、`reject_reason`；warnings 仍产出 `type=property_source_rejected`

- [ ] **Step 1: 改写失败测试**

```python
# tests/test_validate_provenance.py
from tools.pipeline import validate_properties

CFG = {
    "property_source": {
        "allow": ["measured_table"],
        "deny": ["abstract_target"],
        "deny_phrase_patterns": ["above"],
    },
    "fields": {"property": ["yield_strength"]},
}


def test_keeps_excerpt_on_clean_value():
    props = [{"condition_id": "C1", "yield_strength": {
        "value": "685", "unit": "MPa", "source": "measured_table",
        "excerpt": "A-700 is 685 MPa", "location": "Table 2"}}]
    cleaned, warnings = validate_properties(props, CFG)
    assert cleaned[0]["yield_strength"]["excerpt"] == "A-700 is 685 MPa"
    assert cleaned[0]["yield_strength"]["status"] == "accepted"
    assert warnings == []


def test_rejected_value_kept_with_status():
    props = [{"condition_id": "C4", "yield_strength": {
        "value": "600", "unit": "MPa", "source": "abstract_target",
        "excerpt": "above 600 MPa", "location": "Abstract"}}]
    cleaned, warnings = validate_properties(props, CFG)
    val = cleaned[0]["yield_strength"]
    assert val["value"] == "600"
    assert val["status"] == "rejected_by_rule"
    assert "reject_reason" in val and val["reject_reason"]
    assert val["excerpt"] == "above 600 MPa"
    assert warnings[0]["type"] == "property_source_rejected"
    assert warnings[0]["excerpt"] == "above 600 MPa"
```

- [ ] **Step 2: 跑测试确认旧行为失败**

Run: `python3 -m pytest tests/test_validate_provenance.py::test_rejected_value_kept_with_status -v`  
Expected: FAIL（当前实现把字段从 cleaned 删掉）

- [ ] **Step 3: 实现标记语义**

在 `tools/pipeline.py` 的 `validate_properties` 中，命中 deny 时**不要** `continue` 跳过写入；改为写入完整对象并设：

```python
new_row[f] = {
    "value": val.get("value"),
    "unit": val.get("unit", ""),
    "source": val.get("source", ""),
    "excerpt": val.get("excerpt", ""),
    "location": val.get("location", ""),
    "status": "rejected_by_rule",
    "reject_reason": f"来源不可靠({val.get('source')})",
}
# 同时仍 append warnings（type 保持 property_source_rejected）
```

通过项设 `"status": "accepted"`（可无 `reject_reason`）。

- [ ] **Step 4: 跑测试通过**

Run: `python3 -m pytest tests/test_validate_provenance.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（若 git 可用）**

```bash
git -c safe.directory=* add tools/pipeline.py tests/test_validate_provenance.py
git -c safe.directory=* commit -m "fix: keep rule-rejected properties with status instead of dropping"
```

---

### Task 2: 图片策略改为标记 status（非删除）

**Files:**
- Modify: `tools/pipeline.py`（`classify_figures`）
- Create: `tests/test_classify_figures_status.py`

**Interfaces:**
- Consumes: `classify_figures(figures, field_config, apply_filter) -> tuple[list, list]`
- Produces: `apply_filter=True` 时全部 figure 仍在列表中；未通过者 `status=rejected_by_rule` + `reject_reason`；通过者 `status=accepted`；`apply_filter=False` 时全部 `accepted` 且无 figure_dropped warnings

- [ ] **Step 1: 写失败测试**

```python
# tests/test_classify_figures_status.py
from tools.pipeline import classify_figures

CFG = {
    "figure_filter": {
        "keep_types": ["OM", "SEM"],
        "drop_types": ["XRD"],
        "drop_if_post_test": True,
        "require_microstructure": True,
    }
}


def test_xrd_kept_with_rejected_status():
    figs = [
        {"figure_id": "Figure 1", "figure_type": "OM",
         "is_microstructure_image": True, "is_post_test_image": False,
         "placeholder_index": 1},
        {"figure_id": "Figure 3", "figure_type": "XRD",
         "is_microstructure_image": False, "is_post_test_image": False,
         "placeholder_index": 3},
    ]
    kept, warnings = classify_figures(figs, CFG, apply_filter=True)
    assert len(kept) == 2
    by_id = {f["figure_id"]: f for f in kept}
    assert by_id["Figure 1"]["status"] == "accepted"
    assert by_id["Figure 3"]["status"] == "rejected_by_rule"
    assert "XRD" in by_id["Figure 3"]["reject_reason"]
    assert any(w["type"] == "figure_dropped" for w in warnings)


def test_single_pass_all_accepted():
    figs = [{"figure_id": "Figure 3", "figure_type": "XRD",
             "is_microstructure_image": False, "is_post_test_image": False}]
    kept, warnings = classify_figures(figs, CFG, apply_filter=False)
    assert kept[0]["status"] == "accepted"
    assert warnings == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_classify_figures_status.py -v`  
Expected: FAIL（当前 XRD 被从 kept 删除）

- [ ] **Step 3: 实现**

改 `classify_figures`：未通过时 `fig = {**fig, "status": "rejected_by_rule", "reject_reason": reason}` 后 `kept.append(fig)`，并仍写 warning；通过时设 `status=accepted`。`apply_filter=False` 时全部 append 且 `status=accepted`。

- [ ] **Step 4: 跑测试通过**

Run: `python3 -m pytest tests/test_classify_figures_status.py tests/test_validate_provenance.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（若可用）**

```bash
git -c safe.directory=* add tools/pipeline.py tests/test_classify_figures_status.py
git -c safe.directory=* commit -m "fix: mark filtered figures with status instead of dropping"
```

---

### Task 3: 覆盖层 `steps` 为阶段真相 + 保存校验

**Files:**
- Modify: `tools/config_model.py`（`generate_steps`、新增 `validate_overlay_stages`、`save_overlay` 调用校验）
- Create: `tests/test_config_stages.py`
- Modify: `configs/projects/demo_steel.json`（写入显式 `steps`，去掉对「图片过滤步」的依赖）

**Interfaces:**
- Consumes: `overlay["steps"]` | 旧 `step_overrides` | 字段 `group`
- Produces:
  - `generate_steps(...)`：若 `overlay.get("steps")` 非空则用之；否则回退 `step_overrides`；再否则按 group 自动生成；**自动生成不再追加 `type=figure`**
  - `validate_overlay_stages(overlay, fields) -> None`：骨架第一且唯一 entity；每个 `category==property` 的有效字段恰好属于一个 property 步的 `fields`；property 步 `fields` 非空；禁止用户 steps 含 `type=figure`（保存时剥掉或报错——本计划：**报 ValueError**）
  - `save_overlay`：先 `validate_overlay_stages` 再写盘

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config_stages.py
import pytest
from tools.config_model import generate_steps, validate_overlay_stages

TEMPLATE = {
    "property_groups": [
        {"id": "mechanical_properties", "name": "力学性能"},
        {"id": "magnetic_properties", "name": "磁性能"},
    ],
    "identity_fields": ["sample_id", "condition_id"],
}


def test_overlay_steps_win_over_groups():
    fields = [
        {"id": "yield_strength", "category": "property", "group": "mechanical_properties"},
        {"id": "permeability", "category": "property", "group": "magnetic_properties"},
        {"id": "electrical_conductivity", "category": "property", "group": "conductivity_properties"},
    ]
    overlay = {
        "steps": [
            {"id": "entity", "type": "entity", "name": "骨架"},
            {"id": "mechanical", "type": "property", "name": "力学性能",
             "group": "mechanical_properties", "fields": ["yield_strength"]},
            {"id": "conductivity", "type": "property", "name": "电导性能",
             "group": "conductivity_properties", "fields": ["electrical_conductivity"]},
        ]
    }
    steps = generate_steps(TEMPLATE, fields, overlay)
    assert [s["id"] for s in steps] == ["entity", "mechanical", "conductivity"]
    assert not any(s.get("type") == "figure" for s in steps)


def test_auto_generate_omits_figure_step():
    fields = [
        {"id": "yield_strength", "category": "property", "group": "mechanical_properties"},
        {"id": "figure_id", "category": "figure", "group": None},
    ]
    steps = generate_steps(TEMPLATE, fields, {})
    assert not any(s.get("type") == "figure" for s in steps)


def test_validate_rejects_unassigned_property_field():
    fields = [
        {"id": "yield_strength", "category": "property", "group": "mechanical_properties"},
        {"id": "permeability", "category": "property", "group": "magnetic_properties"},
    ]
    overlay = {
        "selected_field_ids": ["yield_strength", "permeability"],
        "steps": [
            {"id": "entity", "type": "entity", "name": "骨架"},
            {"id": "mechanical", "type": "property", "name": "力学性能",
             "fields": ["yield_strength"]},
        ],
    }
    with pytest.raises(ValueError, match="未挂阶段"):
        validate_overlay_stages(overlay, fields)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_config_stages.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 `generate_steps` / `validate_overlay_stages` / `save_overlay`**

要点：

```python
def generate_steps(template, fields, overlay):
    if overlay.get("steps"):
        return list(overlay["steps"])
    # 旧 step_overrides 兼容…
    # 自动生成：entity + 按 group 的 property；不要 append figure

def validate_overlay_stages(overlay, fields):
    steps = overlay.get("steps") or []
    # entity 必须 index 0；禁止 type==figure
    # property 字段集合 == 各 property 步 fields 并集，且无遗漏、无重复
```

`demo_steel.json` 增加与当前勾选一致的 `steps`（entity + mechanical + magnetic），**不含** figures 步；可删 `step_overrides: null` 或保留无害。

- [ ] **Step 4: 跑相关测试**

Run: `python3 -m pytest tests/test_config_stages.py tests/test_config_model.py tests/test_export.py -v`  
Expected: PASS（若 `test_config_model` 仍断言 figure 步，同步改断言：用户 steps 无 figure）

- [ ] **Step 5: Commit（若可用）**

```bash
git -c safe.directory=* add tools/config_model.py tests/test_config_stages.py configs/projects/demo_steel.json tests/test_config_model.py
git -c safe.directory=* commit -m "feat: project steps as stage plan with validation, no figure stage"
```

---

### Task 4: 流水线在无 figure 步时仍做图片策略后处理

**Files:**
- Modify: `tools/pipeline.py`（`run_extraction` / `run_step` 收尾、`_finalize` 一类逻辑）
- Modify: 现有依赖「必须有 figures 步」的测试（如有）

**Interfaces:**
- Consumes: Task 1–3 的 status 与无 figure 的 `steps`
- Produces: 整篇跑完或骨架+性能跑完后，若 entity 含 figures，则调用 `classify_figures` 写入 `state["figures"]` 与 warnings；`single_pass` 时 `apply_filter=False`

- [ ] **Step 1: 写/改集成测试**

新建 `tests/test_figure_postprocess.py`，调用与 `tests/test_run_step.py` 相同的 `run_extraction` 入口（`ROOT` + `demo_steel` + `demo_steel_2024` + `mode="two_stage"`）：

```python
# tests/test_figure_postprocess.py
from pathlib import Path
from tools.pipeline import run_extraction, load_field_config

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_demo_two_stage_marks_xrd_without_figure_step():
    out = run_extraction(ROOT, "demo_steel", "demo_steel_2024", mode="two_stage")
    steps = load_field_config(ROOT, "demo_steel").get("steps") or []
    assert not any(s.get("type") == "figure" for s in steps)
    figs = (out.get("result") or out.get("merged") or {}).get("figures")
    if figs is None:
        # 兼容实际返回键名：以 run 目录 merged_outputs 为准
        run_dir = Path(out["run_dir"]) if "run_dir" in out else None
        assert run_dir is not None
        import json
        figs = json.loads((run_dir / "merged_outputs" / "paper.json").read_text())["figures"]
    xrd = next(f for f in figs if f.get("figure_type") == "XRD" or f.get("figure_id") == "Figure 3")
    assert xrd["status"] == "rejected_by_rule"
```

实现时以 `run_extraction` 真实返回结构为准，删掉无效键名分支，只保留一条断言路径。

- [ ] **Step 2: 跑测试确认失败或缺口**

Run: `python3 -m pytest tests/test_run_step.py -v`（及新建测试）  
Expected: 缺后处理时 FAIL

- [ ] **Step 3: 实现后处理钩子**

在 `run_extraction` 所有 property 步之后（以及 `run_step` 在最后一档性能完成或显式 finalize 时）：

```python
def _apply_figure_policy(state, apply_rules: bool):
    raw_figs = (state.get("entity") or {}).get("figures") or []
    if not raw_figs and not state.get("figures"):
        raw_figs = state.get("figures") or []
    source = state.get("entity", {}).get("figures") or []
    figures, fig_warnings = classify_figures(
        source, state["field_config"], apply_filter=apply_rules)
    state["figures"] = figures
    # 替换旧 figure_dropped warnings 后 extend
```

若仍存在历史 `type=figure` 步（旧 overlay），保持 `run_step` 分支可运行，但新 demo 不再包含该步。

- [ ] **Step 4: 全量 pytest**

Run: `python3 -m pytest -q`  
Expected: PASS

- [ ] **Step 5: Commit（若可用）**

```bash
git -c safe.directory=* add tools/pipeline.py tests/
git -c safe.directory=* commit -m "feat: apply figure policy as post-process without user-facing stage"
```

---

### Task 5: HTTP — PDF / 图片 / paper_meta / 结果导出

**Files:**
- Modify: `tools/workbench_server.py`
- Create: `tests/test_paper_assets.py`
- Create: `tests/test_export_results.py`
- Modify: `tools/config_model.py` 或 `pipeline.py`（`export_results` 辅助函数）

**Interfaces:**
- `GET /api/paper_meta?project=&paper_id=` → `{paper_id, has_pdf, has_md, image_count}`
- `GET /api/paper_pdf?project=&paper_id=` → `application/pdf` 字节（无则 404）
- `GET /api/paper_image?project=&paper_id=&name=fig1_om.png` → 图片字节（仅允许 `images_from_md/` 下 basename，防路径穿越）
- `GET /api/projects/:id/export` 已有；确保响应含 `steps`（已有则回归）
- `GET /api/projects/:id/export_results?paper_id=&include_rejected=true|false` → 单篇或（无 paper_id 时）项目最新结果列表；`include_rejected=false` 时剥离 `status=rejected_by_rule` 的性能字段与图片

- [ ] **Step 1: 写失败测试**

```python
# tests/test_paper_assets.py
from tools import workbench_server as wb

def test_paper_meta_demo():
    code, body = wb.handle_get("/api/paper_meta", {
        "project": ["demo_steel"], "paper_id": ["demo_steel_2024"]})
    assert code == 200
    assert body["has_md"] is True
    assert "has_pdf" in body


def test_paper_image_demo():
    # handle_get 若只返回 JSON，可改为测内部 resolve 函数
    from tools.workbench_server import resolve_paper_image_path
    p = resolve_paper_image_path(wb.ROOT, "demo_steel", "demo_steel_2024", "fig1_om.png")
    assert p is not None and p.exists()


def test_paper_image_rejects_traversal():
    from tools.workbench_server import resolve_paper_image_path
    assert resolve_paper_image_path(
        wb.ROOT, "demo_steel", "demo_steel_2024", "../evil.png") is None
```

```python
# tests/test_export_results.py
from tools.pipeline import filter_result_by_status

def test_filter_drops_rejected():
    result = {
        "conditions": [{
            "condition_id": "C4",
            "mechanical_properties": {
                "yield_strength": {
                    "value": "600", "status": "rejected_by_rule",
                    "unit": "MPa", "source": "abstract_target",
                    "excerpt": "", "location": "",
                },
                "elongation": {
                    "value": "40", "status": "accepted",
                    "unit": "%", "source": "measured_table",
                    "excerpt": "", "location": "",
                },
            },
        }],
        "figures": [
            {"figure_id": "Figure 3", "status": "rejected_by_rule"},
            {"figure_id": "Figure 1", "status": "accepted"},
        ],
    }
    out = filter_result_by_status(result, include_rejected=False)
    assert "yield_strength" not in out["conditions"][0]["mechanical_properties"]
    assert "elongation" in out["conditions"][0]["mechanical_properties"]
    assert [f["figure_id"] for f in out["figures"]] == ["Figure 1"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_paper_assets.py tests/test_export_results.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现路由与 `filter_result_by_status`**

注意：`workbench_server` 静态文件服务需能返回非 JSON 的 PDF/图片（看现有 `do_GET`：若只 `json.dumps`，增加 content-type 分支）。`resolve_paper_image_path` 必须 `Path(name).name == name` 且 resolve 后仍在 `images_from_md` 目录下。

- [ ] **Step 4: 跑测试通过**

Run: `python3 -m pytest tests/test_paper_assets.py tests/test_export_results.py tests/test_export.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（若可用）**

```bash
git -c safe.directory=* add tools/workbench_server.py tools/pipeline.py tests/test_paper_assets.py tests/test_export_results.py
git -c safe.directory=* commit -m "feat: serve paper PDF/images and export results with status filter"
```

---

### Task 6: 前端五视图导航壳

**Files:**
- Modify: `app/index.html`
- Modify: `app/styles.css`
- Modify: `app/app.js`（视图状态 + 显示/隐藏）

**Interfaces:**
- Consumes: 无后端新依赖
- Produces: `state.view ∈ {project, config, papers, review, export}`；顶栏或侧栏切换；五块 `section[data-view]` 互斥显示

- [ ] **Step 1: 改 HTML 结构**

在 `index.html` 增加导航：

```html
<nav class="view-nav" id="viewNav">
  <button type="button" data-view="project">项目</button>
  <button type="button" data-view="config">配置</button>
  <button type="button" data-view="papers">文献与运行</button>
  <button type="button" data-view="review">复核</button>
  <button type="button" data-view="export">导出</button>
</nav>
```

用 `data-view` 包裹现有面板：项目列表→`project`；字段配置→`config`；文献输入+运行按钮→`papers`；review-workbench→`review`；导出按钮区→`export`。暂时把 Schema/Prompt/快照/芯片双份放进 `<div id="legacyDevPanels" hidden>`，本任务只做壳，不删逻辑以免断引用。

- [ ] **Step 2: JS 切换**

```javascript
function setView(name) {
  state.view = name;
  document.querySelectorAll("[data-view-panel]").forEach((el) => {
    el.hidden = el.getAttribute("data-view-panel") !== name;
  });
  document.querySelectorAll("#viewNav [data-view]").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === name);
  });
}
```

- [ ] **Step 3: 手动验收**

Run: `python3 tools/workbench_server.py --host 127.0.0.1 --port 8787`  
打开页面，点击五按钮，仅对应面板可见。

- [ ] **Step 4: Commit（若可用）**

```bash
git -c safe.directory=* add app/index.html app/app.js app/styles.css
git -c safe.directory=* commit -m "feat: add five-view navigation shell for workbench"
```

---

### Task 7: 配置视图 — 字段 + 阶段 + 策略

**Files:**
- Modify: `app/index.html`（配置区 DOM）
- Modify: `app/app.js`（去掉主路径芯片双份与 `selected_field_ids` 文案；阶段编辑器；策略表单）
- Modify: `app/styles.css`

**Interfaces:**
- Consumes: `GET/PUT /api/projects/:id/config`，`GET /api/field_library`；保存 body 含 `selected_field_ids`、`steps`、`property_source`、`figure_filter`
- Produces: 用户可增删性能阶段、把性能字段划入阶段；未挂阶段时 PUT 前前端拦截；后端 `save_overlay` 二次校验

- [ ] **Step 1: 配置区 UI**

- 字段：仅按类别 checkbox + 中文 label（已有 `renderFieldLibraryChecks`，删掉「写入项目覆盖层 selected_field_ids」文案）。
- 删除或隐藏 `#metadataFields` 等五列 chips 主路径（改规则改为字段旁「规则」小按钮）。
- 阶段编辑：`#stageEditor` 列表；骨架只读；「添加性能阶段」；每阶段名称 input + 字段多选（仅性能已勾选）；上移/下移/删除。
- 策略：两块说明 + 编辑 allow/deny 列表与 keep_types 等（可用逗号分隔 textarea，保存时 split）。

- [ ] **Step 2: 保存逻辑**

```javascript
function buildStepsFromEditor() {
  const steps = [{ id: "entity", type: "entity", name: "骨架" }];
  // 从 DOM 收集性能阶段 → push {id, type:"property", name, group, fields}
  return steps;
}

async function saveConfigView() {
  const steps = buildStepsFromEditor();
  const unassigned = propertyIdsSelected().filter(
    (id) => !steps.some((s) => s.type === "property" && (s.fields || []).includes(id))
  );
  if (unassigned.length) {
    $("runStatus").textContent = "未挂阶段的性能字段：" + unassigned.join(", ");
    return;
  }
  state.overlay.steps = steps;
  state.overlay.property_source = readStrategyPropertySource();
  state.overlay.figure_filter = readStrategyFigureFilter();
  await saveOverlay(state.overlay);
}
```

- [ ] **Step 3: 手动验收**

在配置页把磁学字段移出、增加名为「电导性能」的空阶段再挂字段（若库无电导可先只测合并力学+磁学为一段）；保存后 `GET .../config` 见 `steps`；刷新后阶段编辑器恢复。

- [ ] **Step 4: Commit（若可用）**

```bash
git -c safe.directory=* add app/
git -c safe.directory=* commit -m "feat: config view for fields, stages, and plain-language strategy"
```

---

### Task 8: 文献与运行视图整理

**Files:**
- Modify: `app/index.html`、`app/app.js`

**Interfaces:**
- Consumes: 现有 `/api/run`、`/api/run_step`、`/api/parse`、`/api/reextract`；`state.project.steps` 显示名
- Produces: 文献列表 + 主按钮；进度用阶段 `name`；跑完提供「去复核」→ `setView("review")`；侧栏旧「抽取步骤」四步清单改为可选进度或移除主路径

- [ ] **Step 1: 挪面板与文案**

- 文献选择、PDF 路径、运行按钮、模式（含 `single_pass` 高级）放入 `data-view-panel="papers"`。
- `renderStepList`：若保留，仅显示 `type!=figure` 的 steps，名称用配置；或改为水平进度。
- 去掉运行区对「图片过滤」的强调。

- [ ] **Step 2: 跑完跳转**

在 `renderRun` / 成功回调末尾显示按钮：

```javascript
$("btnGoReview").onclick = () => {
  setView("review");
  loadReview();
};
```

- [ ] **Step 3: 手动验收**

`demo_steel` 整篇一次跑完 → 点去复核进入复核视图。

- [ ] **Step 4: Commit（若可用）**

```bash
git -c safe.directory=* add app/
git -c safe.directory=* commit -m "feat: papers-and-run view with stage progress and jump to review"
```

---

### Task 9: 复核视图 — PDF/md、层级、异色、缩略图

**Files:**
- Modify: `app/index.html`、`app/app.js`、`app/styles.css`
- Optional: `app/vendor/marked.min.js`（或文档约定 CDN）

**Interfaces:**
- Consumes: `/api/paper_meta`、`/api/paper_pdf`、`/api/paper_text`、`/api/paper_image`、`/api/result`
- Produces: 左栏 PDF 或渲染 md；右栏层级树；`rejected_by_rule` 使用 CSS class `field-rejected`；无恢复/编辑；缩略图 URL：`/api/paper_image?project=&paper_id=&name=`

- [ ] **Step 1: 左栏载入**

```javascript
async function loadSourcePane(project, paperId) {
  const meta = await api(`/api/paper_meta?project=${...}&paper_id=${...}`);
  if (meta.has_pdf) {
    $("pdfViewer").src = `/api/paper_pdf?project=${...}&paper_id=${...}`;
    $("pdfViewer").hidden = false;
    $("paperHtmlViewer").hidden = true;
  } else {
    const txt = await api(`/api/paper_text?...`);
    // 将 md 中 images_from_md/X 替换为 API URL 后 marked.parse → paperHtmlViewer
    $("pdfViewer").hidden = true;
    $("paperHtmlViewer").hidden = false;
  }
}
```

新增 `#paperHtmlViewer`（article/div）；保留隐藏的纯文本节点供高亮算法使用（或高亮时切到 text 模式）。

- [ ] **Step 2: 右栏层级渲染**

替换扁平 `renderResultFieldList`：

```javascript
function renderResultTree(result) {
  // 文章信息 section
  // for sample of samples:
  //   header 样品 {sample_id}
  //   for condition where sample_id match:
  //     状态 {condition_id} + property groups as field blocks
  //     thumbnails: figures where figure.sample_id/condition_id match
  // 图片总览 section（含 rejected 异色）
}
```

字段块 class：`field-result-item` + （`raw.status==="rejected_by_rule"` ? `field-rejected` : `field-accepted`）。展示 `reject_reason`。中文名从 `state.fieldLibrary` / rules label 查，禁止主文案只用 JSON path。

- [ ] **Step 3: 筛选与无标注控件**

- 「全部 / 仅未通过」toggle。
- 确认 DOM 无「恢复」「编辑值」按钮。

- [ ] **Step 4: 手动验收（对照规格 §9.3–9.5）**

`demo_steel` 载入最新 two_stage 结果：屈服强度 600 异色；Figure 3 XRD 异色且有缩略图或占位；无 pdf 时 md 可见 fig 图。

- [ ] **Step 5: Commit（若可用）**

```bash
git -c safe.directory=* add app/
git -c safe.directory=* commit -m "feat: review pane with PDF/md, hierarchy, status colors, thumbnails"
```

---

### Task 10: 导出视图 + 文档收尾

**Files:**
- Modify: `app/index.html`、`app/app.js`
- Modify: `README.md`（任务流与 status 语义简述）
- Modify: `docs/tool_design_notes.md`（指向新规格）

**Interfaces:**
- Consumes: `/api/projects/:id/export`、`/api/projects/:id/export_results`
- Produces: 配置 JSON 下载；结果 JSON 下载（checkbox「含规则未通过」→ `include_rejected`）

- [ ] **Step 1: 导出 UI**

两按钮 + `include_rejected` checkbox；触发 `fetch` → blob download。

- [ ] **Step 2: README 三节更新**

说明五视图、阶段可配、规则未通过保留在结果中；删除「规则校验会把它剔除」的过时说法，改为「标记为未通过」。

- [ ] **Step 3: 全量测试 + 手动冒烟**

Run: `python3 -m pytest -q`  
Expected: PASS  

手动：配置阶段 → 跑 demo → 复核异色 → 导出仅 accepted。

- [ ] **Step 4: Commit（若可用）**

```bash
git -c safe.directory=* add app/ README.md docs/tool_design_notes.md
git -c safe.directory=* commit -m "feat: export view and docs for workbench UX redesign"
```

- [ ] **Step 5: 隐藏 legacy 面板**

确认 `#legacyDevPanels`（Schema/Prompt/快照/旧 JSON 三列）默认 `hidden`；若需调试可在导出页「高级」勾选显示。无测试要求，手动确认主路径干净。

---

## Spec coverage（自检）

| 规格条目 | Task |
| --- | --- |
| 五视图导航 | 6, 8, 10 |
| 自定义性能阶段 / `steps` 真相 | 3, 7 |
| 无用户可见「图片过滤」步 | 3, 4, 8 |
| 规则未通过保留 + status | 1, 2, 9 |
| 无改值/无恢复 | 9（显式禁止） |
| PDF 优先 / 渲染 md | 5, 9 |
| 层级 + 缩略图 | 5, 9 |
| 策略白话配置 | 7 |
| 配置/结果导出 | 5, 10 |
| demo 验收与回归 | 4, 10 |

## Placeholder scan

无 TBD/TODO；测试与函数名在任务间一致：`validate_overlay_stages`、`filter_result_by_status`、`resolve_paper_image_path`、`status`/`rejected_by_rule`。
