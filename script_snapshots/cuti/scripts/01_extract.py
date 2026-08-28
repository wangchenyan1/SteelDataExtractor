"""Cu-Ti 合金多模态信息抽取脚本。

核心理念：
1. 一次调用，LLM 同时看到论文文本 + 全部图片
2. 输出严格 JSON：samples、figures、figure→sample 映射
3. 不再用中间 markdown 格式，直接 JSON 驱动后续导出

输入：parsed_results/<paper_id>/paper.md
输出：outputs/<paper_id>/paper.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_client import call_multimodal, parse_json_strict
from paper_parser import parse_paper_md


PROJECT_DIR = Path(__file__).resolve().parents[1]
PARSED_DIR = PROJECT_DIR / "parsed_results"
OUTPUT_DIR = PROJECT_DIR / "outputs"
LOG_DIR = PROJECT_DIR / "logs"


SYSTEM_PROMPT = """你是铜钛合金（Cu-Ti / CuTi）学术论文的结构化抽取专家。你必须严格按照用户给出的 JSON Schema 输出，禁止任何额外解释。所有数据字段以英文输出；样品名（sample_name）严格保留论文原文写法。"""


# 严格 JSON Schema 说明（嵌入到 user prompt 里）
JSON_SCHEMA_PROMPT = """
请输出一个严格的 JSON 对象，结构如下：

{
  "paper_metadata": {
    "title": "...",
    "material_system": "合金体系简短描述（如 Cu-4Ti, Cu-3Ti-2Si-1.5Ni, Cu-Ti-Cr-Mg）"
  },
  "samples": [
    {
      "sample_id": "S1",
      "sample_name": "论文中样品的原始命名（如 Cu-4Ti, Cu-3.5Ti, Cu-4Ti-1Cr）",
      "alloy_family": "Cu-Ti | Cu-Ti-Cr | Cu-Ti-Fe-Cr | Cu-Ti-Ni-Si | Cu-Ti-Cr-Mg-Si 等（见规则 §3）",
      "product_form": "sheet | strip | foil | plate | bar | rod | wire | pipe | tube | forging | casting | powder | bulk | other",
      "composition": {
        "Cu": "Bal.", "Ti": "3.95", "Zn": "0.13", "Fe": "0.03"
      },
      "composition_unit": "wt.%",
      "base_processing_description": "样品级公共工艺：冶炼、铸造、热轧成材等所有 condition 共享的部分",
      "sample_processing_overview": "样品整体工艺关键参数（固定格式，去修饰词）：合金名、固溶/时效/冷轧等关键温度与时间、加工状态",
      "sample_microstructure_overview": "样品整体组织关键特征（固定格式，去修饰词）：相组成、析出相（如 β'-Cu4Ti）、晶粒尺寸、组织形貌"
    }
  ],
  "conditions": [
    {
      "condition_id": "C1",
      "sample_id": "S1",
      "condition_name": "条件名（极简代号，如 ST900, A450-120min, CR50+A450, peak-aged, as-solution-treated）",
      "condition_type": "processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition",
      "solution_treatment": "定格式文本，例：900°C/4h, WQ（见规则 §7）",
      "aging": "定格式文本，例：450°C/60min 或 300°C/2h + 450°C/7h（见规则 §7）",
      "cold_rolling": "定格式文本，例：50% 或 85% + 90% + 95%（见规则 §7）",
      "condition_processing_description": "定格式字段未覆盖的残余工艺细节（气氛、工序顺序补充等）；勿重复抄写温度/时间/压下率",
      "mechanical_properties": {
        "yield_strength":     {"value": "880", "unit": "MPa"},
        "tensile_strength":   {"value": "970", "unit": "MPa"},
        "elongation":         {"value": "6",   "unit": "%"},
        "hardness":           {"value": "300", "unit": "HV"}
      },
      "electrical_properties": {
        "electrical_conductivity": {"value": "12", "unit": "%IACS"}
      },
      "bending_performance": "按规则 §10 固定格式拼接；例：parallel to RD, 90° bend, no crack (t=0.15 mm, R/t=2)",
      "microstructure_description": "该条件下的组织描述（相组成、析出相 β'-Cu4Ti、晶粒/位错等）"
    }
  ],
  "figures": [
    {
      "figure_id": "Figure 1a",
      "placeholder_index": 1,
      "figure_type": "OM | SEM | TEM | EBSD | XRD | stress_strain_curve | schematic | other",
      "is_microstructure_image": true,
      "is_post_test_image": false,
      "sample_id": "S1",
      "condition_id": "C1",
      "caption": "图片标题",
      "scale_bar_info": {"value": "50", "unit": "μm"},
      "image_purpose": "before_test_microstructure | sample_level_microstructure | heat_treated_microstructure | post_test_fractography | fracture_surface | mechanical_curve | diffraction | schematic | other"
    }
  ]
}

