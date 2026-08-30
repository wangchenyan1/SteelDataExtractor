"""测试用固定抽取结果，不进入产品运行路径。"""

from __future__ import annotations

from pathlib import Path


def _fact(value, unit="", excerpt="", location=""):
    return {"value": value, "unit": unit, "excerpt": excerpt, "location": location}


def _entity_result() -> dict:
    return {
        "paper_metadata": {
            "title": _fact(
                "Effect of Annealing Temperature on a High-Nitrogen Austenitic Stainless Steel",
                excerpt="Effect of Annealing Temperature on Microstructure and Mechanical Properties of a High-Nitrogen Austenitic Stainless Steel",
                location="Title",
            ),
            "material_system": _fact(
                "Cr-Mn-N high-nitrogen austenitic stainless steel",
                excerpt="High-nitrogen austenitic stainless steels are promising non-magnetic structural materials",
                location="Abstract",
            ),
        },
        "samples": [
            {
                "sample_id": "S1",
                "sample_name": _fact("Steel A (Cr-Mn-N)", excerpt="Cr-Mn-N steel (Steel A)", location="Section 1. Introduction"),
                "product_form": _fact("plate", excerpt="hot rolling into 12 mm plates", location="Section 2. Materials and Methods"),
                "alloy_family": _fact("Cr-Mn-N", excerpt="Cr-Mn-N steel (Steel A)", location="Section 1. Introduction"),
                "composition": {
                    "value": {"C": "0.05", "Cr": "18.2", "Mn": "10.5", "Ni": "0.3", "N": "0.52"},
                    "unit": "",
                    "excerpt": "Steel A (Cr-Mn-N) | 0.05 | 18.2",
                    "location": "Table 1",
                },
                "base_processing_description": _fact(
                    "vacuum induction melting, hot forging, hot rolling into 12 mm plate",
                    excerpt="prepared by vacuum induction melting, hot forging and hot rolling into 12 mm plates",
                    location="Section 2. Materials and Methods",
                ),
            },
            {
                "sample_id": "S2",
                "sample_name": _fact("Steel B (Cr-Ni ref.)", excerpt="reference Cr-Ni steel (Steel B)", location="Section 1. Introduction"),
                "product_form": _fact("plate", excerpt="hot rolling into 12 mm plates", location="Section 2. Materials and Methods"),
                "alloy_family": _fact("Cr-Ni", excerpt="reference Cr-Ni steel (Steel B)", location="Section 1. Introduction"),
                "composition": {
                    "value": {"C": "0.04", "Cr": "18.0", "Mn": "1.2", "Ni": "10.4", "N": "0.03"},
                    "unit": "",
                    "excerpt": "Steel B (Cr-Ni ref.) | 0.04 | 18.0",
                    "location": "Table 1",
                },
                "base_processing_description": _fact(
                    "vacuum induction melting, hot forging, hot rolling into 12 mm plate",
                    excerpt="prepared by vacuum induction melting, hot forging and hot rolling into 12 mm plates",
                    location="Section 2. Materials and Methods",
                ),
            },
        ],
        "conditions": [
            {"condition_id": "C1", "sample_id": "S1",
             "condition_name": _fact("A-700", excerpt="A-700 | 700 | 685 | 1020 | 42", location="Table 2"),
             "condition_type": _fact("processing_condition", excerpt="solution annealed at 700, 720 and 740 °C", location="Section 2. Materials and Methods"),
             "heat_treatment_condition": _fact(
                 "solution annealed 700C 30min, water quenched",
                 excerpt="solution annealed at 700, 720 and 740 °C for 30 min followed by water quenching",
                 location="Section 2. Materials and Methods"),
             "test_temperature": _fact("RT", excerpt="Room-temperature tensile properties", location="Table 2"),
             "condition_processing_description": _fact(
                 "solution annealed at 700 C for 30 min",
                 excerpt="solution annealed at 700, 720 and 740 °C for 30 min",
                 location="Section 2. Materials and Methods")},
            {"condition_id": "C2", "sample_id": "S1",
             "condition_name": _fact("A-720", excerpt="A-720 | 720 | 660 | 995 | 45", location="Table 2"),
             "condition_type": _fact("processing_condition", excerpt="solution annealed at 700, 720 and 740 °C", location="Section 2. Materials and Methods"),
             "heat_treatment_condition": _fact(
                 "solution annealed 720C 30min, water quenched",
                 excerpt="solution annealed at 700, 720 and 740 °C for 30 min followed by water quenching",
                 location="Section 2. Materials and Methods"),
             "test_temperature": _fact("RT", excerpt="Room-temperature tensile properties", location="Table 2"),
             "condition_processing_description": _fact(
                 "solution annealed at 720 C for 30 min",
                 excerpt="solution annealed at 700, 720 and 740 °C for 30 min",
                 location="Section 2. Materials and Methods")},
            {"condition_id": "C3", "sample_id": "S1",
             "condition_name": _fact("A-740", excerpt="A-740 | 740 | 632 | 970 | 48", location="Table 2"),
             "condition_type": _fact("processing_condition", excerpt="solution annealed at 700, 720 and 740 °C", location="Section 2. Materials and Methods"),
             "heat_treatment_condition": _fact(
                 "solution annealed 740C 30min, water quenched",
                 excerpt="solution annealed at 700, 720 and 740 °C for 30 min followed by water quenching",
                 location="Section 2. Materials and Methods"),
             "test_temperature": _fact("RT", excerpt="Room-temperature tensile properties", location="Table 2"),
             "condition_processing_description": _fact(
                 "solution annealed at 740 C for 30 min",
                 excerpt="solution annealed at 700, 720 and 740 °C for 30 min",
                 location="Section 2. Materials and Methods")},
            {"condition_id": "C4", "sample_id": "S2",
             "condition_name": _fact("B-1050", excerpt="Steel B was solution annealed at 1050 °C for 30 min", location="Section 2. Materials and Methods"),
             "condition_type": _fact("processing_condition", excerpt="Steel B was solution annealed at 1050 °C for 30 min as a reference condition", location="Section 2. Materials and Methods"),
             "heat_treatment_condition": _fact(
                 "solution annealed 1050C 30min",
                 excerpt="Steel B was solution annealed at 1050 °C for 30 min as a reference condition",
                 location="Section 2. Materials and Methods"),
             "test_temperature": _fact("RT", excerpt="measured yield strength was 245 MPa and the tensile strength was 585 MPa at room temperature", location="Section 3.1 Mechanical properties"),
             "condition_processing_description": _fact(
                 "reference condition, annealed at 1050 C for 30 min",
                 excerpt="Steel B was solution annealed at 1050 °C for 30 min as a reference condition",
                 location="Section 2. Materials and Methods")},
        ],
        "figures": [
            {"figure_id": "Figure 1", "placeholder_index": 1, "figure_type": "OM",
             "is_microstructure_image": True, "is_post_test_image": False,
             "sample_id": "S1", "condition_id": "C2", "scale_bar_info": {"value": "25", "unit": "μm"}},
            {"figure_id": "Figure 2", "placeholder_index": 2, "figure_type": "SEM",
             "is_microstructure_image": True, "is_post_test_image": False,
             "sample_id": "S1", "condition_id": None, "scale_bar_info": {"value": "5", "unit": "μm"}},
            {"figure_id": "Figure 3", "placeholder_index": 3, "figure_type": "XRD",
             "is_microstructure_image": False, "is_post_test_image": False,
             "sample_id": None, "condition_id": None, "scale_bar_info": None},
        ],
    }


