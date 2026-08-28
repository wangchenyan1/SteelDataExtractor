"""无磁钢专用：多模态信息抽取脚本。

复用 paper_processing_v4/scripts/ 下的 llm_client.py + paper_parser.py，
按"无磁钢"字段清单（原文明示化学成分 / 轧制工艺5项 / 微观组织 / 磁性能 / 力学性能含 77K 冲击）
输出严格 JSON。

输入：无磁钢/parsed_results/<paper_id>/paper.md
输出：无磁钢/outputs/<paper_id>/paper.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

# 把项目根的 scripts/ 加入 import 路径，复用 LLM 客户端和 paper 解析器
PROJECT_DIR = Path(__file__).resolve().parents[2]  # paper_processing_v4/
SHARED_SCRIPTS = PROJECT_DIR / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from llm_client import call_multimodal, parse_json_strict  # noqa: E402
from paper_parser import parse_paper_md  # noqa: E402


SUBPROJECT_DIR = Path(__file__).resolve().parents[1]   # 无磁钢/
PARSED_DIR = SUBPROJECT_DIR / "parsed_results"
OUTPUT_DIR = SUBPROJECT_DIR / "outputs"
LOG_DIR = SUBPROJECT_DIR / "logs"


SYSTEM_PROMPT = """你是钢铁/金属材料学术论文的结构化抽取专家，专门负责"无磁钢（non-magnetic / paramagnetic / austenitic Mn steel / 高锰奥氏体无磁钢）"领域的论文。你必须严格按照用户给出的 JSON Schema 输出，禁止任何额外解释。所有字段名以英文输出；样品名（sample_name）严格保留论文原文写法。"""


# 严格 JSON Schema
JSON_SCHEMA_PROMPT = """
请输出一个严格的 JSON 对象，结构如下：

{
  "paper_metadata": {
    "title": "...",
    "material_system": "钢种/合金体系简短描述（如 high-Mn non-magnetic steel, Cr-Mn-N austenitic steel）"
  },
  "samples": [
    {
      "sample_id": "S1",
      "sample_name": "论文中样品的原始命名",
      "product_form": "plate | sheet | bar | rod | rebar | wire | pipe | tube | angle_steel | pin | forging | casting | powder | bulk | target | other | not_specified",
      "alloy_family": "Fe-Mn-Al-C | Mn-Cr-N | Mn-Cr-Mo-Ni 等（具体根据样品原始命名和元素组成而定）",
      "composition": {
        "C": "0.45", "Si": "0.35", "Mn": "18.5",
        "P": "0.020", "S": "0.005", "Cr": "3.5", "Ni": "0.20",
        "Mo": "0.10", "N": "0.05", "Nb": "0.02", "V": "0.05",
        "Cu": "0.10", "Al": "0.03"
      },
      "composition_unit": "wt.%",
      "base_processing_description": "样品级公共工艺（冶炼、锻造等所有 condition 共享部分）",
      "sample_processing_overview": "样品整体工艺关键参数（固定格式提取，去除修饰词）：钢号/材料名（如 AISI 304, 18Mn, Cr-Mn-N）、钢种大类（无磁钢/高锰奥氏体钢/奥氏体不锈钢）、热处理状态（annealed/quenched/tempered/normalized/solution treated）、关键温度与时间（如 solution treated at 1100°C for 30 min）、加工状态（hot rolled/cold rolled/forged/as-cast）、状态短语（as-received/as-quenched/as-tempered）",
      "sample_microstructure_overview": "样品整体组织关键特征（固定格式提取，去除修饰词）：相组成（austenite/ferrite/martensite/bainite/pearlite）、残余奥氏体分数（retained austenite fraction）、晶粒尺寸（grain size/mean austenite grain size）、析出相（carbide/NbC/VN/precipitate size）、组织形貌（lath/acicular/polygonal/equiaxed/twinned）。显微手段（OM/SEM/TEM/EBSD）仅作弱信息标注"
    }
  ],
  "conditions": [
    {
      "condition_id": "C1",
      "sample_id": "S1",
      "condition_name": "条件名（极简代号，如 HR, ST1100, A900-15min, as-rolled）",
      "condition_type": "processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition",
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
      "magnetic_properties": {
        "permeability": {"value": "1.003", "unit": "(relative)"},
        "remanence":    {"value": "0.5",   "unit": "Gs"},
        "saturation_magnetization": {"value": "1.2", "unit": "emu/g"},
        "coercivity": {"value": "12", "unit": "Oe"},
        "curie_temperature": {"value": "580", "unit": "°C"},
        "neel_temperature": {"value": "120", "unit": "K"},
        "austenite_stability": "stable, no α'-martensite after 20% cold rolling, SFE=30 mJ/m²",
        "martensite_transformation_temperature": "Ms=-80°C, Md30=-40°C"
      },
      "mechanical_properties": {
        "yield_strength":     {"value": "650", "unit": "MPa"},
        "tensile_strength":   {"value": "950", "unit": "MPa"},
        "elongation":         {"value": "45",  "unit": "%"},
        "elastic_modulus":    {"value": "200", "unit": "GPa"},
        "hardness":           {"value": "220", "unit": "HV"},
        "impact_77K":         {"value": "120", "unit": "J"}
      }
    }
  ],
  "figures": [
    {
      "figure_id": "Figure 1a",
      "placeholder_index": 1,
      "figure_type": "OM | SEM | TEM | EBSD | XRD | stress_strain_curve | hysteresis_loop | schematic | other",
      "is_microstructure_image": true,
      "is_post_test_image": false,
      "sample_id": "S1",
      "condition_id": "C1",
      "caption": "图片标题（≤80 字符）",
      "scale_bar_info": {"value": "50", "unit": "μm"},
      "image_purpose": "before_test_microstructure | sample_level_microstructure | heat_treated_microstructure | post_test_fractography | fracture_surface | mechanical_curve | magnetic_curve | diffraction | schematic | other"
    }
  ]
}

