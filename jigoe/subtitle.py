"""字幕（SRT / WebVTT）と YouTube チャプターの出力。

読み上げ区間の実測尺からタイムラインを作るので、編集ソフト側で自動字幕を
かけ直すより正確に台本と一致する。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Cue:
    """字幕 1 枚。"""

    index: int
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _clock(seconds: float, *, comma: bool = True) -> str:
    seconds = max(0.0, seconds)
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    """SRT 形式の文字列にする。"""
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue.index}\n{_clock(cue.start)} --> {_clock(cue.end)}\n{cue.text}\n"
        )
    return "\n".join(blocks)


def to_vtt(cues: list[Cue]) -> str:
    """WebVTT 形式の文字列にする。"""
    blocks = ["WEBVTT\n"]
    for cue in cues:
        blocks.append(
            f"{cue.index}\n"
            f"{_clock(cue.start, comma=False)} --> {_clock(cue.end, comma=False)}\n"
            f"{cue.text}\n"
        )
    return "\n".join(blocks)


def to_youtube_chapters(
    chapters: list[tuple[str, float]],
    *,
    intro_threshold: float = 3.0,
    intro_title: str = "イントロ",
) -> str:
    """YouTube の概要欄にそのまま貼れるチャプター一覧。

    YouTube は最初のチャプターが 0:00 であることを要求する。最初の見出しが
    ``intro_threshold`` 秒より後に始まる場合は、その前に本編があるとみなして
    冒頭にイントロの行を足す。それ以内なら 0:00 に丸める。
    """
    if not chapters:
        return ""
    items = list(chapters)
    if items[0][1] > intro_threshold:
        items.insert(0, (intro_title, 0.0))
    else:
        items[0] = (items[0][0], 0.0)
    lines = []
    for title, start in items:
        total = int(start)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        stamp = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        lines.append(f"{stamp} {title}")
    return "\n".join(lines) + "\n"
