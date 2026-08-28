"""Patent parser-text filter. Produces core_text for LLM input."""

from __future__ import annotations

import re
from dataclasses import dataclass


CORE_START_RE = re.compile(
    r"(?im)^[ \t#>*【\[]*"
    r"(?:\[\d+\]\s*)?"
    r"[\(（]?"
    r"(?:"
    r"具体实施方式|具体实施例|实施例|实施方式|实施发明的最佳方式|"
    r"发明的具体实施方式|用于实施发明的方式|发明实施方式|"
    r"具體實施方式|具體實施例|實施例|實施方式|發明實施方式"
    r")"
    r"[\d一二三四五六七八九十]*[\)）]?"
    r"[】\]：: 　\t]*$"
)

DROP_BLOCK_RE = re.compile(
    r"(?ims)"
    r"^[ \t#>*【\[]*(?:技术领域|发明所属的技术领域|所属领域|背景技术|摘要|权利要求书|"
    r"技術領域|發明所屬之技術領域|先前技術|背景技術|中文發明摘要|英文發明摘要|"
    r"發明摘要|申請專利範圍)"
    r"[】\]：: 　\t]*.*?"
    r"(?=^[ \t#>*【\[]*(?:背景技术|发明内容|附图说明|具体实施方式|具体实施例|"
    r"实施例|实施方式|发明的具体实施方式|发明实施方式|权利要求书|摘要|"
    r"背景技術|發明內容|圖式簡單說明|圖式簡要說明|具體實施方式|具體實施例|"
    r"實施例|實施方式|發明實施方式|申請專利範圍|中文發明摘要|英文發明摘要)"
    r"[】\]：: 　\t]*$|\Z)"
)

PATENT_TITLE_PATTERNS = [
    re.compile(r"\[54\]\s*发明名称\s*([^\n]{3,120})"),
    re.compile(r"发明名称\s*[:：]?\s*([^\n]{3,120})"),
    re.compile(r"(?m)^#\s*([^\n]{3,120})\s*$"),
]


@dataclass
class FilteredPatentText:
    title: str
    core_text: str
    core_start: int | None
    removed_prefix: str


def clean_noise(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            lines.append(line)
            continue
        if s.startswith("www.") or "soopat.com" in s.lower():
            continue
        if "本页蓝色字体部分可点击查询相关专利" in s:
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.strip() + "\n"


def extract_title(text: str, fallback: str = "") -> str:
    for pattern in PATENT_TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip(" #")
            if title:
                return title[:120]
    return fallback


def first_core_start(text: str) -> int | None:
    matches = list(CORE_START_RE.finditer(text))
    if not matches:
        return None
    strong = []
    for match in matches:
        heading = re.sub(r"^[ \t#>*【\[]+|[】\]：: 　\t]+$", "", match.group(0)).strip()
        heading = re.sub(r"^\[\d+\]\s*", "", heading)
        if not heading.startswith(("实施例", "實施例")):
            strong.append(match)
    return (strong[0] if strong else matches[0]).start()


def drop_explicit_unwanted_blocks(text: str) -> str:
    return clean_noise(DROP_BLOCK_RE.sub("\n", text))


def build_filtered_text(text: str, *, paper_id: str = "") -> FilteredPatentText:
    title = extract_title(text, fallback=paper_id)
    start = first_core_start(text)
    if start is not None:
        removed_prefix = text[:start]
        core = text[start:]
    else:
        removed_prefix = ""
        core = drop_explicit_unwanted_blocks(text)

    core = clean_noise(core)
    header = f"# {title}\n\n[文档ID] {paper_id}\n\n" if title or paper_id else ""
    core_text = header + core
    return FilteredPatentText(
        title=title,
        core_text=core_text,
        core_start=start,
        removed_prefix=removed_prefix,
    )
