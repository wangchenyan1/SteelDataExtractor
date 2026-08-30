# 抽取工作台真实任务补齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按三块规格把工作台改成能配字段/阶段、上传并勾选多篇抽取、以及按大类（含项目自建）挂细化字段。

**Architecture:** 不重写抽取引擎。第 1 块改覆盖层校验与配置页草稿；第 2 块扩展文献列表 API 与文献页；第 3 块扩展模板大类、公共库种子与覆盖层 `property_groups`。三块按序落地，每一块结束即可单独验收。

**Tech Stack:** Python 3 标准库 + 现有 `tools/config_model.py` / `pipeline.py` / `workbench_server.py`；前端 `app/index.html` + `app.js` + `styles.css`；`python3 -m pytest`。

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-28-field-stage-config-design.md`、`2026-08-28-paper-upload-batch-design.md`、`2026-08-28-field-library-groups-design.md`。
- 禁止写入 `/internfs/wangchenyan/shougang/Extract_data`。
- 不迁移四个只读快照为可跑；不提供覆盖解析；不新开批量 parse/run 聚合 HTTP。
- 工作区 git 可能因 `safe.directory` 失败。每个 Commit 步：先 `git -c safe.directory=* rev-parse --is-inside-work-tree`；失败则跳过 commit，不要改 global git config，不要 `git init`。
- 测试根目录：`cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest -q`
- 已有 `paper.md` 的 parse / run 不得再调 UniParser（现有 skip 保持）。
- 保存配置前勾选不得 PUT；空性能段保存时剥离，不报错。

---

## 文件结构

| 路径 | 职责 |
| --- | --- |
| `tools/config_model.py` | `LOCKED_FIELD_IDS`、剥空段、挂段辅助、`create_project` 写 `steps`、合并 `property_groups`、`generate_steps` 读自建大类 |
| `tools/pipeline.py` | `paper_title_from_md`、`list_paper_records` |
| `tools/workbench_server.py` | `/api/papers` 与 projects.papers 改为对象数组 |
| `app/index.html` | 配置页阶段芯片区；文献上传+表；大类管理；新建字段表单 |
| `app/app.js` | 配置草稿、自动挂段、文献导入/多篇抽取、自建大类 |
| `app/styles.css` | 文献表、芯片、大类行 |
| `configs/templates/steel.json` | 六类 `property_groups` |
| `configs/field_library/steel.json` | 三条种子字段 |
| `tests/test_config_stages.py` | 空段剥离、未挂字段、挂段函数 |
| `tests/test_config_model.py` | `create_project` 写出 steps + 锁定字段 |
| `tests/test_paper_records.py` | 文献记录 title/extracted |
| `tests/test_workbench_config_status.py` | 前端字符串断言（草稿/芯片/上传/大类） |

---

# Part A — 字段勾选自动挂阶段

规格：`2026-08-28-field-stage-config-design.md`

### Task 1: 空段剥离与校验

**Files:**
- Modify: `tools/config_model.py`（`validate_overlay_stages`、`save_overlay`）
- Test: `tests/test_config_stages.py`

**Interfaces:**
- Consumes: 现有 `validate_overlay_stages(overlay, fields) -> None`
- Produces: `strip_empty_property_steps(steps: list) -> list`；校验前先剥离；空段不再抛「fields 不能为空」

- [ ] **Step 1: 写失败测试**

在 `tests/test_config_stages.py` 追加：

```python
from tools.config_model import strip_empty_property_steps, validate_overlay_stages, save_overlay


def test_strip_empty_property_steps():
    steps = [
        {"id": "entity", "type": "entity", "name": "骨架"},
        {"id": "mechanical", "type": "property", "name": "力学性能", "fields": ["yield_strength"]},
        {"id": "empty", "type": "property", "name": "空", "fields": []},
    ]
    out = strip_empty_property_steps(steps)
    assert [s["id"] for s in out] == ["entity", "mechanical"]


