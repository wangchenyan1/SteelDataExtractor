"""Patent extract rules aligned with Extract_data/cuti_patent/scripts/01_extract.py.

Stage 1 = skeleton only. Stage 2 fills properties for Stage-1 rows only.
"""

PATENT_STAGE1_RULES = """
## 专利抽取规则（必须严格遵守，对齐 01_extract.py）
- 每个 condition 必须带 sample_id，且 sample_id 必须是本 JSON 里已有的样品。
- 主表只抽说明书中的实施例、发明例、表格 No. 行等具体数据。
- 权利要求、摘要、发明内容中的成分范围、性能阈值、公式只用于理解专利，不要作为 sample 或 condition 输出。
- 如果某篇专利只有权利要求范围，没有实施例或表格中的具体成分/工艺/性能数据，则可以输出 metadata 和空的 samples/conditions。
- 比较例默认不要输出；除非比较例同时被专利明确作为有效实施例使用。普通“比较例/对比例”跳过。
- 样品（sample）= 同一实施例链路中的材料实体；判定边界必须同时看来源位置（实施例/表号/段落）、成分、产品形态、主工艺路线，不能只按成分或 No. 编号合并。
- No.1、No.2 等编号只在其所在表格/实施例内有效。不同表、不同实施例中出现相同 No. 或相同成分时，默认不是同一个 sample。
- 同一 sample 下的 conditions 必须共享同一材料来源和主工艺路线。
- 若主工艺路线发生实质变化，即使成分相同也应拆成不同 samples。
- 表格中 No.1、No.2 等如果每行成分不同，可各自作为 sample；如果同一表/同一实施例链路中成分相同而只改变状态或末端工艺，可共用 sample 并建多个 conditions。
- 不确定是否同一样品时，优先拆分为不同 samples。
- 禁止把多个实施例合并成一个范围成分样品。
- condition_name 使用专利原文中的实施例名或表格编号：Example 1、实施例1、发明例1、表3 No.1。不要使用 claim-1，不要堆砌完整工艺。
- 只建有明确性能或评价数字的 condition（正文/表中有 YS、UTS、EL、HV、EC、弯曲/松弛/0.2%耐受力/永久变形率/箔厚/成品规格之一）。无性能数字的纯工艺步骤不要单独建 condition。
- 如果材料制备后直接测试，也要建立一个 condition，并写上对应 sample_id。
- 如果表A列成分工艺、表B列同编号性能，要在 condition 的 location/excerpt 中写明表A + 表B。
- 本阶段不抽具体性能数值。
"""

PATENT_STAGE2_RULES = """
## 专利性能规则（必须严格遵守，只补骨架行）
- 只给上面「样品-状态骨架」里已有的 condition 补性能，禁止新增样品或状态，禁止改 condition_id / sample_id。
- 输出每一行必须带回骨架中的 condition_id 和 sample_id。
- 只抽说明书实施例/发明例/表格中的实测或评价数字；权利要求阈值不抽。
- 如果原文是 0.2%耐力/0.2%耐受力/YS/屈服强度，写入 yield_strength；只有原文明确「抗拉强度/拉伸强度」时才写 tensile_strength。
- 弹性极限、松弛量、永久变形率、粗糙度、弯曲等写入 bending_performance（若本组字段包含它）或按本组字段规则填写。
- 单位按原文，不换算。
"""
