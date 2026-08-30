from pathlib import Path
import pytest
from tools.llm_backends import get_backend


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="未知抽取后端"):
        get_backend("nope", Path("."))


def test_claude_backend_name():
    # 不真正发请求；只确认工厂返回 claude
    backend = get_backend("claude", Path(__file__).resolve().parents[1])
    assert backend.name == "claude"
