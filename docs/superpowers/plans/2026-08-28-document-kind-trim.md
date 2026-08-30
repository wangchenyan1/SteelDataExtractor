# 文档类型（文献 / 专利）剪裁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 项目覆盖层增加 `document_kind`（`paper` / `patent`），配置页可选，送入 LLM 前按类型剪裁 parser 文本。

**Architecture:** 覆盖层存类型；`prepare_model_text` 分发到现有 `trim_input` 或迁入的专利 `core_text` 过滤器。UniParser、字段、阶段、prompt 不变。`paper.md` 只读。

**Tech Stack:** Python 3 标准库；`tools/input_trim.py`、`tools/patent_text_filter.py`、`tools/config_model.py`、`tools/pipeline.py`、`tools/workbench_server.py`；前端 `app/index.html` + `app/app.js` + `app/styles.css`；`python3 -m pytest`。

## Global Constraints

- 规格：`docs/superpowers/specs/2026-08-28-document-kind-trim-design.md`。
- 禁止写入 `/internfs/wangchenyan/shougang/Extract_data`。运行时禁止 import / 调用该目录脚本。
- 专利规则从只读文件复制进本仓库：`/internfs/wangchenyan/shougang/Extract_data/cuti_patent/scripts/cuti_patent_text_filter_probe.py`。
- 不按单篇选类型；不为专利另做字段/阶段/prompt；不做超长专利分段。
- 现有项目（含 `cuti`）不要回填 `document_kind`；缺省按 `paper`。
- 两种剪裁互斥，不叠加。
- `handle_put` 校验失败沿用现网：`Exception` → HTTP 500 + `{"error": "..."}`，不要单独改成 400。
- 工作区 git 可能因 `safe.directory` 或 Author identity 失败。每个 Commit 步：`git -c safe.directory=* status`；失败或 hook/author 报错则跳过 commit，不要改 git config，不要 `--no-verify`。
- 测试根目录：`cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest -q`

---

## 文件结构

| 路径 | 职责 |
| --- | --- |
| `tools/patent_text_filter.py` | 专利 `core_text`：噪声清洗、核心起点、drop-block、标题头 |
| `tools/input_trim.py` | `normalize_document_kind`、`prepare_model_text` |
| `tools/config_model.py` | `save_overlay` 规范化/校验；`create_project` 默认 `paper` |
| `tools/pipeline.py` | `project_document_kind`；`_prepare_run` 与重抽走分发 |
| `tools/workbench_server.py` | `GET /api/projects` 带 `document_kind` |
| `app/index.html` | 配置页文档类型下拉；项目/文献页徽章 |
| `app/app.js` | 草稿、保存、徽章、keepDraft |
| `app/styles.css` | `.kind-badge` |
| `tests/test_patent_text_filter.py` | 专利过滤器 |
| `tests/test_input_trim.py` | 分发 |
| `tests/test_config_model.py` | 保存/新建 |
| `tests/test_api_handlers.py` | projects payload |
| `tests/test_workbench_config_status.py` | 前端字符串断言 |

---

### Task 1: 专利 core_text 过滤器

**Files:**
- Create: `tools/patent_text_filter.py`
- Test: `tests/test_patent_text_filter.py`

**Interfaces:**
- Consumes: 无（不要 import `Extract_data` / `paper_parser` / `input_trim`）
- Produces: `build_filtered_text(text: str, *, paper_id: str = "") -> FilteredPatentText`；`FilteredPatentText` 字段：`title: str`、`core_text: str`、`core_start: int | None`、`removed_prefix: str`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_patent_text_filter.py`：

```python
from tools.patent_text_filter import build_filtered_text

PATENT = """# 一种铜钛合金

[54] 发明名称 一种铜钛合金及其制备方法

www.soopat.com
本页蓝色字体部分可点击查询相关专利

技术领域
本发明属于金属材料。

背景技术
现有技术提到实施例仅作对比说明。

发明内容
一种合金。

权利要求书
1. 一种合金，钛含量 1-10%。

具体实施方式
实施例1
将铜钛合金固溶后时效，测得电导率 20%IACS，硬度 200 HV。
表1 性能测试结果
"""


