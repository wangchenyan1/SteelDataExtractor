"""多模态信息抽取脚本。

复用 paper_processing_v4/scripts/ 下的 llm_client.py + paper_parser.py，
输出严格 JSON。

输入：cor_res/parsed_results/<paper_id>/paper.md
输出：cor_res/outputs/<paper_id>/paper.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

# 把共享 scripts/ 加入 import 路径，复用 LLM 客户端和 paper 解析器
EXTRACT_DATA_DIR = Path("/internfs/wangchenyan/shougang/Extract_data")
SUBPROJECT_DIR = EXTRACT_DATA_DIR / "cor_res"
SHARED_SCRIPTS = EXTRACT_DATA_DIR / "initial_version" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from llm_client import call_multimodal, parse_json_strict  # noqa: E402
from paper_parser import parse_paper_md  # noqa: E402


PARSED_DIR = SUBPROJECT_DIR / "parsed_results"
OUTPUT_DIR = SUBPROJECT_DIR / "outputs"
LOG_DIR = SUBPROJECT_DIR / "logs"


SYSTEM_PROMPT = """你是钢铁/金属材料学术论文的结构化抽取专家，专门负责"耐腐蚀（corrosion resistance）"领域的论文。你必须严格按照用户给出的 JSON Schema 输出，禁止任何额外解释。所有字段名以英文输出；样品名（sample_name）严格保留论文原文写法。"""


# 严格 JSON Schema
JSON_SCHEMA_PROMPT = """
请输出一个严格的 JSON 对象，结构如下：

{
  "paper_metadata": {
    "title": "...",
    "material_system": "钢种/合金体系简短描述（如 Nb-Mo HSLA steel, 4Mn medium-Mn TRIP steel）"
  },
  "samples": [
    {
      "sample_id": "S1",
      "sample_name": "论文中样品的原始命名（如 Nb-Ti steel, Nb-Mo steel, low carbon steel）",
      "product_form": "plate | sheet | bar | rod | rebar | wire | pipe | tube | angle_steel | pin | forging | casting | powder | bulk | target | other ",
      "composition": {
        "C": "0.039", "Mn": "1.10", "Si": "0.26",
        "Nb": "0.055", "Ti": "0.015", "N": "0.0012"
      },
      "composition_unit": "wt.%",
      "base_processing_description": "样品级公共工艺（冶炼、锻造等所有 condition 共享部分）",
      "sample_processing_overview": "样品整体工艺关键参数（固定格式提取，去除修饰词）：钢号/材料名（如 AISI 304, 4140, H13, D2）、钢种大类（不锈钢/工具钢/轴承钢/低合金钢/马氏体钢）、热处理状态（annealed/quenched/tempered/normalized/solution treated）、关键温度与时间（如 austenitized at 850°C, tempered at 600°C for 2h）、加工状态（hot rolled/cold rolled/forged/as-cast）、状态短语（as-received/as-quenched/as-tempered）",
      "sample_microstructure_overview": "样品整体组织关键特征（固定格式提取，去除修饰词）：相组成（ferrite/martensite/bainite/austenite/pearlite）、残余奥氏体分数（retained austenite fraction）、晶粒尺寸（grain size/mean ferrite grain size）、析出相（carbide/TiC/NbC/(Nb,Mo)C/precipitate size）、组织形貌（lath/acicular/polygonal/equiaxed）。显微手段（OM/SEM/TEM/EPMA）仅作弱信息标注"
    }
  ],
  "conditions": [
    {
      "condition_id": "C1",
      "sample_id": "S1",
      "condition_name": "条件名（极简代号，如 HR, ST1100, A900-15min, as-rolled）",
      "condition_type": "processing_condition | microstructure_condition | mechanical_test_condition | corrosion_test_condition | post_test_condition",
      "condition_processing_description": "该条件独有的工艺细节（如 solution treated at 1100°C for 30 min, water quenched）。必须随 condition 不同而不同！",
      "rolling_processing": {
        "heating_temperature":         {"value": "1200", "unit": "°C"},
        "start_rolling_temperature":   {"value": "1100", "unit": "°C"},
        "finish_rolling_temperature":  {"value": "900",  "unit": "°C"},
        "reduction_ratio":             {"value": "80",   "unit": "%"},
        "cooling_rate":                {"value": "10",   "unit": "°C/s"}
      },
      "microstructure": {
        "grain_size": {"value": "15", "unit": "μm"},
        "description": "该条件下的组织描述（相组成、晶粒、孪晶/位错/析出等，≤150 字符）"
      },
      "mechanical_properties": {
        "yield_strength":     {"value": "650", "unit": "MPa"},
        "tensile_strength":   {"value": "950", "unit": "MPa"},
        "elongation":         {"value": "45",  "unit": "%"}
      }
    }
  ],
  "figures": [
    {
      "figure_id": "Figure 1a",
      "placeholder_index": 1,
      "figure_type": "OM | SEM | TEM | EBSD | XRD | EDS | stress_strain_curve | polarization_curve | EIS | schematic | other",
      "is_microstructure_image": true,
      "is_post_test_image": false,
      "sample_id": "S1",
      "condition_id": "C1",
      "caption": "图片标题（≤80 字符）",
      "scale_bar_info": {"value": "50", "unit": "μm"},
      "image_purpose": [
  "before_test_microstructure | sample_level_microstructure | heat_treated_microstructure | post_test_fractography | fracture_surface | corrosion_morphology | corrosion_electrochemistry | corrosion_test_summary | mechanical_curve | magnetic_curve | diffraction | schematic | other"
]
    }
  ]
}

