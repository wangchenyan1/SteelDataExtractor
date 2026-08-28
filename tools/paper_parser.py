"""paper.md 解析器（工具自带、无外部强依赖版）。

从 UniParser 生成的 paper.md 中分离：
- 纯文本（图片位置替换为 [FIGURE_PLACEHOLDER_n]）
- 图片列表（label + base64 数据 + 附近上下文）

PIL 可选：安装了则压缩图片，未安装则原样使用。
"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


MAX_IMAGE_DIM = 768
JPEG_QUALITY = 75


def _maybe_compress(data: bytes, fmt: str) -> tuple[bytes, str]:
    if not _PIL_AVAILABLE:
        return data, fmt
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_IMAGE_DIM:
            scale = MAX_IMAGE_DIM / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) < len(data):
            return compressed, "jpeg"
        return data, fmt
    except Exception:
        return data, fmt


IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)", re.DOTALL)
DATA_URL_PATTERN = re.compile(r"data:image/(?P<fmt>\w+);base64,(?P<data>[^)\s]+)")
FIGURE_LABEL_PATTERN = re.compile(
    r"\b(?:Fig(?:ure)?\.?|图)\s*\.?\s*(\d+[a-zA-Z]?(?:[-,]\s*\d*[a-zA-Z]?)*)",
    re.IGNORECASE,
)


@dataclass
class ImageResource:
    index: int
    label: str
    alt: str
    media_type: str
    data_b64: str
    nearby_text: str = ""


@dataclass
class ParsedPaper:
    paper_id: str
    text_with_placeholders: str
    images: list = field(default_factory=list)
    raw_chars: int = 0
    text_chars: int = 0


def _infer_label_from_context(alt: str, before: str, after: str) -> str:
    for source in (alt, after[:200], before[-200:]):
        if not source:
            continue
        m = FIGURE_LABEL_PATTERN.search(source)
        if m:
            num = m.group(1).replace(" ", "")
            return f"Figure {num}"
    return ""


def parse_paper_md(paper_id: str, paper_md_path: Path) -> ParsedPaper:
    paper_md_path = Path(paper_md_path)
    text = paper_md_path.read_text(encoding="utf-8", errors="replace")
    raw_chars = len(text)

    images: list = []
    output_parts: list = []
    cursor = 0
    img_index = 0

    for match in IMAGE_PATTERN.finditer(text):
        output_parts.append(text[cursor:match.start()])
        cursor = match.end()

        alt = match.group("alt").strip()
        src = match.group("src").strip()

        data_match = DATA_URL_PATTERN.match(src)
        if data_match:
            fmt = data_match.group("fmt").lower()
            try:
                raw_bytes = base64.b64decode(data_match.group("data"))
                raw_bytes, fmt = _maybe_compress(raw_bytes, fmt)
                data_b64 = base64.b64encode(raw_bytes).decode("ascii")
            except Exception:
                data_b64 = data_match.group("data")
        elif src.startswith(("http://", "https://")):
            output_parts.append(f"[IMAGE_SKIPPED:{src}]")
            continue
        else:
            img_file = (paper_md_path.parent / src).resolve()
            if not img_file.exists():
                alt_file = paper_md_path.parent / "images_from_md" / Path(src).name
                if alt_file.exists():
                    img_file = alt_file
                else:
                    output_parts.append(f"[IMAGE_MISSING:{src}]")
                    continue
            fmt = img_file.suffix.lstrip(".").lower() or "png"
            if fmt == "jpg":
                fmt = "jpeg"
            raw_bytes = img_file.read_bytes()
            raw_bytes, fmt = _maybe_compress(raw_bytes, fmt)
            data_b64 = base64.b64encode(raw_bytes).decode("ascii")

        img_index += 1
        before = text[max(0, match.start() - 300):match.start()]
        after = text[match.end():match.end() + 300]
        label = _infer_label_from_context(alt, before, after)

        images.append(ImageResource(
            index=img_index,
            label=label,
            alt=alt,
            media_type=f"image/{fmt}",
            data_b64=data_b64,
            nearby_text=(before[-150:] + " ... " + after[:150]).strip(),
        ))

        placeholder = f"[FIGURE_PLACEHOLDER_{img_index}"
        if label:
            placeholder += f": {label}"
        if alt:
            placeholder += f" (alt: {alt})"
        placeholder += "]"
        output_parts.append(placeholder)

    output_parts.append(text[cursor:])
    text_clean = "".join(output_parts)

    return ParsedPaper(
        paper_id=paper_id,
        text_with_placeholders=text_clean,
        images=images,
        raw_chars=raw_chars,
        text_chars=len(text_clean),
    )
