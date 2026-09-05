# -*- coding: utf-8 -*-
from tools.pipeline import build_run_id, run_id_model_slug


def test_run_id_model_slug_sanitizes():
    assert run_id_model_slug("claude-4.5-sonnet") == "claude-4.5-sonnet"
    assert run_id_model_slug("Vendor2/Claude") == "Vendor2-Claude"
    assert run_id_model_slug(None) == "default"
    assert run_id_model_slug("") == "default"


def test_build_run_id_includes_model():
    rid = build_run_id("two_stage", "claude-4.5-sonnet", stamp="20260903_152819")
    assert rid == "20260903_152819_two_stage_claude-4.5-sonnet"


def test_build_run_id_avoids_collision():
    existing = {"20260903_152819_two_stage_claude-4.5-sonnet"}
    rid = build_run_id(
        "two_stage",
        "claude-4.5-sonnet",
        stamp="20260903_152819",
        existing=existing,
    )
    assert rid == "20260903_152819_two_stage_claude-4.5-sonnet_1"