def test_validate_allows_after_empty_stripped():
    fields = [{"id": "yield_strength", "category": "property", "group": "mechanical_properties"}]
    overlay = {
        "steps": [
            {"id": "entity", "type": "entity", "name": "骨架"},
            {"id": "mechanical", "type": "property", "name": "力学性能", "fields": ["yield_strength"]},
            {"id": "empty", "type": "property", "name": "空", "fields": []},
        ]
    }
    validate_overlay_stages(overlay, fields)
    assert [s["id"] for s in overlay["steps"]] == ["entity", "mechanical"]
```

保留现有 `test_validate_rejects_unassigned_property_field`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_config_stages.py::test_strip_empty_property_steps tests/test_config_stages.py::test_validate_allows_after_empty_stripped -v`

Expected: FAIL `strip_empty_property_steps` 未定义

- [ ] **Step 3: 最小实现**

在 `tools/config_model.py` 的 `validate_overlay_stages` 之前加入：

```python
def strip_empty_property_steps(steps: list) -> list:
    out = []
    for s in steps or []:
        if s.get("type") == "property" and not list(s.get("fields") or []):
            continue
        out.append(s)
    return out
```

改 `validate_overlay_stages`：开头 `steps = strip_empty_property_steps(overlay.get("steps") or [])`，写回 `overlay["steps"] = steps`，删掉「`if not fl: raise 性能阶段 fields 不能为空`」。其余校验不变。

改 `save_overlay`：在 `if overlay.get("steps"):` 内、`validate_overlay_stages` 之前执行 `overlay["steps"] = strip_empty_property_steps(overlay["steps"])`。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_config_stages.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/config_model.py tests/test_config_stages.py
git commit -m "fix: strip empty property stages before overlay validate"
```

失败则跳过 commit（见 Global Constraints）。

---

### Task 2: create_project 写 steps，并补锁定字段

**Files:**
- Modify: `tools/config_model.py`（`create_project`、常量）
- Modify: `tests/test_config_model.py`（`test_create_project_selects_subset`）
- Test: `tests/test_config_stages.py`（`assign_property_to_stage`）

**Interfaces:**
- Consumes: `generate_steps`、`effective_fields`、`load_template`、`load_field_library`
- Produces:
  - `LOCKED_FIELD_IDS = ("sample_id", "condition_id", "figure_id", "placeholder_index")`
  - `assign_property_to_stage(stages: list, field: dict, group_names: dict) -> list`
  - `create_project(...)` 落盘 overlay 含 `steps`；`selected_field_ids` 并入库中存在的锁定 id

- [ ] **Step 1: 写失败测试**

`tests/test_config_stages.py`：

```python
from tools.config_model import assign_property_to_stage

NAMES = {"mechanical_properties": "力学性能", "electrical_properties": "电性能"}


def test_assign_creates_named_stage():
    field = {"id": "yield_strength", "category": "property", "group": "mechanical_properties"}
    stages = assign_property_to_stage([], field, NAMES)
    assert stages == [{
        "id": "mechanical", "type": "property", "name": "力学性能",
        "group": "mechanical_properties", "fields": ["yield_strength"],
    }]


def test_assign_same_group_reuses_stage():
    field1 = {"id": "yield_strength", "category": "property", "group": "mechanical_properties"}
    field2 = {"id": "tensile_strength", "category": "property", "group": "mechanical_properties"}
    stages = assign_property_to_stage([], field1, NAMES)
    stages = assign_property_to_stage(stages, field2, NAMES)
    assert len(stages) == 1
    assert stages[0]["fields"] == ["yield_strength", "tensile_strength"]


def test_assign_follows_existing_same_group_stage_even_if_renamed():
    stages = [{
        "id": "tensile", "type": "property", "name": "拉伸",
        "group": "mechanical_properties", "fields": ["yield_strength"],
    }]
    field = {"id": "tensile_strength", "category": "property", "group": "mechanical_properties"}
    out = assign_property_to_stage(stages, field, NAMES)
    assert len(out) == 1
    assert out[0]["name"] == "拉伸"
    assert "tensile_strength" in out[0]["fields"]
