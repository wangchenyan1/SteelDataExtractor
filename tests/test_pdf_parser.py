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
