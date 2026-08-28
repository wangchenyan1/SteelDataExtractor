# Task 7 Report: PDF 解析包装（假 client 可测）

## RED

Created `tests/test_pdf_parser.py`（FakeClient 写出 md+图；已有 md 跳过；空 content 不写 paper.md）.

```
$ python3 -m pytest tests/test_pdf_parser.py -v
ERROR collecting tests/test_pdf_parser.py
ImportError: No module named 'tools.pdf_parser'
```

## GREEN

Changed:

- `tools/pdf_parser.py`：移植 `IMAGE_PATTERN` / `image_extension` / `save_base64_images`；`parse_pdf_to_paper` 写 `paper.md`、`images_from_md/`、`uniparser_submit_result.json`；`client is None` 时才建 `UniParserClient`（`UNIPARSER_API_KEY` / `UP_API_KEY`）；无硬编码 CuTi / Extract_data 路径
- `tests/test_pdf_parser.py`：按 brief 契约

```
$ python3 -m pytest tests/test_pdf_parser.py -v
3 passed

$ python3 -m pytest tests -q
26 passed
```

## Notes

- Skip git（按任务说明）.
- 调用方负责复制 `source.pdf`；本模块不写.
- 注入 FakeClient 时仍会 import `uniparser_tools` 常量以对齐真实 trigger/get_formatted flags.
