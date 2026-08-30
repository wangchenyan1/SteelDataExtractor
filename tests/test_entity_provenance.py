from tools.pipeline import build_entity_prompt, normalize_entity_provenance


def test_entity_prompt_requires_excerpt_location():
    cfg = {
        "domain_hint": "金属材料文献",
        "fields": {
            "metadata": ["title"],
            "sample": ["sample_id", "sample_name", "composition"],
            "condition": ["condition_id", "condition_name"],
            "figure": ["figure_id", "figure_type"],
        },
        "rules": {},
    }
    prompt = build_entity_prompt(cfg, "Table 1 composition of Steel A")
    assert "excerpt" in prompt
    assert "location" in prompt
    assert "每个非标识字段" in prompt
    assert "Table 1 composition of Steel A" in prompt
    # 标识字段仍可为裸字符串
    assert '"sample_id": "..."' in prompt or '"sample_id":"..."' in prompt


def test_normalize_wraps_bare_strings():
    entity = {
        "paper_metadata": {"title": "Hello Paper"},
        "samples": [{"sample_id": "S1", "sample_name": "Steel A"}],
        "conditions": [{"condition_id": "C1", "condition_name": "A-700"}],
        "figures": [],
    }
    out = normalize_entity_provenance(entity)
    assert out["paper_metadata"]["title"]["value"] == "Hello Paper"
    assert "excerpt" in out["paper_metadata"]["title"]
    assert out["samples"][0]["sample_id"] == "S1"
    assert out["samples"][0]["sample_name"]["value"] == "Steel A"
    assert out["conditions"][0]["condition_id"] == "C1"
