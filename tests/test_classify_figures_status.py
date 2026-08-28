# tests/test_classify_figures_status.py
from tools.pipeline import classify_figures

CFG = {
    "figure_filter": {
        "keep_types": ["OM", "SEM"],
        "drop_types": ["XRD"],
        "drop_if_post_test": True,
        "require_microstructure": True,
    }
}


def test_xrd_kept_with_rejected_status():
    figs = [
        {"figure_id": "Figure 1", "figure_type": "OM",
         "is_microstructure_image": True, "is_post_test_image": False,
         "placeholder_index": 1},
        {"figure_id": "Figure 3", "figure_type": "XRD",
         "is_microstructure_image": False, "is_post_test_image": False,
         "placeholder_index": 3},
    ]
    kept, warnings = classify_figures(figs, CFG, apply_filter=True)
    assert len(kept) == 2
    by_id = {f["figure_id"]: f for f in kept}
    assert by_id["Figure 1"]["status"] == "accepted"
    assert by_id["Figure 3"]["status"] == "rejected_by_rule"
    assert "XRD" in by_id["Figure 3"]["reject_reason"]
    assert any(w["type"] == "figure_dropped" for w in warnings)


def test_single_pass_all_accepted():
    figs = [{"figure_id": "Figure 3", "figure_type": "XRD",
             "is_microstructure_image": False, "is_post_test_image": False}]
    kept, warnings = classify_figures(figs, CFG, apply_filter=False)
    assert kept[0]["status"] == "accepted"
    assert warnings == []
