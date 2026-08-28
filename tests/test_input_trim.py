import pytest

from tools.input_trim import normalize_document_kind, prepare_model_text, trim_input

_PAD = "body padding. " * 80  # push end-matter headings past 50% mark

APPENDIX_AFTER_REFS = f"""# Intro
body with see References in prose and [1] cites.

{_PAD}
# Results
measured 685 MPa

# References
[1] Smith 2019

# Appendix
keep this appendix table
"""

ACK_THEN_REFS = f"""# Methods
do work

{_PAD}
# Acknowledgements
thanks lab

# References
[1] Lee 2020
"""

ROMAN = f"""# VI. CONCLUSIONS
done

{_PAD}
# VII. REFERENCES
[1] Nyilas 1990
"""

EARLY = """# References
this is related work in the first half of a long paper
""" + ("x" * 400) + """
# Results
real results here
"""


def test_keeps_appendix_after_references():
    kept, stats = trim_input(APPENDIX_AFTER_REFS)
    assert "keep this appendix table" in kept
    assert "[1] Smith 2019" not in kept
    assert "measured 685 MPa" in kept
    titles = [s["title"] for s in stats["removed_sections"]]
    assert any("References" in t for t in titles)


def test_removes_ack_and_refs_as_two_sections():
    kept, stats = trim_input(ACK_THEN_REFS)
    assert "thanks lab" not in kept
    assert "[1] Lee 2020" not in kept
    assert "do work" in kept
    assert len(stats["removed_sections"]) == 2


def test_roman_numeral_references_heading():
    kept, _ = trim_input(ROMAN)
    assert "Nyilas 1990" not in kept
    assert "done" in kept


def test_body_mentions_are_not_stripped():
    kept, _ = trim_input(APPENDIX_AFTER_REFS)
    assert "see References in prose" in kept


def test_skips_heading_in_first_half():
    kept, stats = trim_input(EARLY)
    assert "related work" in kept
    assert stats["skipped_too_early"]


def test_normalize_document_kind_defaults_and_rejects():
    assert normalize_document_kind(None) == "paper"
    assert normalize_document_kind("") == "paper"
    assert normalize_document_kind("patent") == "patent"
    with pytest.raises(ValueError, match="非法 document_kind"):
        normalize_document_kind("book")


def test_prepare_paper_matches_trim_input():
    kept_a, stats_a = trim_input(APPENDIX_AFTER_REFS)
    kept_b, stats_b = prepare_model_text(APPENDIX_AFTER_REFS, "paper")
    assert kept_a == kept_b
    assert stats_b["document_kind"] == "paper"
    assert "keep this appendix table" in kept_b
    assert "[1] Smith 2019" not in kept_b


def test_prepare_patent_uses_core_text():
    text = """摘要
不要这段。

具体实施方式
实施例1 保留这段实测硬度 180 HV。
"""
    kept, stats = prepare_model_text(text, "patent", paper_id="x1")
    assert "保留这段实测硬度 180 HV" in kept
    assert "不要这段" not in kept
    assert stats["document_kind"] == "patent"
    assert stats["core_start_found"] is True
    assert stats["raw_chars"] == len(text)
