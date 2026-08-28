"""按节剪裁 References / Acknowledgements，保留附录等后续内容。"""

from __future__ import annotations

import re

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
ARABIC_PREFIX_RE = re.compile(r"^\d+[\.\)]\s*")
ROMAN_PREFIX_RE = re.compile(r"^[IVXLCDM]+\.\s*", re.IGNORECASE)
CHINESE_PREFIX_RE = re.compile(r"^[一二三四五六七八九十]+[、.]\s*")

REF_TERMS = frozenset({
    "reference",
    "references",
    "bibliography",
    "参考文献",
    "文献引用",
    "references and notes",
})
ACK_TERMS = frozenset({
    "acknowledgement",
    "acknowledgements",
    "acknowledgment",
    "acknowledgments",
    "致谢",
    "鸣谢",
})
TRIM_TERMS = REF_TERMS | ACK_TERMS


def _normalize_title(raw: str) -> str:
    title = raw.strip().replace(":", "").replace("：", "")
    for pat in (ARABIC_PREFIX_RE, ROMAN_PREFIX_RE, CHINESE_PREFIX_RE):
        title = pat.sub("", title, count=1)
    return title.strip()


def _heading_match(raw_title: str) -> bool:
    norm = _normalize_title(raw_title).casefold()
    return norm in TRIM_TERMS


def _find_headings(text: str) -> list[dict]:
    headings = []
    for match in HEADING_RE.finditer(text):
        level = len(match.group(1))
        raw_title = match.group(2)
        headings.append({
            "level": level,
            "title": raw_title.strip(),
            "start": match.start(),
            "line_end": match.end(),
        })
    return headings


def _section_end(text: str, headings: list[dict], index: int) -> int:
    current = headings[index]
    for nxt in headings[index + 1:]:
        if nxt["level"] <= current["level"]:
            return nxt["start"]
    return len(text)


def trim_input(text: str) -> tuple[str, dict]:
    """剪掉 References/Acknowledgements 节，返回剪裁后文本与统计。"""
    raw_len = len(text)
    headings = _find_headings(text)
    half = raw_len * 0.5

    removed_sections: list[dict] = []
    skipped_too_early: list[dict] = []
    remove_ranges: list[tuple[int, int]] = []

    for idx, heading in enumerate(headings):
        if not _heading_match(heading["title"]):
            continue
        start = heading["start"]
        end = _section_end(text, headings, idx)
        entry = {
            "title": heading["title"],
            "start": start,
            "end": end,
            "chars": end - start,
        }
        if start < half:
            skipped_too_early.append(entry)
            continue
        removed_sections.append(entry)
        remove_ranges.append((start, end))

    if not remove_ranges:
        kept = text
    else:
        parts: list[str] = []
        cursor = 0
        for start, end in sorted(remove_ranges):
            parts.append(text[cursor:start])
            cursor = end
        parts.append(text[cursor:])
        kept = "".join(parts)

    kept_len = len(kept)
    ratio = round(kept_len / raw_len, 4) if raw_len else 1.0
    return kept, {
        "raw_chars": raw_len,
        "kept_chars": kept_len,
        "kept_ratio": ratio,
        "dropped_chars": raw_len - kept_len,
        "removed_sections": removed_sections,
        "skipped_too_early": skipped_too_early,
    }
