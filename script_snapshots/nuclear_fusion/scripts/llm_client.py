"""V4 LLM 客户端：支持文本 + 多模态（图片）调用。

设计目标：
- 一次性把论文文本 + 所有图片送进 Claude
- 强制输出严格 JSON
- 支持长超时（处理大论文）
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests


DEFAULT_BASE_URL = "https://api.gpugeek.com/v1/messages"
DEFAULT_MODEL = "Vendor2/Claude-4.5-Sonnet"
DEFAULT_MAX_TOKENS = 32768  # V4: 提高到 32K，避免大论文 JSON 截断
DEFAULT_TIMEOUT = 600  # 10 分钟


def _load_env() -> None:
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parent / ".env",      # Extract_data/non_magnetic/scripts/.env
        script_path.parents[1] / ".env",  # Extract_data/non_magnetic/.env
        script_path.parents[3] / ".env",  # shougang/.env
    ]
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


_load_env()


def get_api_key() -> str:
    key = os.getenv("LLM_API_KEY") or os.getenv("GPUGEEK_API_KEY")
    if not key:
        raise RuntimeError("LLM_API_KEY / GPUGEEK_API_KEY missing in .env")
    return key


def get_model() -> str:
    return os.getenv("LLM_MODEL") or DEFAULT_MODEL


def get_base_url() -> str:
    return (os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def call_multimodal(
    text_prompt: str,
    images: list[dict[str, str]] | None = None,
    system_prompt: str = "",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = 2,
) -> str:
    """调用 Claude 多模态接口。

    images 列表里每个元素：{'media_type': 'image/png', 'data': <base64>, 'label': 'Figure 1'}
    """
    content_blocks: list[dict[str, Any]] = []
    if images:
        for img in images:
            label = img.get("label", "")
            if label:
                content_blocks.append({"type": "text", "text": f"[{label}]"})
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img["media_type"],
                    "data": img["data"],
                },
            })
    content_blocks.append({"type": "text", "text": text_prompt})

    payload = {
        "model": get_model(),
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "system": system_prompt,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    headers = {
        "x-api-key": get_api_key(),
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(get_base_url(), headers=headers, json=payload, timeout=timeout)
            if response.status_code >= 400:
                # 打印详细错误信息
                err_body = response.text[:500] if response.text else "(no body)"
                raise requests.exceptions.HTTPError(
                    f"{response.status_code} Client Error: {err_body}",
                    response=response,
                )
            data = response.json()
            return "".join(
                b.get("text", "")
                for b in data.get("content", [])
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        except requests.exceptions.ProxyError as e:
            last_exc = e
            if attempt < max_retries:
                import time
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            if attempt < max_retries:
                import time
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise last_exc if last_exc else RuntimeError("Unknown LLM error")


def parse_json_strict(text: str) -> dict[str, Any]:
    """从 LLM 响应中抽取 JSON 对象（容忍 markdown 代码块包裹和闲聊开场白）。"""
    text = text.strip()
    # 直接尝试
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 优先寻找 ```json ... ``` 代码块
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass
    # 寻找以 {"paper_metadata" 开头的 JSON 块（更精确）
    paper_match = re.search(r'\{\s*"paper_metadata"', text)
    if paper_match:
        start = paper_match.start()
        # 平衡括号找结束
        depth = 0
        end = start
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        candidate = text[start:end]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    # 匹配第一个 { ... 最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法解析 LLM 输出为 JSON: {text[:500]}")
