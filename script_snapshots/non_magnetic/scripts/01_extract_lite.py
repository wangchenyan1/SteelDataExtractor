"""无磁钢专用：多模态信息抽取 lite 版。

适用场景：
- 标准 01_extract.py 输出过长、JSON 截断或图片很多
- 希望减少 caption / image_purpose / microstructure.description 等冗余生成

策略：
- 仍输出与 02_export.py 兼容的 paper.json 主体结构
- LLM 不生成 caption、image_purpose、microstructure.description
- figure.caption 保存时由 _image_resources.nearby_text 自动兜底
- 其他核心字段继续抽取：成分、产品形态、样品/条件、轧制、磁性能、力学性能、scale_bar_info
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
PARSED_DIR = PROJECT_DIR / "parsed_results"
OUTPUT_DIR = PROJECT_DIR / "outputs"
STANDARD_SCRIPT = Path(__file__).resolve().with_name("01_extract.py")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_client import call_multimodal, parse_json_strict  # noqa: E402
from paper_parser import parse_paper_md  # noqa: E402


def _load_standard_sanitizer():
    """Reuse deterministic cleanup from the standard extractor when available."""
    if not STANDARD_SCRIPT.exists():
        return None
    spec = importlib.util.spec_from_file_location("nonmag_standard_extract", STANDARD_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "sanitize_extraction", None)


SANITIZE_EXTRACTION = _load_standard_sanitizer()


SYSTEM_PROMPT = """你是钢铁/金属材料学术论文的结构化抽取专家，专门负责无磁钢（non-magnetic / paramagnetic / austenitic Mn steel / high-Mn austenitic non-magnetic steel）领域论文。严格按用户给出的 JSON Schema 输出，禁止解释、开场白或 markdown 代码块。第一个字符必须是 {，最后一个字符必须是 }。"""


JSON_SCHEMA_PROMPT = """
请直接输出严格 JSON 对象。lite 版不要生成 caption、image_purpose、microstructure.description。

{
  "paper_metadata": {
    "title": "...",
    "material_system": "high-Mn non-magnetic steel / Cr-Mn-N austenitic steel / ..."
  },
  "samples": [
    {
      "sample_id": "S1",
      "sample_name": "论文中样品原始命名",
      "product_form": "plate | sheet | bar | rod | rebar | wire | pipe | tube | angle_steel | pin | forging | casting | powder | bulk | target | other | not_specified",
      "alloy_family": "Fe-Mn-Al-C | Mn-Cr-N | Mn-Cr-Mo-Ni | ...",
      "composition": {"C": "0.45", "Mn": "18.5", "Cr": "3.5", "N": "0.05"},
      "composition_unit": "wt.%",
      "base_processing_description": "样品级公共工艺（≤200 字符）",
      "sample_processing_overview": "样品整体工艺概述（≤200 字符）",
      "sample_microstructure_overview": "样品整体组织概述（≤200 字符）"
    }
  ],
  "conditions": [
    {
      "condition_id": "C1",
      "sample_id": "S1",
      "condition_name": "极简条件代号，如 HR, ST1100, A900-15min, as-rolled",
      "condition_type": "processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition",
      "condition_processing_description": "该条件独有工艺或测试状态（≤200 字符）",
      "rolling_processing": {
        "heating_temperature": {"value": "1200", "unit": "°C"},
        "start_rolling_temperature": {"value": "1100", "unit": "°C"},
        "finish_rolling_temperature": {"value": "900", "unit": "°C"},
        "reduction_ratio": {"value": "80", "unit": "%"},
        "cooling_rate": {"value": "10", "unit": "°C/s"}
      },
      "microstructure": {
        "grain_size": {"value": "15", "unit": "μm"}
      },
      "magnetic_properties": {
        "permeability": {"value": "1.003", "unit": "(relative)"},
        "remanence": {"value": "0.5", "unit": "Gs"},
        "saturation_magnetization": {"value": "1.2", "unit": "emu/g"},
        "coercivity": {"value": "12", "unit": "Oe"},
        "curie_temperature": {"value": "580", "unit": "°C"},
        "neel_temperature": {"value": "120", "unit": "K"},
        "austenite_stability": "stable, no α'-martensite after 20% cold rolling, SFE=30 mJ/m²",
        "martensite_transformation_temperature": "Ms=-80°C, Md30=-40°C"
      },
      "mechanical_properties": {
        "yield_strength": {"value": "650", "unit": "MPa"},
        "tensile_strength": {"value": "950", "unit": "MPa"},
        "elongation": {"value": "45", "unit": "%"},
        "elastic_modulus": {"value": "200", "unit": "GPa"},
        "hardness": {"value": "220", "unit": "HV"},
        "impact_77K": {"value": "120", "unit": "J"}
      }
    }
  ],
  "figures": [
    {
      "figure_id": "Figure 1a",
      "placeholder_index": 1,
      "figure_type": "OM | SEM | TEM | EBSD | XRD | stress_strain_curve | hysteresis_loop | schematic | magnetic_curve | other",
      "is_microstructure_image": true,
      "is_post_test_image": false,
      "sample_id": "S1",
      "condition_id": "C1",
      "scale_bar_info": {"value": "50", "unit": "μm"}
    }
  ]
}