def test_keeps_embodiment_drops_front_matter_and_claims():
    filtered = build_filtered_text(PATENT, paper_id="p001")
    assert "具体实施方式" in filtered.core_text
    assert "电导率 20%IACS" in filtered.core_text
    assert "表1 性能测试结果" in filtered.core_text
    assert "本发明属于金属材料" not in filtered.core_text
    assert "钛含量 1-10%" not in filtered.core_text
    assert filtered.core_start is not None
    assert "[文档ID] p001" in filtered.core_text
    assert "一种铜钛合金及其制备方法" in filtered.core_text
    assert "soopat.com" not in filtered.core_text
    assert "本页蓝色字体部分可点击查询相关专利" not in filtered.core_text


def test_bare_embodiment_defers_to_strong_heading():
    text = """背景技术
正文先提到实施例作为对比。

具体实施方式
实施例2 真实工艺。
"""
    filtered = build_filtered_text(text, paper_id="p002")
    assert "真实工艺" in filtered.core_text
    assert "作为对比" not in filtered.core_text
    assert filtered.core_start is not None


def test_no_core_heading_drops_named_blocks():
    text = """摘要
这是摘要内容。

权利要求书
1. 一种方法。

发明内容
留下这段工艺描述和表2。
"""
    filtered = build_filtered_text(text, paper_id="")
    assert "这是摘要内容" not in filtered.core_text
    assert "一种方法" not in filtered.core_text
    assert "留下这段工艺描述和表2" in filtered.core_text
    assert filtered.core_start is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest tests/test_patent_text_filter.py -v`

Expected: FAIL，`ModuleNotFoundError` 或 `build_filtered_text` 未定义。

- [ ] **Step 3: 写最小实现**

创建 `tools/patent_text_filter.py`。正则与 `clean_noise` / `extract_title` / `first_core_start` / `drop_explicit_unwanted_blocks` 必须与探针脚本一致（从上述 probe 路径复制，不要改写匹配规则）。不要实现 `figure_text`、`audit`、命令行。

```python
"""Patent parser-text filter. Produces core_text for LLM input."""

from __future__ import annotations

import re
from dataclasses import dataclass


CORE_START_RE = re.compile(
    r"(?im)^[ \t#>*【\[]*"
    r"(?:\[\d+\]\s*)?"
    r"[\(（]?"
    r"(?:"
    r"具体实施方式|具体实施例|实施例|实施方式|实施发明的最佳方式|"
    r"发明的具体实施方式|用于实施发明的方式|发明实施方式|"
    r"具體實施方式|具體實施例|實施例|實施方式|發明實施方式"
    r")"
    r"[\d一二三四五六七八九十]*[\)）]?"
    r"[】\]：: 　\t]*$"
)

DROP_BLOCK_RE = re.compile(
    r"(?ims)"
    r"^[ \t#>*【\[]*(?:技术领域|发明所属的技术领域|所属领域|背景技术|摘要|权利要求书|"
    r"技術領域|發明所屬之技術領域|先前技術|背景技術|中文發明摘要|英文發明摘要|"
    r"發明摘要|申請專利範圍)"
    r"[】\]：: 　\t]*.*?"
    r"(?=^[ \t#>*【\[]*(?:背景技术|发明内容|附图说明|具体实施方式|具体实施例|"
    r"实施例|实施方式|发明的具体实施方式|发明实施方式|权利要求书|摘要|"
    r"背景技術|發明內容|圖式簡單說明|圖式簡要說明|具體實施方式|具體實施例|"
    r"實施例|實施方式|發明實施方式|申請專利範圍|中文發明摘要|英文發明摘要)"
    r"[】\]：: 　\t]*$|\Z)"
)

PATENT_TITLE_PATTERNS = [
    re.compile(r"\[54\]\s*发明名称\s*([^\n]{3,120})"),
    re.compile(r"发明名称\s*[:：]?\s*([^\n]{3,120})"),
    re.compile(r"(?m)^#\s*([^\n]{3,120})\s*$"),
]


