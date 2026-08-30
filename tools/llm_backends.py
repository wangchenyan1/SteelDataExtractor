"""抽取后端：真实多模态 Claude 兼容接口。

pipeline 只依赖 `Backend.call_json(system_prompt, text_prompt, images, hint)`。
ClaudeBackend 读取工作区 .env 里的 key，真正调用多模态接口。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.gpugeek.com/v1/messages"
DEFAULT_MODEL = "Vendor2/Claude-4.5-Sonnet"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_TIMEOUT = 600


def _load_env(start: Path) -> None:
    start = Path(start).resolve()
    candidates = [start / ".env"]
    if start.parent != start:
        candidates.append(start.parent / ".env")
    if len(start.parents) > 1:
        candidates.append(start.parents[1] / ".env")
    for env_path in candidates:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v


def parse_json_strict(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法解析 LLM 输出为 JSON: {text[:300]}")


class ClaudeBackend:
    name = "claude"

    def __init__(self, workspace_root: Path):
        _load_env(Path(workspace_root))

    def _key(self) -> str:
        key = os.getenv("LLM_API_KEY") or os.getenv("GPUGEEK_API_KEY")
        if not key:
            raise RuntimeError("LLM_API_KEY / GPUGEEK_API_KEY 未在 .env 中配置")
        return key

    def call_json(self, system_prompt: str, text_prompt: str,
                  images: list | None = None, hint: dict | None = None) -> dict:
        import requests  # 延迟导入，避免未装依赖时影响其它 CLI

        content: list[dict[str, Any]] = []
        for img in images or []:
            if img.get("label"):
                content.append({"type": "text", "text": f"[{img['label']}]"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": img["media_type"], "data": img["data"]},
            })
        content.append({"type": "text", "text": text_prompt})

        payload = {
            "model": os.getenv("LLM_MODEL") or DEFAULT_MODEL,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "x-api-key": self._key(),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        base_url = (os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        resp = requests.post(base_url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        raw = "".join(
            b.get("text", "") for b in data.get("content", [])
            if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
        return parse_json_strict(raw)


def get_backend(name: str, workspace_root: Path):
    key = (name or "claude").strip().lower()
    if key == "claude":
        return ClaudeBackend(workspace_root)
    raise ValueError(f"未知抽取后端 {name!r}。请使用 claude。")
