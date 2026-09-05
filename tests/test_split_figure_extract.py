# -*- coding: utf-8 -*-
import json
from pathlib import Path

from tools.llm_backends import (
    ENTITY_MAX_TOKENS,
    LLMCallError,
    resolve_max_tokens,
)
from tools.pipeline import (
    build_entity_prompt,
    build_figure_extract_prompt,
    dump_llm_failure,
    get_steps,
    _merge_figure_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def _demo_field_config():
    from tools.pipeline import load_workspace_config, load_field_config
    ws = load_workspace_config(ROOT)
    return load_field_config(ROOT, ws["projects"]["demo_steel"])


def test_entity_prompt_has_no_figures_schema():
    fc = _demo_field_config()
    prompt = build_entity_prompt(fc, "body text")
    assert '"figures"' not in prompt
    assert "figure_id" not in prompt
    assert "figures" in prompt  # prose says figures are handled elsewhere


def test_get_steps_injects_figure_extract_when_figure_fields():
    fc = _demo_field_config()
    steps = get_steps(fc)
    types = [s.get("type") for s in steps]
    assert "entity" in types
    assert "figure_extract" in types
    assert "figure" not in types
    assert types.index("entity") == 0
    assert types.index("figure_extract") == len(types) - 1


def test_figure_extract_prompt_includes_skeleton_and_batch():
    fc = _demo_field_config()
    entity = {
        "samples": [{"sample_id": "S1", "sample_name": {"value": "A"}}],
        "conditions": [{"condition_id": "C1", "sample_id": "S1"}],
    }
    prompt = build_figure_extract_prompt(fc, "body", entity, ["Figure 1", "Figure 2"])
    assert '"figures"' in prompt
    assert "S1" in prompt
    assert "Figure 1" in prompt
    assert "placeholder_index" in prompt


def test_resolve_max_tokens_entity_and_figure_extract():
    assert resolve_max_tokens({"stage": "entity"}) == ENTITY_MAX_TOKENS
    assert resolve_max_tokens({"stage": "figure_extract"}) == ENTITY_MAX_TOKENS
    assert resolve_max_tokens({"stage": "property"}) == 16384
    assert resolve_max_tokens({"stage": "entity", "max_tokens": 1000}) == 1000


def test_dump_llm_failure_writes_raw_and_meta(tmp_path: Path):
    exc = LLMCallError(
        "cannot parse LLM output as JSON: {",
        raw_text='{"paper_metadata": truncated',
        stop_reason="max_tokens",
        http_status=200,
    )
    written = dump_llm_failure(tmp_path, "entity", exc)
    assert Path(written["raw"]).exists()
    assert "truncated" in Path(written["raw"]).read_text(encoding="utf-8")
    meta = json.loads(Path(written["meta"]).read_text(encoding="utf-8"))
    assert meta["stop_reason"] == "max_tokens"


def test_merge_figure_rows_dedupes():
    merged = _merge_figure_rows([
        [{"figure_id": "F1", "caption": {"value": "a"}}],
        [{"figure_id": "F1", "caption": {"value": "b"}}, {"figure_id": "F2"}],
    ])
    assert len(merged) == 2
    assert merged[0]["caption"]["value"] == "b"
