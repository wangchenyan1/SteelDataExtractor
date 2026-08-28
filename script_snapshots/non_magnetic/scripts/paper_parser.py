"""V4 paper.md 解析器：提取文本和图片资源。

UniParser 生成的 paper.md 格式：
  正文（含 markdown 标题、段落、表格）
  ![alt text](data:image/png;base64,xxxxx) 或 ![](images_from_md/xxx.png)

本模块提取：
  - 纯文本（图片位置替换为 [FIGURE_PLACEHOLDER_n]）
  - 图片列表（label + base64 数据）
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


# 图片压缩参数（防止 LLM payload 过大触发 400）
MAX_IMAGE_DIM = 768  # 单边最大像素（足够 Claude 看清组织结构）
MAX_IMAGE_BYTES = 200 * 1024  # 单张最大 200KB
JPEG_QUALITY = 75


def _maybe_compress(data: bytes, fmt: str) -> tuple[bytes, str]:
    """无条件缩放并重新编码为 JPEG（钢铁组织图 768px 足够 Claude 识别）。"""
    if not _PIL_AVAILABLE:
        return data, fmt
    try:
        img = Image.open(io.BytesIO(data))
        # 保留透明度的图片转为 RGB
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        # 缩放
        w, h = img.size
        if max(w, h) > MAX_IMAGE_DIM:
            scale = MAX_IMAGE_DIM / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        # 输出为 JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) < len(data):
            return compressed, "jpeg"
        return data, fmt
    except Exception:
        return data, fmt


# 匹配 markdown 图片：![alt](src) 或 ![alt](data:image/...)
IMAGE_PATTERN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)",
    re.DOTALL,
)
# 匹配 base64 data URL
DATA_URL_PATTERN = re.compile(r"data:image/(?P<fmt>\w+);base64,(?P<data>[^)\s]+)")
# 检测附近文本中的 Figure 编号
FIGURE_LABEL_PATTERN = re.compile(
    r"\b(?:Fig(?:ure)?\.?|图)\s*\.?\s*(\d+[a-zA-Z]?(?:[-,]\s*\d*[a-zA-Z]?)*)",
    re.IGNORECASE,
)


@dataclass
class ImageResource:
    """单张图片资源。"""
    index: int               # 在 paper.md 中出现的次序（从 1 开始）
    label: str               # 推断的图号 (如 "Figure 1a")，无则 ""
    alt: str                 # markdown alt 文本
    media_type: str          # image/png, image/jpeg, ...
    data_b64: str            # base64 数据
    nearby_text: str = ""    # 图片前后 200 字符的上下文，辅助分类


@dataclass
class ParsedPaper:
    """解析后的论文。"""
    paper_id: str
    text_with_placeholders: str  # 纯文本，图片位置替换为 [FIGURE_PLACEHOLDER_n]
    images: list[ImageResource] = field(default_factory=list)
    raw_chars: int = 0           # 原始 paper.md 字符数
    text_chars: int = 0          # 去掉 base64 后的纯文本字符数


def _infer_label_from_context(alt: str, before: str, after: str) -> str:
    """从 alt 文本和附近上下文推断 Figure 编号。"""
    for source in (alt, after[:200], before[-200:]):
        if not source:
            continue
        m = FIGURE_LABEL_PATTERN.search(source)
        if m:
            num = m.group(1).replace(" ", "")
            return f"Figure {num}"
    return ""


def parse_paper_md(paper_id: str, paper_md_path: Path) -> ParsedPaper:
    """解析 paper.md，分离出文本与图片。"""
    text = paper_md_path.read_text(encoding="utf-8", errors="replace")
    raw_chars = len(text)

    images: list[ImageResource] = []
    output_parts: list[str] = []
    cursor = 0
    img_index = 0

    for match in IMAGE_PATTERN.finditer(text):
        # 收集 match 之前的文本
        output_parts.append(text[cursor:match.start()])
        cursor = match.end()

        alt = match.group("alt").strip()
        src = match.group("src").strip()

        # 区分 base64 / 文件路径
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
            # 网络图片：跳过（占位符）
            output_parts.append(f"[IMAGE_SKIPPED:{src}]")
            continue
        else:
            # 文件路径：从同目录读取
            img_file = (paper_md_path.parent / src).resolve()
            if not img_file.exists():
                # 也试 images_from_md 子目录
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
        # 取前后 300 字符作为上下文
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

        # 在文本中放占位符
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
