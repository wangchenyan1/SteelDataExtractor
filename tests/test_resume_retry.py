import json
from pathlib import Path

import pytest

from tools.pipeline import (
    STEP_LLM_MAX_ATTEMPTS,
    _call_backend_json,
    _run_skeleton_done,
    find_resumable_run,
    run_extraction,
)

ROOT = Path(__file__).resolve().parents[1]


class _CountingBackend:
    name = "fake"

    def __init__(self, fail_times: int, ok: dict):
        self.fail_times = fail_times
        self.ok = ok
        self.calls = 0

    def call_json(self, system_prompt, text_prompt, images=None, hint=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"boom-{self.calls}")
        return self.ok


def test_property_call_retries_then_succeeds(tmp_path):
    be = _CountingBackend(2, {"properties": []})
    state = {"backend": be, "run_dir": tmp_path}
    out = _call_backend_json(
        state, "sys", "user", None, {"stage": "property", "step_id": "mechanical"}
    )
    assert out == {"properties": []}
    assert be.calls == 3
    assert STEP_LLM_MAX_ATTEMPTS == 5


def test_property_call_gives_up_after_max_attempts(tmp_path):
    be = _CountingBackend(10, {"properties": []})
    state = {"backend": be, "run_dir": tmp_path}
    with pytest.raises(RuntimeError, match="boom-5"):
        _call_backend_json(
            state, "sys", "user", None, {"stage": "property", "step_id": "mechanical"}
        )
    assert be.calls == 5


def test_entity_call_does_not_retry(tmp_path):
    be = _CountingBackend(1, {"samples": []})
    state = {"backend": be, "run_dir": tmp_path}
    with pytest.raises(RuntimeError, match="boom-1"):
        _call_backend_json(
            state, "sys", "user", None, {"stage": "entity", "step_id": "entity"}
        )
    assert be.calls == 1


def test_find_resumable_run_requires_failed_with_skeleton(tmp_path):
    paper_id = "p_resume"
    run_id = "20260904_100000_two_stage_claude-4.5-sonnet"
    rd = tmp_path / "test" / run_id
    (rd / "entities").mkdir(parents=True)
    (rd / "entities" / "entity.json").write_text(
        json.dumps({"samples": [{"sample_id": "S1"}], "conditions": []}),
        encoding="utf-8",
    )
    (rd / "RUN_INFO.json").write_text(
        json.dumps({
            "run_id": run_id,
            "paper_id": paper_id,
            "mode": "two_stage",
            "partition": "test",
            "status": "failed",
            "completed_steps": ["entity"],
            "model_id": "claude-4.5-sonnet",
        }),
        encoding="utf-8",
    )
    cfg = {"test_runs": str(tmp_path)}
    found = find_resumable_run(
        ROOT, cfg, paper_id,
        mode="two_stage", partition="test", model_id="claude-4.5-sonnet",
    )
    assert found == run_id
    assert find_resumable_run(
        ROOT, cfg, paper_id,
        mode="two_stage", partition="test", model_id="gpt-5.2",
    ) is None


def test_run_extraction_resumes_after_entity(tmp_path, monkeypatch):
    from tools import pipeline as pl

    paper_id = "demo_steel_2024"
    cfg = pl.load_workspace_config(ROOT)["projects"]["demo_steel"]
    monkeypatch.setitem(cfg, "test_runs", str(tmp_path))
    orig_load = pl.load_workspace_config

    def _ws(root):
        ws = orig_load(root)
        ws["projects"]["demo_steel"]["test_runs"] = str(tmp_path)
        return ws

    monkeypatch.setattr(pl, "load_workspace_config", _ws)

    class _SeqBackend:
        name = "fake"

        def __init__(self):
            self.calls = []
            self.property_fails_left = STEP_LLM_MAX_ATTEMPTS

        def call_json(self, system_prompt, text_prompt, images=None, hint=None):
            stage = (hint or {}).get("stage")
            self.calls.append(stage)
            if stage == "entity":
                return {
                    "paper_metadata": {},
                    "samples": [{"sample_id": "S1", "sample_name": {"value": "A"}}],
                    "conditions": [{"condition_id": "C1", "sample_id": "S1"}],
                }
            if stage == "property":
                if self.property_fails_left > 0:
                    self.property_fails_left -= 1
                    raise RuntimeError("property down")
                return {"properties": [{"condition_id": "C1"}]}
            if stage == "figure_extract":
                return {"figures": []}
            return {}

    be = _SeqBackend()
    monkeypatch.setattr(pl, "get_backend", lambda name, root, **kwargs: be)

    with pytest.raises(RuntimeError, match="property down"):
        run_extraction(ROOT, "demo_steel", paper_id, mode="two_stage", model_id="claude-4.5-sonnet")
    assert be.calls.count("entity") == 1
    assert be.calls.count("property") == STEP_LLM_MAX_ATTEMPTS

    be.calls.clear()
    out = run_extraction(ROOT, "demo_steel", paper_id, mode="two_stage", model_id="claude-4.5-sonnet")
    assert out.get("resumed") is True
    assert "entity" not in be.calls
    assert be.calls.count("property") >= 1
    info = json.loads((tmp_path / "test" / out["run_id"] / "RUN_INFO.json").read_text(encoding="utf-8"))
    assert info["status"] == "success"


def test_run_skeleton_done_from_steps_or_files(tmp_path):
    assert _run_skeleton_done({"completed_steps": ["entity"]}, tmp_path) is True
    assert _run_skeleton_done({"completed_steps": []}, tmp_path) is False
    ent = tmp_path / "entities"
    ent.mkdir()
    (ent / "entity.json").write_text("{}", encoding="utf-8")
    assert _run_skeleton_done({"completed_steps": []}, tmp_path) is True