```

改 `tests/test_config_model.py` 的 `test_create_project_selects_subset`：创建后

```python
overlay = cm.load_overlay(ws, "mini")
assert "title" in overlay["selected_field_ids"]
assert "sample_id" in overlay["selected_field_ids"]
assert "yield_strength" in overlay["selected_field_ids"]
assert "condition_id" in overlay["selected_field_ids"]  # 库中存在则补锁定
assert overlay.get("steps")
assert overlay["steps"][0]["type"] == "entity"
assert any(s.get("group") == "mechanical_properties" for s in overlay["steps"])
```

不要再断言 `selected_field_ids` 恰好等于三个元素。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_config_stages.py::test_assign_creates_named_stage tests/test_config_model.py::test_create_project_selects_subset -v`

Expected: FAIL（`assign_property_to_stage` 未定义；create 后无 `steps` 或锁定字段）

- [ ] **Step 3: 最小实现**

`tools/config_model.py`：

```python
LOCKED_FIELD_IDS = ("sample_id", "condition_id", "figure_id", "placeholder_index")


def assign_property_to_stage(stages: list, field: dict, group_names: dict) -> list:
    stages = [dict(s, fields=list(s.get("fields") or [])) for s in (stages or [])]
    fid = field["id"]
    group = field.get("group") or ""
    if any(fid in (s.get("fields") or []) for s in stages):
        return stages
    target = None
    if group:
        target = next((s for s in stages if s.get("group") == group), None)
    elif not group:
        target = next((s for s in stages if s.get("id") == "other"), None)
        if target is None:
            target = {
                "id": "other",
                "type": "property",
                "name": "其他性能",
                "group": "other_properties",
                "fields": [],
            }
            stages.append(target)
    if target is None:
        base_id = group.removesuffix("_properties") if group else "other"
        step_id = base_id
        existing = {s.get("id") for s in stages}
        n = 2
        while step_id in existing:
            step_id = f"{base_id}_{n}"
            n += 1
        target = {
            "id": step_id,
            "type": "property",
            "name": group_names.get(group, group or "其他性能"),
            "group": group or "other_properties",
            "fields": [],
        }
        stages.append(target)
    if fid not in target["fields"]:
        target["fields"].append(fid)
    return stages
```

改名后的段只要仍带原来的 `group`，同组新字段会进该段。字段被拖到另一段后，保存时用 `inferGroup` 更新该段 `group`。

`create_project` 在组装 overlay 后、`save_overlay` 前：

```python
    library = load_field_library(root, template_id)
    lib_ids = {f["id"] for f in library.get("fields") or []}
    selected = list(selected_field_ids)
    for lid in LOCKED_FIELD_IDS:
        if lid in lib_ids and lid not in selected:
            selected.append(lid)
    overlay["selected_field_ids"] = selected
    template = load_template(root, template_id)
    fields = effective_fields(library, overlay)
    overlay["steps"] = generate_steps(template, fields, overlay)
    save_overlay(root, project_id, overlay)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_config_stages.py tests/test_config_model.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/config_model.py tests/test_config_stages.py tests/test_config_model.py
git commit -m "feat: write steps and lock ids on create_project"
```

---

### Task 3: 配置页草稿、自动挂段、阶段芯片

**Files:**
- Modify: `app/app.js`（`onLibraryCheckChange`、`renderStageEditor`、`saveConfigView`、`setView`、`loadConfigEditor`）
- Modify: `app/index.html`（如需锁定提示，可选）
- Test: `tests/test_workbench_config_status.py`

**Interfaces:**
- Consumes: Task 2 的挂段规则（前端用同等逻辑，不发新 API）
- Produces: 勾选不 PUT；性能勾选调用 `assignPropertyToDraft`；阶段区只有芯片；锁定字段 checkbox disabled

- [ ] **Step 1: 写失败测试（静态断言）**

在 `tests/test_workbench_config_status.py` 追加：

```python
def test_library_check_does_not_save_overlay_immediately():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("async function onLibraryCheckChange")
    end = js.index("async function saveOverlay", start)
    fn = js[start:end]
    assert "saveOverlay" not in fn
    assert "assignPropertyToDraft" in fn


def test_stage_editor_renders_chips_not_property_checkboxes():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("function renderStageEditor")
    end = js.index("function loadConfigEditor", start)
    fn = js[start:end]
    assert "stage-chip" in fn
    assert 'input[type="checkbox"]' not in fn or "checkbox" not in fn.split("stage-fields")[-1][:400]


def test_locked_field_ids_constant():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "sample_id" in js
    assert "LOCKED_FIELD_IDS" in js
```