## 关键规则（必须严格遵守）

### 1. 样品识别（极其重要）
- 样品（sample）= 论文中**化学成分独特**或**初始工艺独特**的材料实体
- 同一样品的不同热处理态/不同退火温度/不同冷却条件 → 属于 **conditions**，不是新样品
- 例如：同一 18Mn 钢的 HR / ST1050 / ST1100 / ST1150 = **1 个样品 + 4 个 conditions**
- 例如：Mn 含量不同的 13Mn / 18Mn / 23Mn = 3 个样品

### 2. product_form 填写规则
- 必须从枚举值中选择，**禁止自创类别**
- 推断优先级：论文明确声明 > 实验描述暗示 > 默认 other
- 常见对应：plate(板材/薄板), bar(棒材/圆棒), rebar(钢筋), wire(线材), pipe(管材), angle_steel(角钢), pin(销轴), forging(锻件), casting(铸件), powder(粉末), bulk(块体), target(靶材)
- 无法确定 → other，不要瞎猜，不要把文中提到的参考文献的样品形态套到文献样品中



### 化学成分抽取（极其重要）
- composition 只填写论文成分表、正文或图表中**明确给出的元素和值**，不要为了凑字段补全元素
- 严禁默认添加 `"Fe": "bal."`；只有原文明确写出 `Fe balance`、`Fe bal.`、`balance Fe`、`Fe for balance`、`rest Fe`、`remainder Fe` 等含义时，才可以填写 Fe 为 `bal.`
- 合金名或名义成分写成 `Fe-26Mn-11Al-1.15C`、`Fe-xMn-yAl-zC`、`Fe-34.5Ni-5Cr...`，**不等于**原文给出了 `Fe=bal.`；这种情况只抽取 Mn/Al/C/Ni/Cr 等明示数值，不要自动补 `Fe: bal.`
- 如果表格/正文给出 Fe 的明确数值（如 at.% 表中 Fe=50.0，或 wt.% 表中 Fe=66.00），则按原数值填写 Fe；不要把明确数值改成 `bal.`
- 原文只说 steel / non-magnetic steel / iron-rich / Fe-X binary alloy components / iron content 等材料背景，不等于给出了成分表中的 Fe；这种情况不要输出 Fe
- 某元素未在原文成分中明确出现时，直接省略该元素，不要填 `0`、`unknown`、`not reported` 或示例值

### 3. condition_name（极其重要）
- **必须用论文中给该条件起的简短代号**：HR、CR、ST1100、A900-15min 等
- **不要在 condition_name 中堆砌完整工艺描述**

### 4. condition_processing_description（极其重要：必须随 condition 变化）
- 每个 condition 必须有**自己独有的**工艺细节
- **绝对不要**让所有 condition 共享同一段笼统工艺
- 样品级公共工艺（冶炼成材）放到 sample.base_processing_description

### 5. condition_type 严格区分
- `processing_condition`: 不同工艺态 
- `microstructure_condition`: 仅描述组织态 
- `mechanical_test_condition`: 性能测试条件 
- `post_test_condition`: 断后样品（fractured, post-tensile）