## 关键规则（必须严格遵守）

### 1. 样品识别（极其重要）
- 样品（sample）= 论文中**作为研究对象的合金实体**（化学成分独特或初始工艺独特）
- 同一样品的不同热处理态/时效温度时间/冷变形量 → 属于 **conditions**，不是新样品
- 例如：同一 Cu-4Ti 的 ST900 / A450-120min / CR50+A450 = **1 个样品 + 多个 conditions**
- 例如：Cu-2.7Ti / Cu-3.5Ti / Cu-4.3Ti（Ti 含量不同）= 3 个样品
- **禁止**把原料/试剂/纳米粉末本身当成样品（如 Nb nanopowder、pure Cu rod、Ti sponge）——这些只是制备用料

### 2. product_form（sample 级）填写规则
- 必须从枚举值中选择，**禁止自创类别**
- 推断优先级：论文明确声明 > 实验描述暗示 > 默认 other
- 常见对应：sheet(薄板), strip(带材), foil(箔材), plate(厚板), bar/rod(棒材), wire(线材), pipe/tube(管材), forging(锻件), casting(铸件), powder(粉末), bulk(块体)
- 无法确定 → other

### 3. alloy_family（sample 级，极其重要）
- 由**有意添加的合金元素**归一成族名短串，**不含含量数字**
- 格式：二元写 `Cu-Ti`；多元写 `Cu-Ti-<其余元素按字母序>`，如 `Cu-Ti-Cr-Fe`、`Cu-Ti-Ni-Si`、`Cu-Ti-Cr-Mg-Si`
- 只计设计合金元素，**忽略**杂质/偶然检出（如微量 Zn、意外 Fe）；若 Fe/Cr 等为论文明确添加的合金元素则计入
- 例：Cu-3Ti → `Cu-Ti`；Cu-3Ti-0.2Fe-0.2Cr → `Cu-Ti-Cr-Fe`；Cu-3Ti-3Ni-0.5Si → `Cu-Ti-Ni-Si`；Cu-2.57Ti-0.35Cr-0.11Mg-0.04Si → `Cu-Ti-Cr-Mg-Si`
- 每个 sample 必填；同族不同 Ti 含量仍共用同一 alloy_family（如 Cu-2.7Ti 与 Cu-4.3Ti 都是 `Cu-Ti`）

### 4. sample_processing_overview 与 sample_microstructure_overview
- 固定格式、去修饰词；各 ≤200 字符；显微手段仅弱标注
- processing 例：`"Cu-4Ti, solution treated 900°C/1h WQ, cold rolled 50%, aged 450°C/120min"`
- microstructure 例：`"α-Cu + β'-Cu4Ti precipitates ~10 nm, grain size ~20 μm, cellular lamellae"`