def _prop(value, unit, source, excerpt="", location=""):
    return {
        "value": value, "unit": unit, "source": source,
        "excerpt": excerpt, "location": location,
    }


def _mechanical_result() -> dict:
    return {
        "properties": [
            {"condition_id": "C1",
             "yield_strength": _prop("685", "MPa", "measured_table",
                                     "A-700 | 700 | 685 | 1020 | 42", "Table 2"),
             "tensile_strength": _prop("1020", "MPa", "measured_table",
                                       "A-700 | 700 | 685 | 1020 | 42", "Table 2"),
             "elongation": _prop("42", "%", "measured_table",
                                 "A-700 | 700 | 685 | 1020 | 42", "Table 2")},
            {"condition_id": "C2",
             "yield_strength": _prop("660", "MPa", "measured_table",
                                     "A-720 | 720 | 660 | 995 | 45", "Table 2"),
             "tensile_strength": _prop("995", "MPa", "measured_table",
                                       "A-720 | 720 | 660 | 995 | 45", "Table 2"),
             "elongation": _prop("45", "%", "measured_table",
                                 "A-720 | 720 | 660 | 995 | 45", "Table 2")},
            {"condition_id": "C3",
             "yield_strength": _prop("632", "MPa", "measured_table",
                                     "A-740 | 740 | 632 | 970 | 48", "Table 2"),
             "tensile_strength": _prop("970", "MPa", "measured_table",
                                       "A-740 | 740 | 632 | 970 | 48", "Table 2"),
             "elongation": _prop("48", "%", "measured_table",
                                 "A-740 | 740 | 632 | 970 | 48", "Table 2")},
            {"condition_id": "C4",
             "yield_strength": {
                 "value": "600", "unit": "MPa", "source": "abstract_target",
                 "evidence": "design target ... yield strength above 600 MPa",
                 "excerpt": "yield strength above 600 MPa", "location": "Abstract",
             },
             "tensile_strength": _prop(
                 "585", "MPa", "measured_text",
                 "the measured yield strength was 245 MPa and the tensile strength was 585 MPa",
                 "Section 3.1 Mechanical properties",
             )},
        ]
    }


def _magnetic_result() -> dict:
    return {
        "properties": [
            {"condition_id": "C1", "permeability": _prop(
                "1.01", "(relative)", "measured_text",
                "while remaining fully austenitic and non-magnetic", "Section 4. Conclusions")},
            {"condition_id": "C2", "permeability": _prop(
                "1.01", "(relative)", "measured_text",
                "while remaining fully austenitic and non-magnetic", "Section 4. Conclusions")},
            {"condition_id": "C3", "permeability": _prop(
                "1.02", "(relative)", "measured_text",
                "while remaining fully austenitic and non-magnetic", "Section 4. Conclusions")},
        ]
    }


class FixtureBackend:
    name = "fixture"

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root

    def call_json(self, system_prompt: str, text_prompt: str,
                  images: list | None = None, hint: dict | None = None) -> dict:
        hint = hint or {}
        stage = hint.get("stage")
        step_id = hint.get("step_id")
        if stage == "entity":
            return _entity_result()
        if stage == "property":
            if step_id == "magnetic":
                return _magnetic_result()
            return _mechanical_result()
        if stage == "reextract":
            field_id = hint.get("field_id")
            if field_id == "yield_strength":
                props = []
                for row in _mechanical_result().get("properties", []):
                    item = {"condition_id": row.get("condition_id")}
                    if "yield_strength" in row:
                        item["yield_strength"] = row["yield_strength"]
                    props.append(item)
                return {"properties": props}
            return {"properties": []}
        return {}