## 核心规则
1. sample = 化学成分独特或初始工艺独特的材料实体；同一样品不同热处理/轧制/测试态放入 conditions。
2. composition 只填原文成分表/正文/图表明确给出的元素和值；不要补未知元素。
3. 严禁默认添加 "Fe": "bal."；只有原文明确写 Fe balance / Fe for balance / balance Fe / Fe bal. / rest Fe / remainder Fe，才可填 Fe="bal."。
4. 合金名 Fe-26Mn-11Al-1.15C 或 Fe-xMn-yAl-zC 不等于 Fe=bal.；这种情况不要自动补 Fe。
5. condition_name 用极简代号；condition_processing_description 必须是该 condition 独有信息。
6. rolling_processing 只抽原文明示的 5 项：heating_temperature、start_rolling_temperature、finish_rolling_temperature、reduction_ratio、cooling_rate；没有就省略。
7. magnetic_properties 数值和单位按原文，不换算；不要把屈服强度 σs 误作 saturation_magnetization。
8. mechanical_properties 默认只放室温拉伸；-196°C 冲击可作为 impact_77K。
9. microstructure 只保留 grain_size；不要输出 description。
10. figures 不要输出 caption，不要输出 image_purpose；caption 保存时由系统用图片 nearby_text 自动填充。
11. is_microstructure_image 与 is_post_test_image 是独立维度；断口 SEM/断后 TEM/OM 可同时为 true。
12. XRD、electron diffraction、microdiffraction、SAED、schematic、stress-strain、hysteresis、magnetization curve 等非形貌图必须 is_microstructure_image=false。
13. placeholder_index 必须对应文本中的 [FIGURE_PLACEHOLDER_n]。
14. 未给出的数值字段直接省略，不要写 unknown / not reported / n/a。
"""


def build_prompt(text_with_placeholders: str, image_count: int) -> str:
    return f"""{JSON_SCHEMA_PROMPT}

## 论文内容

下面是论文完整文本（{image_count} 张图片按顺序作为附件传入，对应文本中的 [FIGURE_PLACEHOLDER_n]）：

{text_with_placeholders}