@dataclass
class FilteredPatentText:
    title: str
    core_text: str
    core_start: int | None
    removed_prefix: str


def clean_noise(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            lines.append(line)
            continue
        if s.startswith("www.") or "soopat.com" in s.lower():
            continue
        if "本页蓝色字体部分可点击查询相关专利" in s:
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.strip() + "\n"


def extract_title(text: str, fallback: str = "") -> str:
    for pattern in PATENT_TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip(" #")
            if title:
                return title[:120]
    return fallback


def first_core_start(text: str) -> int | None:
    matches = list(CORE_START_RE.finditer(text))
    if not matches:
        return None
    strong = []
    for match in matches:
        heading = re.sub(r"^[ \t#>*【\[]+|[】\]：: 　\t]+$", "", match.group(0)).strip()
        heading = re.sub(r"^\[\d+\]\s*", "", heading)
        if not heading.startswith(("实施例", "實施例")):
            strong.append(match)
    return (strong[0] if strong else matches[0]).start()


def drop_explicit_unwanted_blocks(text: str) -> str:
    return clean_noise(DROP_BLOCK_RE.sub("\n", text))


def build_filtered_text(text: str, *, paper_id: str = "") -> FilteredPatentText:
    title = extract_title(text, fallback=paper_id)
    start = first_core_start(text)
    if start is not None:
        removed_prefix = text[:start]
        core = text[start:]
    else:
        removed_prefix = ""
        core = drop_explicit_unwanted_blocks(text)

    core = clean_noise(core)
    header = f"# {title}\n\n[文档ID] {paper_id}\n\n" if title or paper_id else ""
    core_text = header + core
    return FilteredPatentText(
        title=title,
        core_text=core_text,
        core_start=start,
        removed_prefix=removed_prefix,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace && python3 -m pytest tests/test_patent_text_filter.py -v`

Expected: PASS（3 passed）。若「发明内容」块被 `DROP_BLOCK_RE` 误伤，不要放宽正则；改测试样例，把「留下这段…」放到不会被 drop 的节名下（例如单独一段无标题正文），但 **优先保持探针正则不变**。`test_no_core_heading_drops_named_blocks` 的「发明内容」本身不在 DROP 起始列表里，应被保留。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=* add tools/patent_text_filter.py tests/test_patent_text_filter.py
git -c safe.directory=* commit -m "$(cat <<'EOF'
feat: 迁入专利 core_text 文本过滤器

EOF
)"
```

失败则跳过。

---

### Task 2: 剪裁分发 `prepare_model_text`

**Files:**
- Modify: `tools/input_trim.py`
- Test: `tests/test_input_trim.py`

**Interfaces:**
- Consumes: `trim_input`；`build_filtered_text`
- Produces:
  - `ALLOWED_DOCUMENT_KINDS = frozenset({"paper", "patent"})`
  - `normalize_document_kind(value) -> str`：`None` / `""` → `"paper"`；`"paper"` / `"patent"` 原样（先 `str.strip`）；其它 → `ValueError("非法 document_kind: ...")`
  - `prepare_model_text(text: str, document_kind=None, paper_id: str = "") -> tuple[str, dict]`

统计字典必须含：`raw_chars`、`kept_chars`、`kept_ratio`、`dropped_chars`、`document_kind`。专利额外：`core_start_found: bool`。

专利统计口径：`raw_chars = len(text or "")`；`kept_chars = len(core_text)`（含标题头）；`dropped_chars = max(raw_chars - len(filtered.core_text) + len(header), 0)` 实现时用更稳的：`body_len = len(core)`（`clean_noise` 后、加头前），`dropped_chars = max(raw_chars - body_len, 0)`，`kept_ratio = round(body_len / raw_chars, 4) if raw_chars else 1.0`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_input_trim.py` 追加：

```python
import pytest
from tools.input_trim import prepare_model_text, normalize_document_kind, trim_input


def test_normalize_document_kind_defaults_and_rejects():
    assert normalize_document_kind(None) == "paper"
    assert normalize_document_kind("") == "paper"
    assert normalize_document_kind("patent") == "patent"
    with pytest.raises(ValueError, match="非法 document_kind"):
        normalize_document_kind("book")


def test_prepare_paper_matches_trim_input():
    kept_a, stats_a = trim_input(APPENDIX_AFTER_REFS)
    kept_b, stats_b = prepare_model_text(APPENDIX_AFTER_REFS, "paper")
    assert kept_a == kept_b
    assert stats_b["document_kind"] == "paper"
    assert "keep this appendix table" in kept_b
    assert "[1] Smith 2019" not in kept_b


def test_prepare_patent_uses_core_text():
    text = """摘要
不要这段。

具体实施方式
实施例1 保留这段实测硬度 180 HV。
"""
    kept, stats = prepare_model_text(text, "patent", paper_id="x1")
    assert "保留这段实测硬度 180 HV" in kept
    assert "不要这段" not in kept
    assert stats["document_kind"] == "patent"
    assert stats["core_start_found"] is True
    assert stats["raw_chars"] == len(text)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_input_trim.py::test_normalize_document_kind_defaults_and_rejects tests/test_input_trim.py::test_prepare_paper_matches_trim_input tests/test_input_trim.py::test_prepare_patent_uses_core_text -v`

Expected: FAIL，`normalize_document_kind` / `prepare_model_text` 未定义。

- [ ] **Step 3: 写最小实现**

在 `tools/input_trim.py` 增加（文件顶部已有 `trim_input`，不要改它的行为）：

```python
from patent_text_filter import build_filtered_text

ALLOWED_DOCUMENT_KINDS = frozenset({"paper", "patent"})


def normalize_document_kind(value) -> str:
    if value is None:
        return "paper"
    kind = str(value).strip()
    if kind == "":
        return "paper"
    if kind not in ALLOWED_DOCUMENT_KINDS:
        raise ValueError(f"非法 document_kind: {kind}，仅允许 paper 或 patent")
    return kind


def prepare_model_text(text: str, document_kind=None, paper_id: str = "") -> tuple[str, dict]:
    kind = normalize_document_kind(document_kind)
    raw = text or ""
    if kind == "paper":
        kept, stats = trim_input(raw)
        stats = dict(stats)
        stats["document_kind"] = "paper"
        return kept, stats

    filtered = build_filtered_text(raw, paper_id=paper_id or "")
    header = ""
    if filtered.title or paper_id:
        header = f"# {filtered.title}\n\n[文档ID] {paper_id}\n\n"
    body_len = max(len(filtered.core_text) - len(header), 0)
    raw_len = len(raw)
    stats = {
        "raw_chars": raw_len,
        "kept_chars": len(filtered.core_text),
        "kept_ratio": round(body_len / raw_len, 4) if raw_len else 1.0,
        "dropped_chars": max(raw_len - body_len, 0),
        "document_kind": "patent",
        "core_start_found": filtered.core_start is not None,
    }
    return filtered.core_text, stats
```

`input_trim.py` 被 `pipeline` 以脚本目录方式 import（`from input_trim import ...`），因此这里用 `from patent_text_filter import build_filtered_text`，不要写成 `from tools.patent_text_filter`。若测试是 `from tools.input_trim import ...`，需确认 `tools/` 在 `sys.path`（现有 `test_input_trim.py` 已是 `from tools.input_trim import trim_input` 且通过，说明包导入可用）。为同时服务两种导入，在 `patent_text_filter` 导入处写成：

```python
try:
    from patent_text_filter import build_filtered_text
except ImportError:
    from tools.patent_text_filter import build_filtered_text
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_input_trim.py tests/test_patent_text_filter.py -v`

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=* add tools/input_trim.py tests/test_input_trim.py
git -c safe.directory=* commit -m "$(cat <<'EOF'
feat: 按 document_kind 分发文献/专利剪裁

EOF
)"
```

失败则跳过。

---

### Task 3: 覆盖层保存与新建项目

**Files:**
- Modify: `tools/config_model.py`（`save_overlay`、`create_project`）
- Test: `tests/test_config_model.py`

**Interfaces:**
- Consumes: `normalize_document_kind`
- Produces: 每个写入的 overlay 含规范化后的 `document_kind`；非法值 `save_overlay` 抛 `ValueError` 且不写盘

`save_overlay` 在现有 `steps` 校验**之前**执行：

```python
from input_trim import normalize_document_kind
# 若包导入失败则 try/except tools.input_trim，与 Task 2 相同
overlay["document_kind"] = normalize_document_kind(overlay.get("document_kind"))
```

`create_project` 的初始 `overlay = { ... }` 增加 `"document_kind": "paper"`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_config_model.py` 追加：

```python
def test_save_overlay_normalizes_and_rejects_document_kind(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    overlay = json.loads((ROOT / "configs/projects/demo_steel.json").read_text(encoding="utf-8"))
    overlay.pop("document_kind", None)
    (ws / "configs/projects/demo_steel.json").write_text(
        json.dumps(overlay, ensure_ascii=False), encoding="utf-8"
    )
    cm.save_overlay(ws, "demo_steel", overlay)
    saved = cm.load_overlay(ws, "demo_steel")
    assert saved["document_kind"] == "paper"

    overlay["document_kind"] = "patent"
    cm.save_overlay(ws, "demo_steel", overlay)
    assert cm.load_overlay(ws, "demo_steel")["document_kind"] == "patent"

    overlay["document_kind"] = "book"
    with pytest.raises(ValueError, match="非法 document_kind"):
        cm.save_overlay(ws, "demo_steel", overlay)
    assert cm.load_overlay(ws, "demo_steel")["document_kind"] == "patent"


def test_create_project_defaults_document_kind_paper(tmp_path: Path):
    ws = tmp_path
    for sub in ("configs/templates", "configs/field_library", "configs/projects"):
        (ws / sub).mkdir(parents=True)
    shutil.copy(ROOT / "configs/templates/steel.json", ws / "configs/templates/steel.json")
    shutil.copy(ROOT / "configs/field_library/steel.json", ws / "configs/field_library/steel.json")
    (ws / "configs/project_config.json").write_text(
        json.dumps({"default_project": "demo_steel", "projects": {}}), encoding="utf-8"
    )
    cm.create_project(ws, "mini2", "力学子集", "steel", ["title", "sample_id", "yield_strength"])
    overlay = cm.load_overlay(ws, "mini2")
    assert overlay["document_kind"] == "paper"
```

该文件已 `import pytest`。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_config_model.py::test_save_overlay_normalizes_and_rejects_document_kind tests/test_config_model.py::test_create_project_defaults_document_kind_paper -v`

Expected: FAIL（断言 `document_kind` 或未抛错）。

- [ ] **Step 3: 写最小实现**

`create_project` 的 overlay 字典增加一行 `"document_kind": "paper"`。

`save_overlay` 开头（写盘与 `validate_overlay_stages` 之前）：

```python
try:
    from input_trim import normalize_document_kind
except ImportError:
    from tools.input_trim import normalize_document_kind

overlay["document_kind"] = normalize_document_kind(overlay.get("document_kind"))
```

不要改 `project_config.json` 结构，不要回填仓库里已有的 `configs/projects/*.json`。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_config_model.py tests/test_input_trim.py tests/test_patent_text_filter.py -v`

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=* add tools/config_model.py tests/test_config_model.py
git -c safe.directory=* commit -m "$(cat <<'EOF'
feat: 覆盖层保存并校验 document_kind

EOF
)"
```

失败则跳过。

---

### Task 4: GET /api/projects 暴露 document_kind

**Files:**
- Modify: `tools/workbench_server.py`（`build_projects_payload`）
- Test: `tests/test_api_handlers.py`

**Interfaces:**
- Consumes: `config_model.load_overlay`、`normalize_document_kind`
- Produces: 每个项目对象多 `"document_kind": "paper" | "patent"`。覆盖层缺失/读失败/非法值时 payload 用 `"paper"`，**不要**让列表接口 500。

- [ ] **Step 1: 写失败测试**

在 `tests/test_api_handlers.py` 追加：

```python
def test_projects_payload_includes_document_kind():
    status, data = handle_get("/api/projects", {})
    assert status == 200
    demo = data["projects"]["demo_steel"]
    assert demo["document_kind"] == "paper"
    cuti = data["projects"]["cuti"]
    assert cuti["document_kind"] == "paper"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_api_handlers.py::test_projects_payload_includes_document_kind -v`

Expected: FAIL，`KeyError: 'document_kind'`。

- [ ] **Step 3: 写最小实现**

在 `build_projects_payload` 的循环里，构造 `projects[pid]` 时增加读取：

```python
try:
    from input_trim import normalize_document_kind
except ImportError:
    from tools.input_trim import normalize_document_kind

def _project_document_kind(project_id: str, cfg: dict) -> str:
    if not cfg.get("overlay"):
        return "paper"
    try:
        overlay = config_model.load_overlay(ROOT, project_id)
        return normalize_document_kind(overlay.get("document_kind"))
    except Exception:
        return "paper"
```

把 `_project_document_kind` 放在 `build_projects_payload` 上方。循环内：

```python
"document_kind": _project_document_kind(pid, cfg),
```

与现有 `name` / `runnable` 并列。不要改 PUT 状态码。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_api_handlers.py tests/test_config_model.py -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=* add tools/workbench_server.py tests/test_api_handlers.py
git -c safe.directory=* commit -m "$(cat <<'EOF'
feat: 项目列表 API 返回 document_kind

EOF
)"
```

失败则跳过。

---

### Task 5: pipeline 按项目类型剪裁

**Files:**
- Modify: `tools/pipeline.py`（import、`_prepare_run` 约 699 行、重抽约 1127 行）
- Test: `tests/test_pipeline_document_kind.py`（新建）

**Interfaces:**
- Consumes: `prepare_model_text`、`normalize_document_kind`
- Produces: `project_document_kind(root: Path, project_cfg: dict) -> str`；两处调用改为 `prepare_model_text(..., kind, paper_id=paper_id)`。源码中不再出现 `trim_input(`。

`project_document_kind`：

```python
def project_document_kind(root: Path, project_cfg: dict) -> str:
    overlay_rel = project_cfg.get("overlay")
    value = None
    if overlay_rel:
        overlay_path = Path(root) / overlay_rel
        if overlay_path.exists():
            value = json.loads(overlay_path.read_text(encoding="utf-8")).get("document_kind")
    return normalize_document_kind(value)
```

`_prepare_run` 替换：

```python
kind = project_document_kind(root, project_cfg)
trimmed_text, trim_stats = prepare_model_text(
    parsed.text_with_placeholders, kind, paper_id=paper_id
)
```

重抽分支在 `inputs/parsed_text.txt` 不存在时：

```python
raw = get_paper_text(root, project_cfg, paper_id) or ""
kind = project_document_kind(root, project_cfg)
trimmed_text, _ = prepare_model_text(raw, kind, paper_id=paper_id)
```

将 `from input_trim import trim_input` 改为 `from input_trim import prepare_model_text, normalize_document_kind`。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_pipeline_document_kind.py`：

```python
import json
from pathlib import Path

from tools.pipeline import project_document_kind

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_project_document_kind_defaults_paper(tmp_path: Path):
    overlay = {"template_id": "steel"}
    (tmp_path / "configs/projects").mkdir(parents=True)
    (tmp_path / "configs/projects/p.json").write_text(
        json.dumps(overlay), encoding="utf-8"
    )
    cfg = {"overlay": "configs/projects/p.json"}
    assert project_document_kind(tmp_path, cfg) == "paper"


def test_project_document_kind_reads_patent(tmp_path: Path):
    overlay = {"template_id": "steel", "document_kind": "patent"}
    (tmp_path / "configs/projects").mkdir(parents=True)
    (tmp_path / "configs/projects/p.json").write_text(
        json.dumps(overlay), encoding="utf-8"
    )
    cfg = {"overlay": "configs/projects/p.json"}
    assert project_document_kind(tmp_path, cfg) == "patent"


def test_pipeline_calls_prepare_model_text_not_trim_input():
    src = (ROOT / "tools/pipeline.py").read_text(encoding="utf-8")
    assert "prepare_model_text" in src
    assert "trim_input(" not in src
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_pipeline_document_kind.py -v`

Expected: FAIL，`project_document_kind` 未定义或源码仍有 `trim_input(`。

- [ ] **Step 3: 写最小实现**

按上面替换 import 与两处调用，新增 `project_document_kind`（放在 `load_field_config` 附近）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_pipeline_document_kind.py tests/test_run_step.py tests/test_input_trim.py -v`

Expected: PASS。`test_run_step.py` 仍走 `demo_steel`（缺省 paper），行为与改前一致。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=* add tools/pipeline.py tests/test_pipeline_document_kind.py
git -c safe.directory=* commit -m "$(cat <<'EOF'
feat: 抽取前按项目 document_kind 剪裁文本

EOF
)"
```

失败则跳过。

---

### Task 6: 配置页下拉与徽章

**Files:**
- Modify: `app/index.html`（抽取阶段卡片上方；项目标题旁；文献面板标题旁）
- Modify: `app/app.js`（草稿、保存、keepDraft、列表徽章）
- Modify: `app/styles.css`（`.kind-badge`，可复用 `.project-tag` 视觉）
- Test: `tests/test_workbench_config_status.py`

**Interfaces:**
- Consumes: overlay / projects 的 `document_kind`
- Produces: `#documentKind` 下拉；`#projectKindBadge`、`#papersKindBadge`；保存写入 `overlay.document_kind`；改下拉不 PUT

- [ ] **Step 1: 写失败测试**

在 `tests/test_workbench_config_status.py` 追加：

```python
def test_config_has_document_kind_select_above_stages():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    kind_idx = html.index('id="documentKind"')
    stage_idx = html.index(">抽取阶段<")
    assert kind_idx < stage_idx
    select = html[kind_idx:stage_idx]
    assert 'value="paper"' in select
    assert 'value="patent"' in select
    assert "学术文献" in html
    assert "专利" in html
    assert 'id="projectKindBadge"' in html
    assert 'id="papersKindBadge"' in html


def test_document_kind_stays_in_draft_until_save():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    start = js.index("async function saveConfigView")
    end = js.index("function renderFields", start)
    fn = js[start:end]
    assert "document_kind" in fn
    bind = js[js.index("function bindEvents"):]
    assert 'documentKind"' in bind or "documentKind" in bind
    hydrate = js[js.index("async function refreshProjectConfig"): js.index("function splitCsv")]
    assert "document_kind" in hydrate
    assert "kind-badge" in js or "projectKindBadge" in js
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_workbench_config_status.py::test_config_has_document_kind_select_above_stages tests/test_workbench_config_status.py::test_document_kind_stays_in_draft_until_save -v`

Expected: FAIL，`id="documentKind"` 不存在。

- [ ] **Step 3: 写最小实现**

`app/index.html` 在「抽取阶段」那个 `config-section` **之前**插入：

```html
            <div class="config-section">
              <div class="panel-title">
                <h3>文档类型</h3>
              </div>
              <p class="mode-hint">只影响送入模型前的文本剪裁，不改字段和阶段。专利会去掉摘要、技术领域、背景和权利要求，从实施方式/实施例起保留。</p>
              <label>文档类型
                <select id="documentKind">
                  <option value="paper">学术文献</option>
                  <option value="patent">专利</option>
                </select>
              </label>
            </div>
```

项目 intro 的 `h2#projectTitle` 旁加 `<span id="projectKindBadge" class="kind-badge">文献</span>`。

文献面板 `h3`「文献」旁加 `<span id="papersKindBadge" class="kind-badge">文献</span>`。

`app/styles.css` 追加：

```css
.kind-badge {
  font-size: 11px;
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 2px 6px;
  white-space: nowrap;
}
.project-intro-title,
.project-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
```

给包着 `projectTitle` 的 `div` 加 class `project-title-row`（不要只靠 CSS 把整个 intro 变成 flex 以致描述错位）。

`app/app.js`：

1. `refreshProjectConfig` 的 `keepDraft` 增加保存/恢复 `state.overlay.document_kind`（与 `selected_field_ids` 相同写法）。
2. `loadConfigEditor` 每次结尾调用 `fillDocumentKindSelect()`：
```javascript
  function fillDocumentKindSelect() {
    const sel = $("documentKind");
    if (!sel) return;
    const kind = state.overlay && state.overlay.document_kind === "patent" ? "patent" : "paper";
    sel.value = kind;
  }

  function documentKindLabel(kind) {
    return kind === "patent" ? "专利" : "文献";
  }

  function renderDocumentKindBadges() {
    const kind = (state.overlay && state.overlay.document_kind)
      || (state.project && state.project.document_kind)
      || "paper";
    const label = documentKindLabel(kind);
    if ($("projectKindBadge")) $("projectKindBadge").textContent = label;
    if ($("papersKindBadge")) $("papersKindBadge").textContent = label;
  }
```
3. `saveConfigView` 在 PUT 前：`state.overlay.document_kind = ($("documentKind") && $("documentKind").value) || "paper";` 日志可改为 `保存配置（字段 / 阶段 / 策略 / 文档类型）`。
4. `renderProjectList`：
```javascript
      const kind = p.document_kind === "patent" ? "专利" : "文献";
      el.innerHTML =
        `<span class="project-name">${esc(p.name)}</span><span class="kind-badge">${kind}</span>`;
```
5. `selectProject` 在 `loadOverlayAndLibrary` 之后调用 `renderDocumentKindBadges()`。
6. `bindEvents`：
```javascript
    if ($("documentKind")) {
      $("documentKind").addEventListener("change", () => {
        if (!state.overlay) return;
        state.overlay.document_kind = $("documentKind").value;
        setConfigStatus("已更新草稿，保存配置后生效。", "running");
      });
    }
```
改下拉处禁止调用 `saveOverlay`。

7. `refreshProjectConfig` 末尾（`loadConfigEditor()` 之后）再调 `renderDocumentKindBadges()` 与 `renderProjectList()`，保存后徽章能更新。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_workbench_config_status.py tests/test_api_handlers.py tests/test_pipeline_document_kind.py tests/test_input_trim.py tests/test_patent_text_filter.py tests/test_config_model.py -q`

再跑全量：`python3 -m pytest -q`

Expected: 全绿。

手工（实现者本机若有工作台）：配置页改成专利 → 不保存刷新复原为文献 → 保存后再进仍是专利；项目列表与文献页徽章变为「专利」。整篇再跑才换剪裁。

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=* add app/index.html app/app.js app/styles.css tests/test_workbench_config_status.py
git -c safe.directory=* commit -m "$(cat <<'EOF'
feat: 配置页选择文献或专利文档类型

EOF
)"
```

失败则跳过。

---

## 规格对照

| 规格条款 | 任务 |
| --- | --- |
| overlay `document_kind` paper/patent，缺省 paper | Task 3 |
| 非法值保存报错不写盘 | Task 3 |
| create_project 默认 paper；不回填旧项目 | Task 3 |
| GET /api/projects 带字段 | Task 4 |
| 配置页下拉，随保存落盘，进草稿 | Task 6 |
| 项目列表 / 文献页徽章 | Task 6 |
| paper → trim_input；patent → core_text；互斥 | Task 1–2 |
| `_prepare_run` + 重抽无 parsed_text 时分发 | Task 5 |
| 迁入探针规则，不依赖 Extract_data，不用 figure_text | Task 1 |
| paper.md 不改；改类型后整篇再生效 | Task 5（重抽沿用 parsed_text.txt） |
| 测试：文献砍参考文献；专利留实施例 | Task 1–2 |
