from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def locate_token_sets(needle):
    s = str(needle or "").strip()
    if not s:
        return []
    sets = []
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if len(nums) >= 3:
        sets.append(nums)
    words = [w for w in re.split(r"[\s/,;|·•]+", re.sub(r"\s+", " ", s).strip()) if w]
    if words:
        sets.append(words)
    return sets


def find_needle(text, needle):
    if not needle or not text:
        return None
    for tokens in locate_token_sets(needle):
        if not tokens:
            continue
        pat = r"(?:[\s|/,;·•:()\[\]]|[^0-9\s]){0,32}?".join(re.escape(t) for t in tokens)
        m = re.search(pat, text)
        if m:
            return m.start()
    return None


def test_app_js_value_first_locate():
    js = (ROOT / "app/app.js").read_text(encoding="utf-8")
    assert "function factLocateNeedles" in js
    assert "function highlightFact" in js
    assert "function factCanLocate" in js
    start = js.index("function factLocateNeedles")
    fn = js[start : start + 700]
    assert fn.index("displayValue") < fn.index("excerpt")


def test_composition_value_locates_in_table():
    paper = (
        ROOT
        / "example_data/example_demo/parsed_results/10.1007_s11665-019-04233-6/paper.md"
    ).read_text(encoding="utf-8")
    value = (
        "C 0.18 / Si 0.203 / Mn 5.9 / P 0.0048 / S 0.0044 / Mo 0.50 / "
        "Ni 14.85 / Cr 20.25 / Nb 1.34 / V 0.35 / N 0.368 / Fe balance"
    )
    excerpt = (
        "Base metal: C 0.18, Si 0.203, Mn 5.9, P 0.0048, S 0.0044, Mo 0.50, "
        "Ni 14.85, Cr 20.25, Nb 1.34, V 0.35, N 0.368"
    )
    assert find_needle(paper, value) is not None
    assert find_needle(paper, excerpt) is not None
