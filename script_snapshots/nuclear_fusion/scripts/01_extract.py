"""核聚变高强高韧低磁奥氏体不锈钢焊接文献多模态信息抽取脚本。

复用 paper_processing_v4/scripts/ 下的 llm_client.py + paper_parser.py，
按核聚变装置 4.2K 高强高韧奥氏体不锈钢焊材/焊接接头字段清单输出严格 JSON。

输入：nuclear_fusion/parsed_results/<paper_id>/paper.md
输出：nuclear_fusion/outputs/<paper_id>/paper.json
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


SUBPROJECT_DIR = Path(__file__).resolve().parents[1]   # nuclear_fusion/
PARSED_DIR = SUBPROJECT_DIR / "parsed_results"
OUTPUT_DIR = SUBPROJECT_DIR / "outputs"
LOG_DIR = SUBPROJECT_DIR / "logs"


SYSTEM_PROMPT = """你是钢铁/金属材料学术论文的结构化抽取专家，专门负责核聚变装置高强高韧低磁/无磁奥氏体不锈钢焊材、焊缝金属和焊接接头文献。你必须严格按照用户给出的 JSON Schema 输出，禁止任何额外解释。所有字段名以英文输出；样品名（sample_name）严格保留论文原文写法。"""


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
      "product_form": "plate | sheet | bar | rod | wire | pipe | tube | conduit | jacket | coil_case | weldment | weld_metal | filler_wire | forging | casting | bulk | other | not_specified",
      "alloy_family": "Cu-Mn-Nb-V-N | Cr-Mn-N | other",
      "composition": {
        "C": "0.45", "Si": "0.35", "Mn": "18.5",
        "P": "0.020", "S": "0.005", "Cr": "3.5", "Ni": "0.20",
        "Mo": "0.10", "N": "0.05", "Nb": "0.02", "V": "0.05",
        "Cu": "0.10", "Al": "0.03"
      },
      "composition_unit": "wt.%",
      "base_processing_description": "样品级公共工艺（冶炼、锻造等所有 condition 共享部分）",
      "sample_processing_overview": "样品整体工艺关键参数（固定格式提取，去除修饰词）：钢号/材料名（如 316LN, JJ1, JK2LB）、钢种大类（低磁/高氮/氮强化奥氏体不锈钢）、热处理状态（solution treated/aged/Nb3Sn reacted/as-welded）、关键温度与时间、加工状态（forged/rolled/welded/as-received）",
      "sample_microstructure_overview": "样品整体组织关键特征（固定格式提取，去除修饰词）：austenite/ferrite/delta-ferrite/martensite、晶粒尺寸、析出相、焊缝/HAZ组织、断裂相关组织。显微手段（OM/SEM/TEM/EBSD）仅作弱信息标注"
    }
  ],
  "conditions": [
    {
      "condition_id": "C1",
      "sample_id": "S1",
      "condition_name": "条件名（极简代号，如 as-welded, 4.2K, Nb3Sn-reacted, aged, HAZ, WM）",
      "condition_type": "processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition",
      "component_type": "armor | coil_case | conduit_jacket | magnet_structure | other | unclear",
      "joint_or_material_type": "base_metal | weld_metal | welded_joint | HAZ | deposited_metal | unclear",
      "welding_process": "TIG | GTAW | laser_welding | electron_beam_welding | NG-MAG | SAW | hybrid_welding | other | not_specified",
      "filler_material": "焊材/焊丝/填充金属原文名称，如 ER316LMn, FMYJJ1, 316L filler, none, not_specified",
      "heat_treatment_condition": "as-welded | Nb3Sn reacted | aged | solution treated | PWHT | other | not_specified；可保留原文温度时间",
      "test_temperature": {"value": "4.2", "unit": "K"},
      "condition_processing_description": "该条件独有的补充工艺/测试细节：板厚、坡口、试样位置、取向、热输入等低频信息合并写在这里。必须随 condition 不同而不同！",
      "microstructure": {
        "grain_size": {"value": "15", "unit": "μm"},
        "description": "该条件下的组织描述（相组成、晶粒、孪晶/位错/析出等，≤150 字符）"
      },
      "magnetic_properties": {
        "permeability": {"value": "1.003", "unit": "(relative)"}
      },
      "mechanical_properties": {
        "yield_strength":       {"value": "1350", "unit": "MPa"},
        "tensile_strength":     {"value": "1700", "unit": "MPa"},
        "elongation":           {"value": "20",   "unit": "%"},
        "fracture_toughness":   {"value": "150",  "unit": "MPa·m^1/2"}
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
- 样品拆分硬规则：不要按成分表、性能表或组织表的每一行机械拆分 sample。filler/welding wire/electrode、weld metal/weld zone/WZ、HAZ、BM 测试位置、deposited metal、coating/surface layer、fracture/tensile/impact specimen、top/bottom/center/interface 等默认不是新 sample，应作为 condition、filler_material、joint_or_material_type 或 condition_processing_description。只有原文明确将其作为独立制备和独立研究的材料体系时，才可创建新 sample。
- 例如：同一 18Mn 钢的 HR / ST1050 / ST1100 / ST1150 = **1 个样品 + 4 个 conditions**
- 例如：Mn 含量不同的 13Mn / 18Mn / 23Mn = 3 个样品
- 例如：表格中同时出现 SS316L 40 mm、SS316L 60 mm、Filler ER316L、Weld 40 mm、Weld 60 mm；如果论文研究对象是 40 mm 和 60 mm TIG welded SS316L plates，则只创建 2 个样品，Filler ER316L 写入 filler_material，Weld 40/60 mm 作为 welded_joint/weld_metal condition 的证据。

### 2. product_form 填写规则
- 必须从枚举值中选择，**禁止自创类别**
- 推断优先级：论文明确声明 > 实验描述暗示 > 默认 other
- 常见对应：plate(板材), sheet(薄板), bar/rod(棒材), wire/filler wire(焊丝), pipe/tube/conduit/jacket(管/导管/套管), coil_case(线圈盒), weldment/weld_metal(焊接件/焊缝金属), forging(锻件), casting(铸件), bulk(块体)
- 无法确定 → other，不要瞎猜，不要把参考文献的样品形态套到本文样品中

### 3. 化学成分抽取（极其重要）
- composition 只填写论文成分表、正文或图表中**明确给出的元素和值**，不要为了凑字段补全元素
- 严禁默认添加 `"Fe": "bal."`；只有原文明确写出 `Fe balance`、`Fe bal.`、`balance Fe`、`Fe for balance`、`rest Fe`、`remainder Fe` 等含义时，才可以填写 Fe 为 `bal.`
- 合金名或名义成分写成 `Fe-26Mn-11Al-1.15C`、`Fe-xMn-yAl-zC`、`Fe-34.5Ni-5Cr...`，**不等于**原文给出了 `Fe=bal.`；这种情况只抽取 Mn/Al/C/Ni/Cr 等明示数值，不要自动补 `Fe: bal.`
- 如果表格/正文给出 Fe 的明确数值（如 at.% 表中 Fe=50.0，或 wt.% 表中 Fe=66.00），则按原数值填写 Fe；不要把明确数值改成 `bal.`
- 原文只说 steel / non-magnetic steel / iron-rich / Fe-X binary alloy components / iron content 等材料背景，不等于给出了成分表中的 Fe；这种情况不要输出 Fe
- 某元素未在原文成分中明确出现时，直接省略该元素，不要填 `0`、`unknown`、`not reported` 或示例值

### 4. condition_name（极其重要）
- **必须用论文中给该条件起的简短代号**：HR、CR、ST1100、A900-15min 等
- **不要在 condition_name 中堆砌完整工艺描述**

### 5. condition_processing_description（极其重要：必须随 condition 变化）
- 每个 condition 必须有**自己独有的**工艺细节
- **绝对不要**让所有 condition 共享同一段笼统工艺
- 样品级公共工艺（冶炼成材）放到 sample.base_processing_description

### 6. condition_type 严格区分
- `processing_condition`: 不同工艺态 
- `microstructure_condition`: 仅描述组织态 
- `mechanical_test_condition`: 性能测试条件 
- `post_test_condition`: 断后样品（fractured, post-tensile）

### 7. 焊接/热处理/测试温度字段规则
- welding_process 表示焊接方法，必须从枚举中选择：TIG | GTAW | laser_welding | electron_beam_welding | NG-MAG | SAW | hybrid_welding | other | not_specified。
- filler_material 填写焊材、焊丝或填充金属的原文名称；无填充金属可写 none，未说明写 not_specified。
- heat_treatment_condition 填写该 condition 对应的热处理/服役前热循环，如 as-welded、Nb3Sn reacted、aged、solution treated、PWHT；如果原文给出温度和时间，应保留在同一字符串中。
- test_temperature 只填写这组性能数据对应的测试温度，如 4.2 K、4 K、77 K、RT；不要把热处理温度误填为测试温度。RT 必须写成 {"value":"RT","unit":""}。
- 板厚、坡口、焊接电流/电压、热输入、保护气、试样位置、取向等低频工艺细节统一写入 condition_processing_description，不作为独立字段。

### 8. component_type 与 joint_or_material_type 规则
- component_type 表示这组 condition/性能数据对应的核聚变工程对象，必须从枚举中选择：
  - armor：原文明示 armor / jacket armor / 结构铠甲相关焊接接头。
  - coil_case：原文明示 coil case / TF coil case / CS coil case / PF coil case / correction coil case / coil case structure。
  - conduit_jacket：原文明示 conduit / CICC jacket / cable-in-conduit conductor jacket / CS conduit。
  - magnet_structure：只说明 fusion magnet / superconducting magnet structure，但不能明确归入 coil_case 或 conduit_jacket。
  - other：核聚变相关但不是上述对象。
  - unclear：无法从论文判断。
- joint_or_material_type 表示性能数据测量对象，必须从枚举中选择：base_metal | weld_metal | welded_joint | HAZ | deposited_metal | unclear。
- “铠甲焊接接头”和“线圈盒焊接接头”不是处理状态；它们应拆成 component_type + joint_or_material_type。
- 如果同一论文同时给出 base metal、weld metal、HAZ、welded joint 或多个试样位置的数据，应建多个 condition，分别绑定对应性能。

### 9. magnetic_properties（磁性能）规则
- 只抽取 permeability（相对磁导率 μr 或 magnetic permeability）。
- 论文未给出 permeability 数值时省略 magnetic_properties 或留空对象；除 permeability 外，其他磁性能不作为独立字段抽取。
- 单位按原文填写；相对磁导率可写 unit="(relative)"。

### 10. mechanical_properties（力学性能）规则
- 优先抽取与核聚变装置 4.2K 焊接接头相关的实测性能；如果论文给出多个温度，分别建立 condition 或在 condition_processing_description 中明确温度。
- "yield_strength"（屈服强度 / 0.2% proof stress / Rp0.2 / YS，MPa）
- "tensile_strength"（抗拉强度 / UTS / Rm，MPa）
- "elongation"（断后伸长率 / total elongation / uniform elongation，%，如原文给出）
- "fracture_toughness"（断裂韧性 KIC/KJIC/KIC(J)/JIC/JQ/J-R），单位 MPa·m^1/2；如果原文只给 JIC，按原文单位填写，不要强行换算）
- 只抽取上述列出的力学性能字段；其他低频力学信息不作为独立字段。
- 以下内容禁止填入 mechanical_properties：
- Young's modulus / elastic modulus / shear modulus / bulk modulus / Poisson ratio
- hardness / impact toughness / Charpy / impact energy
- fatigue stress range / maximum stress / minimum stress / cycles / S-N / FCGR / da/dN / ΔK
- creep / thermal / electrical / magnetic / physical properties

### 11. Figure → Sample 映射 & 图片类型
- OM / SEM / TEM / EBSD / XRD 按图像内容判定

### 12. scale_bar_info（组织/形貌图比例尺提取）
- 对所有显微图片（组织图、断口形貌图等），必须尝试从图片上提取比例尺标注
- 常见格式：50 μm、200 nm、1 mm、500 nm、10 μm 等
- 如图片上确实没有比例尺标注（如曲线图、示意图、磁滞回线），填 null
- 注意区分比例尺（scale bar）和标尺文字，优先提取图片右下角/左下角的标注

### 13. sample_processing_overview 与 sample_microstructure_overview（样品级概述）
- sample_processing_overview：以固定格式提取样品整体工艺关键参数，尽量减少冗余修饰词
  - 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语
  - 例如："18Mn non-magnetic steel, austenitic stainless steel, solution treated at 1100°C for 30 min, water quenched, hot rolled"
- sample_microstructure_overview：以固定格式提取样品整体组织关键特征，尽量减少冗余修饰词
  - 必须包含的要素（如论文中有）：相组成、残余奥氏体分数、晶粒尺寸、析出相及尺寸、组织形貌
  - 例如："fully austenitic, grain size ~25 μm, annealing twins, NbC precipitates ~10-20 nm, equiaxed morphology"
  - 显微手段（OM/SEM/TEM/EBSD）仅作弱信息标注，不要过度拟合设备名称
- 两个字段控制在 ≤200 字符

### 14. is_microstructure_image 与 is_post_test_image（极其重要）
- `is_microstructure_image=true` 且 `is_post_test_image=false`：组织观察图（before-test）
- `is_post_test_image=true`：断后断口、断后 TEM/SEM/OM、拉伸后/变形后组织图、断口形貌图；caption 含 "fractured"、"fracture surface"、"fractograph"、"post-test"、"after tensile"、"tensile-tested"、"interrupted tensile"、"deformed to fracture"、"rupture" 等
- `is_microstructure_image` 与 `is_post_test_image` 是两个独立维度，不是互斥字段
- `is_microstructure_image=false`: 器件图、XRD 衍射图、电子衍射图、微衍射图、SAED/selected-area diffraction、相图/示意图、磁滞回线、磁化曲线、应力-应变曲线、性能曲线
- `is_microstructure_image=true`: TEM/SEM/OM/EBSD 中的组织形貌、断口形貌、变形后形貌 
- J-R curve、S-N curve、FCGR curve、crack extension curve、stress-strain curve、XRD、SAED、EDS spectrum、schematic/specimen dimension/sample location 一律不是 post-test image，除非图像本身是断口/断后形貌照片。

### 15. placeholder_index
- 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致

## 输出要求
- **直接输出 JSON 对象本身**，不要任何 markdown 代码块包裹（不要 ```json）
- **不要任何开场白**，第一个字符必须是 {，最后一个字符必须是 }
- 不要输出 paper_metadata.doi（系统会自动从 paper_id 推断）
- caption ≤80 字符；microstructure.description ≤150 字符；condition_processing_description ≤200 字符
- sample_processing_overview 控制在 ≤200 字符
- sample_microstructure_overview 控制在 ≤200 字符
对于明显非组织的图，仍输出 figure_id/placeholder_index/figure_type/is_microstructure_image=false/is_post_test_image=false/caption/image_purpose；sample_id、condition_id、scale_bar_info 可为 null 或省略
- 组织/形貌图必须完整输出 scale_bar_info（有则填 value/unit，无则 null）
"""


def build_extraction_prompt(text_with_placeholders: str, image_count: int) -> str:
    return f"""{JSON_SCHEMA_PROMPT}

## 论文内容

下面是论文的完整文本（{image_count} 张图片已按顺序作为附件传入，对应文本中的 [FIGURE_PLACEHOLDER_n]）：

{text_with_placeholders}

请仔细识别论文中**真正独立的样品数量**（不要把同一样品的不同焊接态、热处理态或测试温度错拆成多个样品），并准确提取核聚变低磁奥氏体不锈钢焊接相关字段：原文明示化学成分、样品形态、材料体系、component_type、joint_or_material_type、welding_process、filler_material、heat_treatment_condition、test_temperature、permeability、屈服强度、抗拉强度、伸长率、断裂韧性、组织描述、sample_processing_overview、sample_microstructure_overview、以及显微图 scale_bar_info。输出严格 JSON。
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
    parser = argparse.ArgumentParser(description="核聚变低磁奥氏体不锈钢焊接文献多模态信息抽取")
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