（第三段 checkbox 断言若过严：改为断言 `stage-chip` 存在且 `cb.disabled = takenElsewhere` 那段循环已删除。）

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_workbench_config_status.py::test_library_check_does_not_save_overlay_immediately -v`

Expected: FAIL

- [ ] **Step 3: 改前端**

`app/app.js`：

1. 增加 `const LOCKED_FIELD_IDS = new Set(["sample_id","condition_id","figure_id","placeholder_index"]);`
2. `state.configHydratedFor` 记录当前已灌入草稿的 `projectId`。`loadConfigEditor`：仅当 `state.configHydratedFor !== state.currentId` 时从 overlay 重建 `stageDraft` / 勾选 / 策略，然后设 `configHydratedFor`。`setView("config")` 只 `render`，不强制重载。`selectProject` 时把 `configHydratedFor` 置空再加载。
3. `onLibraryCheckChange`：更新 `state.overlay.selected_field_ids`；性能字段勾选则 `assignPropertyToDraft(meta)`，取消则从各段 `fields` 去掉并删空段；**不要** `await saveOverlay`。最后 `renderFieldLibraryChecks(); renderStageEditor();`
4. `assignPropertyToDraft(field)`：按 Task 2 同规则改 `state.stageDraft`（只含 property 段）。`group` 显示名：`state.overlay.property_groups` 优先，再 `state.fieldLibrary` 字段的 group，再硬编码「力学性能」等可由 `field.group` 去掉 `_properties`。
5. `renderFieldLibraryChecks`：锁定 id 的 checkbox `disabled=true` 且保持 checked。
6. `renderStageEditor`：性能段字段渲染为 `<span class="stage-chip" data-field-id="...">中文名</span>`，带「移至」`<select>`（选项为其他性能段）。不要再给每个性能字段做 checkbox。
7. `saveConfigView`：`steps = buildStepsFromEditor()` 后 `steps = steps.filter(s => s.type !== "property" || (s.fields||[]).length)`；未挂性能字段用中文 label 拦截；补 LOCKED 进 selected；然后唯一一次 `saveOverlay`；成功后 `configHydratedFor = null` 再 `refreshProjectConfig`。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_workbench_config_status.py tests/test_config_stages.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/app.js app/index.html app/styles.css tests/test_workbench_config_status.py
git commit -m "feat: draft field checks auto-assign stages as chips"
```

Part A 验收（人手）：勾屈服强度出现力学性能芯片；刷新未保存则复原；保存后才落盘。

---

# Part B — 文献上传与多篇抽取

规格：`2026-08-28-paper-upload-batch-design.md`

### Task 4: 文献记录（title / extracted）

**Files:**
- Modify: `tools/pipeline.py`
- Create: `tests/test_paper_records.py`

**Interfaces:**
- Consumes: `list_papers`、`list_runs`、`get_paper_text`、`_latest_merged_run`
- Produces:
  - `paper_title_from_md(text: str) -> str | None`
  - `list_paper_records(root, project_cfg) -> list[dict]` 每项 `{paper_id, title, parsed: True, extracted: bool}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_paper_records.py
from pathlib import Path
from tools.pipeline import paper_title_from_md, list_paper_records, load_workspace_config

ROOT = Path(__file__).resolve().parents[1]


def test_title_from_first_heading():
    md = "preface\n# High temperature tensile\n\nHello\n"
    assert paper_title_from_md(md) == "High temperature tensile"


def test_title_none_without_heading():
    assert paper_title_from_md("no heading here") is None


def test_list_paper_records_demo_steel():
    ws = load_workspace_config(ROOT)
    cfg = ws["projects"]["demo_steel"]
    recs = list_paper_records(ROOT, cfg)
    ids = {r["paper_id"] for r in recs}
    assert "10.1007_s11665-019-04233-6" in ids
    rec = next(r for r in recs if r["paper_id"] == "10.1007_s11665-019-04233-6")
    assert rec["parsed"] is True
    assert rec["title"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_paper_records.py -v`

Expected: FAIL 未定义