### 5. condition 筛选（控制数量）
- **只建有明确性能数字的 condition**（正文/表中有 YS、UTS、EL、HV、EC、弯曲之一）；无性能数字的工艺态不要建
- 时效/变形矩阵**禁止全表展开**；优先：as-ST、peak-aged、over-aged、文中最优/对比点、冷轧前后关键点
- 全文 conditions **≤15**；超了按上面优先级保留

### 6. condition_name（极其重要）
- **必须用论文中给该条件起的简短代号**：ST900、A450-120min、CR50+A450、peak-aged、as-solution-treated 等
- **不要在 condition_name 中堆砌完整工艺描述**
- 反例：❌ condition_name = "A450 (aged at 450°C for 120 min after 50% cold rolling)"
- 正例：✅ condition_name = "A450"

### 7. solution_treatment / aging / cold_rolling（condition 级定格式文本）
均为短字符串；无明确信息则整字段省略（勿写 none/N/A）。取值必须对应该 condition 自身。
- `solution_treatment`：`<T>/<t>, <cooling>`，冷却用 WQ/AC/FC；例 `"900°C/4h, WQ"`
- `aging`：`<T>/<t>`，多步用 ` + ` 拼接；例 `"450°C/60min"`、`"300°C/2h + 450°C/7h"`（温度统一 °C）
- `cold_rolling`：压下率，多级用 ` + `；例 `"50%"`、`"85% + 90%"`。仅冷轧，拉拔写入 description
- T/t/压下率写入上述三字段；`condition_processing_description` 只补气氛、工序顺序、拉拔等残余信息，勿重复抄写

### 8. condition_processing_description（必须随 condition 变化）
- 每个 condition 写自己独有的残余工艺细节，例如：
  - C1 (ST900): "Ar atmosphere during solution treatment"
  - C2 (peak-aged): "Aged after 97.5% cold rolling to 0.1 mm foil"
  - C3 (CR50+A450): "Cold rolled after solution treatment, then aged"
- **绝对不要**让所有 condition 共享同一段笼统工艺
- 样品级公共工艺（冶炼、铸造、热轧成材、均匀化）放到 sample.base_processing_description

### 9. condition_type 严格区分
- `processing_condition`: 不同工艺态（固溶/时效/冷轧/退火等）
- `microstructure_condition`: 仅描述组织态
- `mechanical_test_condition`: 拉伸等测试条件
- `post_test_condition`: 断后样品（fractured sample, post-tensile）

### 10. mechanical_properties / electrical_properties
- 室温优先；单位按原文不换算；无则省略
- 来源：正文/表格明确数字 > 图中清晰标注；禁止目估曲线、禁止内插中间成分
- 只抽本文实测，不抽综述对比数据

### 11. bending_performance
- 仅本文弯曲试验；引言泛谈则省略；≤100 字符
- 模板：`<direction>, <angle> bend, <result> (<t, R/t...>)`；定性可用 `loop bend, few microcracks`

### 12. Figure → Sample 映射
- 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition
- caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample
- 多 panel 图为每个 panel 输出独立 figures 条目（figure_id="Figure 1a"、"Figure 1b" 等）
- 无法判断归属时：sample_id = null

### 13. 图片类型判定（看图本身 + 看 caption）
- OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）
- SEM = 扫描电镜（高分辨灰度组织/断口）
- TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）
- EBSD = 反极图/取向图（彩色 IPF）
- XRD = X射线衍射图（曲线图，有 2θ 横坐标）
- 注意：论文偶有把 SEM 写成 EPMA 的错误，请以图像内容为准

### 14. is_microstructure_image 与 is_post_test_image（极其重要）
- `is_microstructure_image=true` 且 `is_post_test_image=false`：组织观察图（before-test）
- `is_post_test_image=true`：断后断口、断后 TEM/SEM（fractured sample 的所有图）、力学曲线
- caption 含 "fractured"、"post-test"、"after tensile"、"interrupted tensile"、"deformed to fracture" 等 → 必为 is_post_test_image=true
- XRD 衍射图、示意图、力学曲线 → is_microstructure_image=false

