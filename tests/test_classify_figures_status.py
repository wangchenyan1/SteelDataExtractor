# tests/test_classify_figures_status.py
from tools.pipeline import classify_figures

CFG = {
    "figure_filter": {
        "keep_types": ["OM", "SEM"],  # 保留配置项，但不再参与硬过滤
        "drop_types": ["XRD"],
        "drop_if_post_test": True,
        "require_microstructure": True,
    }
}


def test_non_microstructure_rejected_by_flag_not_type():
    figs = [
        {"figure_id": "Figure 1", "figure_type": "OM",
         "is_microstructure_image": True, "is_post_test_image": False,
         "placeholder_index": 1},
        {"figure_id": "Figure 3", "figure_type": "XRD",
         "is_microstructure_image": False, "is_post_test_image": False,
         "placeholder_index": 3},
        {"figure_id": "Figure 9", "figure_type": "weird_free_text",
         "is_microstructure_image": True, "is_post_test_image": False},
    ]
    kept, warnings = classify_figures(figs, CFG, apply_filter=True)
    assert len(kept) == 3
    by_id = {f["figure_id"]: f for f in kept}
    assert by_id["Figure 1"]["status"] == "accepted"
    assert by_id["Figure 9"]["status"] == "accepted"  # 类型不在白名单也不拦
    assert by_id["Figure 3"]["status"] == "rejected_by_rule"
    assert "is_microstructure_image" in by_id["Figure 3"]["reject_reason"]
    assert "白名单" not in by_id["Figure 3"]["reject_reason"]
    assert any(w["type"] == "figure_dropped" for w in warnings)


def test_provenance_wrapped_figure_type_does_not_crash():
    figs = [
        {
            "figure_id": "Fig1",
            "figure_type": {"value": "OM", "excerpt": "OM image", "location": "Fig.1"},
            "is_microstructure_image": {"value": "yes"},
            "is_post_test_image": {"value": "no"},
        },
        {
            "figure_id": "Fig3",
            "figure_type": {"value": "XRD", "excerpt": "XRD", "location": "Fig.3"},
            "is_microstructure_image": {"value": False},
            "is_post_test_image": {"value": False},
        },
    ]
    kept, warnings = classify_figures(figs, CFG, apply_filter=True)
    by_id = {f["figure_id"]: f for f in kept}
    assert by_id["Fig1"]["status"] == "accepted"
    assert by_id["Fig3"]["status"] == "rejected_by_rule"
    assert "is_microstructure_image" in by_id["Fig3"]["reject_reason"]
    assert any(w["type"] == "figure_dropped" for w in warnings)


def test_post_test_rejected_even_if_microstructure():
    figs = [
        {
            "figure_id": "Fig9a",
            "figure_type": "SEM",
            "is_microstructure_image": True,
            "is_post_test_image": True,
        }
    ]
    kept, warnings = classify_figures(figs, CFG, apply_filter=True)
    assert kept[0]["status"] == "rejected_by_rule"
    assert "断后" in kept[0]["reject_reason"] or "post-test" in kept[0]["reject_reason"]


def test_single_pass_all_accepted():
    figs = [{"figure_id": "Figure 3", "figure_type": "XRD",
             "is_microstructure_image": False, "is_post_test_image": False}]
    kept, warnings = classify_figures(figs, CFG, apply_filter=False)
    assert kept[0]["status"] == "accepted"
    assert warnings == []
