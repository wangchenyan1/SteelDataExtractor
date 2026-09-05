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
ENTITY_MAX_TOKENS = 32768
DEFAULT_TIMEOUT = 600


class LLMCallError(RuntimeError):
    """LLM 调用或 JSON 解析失败，附带完整 raw / stop_reason 供落盘。"""

    def __init__(
        self,
        message: str,
        *,
        raw_text: str = "",
        stop_reason: str | None = None,
        http_status: int | None = None,
        response_body: str = "",
    ):
        super().__init__(message)
        self.raw_text = raw_text or ""
        self.stop_reason = stop_reason
        self.http_status = http_status
        self.response_body = response_body or ""


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


def resolve_max_tokens(hint: dict | None = None) -> int:
    """骨架(entity) 用更大窗口；hint.max_tokens 可覆盖。"""
    hint = hint or {}
    override = hint.get("max_tokens")
    if override is not None:
        try:
            return max(1, int(override))
        except (TypeError, ValueError):
            pass
    if hint.get("stage") in ("entity", "figure_extract"):
        return ENTITY_MAX_TOKENS
    return DEFAULT_MAX_TOKENS


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


def extract_text_and_stop(data: dict) -> tuple[str, str | None]:
    raw = "".join(
        b.get("text", "") for b in data.get("content", [])
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    stop = data.get("stop_reason")
    if stop is not None:
        stop = str(stop)
    return raw, stop


class ClaudeBackend:
    name = "claude"

    def __init__(
        self,
        workspace_root: Path,
        model: str | None = None,
        base_url: str | None = None,
    ):
        _load_env(Path(workspace_root))
        self.model = (model or os.getenv("LLM_MODEL") or DEFAULT_MODEL).strip()
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

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

        max_tokens = resolve_max_tokens(hint)
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "x-api-key": self._key(),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        resp = requests.post(self.base_url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
        if resp.status_code >= 400:
            body = resp.text or ""
            raise LLMCallError(
                f"LLM HTTP {resp.status_code}: {body[:300]}",
                http_status=resp.status_code,
                response_body=body,
                raw_text=body,
            )
        try:
            data = resp.json()
        except ValueError as exc:
            body = resp.text or ""
            raise LLMCallError(
                f"LLM 响应不是 JSON: {body[:300]}",
                http_status=resp.status_code,
                response_body=body,
                raw_text=body,
            ) from exc

        raw, stop_reason = extract_text_and_stop(data if isinstance(data, dict) else {})
        try:
            return parse_json_strict(raw)
        except ValueError as exc:
            raise LLMCallError(
                str(exc),
                raw_text=raw,
                stop_reason=stop_reason,
                http_status=resp.status_code,
                response_body=json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else (resp.text or ""),
            ) from exc


def get_backend(
    name: str,
    workspace_root: Path,
    model: str | None = None,
    base_url: str | None = None,
):
    key = (name or "claude").strip().lower()
    if key == "claude":
        return ClaudeBackend(workspace_root, model=model, base_url=base_url)
    raise ValueError(f"未知抽取后端 {name!r}。请使用 claude。")
