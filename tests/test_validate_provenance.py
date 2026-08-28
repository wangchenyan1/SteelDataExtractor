# tests/test_validate_provenance.py
from tools.pipeline import validate_properties

CFG = {
    "property_source": {
        "allow": ["measured_table"],
        "deny": ["abstract_target"],
        "deny_phrase_patterns": ["above"],
    },
    "fields": {"property": ["yield_strength"]},
}


def test_keeps_excerpt_on_clean_value():
    props = [{"condition_id": "C1", "yield_strength": {
        "value": "685", "unit": "MPa", "source": "measured_table",
        "excerpt": "A-700 is 685 MPa", "location": "Table 2"}}]
    cleaned, warnings = validate_properties(props, CFG)
    assert cleaned[0]["yield_strength"]["excerpt"] == "A-700 is 685 MPa"
    assert cleaned[0]["yield_strength"]["status"] == "accepted"
    assert warnings == []


def test_rejected_value_kept_with_status():
    props = [{"condition_id": "C4", "yield_strength": {
        "value": "600", "unit": "MPa", "source": "abstract_target",
        "excerpt": "above 600 MPa", "location": "Abstract"}}]
    cleaned, warnings = validate_properties(props, CFG)
    val = cleaned[0]["yield_strength"]
    assert val["value"] == "600"
    assert val["status"] == "rejected_by_rule"
    assert "reject_reason" in val and val["reject_reason"]
    assert val["excerpt"] == "above 600 MPa"
    assert warnings[0]["type"] == "property_source_rejected"
    assert warnings[0]["excerpt"] == "above 600 MPa"
