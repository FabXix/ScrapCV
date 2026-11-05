import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapcv.bootstrap import build_app  # noqa: E402
from scrapcv.infrastructure.config import Settings  # noqa: E402


@pytest.fixture()
def demo_app(tmp_path):
    """Aplicación completa contra el Canvas simulado, sin modelo de lenguaje."""
    return build_app(Settings(data_dir=str(tmp_path / "data"), use_demo=True, use_llm=False), None)


@pytest.fixture()
def processed_app(demo_app):
    demo_app.run_all()
    return demo_app
