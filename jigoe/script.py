"""台本のパース。

台本はプレーンテキスト（.txt / .md）。書式は最小限で、動画制作でそのまま使える
ことを優先している。

::

    # オープニング              ← 見出し。読み上げずチャプター（章）として記録
    // これはコメント。無視される

    @speed 1.05                 ← 以降の行に効くディレクティブ
    NBAの歴史には、記録よりも語り継がれた選手がいます。[[0.8]]その名はピストル・ピート。

    @pause 1.2                  ← 明示的な無音

``[[0.8]]`` は行内の無音（秒）。リサーチで「人間が担当すべき」とされた
重要箇所の“間”の調整（0.3〜0.8秒）は、この記法で台本側に残す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import AudioConfig
from .errors import ScriptError

#: 行内ポーズ記法 ``[[0.8]]``
INLINE_PAUSE = re.compile(r"\[\[\s*(\d+(?:\.\d+)?)\s*\]\]")

#: 文末になり得る文字
SENTENCE_ENDINGS = "。．！？!?"

#: 文末の直後に来ても文を切らない文字（閉じ括弧・閉じ引用符）
TRAILING = "」』）)】〉》\"'"

#: 長文を分割するときの候補位置
SOFT_BREAKS = "、，,；;：:"

_DIRECTIVES = {"pause", "speed", "style", "volume", "pitch"}


@dataclass
class Segment:
    """合成の最小単位。読み上げか無音のどちらか。"""

    kind: str  # "speech" | "pause"
    line_no: int
    text: str = ""
    seconds: float = 0.0
    speed: float | None = None
    pitch: float | None = None
    volume: float | None = None
    style: str | None = None
    #: この時点で有効な章タイトル
    chapter: str | None = None

    @property
    def is_speech(self) -> bool:
        return self.kind == "speech"

    def char_count(self) -> int:
        """課金・尺見積り用の文字数（読み上げ対象のみ）。"""
        return len(self.text) if self.is_speech else 0


@dataclass
class Chapter:
    """見出し。YouTube のチャプター出力に使う。"""

    title: str
    #: この章が始まる直前の segment インデックス
    segment_index: int
    line_no: int


@dataclass
class Script:
    """パース済みの台本。"""

    segments: list[Segment] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    source: Path | None = None

    @property
    def speech_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.is_speech]

    def char_count(self) -> int:
        """読み上げる総文字数。ポーズやコメントは含まない。"""
        return sum(s.char_count() for s in self.segments)

    def pause_seconds(self) -> float:
        return sum(s.seconds for s in self.segments if not s.is_speech)

    def text(self) -> str:
        """読み上げ部分だけを連結したテキスト。"""
        return "".join(s.text for s in self.segments if s.is_speech)


def split_sentences(text: str) -> list[str]:
    """日本語の文末記号で分割する。閉じ括弧は前の文に含める。"""
    out: list[str] = []
    buf: list[str] = []
    for i, ch in enumerate(text):
        buf.append(ch)
        if ch in SENTENCE_ENDINGS:
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt in TRAILING:
                continue
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def soft_wrap(sentence: str, max_chars: int) -> list[str]:
    """長すぎる文を読点などで分割する。

    エンジンによっては 1 リクエストあたりの文字数制限があり、また長い一息は
    抑揚が崩れやすい。区切り候補が無い場合のみ強制的に切る。
    """
    if max_chars <= 0 or len(sentence) <= max_chars:
        return [sentence]
    parts: list[str] = []
    rest = sentence
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cut = max((window.rfind(c) for c in SOFT_BREAKS), default=-1)
        if cut < max_chars // 3:  # 候補が先頭寄りすぎるなら諦めて等分
            cut = max_chars - 1
        parts.append(rest[: cut + 1].strip())
        rest = rest[cut + 1 :].lstrip()
    if rest:
        parts.append(rest)
    return [p for p in parts if p]


def _parse_directive(body: str, line_no: int) -> tuple[str, object]:
    parts = body.split(None, 1)
    name = parts[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ""
    if name not in _DIRECTIVES:
        raise ScriptError(
            f"{line_no} 行目: 未知のディレクティブ @{name}"
            f"（使えるのは {', '.join('@' + d for d in sorted(_DIRECTIVES))}）"
        )
    if name == "style":
        return name, (value or None)
    if not value:
        raise ScriptError(f"{line_no} 行目: @{name} には値が必要です")
    if value.lower() in {"reset", "default"}:
        return name, None
    try:
        return name, float(value)
    except ValueError as exc:
        raise ScriptError(f"{line_no} 行目: @{name} の値が数値ではありません: {value}") from exc


def parse_script(
    text: str,
    audio: AudioConfig | None = None,
    *,
    source: Path | None = None,
    max_chars: int = 120,
    speak_headings: bool = False,
) -> Script:
    """台本テキストを :class:`Script` に変換する。"""
    audio = audio or AudioConfig()
    script = Script(source=source)
    overrides: dict[str, object] = {"speed": None, "pitch": None, "volume": None, "style": None}
    chapter: str | None = None
    pending_pause = 0.0
    pending_explicit = False
    prev_blank = True  # 冒頭に段落ポーズを入れないため

    def push_pause(seconds: float, line_no: int, *, explicit: bool = False) -> None:
        """次の読み上げの前に入れる無音を積む。

        ``[[0.8]]`` や ``@pause`` で書かれた値は書き手の意図なのでそのまま採用し、
        文末・段落・見出しから自動で入る既定値に上書きされないようにする。
        暗黙どうしが重なった場合は長い方を採る。
        """
        nonlocal pending_pause, pending_explicit
        if explicit:
            pending_pause = seconds
            pending_explicit = True
        elif not pending_explicit:
            pending_pause = max(pending_pause, seconds)

    def flush_pause(line_no: int) -> None:
        nonlocal pending_pause, pending_explicit
        if pending_pause > 0 and script.segments:
            script.segments.append(
                Segment(kind="pause", line_no=line_no, seconds=round(pending_pause, 3))
            )
        pending_pause = 0.0
        pending_explicit = False

    def push_speech(chunk: str, line_no: int) -> None:
        flush_pause(line_no)
        script.segments.append(
            Segment(
                kind="speech",
                line_no=line_no,
                text=chunk,
                speed=overrides["speed"],  # type: ignore[arg-type]
                pitch=overrides["pitch"],  # type: ignore[arg-type]
                volume=overrides["volume"],  # type: ignore[arg-type]
                style=overrides["style"],  # type: ignore[arg-type]
                chapter=chapter,
            )
        )

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()

        if not line:
            if not prev_blank:
                push_pause(audio.paragraph_pause, line_no)
            prev_blank = True
            continue
        prev_blank = False

        if line.startswith("//"):
            continue

        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if not title:
                raise ScriptError(f"{line_no} 行目: 見出しが空です")
            chapter = title
            script.chapters.append(
                Chapter(title=title, segment_index=len(script.segments), line_no=line_no)
            )
            push_pause(audio.chapter_pause, line_no)
            if speak_headings:
                for sentence in split_sentences(title) or [title]:
                    for chunk in soft_wrap(sentence, max_chars):
                        push_speech(chunk, line_no)
                    push_pause(audio.sentence_pause, line_no)
            continue

        if line.startswith("@"):
            name, value = _parse_directive(line[1:], line_no)
            if name == "pause":
                push_pause(float(value), line_no, explicit=True)  # type: ignore[arg-type]
            else:
                overrides[name] = value
            continue

        # 通常の読み上げ行。行内ポーズで区切りつつ文単位に分割する。
        pieces = INLINE_PAUSE.split(line)
        for i, piece in enumerate(pieces):
            if i % 2 == 1:  # 正規表現のキャプチャ＝ポーズ秒数
                push_pause(float(piece), line_no, explicit=True)
                continue
            body = piece.strip()
            if not body:
                continue
            sentences = split_sentences(body)
            for j, sentence in enumerate(sentences):
                for chunk in soft_wrap(sentence, max_chars):
                    push_speech(chunk, line_no)
                if j < len(sentences) - 1:
                    push_pause(audio.sentence_pause, line_no)
        push_pause(audio.sentence_pause, line_no)

    if not script.speech_segments:
        raise ScriptError("読み上げる本文が台本にありません")
    return script


def load_script(path: str | Path, audio: AudioConfig | None = None, **kwargs) -> Script:
    """ファイルから台本を読み込む。"""
    p = Path(path)
    if not p.is_file():
        raise ScriptError(f"台本が見つかりません: {p}")
    return parse_script(p.read_text(encoding="utf-8"), audio, source=p, **kwargs)
