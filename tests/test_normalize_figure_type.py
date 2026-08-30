from tools.pipeline import classify_figures, normalize_figure_type

CFG = {
    "figure_filter": {
        "keep_types": ["OM", "SEM", "TEM", "EBSD"],
        "drop_if_post_test": True,
        "require_microstructure": True,
    }
}


def test_normalize_free_text_aliases():
    assert normalize_figure_type("optical micrograph") == "OM"
    assert normalize_figure_type("SEM fracture surface micrograph") == "SEM"
    assert normalize_figure_type("EBSD Schmid factor map") == "EBSD"
    assert normalize_figure_type({"value": "schematic/engineering drawing"}) == "schematic"
    assert normalize_figure_type("XRD pattern") == "XRD"
    assert normalize_figure_type("impact energy vs temperature plot") == "other"
    assert normalize_figure_type("optical macrograph") == "OM"


def test_classify_accepts_normalized_micrographs():
    figs = [
        {
            "figure_id": "Fig4a",
            "figure_type": {"value": "optical micrograph"},
            "is_microstructure_image": {"value": "yes"},
            "is_post_test_image": {"value": "no"},
        },
        {
            "figure_id": "Fig1",
            "figure_type": {"value": "schematic/engineering drawing"},
            "is_microstructure_image": {"value": "no"},
            "is_post_test_image": {"value": "no"},
        },
        {
            "figure_id": "Fig9a",
            "figure_type": {"value": "SEM fracture surface micrograph"},
            "is_microstructure_image": {"value": "yes"},
            "is_post_test_image": {"value": "yes"},
        },
        {
            "figure_id": "Fig11a",
            "figure_type": {"value": "EBSD Schmid factor map"},
            "is_microstructure_image": {"value": "yes"},
            "is_post_test_image": {"value": "no"},
        },
    ]
    kept, warnings = classify_figures(figs, CFG, apply_filter=True)
    by_id = {f["figure_id"]: f for f in kept}
    assert by_id["Fig4a"]["status"] == "accepted"
    assert by_id["Fig11a"]["status"] == "accepted"
    assert by_id["Fig1"]["status"] == "rejected_by_rule"
    assert "is_microstructure_image" in by_id["Fig1"]["reject_reason"]
    assert "白名单" not in by_id["Fig1"]["reject_reason"]
    assert by_id["Fig9a"]["status"] == "rejected_by_rule"
    assert "断后" in by_id["Fig9a"]["reject_reason"] or "post-test" in by_id["Fig9a"]["reject_reason"]