- [ ] **Step 3: 最小实现**

`tools/pipeline.py`：

```python
def paper_title_from_md(text: str) -> str | None:
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or None
    return None


def list_paper_records(root: Path, project_cfg: dict) -> list:
    records = []
    for pid in list_papers(root, project_cfg):
        text = get_paper_text(root, project_cfg, pid) or ""
        extracted = False
        try:
            _latest_merged_run(root, project_cfg, pid)
            extracted = True
        except FileNotFoundError:
            extracted = False
        records.append({
            "paper_id": pid,
            "title": paper_title_from_md(text),
            "parsed": True,
            "extracted": extracted,
        })
    return records
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_paper_records.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/pipeline.py tests/test_paper_records.py
git commit -m "feat: paper records with title and extracted flag"
```

---

### Task 5: HTTP 返回文献对象数组

**Files:**
- Modify: `tools/workbench_server.py`（`handle_get /api/papers`、`build_projects_payload`）
- Test: `tests/test_paper_records.py` 或 `tests/test_api_handlers.py`

**Interfaces:**
- Consumes: `list_paper_records`
- Produces: `GET /api/papers?project=` → `{"papers":[{paper_id,title,parsed,extracted}]}`；`GET /api/projects` 的 `projects.*.papers` 同形

- [ ] **Step 1: 写失败测试**

```python
from tools import workbench_server as wb

def test_api_papers_objects():
    code, body = wb.handle_get("/api/papers", {"project": ["demo_steel"]})
    assert code == 200
    assert body["papers"]
    assert isinstance(body["papers"][0], dict)
    assert "paper_id" in body["papers"][0]
    assert "parsed" in body["papers"][0]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_paper_records.py::test_api_papers_objects -v`

Expected: FAIL（现为字符串列表）

- [ ] **Step 3: 最小实现**

`handle_get` 的 `/api/papers`：`{"papers": pipeline.list_paper_records(ROOT, cfg)}`

`build_projects_payload`：`"papers": pipeline.list_paper_records(ROOT, cfg)`

导出循环若用 `list_papers` 取 id，保持 `list_papers` 不变。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_paper_records.py tests/test_export_results.py tests/test_api_handlers.py -q`

Expected: PASS（若有测试仍当 papers 为 str，一并改成 `p["paper_id"] if isinstance(p, dict) else p`）

- [ ] **Step 5: Commit**

```bash
git add tools/workbench_server.py tests/test_paper_records.py
git commit -m "feat: expose paper records on papers and projects APIs"
```

---

### Task 6: 文献页上传 + 表 + 多篇抽取

**Files:**
- Modify: `app/index.html`（`data-view-panel="papers"`）
- Modify: `app/app.js`（`renderPapers`、parse/run）
- Modify: `app/styles.css`
- Test: `tests/test_workbench_config_status.py`

**Interfaces:**
- Consumes: Task 5 API；现有 `POST /api/parse` multipart、`POST /api/run`
- Produces: 多选 PDF、导入进度、文献表、整篇跑当前、抽取所选

- [ ] **Step 1: 写失败测试**

```python
def test_papers_view_has_upload_and_table():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    papers = html[html.index('data-view-panel="papers"'):]
    assert 'id="pdfFileInput"' in papers
    assert "multiple" in papers
    assert 'id="paperTable"' in papers
    assert 'id="btnImportPdfs"' in papers
    assert 'id="btnRunSelected"' in papers
    assert 'id="paperRunPreview"' not in papers.split("legacy")[0] or 'hidden' in papers


def test_import_pdfs_function_exists():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "async function importPdfs" in js
    assert "async function runSelectedPapers" in js
    assert "FormData" in js
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_workbench_config_status.py::test_papers_view_has_upload_and_table -v`

Expected: FAIL

- [ ] **Step 3: 改 HTML/JS**

文献主面板替换为：

- `<input id="pdfFileInput" type="file" accept=".pdf" multiple />`
- `<button id="btnImportPdfs">导入并解析</button>`
- `<div id="importProgress"></div>`
- `<table id="paperTable">` 列：勾选、文献（title 或 paper_id）、解析、抽取
- 表头「全选已解析」`#paperSelectAll`
- 按钮：`btnRunAll`（整篇跑当前）、`btnRunSelected`（抽取所选）
- 把路径 / paper_id / JSON preview / extractMode 包进 `<details class="advanced">`，主路径不验收

