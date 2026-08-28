"""核聚变低磁奥氏体不锈钢焊接文献多模态信息抽取 lite 版。

适用场景：
- 标准 01_extract.py 输出过长、JSON 截断或图片很多
- 希望减少 caption / image_purpose / microstructure.description 等冗余生成

策略：
- 仍输出与 02_export.py 兼容的 paper.json 主体结构
- LLM 不生成 caption、image_purpose、microstructure.description
- figure.caption 保存时由 _image_resources.nearby_text 自动兜底
- 其他核心字段继续抽取：成分、产品形态、样品/条件、component_type、joint_or_material_type、welding_process、filler_material、heat_treatment_condition、test_temperature、permeability、屈服/抗拉/伸长率/断裂韧性、scale_bar_info
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
    spec = importlib.util.spec_from_file_location("nuclear_fusion_standard_extract", STANDARD_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "sanitize_extraction", None)


SANITIZE_EXTRACTION = _load_standard_sanitizer()


SYSTEM_PROMPT = """你是钢铁/金属材料学术论文的结构化抽取专家，专门负责核聚变装置低磁/无磁奥氏体不锈钢焊材、焊缝金属和焊接接头文献。严格按用户给出的 JSON Schema 输出，禁止解释、开场白或 markdown 代码块。第一个字符必须是 {，最后一个字符必须是 }。"""


JSON_SCHEMA_PROMPT = """
请直接输出严格 JSON 对象。lite 版不要生成 caption、image_purpose、microstructure.description。

{
  "paper_metadata": {
    "title": "...",
    "material_system": "316LN / JJ1 / JK2LB / high-nitrogen austenitic stainless steel / ..."
  },
  "samples": [
    {
      "sample_id": "S1",
      "sample_name": "论文中样品原始命名",
      "product_form": "plate | sheet | bar | rod | wire | pipe | tube | conduit | jacket | coil_case | weldment | weld_metal | filler_wire | forging | casting | bulk | other | not_specified",
      "alloy_family": "316LN | 316L | 304L | JJ1 | JK2LB | high-nitrogen austenitic stainless steel | nitrogen-strengthened stainless steel | other",
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
      "condition_name": "极简条件代号，如 as-welded, 4.2K, Nb3Sn-reacted, aged, HAZ, WM",
      "condition_type": "processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition",
      "component_type": "armor | coil_case | conduit_jacket | magnet_structure | other | unclear",
      "joint_or_material_type": "base_metal | weld_metal | welded_joint | HAZ | deposited_metal | unclear",
      "welding_process": "TIG | GTAW | laser_welding | electron_beam_welding | NG-MAG | SAW | hybrid_welding | other | not_specified",
      "filler_material": "焊材/焊丝/填充金属原文名称，如 ER316LMn, FMYJJ1, 316L filler, none, not_specified",
      "heat_treatment_condition": "as-welded | Nb3Sn reacted | aged | solution treated | PWHT | other | not_specified；可保留原文温度时间",
      "test_temperature": {"value": "4.2", "unit": "K"},
      "condition_processing_description": "该条件独有补充工艺或测试状态：板厚、坡口、试样位置、取向、热输入等（≤200 字符）",
      "microstructure": {
        "grain_size": {"value": "15", "unit": "μm"}
      },
      "magnetic_properties": {
        "permeability": {"value": "1.003", "unit": "(relative)"}
      },
      "mechanical_properties": {
        "yield_strength": {"value": "1350", "unit": "MPa"},
        "tensile_strength": {"value": "1700", "unit": "MPa"},
        "elongation": {"value": "20", "unit": "%"},
        "fracture_toughness": {"value": "150", "unit": "MPa·m^1/2"}
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
1. sample = 化学成分独特或初始工艺独特的材料实体；同一样品不同焊接态、热处理态或测试温度放入 conditions。
2. 样品拆分硬规则：不要按成分表、性能表或组织表的每一行机械拆分 sample。filler/welding wire/electrode、weld metal/weld zone/WZ、HAZ、BM 测试位置、deposited metal、coating/surface layer、fracture/tensile/impact specimen、top/bottom/center/interface 等默认不是新 sample，应作为 condition、filler_material、joint_or_material_type 或 condition_processing_description。只有原文明确将其作为独立制备和独立研究的材料体系时，才可创建新 sample。
3. 正例：表格中同时出现 SS316L 40 mm、SS316L 60 mm、Filler ER316L、Weld 40 mm、Weld 60 mm；如果论文研究对象是 40 mm 和 60 mm TIG welded SS316L plates，则只创建 2 个样品，Filler ER316L 写入 filler_material，Weld 40/60 mm 作为 welded_joint/weld_metal condition 的证据。
4. composition 只填原文成分表/正文/图表明确给出的元素和值；不要补未知元素。
5. 严禁默认添加 "Fe": "bal."；只有原文明确写 Fe balance / Fe for balance / balance Fe / Fe bal. / rest Fe / remainder Fe，才可填 Fe="bal."。
6. condition_name 用极简代号；condition_processing_description 必须是该 condition 独有信息。
7. component_type 表示该 condition/性能数据对应的工程对象：armor | coil_case | conduit_jacket | magnet_structure | other | unclear。
8. joint_or_material_type 表示性能数据测量对象：base_metal | weld_metal | welded_joint | HAZ | deposited_metal | unclear。
9. “铠甲焊接接头”和“线圈盒焊接接头”不是处理状态，应拆成 component_type + joint_or_material_type。
10. welding_process、filler_material、heat_treatment_condition、test_temperature 是核聚变焊接接头核心工艺/测试字段；板厚、坡口、热输入、保护气、试样位置、取向等低频信息合并写入 condition_processing_description。
11. test_temperature 只填性能测试温度，不要填热处理温度。magnetic_properties 只抽 permeability；数值和单位按原文，不换算。
12. mechanical_properties 只抽 yield_strength、tensile_strength、elongation、fracture_toughness；断裂韧性包括 KIC / KJIC / KIC(J)，如原文只给 JIC 则按原文单位填写。
13. microstructure 只保留 grain_size；不要输出 description。
14. figures 不要输出 caption，不要输出 image_purpose；caption 保存时由系统用图片 nearby_text 自动填充。
15. is_microstructure_image 与 is_post_test_image 是独立维度；断口 SEM/断后 TEM/OM 可同时为 true。
16. XRD、electron diffraction、microdiffraction、SAED、schematic、stress-strain、hysteresis、magnetization curve 等非形貌图必须 is_microstructure_image=false。
17. placeholder_index 必须对应文本中的 [FIGURE_PLACEHOLDER_n]。
18. 未给出的数值字段直接省略，不要写 unknown / not reported / n/a。
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
    parser = argparse.ArgumentParser(description="核聚变低磁奥氏体不锈钢焊接文献多模态信息抽取 lite 版")
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