### 6. rolling_processing（轧制工艺）规则
- 5 项："heating_temperature"（加热/再加热温度）、"start_rolling_temperature"（开轧温度）、"finish_rolling_temperature"（终轧/精轧温度）、"reduction_ratio"（总压下率/累计压下率，单位 % 或道次记 pass 时换算）、"cooling_rate"（轧后冷却速率 / 控冷速率）
- 论文中没明确给出的字段：**留空对象 {} 或省略**，不要瞎编
- 若某 condition 是 ST 固溶/退火态，没有轧制信息：rolling_processing 可整体省略

### 7. magnetic_properties（磁性能）规则
- "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）
- "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）
- "saturation_magnetization"（饱和磁化强度 Ms / σs(磁)，常见单位 emu/g、A/m、T、kA/m；勿与屈服强度 σs 混淆）
- "coercivity"（矫顽力 Hc，常见单位 Oe、A/m、kA/m）
- "curie_temperature"（居里温度 Tc，单位 °C 或 K，按原文，不换算）
- "neel_temperature"（奈尔温度 TN，单位 °C 或 K，按原文；勿与居里温度混淆）
- 上述数值型字段：论文未给出对应数值时不要瞎编，可省略该字段；单位按原文填写
- "austenite_stability"（奥氏体稳定性，固定格式字符串，≤150 字符，去除修饰词）：
  - 必须包含的要素（如论文中有）：稳定状态（stable/metastable/unstable）、变形后是否诱发马氏体（no α'-martensite / strain-induced α' detected）、关键量化指标（SFE=xx mJ/m²、Md30=xx°C、ΔGγ→α'=xx J/mol）、判定依据弱标注（XRD/magnetic/TEM）
  - 例如："stable, no α'-martensite after 20% cold rolling, SFE=30 mJ/m²"
  - 例如："metastable, strain-induced α' detected, Md30=-40°C"
- "martensite_transformation_temperature"（马氏体转变温度，固定格式字符串，≤150 字符，去除修饰词）：
  - 只抽取温度点：Ms / Mf / Md / Md30（含单位，按原文 °C 或 K，不换算），用逗号拼接
  - 例如："Ms=-80°C, Mf=-120°C, Md30=-40°C"
  - 无数值的定性描述不要填该字段

### 8. mechanical_properties（力学性能）规则
- 都默认室温拉伸；如果论文给出多个温度，则只把室温值放在该字段。不能根据图表信息预估，只抽取正文中的性能数据。
- "yield_strength"（屈服强度 σs / Rp0.2，MPa）
- "tensile_strength"（抗拉强度 σb / Rm，MPa）
- "elongation"（断后伸长率 δ / A，%）
- "elastic_modulus"（弹性模量 E，GPa）
- "hardness"（硬度 HV / HRC / HB，按论文标注单位）
- "impact_77K"（77K 液氮温度冲击功，J 或 J/cm²，按论文标注；如论文只给室温/0°C/-196°C 冲击值，注意 -196°C ≈ 77K，可填入该字段）

### 9. Figure → Sample 映射 & 图片类型
- OM / SEM / TEM / EBSD / XRD 按图像内容判定
- hysteresis_loop = 磁滞回线，is_microstructure_image=false
- 断后/拉断后/post-test 类图 → is_post_test_image=true → 不入数据库
- 力学曲线、磁滞回线、XRD、示意图 → is_microstructure_image=false

### 10. scale_bar_info（组织/形貌图比例尺提取）
- 对所有显微图片（组织图、断口形貌图等），必须尝试从图片上提取比例尺标注
- 常见格式：50 μm、200 nm、1 mm、500 nm、10 μm 等
- 如图片上确实没有比例尺标注（如曲线图、示意图、磁滞回线），填 null
- 注意区分比例尺（scale bar）和标尺文字，优先提取图片右下角/左下角的标注

### 11. sample_processing_overview 与 sample_microstructure_overview（样品级概述）
- sample_processing_overview：以固定格式提取样品整体工艺关键参数，尽量减少冗余修饰词
  - 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语
  - 例如："18Mn non-magnetic steel, austenitic stainless steel, solution treated at 1100°C for 30 min, water quenched, hot rolled"
- sample_microstructure_overview：以固定格式提取样品整体组织关键特征，尽量减少冗余修饰词
  - 必须包含的要素（如论文中有）：相组成、残余奥氏体分数、晶粒尺寸、析出相及尺寸、组织形貌
  - 例如："fully austenitic, grain size ~25 μm, annealing twins, NbC precipitates ~10-20 nm, equiaxed morphology"
  - 显微手段（OM/SEM/TEM/EBSD）仅作弱信息标注，不要过度拟合设备名称
- 两个字段控制在 ≤200 字符