### 15. placeholder_index
- 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致

## 输出要求
- **直接输出 JSON 对象本身**，不要任何 markdown 代码块包裹（不要 ```json）
- **不要任何开场白**，不要"Here is..."、"I'll analyze..."、"Based on..."、"I'm Claude..."等任何前言
- 第一个字符必须是 {，最后一个字符必须是 }
- 所有字符串值不要包含未转义的引号或换行
- 不要输出 paper_metadata.doi（系统会自动从 paper_id 推断）
- caption 字段保持精简（≤80 字符），避免完整复制论文 caption
- microstructure_description 控制在 ≤150 字符
- condition_processing_description 控制在 ≤200 字符
- solution_treatment / aging / cold_rolling 各 ≤80 字符
- bending_performance 控制在 ≤100 字符
- 对于明显非组织的图（schematic、stress-strain curve），只输出最小信息：figure_id/placeholder_index/figure_type/is_microstructure_image=false，其他字段可省略
"""


def build_extraction_prompt(text_with_placeholders: str, image_count: int) -> str:
    return f"""{JSON_SCHEMA_PROMPT}

## 论文内容

下面是论文的完整文本（{image_count} 张图片已按顺序作为附件传入，对应文本中的 [FIGURE_PLACEHOLDER_n]）：

{text_with_placeholders}

请仔细识别论文中**真正独立的 Cu-Ti 样品数量**（注意不要把同一样品的不同固溶/时效/冷变形态错拆成多个样品），为每个 sample 填写 alloy_family，为每个 condition 按定格式填写 solution_treatment / aging / cold_rolling（无则省略），输出严格 JSON。
"""


def extract_one_paper(paper_id: str, *, overwrite: bool = False) -> dict:
    """对单篇论文执行抽取。"""
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

    prompt = build_extraction_prompt(parsed.text_with_placeholders, len(parsed.images))

    # 保存 prompt 供调试
    debug_dir = output_dir / "_debug"
    debug_dir.mkdir(exist_ok=True)
    (debug_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    (debug_dir / "image_index.json").write_text(
        json.dumps([
            {"index": img.index, "label": img.label, "alt": img.alt, "media_type": img.media_type,
             "nearby": img.nearby_text[:300]}
            for img in parsed.images
        ], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[INFO] 调用 LLM（多模态，含 {len(images_payload)} 张图片）...")
    t0 = time.time()
    raw_response = call_multimodal(
        text_prompt=prompt,
        images=images_payload,
        system_prompt=SYSTEM_PROMPT,
        max_tokens=16384,  # GPUGeek 单次上限
        timeout=900,  # 15 分钟
    )
    elapsed = time.time() - t0
    print(f"[INFO] LLM 响应耗时: {elapsed:.1f}s | 长度: {len(raw_response)} 字符")

    (debug_dir / "raw_response.txt").write_text(raw_response, encoding="utf-8")

    try:
        data = parse_json_strict(raw_response)
    except ValueError as e:
        print(f"[ERROR] JSON 解析失败: {e}")
        raise

    # 把图片资源信息附加进 JSON（供后续 export 用）
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

    paper_json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] 保存: {paper_json_path}")

    # 同时把图片拷贝到 outputs/<paper_id>/images_raw/ 供 export 使用
    images_raw_dir = output_dir / "images_raw"
    images_raw_dir.mkdir(exist_ok=True)
    import base64
    for img in parsed.images:
        ext = img.media_type.split("/")[-1]
        if ext == "jpeg":
            ext = "jpg"
        fname = f"placeholder_{img.index:03d}.{ext}"
        (images_raw_dir / fname).write_bytes(base64.b64decode(img.data_b64))

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Cu-Ti 多模态信息抽取")
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

    print(f"[INFO] 共 {len(paper_ids)} 篇论文待处理")
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
