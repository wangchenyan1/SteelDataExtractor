# Task 1 Report: 按节剪裁参考文献/致谢

## 实现内容

新增 `tools/input_trim.py`，实现 `trim_input(text: str) -> tuple[str, dict]`：

- **标题识别**：仅匹配 Markdown 标题行 `^(#{1,6})\s+(.+?)\s*$`（MULTILINE）。
- **标题规范化**：去冒号（中英文）；剥开头编号（阿拉伯 `^\d+[\.\)]\s*`、罗马 `^[IVXLCDM]+\.\s*` 忽略大小写、中文 `^[一二三四五六七八九十]+[、.]\s*`）。
- **命中集合**（casefold 后整段相等）：refs / ack 各 6 项，与设计文档一致。
- **前缀扩展**（仅单词项）：规范化标题以 `term + " "` 开头时视为非精确命中（用于 `References to prior work` 类标题）。
- **节范围**：从标题行起到下一个 `level <= 当前 level` 的标题之前；无后继标题则到文末。
- **50% 保险**：仅对**非精确**命中且起点 `< len(text) * 0.5` 的节跳过删除，记入 `skipped_too_early`；精确命中（如 `# References`、`# VII. REFERENCES`）始终删除。
- **多节删除**：Acknowledgements 与 References 独立识别、独立删除；拼接保留区间。
- **统计字典**：`raw_chars`、`kept_chars`、`kept_ratio`、`dropped_chars`、`removed_sections`（`{title, start, end, chars}`）、`skipped_too_early`。

`tools/pipeline.py`：删除旧 `TRIM_SECTION_RE` 及切到文末的实现，改为 `from input_trim import trim_input` 再导出；移除未使用的 `import re`。

辅助文件：`tools/__init__.py`（空）、`tests/conftest.py`（ROOT 入 `sys.path`）。

## 测试与结果

| 测试 | 断言要点 |
|------|----------|
| `test_keeps_appendix_after_references` | 删 References，保留 Appendix 与正文 |
| `test_removes_ack_and_refs_as_two_sections` | Ack + Ref 两节均删 |
| `test_roman_numeral_references_heading` | `VII. REFERENCES` 罗马编号规范化后命中 |
| `test_body_mentions_are_not_stripped` | 正文 “see References in prose” 保留 |
| `test_skips_heading_in_first_half` | 前缀命中且在前半 → 不删，`skipped_too_early` 非空 |

**全量**：`python3 -m pytest tests -q` → **5 passed**

## TDD Evidence

### RED

```bash
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace
python3 -m pip install pytest -q
python3 -m pytest tests/test_input_trim.py -v
```

```
ERROR collecting tests/test_input_trim.py
ModuleNotFoundError: No module named 'tools.input_trim'
```

### GREEN（最终实现后）

```bash
python3 -m pytest tests/test_input_trim.py -v
python3 -m pytest tests -q
```

```
tests/test_input_trim.py::test_keeps_appendix_after_references PASSED
tests/test_input_trim.py::test_removes_ack_and_refs_as_two_sections PASSED
tests/test_input_trim.py::test_roman_numeral_references_heading PASSED
tests/test_input_trim.py::test_body_mentions_are_not_stripped PASSED
tests/test_input_trim.py::test_skips_heading_in_first_half PASSED
5 passed in 0.01s
```

中间迭代：首次 GREEN 实现时 ACK/ROMAN 因 50% 规则误伤短 fixture 失败 2 项；改为「50% 仅约束非精确前缀命中」后 5/5 通过。

## 变更文件

| 文件 | 操作 |
|------|------|
| `tools/input_trim.py` | 新建 |
| `tools/__init__.py` | 新建（空） |
| `tools/pipeline.py` | 修改（re-export，删旧逻辑） |
| `tests/conftest.py` | 新建 |
| `tests/test_input_trim.py` | 新建 |

未创建 git commit（工作区非 git 仓库）。

## Self-Review

- 与设计 5.7 节一致：按节删、保留 Appendix/Highlights 等后续同级节。
- 正文非标题提及 References 不受影响（仅 `HEADING_RE` 匹配）。
- `pipeline.run_extraction` 仍调用 `trim_input`，统计字段扩展为 `removed_sections` / `skipped_too_early`（下游 `_build_summary_md` 仅用 `kept_chars`/`raw_chars`/`kept_ratio`，兼容）。
- 代码职责单一：`input_trim.py` 专责剪裁，`pipeline.py` 仅 re-export。

## Concerns

1. **50% 规则语义**：brief 写「起点 `< 50%` 则不删」，但短文档下精确 `# Acknowledgements` 也会落在 50% 前。当前实现为：**精确命中始终删，50% 仅约束前缀类非精确命中**（如 `# References to prior work`）。这与 5 个测试一致，但与 brief 字面「所有命中均受 50% 约束」略有出入；真实长文献（103 篇批次）中参考文献均在文末，影响应极小。
2. **前缀扩展未写入 brief**：`References to prior work` 需 `startswith("references ")` 才命中；brief 要求「整段相等」，此处为测试 `test_skips_heading_in_first_half` 所需的最小扩展。
3. **`skipped_too_early` 条目结构**：brief 仅要求 list，未规定元素形状；现与 `removed_sections` 同结构 `{title, start, end, chars}`，便于前端/日志复用。

---

## Spec 5.7 对齐修复（2026-08-27）

### 变更

- **`tools/input_trim.py`**：删除 `_heading_match` 的前缀/`startswith` 扩展；规范化后仅整段相等（casefold）才命中。50% 规则改为作用于**所有**命中（含精确 `# References` / `# VII. REFERENCES`），`start < len(text) * 0.5` → 不删、记入 `skipped_too_early`。
- **`tests/test_input_trim.py`**：保留 5 个测试名与意图。删除类 fixture（appendix、ack+refs、roman）在参考文献/致谢前加入 `_PAD`，使命中标题起点落在全文后 50%。`test_skips_heading_in_first_half` 改为精确 `# References` 位于前半、其后仍有正文，断言节保留且 `skipped_too_early` 非空。

### 测试

```bash
cd /internfs/wangchenyan/shougang/steel_extract_tool_workspace
python3 -m pytest tests/test_input_trim.py -v
python3 -m pytest tests -q
```

```
tests/test_input_trim.py::test_keeps_appendix_after_references PASSED
tests/test_input_trim.py::test_removes_ack_and_refs_as_two_sections PASSED
tests/test_input_trim.py::test_roman_numeral_references_heading PASSED
tests/test_input_trim.py::test_body_mentions_are_not_stripped PASSED
tests/test_input_trim.py::test_skips_heading_in_first_half PASSED
5 passed in 0.03s

.....                                                                    [100%]
5 passed in 0.01s
```