`renderPapers`：消费 `state.project.papers` 为对象数组（兼容旧字符串：包成 `{paper_id, parsed:true}`）。点行（非 checkbox）设 `state.paperId` 并高亮。

`importPdfs`：对 `pdfFileInput.files` 串行

```javascript
const fd = new FormData();
fd.append("project", state.currentId);
fd.append("pdf", file, file.name);
await fetch("/api/parse", { method: "POST", body: fd }).then(...)
```

进度行：等待/解析中/已解析/已跳过/失败。`skipped` 当跳过。失败不中断。结束后 `reloadProjects` + `renderPapers`。只读项目隐藏上传。

`runSelectedPapers`：勾选的 `paper_id` 串行 `POST /api/run` `{project, paper_id, mode:"two_stage", partition, model_id}`。无勾选或项目不可跑则按钮 disabled。进行中禁用导入与再抽取。

`parseOnly` / 路径导入可留在 advanced，调用现有逻辑。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_workbench_config_status.py tests/test_paper_records.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/index.html app/app.js app/styles.css tests/test_workbench_config_status.py
git commit -m "feat: multi PDF import and selected-paper extract"
```

---

# Part C — 性能大类与种子字段

规格：`2026-08-28-field-library-groups-design.md`

### Task 7: 模板六类 + 库种子 + generate_steps 读自建大类

**Files:**
- Modify: `configs/templates/steel.json`
- Modify: `configs/field_library/steel.json`
- Modify: `tools/config_model.py`（`merged_property_groups`、`generate_steps`）
- Test: `tests/test_config_stages.py`、`tests/test_config_model.py`

**Interfaces:**
- Consumes: overlay `property_groups: [{id, name}]`
- Produces: `merged_property_groups(template, overlay) -> list`；`generate_steps` 按模板顺序再接覆盖层自建类

- [ ] **Step 1: 写失败测试**

```python
def test_merged_property_groups_appends_overlay():
    from tools.config_model import merged_property_groups
    template = {"property_groups": [{"id": "mechanical_properties", "name": "力学性能"}]}
    overlay = {"property_groups": [{"id": "fatigue_properties", "name": "疲劳性能"}]}
    ids = [g["id"] for g in merged_property_groups(template, overlay)]
    assert ids == ["mechanical_properties", "fatigue_properties"]


def test_generate_steps_includes_overlay_group():
    from tools.config_model import generate_steps
    template = {"property_groups": [{"id": "mechanical_properties", "name": "力学性能"}]}
    fields = [{"id": "fatigue_limit", "category": "property", "group": "fatigue_properties"}]
    overlay = {"property_groups": [{"id": "fatigue_properties", "name": "疲劳性能"}]}
    steps = generate_steps(template, fields, overlay)
    assert [s["id"] for s in steps if s["type"] == "property"] == ["fatigue"]
    assert steps[-1]["name"] == "疲劳性能"
```

另加：库文件含 `hardness` / `electrical_conductivity` / `impact_toughness`；模板 `property_groups` 含 `electrical_properties`。

```python
def test_steel_library_has_seed_property_fields():
    lib = json.loads((ROOT / "configs/field_library/steel.json").read_text(encoding="utf-8"))
    ids = {f["id"] for f in lib["fields"]}
    assert {"hardness", "electrical_conductivity", "impact_toughness"} <= ids
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_config_stages.py::test_merged_property_groups_appends_overlay tests/test_config_model.py::test_steel_library_has_seed_property_fields -v`

Expected: FAIL

- [ ] **Step 3: 最小实现**

`merged_property_groups`：模板组 + 覆盖层组，id 去重（模板优先）。

`generate_steps` 自动生成分支：用 `merged_property_groups(template, overlay)` 代替只读 `template["property_groups"]`。无 `group` 的性能字段不进自动段（仍可由前端挂「其他性能」）。

模板追加：

```json
{"id": "electrical_properties", "name": "电性能"},
{"id": "impact_properties", "name": "冲击性能"},
{"id": "corrosion_properties", "name": "腐蚀性能"},
{"id": "phase_stability", "name": "相稳定性"}
```

库追加三条（`number_with_unit`，规则按规格第 4 节短写）。不要加 `conductivity`。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_config_stages.py tests/test_config_model.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add configs/templates/steel.json configs/field_library/steel.json tools/config_model.py tests/test_config_stages.py tests/test_config_model.py
git commit -m "feat: steel property groups, seed fields, overlay groups"
```