## 关键规则（必须严格遵守）

### 1. 样品识别（极其重要）
- 样品（sample）= 论文中**化学成分独特**或**初始工艺/材料角色独特**的材料实体
- 同一样品的不同热处理态/不同退火温度/不同冷却条件/不同腐蚀暴露时长 → 属于 **conditions**，不是新样品
- 例如：同一 18Mn 钢的 HR / ST1050 / ST1100 / ST1150 = **1 个样品 + 4 个 conditions**
- 例如：Mn 含量不同的 13Mn / 18Mn / 23Mn = 3 个样品
- **必须拆成多个样品**的常见情形（成分不同或材料角色不同）：
  - 名义成分不同的钢种/合金牌号
  - 焊缝金属 vs 母材、堆焊层 vs 基体、涂层 vs 基体、焊丝/填充金属 vs 母材
  - 对比用的对照钢 / 商用钢 / 异种材料（只要成分表或正文给出独立成分）
- **禁止**把多个材料名用 `/`、`+`、`and` 等拼成一个 `sample_name`；应拆成独立 sample，各自保留原文命名
- 每个 sample 只对应自己的 composition；不要把 A 材料的成分填到 B 材料上，也不要因为只找到一张成分表就合并样品

### 2. product_form 填写规则
- 必须从枚举值中选择，**禁止自创类别**
- 推断优先级：论文明确声明 > 实验描述暗示 > 默认 other
- 常见对应：plate(板材/薄板), bar(棒材/圆棒), rebar(钢筋), wire(线材), pipe(管材), angle_steel(角钢), pin(销轴), forging(锻件), casting(铸件), powder(粉末), bulk(块体), target(靶材)
- 无法确定 → other

### 3. 化学成分抽取（极其重要：按表头映射，禁止列错位）
- composition 只填写论文成分表、正文或图表中**明确给出的元素和值**，不要为了凑字段补全元素
- **必须按列头/元素符号一一对应取值**；严禁因某格为空就把右侧或下一列数值挪到当前元素
- 单元格为 `N.d.` / `n.d.` / `n.d` / `ND` / `n/a` / `—` / `-` / 空白 / `not detected` 时：
  - **直接省略该元素**，不要填 `N.d.`，更不要用相邻列的数值顶替
  - 尤其常见错误：C 为未检出时把 Si 值误写入 C、再把 Si 标成 `N.d.` —— 必须避免
- 微量元素（N、O、S、P、B、Ti、Nb、V、Al 等）只要原文对该样品明确给出数值，就必须抽取，不要漏提
- 严禁默认添加 `"Fe": "bal."`；只有原文明确写出 `Fe balance`、`Fe bal.`、`balance Fe`、`rest Fe`、`remainder Fe` 等含义时，才可以填写 Fe 为 `bal.`
- 某元素未在原文成分中明确出现时，直接省略该元素，不要填 `0`、`unknown`、`not reported` 或示例值
- 成分表按样品分行/分列时：先对齐样品名与行/列，再读数；多张表时分别归属到对应 sample

