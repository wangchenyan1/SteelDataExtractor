"""Parse PDF papers with UniParser into paper.md + images (injectable client)."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

IMAGE_PATTERN = re.compile(
    r"!\[(figure|chart|image)\]\(data:image/([^;]+);base64,([A-Za-z0-9+/=\n\r]+?)\)"
)

DEFAULT_HOST = "https://uniparser.dp.tech/"


def get_api_key(api_key: str | None = None) -> str:
    key = api_key or os.getenv("UNIPARSER_API_KEY") or os.getenv("UP_API_KEY")
    if not key:
        raise RuntimeError(
            "未找到 UniParser API Key。请设置环境变量 UNIPARSER_API_KEY，"
            "或传入 api_key / 注入 client。"
        )
    return key


def image_extension(media_subtype: str) -> str:
    subtype = media_subtype.lower().split("+", 1)[0]
    if subtype == "jpeg":
        return "jpg"
    return subtype


def save_base64_images(content: str, paper_dir: Path) -> tuple[str, list[Path]]:
    image_dir = paper_dir / "images_from_md"
    image_dir.mkdir(parents=True, exist_ok=True)
    saved_images: list[Path] = []

    def save_image(match: re.Match[str]) -> str:
        img_type = match.group(1)
        ext = image_extension(match.group(2))
        b64_data = match.group(3).replace("\n", "").replace("\r", "")

        image_path = image_dir / f"{img_type}_{len(saved_images) + 1:03d}.{ext}"
        image_path.write_bytes(base64.b64decode(b64_data))
        saved_images.append(image_path)

        return f"![{img_type}](images_from_md/{image_path.name})"

    content_with_local_images = IMAGE_PATTERN.sub(save_image, content)
    return content_with_local_images, saved_images


def _build_client(*, host: str | None, api_key: str | None):
    from uniparser_tools.api.clients import UniParserClient

    return UniParserClient(host=host or DEFAULT_HOST, api_key=get_api_key(api_key))


def parse_pdf_to_paper(
    pdf_path: Path,
    output_dir: Path,
    *,
    client=None,
    overwrite: bool = False,
    host: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Parse one PDF into ``output_dir/<paper_id>/paper.md`` (+ images).

    Caller is responsible for copying the original PDF to ``source.pdf``.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    paper_id = pdf_path.stem

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    paper_dir = output_dir / paper_id
    paper_md_path = paper_dir / "paper.md"
    meta_path = paper_dir / "uniparser_submit_result.json"

    if paper_md_path.exists() and not overwrite:
        return {"paper_id": paper_id, "status": "skipped", "paper_md": str(paper_md_path)}

    if client is None:
        client = _build_client(host=host, api_key=api_key)

    from uniparser_tools.common.constant import FormatFlag, ParseMode, ParseModeTextual

    paper_dir.mkdir(parents=True, exist_ok=True)

    submit_result = client.trigger_file(
        file_path=str(pdf_path),
        sync=True,
        textual=ParseModeTextual.OCRHighQuality,
        table=ParseMode.OCRHighQuality,
        chart=ParseMode.DumpBase64,
        figure=ParseMode.DumpBase64,
        equation=ParseMode.OCRHighQuality,
    )
    meta_path.write_text(json.dumps(submit_result, ensure_ascii=False, indent=2), encoding="utf-8")

    token = submit_result["token"]
    result = client.get_formatted(
        token,
        content=True,
        objects=True,
        textual=FormatFlag.Markdown,
        table=FormatFlag.Markdown,
        equation=FormatFlag.Markdown,
        figure=FormatFlag.Markdown,
        chart=FormatFlag.Markdown,
    )

    content = result.get("content")
    if not content:
        raise RuntimeError(f"UniParser 返回内容为空: {paper_id}")

    content_with_local_images, saved_images = save_base64_images(content, paper_dir)
    paper_md_path.write_text(content_with_local_images, encoding="utf-8")

    return {
        "paper_id": paper_id,
        "status": "success",
        "paper_md": str(paper_md_path),
        "images": len(saved_images),
    }