---

### Task 8: 配置页自建大类 + 新建字段选大类

**Files:**
- Modify: `app/index.html`（大类管理、`fieldDialog`）
- Modify: `app/app.js`
- Test: `tests/test_workbench_config_status.py`

**Interfaces:**
- Consumes: Task 7 合并大类；第 1 块草稿保存
- Produces: `state.overlay.property_groups` 草稿；新建性能字段必选大类；保存时一并 PUT

- [ ] **Step 1: 写失败测试**

```python
def test_add_property_group_ui():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    assert 'id="btnAddPropertyGroup"' in html
    assert 'id="fieldLabel"' in html
    assert 'id="fieldGroup"' in html


def test_save_config_includes_property_groups():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    fn = js[js.index("async function saveConfigView"): js.index("function renderFields")]
    assert "property_groups" in fn
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_workbench_config_status.py::test_add_property_group_ui -v`

Expected: FAIL

- [ ] **Step 3: 改 UI**

配置页阶段区上方加「性能大类」：列出合并大类；模板类无删除按钮；`btnAddPropertyGroup` prompt/小表单要中文名，写入 `state.overlay.property_groups`（草稿）。删除自建类：若 `stageDraft` 或已选性能字段的 `group` 等于该类 id，则 `setConfigStatus` 拦截。

`fieldDialog`：

- `fieldLabel` 中文名（必填）
- `fieldLevel` 类别
- `fieldGroup`：类别=property 时显示，选项=合并大类
- `fieldName` 改为可选内部 id，默认根据 label 生成：非 ASCII 则 `field_` + Date.now().toString(36)
- 性能未选大类不能加入
- `addPrivateField` 写入 `private_fields` + 草稿已选 + `assignPropertyToDraft`；不单独 PUT

`saveConfigView` 增加 `state.overlay.property_groups = state.overlay.property_groups || []`（仅自建项，不要把模板六类写进覆盖层）。

性能勾选按合并大类分组渲染。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_workbench_config_status.py tests/test_config_stages.py tests/test_config_model.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/index.html app/app.js app/styles.css tests/test_workbench_config_status.py
git commit -m "feat: project property groups and labeled private fields"
```

---

### Task 9: 回归套件

**Files:** 不新写功能

- [ ] **Step 1: 跑全量测试**

Run: `python3 -m pytest -q`

Expected: PASS

- [ ] **Step 2: 对照规格清单**

- 勾选不即时保存、芯片挂段、空段剥离、锁定字段、create 含 steps
- 上传多 PDF、已有 md skip、文献表、抽取所选
- 六类+三种子、自建大类不写模板、demo_steel steps 不重算

缺了就回到对应 Task 补，不要开新范围。

- [ ] **Step 3: Commit（若有修复）**

```bash
git add -u
git commit -m "test: workbench real-task regression"
```

无变更则跳过。

---

## 规格覆盖（自检）

| 规格条目 | Task |
| --- | --- |
| 空段剥离 / 未挂拦截 | 1, 3 |
| 勾选即挂段 / 草稿保存 / 锁定字段 | 2, 3 |
| create_project 写 steps | 2 |
| 文献记录与 API | 4, 5 |
| 单/多 PDF、skip、表、抽取所选 | 6 |
| 模板大类、种子、自建大类 | 7, 8 |
| demo_steel 不重算 steps | 3 的 hydrated 逻辑 + generate_steps 仅在无 steps 时生成 |

无 TBD。函数名：`strip_empty_property_steps`、`assign_property_to_stage`、`LOCKED_FIELD_IDS`、`list_paper_records`、`paper_title_from_md`、`merged_property_groups`、`importPdfs`、`runSelectedPapers`。
