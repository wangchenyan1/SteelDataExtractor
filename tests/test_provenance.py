from tools.provenance import find_excerpt_span, value_shape, is_identity_field
from tools.config_model import load_template
from pathlib import Path

ROOT = Path("/internfs/wangchenyan/shougang/steel_extract_tool_workspace")


def test_find_excerpt_ignores_whitespace():
    text = "The yield strength of A-700 is 685 MPa"
    span = find_excerpt_span(text, "yield strength of A-700 is 685 MPa")
    assert span is not None
    start, end = span
    assert "685 MPa" in text[start:end]


def test_find_excerpt_missing():
    assert find_excerpt_span("hello", "not here") is None


def test_identity_not_wrapped():
    tmpl = load_template(ROOT, "steel")
    assert is_identity_field(tmpl, {"id": "sample_id", "category": "sample"})
    assert is_identity_field(tmpl, {"id": "sample_id", "category": "condition"})
    assert not is_identity_field(tmpl, {"id": "title", "category": "metadata"})


def test_property_shape_has_source():
    shape = value_shape({"id": "yield_strength", "category": "property", "value_type": "number_with_unit"})
    assert set(shape) >= {"value", "unit", "excerpt", "location", "source"}
