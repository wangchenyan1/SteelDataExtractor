# Field Rule Audit

Generated from `script_snapshots/*/scripts/01_extract.py` via read-only snapshot. Rules are checked by scoped key `level.field`.

## Summary

| project | scoped fields | parsed rules | missing rules | empty examples |
|---|---:|---:|---:|---:|
| non_magnetic | 43 | 41 | 2 | 33 |
| nuclear_fusion | 40 | 39 | 1 | 36 |
| cor_res | 35 | 28 | 7 | 22 |
| cuti | 39 | 36 | 3 | 31 |

## non_magnetic - 无磁钢

- total scoped fields: 43
- scoped fields with parsed rules: 41
- scoped fields missing parsed rules: 2
- scoped fields with empty positive/negative examples: 33

| level | field | rule source | rule preview | empty examples |
|---|---|---|---|---|
| metadata | `title` | 来自真实 01_extract.py 字段定义。 | 字段定义：... | yes |
| metadata | `doi` | missing |  | yes |
| metadata | `material_system` | 来自真实 01_extract.py 字段定义。 | 字段定义：钢种/合金体系简短描述（如 high-Mn non-magnetic steel, Cr-Mn-N austenitic steel） | yes |
| sample | `sample_name` | 来自规则：样品识别（极其重要） | 字段定义：论文中样品的原始命名; 样品（sample）= 论文中**化学成分独特**或**初始工艺独特**的材料实体; 同一样品的不同热处理态/不同退火温度/不同冷却条件 → 属于 **conditions**，不是新样品 | yes |
| sample | `product_form` | 来自规则：product_form 填写规则 | 字段定义：plate | sheet | bar | rod | rebar | wire | pipe | tube | angle_steel | pin | forging | casting | powder | bulk | target | other | not_s | yes |
| sample | `alloy_family` | 来自真实 01_extract.py 字段定义。 | 字段定义：Fe-Mn-Al-C | Mn-Cr-N | Mn-Cr-Mo-Ni 等（具体根据样品原始命名和元素组成而定） | yes |
| sample | `composition` | missing |  | yes |
| sample | `base_processing_description` | 来自真实 01_extract.py 字段定义。 | 字段定义：样品级公共工艺（冶炼、锻造等所有 condition 共享部分） | yes |
| sample | `sample_processing_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | sample_processing_overview：以固定格式提取样品整体工艺关键参数，尽量减少冗余修饰词; 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语; sample_microstructure_overview：以 | no |
| sample | `sample_microstructure_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | sample_processing_overview：以固定格式提取样品整体工艺关键参数，尽量减少冗余修饰词; 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语; sample_microstructure_overview：以 | no |
| sample | `sample_id` | 来自规则：样品识别（极其重要） | 字段定义：S1; 样品（sample）= 论文中**化学成分独特**或**初始工艺独特**的材料实体; 同一样品的不同热处理态/不同退火温度/不同冷却条件 → 属于 **conditions**，不是新样品 | yes |
| sample | `composition_unit` | 来自真实 01_extract.py 字段定义。 | 字段定义：wt.% | yes |
| condition | `condition_name` | 来自规则：condition_name（极其重要） | 字段定义：条件名（极简代号，如 HR, ST1100, A900-15min, as-rolled）; **必须用论文中给该条件起的简短代号**：HR、CR、ST1100、A900-15min 等 | yes |
| condition | `condition_type` | 来自规则：condition_type 严格区分 | 字段定义：processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition; `processing_condition`: 不同工艺态; `micr | yes |
| condition | `condition_processing_description` | 来自规则：condition_processing_description（极其重要：必须随 condition 变化） | 字段定义：该条件独有的工艺细节（如 solution treated at 1100°C for 30 min, water quenched）。必须随 condition 不同而不同！; 每个 condition 必须有**自己独有的**工艺细节; 样品级公共工艺（冶炼成材）放 | yes |
| condition | `microstructure` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | sample_processing_overview：以固定格式提取样品整体工艺关键参数，尽量减少冗余修饰词; 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语; sample_microstructure_overview：以 | no |
| condition | `condition_id` | 来自规则：condition_name（极其重要） | 字段定义：C1; **必须用论文中给该条件起的简短代号**：HR、CR、ST1100、A900-15min 等 | yes |
| condition | `sample_id` | 来自真实 01_extract.py 字段定义。 | 字段定义：S1 | yes |
| condition | `rolling_processing` | 来自规则：rolling_processing（轧制工艺）规则 | 5 项："heating_temperature"（加热/再加热温度）、"start_rolling_temperature"（开轧温度）、"finish_rolling_temperature"（终轧/精轧温度）、"reduction_ratio"（总压下率/累计压下率，单位  | yes |
| property | `yield_strength` | 来自规则：mechanical_properties（力学性能）规则 | "yield_strength"（屈服强度 σs / Rp0.2，MPa）; "tensile_strength"（抗拉强度 σb / Rm，MPa）; "elongation"（断后伸长率 δ / A，%）; "elastic_modulus"（弹性模量 E，GPa）; "ha | yes |
| property | `tensile_strength` | 来自规则：mechanical_properties（力学性能）规则 | "yield_strength"（屈服强度 σs / Rp0.2，MPa）; "tensile_strength"（抗拉强度 σb / Rm，MPa）; "elongation"（断后伸长率 δ / A，%）; "elastic_modulus"（弹性模量 E，GPa）; "ha | yes |
| property | `elongation` | 来自规则：mechanical_properties（力学性能）规则 | "yield_strength"（屈服强度 σs / Rp0.2，MPa）; "tensile_strength"（抗拉强度 σb / Rm，MPa）; "elongation"（断后伸长率 δ / A，%）; "elastic_modulus"（弹性模量 E，GPa）; "ha | yes |
| property | `permeability` | 来自规则：magnetic_properties（磁性能）规则 | "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）; "coercivity"（矫顽力 Hc，常见单位 Oe、A/m、kA/m）; "curie_tempe | yes |
| property | `hardness` | 来自规则：mechanical_properties（力学性能）规则 | "yield_strength"（屈服强度 σs / Rp0.2，MPa）; "tensile_strength"（抗拉强度 σb / Rm，MPa）; "elongation"（断后伸长率 δ / A，%）; "elastic_modulus"（弹性模量 E，GPa）; "ha | yes |
| property | `austenite_stability` | 来自规则：magnetic_properties（磁性能）规则 | 字段定义：stable, no α'-martensite after 20% cold rolling, SFE=30 mJ/m²; "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常 | yes |
| property | `impact_77K` | 来自规则：mechanical_properties（力学性能）规则 | "yield_strength"（屈服强度 σs / Rp0.2，MPa）; "tensile_strength"（抗拉强度 σb / Rm，MPa）; "elongation"（断后伸长率 δ / A，%）; "elastic_modulus"（弹性模量 E，GPa）; "ha | yes |
| property | `martensite_transformation_temperature` | 来自规则：magnetic_properties（磁性能）规则 | 字段定义：Ms=-80°C, Md30=-40°C; "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）; "coercivity"（矫顽力 Hc，常见单位 | yes |
| property | `saturation_magnetization` | 来自规则：magnetic_properties（磁性能）规则 | "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）; "coercivity"（矫顽力 Hc，常见单位 Oe、A/m、kA/m）; "curie_tempe | yes |
| property | `elastic_modulus` | 来自规则：mechanical_properties（力学性能）规则 | "yield_strength"（屈服强度 σs / Rp0.2，MPa）; "tensile_strength"（抗拉强度 σb / Rm，MPa）; "elongation"（断后伸长率 δ / A，%）; "elastic_modulus"（弹性模量 E，GPa）; "ha | yes |
| property | `remanence` | 来自规则：magnetic_properties（磁性能）规则 | "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）; "coercivity"（矫顽力 Hc，常见单位 Oe、A/m、kA/m）; "curie_tempe | yes |
| property | `coercivity` | 来自规则：magnetic_properties（磁性能）规则 | "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）; "coercivity"（矫顽力 Hc，常见单位 Oe、A/m、kA/m）; "curie_tempe | yes |
| property | `curie_temperature` | 来自规则：magnetic_properties（磁性能）规则 | "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）; "coercivity"（矫顽力 Hc，常见单位 Oe、A/m、kA/m）; "curie_tempe | yes |
| property | `neel_temperature` | 来自规则：magnetic_properties（磁性能）规则 | "permeability"（相对磁导率 μr，无量纲；少数论文给 μ 用 H/m）; "remanence"（剩余磁化强度 / 剩磁 Br，常见单位 T、Gs、emu/g）; "coercivity"（矫顽力 Hc，常见单位 Oe、A/m、kA/m）; "curie_tempe | yes |
| figure | `figure_id` | 来自规则：Figure → Sample 映射 & 图片类型 | 字段定义：Figure 1a; OM / SEM / TEM / EBSD / XRD 按图像内容判定; hysteresis_loop = 磁滞回线，is_microstructure_image=false; 力学曲线、磁滞回线、XRD、示意图 → is_microstruc | yes |
| figure | `placeholder_index` | 来自规则：placeholder_index | 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致 | yes |
| figure | `figure_type` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：OM | SEM | TEM | EBSD | XRD | stress_strain_curve | hysteresis_loop | schematic | other; OM / SEM / TEM / EBSD / XRD 按图像内容判定; hysteresi | no |
| figure | `is_microstructure_image` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM / SEM / TEM / EBSD / XRD 按图像内容判定; hysteresis_loop = 磁滞回线，is_microstructure_image=false; 力学曲线、磁滞回线、XRD、示意图 → is_microstructure_image=false | no |
| figure | `is_post_test_image` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM / SEM / TEM / EBSD / XRD 按图像内容判定; hysteresis_loop = 磁滞回线，is_microstructure_image=false; 力学曲线、磁滞回线、XRD、示意图 → is_microstructure_image=false | no |
| figure | `sample_id` | 来自规则：Figure → Sample 映射 & 图片类型 | 字段定义：S1; OM / SEM / TEM / EBSD / XRD 按图像内容判定; hysteresis_loop = 磁滞回线，is_microstructure_image=false; 力学曲线、磁滞回线、XRD、示意图 → is_microstructure_im | yes |
| figure | `condition_id` | 来自规则：Figure → Sample 映射 & 图片类型 | 字段定义：C1; OM / SEM / TEM / EBSD / XRD 按图像内容判定; hysteresis_loop = 磁滞回线，is_microstructure_image=false; 力学曲线、磁滞回线、XRD、示意图 → is_microstructure_im | yes |
| figure | `caption` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：图片标题（≤80 字符）; OM / SEM / TEM / EBSD / XRD 按图像内容判定; hysteresis_loop = 磁滞回线，is_microstructure_image=false; 力学曲线、磁滞回线、XRD、示意图 → is_microst | no |
| figure | `scale_bar_info` | 来自规则：scale_bar_info（组织/形貌图比例尺提取） | 对所有显微图片（组织图、断口形貌图等），必须尝试从图片上提取比例尺标注; 如图片上确实没有比例尺标注（如曲线图、示意图、磁滞回线），填 null; 注意区分比例尺（scale bar）和标尺文字，优先提取图片右下角/左下角的标注 | yes |
| figure | `image_purpose` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：before_test_microstructure | sample_level_microstructure | heat_treated_microstructure | post_test_fractography | fracture_surface | me | no |

Missing parsed rules: `metadata.doi`, `sample.composition`

## nuclear_fusion - 核聚变低磁奥氏体钢

- total scoped fields: 40
- scoped fields with parsed rules: 39
- scoped fields missing parsed rules: 1
- scoped fields with empty positive/negative examples: 36

| level | field | rule source | rule preview | empty examples |
|---|---|---|---|---|
| metadata | `title` | 来自真实 01_extract.py 字段定义。 | 字段定义：... | yes |
| metadata | `doi` | missing |  | yes |
| metadata | `material_system` | 来自真实 01_extract.py 字段定义。 | 字段定义：钢种/合金体系简短描述（如 high-Mn non-magnetic steel, Cr-Mn-N austenitic steel） | yes |
| sample | `sample_name` | 来自规则：样品识别（极其重要） | 字段定义：论文中样品的原始命名; 样品（sample）= 论文中**化学成分独特**或**初始工艺独特**的材料实体; 同一样品的不同热处理态/不同退火温度/不同冷却条件 → 属于 **conditions**，不是新样品 | yes |
| sample | `product_form` | 来自规则：product_form 填写规则 | 字段定义：plate | sheet | bar | rod | wire | pipe | tube | conduit | jacket | coil_case | weldment | weld_metal | filler_wire | forging | casting | yes |
| sample | `alloy_family` | 来自真实 01_extract.py 字段定义。 | 字段定义：Cu-Mn-Nb-V-N | Cr-Mn-N | other | yes |
| sample | `composition` | 来自规则：化学成分抽取（极其重要） | composition 只填写论文成分表、正文或图表中**明确给出的元素和值**，不要为了凑字段补全元素 | yes |
| sample | `base_processing_description` | 来自真实 01_extract.py 字段定义。 | 字段定义：样品级公共工艺（冶炼、锻造等所有 condition 共享部分） | yes |
| sample | `sample_processing_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | 字段定义：样品整体工艺关键参数（固定格式提取，去除修饰词）：钢号/材料名（如 316LN, JJ1, JK2LB）、钢种大类（低磁/高氮/氮强化奥氏体不锈钢）、热处理状态（solution treated/aged/Nb3Sn reacted/as-welded）、关键温度与时间 | no |
| sample | `sample_microstructure_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | 字段定义：样品整体组织关键特征（固定格式提取，去除修饰词）：austenite/ferrite/delta-ferrite/martensite、晶粒尺寸、析出相、焊缝/HAZ组织、断裂相关组织。显微手段（OM/SEM/TEM/EBSD）仅作弱信息标注; sample_proce | no |
| sample | `sample_id` | 来自规则：样品识别（极其重要） | 字段定义：S1; 样品（sample）= 论文中**化学成分独特**或**初始工艺独特**的材料实体; 同一样品的不同热处理态/不同退火温度/不同冷却条件 → 属于 **conditions**，不是新样品 | yes |
| sample | `composition_unit` | 来自规则：化学成分抽取（极其重要） | 字段定义：wt.% | yes |
| condition | `condition_name` | 来自规则：condition_name（极其重要） | 字段定义：条件名（极简代号，如 as-welded, 4.2K, Nb3Sn-reacted, aged, HAZ, WM）; **必须用论文中给该条件起的简短代号**：HR、CR、ST1100、A900-15min 等 | yes |
| condition | `condition_type` | 来自规则：condition_type 严格区分 | 字段定义：processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition; `processing_condition`: 不同工艺态; `micr | yes |
| condition | `component_type` | 来自规则：component_type 与 joint_or_material_type 规则 | 字段定义：armor | coil_case | conduit_jacket | magnet_structure | other | unclear; component_type 表示这组 condition/性能数据对应的核聚变工程对象，必须从枚举中选择：; armor： | yes |
| condition | `joint_or_material_type` | 来自规则：component_type 与 joint_or_material_type 规则 | 字段定义：base_metal | weld_metal | welded_joint | HAZ | deposited_metal | unclear; component_type 表示这组 condition/性能数据对应的核聚变工程对象，必须从枚举中选择：; armor | yes |
| condition | `welding_process` | 来自规则：焊接/热处理/测试温度字段规则 | 字段定义：TIG | GTAW | laser_welding | electron_beam_welding | NG-MAG | SAW | hybrid_welding | other | not_specified; welding_process 表示焊接方法，必须从枚 | yes |
| condition | `filler_material` | 来自规则：焊接/热处理/测试温度字段规则 | 字段定义：焊材/焊丝/填充金属原文名称，如 ER316LMn, FMYJJ1, 316L filler, none, not_specified; welding_process 表示焊接方法，必须从枚举中选择：TIG | GTAW | laser_welding | elect | yes |
| condition | `heat_treatment_condition` | 来自规则：焊接/热处理/测试温度字段规则 | 字段定义：as-welded | Nb3Sn reacted | aged | solution treated | PWHT | other | not_specified；可保留原文温度时间; welding_process 表示焊接方法，必须从枚举中选择：TIG | GTA | yes |
| condition | `test_temperature` | 来自规则：焊接/热处理/测试温度字段规则 | welding_process 表示焊接方法，必须从枚举中选择：TIG | GTAW | laser_welding | electron_beam_welding | NG-MAG | SAW | hybrid_welding | other | not_specified。; | yes |
| condition | `condition_processing_description` | 来自规则：condition_processing_description（极其重要：必须随 condition 变化） | 字段定义：该条件独有的补充工艺/测试细节：板厚、坡口、试样位置、取向、热输入等低频信息合并写在这里。必须随 condition 不同而不同！; 每个 condition 必须有**自己独有的**工艺细节; 样品级公共工艺（冶炼成材）放到 sample.base_processin | yes |
| condition | `microstructure` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | sample_processing_overview：以固定格式提取样品整体工艺关键参数，尽量减少冗余修饰词; 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语; sample_microstructure_overview：以 | no |
| condition | `condition_id` | 来自规则：condition_name（极其重要） | 字段定义：C1; **必须用论文中给该条件起的简短代号**：HR、CR、ST1100、A900-15min 等 | yes |
| condition | `sample_id` | 来自真实 01_extract.py 字段定义。 | 字段定义：S1 | yes |
| property | `yield_strength` | 来自规则：mechanical_properties（力学性能）规则 | 优先抽取与核聚变装置 4.2K 焊接接头相关的实测性能；如果论文给出多个温度，分别建立 condition 或在 condition_processing_description 中明确温度。; "yield_strength"（屈服强度 / 0.2% proof stress  | yes |
| property | `tensile_strength` | 来自规则：mechanical_properties（力学性能）规则 | 优先抽取与核聚变装置 4.2K 焊接接头相关的实测性能；如果论文给出多个温度，分别建立 condition 或在 condition_processing_description 中明确温度。; "yield_strength"（屈服强度 / 0.2% proof stress  | yes |
| property | `elongation` | 来自规则：mechanical_properties（力学性能）规则 | 优先抽取与核聚变装置 4.2K 焊接接头相关的实测性能；如果论文给出多个温度，分别建立 condition 或在 condition_processing_description 中明确温度。; "yield_strength"（屈服强度 / 0.2% proof stress  | yes |
| property | `fracture_toughness` | 来自规则：mechanical_properties（力学性能）规则 | 优先抽取与核聚变装置 4.2K 焊接接头相关的实测性能；如果论文给出多个温度，分别建立 condition 或在 condition_processing_description 中明确温度。; "yield_strength"（屈服强度 / 0.2% proof stress  | yes |
| property | `permeability` | 来自规则：magnetic_properties（磁性能）规则 | 只抽取 permeability（相对磁导率 μr 或 magnetic permeability）。; 单位按原文填写；相对磁导率可写 unit="(relative)"。 | yes |
| property | `hardness` | 来自规则：mechanical_properties（力学性能）规则 | 优先抽取与核聚变装置 4.2K 焊接接头相关的实测性能；如果论文给出多个温度，分别建立 condition 或在 condition_processing_description 中明确温度。; "yield_strength"（屈服强度 / 0.2% proof stress  | yes |
| figure | `figure_id` | 来自规则：Figure → Sample 映射 & 图片类型 | 字段定义：Figure 1a; OM / SEM / TEM / EBSD / XRD 按图像内容判定 | yes |
| figure | `placeholder_index` | 来自规则：placeholder_index | 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致 | yes |
| figure | `figure_type` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：OM | SEM | TEM | EBSD | XRD | stress_strain_curve | hysteresis_loop | schematic | other; OM / SEM / TEM / EBSD / XRD 按图像内容判定; `is_micro | yes |
| figure | `is_microstructure_image` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM / SEM / TEM / EBSD / XRD 按图像内容判定; `is_microstructure_image=true` 且 `is_post_test_image=false`：组织观察图（before-test）; `is_microstructure_imag | yes |
| figure | `is_post_test_image` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM / SEM / TEM / EBSD / XRD 按图像内容判定; `is_microstructure_image=true` 且 `is_post_test_image=false`：组织观察图（before-test）; `is_microstructure_imag | yes |
| figure | `sample_id` | 来自规则：Figure → Sample 映射 & 图片类型 | 字段定义：S1; OM / SEM / TEM / EBSD / XRD 按图像内容判定 | yes |
| figure | `condition_id` | 来自规则：Figure → Sample 映射 & 图片类型 | 字段定义：C1; OM / SEM / TEM / EBSD / XRD 按图像内容判定 | yes |
| figure | `caption` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：图片标题（≤80 字符）; OM / SEM / TEM / EBSD / XRD 按图像内容判定; `is_microstructure_image=true` 且 `is_post_test_image=false`：组织观察图（before-test）; `is_ | yes |
| figure | `scale_bar_info` | 来自规则：scale_bar_info（组织/形貌图比例尺提取） | 对所有显微图片（组织图、断口形貌图等），必须尝试从图片上提取比例尺标注; 如图片上确实没有比例尺标注（如曲线图、示意图、磁滞回线），填 null; 注意区分比例尺（scale bar）和标尺文字，优先提取图片右下角/左下角的标注 | yes |
| figure | `image_purpose` | 来自规则：Figure → Sample 映射 & 图片类型; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：before_test_microstructure | sample_level_microstructure | heat_treated_microstructure | post_test_fractography | fracture_surface | me | yes |

