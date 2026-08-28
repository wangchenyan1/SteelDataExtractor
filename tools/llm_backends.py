"""抽取后端：离线 mock 后端 + 真实 Claude 后端。

pipeline 只依赖 `Backend.call_json(system_prompt, text_prompt, images, hint)`：
- MockBackend：不联网、不需要 key，用 hint(stage, paper_id) 返回内置示例结果，
  让 demo 端到端跑通，并复现「one-shot 会把摘要目标值误抽成性能」的坑。
- ClaudeBackend：读取 .env 里的 key，真正调用多模态接口。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 真实后端
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://api.gpugeek.com/v1/messages"
DEFAULT_MODEL = "Vendor2/Claude-4.5-Sonnet"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_TIMEOUT = 600


def _load_env(start: Path) -> None:
    candidates = [start / ".env", start.parent / ".env", start.parents[1] / ".env"]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v


def parse_json_strict(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法解析 LLM 输出为 JSON: {text[:300]}")


class ClaudeBackend:
    name = "claude"

    def __init__(self, workspace_root: Path):
        _load_env(Path(workspace_root))

    def _key(self) -> str:
        key = os.getenv("LLM_API_KEY") or os.getenv("GPUGEEK_API_KEY")
        if not key:
            raise RuntimeError("LLM_API_KEY / GPUGEEK_API_KEY 未在 .env 中配置")
        return key

    def call_json(self, system_prompt: str, text_prompt: str,
                  images: list | None = None, hint: dict | None = None) -> dict:
        import requests  # 延迟导入，mock 模式无需安装

        content: list[dict[str, Any]] = []
        for img in images or []:
            if img.get("label"):
                content.append({"type": "text", "text": f"[{img['label']}]"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": img["media_type"], "data": img["data"]},
            })
        content.append({"type": "text", "text": text_prompt})

        payload = {
            "model": os.getenv("LLM_MODEL") or DEFAULT_MODEL,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "x-api-key": self._key(),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        base_url = (os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        resp = requests.post(base_url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        raw = "".join(
            b.get("text", "") for b in data.get("content", [])
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
        return parse_json_strict(raw)


# ---------------------------------------------------------------------------
# 离线 mock 后端（非标识字段按规格 5.5 包成 {value, unit, excerpt, location}）
# ---------------------------------------------------------------------------
def _fact(value, unit="", excerpt="", location=""):
    return {"value": value, "unit": unit, "excerpt": excerpt, "location": location}


def _demo_entity_result() -> dict:
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


def _demo_mechanical_result() -> dict:
    # 注意 C4 的 yield_strength=600 故意来自摘要目标值（abstract_target），
    # 用于演示规则校验把「非实测来源」的性能值剔除。
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


def _demo_magnetic_result() -> dict:
    # 磁性能单独一步抽取（无磁钢相对磁导率接近 1）。
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


class MockBackend:
    name = "mock"

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root

    def call_json(self, system_prompt: str, text_prompt: str,
                  images: list | None = None, hint: dict | None = None) -> dict:
        hint = hint or {}
        stage = hint.get("stage")
        step_id = hint.get("step_id")
        paper_id = hint.get("paper_id", "")
        if paper_id != "demo_steel_2024":
            # 只为内置样例提供离线数据；其他文献请用真实后端。
            if stage == "entity":
                return {"paper_metadata": {}, "samples": [], "conditions": [], "figures": []}
            return {"properties": []}
        if stage == "entity":
            return _demo_entity_result()
        if stage == "property":
            if step_id == "magnetic":
                return _demo_magnetic_result()
            return _demo_mechanical_result()
        if stage == "reextract":
            field_id = hint.get("field_id")
            if field_id == "yield_strength":
                props = []
                for row in _demo_mechanical_result().get("properties", []):
                    item = {"condition_id": row.get("condition_id")}
                    if "yield_strength" in row:
                        item["yield_strength"] = row["yield_strength"]
                    props.append(item)
                return {"properties": props}
            return {"properties": []}
        return {}


def get_backend(name: str, workspace_root: Path):
    if name == "claude":
        return ClaudeBackend(workspace_root)
    return MockBackend(workspace_root)
