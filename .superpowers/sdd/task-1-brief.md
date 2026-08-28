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

