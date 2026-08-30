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
