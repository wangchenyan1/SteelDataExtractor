### Task 7: PDF 解析包装（假 client 可测）

**Files:**
- Create: `tools/pdf_parser.py`
- Create: `tests/test_pdf_parser.py`

**Interfaces:**
- Consumes: 规格 5.6；逻辑对齐 `/internfs/wangchenyan/shougang/scripts/parsing/parser.py` 的 `save_base64_images` / `parse_one_pdf`，**禁止 import 那份脚本，禁止默认路径指向 Extract_data**
- Produces:
  - `parse_pdf_to_paper(pdf_path: Path, output_dir: Path, *, client=None, overwrite: bool=False, host: str | None=None, api_key: str | None=None) -> dict`
  - `output_dir` 为 `<parsed_results>/<paper_id>/` 的父目录，paper_id = `pdf_path.stem`
  - 写出 `paper.md`、`images_from_md/`、`uniparser_submit_result.json`；调用方负责把原 PDF 复制为 `source.pdf`
  - 已有 `paper.md` 且 `overwrite=False` → `{status:"skipped"}`
  - `content` 空 → raise，不写空 md
  - 无 key 且未注入 client → `RuntimeError` 文案含 `UNIPARSER_API_KEY`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pdf_parser.py
from pathlib import Path
import json
from tools.pdf_parser import parse_pdf_to_paper, save_base64_images

class FakeClient:
    def trigger_file(self, **kwargs):
        return {"token": "t1"}
    def get_formatted(self, token, **kwargs):
        md = "hello\n\n![figure](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==)\n"
        return {"content": md}


def test_writes_md_and_image(tmp_path: Path):
    pdf = tmp_path / "p1.pdf"
    pdf.write_bytes(b"%PDF-fake")
    out = tmp_path / "parsed"
    result = parse_pdf_to_paper(pdf, out, client=FakeClient())
    paper_dir = out / "p1"
    assert (paper_dir / "paper.md").exists()
    assert "images_from_md/" in (paper_dir / "paper.md").read_text()
    assert list((paper_dir / "images_from_md").glob("*"))
    assert result["status"] == "success"


def test_skip_existing(tmp_path: Path):
    pdf = tmp_path / "p1.pdf"
    pdf.write_bytes(b"%PDF-fake")
    paper_dir = tmp_path / "parsed" / "p1"
    paper_dir.mkdir(parents=True)
    (paper_dir / "paper.md").write_text("old", encoding="utf-8")
    result = parse_pdf_to_paper(pdf, tmp_path / "parsed", client=FakeClient(), overwrite=False)
    assert result["status"] == "skipped"
    assert (paper_dir / "paper.md").read_text() == "old"


def test_empty_content_does_not_write(tmp_path: Path):
    class Empty:
        def trigger_file(self, **kwargs):
            return {"token": "t"}
        def get_formatted(self, token, **kwargs):
            return {"content": ""}
    pdf = tmp_path / "p1.pdf"
    pdf.write_bytes(b"%PDF")
    try:
        parse_pdf_to_paper(pdf, tmp_path / "parsed", client=Empty())
        assert False
    except RuntimeError:
        pass
    assert not (tmp_path / "parsed" / "p1" / "paper.md").exists()
```

- [ ] **Step 2: Run, expect FAIL**

- [ ] **Step 3: Implement `tools/pdf_parser.py`**

从 `scripts/parsing/parser.py` 拷 `IMAGE_PATTERN`、`save_base64_images`、`image_extension`。真实 client 仅当 `client is None` 时 `UniParserClient(host=..., api_key=get_api_key())`。`get_api_key` 读 `UNIPARSER_API_KEY` 或 `UP_API_KEY`。不要写死 CuTi 路径。

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit** `feat: wrap UniParser PDF parsing into the workbench`

---