Missing parsed rules: `metadata.doi`

## cor_res - 耐蚀钢

- total scoped fields: 35
- scoped fields with parsed rules: 28
- scoped fields missing parsed rules: 7
- scoped fields with empty positive/negative examples: 22

| level | field | rule source | rule preview | empty examples |
|---|---|---|---|---|
| metadata | `title` | 来自真实 01_extract.py 字段定义。 | 字段定义：... | yes |
| metadata | `doi` | missing |  | yes |
| metadata | `material_system` | 来自真实 01_extract.py 字段定义。 | 字段定义：钢种/合金体系简短描述（如 Nb-Mo HSLA steel, 4Mn medium-Mn TRIP steel） | yes |
| sample | `sample_name` | 来自规则：样品识别（极其重要） | 字段定义：论文中样品的原始命名（如 Nb-Ti steel, Nb-Mo steel, low carbon steel）; 样品（sample）= 论文中**化学成分独特**或**初始工艺/材料角色独特**的材料实体; 同一样品的不同热处理态/不同退火温度/不同冷却条件/不同腐 | yes |
| sample | `product_form` | 来自规则：product_form 填写规则 | 字段定义：plate | sheet | bar | rod | rebar | wire | pipe | tube | angle_steel | pin | forging | casting | powder | bulk | target | other ; 推断优先级 | yes |
| sample | `composition` | 来自规则：化学成分抽取（极其重要：按表头映射，禁止列错位） | composition 只填写论文成分表、正文或图表中**明确给出的元素和值**，不要为了凑字段补全元素 | yes |
| sample | `base_processing_description` | 来自真实 01_extract.py 字段定义。 | 字段定义：样品级公共工艺（冶炼、锻造等所有 condition 共享部分） | yes |
| sample | `sample_processing_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | sample_processing_overview：以固定格式提取样品整体工艺关键参数，减少冗余修饰词; 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语; sample_microstructure_overview：以固定 | no |
| sample | `sample_microstructure_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | sample_processing_overview：以固定格式提取样品整体工艺关键参数，减少冗余修饰词; 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语; sample_microstructure_overview：以固定 | no |
| sample | `sample_id` | 来自规则：样品识别（极其重要） | 字段定义：S1; 样品（sample）= 论文中**化学成分独特**或**初始工艺/材料角色独特**的材料实体; 同一样品的不同热处理态/不同退火温度/不同冷却条件/不同腐蚀暴露时长 → 属于 **conditions**，不是新样品; **必须拆成多个样品**的常见情形（成分不 | yes |
| sample | `composition_unit` | 来自规则：化学成分抽取（极其重要：按表头映射，禁止列错位） | 字段定义：wt.% | yes |
| condition | `condition_name` | 来自规则：condition_id / condition_name（极其重要） | 字段定义：条件名（极简代号，如 HR, ST1100, A900-15min, as-rolled）; `condition_name` **必须用论文中给该条件起的简短代号**：A700、A720、TP000、HR、as-rolled、14d、28d 等; 同一工艺/暴露代号若 | no |
| condition | `condition_type` | 来自规则：condition_type 严格区分 | 字段定义：processing_condition | microstructure_condition | mechanical_test_condition | corrosion_test_condition | post_test_condition; `processi | yes |
| condition | `condition_processing_description` | 来自规则：condition_processing_description（极其重要：必须随 condition 变化） | 字段定义：该条件独有的工艺细节（如 solution treated at 1100°C for 30 min, water quenched）。必须随 condition 不同而不同！; C1 (as-hot-rolled): "Hot-rolled state, no fur | no |
| condition | `microstructure` | 来自规则：sample_processing_overview 与 sample_microstructure_overview（样品级概述） | sample_processing_overview：以固定格式提取样品整体工艺关键参数，减少冗余修饰词; 必须包含的要素（如论文中有）：钢号/材料名、钢种大类、热处理状态、关键温度与时间、加工状态、状态短语; sample_microstructure_overview：以固定 | no |
| condition | `condition_id` | 来自规则：condition_id / condition_name（极其重要） | 字段定义：C1; `condition_name` **必须用论文中给该条件起的简短代号**：A700、A720、TP000、HR、as-rolled、14d、28d 等; 同一工艺/暴露代号若分别作用于多个 sample，应输出多条 condition（不同 `conditio | no |
| condition | `sample_id` | 来自真实 01_extract.py 字段定义。 | 字段定义：S1 | yes |
| condition | `rolling_processing` | 来自规则：rolling_processing（轧制工艺）规则 | 5 项："heating_temperature"（加热/再加热温度）、"start_rolling_temperature"（开轧温度）、"finish_rolling_temperature"（终轧/精轧温度）、"reduction_ratio"（总压下率/累计压下率，单位  | yes |
| property | `yield_strength` | missing |  | yes |
| property | `tensile_strength` | 来自规则：product_form 填写规则 | 推断优先级：论文明确声明 > 实验描述暗示 > 默认 other; 常见对应：plate(板材/薄板), bar(棒材/圆棒), rebar(钢筋), wire(线材), pipe(管材), angle_steel(角钢), pin(销轴), forging(锻件), casti | yes |
| property | `elongation` | missing |  | yes |
| property | `hardness` | missing |  | yes |
| property | `reduction_of_area` | missing |  | yes |
| property | `impact_toughness` | missing |  | yes |
| property | `microhardness` | missing |  | yes |
| figure | `figure_id` | 来自规则：Figure → Sample 映射 | 字段定义：Figure 1a; 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition; caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample; 多 panel  | yes |
| figure | `placeholder_index` | 来自规则：placeholder_index | 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致 | yes |
| figure | `figure_type` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：OM | SEM | TEM | EBSD | XRD | EDS | stress_strain_curve | polarization_curve | EIS | schematic | other; OM = 光学显微（optical micrograph，通常 | yes |
| figure | `is_microstructure_image` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口/腐蚀形貌）; TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）; EBSD = 反极图/取向图（彩色 IPF）; XRD = X射线衍射图（ | yes |
| figure | `is_post_test_image` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口/腐蚀形貌）; TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）; EBSD = 反极图/取向图（彩色 IPF）; XRD = X射线衍射图（ | yes |
| figure | `sample_id` | 来自规则：Figure → Sample 映射 | 字段定义：S1; 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition; caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample; 多 panel 图为每个 pa | yes |
| figure | `condition_id` | 来自规则：Figure → Sample 映射 | 字段定义：C1; 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition; caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample; 多 panel 图为每个 pa | yes |
| figure | `caption` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：图片标题（≤80 字符）; OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口/腐蚀形貌）; TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）; EBSD = 反极图/取向图（彩色  | yes |
| figure | `scale_bar_info` | 来自规则：scale_bar_info（组织/形貌图比例尺提取） | 对所有显微图片（组织图、腐蚀形貌图、断口图等），必须尝试从图片上提取比例尺标注; 如图片上确实没有比例尺标注（如曲线图、示意图），填 null; 注意区分比例尺（scale bar）和标尺文字，优先提取图片右下角/左下角的标注 | yes |
| figure | `image_purpose` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要）; 来自规则：image_p | OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口/腐蚀形貌）; TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）; EBSD = 反极图/取向图（彩色 IPF）; XRD = X射线衍射图（ | yes |