### 4. condition_id / condition_name（极其重要）
- `condition_id` 在**整篇论文内必须唯一**（C1、C2、C3… 不重复）；不同 sample 的条件也不能共用同一个 `condition_id`
- `condition_name` **必须用论文中给该条件起的简短代号**：A700、A720、TP000、HR、as-rolled、14d、28d 等
- **不要在 condition_name 中堆砌完整工艺描述**
- 反例：❌ condition_name = "A720 (intercritically annealed at 720°C for 60min)"
- 正例：✅ condition_name = "A720"
- 同一工艺/暴露代号若分别作用于多个 sample，应输出多条 condition（不同 `condition_id` + 各自 `sample_id`），`condition_name` 可相同

### 5. condition_processing_description（极其重要：必须随 condition 变化）
- 每个 condition 必须有**自己独有的**工艺细节，例如：
  - C1 (as-hot-rolled): "Hot-rolled state, no further annealing"
  - C2 (A700): "Intercritically annealed at 700°C for 60 min, air cooled"
  - C3 (A720): "Intercritically annealed at 720°C for 60 min, air cooled"
- **绝对不要**让所有 condition 共享同一段含"700/720/740/760°C"的笼统工艺
- 样品级公共工艺（冶炼、锻造、热轧成材）放到 sample.base_processing_description

### 6. condition_type 严格区分
- `processing_condition`: 不同工艺态（退火/淬火/回火/轧制等）
- `microstructure_condition`: 仅描述组织态（如初始态 vs 退火态对比）
- `mechanical_test_condition`: 拉伸/Charpy/疲劳测试条件
- `corrosion_test_condition`: 以腐蚀试验参数区分的条件（盐雾时长、浸泡介质/时长、电化学测试工况等）
- `post_test_condition`: 断后样品（fractured sample, post-tensile, post-fatigue）或腐蚀后样品形貌条件

### 7. rolling_processing（轧制工艺）规则
- 5 项："heating_temperature"（加热/再加热温度）、"start_rolling_temperature"（开轧温度）、"finish_rolling_temperature"（终轧/精轧温度）、"reduction_ratio"（总压下率/累计压下率，单位 % 或道次记 pass 时换算）、"cooling_rate"（轧后冷却速率 / 控冷速率）
- 论文中没明确给出的字段：**留空对象 {} 或省略**，不要瞎编
- 若某 condition 是 ST 固溶/退火态，没有轧制信息：rolling_processing 可整体省略

### 8. Figure → Sample 映射
- 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition
- caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample
- 多 panel 图为每个 panel 输出独立 figures 条目（figure_id="Figure 1a"、"Figure 1b" 等）
- 无法判断归属时：sample_id = null

### 9. 图片类型判定（看图本身 + 看 caption）
- OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）
- SEM = 扫描电镜（高分辨灰度组织/断口/腐蚀形貌）
- TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）
- EBSD = 反极图/取向图（彩色 IPF）
- XRD = X射线衍射图（曲线图，有 2θ 横坐标）
- EDS = 能谱分析（元素分布图/谱线）
- polarization_curve = 极化曲线（电化学极化测试结果）
- EIS = 电化学阻抗谱（Nyquist 图/Bode 图）
- 注意：论文偶有把 SEM 写成 EPMA 的错误，请以图像内容为准

### 10. is_microstructure_image 与 is_post_test_image（极其重要）
- `is_microstructure_image` 表示是否为**显微形貌类图像**，与是否测试后**解耦**：
  - `true`：OM / SEM / TEM / EBSD 等显微图，包括测试前组织、断口形貌、腐蚀形貌、磨损形貌等
  - `false`：曲线图、示意图、XRD 谱、宏观照片（非显微）、流程图等
- `is_post_test_image` 表示是否为**测试后/腐蚀后/服役后**图像：
  - caption 或上下文含 fractured / fracture surface / post-test / after tensile / after corrosion / after salt spray / corrosion morphology / rust layer 等 → `is_post_test_image=true`
  - 测试前组织、工艺态组织、样品级初始组织 → `is_post_test_image=false`
- 因此：断口 SEM、腐蚀形貌 SEM/OM **通常**为 `is_microstructure_image=true` 且 `is_post_test_image=true`（不要因为是断口/腐蚀形貌就设 micro=false）
- 力学曲线、极化曲线、EIS、XRD、示意图 → `is_microstructure_image=false`；其中测试结果曲线可同时 `is_post_test_image=true`
- 入库存过滤由下游根据 `is_post_test_image` / `image_purpose` 处理；抽取阶段不要用 micro=false 去“代替” post_test 标记

