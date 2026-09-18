"""音声合成エンジンの共通インターフェース。

台本・読み辞書・音声整形はエンジンから独立している。エンジンが担うのは
「テキスト 1 片 → PCM」だけ。これにより、無料のローカルモデルで試作して
から、同じ台本のままクラウドの高品質モデルに差し替えられる。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..audio import Pcm
from ..config import VoiceConfig
from ..errors import ConfigError, EngineError


@dataclass(frozen=True)
class Voice:
    """エンジンが提供する話者。"""

    id: str
    name: str
    note: str = ""


class Engine(ABC):
    """音声合成エンジンの基底クラス。"""

    #: `[engines.<name>]` および `voice.engine` で使う識別子
    name: str = "base"
    #: 任意の声を複製し得るエンジンか（同意ゲートの対象になる）
    clones_voice: bool = False
    #: 人が読める短い説明
    description: str = ""

    def __init__(self, options: dict[str, Any] | None = None, voice: VoiceConfig | None = None):
        self.options = dict(options or {})
        self.voice = voice or VoiceConfig()

    # --- 設定ヘルパ -----------------------------------------------------

    def option(self, key: str, default: Any = None, *, required: bool = False) -> Any:
        value = self.options.get(key, default)
        if required and (value is None or value == ""):
            raise ConfigError(
                f"[engines.{self.name}] の {key} が未設定です。jigoe.toml に追記してください。"
            )
        return value

    def api_key(self, default_env: str) -> str:
        """環境変数から API キーを読む。設定ファイルには置かせない。"""
        env_name = self.option("api_key_env", default_env)
        key = os.environ.get(str(env_name), "").strip()
        if not key:
            raise ConfigError(
                f"環境変数 {env_name} に API キーが設定されていません。"
                f"例: export {env_name}='...'"
            )
        return key

    def base_url(self, default: str) -> str:
        return str(self.option("base_url", default)).rstrip("/")

    # --- エンジンが実装するもの -----------------------------------------

    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        speed: float | None = None,
        pitch: float | None = None,
        volume: float | None = None,
        style: str | None = None,
    ) -> Pcm:
        """テキスト 1 片を合成して PCM を返す。

        話速などに ``None`` を渡した場合は、設定ファイルの ``[voice]``、
        さらに無ければエンジンの既定値が使われる（:meth:`resolve`）。
        """

    def voices(self) -> list[Voice]:
        """利用可能な話者一覧。取得できないエンジンは空リストを返す。"""
        return []

    def health(self) -> str:
        """接続確認。問題なければ 1 行の状態メッセージを返す。"""
        self.voices()
        return f"{self.name}: 接続できました"

    # --- 共通処理 -------------------------------------------------------

    def resolve(self, key: str, override: float | None, default: float) -> float:
        """行ごとの上書き → 設定ファイルの [voice] → 既定値 の順で解決する。

        台本の ``@speed`` などの行単位指定が最優先。指定が無い（``None``）なら
        設定ファイルの値、それも無ければエンジンごとの既定値になる。
        """
        if override is not None:
            return float(override)
        value = getattr(self.voice, key, None)
        return float(value) if value is not None else default


_REGISTRY: dict[str, type[Engine]] = {}


def register(cls: type[Engine]) -> type[Engine]:
    """エンジンをレジストリに登録するデコレータ。"""
    _REGISTRY[cls.name] = cls
    return cls


def available_engines() -> dict[str, type[Engine]]:
    from . import load_builtin  # 循環 import を避けるため遅延

    load_builtin()
    return dict(_REGISTRY)


def get_engine(name: str, options: dict[str, Any] | None = None, voice: VoiceConfig | None = None) -> Engine:
    """名前からエンジンを組み立てる。"""
    registry = available_engines()
    cls = registry.get(name)
    if cls is None:
        raise EngineError(
            f"未知のエンジンです: {name}（使えるのは {', '.join(sorted(registry))}）"
        )
    return cls(options, voice)
