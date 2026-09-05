from pathlib import Path
import json

from tools.result_analysis import (
    slice_result_for_analysis,
    postprocess_analysis,
    build_analyze_prompt,
    filter_diff_for_analysis,
    run_analysis,
    list_analyses_under_runs,
    find_analysis,
    resolve_analyze_scope,
)
from tools.workbench_server import handle_get, handle_post

ROOT = Path(__file__).resolve().parents[1]


def _sample_result():
    return {
        "samples": [{
            "sample_id": "S1",
            "composition": {"value": "C 0.1"},
            "sample_processing_overview": {"value": "aged 450C"},
        }],
        "conditions": [{
            "condition_id": "C1",
            "sample_id": "S1",
            "mechanical_properties": {
                "yield_strength": {"value": "500", "unit": "MPa"}
            },
            "condition_name": {"value": "ST+CR"},
        }],
        "figures": [{
            "figure_id": "Fig1",
            "figure_type": {"value": "OM"},
            "is_microstructure_image": True,
            "is_post_test_image": False,
            "caption": {"value": "microstructure"},
            "extra_noise": "x" * 100,
        }],
    }


def _write_run(runs_root: Path, run_id: str, paper_id: str, mode: str, result: dict, text="Table 1 C 0.1"):
    rd = runs_root / "test" / run_id
    (rd / "merged_outputs").mkdir(parents=True)
    (rd / "inputs").mkdir(parents=True)
    (rd / "merged_outputs" / "paper.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    (rd / "inputs" / "parsed_text.txt").write_text(text, encoding="utf-8")
    (rd / "RUN_INFO.json").write_text(
        json.dumps({
            "run_id": run_id,
            "paper_id": paper_id,
            "mode": mode,
            "partition": "test",
            "status": "success",
            "backend": "claude",
        }),
        encoding="utf-8",
    )
    return rd


def test_slice_keeps_three_foci():
    sliced = slice_result_for_analysis(_sample_result())
    assert "value_binding" in sliced
    assert sliced["value_binding"]["samples"][0]["composition"]["value"] == "C 0.1"
    assert "yield_strength" in sliced["value_binding"]["conditions"][0]["mechanical_properties"]
    assert sliced["process_binding"]["samples"][0]["sample_processing_overview"]["value"] == "aged 450C"
    figs = sliced["figure_judgment"]["figures"]
    assert figs[0]["figure_id"] == "Fig1"
    assert "extra_noise" not in figs[0]


def test_postprocess_caps_and_requires_focus():
    raw = {
        "summary": "x" * 100,
        "issues": [
            {"severity": "low", "focus": "value_binding", "title": "a", "detail": "d", "suggestion": "s"},
            {"severity": "high", "focus": "figure_judgment", "title": "b", "detail": "d", "suggestion": "s"},
            {"severity": "high", "focus": "nope", "title": "drop", "detail": "d", "suggestion": "s"},
        ] + [
            {"severity": "medium", "focus": "process_binding", "title": f"t{i}", "detail": "d", "suggestion": "s"}
            for i in range(15)
        ],
    }
    out = postprocess_analysis(raw, "vs_source")
    assert len(out["summary"]) <= 80
    assert len(out["issues"]) <= 12
    assert out["issues"][0]["focus"] == "figure_judgment"
    assert all(i["focus"] in ("value_binding", "process_binding", "figure_judgment") for i in out["issues"])


def test_prompt_mentions_three_foci():
    system, user = build_analyze_prompt("vs_source", sliced={}, source_text="hello")
    assert "value_binding" in system
    assert "process_binding" in system
    assert "figure_judgment" in system
    assert "最多12" in system.replace(" ", "")
    assert "vs_source" in user


def test_prompt_respects_selected_and_custom_focus():
    system, user = build_analyze_prompt(
        "vs_source",
        sliced={},
        source_text="hello",
        focuses=["figure_judgment"],
        custom_focus="只看断后图有没有标错",
    )
    assert "figure_judgment" in system
    assert "process_binding" not in system
    assert "只看断后图" in system
    assert "custom" in user
    try:
        resolve_analyze_scope([], "")
        assert False, "should raise"
    except ValueError:
        pass


def test_slice_filters_to_selected_focus():
    sliced = slice_result_for_analysis(_sample_result(), ["figure_judgment"])
    assert list(sliced.keys()) == ["figure_judgment"]


def test_filter_diff_keeps_relevant_paths():
    rows = [
        {"path": "samples[S1].composition", "a": "1", "b": "2", "changed": True},
        {"path": "paper_metadata.doi", "a": "x", "b": "y", "changed": True},
        {"path": "figures[Fig1].is_microstructure_image", "a": "yes", "b": "no", "changed": True},
    ]
    filtered = filter_diff_for_analysis(rows)
    paths = {r["path"] for r in filtered}
    assert "samples[S1].composition" in paths
    assert "figures[Fig1].is_microstructure_image" in paths
    assert "paper_metadata.doi" not in paths


def test_run_analysis_vs_source_with_mock(tmp_path):
    paper_id = "p_analyze"
    runs = tmp_path / "runs"
    _write_run(runs, "run_a", paper_id, "two_stage", _sample_result())
    cfg = {"test_runs": str(runs), "backend": "claude"}

    def fake_call(system, user):
        return {
            "summary": "数值绑定1处高风险",
            "issues": [{
                "severity": "high",
                "focus": "value_binding",
                "category": "wrong_binding",
                "path": "samples[S1].composition",
                "title": "成分挂接可疑",
                "detail": "与 Table 1 不一致",
                "suggestion": "核对样品",
            }],
        }

    out = run_analysis(
        root=ROOT,
        project_cfg=cfg,
        project_id="demo_steel",
        paper_id=paper_id,
        analysis_type="vs_source",
        call_json=fake_call,
    )
    assert out["ok"] is True
    assert out["analysis"]["issues"][0]["focus"] == "value_binding"
    p = Path(out["path"])
    assert p.exists()
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["status"] == "success"
    listed = list_analyses_under_runs([p.parent.parent])
    assert listed[0]["analysis_id"] == out["analysis_id"]
    found = find_analysis([p.parent.parent], out["analysis_id"])
    assert found["issues"][0]["title"] == "成分挂接可疑"


def test_run_analysis_vs_runs_with_mock(tmp_path):
    paper_id = "p_compare"
    runs = tmp_path / "runs"
    a = _sample_result()
    b = _sample_result()
    b["samples"][0]["composition"] = {"value": "C 0.3"}
    _write_run(runs, "run_a", paper_id, "two_stage", a)
    _write_run(runs, "run_b", paper_id, "single_pass", b)
    cfg = {"test_runs": str(runs), "backend": "claude"}

    def fake_call(system, user):
        assert "diff_rows" in user
        return {
            "summary": "成分数值不一致",
            "issues": [{
                "severity": "high",
                "focus": "value_binding",
                "category": "method_diff",
                "path": "samples[S1].composition",
                "title": "成分不同",
                "detail": "A 与 B 成分值不同",
                "suggestion": "以原文表格为准",
            }],
        }

    out = run_analysis(
        root=ROOT,
        project_cfg=cfg,
        project_id="demo_steel",
        paper_id=paper_id,
        analysis_type="vs_runs",
        run_id_a="run_a",
        run_id_b="run_b",
        call_json=fake_call,
    )
    assert out["ok"] is True
    assert out["analysis"]["inputs"]["run_id_a"] == "run_a"
    assert Path(out["path"]).parent.name == "analysis"


def test_analyze_api_missing_params():
    status, data = handle_post("/api/analyze", {})
    assert status == 400
    status, data = handle_post("/api/analyze", {
        "project": "demo_steel",
        "paper_id": "x",
        "analysis_type": "nope",
    })
    assert status == 400
    status, data = handle_post("/api/analyze", {
        "project": "demo_steel",
        "paper_id": "x",
        "analysis_type": "vs_runs",
    })
    assert status == 400
    status, data = handle_get("/api/analyze_list", {})
    assert status == 400
    status, data = handle_get("/api/analyze", {
        "project": ["demo_steel"],
        "paper_id": ["x"],
    })
    assert status == 400


def test_analyze_api_not_found():
    status, data = handle_post("/api/analyze", {
        "project": "demo_steel",
        "paper_id": "no_such_paper_xyz",
        "analysis_type": "vs_source",
    })
    assert status == 404
    status, data = handle_get("/api/analyze", {
        "project": ["demo_steel"],
        "paper_id": ["10.1007_s11665-019-04233-6"],
        "analysis_id": ["no_such_analysis"],
    })
    assert status == 404


def test_analyze_api_post_ok(monkeypatch):
    import tools.workbench_server as wb

    def fake(**kwargs):
        return {
            "ok": True,
            "analysis_id": "fake_vs_source",
            "path": "/tmp/x.json",
            "analysis": {
                "analysis_id": "fake_vs_source",
                "analysis_type": "vs_source",
                "summary": "未发现上述三类硬问题",
                "issues": [],
            },
        }

    monkeypatch.setattr(wb.result_analysis, "run_analysis", fake)
    status, data = handle_post("/api/analyze", {
        "project": "demo_steel",
        "paper_id": "p",
        "analysis_type": "vs_source",
    })
    assert status == 200
    assert data["ok"] is True
    assert data["analysis"]["issues"] == []


def test_analyze_panel_in_review():
    html = (ROOT / "app/index.html").read_text(encoding="utf-8")
    start = html.index('data-view-panel="review"')
    block = html[start: start + 5500]
    assert 'id="analyzeType"' in block
    assert 'id="btnStartAnalyze"' in block
    assert 'id="analyzeHistory"' in block
    assert 'id="analyzePanel"' in block
    assert 'value="vs_source"' in block
    assert 'value="vs_runs"' in block
    assert 'id="analyzeCustomFocus"' in block
    assert "analyze-focus" in block
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "async function startAnalyze" in js
    assert "function collectAnalyzeScope" in js
    assert "custom_focus" in js
    assert "value_binding" in js
    assert "process_binding" in js
    assert "figure_judgment" in js
