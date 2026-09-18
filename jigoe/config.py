"""設定の読み込み（TOML）。

探索順は ``--config`` で明示 → カレントの ``jigoe.toml`` →
``~/.config/jigoe/config.toml``。見つからなければ全部デフォルトで動く。

API キーは **設定ファイルに書かない**。``api_key_env`` で環境変数名だけを指定し、
値は実行時に環境から読む。設定ファイルは台本と一緒に git に入る想定のため。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError

CONFIG_FILENAME = "jigoe.toml"


def user_config_dir() -> Path:
    """XDG に沿ったユーザー設定ディレクトリ。"""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "jigoe"


@dataclass
class VoiceConfig:
    """話し方に関する設定。エンジン差を吸収した共通パラメータ。"""

    engine: str = "mock"
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    #: 感情/スタイル名。対応するエンジン（Style-Bert-VITS2 等）でのみ使う。
    style: str | None = None


@dataclass
class AudioConfig:
    """出力音声の整形。ポーズ長の既定値はリサーチの「0.3〜0.8秒」に合わせている。"""

    sample_rate: int = 44100
    #: ピークノーマライズの目標値（dBFS）。None で無効。
    peak_dbfs: float | None = -1.5
    lead_silence: float = 0.3
    tail_silence: float = 0.6
    sentence_pause: float = 0.35
    paragraph_pause: float = 0.7
    chapter_pause: float = 1.0

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ConfigError("audio.sample_rate は正の整数で指定してください")
        for name in (
            "lead_silence",
            "tail_silence",
            "sentence_pause",
            "paragraph_pause",
            "chapter_pause",
        ):
            if getattr(self, name) < 0:
                raise ConfigError(f"audio.{name} に負の値は指定できません")


@dataclass
class Config:
    """アプリ全体の設定。"""

    project_name: str = "jigoe project"
    out_dir: Path = Path("out")
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    #: 読み辞書ファイル（TSV/JSON）のパス
    lexicon_paths: list[Path] = field(default_factory=list)
    #: エンジン名 -> エンジン固有設定
    engines: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: 読み込み元（デバッグ表示用）。デフォルトのみなら None。
    source: Path | None = None

    def engine_options(self, name: str | None = None) -> dict[str, Any]:
        """指定エンジンの固有設定を返す（未設定なら空 dict）。"""
        return dict(self.engines.get(name or self.voice.engine, {}))

    def with_overrides(self, **kwargs: Any) -> "Config":
        """CLI 引数などで一部だけ差し替えた複製を返す。None の値は無視する。"""
        voice_overrides = {}
        top_overrides: dict[str, Any] = {}
        voice_names = {f.name for f in fields(VoiceConfig)}
        for key, value in kwargs.items():
            if value is None:
                continue
            if key in voice_names:
                voice_overrides[key] = value
            else:
                top_overrides[key] = value
        cfg = self
        if voice_overrides:
            cfg = replace(cfg, voice=replace(cfg.voice, **voice_overrides))
        if top_overrides:
            cfg = replace(cfg, **top_overrides)
        return cfg


def find_config(explicit: str | Path | None = None) -> Path | None:
    """使用する設定ファイルを探す。"""
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError(f"設定ファイルが見つかりません: {path}")
        return path
    local = Path.cwd() / CONFIG_FILENAME
    if local.is_file():
        return local
    user = user_config_dir() / "config.toml"
    if user.is_file():
        return user
    return None


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] はテーブルとして書いてください")
    return value


def _build(cls: type, data: dict[str, Any], section: str):
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(
            f"[{section}] に未知のキーがあります: {', '.join(sorted(unknown))}"
        )
    return cls(**data)


def load_config(explicit: str | Path | None = None) -> Config:
    """設定ファイルを読み込む。存在しなければデフォルト設定を返す。"""
    path = find_config(explicit)
    if path is None:
        return Config()
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} の TOML を解析できません: {exc}") from exc

    project = _section(data, "project")
    base = path.parent

    out_dir = Path(project.get("out_dir", "out"))
    if not out_dir.is_absolute():
        out_dir = base / out_dir

    lexicon_paths = []
    for entry in _section(data, "lexicon").get("paths", []):
        p = Path(entry)
        lexicon_paths.append(p if p.is_absolute() else base / p)

    engines = _section(data, "engines")
    for name, opts in engines.items():
        if not isinstance(opts, dict):
            raise ConfigError(f"[engines.{name}] はテーブルとして書いてください")

    return Config(
        project_name=project.get("name", "jigoe project"),
        out_dir=out_dir,
        voice=_build(VoiceConfig, _section(data, "voice"), "voice"),
        audio=_build(AudioConfig, _section(data, "audio"), "audio"),
        lexicon_paths=lexicon_paths,
        engines=engines,
        source=path,
    )


TEMPLATE = """\
# jigoe 設定ファイル
# API キーはここに書かず、api_key_env で環境変数名だけを指定すること。

[project]
name = "{name}"
out_dir = "out"

[voice]
# mock | aivisspeech | voicevox | sbv2 | gptsovits | elevenlabs | fishaudio
engine = "{engine}"
speed = 1.0
pitch = 0.0
volume = 1.0

[audio]
sample_rate = 44100
peak_dbfs = -1.5        # ピークノーマライズの目標。null で無効
lead_silence = 0.3      # 冒頭の無音
tail_silence = 0.6      # 末尾の無音
sentence_pause = 0.35   # 文と文のあいだ
paragraph_pause = 0.7   # 段落のあいだ
chapter_pause = 1.0     # 見出し（#）の前

[lexicon]
# 固有名詞の読み辞書。誤読チェックの対象にもなる
paths = ["lexicon/names.tsv"]

# --- ローカル（無料）---------------------------------------------------
[engines.aivisspeech]
base_url = "http://127.0.0.1:10101"
speaker = 888753760      # `jigoe voices` で確認できる話者 ID

[engines.voicevox]
base_url = "http://127.0.0.1:50021"
speaker = 3

[engines.sbv2]           # Style-Bert-VITS2 の API サーバー
base_url = "http://127.0.0.1:5000"
model_name = "my-voice"
speaker_name = ""
style = "Neutral"
style_weight = 1.0

[engines.gptsovits]      # GPT-SoVITS api_v2
base_url = "http://127.0.0.1:9880"
ref_audio_path = "refs/my_voice_10s.wav"
prompt_text = "参照音声で実際に喋っている内容をそのまま書く"
prompt_lang = "ja"
text_lang = "ja"

# --- クラウド（有料）---------------------------------------------------
[engines.elevenlabs]
api_key_env = "ELEVENLABS_API_KEY"
voice_id = ""            # 自分のクローン音声の ID
model_id = "eleven_multilingual_v2"
output_format = "pcm_24000"
stability = 0.5
similarity_boost = 0.75

[engines.fishaudio]
api_key_env = "FISH_AUDIO_API_KEY"
reference_id = ""        # 自分のクローンモデル ID
"""


def write_template(path: Path, name: str, engine: str) -> None:
    """設定ファイルの雛形を書き出す。既存ファイルは上書きしない。"""
    if path.exists():
        raise ConfigError(f"{path} は既に存在します")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE.format(name=name, engine=engine), encoding="utf-8")