### 11. image_purpose 标注规则
- image_purpose 必须输出为字符串数组，即使只有一个目的也写成数组，如 ["corrosion_morphology"]
- 可多选；同一张图同时满足多个用途时，把所有适用标签都放入数组
- 断口类可用 `post_test_fractography` / `fracture_surface`；腐蚀形貌用 `corrosion_morphology`；极化/EIS 用 `corrosion_electrochemistry`
- 不确定时使用 ["other"]，不要强行归类

### 12. scale_bar_info（组织/形貌图比例尺提取）
- 对所有显微图片（组织图、腐蚀形貌图、断口图等），必须尝试从图片上提取比例尺标注
- 常见格式：50 μm、200 nm、1 mm、500 nm、10 μm 等
- 如图片上确实没有比例尺标注（如曲线图、示意图），填 null
- 注意区分比例尺（scale bar）和标尺文字，优先提取图片右下角/左下角的标注

### 13. sample_processing_overview 与 sample_microstructure_overview（样品级概述）
- sample_processing_overview：以固定格式提取样品整体工艺关键参数，减少冗余修饰词
  - 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语
  - 例如："AISI 4140, 低合金钢, quenched + tempered, austenitized at 860°C for 1h, tempered at 550°C for 2h, hot rolled"
- sample_microstructure_overview：以固定格式提取样品整体组织关键特征，减少冗余修饰词
  - 必须包含的要素（如论文中有）：相组成、残余奥氏体分数、晶粒尺寸、析出相及尺寸、组织形貌
  - 例如："tempered martensite + retained austenite (5.2%), prior austenite grain size ~20 μm, (Nb,Mo)C precipitates ~5-10 nm, lath morphology"
  - 显微手段（OM/SEM/TEM/EPMA）仅作弱信息标注，不要过度拟合设备名称
- 两个字段控制在 ≤200 字符

### 14. placeholder_index
- 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致


## 输出要求
- **直接输出 JSON 对象本身**，不要任何 markdown 代码块包裹（不要 ```json）
- **不要任何开场白**，不要"Here is..."、"I'll analyze..."、"Based on..."、"I'm Claude..."等任何前言
- 第一个字符必须是 {，最后一个字符必须是 }
- 所有字符串值不要包含未转义的引号或换行
- 不要输出 paper_metadata.doi（系统会自动从 paper_id 推断）
- caption 字段保持精简（≤80 字符），避免完整复制论文 caption
- microstructure.description 控制在 ≤150 字符
- condition_processing_description 控制在 ≤200 字符
- sample_processing_overview 控制在 ≤200 字符
- sample_microstructure_overview 控制在 ≤200 字符
- 对于明显非显微的图（schematic、stress-strain curve、polarization_curve、EIS、XRD），可只输出最小信息：figure_id/placeholder_index/figure_type/is_microstructure_image=false，其他字段可省略
- 显微形貌图（含断口、腐蚀形貌）必须完整输出所有字段（尤其 figure_type、image_purpose、scale_bar_info、is_microstructure_image、is_post_test_image），确保后续可通过 image_purpose 精准定位
"""


def build_extraction_prompt(text_with_placeholders: str, image_count: int) -> str:
    return f"""{JSON_SCHEMA_PROMPT}

## 论文内容

下面是论文的完整文本（{image_count} 张图片已按顺序作为附件传入，对应文本中的 [FIGURE_PLACEHOLDER_n]）：

{text_with_placeholders}

请仔细识别论文中**真正独立的样品数量**：不要把同一样品的不同热处理态/暴露时长错拆成多个样品；也不要把母材/焊缝/涂层/对照钢等成分不同的材料错误合并。成分表必须按元素列头对齐。准确提取耐腐蚀相关字段，输出严格 JSON。
"""


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

    prompt = build_extraction_prompt(parsed.text_with_placeholders, len(parsed.images))

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
        max_tokens=32768,
        timeout=900,
    )
    elapsed = time.time() - t0
    print(f"[INFO] LLM 响应耗时: {elapsed:.1f}s | 长度: {len(raw_response)} 字符")

    (debug_dir / "raw_response.txt").write_text(raw_response, encoding="utf-8")

    try:
        data = parse_json_strict(raw_response)
    except ValueError as e:
        print(f"[ERROR] JSON 解析失败: {e}")
        raise

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
    parser = argparse.ArgumentParser(description="无磁钢 多模态信息抽取")
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
