"""音声合成エンジン群。

``jigoe.engines.base.get_engine(name)`` で取り出す。新しいエンジンを足すときは
:class:`~jigoe.engines.base.Engine` を継承して ``@register`` を付けるだけでよい。
"""

from __future__ import annotations

from .base import Engine, Voice, available_engines, get_engine, register

_LOADED = False


def load_builtin() -> None:
    """同梱エンジンを import してレジストリに登録する。"""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from . import elevenlabs, fishaudio, gptsovits, mock, sbv2, voicevox_like  # noqa: F401


__all__ = ["Engine", "Voice", "available_engines", "get_engine", "register", "load_builtin"]
