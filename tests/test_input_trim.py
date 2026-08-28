from tools.input_trim import trim_input

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
