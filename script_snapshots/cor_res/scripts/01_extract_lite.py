"""V4 瘦身版抽取脚本（仅在标准版被截断时使用）。

适用场景：
- 标准 01_extract.py 因 max_tokens=16384 而 JSON 截断
- 论文图片很多（>30 张），LLM 输出过长

策略：
- Schema 极简：只保留 4 大核心
- 删除 caption、image_purpose、microstructure_description 等冗余字段
- 图片 caption 用解析时保存的 _image_resources.nearby_text 兜底
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import traceback
from pathlib import Path

EXTRACT_DATA_DIR = Path("/internfs/wangchenyan/shougang/Extract_data")
SUBPROJECT_DIR = EXTRACT_DATA_DIR / "cor_res"
SHARED_SCRIPTS = EXTRACT_DATA_DIR / "initial_version" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from llm_client import call_multimodal, parse_json_strict
from paper_parser import parse_paper_md

PARSED_DIR = SUBPROJECT_DIR / "parsed_results"
OUTPUT_DIR = SUBPROJECT_DIR / "outputs"


SYSTEM_PROMPT = """你是钢铁材料论文结构化抽取专家。严格按用户给出的 JSON Schema 输出，禁止任何解释、开场白或代码块包裹。直接输出 JSON 对象。"""


# 极简版 JSON Schema
JSON_SCHEMA_PROMPT = """
直接输出 JSON 对象（第一个字符必须是 {，最后一个字符必须是 }，不要 ```json 包裹，不要任何前言）：

{
  "title": "...",
  "samples": [
    {
      "sid": "S1",
      "name": "样品原始命名（如 Nb-Ti steel, 4Mn steel, low carbon steel）",
      "comp": {"C": "0.039", "Mn": "1.10", "Si": "0.26", "Nb": "0.055"},
      "base_proc": "样品级公共工艺（≤150 字符）"
    }
  ],
  "conds": [
    {
      "cid": "C1",
      "sid": "S1",
      "name": "条件名（极简代号如 A700, A720, TP000）",
      "type": "process | mech_test | post_test",
      "proc": "该条件独有工艺（≤120 字符）",
      "ts": "850", "ts_u": "MPa",
      "ys": "650", "ys_u": "MPa",
      "el": "25", "el_u": "%"
    }
  ],
  "figs": [
    {"fid": "Figure 1a", "pi": 1, "ft": "OM|SEM|TEM|EBSD|XRD|curve|other", "ms": true, "post": false, "sid": "S1", "cid": "C1"}
  ]
}

## 规则
1. **样品识别**：同一钢种的 A700/A720/A740/A760 = 1 个 sample + 4 个 conds（绝不能拆成 4 个 sample）
2. **conds[].name**：极简代号（A700/TP000），不要堆完整工艺
3. **conds[].proc**：每个 cond 独有（700°C ≠ 720°C），不能笼统
4. **conds[].type=post_test**：断后样品（fractured/post-tensile/interrupted）→ 不进库
5. **figs[].ms**：true=组织图（before-test OM/SEM/TEM）；false=断口/曲线/示意图/XRD
6. **figs[].post**：true=断后图（fractured/post-test），后端会过滤掉
7. **figs[].fid**：论文中的图号（如 Figure 3a），多 panel 必须拆开
8. **figs[].pi**：对应文本中的 [FIGURE_PLACEHOLDER_n] 编号
9. **sid/cid**：必须对应 samples/conds 里的 sid/cid（外键）；无法判断时填 null
10. **省略 caption 和组织描述**：caption 由系统从图片附近文本自动填充
11. 性能字段：没有就用空字符串 ""，不要写 null 或 not_provided
"""


def build_prompt(text_placeholders: str, image_count: int) -> str:
    return f"""{JSON_SCHEMA_PROMPT}

## 论文文本（{image_count} 张图按顺序作为附件，对应 [FIGURE_PLACEHOLDER_n]）

{text_placeholders}

输出 JSON："""


def extract_one(paper_id: str, *, overwrite: bool = False) -> dict:
    paper_md = PARSED_DIR / paper_id / "paper.md"
    if not paper_md.exists():
        raise FileNotFoundError(f"paper.md 不存在: {paper_md}")

    out_dir = OUTPUT_DIR / paper_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "paper.json"
    if out_json.exists() and not overwrite:
        print(f"[SKIP] {paper_id} 已存在")
        return json.loads(out_json.read_text(encoding="utf-8"))

    print(f"[INFO] 解析 paper.md")
    parsed = parse_paper_md(paper_id, paper_md)
    print(f"[INFO] 文本: {parsed.text_chars} 字符 | 图片: {len(parsed.images)} 张")

    images_payload = [
        {"label": img.label or f"Image {img.index}", "media_type": img.media_type, "data": img.data_b64}
        for img in parsed.images
    ]

    prompt = build_prompt(parsed.text_with_placeholders, len(parsed.images))

    debug = out_dir / "_debug"
    debug.mkdir(exist_ok=True)
    (debug / "prompt_lite.txt").write_text(prompt, encoding="utf-8")

    print(f"[INFO] 调用 LLM（瘦身模式，含 {len(images_payload)} 张图片）...")
    t0 = time.time()
    raw = call_multimodal(
        text_prompt=prompt,
        images=images_payload,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=16384,
        timeout=900,
    )
    elapsed = time.time() - t0
    print(f"[INFO] LLM 耗时: {elapsed:.1f}s | 输出长度: {len(raw)} 字符")

    (debug / "raw_response_lite.txt").write_text(raw, encoding="utf-8")

    lite = parse_json_strict(raw)

    # 把瘦身 schema 展开成完整 schema（与 02_export.py 兼容）
    image_resources = {img.index: img for img in parsed.images}

    full = {
        "_paper_id": paper_id,
        "paper_metadata": {
            "title": lite.get("title", ""),
            "material_system": "",
        },
        "samples": [],
        "conditions": [],
        "figures": [],
        "_image_resources": [
            {
                "placeholder_index": img.index,
                "label": img.label,
                "alt": img.alt,
                "media_type": img.media_type,
                "nearby_text": img.nearby_text[:300],
            }
            for img in parsed.images
        ],
    }

    for s in lite.get("samples", []):
        full["samples"].append({
            "sample_id": s.get("sid"),
            "sample_name": s.get("name", ""),
            "composition": s.get("comp", {}),
            "composition_unit": "wt.%",
            "base_processing_description": s.get("base_proc", ""),
        })

    type_map = {"process": "processing_condition", "mech_test": "mechanical_test_condition", "post_test": "post_test_condition"}
    for c in lite.get("conds", []):
        ts_v, ts_u = c.get("ts", ""), c.get("ts_u", "")
        ys_v, ys_u = c.get("ys", ""), c.get("ys_u", "")
        el_v, el_u = c.get("el", ""), c.get("el_u", "")
        full["conditions"].append({
            "condition_id": c.get("cid"),
            "sample_id": c.get("sid"),
            "condition_name": c.get("name", ""),
            "condition_type": type_map.get(c.get("type"), "processing_condition"),
            "condition_processing_description": c.get("proc", ""),
            "mechanical_properties": {
                "tensile_strength": {"value": ts_v, "unit": ts_u} if ts_v else {},
                "yield_strength": {"value": ys_v, "unit": ys_u} if ys_v else {},
                "elongation": {"value": el_v, "unit": el_u} if el_v else {},
            },
            "microstructure_description": "",
        })

    for f in lite.get("figs", []):
        pi = f.get("pi")
        img_res = image_resources.get(pi)
        caption = (img_res.nearby_text[:200] if img_res else "").strip()
        ft = (f.get("ft") or "").upper()
        if ft in ("CURVE",):
            ft = "stress_strain_curve"
        full["figures"].append({
            "figure_id": f.get("fid", ""),
            "placeholder_index": pi,
            "figure_type": ft,
            "is_microstructure_image": bool(f.get("ms", False)),
            "is_post_test_image": bool(f.get("post", False)),
            "sample_id": f.get("sid"),
            "condition_id": f.get("cid"),
            "caption": caption,
            "image_purpose": "before_test_microstructure" if f.get("ms") else "other",
        })

    out_json.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 保存: {out_json}")

    # 拷贝图片到 images_raw（与标准版一致）
    images_raw = out_dir / "images_raw"
    images_raw.mkdir(exist_ok=True)
    for img in parsed.images:
        ext = img.media_type.split("/")[-1]
        if ext == "jpeg":
            ext = "jpg"
        (images_raw / f"placeholder_{img.index:03d}.{ext}").write_bytes(base64.b64decode(img.data_b64))

    return full


def main() -> int:
    parser = argparse.ArgumentParser(description="V4 瘦身版抽取（用于大论文）")
    parser.add_argument("--paper-id", action="append", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    success = 0
    failed = []
    for i, pid in enumerate(args.paper_id, 1):
        print(f"\n[{i}/{len(args.paper_id)}] === {pid} ===")
        try:
            extract_one(pid, overwrite=args.overwrite)
            success += 1
        except Exception as e:
            print(f"[FAIL] {pid}: {e}")
            traceback.print_exc()
            failed.append((pid, str(e)))

    print(f"\n[SUMMARY] 成功: {success} | 失败: {len(failed)}")
    for pid, err in failed:
        print(f"  - {pid}: {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
