from tools.pipeline import filter_result_by_status


def test_filter_drops_rejected():
    result = {
        "conditions": [{
            "condition_id": "C4",
            "mechanical_properties": {
                "yield_strength": {
                    "value": "600", "status": "rejected_by_rule",
                    "unit": "MPa", "source": "abstract_target",
                    "excerpt": "", "location": "",
                },
                "elongation": {
                    "value": "40", "status": "accepted",
                    "unit": "%", "source": "measured_table",
                    "excerpt": "", "location": "",
                },
            },
        }],
        "figures": [
            {"figure_id": "Figure 3", "status": "rejected_by_rule"},
            {"figure_id": "Figure 1", "status": "accepted"},
        ],
    }
    out = filter_result_by_status(result, include_rejected=False)
    assert "yield_strength" not in out["conditions"][0]["mechanical_properties"]
    assert "elongation" in out["conditions"][0]["mechanical_properties"]
    assert [f["figure_id"] for f in out["figures"]] == ["Figure 1"]
