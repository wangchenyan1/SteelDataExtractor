from tools.patent_text_filter import build_filtered_text

PATENT = """# 一种铜钛合金

[54] 发明名称 一种铜钛合金及其制备方法

www.soopat.com
本页蓝色字体部分可点击查询相关专利

技术领域
本发明属于金属材料。

背景技术
现有技术提到实施例仅作对比说明。

发明内容
一种合金。

权利要求书
1. 一种合金，钛含量 1-10%。

具体实施方式
实施例1
将铜钛合金固溶后时效，测得电导率 20%IACS，硬度 200 HV。
表1 性能测试结果
"""


def test_keeps_embodiment_drops_front_matter_and_claims():
    filtered = build_filtered_text(PATENT, paper_id="p001")
    assert "具体实施方式" in filtered.core_text
    assert "电导率 20%IACS" in filtered.core_text
    assert "表1 性能测试结果" in filtered.core_text
    assert "本发明属于金属材料" not in filtered.core_text
    assert "钛含量 1-10%" not in filtered.core_text
    assert filtered.core_start is not None
    assert "[文档ID] p001" in filtered.core_text
    assert "一种铜钛合金及其制备方法" in filtered.core_text
    assert "soopat.com" not in filtered.core_text
    assert "本页蓝色字体部分可点击查询相关专利" not in filtered.core_text


def test_bare_embodiment_defers_to_strong_heading():
    text = """背景技术
正文先提到实施例作为对比。

具体实施方式
实施例2 真实工艺。
"""
    filtered = build_filtered_text(text, paper_id="p002")
    assert "真实工艺" in filtered.core_text
    assert "作为对比" not in filtered.core_text
    assert filtered.core_start is not None


def test_no_core_heading_drops_named_blocks():
    text = """摘要
这是摘要内容。

权利要求书
1. 一种方法。

发明内容
留下这段工艺描述和表2。
"""
    filtered = build_filtered_text(text, paper_id="")
    assert "这是摘要内容" not in filtered.core_text
    assert "一种方法" not in filtered.core_text
    assert "留下这段工艺描述和表2" in filtered.core_text
    assert filtered.core_start is None
