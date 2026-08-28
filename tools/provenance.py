"""Provenance value shapes and excerpt span matching."""

from __future__ import annotations

import re
from typing import Any


def is_identity_field(template: dict, field: dict) -> bool:
    """True if field id is identity or equals any layer parent_id_field / ref_fields."""
    fid = field.get("id")
    if not fid:
        return False
    if fid in set(template.get("identity_fields") or []):
        return True
    for layer in template.get("layers") or []:
        if layer.get("parent_id_field") == fid:
            return True
        if fid in (layer.get("ref_fields") or []):
            return True
    return False


def value_shape(field: dict) -> dict:
    """Return provenance-wrapped empty value shape for a non-identity field."""
    value_type = field.get("value_type")
    if value_type == "composition":
        value: Any = {}
    elif value_type == "boolean":
        value = None
    else:
        value = ""
    shape: dict[str, Any] = {
        "value": value,
        "unit": "",
        "excerpt": "",
        "location": "",
    }
    if field.get("category") == "property":
        shape["source"] = ""
    return shape


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def find_excerpt_span(text: str, excerpt: str) -> tuple[int, int] | None:
    """Whitespace-normalized substring match; return original text [start, end)."""
    norm_excerpt = _normalize_ws(excerpt)
    if not norm_excerpt:
        return None

    # Build normalized string and map each norm index → original index.
    norm_chars: list[str] = []
    norm_to_orig: list[int] = []
    i = 0
    while i < len(text) and text[i].isspace():
        i += 1
    while i < len(text):
        if text[i].isspace():
            j = i
            while j < len(text) and text[j].isspace():
                j += 1
            if j >= len(text):
                break  # trailing whitespace omitted from normalized form
            norm_chars.append(" ")
            norm_to_orig.append(i)
            i = j
        else:
            norm_chars.append(text[i])
            norm_to_orig.append(i)
            i += 1

    norm_text = "".join(norm_chars)
    pos = norm_text.find(norm_excerpt)
    if pos < 0:
        return None

    start = norm_to_orig[pos]
    last = norm_to_orig[pos + len(norm_excerpt) - 1]
    return start, last + 1