请输出严格 JSON："""


def _nearby_caption_by_index(parsed) -> dict[int, str]:
    return {
        img.index: (img.nearby_text[:200] if img.nearby_text else "").strip()
        for img in parsed.images
    }


def _strip_redundant_fields(data: dict) -> None:
    for condition in data.get("conditions", []) or []:
        microstructure = condition.get("microstructure")
        if isinstance(microstructure, dict):
            microstructure.pop("description", None)
        condition.pop("microstructure_description", None)

    for figure in data.get("figures", []) or []:
        figure.pop("image_purpose", None)


def _fill_figure_captions_from_nearby_text(data: dict, captions: dict[int, str]) -> None:
    for figure in data.get("figures", []) or []:
        pi = figure.get("placeholder_index")
        fallback = captions.get(pi, "")
        # Lite mode does not ask the model to generate captions. Keep a compact fallback
        # so downstream review/export still has human-readable context.
        figure["caption"] = fallback


def extract_one_paper(paper_id: str, *, overwrite: bool = False) -> dict:
    paper_dir = PARSED_DIR / paper_id
    paper_md = paper_dir / "paper.md"
    if not paper_md.exists():
        raise FileNotFoundError(f"paper.md 不存在: {paper_md}")

    output_dir = OUTPUT_DIR / paper_id
    output_dir.mkdir(parents=True, exist_ok=True)
    paper_json_path = output_dir / "paper.json"

    if paper_json_path.exists() and not overwrite:
        print(f"[SKIP] {paper_id} paper.json 已存在（用 --overwrite 强制重跑）")
        return json.loads(paper_json_path.read_text(encoding="utf-8"))

    print(f"[INFO] 解析 paper.md: {paper_md}")
    parsed = parse_paper_md(paper_id, paper_md)
    print(f"[INFO] 文本: {parsed.text_chars} 字符 | 图片: {len(parsed.images)} 张")

    if not parsed.images:
        print(f"[WARN] {paper_id} 未检测到图片")

    images_payload = [
        {"label": img.label or f"Image {img.index}", "media_type": img.media_type, "data": img.data_b64}
        for img in parsed.images
    ]

    prompt = build_prompt(parsed.text_with_placeholders, len(parsed.images))

    debug_dir = output_dir / "_debug"
    debug_dir.mkdir(exist_ok=True)
    (debug_dir / "prompt_lite.txt").write_text(prompt, encoding="utf-8")
    (debug_dir / "image_index_lite.json").write_text(
        json.dumps(
            [
                {
                    "index": img.index,
                    "label": img.label,
                    "alt": img.alt,
                    "media_type": img.media_type,
                    "nearby": img.nearby_text[:300],
                }
                for img in parsed.images
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[INFO] 调用 LLM（lite，多模态，含 {len(images_payload)} 张图片）...")
    t0 = time.time()
    raw_response = call_multimodal(
        text_prompt=prompt,
        images=images_payload,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=16384,
        timeout=900,
    )
    elapsed = time.time() - t0
    print(f"[INFO] LLM 响应耗时: {elapsed:.1f}s | 长度: {len(raw_response)} 字符")

    (debug_dir / "raw_response_lite.txt").write_text(raw_response, encoding="utf-8")

    data = parse_json_strict(raw_response)
    _strip_redundant_fields(data)
    _fill_figure_captions_from_nearby_text(data, _nearby_caption_by_index(parsed))

    if SANITIZE_EXTRACTION is not None:
        validation_warnings = SANITIZE_EXTRACTION(data, parsed.text_with_placeholders)
        if validation_warnings:
            print(f"[WARN] 后处理清理/审计发现 {len(validation_warnings)} 项")
            (debug_dir / "validation_warnings_lite.json").write_text(
                json.dumps(validation_warnings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            data["_validation_warnings"] = validation_warnings

    data["_image_resources"] = [
        {
            "placeholder_index": img.index,
            "label": img.label,
            "alt": img.alt,
            "media_type": img.media_type,
            "nearby_text": img.nearby_text[:300],
        }
        for img in parsed.images
    ]
    data["_paper_id"] = paper_id

    paper_json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 保存: {paper_json_path}")

    images_raw_dir = output_dir / "images_raw"
    images_raw_dir.mkdir(exist_ok=True)
    for img in parsed.images:
        ext = img.media_type.split("/")[-1]
        if ext == "jpeg":
            ext = "jpg"
        fname = f"placeholder_{img.index:03d}.{ext}"
        (images_raw_dir / fname).write_bytes(base64.b64decode(img.data_b64))

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="无磁钢 多模态信息抽取 lite 版")
    parser.add_argument("--paper-id", action="append", help="处理指定论文（可多次）")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.paper_id:
        paper_ids = args.paper_id
    else:
        paper_ids = sorted(
            d.name for d in PARSED_DIR.iterdir()
            if d.is_dir() and (d / "paper.md").exists()
        )
        if args.limit:
            paper_ids = paper_ids[:args.limit]

    print(f"[INFO] 共 {len(paper_ids)} 篇论文待处理（lite）")
    success = 0
    failed = []
    for i, pid in enumerate(paper_ids, 1):
        print(f"\n[{i}/{len(paper_ids)}] === {pid} ===")
        try:
            extract_one_paper(pid, overwrite=args.overwrite)
            success += 1
        except Exception as e:
            print(f"[FAIL] {pid}: {e}")
            traceback.print_exc()
            failed.append((pid, str(e)))

    print(f"\n[SUMMARY] 成功: {success} | 失败: {len(failed)}")
    if failed:
        for pid, err in failed:
            print(f"  - {pid}: {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