### 12. is_microstructure_image 与 is_post_test_image（极其重要）
- `is_microstructure_image=true` 且 `is_post_test_image=false`：组织观察图（before-test）
- `is_post_test_image=true`：断后断口、断后 TEM/SEM/OM、拉伸后/变形后组织图、断口形貌图、力学曲线；caption 含 "fractured"、"fracture surface"、"fractograph"、"post-test"、"after tensile"、"tensile-tested"、"interrupted tensile"、"deformed to fracture"、"rupture" 等
- `is_microstructure_image` 与 `is_post_test_image` 是两个独立维度，不是互斥字段
- `is_microstructure_image=false`: XRD 衍射图、电子衍射图（electron diffraction / diffraction pattern）、微衍射图（microdiffraction / micro diffraction）、SAED/selected-area diffraction、相图/示意图、磁滞回线、磁化曲线、应力-应变曲线、性能曲线
- `is_microstructure_image=true`: TEM/SEM/OM/EBSD 中的组织形貌、断口形貌、变形后形貌 → 

### 13. placeholder_index
- 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致

## 输出要求
- **直接输出 JSON 对象本身**，不要任何 markdown 代码块包裹（不要 ```json）
- **不要任何开场白**，第一个字符必须是 {，最后一个字符必须是 }
- 不要输出 paper_metadata.doi（系统会自动从 paper_id 推断）
- caption ≤80 字符；microstructure.description ≤150 字符；condition_processing_description ≤200 字符
- sample_processing_overview 控制在 ≤200 字符
- sample_microstructure_overview 控制在 ≤200 字符
- austenite_stability 与 martensite_transformation_temperature 控制在 ≤150 字符
- 对于明显非组织的图（schematic、stress-strain、hysteresis loop、magnetization curve、XRD、electron diffraction、microdiffraction、SAED），只输出 figure_id/placeholder_index/figure_type/is_microstructure_image=false，其他字段可省略
- 组织/形貌图必须完整输出 scale_bar_info（有则填 value/unit，无则 null）
"""


def build_extraction_prompt(text_with_placeholders: str, image_count: int) -> str:
    return f"""{JSON_SCHEMA_PROMPT}

## 论文内容

下面是论文的完整文本（{image_count} 张图片已按顺序作为附件传入，对应文本中的 [FIGURE_PLACEHOLDER_n]）：

{text_with_placeholders}

请仔细识别论文中**真正独立的样品数量**（不要把同一样品的不同热处理态错拆成多个样品），并准确提取无磁钢相关字段（原文明示的化学成分、轧制工艺 5 项、组织、磁性能含饱和磁化/矫顽力/居里/奈尔/奥氏体稳定性/马氏体转变温度、室温力学性能、77K 冲击、product_form、sample_processing_overview、sample_microstructure_overview、以及显微图 scale_bar_info），输出严格 JSON。
"""


FE_BALANCE_RE = re.compile(
    r"\b(?:balance\s+Fe|Fe\s+(?:for\s+)?balance|Fe\s+bal\.?|"
    r"bal\.?\s+Fe|rest\s+Fe|remainder\s+Fe)\b|"
    r"\|\s*Fe\s*\|[\s\S]{0,800}\|\s*Bal\.?\s*\|",
    re.IGNORECASE,
)
FE_BALANCE_VALUES = {"bal", "bal.", "balance", "rest", "remainder"}
POST_TEST_CAPTION_RE = re.compile(
    r"fractur|post[- ]?test|after tensile|after tension|tensile[- ]tested|"
    r"interrupted tensile|deformed to fracture|fractograph|fracture surface|rupture",
    re.IGNORECASE,
)
NON_MICROSTRUCTURE_CAPTION_RE = re.compile(
    r"stress[- ]?strain|true[- ]?stress|engineering stress|hysteresis|"
    r"magneti[sz]ation curve|xrd|diffraction pattern|electron diffraction|"
    r"microdiffraction|micro diffraction|schematic|phase diagram|diagram|curve|plot",
    re.IGNORECASE,
)
NON_MICROSTRUCTURE_TYPES = {"stress_strain_curve", "hysteresis_loop", "schematic", "XRD", "xrd"}
MICROSCOPY_TYPES = {"OM", "SEM", "TEM", "EBSD"}
POST_TEST_MICRO_PURPOSES = {"post_test_fractography", "fracture_surface"}


def _compact_text(value: object, limit: int) -> str:
    """Normalize generated one-line summaries and keep hard schema limits."""
    if value in (None, ""):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" ,;.")


def _is_fe_balance_value(value: object) -> bool:
    return str(value or "").strip().lower() in FE_BALANCE_VALUES


def sanitize_extraction(data: dict, paper_text: str) -> list[str]:
    """Apply deterministic cleanup for errors repeatedly observed in LLM output."""
    warnings: list[str] = []
    has_fe_balance_evidence = bool(FE_BALANCE_RE.search(paper_text))
    samples = data.get("samples", []) or []

    for sample in samples:
        sample_name = sample.get("sample_name") or sample.get("sample_id") or "<unknown sample>"
        composition = sample.get("composition")
        if isinstance(composition, dict):
            fe_value = composition.get("Fe")
            if _is_fe_balance_value(fe_value) and not has_fe_balance_evidence:
                composition.pop("Fe", None)
                warnings.append(
                    f"{sample_name}: removed Fe=bal. because paper text has no explicit Fe-balance evidence"
                )
            elif "Fe" not in composition and composition and has_fe_balance_evidence and len(samples) == 1:
                composition["Fe"] = "bal."
                warnings.append(f"{sample_name}: added Fe=bal. from explicit Fe-balance evidence")

            bad_elements = [
                element for element, value in composition.items()
                if str(value).strip().lower() in {"unknown", "not reported", "n/a", "na", "none"}
            ]
            for element in bad_elements:
                composition.pop(element, None)
                warnings.append(f"{sample_name}: removed placeholder composition value for {element}")

        for field, limit in (
            ("sample_processing_overview", 200),
            ("sample_microstructure_overview", 200),
            ("base_processing_description", 300),
        ):
            original = sample.get(field)
            cleaned = _compact_text(original, limit)
            if original not in (None, "") and cleaned != str(original):
                warnings.append(f"{sample_name}: compacted {field} to {limit} chars")
            if cleaned:
                sample[field] = cleaned

    for condition in data.get("conditions", []) or []:
        condition_name = condition.get("condition_name") or condition.get("condition_id") or "<unknown condition>"
        for field, limit in (("condition_name", 60), ("condition_processing_description", 200)):
            original = condition.get(field)
            cleaned = _compact_text(original, limit)
            if original not in (None, "") and cleaned != str(original):
                warnings.append(f"{condition_name}: compacted {field} to {limit} chars")
            if cleaned:
                condition[field] = cleaned

        microstructure = condition.get("microstructure")
        if isinstance(microstructure, dict):
            original = microstructure.get("description")
            cleaned = _compact_text(original, 150)
            if original not in (None, "") and cleaned != str(original):
                warnings.append(f"{condition_name}: compacted microstructure.description to 150 chars")
            if cleaned:
                microstructure["description"] = cleaned

        rolling = condition.get("rolling_processing")
        if isinstance(rolling, dict):
            for key in list(rolling):
                payload = rolling.get(key)
                if isinstance(payload, dict) and str(payload.get("value", "")).strip().lower() in {
                    "unknown", "not specified", "not reported", "n/a", "na", "none"
                }:
                    rolling.pop(key, None)
                    warnings.append(f"{condition_name}: removed placeholder rolling_processing.{key}")

    for figure in data.get("figures", []) or []:
        caption = _compact_text(figure.get("caption"), 80)
        if caption:
            figure["caption"] = caption
        caption_lower = caption.lower()
        figure_id = figure.get("figure_id", "<unknown figure>")
        if POST_TEST_CAPTION_RE.search(caption):
            if figure.get("is_post_test_image") is not True:
                warnings.append(f"{figure_id}: forced post-test flag from caption")
            figure["is_post_test_image"] = True
        figure_type = figure.get("figure_type")
        is_non_micro = (
            figure_type in NON_MICROSTRUCTURE_TYPES or NON_MICROSTRUCTURE_CAPTION_RE.search(caption_lower)
        )
        if figure.get("is_microstructure_image") is True and is_non_micro:
            figure["is_microstructure_image"] = False
            warnings.append(f"{figure_id}: cleared microstructure flag for curve/diffraction/schematic")
        elif (
            figure.get("is_post_test_image") is True
            and figure.get("is_microstructure_image") is not True
            and figure_type in MICROSCOPY_TYPES
            and (
                figure.get("image_purpose") in POST_TEST_MICRO_PURPOSES
                or POST_TEST_CAPTION_RE.search(caption)
            )
            and not is_non_micro
        ):
            figure["is_microstructure_image"] = True
            warnings.append(f"{figure_id}: set microstructure flag for post-test microscopy image")

    return warnings


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
        max_tokens=16384,
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

    validation_warnings = sanitize_extraction(data, parsed.text_with_placeholders)
    if validation_warnings:
        print(f"[WARN] 后处理清理/审计发现 {len(validation_warnings)} 项")
        (debug_dir / "validation_warnings.json").write_text(
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
