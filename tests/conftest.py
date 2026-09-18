import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """同意記録などがユーザーのホームを汚さないようにする。"""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("JIGOE_VOICE_IS_MINE", raising=False)