Missing parsed rules: `metadata.doi`, `property.yield_strength`, `property.elongation`, `property.hardness`, `property.reduction_of_area`, `property.impact_toughness`, `property.microhardness`

## cuti - 钛铜

- total scoped fields: 39
- scoped fields with parsed rules: 36
- scoped fields missing parsed rules: 3
- scoped fields with empty positive/negative examples: 31

| level | field | rule source | rule preview | empty examples |
|---|---|---|---|---|
| metadata | `title` | 来自真实 01_extract.py 字段定义。 | 字段定义：... | yes |
| metadata | `doi` | missing |  | yes |
| metadata | `material_system` | 来自真实 01_extract.py 字段定义。 | 字段定义：合金体系简短描述（如 Cu-4Ti, Cu-3Ti-2Si-1.5Ni, Cu-Ti-Cr-Mg） | yes |
| sample | `sample_name` | 来自规则：样品识别（极其重要） | 字段定义：论文中样品的原始命名（如 Cu-4Ti, Cu-3.5Ti, Cu-4Ti-1Cr）; 样品（sample）= 论文中**作为研究对象的合金实体**（化学成分独特或初始工艺独特）; 同一样品的不同热处理态/时效温度时间/冷变形量 → 属于 **conditions**， | no |
| sample | `product_form` | 来自规则：product_form（sample 级）填写规则 | 字段定义：sheet | strip | foil | plate | bar | rod | wire | pipe | tube | forging | casting | powder | bulk | other; 推断优先级：论文明确声明 > 实验描述暗示 > 默认 o | yes |
| sample | `alloy_family` | 来自规则：alloy_family（sample 级，极其重要） | 字段定义：Cu-Ti | Cu-Ti-Cr | Cu-Ti-Fe-Cr | Cu-Ti-Ni-Si | Cu-Ti-Cr-Mg-Si 等（见规则 §3）; 由**有意添加的合金元素**归一成族名短串，**不含含量数字**; 格式：二元写 `Cu-Ti`；多元写 `Cu-Ti-<其 | yes |
| sample | `composition` | missing |  | yes |
| sample | `base_processing_description` | 来自真实 01_extract.py 字段定义。 | 字段定义：样品级公共工艺：冶炼、铸造、热轧成材等所有 condition 共享的部分 | yes |
| sample | `sample_processing_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview | 字段定义：样品整体工艺关键参数（固定格式，去修饰词）：合金名、固溶/时效/冷轧等关键温度与时间、加工状态; 固定格式、去修饰词；各 ≤200 字符；显微手段仅弱标注 | yes |
| sample | `sample_microstructure_overview` | 来自规则：sample_processing_overview 与 sample_microstructure_overview | 字段定义：样品整体组织关键特征（固定格式，去修饰词）：相组成、析出相（如 β'-Cu4Ti）、晶粒尺寸、组织形貌; 固定格式、去修饰词；各 ≤200 字符；显微手段仅弱标注 | yes |
| sample | `sample_id` | 来自规则：样品识别（极其重要） | 字段定义：S1; 样品（sample）= 论文中**作为研究对象的合金实体**（化学成分独特或初始工艺独特）; 同一样品的不同热处理态/时效温度时间/冷变形量 → 属于 **conditions**，不是新样品 | no |
| sample | `composition_unit` | 来自真实 01_extract.py 字段定义。 | 字段定义：wt.% | yes |
| condition | `condition_name` | 来自规则：condition 筛选（控制数量）; 来自规则：condition_name（极其重要） | 字段定义：条件名（极简代号，如 ST900, A450-120min, CR50+A450, peak-aged, as-solution-treated）; 全文 conditions **≤15**；超了按上面优先级保留; **必须用论文中给该条件起的简短代号**：ST900 | no |
| condition | `condition_type` | 来自规则：condition 筛选（控制数量）; 来自规则：condition_type 严格区分 | 字段定义：processing_condition | microstructure_condition | mechanical_test_condition | post_test_condition; 全文 conditions **≤15**；超了按上面优先级保留; `p | yes |
| condition | `condition_processing_description` | 来自规则：solution_treatment / aging / cold_rolling（condition 级定格式文本）; 来自规则：condition_processing_descript | 字段定义：定格式字段未覆盖的残余工艺细节（气氛、工序顺序补充等）；勿重复抄写温度/时间/压下率; `solution_treatment`：`<T>/<t>, <cooling>`，冷却用 WQ/AC/FC；例 `"900°C/4h, WQ"`; `aging`：`<T>/<t> | no |
| condition | `microstructure` | 来自规则：sample_processing_overview 与 sample_microstructure_overview | 固定格式、去修饰词；各 ≤200 字符；显微手段仅弱标注 | yes |
| condition | `condition_id` | 来自规则：condition 筛选（控制数量）; 来自规则：condition_name（极其重要） | 字段定义：C1; 全文 conditions **≤15**；超了按上面优先级保留; **必须用论文中给该条件起的简短代号**：ST900、A450-120min、CR50+A450、peak-aged、as-solution-treated 等 | no |
| condition | `sample_id` | 来自真实 01_extract.py 字段定义。 | 字段定义：S1 | yes |
| condition | `solution_treatment` | 来自规则：solution_treatment / aging / cold_rolling（condition 级定格式文本） | 字段定义：定格式文本，例：900°C/4h, WQ（见规则 §7）; `solution_treatment`：`<T>/<t>, <cooling>`，冷却用 WQ/AC/FC；例 `"900°C/4h, WQ"`; `aging`：`<T>/<t>`，多步用 ` + ` 拼接 | yes |
| condition | `microstructure_description` | 来自真实 01_extract.py 字段定义。 | 字段定义：该条件下的组织描述（相组成、析出相 β'-Cu4Ti、晶粒/位错等） | yes |
| condition | `aging` | 来自规则：solution_treatment / aging / cold_rolling（condition 级定格式文本） | 字段定义：定格式文本，例：450°C/60min 或 300°C/2h + 450°C/7h（见规则 §7）; `solution_treatment`：`<T>/<t>, <cooling>`，冷却用 WQ/AC/FC；例 `"900°C/4h, WQ"`; `aging`：` | yes |
| condition | `cold_rolling` | 来自规则：solution_treatment / aging / cold_rolling（condition 级定格式文本） | 字段定义：定格式文本，例：50% 或 85% + 90% + 95%（见规则 §7）; `solution_treatment`：`<T>/<t>, <cooling>`，冷却用 WQ/AC/FC；例 `"900°C/4h, WQ"`; `aging`：`<T>/<t>`，多步用 | yes |
| condition | `bending_performance` | 来自规则：bending_performance | 字段定义：按规则 §10 固定格式拼接；例：parallel to RD, 90° bend, no crack (t=0.15 mm, R/t=2); 模板：`<direction>, <angle> bend, <result> (<t, R/t...>)`；定性可用 `lo | yes |
| property | `yield_strength` | 来自规则：mechanical_properties / electrical_properties | 只抽本文实测，不抽综述对比数据 | yes |
| property | `tensile_strength` | 来自规则：mechanical_properties / electrical_properties | 只抽本文实测，不抽综述对比数据 | yes |
| property | `elongation` | 来自规则：mechanical_properties / electrical_properties | 只抽本文实测，不抽综述对比数据 | yes |
| property | `hardness` | 来自规则：mechanical_properties / electrical_properties | 只抽本文实测，不抽综述对比数据 | yes |
| property | `conductivity` | 来自规则：mechanical_properties / electrical_properties | 只抽本文实测，不抽综述对比数据 | yes |
| property | `electrical_conductivity` | 来自规则：mechanical_properties / electrical_properties | 只抽本文实测，不抽综述对比数据 | yes |
| figure | `figure_id` | 来自规则：Figure → Sample 映射 | 字段定义：Figure 1a; 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition; caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample; 多 panel  | yes |
| figure | `placeholder_index` | 来自规则：placeholder_index | 必须与文本中的 [FIGURE_PLACEHOLDER_n] 编号一致 | yes |
| figure | `figure_type` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：OM | SEM | TEM | EBSD | XRD | stress_strain_curve | schematic | other; OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口） | yes |
| figure | `is_microstructure_image` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口）; TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）; EBSD = 反极图/取向图（彩色 IPF）; XRD = X射线衍射图（曲线图，有 | yes |
| figure | `is_post_test_image` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口）; TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）; EBSD = 反极图/取向图（彩色 IPF）; XRD = X射线衍射图（曲线图，有 | yes |
| figure | `sample_id` | 来自规则：Figure → Sample 映射 | 字段定义：S1; 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition; caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample; 多 panel 图为每个 pa | yes |
| figure | `condition_id` | 来自规则：Figure → Sample 映射 | 字段定义：C1; 必须从 caption 或正文中明确判断每张图属于哪个 sample 和 condition; caption 中提到 "(a) sample X, (b) sample Y" → panel a/b 分别对应不同 sample; 多 panel 图为每个 pa | yes |
| figure | `caption` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：图片标题; OM = 光学显微（optical micrograph，通常有颜色或灰度晶界）; SEM = 扫描电镜（高分辨灰度组织/断口）; TEM = 透射电镜（黑白衍衬像，含位错、析出相、SAED）; EBSD = 反极图/取向图（彩色 IPF）; XRD = X | yes |
| figure | `scale_bar_info` | missing |  | yes |
| figure | `image_purpose` | 来自规则：图片类型判定（看图本身 + 看 caption）; 来自规则：is_microstructure_image 与 is_post_test_image（极其重要） | 字段定义：before_test_microstructure | sample_level_microstructure | heat_treated_microstructure | post_test_fractography | fracture_surface | me | yes |

Missing parsed rules: `metadata.doi`, `sample.composition`, `figure.scale_bar_info`
