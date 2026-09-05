import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_backend import FixtureBackend  # noqa: E402

FIXTURE_PARSED = Path(__file__).resolve().parent / "fixtures" / "parsed_results"


class _ParsedDir:
    """Prefer a test fixture paper when the product parsed_results copy is absent."""

    def __init__(self, primary: Path, fallback: Path):
        self._primary = Path(primary)
        self._fallback = Path(fallback)

    def exists(self):
        return self._primary.exists() or self._fallback.exists()

    def iterdir(self):
        seen = set()
        for base in (self._primary, self._fallback):
            if not base.exists():
                continue
            for p in base.iterdir():
                if p.name not in seen:
                    seen.add(p.name)
                    yield p

    def __truediv__(self, other):
        name = str(other)
        fallback_child = self._fallback / name
        primary_child = self._primary / name
        if fallback_child.exists() and not primary_child.exists():
            return fallback_child
        return primary_child


@pytest.fixture(autouse=True)
def _use_fixture_backend(monkeypatch):
    from tools import pipeline as pl

    monkeypatch.setattr(pl, "get_backend", lambda name, root, **kwargs: FixtureBackend(root))

    orig = pl._resolve_parsed_dir

    def _resolve(root, project_cfg):
        primary = orig(root, project_cfg)
        if primary is None:
            return FIXTURE_PARSED if FIXTURE_PARSED.exists() else None
        return _ParsedDir(primary, FIXTURE_PARSED)

    monkeypatch.setattr(pl, "_resolve_parsed_dir", _resolve)
